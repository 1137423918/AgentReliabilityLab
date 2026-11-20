"""Run a pinned real-repository task, kill workers, and compare recovered patches.

This is a scripted infrastructure experiment, never a model capability score.
"""

import argparse
import hashlib
import importlib.metadata
import json
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path


def wait_stage(process, stage, trace):
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    buffered = b""
    deadline = time.monotonic() + 180
    try:
        while time.monotonic() < deadline:
            if not selector.select(timeout=1):
                continue
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                break
            buffered += chunk
            while b"\n" in buffered:
                line, buffered = buffered.split(b"\n", 1)
                trace.write(line + b"\n")
                trace.flush()
                event = json.loads(line)
                if event.get("stage") == stage:
                    return event
        raise RuntimeError(
            f"Worker did not reach {stage} before the observation deadline."
        )
    finally:
        selector.close()


def execute_case(repo, task_path, directory, stage):
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
    interrupted = None
    if stage:
        with (
            (directory / "interrupted.stdout.jsonl").open("wb") as trace,
            (directory / "interrupted.stderr.log").open("wb") as errors,
        ):
            process = subprocess.Popen(
                argv + ["--hold-after", stage],
                stdout=subprocess.PIPE,
                stderr=errors,
                start_new_session=True,
            )
            try:
                interrupted = wait_stage(process, stage, trace)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=15)
                process.stdout.close()
            if process.returncode != -signal.SIGKILL:
                raise RuntimeError(
                    "The interrupted worker did not terminate with SIGKILL."
                )
    with (
        (directory / "resumed.stdout.jsonl").open("wb") as out,
        (directory / "resumed.stderr.log").open("wb") as errors,
    ):
        process = subprocess.run(
            argv, stdout=out, stderr=errors, timeout=600, start_new_session=True
        )
    if process.returncode:
        raise RuntimeError(
            f"Maintenance worker failed in {directory.name}; preserve its logs."
        )
    result = json.loads((directory / "result.json").read_text())
    if result["status"] != "ready_for_review" or not result["patch_bytes"]:
        raise RuntimeError("The run did not produce a nonempty reviewable patch.")
    if not result["verification"] or any(
        row["returncode"] for row in result["verification"]
    ):
        raise RuntimeError("Verification did not pass.")
    events = [
        json.loads(line)
        for line in (directory / "resumed.stdout.jsonl").read_text().splitlines()
    ]
    checkpoint_counts = [
        event["tool_results"] for event in events if event.get("stage") == "checkpoint"
    ]
    if stage == "checkpoint" and (
        not checkpoint_counts or checkpoint_counts[0] <= interrupted["tool_results"]
    ):
        raise RuntimeError("The resumed trace did not advance the saved tool progress.")
    return {
        "case": directory.name,
        "fault_stage": stage,
        "signal": "SIGKILL" if stage else None,
        "interrupted_progress": interrupted,
        "resumed_checkpoint_tool_counts": checkpoint_counts,
        "result": result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    task = json.loads(args.task.read_text())
    if task.get("model", {}).get("mode") != "scripted":
        parser.error("This fault experiment requires an explicitly scripted plan.")
    args.output.mkdir(parents=True)
    report = {
        "scope": "real repository and verification; scripted model; process-boundary faults only",
        "base_commit": task["base_commit"],
        "task_sha256": hashlib.sha256(
            json.dumps(task, sort_keys=True).encode()
        ).hexdigest(),
        "packages": {
            name: importlib.metadata.version(name)
            for name in ("deepagents", "langgraph", "langgraph-checkpoint-sqlite")
        },
        "cases": [],
    }
    for stage in (None, "checkpoint", "materialized", "before_verification"):
        name = stage or "uninterrupted"
        result = execute_case(
            args.repo.resolve(),
            args.task.resolve(),
            args.output.resolve() / name,
            stage,
        )
        if result["result"]["tool_results"] != len(task["model"]["plan"]):
            raise RuntimeError("Unexpected completed-tool count.")
        report["cases"].append(result)
        if len({row["result"]["patch_sha256"] for row in report["cases"]}) != 1:
            raise RuntimeError(
                "Recovered patch differs from the uninterrupted baseline."
            )
        (args.output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
        print(
            json.dumps(
                {
                    "case": name,
                    "status": "verified",
                    "tool_results": result["result"]["tool_results"],
                }
            ),
            flush=True,
        )
    print(json.dumps({"cases": len(report["cases"]), "same_patch": True}), flush=True)


if __name__ == "__main__":
    main()
