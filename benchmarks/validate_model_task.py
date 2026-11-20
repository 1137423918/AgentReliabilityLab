"""Check an acceptance task against unchanged source and a known reference patch.

This is an operator self-check, not a model-generated patch evaluation.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--reference-patch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    task = json.loads(args.task.read_text())
    output = args.output.resolve()
    output.mkdir(parents=True)
    report = {
        "scope": "Acceptance self-check; unchanged baseline versus operator reference patch; no model inference",
        "base_commit": task["base_commit"],
        "task_sha256": hashlib.sha256(
            json.dumps(task, sort_keys=True).encode()
        ).hexdigest(),
        "reference_patch_sha256": hashlib.sha256(
            args.reference_patch.read_bytes()
        ).hexdigest(),
        "cases": [],
    }
    for name in ("baseline", "reference"):
        directory = output / name
        directory.mkdir()
        worktree = directory / "worktree"
        subprocess.run(
            [
                "git",
                "-C",
                str(args.repo),
                "worktree",
                "add",
                "--detach",
                str(worktree),
                task["base_commit"],
            ],
            check=True,
            capture_output=True,
        )
        if name == "reference":
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(worktree),
                    "apply",
                    str(args.reference_patch.resolve()),
                ],
                check=True,
            )
        records = []
        for index, command in enumerate(task["verify"]):
            log = directory / f"verification-{index}.log"
            with log.open("wb") as stream:
                process = subprocess.run(
                    command["argv"],
                    cwd=worktree / command.get("cwd", "."),
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=command.get("timeout_seconds", 120),
                )
            records.append(
                {
                    "returncode": process.returncode,
                    "log": str(log.relative_to(output)),
                    "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
                }
            )
        report["cases"].append({"case": name, "commands": records})
    baseline, reference = report["cases"]
    if not any(row["returncode"] for row in baseline["commands"]):
        raise RuntimeError("The unchanged baseline passes every acceptance check.")
    if any(row["returncode"] for row in reference["commands"]):
        raise RuntimeError(
            "The reference patch fails acceptance; do not evaluate a model yet."
        )
    report["discriminates_baseline_and_reference"] = True
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"discriminates_baseline_and_reference": True}), flush=True)


if __name__ == "__main__":
    main()
