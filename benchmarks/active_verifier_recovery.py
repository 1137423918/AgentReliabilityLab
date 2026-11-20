"""Kill only a worker while its real upstream pytest process is running."""

import argparse
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from recovery_matrix import execute_case


def identity(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[19] if fields[0] not in ("Z", "X") else None
    except FileNotFoundError:
        return None


def descendants(pid):
    try:
        children = Path(f"/proc/{pid}/task/{pid}/children").read_text().split()
    except FileNotFoundError:
        return []
    result = []
    for value in children:
        child = int(value)
        result.append(child)
        result.extend(descendants(child))
    return result


def interrupt_pytest(repo, task_path, directory, expected):
    directory.mkdir()
    argv = [
        sys.executable,
        "-m",
        "agent_lab.worker",
        "--repo",
        str(repo),
        "--task",
        str(task_path),
        "--run-dir",
        str(directory),
    ]
    observed = []
    command_group = None
    with (
        (directory / "interrupted.stdout.jsonl").open("wb") as out,
        (directory / "interrupted.stderr.log").open("wb") as errors,
    ):
        worker = subprocess.Popen(
            argv, stdout=out, stderr=errors, start_new_session=True
        )
        try:
            deadline = time.monotonic() + 180
            while not observed:
                if worker.poll() is not None:
                    raise RuntimeError("The worker exited before pytest was observed.")
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "No running upstream pytest process was observed."
                    )
                for pid in descendants(worker.pid):
                    try:
                        actual = (
                            Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")[:-1]
                        )
                    except FileNotFoundError:
                        continue
                    if [arg.decode() for arg in actual][1:] == expected[1:]:
                        observed = [
                            {"pid": owned, "start_ticks": identity(owned)}
                            for owned in [pid, *descendants(pid)]
                        ]
                        if not all(row["start_ticks"] for row in observed):
                            observed = []
                            continue
                        command_group = os.getpgid(pid)
                        break
                if not observed:
                    time.sleep(0.01)
            os.kill(worker.pid, signal.SIGKILL)
            worker.wait(timeout=10)
            if worker.returncode != -signal.SIGKILL:
                raise RuntimeError("Only the worker should be killed with SIGKILL.")
            deadline = time.monotonic() + 15
            with (directory / "worker.lock").open("a") as lock:
                while True:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        if any(
                            identity(row["pid"]) == row["start_ticks"]
                            for row in observed
                        ):
                            raise RuntimeError(
                                "The old verifier survived release of the run lock."
                            )
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError(
                                "The supervisor did not release the run lock."
                            )
                        time.sleep(0.01)
            observation = {
                "signal": "SIGKILL",
                "target": "worker PID only",
                "observed_command": expected,
                "observed_processes": observed,
                "old_verifier_stopped_before_lock_release": True,
            }
            (directory / "interruption.json").write_text(
                json.dumps(observation, indent=2) + "\n"
            )
        finally:
            if worker.poll() is None:
                os.killpg(worker.pid, signal.SIGKILL)
                worker.wait(timeout=10)
            if command_group is not None and any(
                identity(row["pid"]) == row["start_ticks"] for row in observed
            ):
                os.killpg(command_group, signal.SIGKILL)
    with (
        (directory / "resumed.stdout.jsonl").open("wb") as out,
        (directory / "resumed.stderr.log").open("wb") as errors,
    ):
        result = subprocess.run(argv, stdout=out, stderr=errors, timeout=600)
    if result.returncode:
        raise RuntimeError("Resumed verification failed; preserve logs.")
    return {
        "interruption": observation,
        "result": json.loads((directory / "result.json").read_text()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, task_path, output = (
        args.repo.resolve(),
        args.task.resolve(),
        args.output.resolve(),
    )
    task = json.loads(task_path.read_text())
    if task.get("model", {}).get("mode") != "scripted":
        parser.error("Only scripted infrastructure experiments are supported.")
    commands = [
        row["argv"] for row in task["verify"] if row["argv"][1:3] == ["-m", "pytest"]
    ]
    if len(commands) != 1:
        parser.error("Provide exactly one explicit upstream pytest verifier.")
    output.mkdir()
    reference = execute_case(repo, task_path, output / "uninterrupted", None)
    recovered = interrupt_pytest(
        repo, task_path, output / "active-verifier", commands[0]
    )
    for result in (reference["result"], recovered["result"]):
        if result["status"] != "ready_for_review" or any(
            row["returncode"] for row in result["verification"]
        ):
            raise RuntimeError("The task did not produce a verified review artifact.")
    if reference["result"]["patch_sha256"] != recovered["result"]["patch_sha256"]:
        raise RuntimeError("Resuming after killing the worker changed the patch.")
    report = {
        "scope": "real repository; running upstream pytest; worker-only SIGKILL; scripted model",
        "base_commit": task["base_commit"],
        "task_sha256": hashlib.sha256(
            json.dumps(task, sort_keys=True).encode()
        ).hexdigest(),
        "reference": reference,
        "recovered": recovered,
        "same_patch": True,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {"same_patch": True, "old_verifier_stopped_before_lock_release": True}
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
