"""Real-repository scripted controls for baseline grading, never a neural score."""

import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent_lab.worker import RunError, create_file_data, initial_files, materialize  # noqa: E402


def sha(value):
    return hashlib.sha256(value).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--legacy-source", type=Path)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    output.mkdir(parents=True, mode=0o700)
    protected = json.loads(
        (ROOT / "tasks/deepagents-path-model-protected.json").read_text()
    )
    old_grading = json.loads(
        (ROOT / "tasks/deepagents-path-model-grounded.json").read_text()
    )
    reference = json.loads(
        (ROOT / "tasks/deepagents-path-maintenance.json").read_text()
    )
    assert protected["base_commit"] == reference["base_commit"]
    assert protected["files"] == reference["files"]
    assert protected["verify"][0] == old_grading["verify"][0]
    assert protected["verify"][2:] == old_grading["verify"][1:]

    def source(path):
        return subprocess.check_output(
            ["git", "-C", str(repo), "show", protected["base_commit"] + ":" + path]
        ).decode()

    production_path, test_path = protected["files"]
    production = source(production_path)
    tests = source(test_path)
    function = next(
        n
        for n in ast.parse(production).body
        if isinstance(n, ast.FunctionDef) and n.name == "regex_literal_hint"
    )
    group = next(
        n
        for n in ast.parse(tests).body
        if isinstance(n, ast.ClassDef) and n.name == "TestLooksLikeRegex"
    )
    function_source = ast.get_source_segment(production, function)
    group_source = ast.get_source_segment(tests, group)
    assert function_source and group_source
    bad_steps = [
        {
            "tool": "edit_file",
            "args": {
                "file_path": "/" + production_path,
                "old_string": function_source,
                "new_string": "def regex_literal_hint(pattern: str) -> str | None:\n    return None\n",
            },
        },
        {
            "tool": "edit_file",
            "args": {
                "file_path": "/" + test_path,
                "old_string": group_source,
                "new_string": "@pytest.mark.skip(reason='controlled grading regression')\n"
                + group_source,
            },
        },
    ]

    def controlled(task, bad=False):
        task = copy.deepcopy(task)
        task["model"] = copy.deepcopy(reference["model"])
        task["prompt"] = (
            "Operator scripted grader control, not a neural maintenance result."
        )
        if bad:
            task["model"]["plan"].extend(bad_steps)
        return task

    def run_case(name, task, cwd=ROOT):
        folder = output / name
        folder.mkdir(mode=0o700)
        task_path = folder / "task.json"
        task_path.write_text(json.dumps(task, indent=2) + "\n")
        with (
            (folder / "stdout.jsonl").open("wb") as stdout,
            (folder / "stderr.log").open("wb") as stderr,
        ):
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "agent_lab.worker",
                    "--repo",
                    str(repo),
                    "--task",
                    str(task_path),
                    "--run-dir",
                    str(folder / "run"),
                ],
                cwd=cwd,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            try:
                code = process.wait(timeout=600)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=15)
                raise RuntimeError("Controlled grading worker exceeded its limit")
        run = folder / "run"
        patch = (
            (run / "patch.diff").read_bytes() if (run / "patch.diff").exists() else b""
        )
        result = (
            json.loads((run / "result.json").read_text())
            if (run / "result.json").exists()
            else None
        )
        records = (
            json.loads((run / "verification.json").read_text())
            if (run / "verification.json").exists()
            else None
        )
        value = {
            "case": name,
            "worker_returncode": code,
            "ready_for_review": result is not None
            and result["status"] == "ready_for_review",
            "task_sha256": sha(json.dumps(task, sort_keys=True).encode()),
            "patch_sha256": sha(patch),
            "patch_bytes": len(patch),
            "verification": records,
        }
        print(
            json.dumps({k: v for k, v in value.items() if k != "verification"}),
            flush=True,
        )
        return value

    bad = controlled(protected, bad=True)
    weak = copy.deepcopy(bad)
    weak["verify"] = copy.deepcopy(old_grading["verify"])
    weak_case = run_case("mutable-grader-control", weak)
    assert weak_case["ready_for_review"], (
        "The intentional test-weakening control must expose the old grading gap"
    )
    weak_log = (output / "mutable-grader-control/run/verification-1.log").read_text()
    assert "96 passed, 23 skipped" in weak_log
    protected_case = run_case("baseline-grader-control", bad)
    assert (
        not protected_case["ready_for_review"]
        and protected_case["worker_returncode"] == 2
    )
    assert protected_case["patch_sha256"] == weak_case["patch_sha256"], (
        "Compare the same candidate under different grading policies"
    )
    assert protected_case["verification"]["commands"][1]["returncode"] != 0
    frozen_log = (output / "baseline-grader-control/run/verification-1.log").read_text()
    assert "TestLooksLikeRegex::test_hint_present_for_regex" in frozen_log
    assert "1 failed, 112 passed" in frozen_log
    reference_case = run_case("protected-reference", controlled(protected))
    assert reference_case["ready_for_review"]
    assert (
        "113 passed"
        in (output / "protected-reference/run/verification-1.log").read_text()
    )
    assert (
        "119 passed"
        in (output / "protected-reference/run/verification-2.log").read_text()
    )
    cases = [weak_case, protected_case, reference_case]
    legacy_sha = None
    if args.legacy_source:
        legacy_sha = sha((args.legacy_source / "agent_lab/worker.py").read_bytes())
        assert (
            legacy_sha
            == "d5d989872c92f5f311f41f16538cf8d2b212ac5920a711d446cc9e958d8a7384"
        )
        legacy_case = run_case(
            "legacy-worker-fails-closed",
            controlled(protected),
            args.legacy_source.resolve(),
        )
        assert (
            not legacy_case["ready_for_review"]
            and legacy_case["worker_returncode"] == 2
        )
        text = (
            output / "legacy-worker-fails-closed/run/verification-1.log"
        ).read_text()
        assert "baseline-view capability required" in text
        cases.append(legacy_case)
    invalid = output / "recorded-invalid-virtual-text"
    invalid.mkdir(mode=0o700)
    sample = (
        ROOT
        / "evidence/native-cpu/audit/normal/libs/deepagents/deepagents/backends/utils.py.txt"
    )
    data = initial_files(repo, protected, protected["files"])
    data["/" + production_path] = create_file_data(sample.read_text())
    try:
        materialize(repo, invalid, protected, protected["files"], {"files": data})
    except RunError as error:
        assert "syntax rejected before export" in str(error)
        rejection = str(error)
    else:
        raise AssertionError("The actual invalid virtual model text was not rejected")
    assert not (invalid / "worktree").exists() and not (invalid / "patch.diff").exists()
    report = {
        "scope": "Scripted real-repository grading controls and replay of an earlier invalid model write; not a neural model repair score",
        "neural_generation": False,
        "legacy_worker_source_sha256": legacy_sha,
        "base_commit": protected["base_commit"],
        "protected_task_sha256": sha(json.dumps(protected, sort_keys=True).encode()),
        "candidate_patch_identical_across_grading_policies": True,
        "cases": cases,
        "invalid_model_text": {
            "sha256": sha(sample.read_bytes()),
            "bytes": sample.stat().st_size,
            "rejected_before_worktree_creation": True,
            "error": rejection,
        },
        "worker_source_sha256": sha((ROOT / "agent_lab/worker.py").read_bytes()),
        "repair_source_sha256": sha((ROOT / "agent_lab/repair.py").read_bytes()),
        "benchmark_source_sha256": sha(Path(__file__).read_bytes()),
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "controls_verified": True,
                "neural_generation": False,
                "legacy_worker_source_sha256": legacy_sha,
                "candidate_patch_identical": True,
            }
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
