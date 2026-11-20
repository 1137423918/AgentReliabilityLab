"""Execute one protocol-bound real-model maintenance trial, preserving failures."""
import argparse
import hashlib
import json
from pathlib import Path

from model_pilot import run_case


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["repo", "task", "protocol", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    protocol = json.loads(args.protocol.read_text())
    task = json.loads(args.task.read_text())
    assert digest(args.task) == protocol["task_file_sha256"]
    assert hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest() == protocol["task_sha256"]
    assert task["model"]["mode"] == "local-openai" and not task.get("max_repair_attempts")
    assert protocol["trials"] == ["normal"]
    root = Path(__file__).resolve().parents[1]
    for name, expected in protocol["source_sha256"].items():
        assert digest(root / name) == expected, name
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"scope": protocol["scope"], "protocol_sha256": digest(args.protocol),
              "task_sha256": protocol["task_sha256"], "cases": []}
    (output / "protocol.json").write_bytes(args.protocol.read_bytes())
    print(json.dumps({"stage": "trial_started", "protocol_sha256": report["protocol_sha256"]}), flush=True)
    try:
        row = run_case(args.repo.resolve(), args.task.resolve(), output / "normal", False,
                       protocol["budget"]["case_wall_seconds"])
    except Exception as error:
        row = {"case": "normal", "verified_patch": False,
               "harness_error": type(error).__name__, "error": str(error)}
    report["cases"].append(row)
    report["verified_trials"] = int(row["verified_patch"])
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"stage": "trial_finished", "verified_trials": report["verified_trials"],
                      "returncode": row.get("returncode"), "timed_out": row.get("timed_out"),
                      "duration_seconds": row.get("duration_seconds")}), flush=True)


if __name__ == "__main__":
    main()
