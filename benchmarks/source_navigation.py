"""Real-source navigation and scripted edit/recovery controls; no model inference."""

import argparse
import copy
import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langchain_core.messages import ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from recovery_matrix import wait_stage

from agent_lab.models import build_model
from agent_lab.source_tools import inspect_source, make_source_tool
from agent_lab.worker import initial_files


def sha(value):
    return hashlib.sha256(value).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    output.mkdir(mode=0o700, parents=True)
    protected = json.loads(
        (ROOT / "tasks/deepagents-path-model-protected.json").read_text()
    )
    reference = json.loads(
        (ROOT / "tasks/deepagents-path-maintenance.json").read_text()
    )
    files = initial_files(repo, protected, protected["files"])
    production = "/" + protected["files"][0]
    outline_raw = inspect_source(files, set(files), production, limit=120)
    outline = json.loads(outline_raw)
    pages = [outline_raw]
    while outline["next_offset"] is not None:
        raw = inspect_source(
            files,
            set(files),
            production,
            offset=outline["next_offset"],
            limit=120,
            expected_sha256=outline["source_sha256"],
        )
        pages.append(raw)
        outline = json.loads(raw)
    entries = [e for p in pages for e in json.loads(p)["items"]]
    # Operator-selected retrieval objectives, not model-discovered localization.
    selected = [
        next(e for e in entries if e["name"] == name)
        for name in ["to_posix_path", "validate_path"]
    ]
    source_pages = []
    for entry in selected:
        offset = 0
        lines = []
        while True:
            raw = inspect_source(
                files,
                set(files),
                production,
                symbol_id=entry["id"],
                offset=offset,
                limit=120,
                expected_sha256=outline["source_sha256"],
            )
            page = json.loads(raw)
            assert page["status"] == "ok"
            source_pages.append(raw)
            lines.extend(page["items"])
            offset = page["next_offset"]
            if offset is None:
                break
        assert [line["line"] for line in lines] == list(
            range(entry["start_line"], entry["end_line"] + 1)
        )
    (output / "navigation.json").write_text(
        json.dumps(
            {
                "scope": "Operator-selected symbol retrieval from fixed real source; no model or runtime speedup claim",
                "source_sha256": outline["source_sha256"],
                "symbols": selected,
                "outline_pages": [json.loads(p) for p in pages],
                "source_pages": [json.loads(p) for p in source_pages],
                "response_bytes": sum(len(p.encode()) for p in pages + source_pages),
                "max_response_bytes": max(
                    len(p.encode()) for p in pages + source_pages
                ),
                "per_response_limit": 8192,
            },
            indent=2,
        )
        + "\n"
    )
    assert min(e["start_line"] for e in selected) > 400
    task = copy.deepcopy(protected)
    task["required_features"].append("python_source_v1")
    task["prompt"] = (
        "Explicit operator reference control for edited-file source navigation and recovery, not a neural repair score."
    )
    task["model"] = copy.deepcopy(reference["model"])
    first, second = task["model"]["plan"]
    task["model"]["plan"] = [
        first,
        {"tool": "inspect_python", "args": {"file_path": production}},
        second,
        {"tool": "inspect_python", "args": {"file_path": "/" + protected["files"][1]}},
    ]
    (output / "task.json").write_text(json.dumps(task, indent=2) + "\n")
    results = []
    for name, fault in [("normal", False), ("checkpoint-resume", True)]:
        case = output / name
        case.mkdir()
        run = case / "run"
        argv = [
            sys.executable,
            "-m",
            "agent_lab.worker",
            "--repo",
            str(repo),
            "--task",
            str(output / "task.json"),
            "--run-dir",
            str(run),
        ]
        observation = None
        if fault:
            with (
                (case / "interrupted.stdout.jsonl").open("wb") as trace,
                (case / "interrupted.stderr.log").open("wb") as errors,
            ):
                process = subprocess.Popen(
                    argv + ["--hold-after", "checkpoint"],
                    stdout=subprocess.PIPE,
                    stderr=errors,
                    start_new_session=True,
                    cwd=ROOT,
                )
                try:
                    observation = wait_stage(process, "checkpoint", trace)
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=15)
                    process.stdout.close()
                assert (
                    process.returncode == -signal.SIGKILL
                    and observation["tool_results"] == 1
                )
        with (
            (case / "stdout.jsonl").open("wb") as stdout,
            (case / "stderr.log").open("wb") as stderr,
        ):
            process = subprocess.Popen(
                argv, stdout=stdout, stderr=stderr, start_new_session=True, cwd=ROOT
            )
            try:
                code = process.wait(timeout=600)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=15)
                raise RuntimeError("Reference control exceeded wall budget")
        assert code == 0, (name, code)
        result = json.loads((run / "result.json").read_text())
        assert result["status"] == "ready_for_review" and result["tool_results"] == 4
        connection = sqlite3.connect(
            "file:" + str(run / "checkpoints.sqlite") + "?mode=ro",
            uri=True,
            check_same_thread=False,
        )
        connection.execute("BEGIN")
        saver = SqliteSaver(connection)
        saver.is_setup = True
        graph = create_deep_agent(
            model=build_model(task["model"]),
            backend=StateBackend(),
            tools=[make_source_tool(task["files"])],
            checkpointer=saver,
        )
        state = graph.get_state({"configurable": {"thread_id": "maintenance"}})
        connection.close()
        source_replies = [
            json.loads(m.content)
            for m in state.values["messages"]
            if isinstance(m, ToolMessage) and m.name == "inspect_python"
        ]
        assert len(source_replies) == 2
        for path, reply in zip(task["files"], source_replies):
            assert reply["source_sha256"] == sha(
                (run / "worktree" / path).read_bytes()
            ), "Tool must inspect edited checkpoint contents, not baseline or checkout"
        assert source_replies[0]["source_sha256"] != outline["source_sha256"]
        logs = [(run / f"verification-{i}.log").read_text() for i in range(4)]
        assert (
            "113 passed" in logs[1]
            and "119 passed" in logs[2]
            and '"passed": 28' in logs[3]
        )
        row = {
            "case": name,
            "worker_returncode": code,
            "checkpoint_interruption": observation,
            "edited_file_checkpoint_resumed": fault,
            "result": result,
            "source_replies": source_replies,
        }
        (case / "audit.json").write_text(json.dumps(row, indent=2) + "\n")
        results.append(row)
        print(
            json.dumps(
                {
                    "case": name,
                    "status": result["status"],
                    "patch_sha256": result["patch_sha256"],
                }
            ),
            flush=True,
        )
    assert len({r["result"]["patch_sha256"] for r in results}) == 1
    report = {
        "scope": "Real-source symbol navigation plus explicit reference edits; actual SIGKILL after a production edit; no neural inference or model repair score",
        "base_commit": task["base_commit"],
        "task_sha256": sha(json.dumps(task, sort_keys=True).encode()),
        "source_sha256": {
            n: sha((ROOT / n).read_bytes())
            for n in [
                "agent_lab/worker.py",
                "agent_lab/source_tools.py",
                "benchmarks/source_navigation.py",
            ]
        },
        "cases": results,
        "same_patch": True,
        "original_tests_per_case": 113,
        "candidate_tests_per_case": 119,
        "independent_contracts_per_case": 28,
        "counts_overlap": True,
        "model_inference": False,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
