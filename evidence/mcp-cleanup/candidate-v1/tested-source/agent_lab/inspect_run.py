"""Inspect worker graph state with a read-only SQLite transaction, never invoke it."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.backends.utils import file_data_to_string
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from agent_lab.models import build_model
from agent_lab.worker import RunError, validate_task

MAX_JSON_BYTES = 4 * 1024**2
MAX_OUTPUT_BYTES = 8192


class InspectionError(ValueError):
    """The run cannot be reconstructed under this worker's supported contract."""


def read_object(path):
    with path.open("rb") as stream:
        data = stream.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        raise InspectionError("Run JSON exceeds the inspection limit.")
    value = json.loads(data)
    if not isinstance(value, dict):
        raise InspectionError("Expected a run JSON object.")
    return value


def encoded(value):
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode()


def inspect_run(directory):
    """Return bounded metadata for an owned worker run without executing its task.

    The checkpoint is a single SQLite read transaction. Artifact existence/status
    is observed separately and is not verification of logs, a patch or acceptance.
    Checkpoints must be trusted local worker data, not arbitrary uploaded databases.
    """
    directory = Path(directory).resolve()
    manifest = read_object(directory / "manifest.json")
    task = manifest["task"]
    expected = hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest()
    if (
        expected != manifest["task_sha256"]
        or task["base_commit"] != manifest["base_commit"]
    ):
        raise InspectionError("Manifest task identity does not match.")
    allowed = frozenset("/" + path for path in validate_task(task))
    database = directory / "checkpoints.sqlite"
    if not database.is_file():
        raise InspectionError("No checkpoint database exists for this run.")
    options = {}
    if "file_inventory_v1" in task.get("required_features", []):
        from agent_lab.file_inventory import FileInventoryMiddleware

        options.setdefault("middleware", []).append(FileInventoryMiddleware())
    if "python_source_v1" in task.get("required_features", []):
        from agent_lab.source_tools import make_source_tool

        options["tools"] = [make_source_tool(task["files"])]
    if "python_read_index_v1" in task.get("required_features", []):
        from agent_lab.read_index import PythonReadIndexMiddleware

        options.setdefault("middleware", []).append(
            PythonReadIndexMiddleware(task["files"])
        )
    connection = sqlite3.connect(
        database.as_uri() + "?mode=ro", uri=True, check_same_thread=False, timeout=5
    )
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        saver = SqliteSaver(connection)
        saver.is_setup = True  # setup() creates tables; this reader must never do so.
        graph = create_deep_agent(
            model=build_model({"mode": "scripted", "plan": []}),
            backend=StateBackend(),
            checkpointer=saver,
            **options,
        )
        snapshot = graph.get_state({"configurable": {"thread_id": "maintenance"}})
    finally:
        connection.close()
    if not snapshot.values:
        raise InspectionError("No maintenance graph checkpoint exists.")
    messages = snapshot.values.get("messages", [])
    calls = Counter(
        call["name"]
        for message in messages
        if isinstance(message, AIMessage)
        for call in message.tool_calls
    )
    summary = {
        "schema_version": 1,
        "scope": "Owned worker checkpoint metadata; no model, tool, resume or acceptance command executed.",
        "consistency": "Checkpoint: one read transaction. Artifact observations are separate and can change during a live run.",
        "task_sha256": expected,
        "base_commit": task["base_commit"],
        "model_invoked": False,
        "checkpoint_step": snapshot.metadata.get("step") if snapshot.metadata else None,
        "pending": [str(name)[:80] for name in snapshot.next[:8]],
        "pending_omitted": max(0, len(snapshot.next) - 8),
        "messages": len(messages),
        "model_turns": sum(isinstance(m, AIMessage) for m in messages),
        "tool_results": sum(isinstance(m, ToolMessage) for m in messages),
        "indexed_read_result_markers": sum(
            isinstance(m, ToolMessage)
            and m.name == "read_file"
            and "python_read_index_v1" in m.additional_kwargs
            for m in messages
        ),
        "tool_errors": sum(
            isinstance(m, ToolMessage) and m.status == "error" for m in messages
        ),
        "tool_call_counts": [
            {"name": name[:80], "name_truncated": len(name) > 80, "count": count}
            for name, count in sorted(calls.items())[:16]
        ],
        "tool_names_omitted": max(0, len(calls) - 16),
        "virtual_file_count": len(snapshot.values.get("files", {})),
        "unexpected_virtual_file_count": len(
            set(snapshot.values.get("files", {})) - allowed
        ),
        "virtual_files": [],
        "virtual_files_omitted": len(snapshot.values.get("files", {})),
        "artifacts_observed_not_revalidated": {
            name: (directory / name).is_file()
            for name in ["patch.diff", "verification.json", "result.json"]
        },
        "observed_result_status": None,
    }
    result_file = directory / "result.json"
    if result_file.is_file():
        status = read_object(result_file).get("status")
        if not isinstance(status, str) or len(status) > 80:
            raise InspectionError("Invalid result status.")
        summary["observed_result_status"] = status
    for path, value in sorted(snapshot.values.get("files", {}).items()):
        text = file_data_to_string(value)
        raw = text.encode()
        row = {
            "path": path[:240],
            "path_truncated": len(path) > 240,
            "allowed_by_task": path in allowed,
            "bytes": len(raw),
            "lines": len(text.splitlines()),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        summary["virtual_files"].append(row)
        summary["virtual_files_omitted"] -= 1
        if len(encoded(summary)) > MAX_OUTPUT_BYTES:
            summary["virtual_files"].pop()
            summary["virtual_files_omitted"] += 1
            break
    if len(encoded(summary)) > MAX_OUTPUT_BYTES:
        raise InspectionError("Checkpoint metadata exceeds the output budget.")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        summary = inspect_run(args.run_dir)
    except (OSError, sqlite3.Error, ValueError, KeyError, TypeError, RunError) as error:
        print(
            json.dumps(
                {
                    "error": type(error).__name__,
                    "message": "Cannot inspect run: manifest, checkpoint or result metadata is invalid or unavailable.",
                }
            ),
            file=sys.stderr,
        )
        return 1
    sys.stdout.write(encoded(summary).decode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
