"""Run a predeclared normal/checkpoint-resume pilot against a local real model.

The operator starts a pinned OpenAI-compatible service before invoking this.
Failures remain in the report; a single task is not a benchmark success rate.
"""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from recovery_matrix import wait_stage


def run_case(repo, task_path, directory, fault, deadline):
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
    observation = None
    started = time.monotonic()
    if fault:
        with (
            (directory / "interrupted.stdout.jsonl").open("wb") as trace,
            (directory / "interrupted.stderr.log").open("wb") as errors,
        ):
            worker = subprocess.Popen(
                argv + ["--hold-after", "checkpoint"],
                stdout=subprocess.PIPE,
                stderr=errors,
                start_new_session=True,
            )
            try:
                observation = wait_stage(worker, "checkpoint", trace)
            finally:
                if worker.poll() is None:
                    os.killpg(worker.pid, signal.SIGKILL)
                worker.wait(timeout=15)
                worker.stdout.close()
            if worker.returncode != -signal.SIGKILL:
                raise RuntimeError(
                    "The checkpoint interruption did not kill a live worker."
                )
    with (
        (directory / "resumed.stdout.jsonl").open("wb") as out,
        (directory / "resumed.stderr.log").open("wb") as errors,
    ):
        worker = subprocess.Popen(
            argv, stdout=out, stderr=errors, start_new_session=True
        )
        try:
            remaining = deadline - (time.monotonic() - started)
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, deadline)
            returncode = worker.wait(timeout=remaining)
            timed_out = False
        except subprocess.TimeoutExpired:
            os.killpg(worker.pid, signal.SIGKILL)
            worker.wait(timeout=15)
            returncode, timed_out = worker.returncode, True
    result_path = directory / "result.json"
    state_path = directory / "status.json"
    result = json.loads(result_path.read_text()) if result_path.exists() else None
    state = json.loads(state_path.read_text()) if state_path.exists() else None
    success = (
        returncode == 0
        and result is not None
        and result["status"] == "ready_for_review"
    )
    if (
        observation is not None
        and result is not None
        and result["tool_results"] < observation["tool_results"]
    ):
        raise RuntimeError("Completed tool progress disappeared after resume.")
    return {
        "case": directory.name,
        "checkpoint_interruption": observation,
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - started, 3),
        "verified_patch": success,
        "result": result,
        "state": state,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case-deadline-seconds", type=float, default=600)
    args = parser.parse_args()
    task = json.loads(args.task.read_text())
    if task.get("max_repair_attempts", 0):
        parser.error(
            "This pilot is single-candidate; use agent_lab.repair for repair tasks."
        )
    if task.get("model", {}).get("mode") != "local-openai":
        parser.error(
            "A local-openai model task is required; scripted responses are not accepted."
        )
    if args.case_deadline_seconds < 180:
        parser.error("Allow at least the 180-second checkpoint observation window.")
    output = args.output.resolve()
    output.mkdir(parents=True)
    report = {
        "scope": "One public maintenance task, two predeclared trials; operator-provided local model endpoint; not SWE-bench or a general success rate",
        "task_sha256": hashlib.sha256(
            json.dumps(task, sort_keys=True).encode()
        ).hexdigest(),
        "base_commit": task["base_commit"],
        "model": task["model"],
        "cases": [],
    }
    for name, fault in (("normal", False), ("checkpoint-resume", True)):
        try:
            case = run_case(
                args.repo.resolve(),
                args.task.resolve(),
                output / name,
                fault,
                args.case_deadline_seconds,
            )
        except Exception as error:
            case = {
                "case": name,
                "verified_patch": False,
                "harness_error": type(error).__name__,
            }
        report["cases"].append(case)
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(
            json.dumps({"case": name, "verified_patch": case["verified_patch"]}),
            flush=True,
        )
    patches = [
        row.get("result", {}).get("patch_sha256")
        for row in report["cases"]
        if row.get("result")
    ]
    report["same_patch"] = len(patches) == 2 and len(set(patches)) == 1
    report["verified_trials"] = sum(row["verified_patch"] for row in report["cases"])
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "verified_trials": report["verified_trials"],
                "planned_trials": 2,
                "same_patch": report["same_patch"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
