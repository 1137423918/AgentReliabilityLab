"""Paired real-repository read-index controls; explicit plans, no inference."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from recovery_matrix import execute_case


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def checkpoint_reads(directory, task):
    from deepagents import create_deep_agent
    from deepagents.backends import StateBackend
    from langchain_core.messages import ToolMessage
    from langgraph.checkpoint.sqlite import SqliteSaver

    from agent_lab.models import build_model
    from agent_lab.read_index import BEGIN, END, MARKER, PythonReadIndexMiddleware

    connection = sqlite3.connect(
        "file:" + str(directory / "checkpoints.sqlite") + "?mode=ro",
        uri=True,
        check_same_thread=False,
    )
    connection.execute("BEGIN")
    saver = SqliteSaver(connection)
    saver.is_setup = True
    options = {}
    if "python_read_index_v1" in task["required_features"]:
        options["middleware"] = [PythonReadIndexMiddleware(task["files"])]
    graph = create_deep_agent(
        model=build_model({"mode": "scripted", "plan": []}),
        backend=StateBackend(),
        checkpointer=saver,
        **options,
    )
    snapshot = graph.get_state({"configurable": {"thread_id": "maintenance"}})
    connection.close()
    rows = []
    for message in snapshot.values.get("messages", []):
        if not isinstance(message, ToolMessage) or message.name != "read_file":
            continue
        original = message.content
        annotation = None
        if MARKER in message.additional_kwargs:
            assert original.startswith(BEGIN)
            header, original = original.split(END, 1)
            annotation = json.loads(header[len(BEGIN) :].split("\n", 1)[0])
            assert all(
                annotation[k] == v for k, v in message.additional_kwargs[MARKER].items()
            )
            assert {"to_posix_path", "validate_path"} <= {
                r[0] for r in annotation["definitions"]
            }
        rows.append(
            {
                "tool_call_id": message.tool_call_id,
                "status": message.status,
                "original_reply_sha256": hashlib.sha256(original.encode()).hexdigest(),
                "original_reply_bytes": len(original.encode()),
                "complete_reply_bytes": len(message.content.encode()),
                "annotation": annotation,
            }
        )
    source = "/" + task["files"][0]
    from deepagents.backends.utils import file_data_to_string

    current = file_data_to_string(snapshot.values["files"][source])
    if "python_read_index_v1" in task["required_features"]:
        assert len(rows) == 2 and all(r["annotation"] is not None for r in rows)
        assert (
            rows[-1]["annotation"]["source_sha256"]
            == hashlib.sha256(current.encode()).hexdigest()
        )
        assert (
            rows[0]["annotation"]["source_sha256"]
            != rows[-1]["annotation"]["source_sha256"]
        )
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["repo", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    base = json.loads((root / "tasks/deepagents-path-model-protected.json").read_text())
    reference = json.loads(
        (root / "tasks/deepagents-path-maintenance.json").read_text()
    )
    production = "/" + base["files"][0]
    base["model"] = {
        "mode": "scripted",
        "plan": [
            {"tool": "read_file", "args": {"file_path": production}},
            *reference["model"]["plan"],
            {"tool": "read_file", "args": {"file_path": production}},
        ],
    }
    base["required_features"].append("python_source_v1")
    base["evaluation_notes"] = (
        "Explicit operator read/edit/read plan; real-repository infrastructure control, not a model result."
    )
    cases = []
    for name, indexed, fault in [
        ("legacy", False, None),
        ("indexed", True, None),
        ("indexed-checkpoint", True, "checkpoint"),
    ]:
        task = json.loads(json.dumps(base))
        if indexed:
            task["required_features"].append("python_read_index_v1")
        task_path = output / (name + "-task.json")
        write(task_path, task)
        row = execute_case(args.repo.resolve(), task_path, output / name, fault)
        row["read_audit"] = checkpoint_reads(output / name, task)
        cases.append(row)
        write(output / "progress.json", cases)
        print(
            json.dumps(
                {
                    "case": name,
                    "status": row["result"]["status"],
                    "tools": row["result"]["tool_results"],
                }
            ),
            flush=True,
        )
    assert len({r["result"]["patch_sha256"] for r in cases}) == 1
    assert all(r["result"]["tool_results"] == 4 for r in cases)
    legacy = cases[0]["read_audit"]
    assert all(r["annotation"] is None for r in legacy)
    for case in cases[1:]:
        assert [r["original_reply_sha256"] for r in case["read_audit"]] == [
            r["original_reply_sha256"] for r in legacy
        ]
    assert cases[-1]["interrupted_progress"]["tool_results"] == 1
    assert all(n > 1 for n in cases[-1]["resumed_checkpoint_tool_counts"])
    report = {
        "scope": "Paired legacy/indexed read/edit/read through real worker, protected acceptance and actual checkpoint SIGKILL; explicit operator plan, no neural inference.",
        "base_commit": base["base_commit"],
        "model_inference": False,
        "gpu": False,
        "same_patch": True,
        "original_read_pages_byte_identical": True,
        "annotation_tracks_current_virtual_revision": True,
        "cases": cases,
        "source_sha256": {
            n: hashlib.sha256((root / n).read_bytes()).hexdigest()
            for n in [
                "agent_lab/worker.py",
                "agent_lab/read_index.py",
                "benchmarks/read_index_recovery.py",
            ]
        },
    }
    write(output / "report.json", report)
    print(
        json.dumps({"cases": 3, "same_patch": True, "original_pages_preserved": True}),
        flush=True,
    )


if __name__ == "__main__":
    main()
