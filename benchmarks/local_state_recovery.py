"""Real filesystem admission, local reference recovery and audit-only backup."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import zipfile

from recovery_matrix import execute_case

from agent_lab.storage import STATE_FILES, admit_state_directory, filesystem_type


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprints(directory):
    return {
        name: {
            "sha256": sha(directory / name),
            "bytes": (directory / name).stat().st_size,
            "mtime_ns": (directory / name).stat().st_mtime_ns,
        }
        for name in STATE_FILES
        if (directory / name).is_file()
    }


def reject(repo, task, directory, prefix):
    before = fingerprints(directory) if directory.is_dir() else None
    started = time.monotonic()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent_lab.worker",
            "--repo",
            str(repo),
            "--task",
            str(task),
            "--run-dir",
            str(directory),
        ],
        capture_output=True,
        timeout=120,
    )
    prefix.with_suffix(".stdout.log").write_bytes(result.stdout)
    prefix.with_suffix(".stderr.log").write_bytes(result.stderr)
    assert result.returncode == 2
    error = json.loads(result.stderr)
    assert "filesystem 'nfs4' is not admitted" in error["error"]
    if before is None:
        assert not directory.exists()
    else:
        assert before == fingerprints(directory)
    return {
        "returncode": result.returncode,
        "wall_seconds": time.monotonic() - started,
        "new_directory_created": False if before is None else None,
        "existing_state_byte_and_mtime_unchanged": True if before is not None else None,
        "error": error,
    }


def inspect(directory, output):
    result = subprocess.run(
        [sys.executable, "-m", "agent_lab.inspect_run", "--run-dir", str(directory)],
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr.decode()
    output.write_bytes(result.stdout)
    return json.loads(result.stdout)


def backup_for_audit(directory, destination, output):
    assert (
        admit_state_directory(directory)
        == filesystem_type(destination.parent)
        == "ext4"
    )
    destination.mkdir(mode=0o700)
    assert admit_state_directory(destination) == "ext4"
    descriptor = os.open(directory / "worker.lock", os.O_RDONLY | os.O_NOFOLLOW)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original = inspect(directory, output / "source-inspection.json")
        before = sha(directory / "checkpoints.sqlite")
        wal = directory / "checkpoints.sqlite-wal"
        wal_before = wal.read_bytes() if wal.exists() else b""
        connection = sqlite3.connect(
            (directory / "checkpoints.sqlite").as_uri() + "?mode=ro", uri=True
        )
        target = sqlite3.connect(destination / "checkpoints.sqlite")
        try:
            connection.execute("PRAGMA query_only=ON")
            connection.execute("BEGIN")
            connection.backup(target)
            assert (
                target.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
            )
            assert target.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        finally:
            target.close()
            connection.close()
        assert sha(directory / "checkpoints.sqlite") == before
        assert (wal.read_bytes() if wal.exists() else b"") == wal_before
        for name in [
            "manifest.json",
            "status.json",
            "result.json",
            "verification.json",
            "patch.diff",
        ]:
            shutil.copyfile(directory / name, destination / name)
        restored = inspect(destination, output / "backup-inspection.json")
        assert original == restored
        # The archive contains private conversation state and stays out of public evidence.
        private = output / "private-archive"
        private.mkdir(mode=0o700)
        archive = private / "audit-snapshot.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(destination.iterdir()):
                assert path.name not in [
                    "checkpoints.sqlite-wal",
                    "checkpoints.sqlite-shm",
                ]
                bundle.write(path, path.name)
        return {
            "source_data_unchanged": True,
            "original_wal_frames_unchanged": True,
            "method": "Exclusive existing worker lock; SQLite backup API to local standalone DELETE-journal snapshot; no live directory move.",
            "audit_output_identical": True,
            "snapshot_db_sha256": sha(destination / "checkpoints.sqlite"),
            "private_archive_sha256": sha(archive),
            "private_archive_bytes": archive.stat().st_size,
            "archive_published": False,
            "snapshot_resumed_as_worker": False,
            "scope": "Read-only audit reconstruction, not executable worktree relocation or cross-host resume.",
        }
    finally:
        os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["repo", "task", "protocol", "local-root", "old-network-run", "output"]:
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    protocol = json.loads(args.protocol.read_text())
    for name, digest in protocol["source_sha256"].items():
        assert sha(root / name) == digest, name
    assert sha(args.task) == protocol["task_file_sha256"]
    task = json.loads(args.task.read_text())
    assert task["model"]["mode"] == "scripted" and len(task["model"]["plan"]) == 4
    assert args.local_root.is_dir() and admit_state_directory(args.local_root) == "ext4"
    assert (
        filesystem_type(args.output.parent)
        == filesystem_type(args.old_network_run)
        == "nfs4"
    )
    manifest = json.loads((args.old_network_run / "manifest.json").read_text())
    assert (
        manifest["task"] == task
        and Path(manifest["repo"]).resolve() == args.repo.resolve()
    )
    assert (
        json.loads((args.old_network_run / "result.json").read_text())["status"]
        == "ready_for_review"
    )
    args.output.mkdir(exist_ok=False)
    report = {
        "scope": protocol["scope"],
        "protocol_sha256": sha(args.protocol),
        "model_inference": False,
        "gpu_used": False,
        "local_filesystem": "ext4",
        "rejected_filesystem": "nfs4",
        "new_run_rejection": reject(
            args.repo,
            args.task,
            args.output / "rejected-new-run",
            args.output / "reject-new",
        ),
        "old_run_rejection": reject(
            args.repo, args.task, args.old_network_run, args.output / "reject-old"
        ),
        "cases": [],
    }
    write(args.output / "progress.json", report)
    for name, fault in [("local-normal", None), ("local-checkpoint", "checkpoint")]:
        directory = args.local_root / name
        row = execute_case(args.repo.resolve(), args.task.resolve(), directory, fault)
        row["actual_filesystem"] = admit_state_directory(directory)
        row["inspection"] = inspect(
            directory, args.output / (name + "-inspection.json")
        )
        assert row["result"]["tool_results"] == 4
        portable = args.output / "cases" / name
        portable.mkdir(parents=True)
        for filename in [
            "result.json",
            "manifest.json",
            "status.json",
            "patch.diff",
            "verification.json",
            "resumed.stdout.jsonl",
            "resumed.stderr.log",
            "interrupted.stdout.jsonl",
            "interrupted.stderr.log",
        ] + [f"verification-{i}.log" for i in range(4)]:
            if (directory / filename).is_file():
                shutil.copyfile(directory / filename, portable / filename)
        report["cases"].append(row)
        write(args.output / "progress.json", report)
        print(
            json.dumps(
                {
                    "case": name,
                    "status": row["result"]["status"],
                    "filesystem": row["actual_filesystem"],
                }
            ),
            flush=True,
        )
    assert len({row["result"]["patch_sha256"] for row in report["cases"]}) == 1
    assert report["cases"][1]["interrupted_progress"]["tool_results"] == 1
    report["backup"] = backup_for_audit(
        args.local_root / "local-checkpoint",
        args.local_root / "audit-snapshot",
        args.output,
    )
    report["same_patch"] = True
    report["source_sha256"] = protocol["source_sha256"]
    write(args.output / "report.json", report)
    print(
        json.dumps(
            {
                "same_patch": True,
                "new_network_state_created": False,
                "old_network_state_unchanged": True,
                "backup_audit_identical": True,
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
