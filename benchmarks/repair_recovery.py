"""Reference repair workflow on a real repository, with a feedback-boundary kill.

Fixed plans intentionally fail the first acceptance. This is infrastructure
evidence, not neural-model capability or an improvement in benchmark success.
"""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

from recovery_matrix import wait_stage


def log_hashes(directory):
    return {
        file.name: hashlib.sha256(file.read_bytes()).hexdigest()
        for file in sorted((directory / "attempts/000").glob("verification-*.log"))
    }


def case(repo, task, directory, interrupt):
    directory.mkdir()
    argv = [
        sys.executable,
        "-m",
        "agent_lab.repair",
        "--repo",
        str(repo),
        "--task",
        str(task),
        "--run-dir",
        str(directory),
    ]
    before = None
    if interrupt:
        with (
            (directory / "interrupted.stdout.jsonl").open("wb") as out,
            (directory / "interrupted.stderr.log").open("wb") as errors,
        ):
            process = subprocess.Popen(
                argv + ["--hold-after", "repair_feedback"],
                stdout=subprocess.PIPE,
                stderr=errors,
                start_new_session=True,
            )
            try:
                event = wait_stage(process, "repair_feedback", out)
                assert event["attempt"] == 0
                before = log_hashes(directory)
                assert before
                os.kill(process.pid, signal.SIGKILL)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=15)
                process.stdout.close()
            assert process.returncode == -signal.SIGKILL
    with (
        (directory / "resumed.stdout.jsonl").open("wb") as out,
        (directory / "resumed.stderr.log").open("wb") as errors,
    ):
        process = subprocess.Popen(
            argv, stdout=out, stderr=errors, start_new_session=True
        )
        try:
            code = process.wait(timeout=600)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=15)
    if code:
        raise RuntimeError("Repair workflow failed; preserve the attempt evidence.")
    result = json.loads((directory / "result.json").read_text())
    assert result["accepted_attempt"] == 1
    assert [r["status"] for r in result["attempts"]] == [
        "verification_failed",
        "ready_for_review",
    ]
    after = log_hashes(directory)
    if before is not None:
        assert before == after, (
            "The failed verifier was unexpectedly repeated on resume"
        )
    return {
        "case": directory.name,
        "signal": "SIGKILL" if interrupt else None,
        "failure_logs_before_kill": before,
        "failure_logs_after_resume": after,
        "result": result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    task = json.loads(args.task.read_text())
    if task.get("model", {}).get("mode") != "scripted":
        parser.error("This workflow requires an explicit scripted reference task.")
    output = args.output.resolve()
    output.mkdir(parents=True)
    report = {
        "scope": __doc__,
        "task_sha256": hashlib.sha256(
            json.dumps(task, sort_keys=True).encode()
        ).hexdigest(),
        "base_commit": task["base_commit"],
        "model_inference": False,
        "cases": [],
    }
    for name, interrupt in (("uninterrupted", False), ("feedback-sigkill", True)):
        row = case(args.repo.resolve(), args.task.resolve(), output / name, interrupt)
        report["cases"].append(row)
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps(
                {"case": name, "accepted_attempt": row["result"]["accepted_attempt"]}
            ),
            flush=True,
        )
    assert len({r["result"]["patch_sha256"] for r in report["cases"]}) == 1
    report["same_patch"] = True
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"cases": 2, "same_patch": True}), flush=True)


if __name__ == "__main__":
    main()
