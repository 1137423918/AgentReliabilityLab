"""Checkpointed Agent edits, isolated Git materialization, and review artifacts.

Only local, explicitly supplied verification commands execute. The Agent edits
virtual files; completed changes are exported to a task-owned detached worktree.
"""

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import sys
from pathlib import Path, PurePosixPath

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data, file_data_to_string
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.errors import GraphRecursionError

from agent_lab.models import build_model


class RunError(RuntimeError):
    """A failed task invariant; no patch is approved automatically."""


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def emit(stage: str, hold: str | None = None, **fields) -> None:
    print(json.dumps({"stage": stage, **fields}), flush=True)
    if stage == hold:
        signal.pause()


def checked_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or any(part in ("..", ".git") for part in path.parts)
    ):
        raise RunError(f"Path is outside the allowed relative-file scope: {value!r}")
    if "\\" in value or any(ord(char) < 32 for char in value):
        raise RunError("Task paths must use ordinary POSIX components.")
    return str(path)


def git(repo: Path, *args: str) -> bytes:
    process = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if process.returncode:
        raise RunError(process.stderr.decode(errors="replace"))
    return process.stdout


def validate_task(task: dict) -> list[str]:
    files = [checked_path(name) for name in task["files"]]
    if not files or len(set(files)) != len(files):
        raise RunError("Task files must be nonempty and unique.")
    if len(task["base_commit"]) != 40 or any(
        c not in "0123456789abcdef" for c in task["base_commit"]
    ):
        raise RunError("Pin a full base commit SHA, not a moving branch.")
    if task.get("max_graph_steps", 200) < 1:
        raise RunError("max_graph_steps must be positive.")
    if not task.get("verify"):
        raise RunError("A maintenance task requires an explicit verification command.")
    for command in task.get("verify", []):
        if not command.get("argv") or not all(
            isinstance(arg, str) for arg in command["argv"]
        ):
            raise RunError("Verification requires explicit argument arrays.")
        if command.get("timeout_seconds", 120) <= 0:
            raise RunError("Verification timeout must be positive.")
        checked_path(command.get("cwd", "."))
    allowed_tools = {"ls", "read_file", "write_file", "edit_file", "glob", "grep"}
    for step in task.get("model", {}).get("plan", []):
        if step["tool"] not in allowed_tools:
            raise RunError("Scripted plans only support virtual file tools.")
    return files


def baseline_files(repo: Path, commit: str, names: list[str]) -> dict:
    files = {}
    total = 0
    for name in names:
        mode = git(repo, "ls-tree", commit, "--", name).decode().split()
        if not mode or mode[0] not in ("100644", "100755"):
            raise RunError(f"Expected a tracked ordinary text file: {name}")
        content = git(repo, "show", f"{commit}:{name}").decode("utf-8")
        total += len(content.encode("utf-8"))
        if total > 2 * 1024 * 1024:
            raise RunError("Initial file scope exceeds the 2 MiB text budget.")
        files["/" + name] = create_file_data(content)
    return files


@contextlib.contextmanager
def run_lock(directory: Path):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / "worker.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RunError("Another worker owns this run directory.") from error
        yield


def prepare_manifest(repo: Path, directory: Path, task: dict) -> dict:
    digest = hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest()
    manifest = {
        "task_sha256": digest,
        "repo": str(repo),
        "base_commit": task["base_commit"],
        "task": task,
    }
    path = directory / "manifest.json"
    if path.exists():
        existing = json.loads(path.read_text())
        if existing != manifest:
            raise RunError("Resume rejected: task, repository, or pinned base changed.")
    else:
        git(repo, "cat-file", "-e", task["base_commit"] + "^{commit}")
        atomic_json(path, manifest)
    return manifest


def agent_phase(
    repo: Path, directory: Path, task: dict, files: list[str], hold: str | None
):
    config = {"configurable": {"thread_id": "maintenance"}, "recursion_limit": 100}
    with SqliteSaver.from_conn_string(str(directory / "checkpoints.sqlite")) as saver:
        agent = create_deep_agent(
            model=build_model(task.get("model", {})),
            backend=StateBackend(),
            checkpointer=saver,
            system_prompt="Prepare the requested maintenance patch using virtual file tools. Do not delegate or execute commands.",
        )
        snapshot = agent.get_state(config)
        initial = (
            None
            if saver.get_tuple(config)
            else {
                "messages": [HumanMessage(content=task["prompt"])],
                "files": baseline_files(repo, task["base_commit"], files),
            }
        )
        while initial is not None or snapshot.next:
            step = snapshot.metadata.get("step", -1) if snapshot.metadata else -1
            remaining = task.get("max_graph_steps", 200) - max(step, 0)
            if remaining <= 0:
                raise RunError("Persistent graph-step budget exhausted.")
            bounded = {**config, "recursion_limit": min(100, remaining)}
            try:
                agent.invoke(
                    initial, bounded, interrupt_after=["tools"], durability="sync"
                )
            except GraphRecursionError as error:
                raise RunError("Persistent graph-step budget exhausted.") from error
            initial = None
            snapshot = agent.get_state(config)
            messages = snapshot.values.get("messages", [])
            emit(
                "checkpoint",
                hold,
                model_turns=sum(isinstance(m, AIMessage) for m in messages),
                tool_results=sum(isinstance(m, ToolMessage) for m in messages),
                pending=list(snapshot.next),
            )
        return snapshot.values


def materialize(
    repo: Path, directory: Path, task: dict, names: list[str], state: dict
) -> bytes:
    outputs = state.get("files", {})
    if set(outputs) != {"/" + name for name in names}:
        raise RunError("Virtual output changed the allowed file set; export rejected.")
    if (
        sum(
            len(file_data_to_string(value).encode("utf-8"))
            for value in outputs.values()
        )
        > 2 * 1024 * 1024
    ):
        raise RunError("Virtual output exceeds the 2 MiB text budget.")
    worktree = directory / "worktree"
    if not worktree.exists():
        git(repo, "worktree", "add", "--detach", str(worktree), task["base_commit"])
    if git(worktree, "rev-parse", "HEAD").decode().strip() != task["base_commit"]:
        raise RunError("The isolated worktree HEAD changed.")
    for name in names:
        destination = worktree / name
        if destination.is_symlink() or not destination.resolve().is_relative_to(
            worktree
        ):
            raise RunError("Refusing to export through a symlink.")
        desired = file_data_to_string(outputs["/" + name]).encode("utf-8")
        if len(desired) > 2 * 1024 * 1024:
            raise RunError("A virtual output exceeds the 2 MiB file budget.")
        original = git(repo, "show", f"{task['base_commit']}:{name}")
        if destination.read_bytes() not in (original, desired):
            raise RunError(
                "Worktree changed outside the saved Agent output; export rejected."
            )
        temporary = destination.with_name(destination.name + ".agent-lab-tmp")
        mode = destination.stat().st_mode
        temporary.write_bytes(desired)
        temporary.chmod(mode)
        temporary.replace(destination)
    patch = git(worktree, "diff", "--no-ext-diff", "--binary", "--", *names)
    (directory / "patch.diff").write_bytes(patch)
    return patch


def verify(directory: Path, task: dict, patch: bytes, hold: str | None) -> list:
    records_path = directory / "verification.json"
    saved = json.loads(records_path.read_text()) if records_path.exists() else {}
    if saved and saved["patch_sha256"] != hashlib.sha256(patch).hexdigest():
        raise RunError("Saved verification belongs to another patch.")
    records = saved.get("commands", [])
    emit("before_verification", hold)
    worktree = directory / "worktree"
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in ("PATH", "HOME", "LANG", "LC_ALL", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR")
    }
    for index, command in enumerate(task.get("verify", [])):
        if index < len(records) and records[index]["returncode"] == 0:
            continue
        cwd = worktree / checked_path(command.get("cwd", "."))
        if not cwd.resolve().is_relative_to(worktree) or not cwd.is_dir():
            raise RunError("Verification working directory escapes the worktree.")
        log = directory / f"verification-{index}.log"
        with log.open("wb") as stream:
            process = subprocess.Popen(
                command["argv"],
                cwd=cwd,
                env=environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                code = process.wait(timeout=command.get("timeout_seconds", 120))
                timed_out = False
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                code, timed_out = process.returncode, True
        record = {
            "argv": command["argv"],
            "returncode": code,
            "timed_out": timed_out,
            "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        }
        records = records[:index] + [record]
        atomic_json(
            records_path,
            {"patch_sha256": hashlib.sha256(patch).hexdigest(), "commands": records},
        )
        if code:
            raise RunError(f"Verification command {index} failed; review its log.")
    return records


def run(repo: Path, directory: Path, task: dict, hold: str | None = None) -> dict:
    with run_lock(directory):
        names = validate_task(task)
        manifest = prepare_manifest(repo, directory, task)
        if (directory / "result.json").exists():
            result = json.loads((directory / "result.json").read_text())
            if result["status"] == "ready_for_review":
                patch = (directory / "patch.diff").read_bytes()
                current = git(
                    directory / "worktree", "diff", "--no-ext-diff", "--binary"
                )
                if (
                    hashlib.sha256(patch).hexdigest() != result["patch_sha256"]
                    or current != patch
                ):
                    raise RunError(
                        "Completed review artifacts changed; refusing a stale success."
                    )
                return result
        atomic_json(directory / "status.json", {"status": "running"})
        try:
            result = execute(repo, directory, task, names, manifest, hold)
        except Exception as error:
            atomic_json(
                directory / "status.json",
                {"status": "failed", "error_type": type(error).__name__},
            )
            raise
        atomic_json(directory / "result.json", result)
        atomic_json(directory / "status.json", {"status": result["status"]})
        return result


def execute(repo, directory, task, names, manifest, hold):
    state = agent_phase(repo, directory, task, names, hold)
    patch = materialize(repo, directory, task, names, state)
    if not patch:
        raise RunError(
            "Agent produced no patch; this is not a completed maintenance result."
        )
    emit("materialized", hold, patch_sha256=hashlib.sha256(patch).hexdigest())
    commands = verify(directory, task, patch, hold)
    if git(directory / "worktree", "diff", "--no-ext-diff", "--binary") != patch:
        raise RunError(
            "Verification changed tracked files; patch requires a new review."
        )
    messages = state.get("messages", [])
    return {
        "status": "ready_for_review",
        "task_sha256": manifest["task_sha256"],
        "base_commit": task["base_commit"],
        "patch_sha256": hashlib.sha256(patch).hexdigest(),
        "patch_bytes": len(patch),
        "model_mode": task.get("model", {}).get("mode", "scripted"),
        "retained_ai_messages": sum(isinstance(m, AIMessage) for m in messages),
        "tool_results": sum(isinstance(m, ToolMessage) for m in messages),
        "verification": commands,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--task", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument(
        "--hold-after", choices=("checkpoint", "materialized", "before_verification")
    )
    args = parser.parse_args()
    try:
        result = run(
            args.repo.resolve(),
            args.run_dir.resolve(),
            json.loads(args.task.read_text()),
            args.hold_after,
        )
    except (RunError, ValueError, OSError, KeyError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
