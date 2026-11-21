"""Checkpointed Agent edits, isolated Git materialization, and review artifacts.

Only local, explicitly supplied verification commands execute. The Agent edits
virtual files; completed changes are exported to a task-owned detached worktree.
"""

import argparse
import ast
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

from agent_lab.models import model_for_run
from agent_lab.request_budget import RequestBudget, RequestBudgetError, task_limits
from agent_lab.storage import admit_state_directory
from agent_lab.verification import VerificationError, run_command


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
    features = task.get("required_features", [])
    if not isinstance(features, list) or any(
        feature
        not in (
            "python_syntax_v1",
            "baseline_verification_v1",
            "python_source_v1",
            "python_read_index_v1",
            "model_request_budget_v1",
            "file_inventory_v1",
        )
        for feature in features
    ):
        raise RunError("The task requires unsupported worker features.")
    task_limits(task)
    if "file_inventory_v1" in features:
        from agent_lab.file_inventory import inventory_prompt

        try:
            inventory_prompt(files)
        except ValueError as error:
            raise RunError(str(error)) from error
    syntax_files = task.get("python_syntax_files", [])
    if (
        not isinstance(syntax_files, list)
        or not all(isinstance(name, str) for name in syntax_files)
        or len(set(syntax_files)) != len(syntax_files)
        or any(name not in files for name in syntax_files)
    ):
        raise RunError("Python syntax checks must name unique editable files.")
    initial = task.get("initial_contents")
    if initial is not None:
        if (
            not isinstance(initial, dict)
            or set(initial) != set(files)
            or not all(isinstance(value, str) for value in initial.values())
        ):
            raise RunError(
                "Initial contents must cover exactly the allowed text files."
            )
        if (
            sum(len(value.encode("utf-8")) for value in initial.values())
            > 2 * 1024 * 1024
        ):
            raise RunError("Initial contents exceed the 2 MiB text budget.")
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
        baseline_verification_files(command)
    allowed_tools = {"ls", "read_file", "write_file", "edit_file", "glob", "grep"}
    if "python_source_v1" in features:
        allowed_tools.add("inspect_python")
    if "file_inventory_v1" in features:
        allowed_tools.remove("ls")
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
    admit_state_directory(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    admit_state_directory(directory)
    descriptor = os.open(
        directory / "worker.lock",
        os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW,
        0o600,
    )
    with os.fdopen(descriptor, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RunError("Another worker owns this run directory.") from error
        admit_state_directory(directory)
        yield lock.fileno()


def prepare_manifest(
    repo: Path, directory: Path, task: dict, shared_budget=None
) -> dict:
    digest = hashlib.sha256(json.dumps(task, sort_keys=True).encode()).hexdigest()
    manifest = {
        "task_sha256": digest,
        "repo": str(repo),
        "base_commit": task["base_commit"],
        "task": task,
    }
    path = directory / "manifest.json"
    limits = task_limits(task)
    existing = json.loads(path.read_text()) if path.exists() else None
    if (
        limits is not None
        and existing is None
        and any(
            (directory / name).exists()
            for name in ("checkpoints.sqlite", "attempts", "result.json")
        )
    ):
        raise RequestBudgetError(
            "Budgeted run manifest is missing beside existing progress; refusing reset."
        )
    if shared_budget is not None and limits != shared_budget.limits:
        raise RequestBudgetError("Shared model request policy differs from the task.")
    if limits is not None:
        if shared_budget is not None:
            shared_budget.summary()
            budget = shared_budget
            scope = "shared"
        else:
            previous = existing.get("model_request_budget", {}) if existing else {}
            if existing and previous.get("scope") != "local":
                raise RequestBudgetError(
                    "Resume this shared model budget through the original repair entry point."
                )
            budget = RequestBudget(
                directory,
                digest,
                limits,
                previous.get("journal_id"),
                create=existing is None,
            )
            scope = "local"
        manifest["model_request_budget"] = {"scope": scope, **budget.identity}
    if path.exists():
        if existing != manifest:
            raise RunError("Resume rejected: task, repository, or pinned base changed.")
    else:
        git(repo, "cat-file", "-e", task["base_commit"] + "^{commit}")
        atomic_json(path, manifest)
    return manifest


def open_request_budget(directory, task, manifest, shared_budget=None):
    limits = task_limits(task)
    if limits is None:
        return None
    if shared_budget is not None:
        return shared_budget
    descriptor = manifest["model_request_budget"]
    return RequestBudget(
        directory, manifest["task_sha256"], limits, descriptor["journal_id"]
    )


def agent_phase(
    repo: Path,
    directory: Path,
    task: dict,
    files: list[str],
    hold: str | None,
    request_budget=None,
):
    if task_limits(task) is not None and request_budget is None:
        raise RequestBudgetError(
            "Budgeted agent requires a manifest-bound request journal."
        )
    config = {"configurable": {"thread_id": "maintenance"}, "recursion_limit": 100}
    with (
        SqliteSaver.from_conn_string(str(directory / "checkpoints.sqlite")) as saver,
        model_for_run(task.get("model", {}), request_budget) as model,
    ):
        options = {}
        prompt = "Prepare the requested maintenance patch using virtual file tools. Do not delegate or execute commands."
        if "file_inventory_v1" in task.get("required_features", []):
            from agent_lab.file_inventory import (
                FileInventoryMiddleware,
                inventory_prompt,
            )

            options.setdefault("middleware", []).append(FileInventoryMiddleware())
            prompt += inventory_prompt(files)
        if "python_source_v1" in task.get("required_features", []):
            from agent_lab.source_tools import make_source_tool

            options["tools"] = [make_source_tool(files)]
            prompt += " For Python files, use inspect_python to locate definitions before reading sequential chunks. Its source hashes bind pages to current virtual content; refresh the outline after edits."
        if "python_read_index_v1" in task.get("required_features", []):
            from agent_lab.read_index import PythonReadIndexMiddleware

            options.setdefault("middleware", []).append(
                PythonReadIndexMiddleware(files)
            )
            prompt += " A first read_file page of a large Python file may include a versioned declaration index. Use its one-based line ranges with read_file offset=start_line-1 to avoid irrelevant sequential pages. The requested source page remains unchanged after the index."
        agent = create_deep_agent(
            model=model,
            backend=StateBackend(),
            checkpointer=saver,
            system_prompt=prompt,
            **options,
        )
        snapshot = agent.get_state(config)
        initial = (
            None
            if saver.get_tuple(config)
            else {
                "messages": [HumanMessage(content=task["prompt"])],
                "files": initial_files(repo, task, files),
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


def initial_files(repo: Path, task: dict, files: list[str]) -> dict:
    values = baseline_files(repo, task["base_commit"], files)
    for name, content in task.get("initial_contents", {}).items():
        values["/" + name] = create_file_data(content)
    return values


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
    validate_python_syntax(
        task, {name: file_data_to_string(outputs["/" + name]) for name in names}
    )
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


def validate_python_syntax(task, contents):
    for name in task.get("python_syntax_files", []):
        try:
            ast.parse(contents[name], filename=name)
        except (SyntaxError, ValueError, RecursionError) as error:
            line = getattr(error, "lineno", None)
            raise RunError(
                f"Python syntax rejected before export: {name}, line {line}: {error}"
            ) from error


def baseline_verification_files(command: dict) -> list[str]:
    values = command.get("baseline_files", [])
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise RunError("baseline_files must be a list of tracked relative paths.")
    names = sorted(checked_path(value) for value in values)
    if len(set(names)) != len(names):
        raise RunError("baseline_files must be unique.")
    return names


def verification_workspace(directory, task, index, command, *, restore):
    """Build/recheck a candidate view with selected files from the pinned base."""
    frozen = baseline_verification_files(command)
    primary = directory / "worktree"
    if not frozen:
        return primary, None
    parent = directory / "verification-worktrees"
    view = parent / f"{index:03d}"
    if (
        parent.is_symlink()
        or view.is_symlink()
        or not view.resolve().is_relative_to(directory.resolve())
    ):
        raise RunError("Verification view escapes the run directory.")
    if not view.exists():
        if not restore:
            raise RunError("Saved baseline verification view is missing.")
        parent.mkdir(mode=0o700, exist_ok=True)
        git(primary, "worktree", "add", "--detach", str(view), task["base_commit"])
    if git(view, "rev-parse", "HEAD").decode().strip() != task["base_commit"]:
        raise RunError("Baseline verification view HEAD changed.")
    names = sorted({checked_path(name) for name in task["files"]} | set(frozen))
    originals = baseline_files(primary, task["base_commit"], names)
    changed = set(git(view, "diff", "--name-only", "HEAD").decode().splitlines())
    if changed - set(names):
        raise RunError("Verification view has unrelated tracked changes.")
    for name in names:
        target = view / name
        if target.is_symlink() or not target.resolve().is_relative_to(view):
            raise RunError("Refusing a symlink in the verification view.")
        original = file_data_to_string(originals["/" + name]).encode("utf-8")
        desired = original if name in frozen else (primary / name).read_bytes()
        current = target.read_bytes()
        if not restore and current != desired:
            raise RunError("Saved baseline verification content changed.")
        if restore and current not in (original, desired):
            raise RunError("Verification view changed outside known export states.")
        if current != desired:
            temporary = target.with_name(target.name + ".agent-lab-baseline-tmp")
            if temporary.is_symlink():
                raise RunError("Refusing a symlink for verification export.")
            temporary.write_bytes(desired)
            temporary.chmod(target.stat().st_mode)
            temporary.replace(target)
    fingerprint = hashlib.sha256(
        git(view, "diff", "HEAD", "--no-ext-diff", "--binary")
    ).hexdigest()
    return view, fingerprint


def validate_verification_record(
    directory, task, index, record, *, require_passed=True
):
    command = task["verify"][index]
    log = directory / f"verification-{index}.log"
    if (
        record["argv"] != command["argv"]
        or (require_passed and (record["returncode"] != 0 or record.get("timed_out")))
        or record.get("view_integrity_error")
        or hashlib.sha256(log.read_bytes()).hexdigest() != record["log_sha256"]
    ):
        raise RunError("Saved verification evidence changed or did not pass.")
    frozen = baseline_verification_files(command)
    if record.get("baseline_files", []) != frozen:
        raise RunError("Saved baseline verification policy changed.")
    if frozen:
        view, fingerprint = verification_workspace(
            directory, task, index, command, restore=False
        )
        if (
            record.get("baseline_files") != frozen
            or record.get("view_patch_sha256") != fingerprint
            or record.get("verification_view") != str(view.relative_to(directory))
        ):
            raise RunError("Saved baseline verification policy or view changed.")


def verify(
    directory: Path, task: dict, patch: bytes, hold: str | None, lock_fd: int
) -> list:
    records_path = directory / "verification.json"
    saved = json.loads(records_path.read_text()) if records_path.exists() else {}
    if saved and saved["patch_sha256"] != hashlib.sha256(patch).hexdigest():
        raise RunError("Saved verification belongs to another patch.")
    records = saved.get("commands", [])
    emit("before_verification", hold)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key
        in ("PATH", "HOME", "LANG", "LC_ALL", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR")
    }
    for index, command in enumerate(task.get("verify", [])):
        if index < len(records) and records[index].get("view_integrity_error"):
            raise RunError(
                "Previous verification changed its tracked view; review required."
            )
        if index < len(records) and records[index]["returncode"] == 0:
            validate_verification_record(directory, task, index, records[index])
            continue
        workspace, fingerprint = verification_workspace(
            directory, task, index, command, restore=True
        )
        cwd = workspace / checked_path(command.get("cwd", "."))
        if not cwd.resolve().is_relative_to(workspace) or not cwd.is_dir():
            raise RunError("Verification working directory escapes the worktree.")
        command_environment = dict(environment)
        if fingerprint is not None:
            command_environment["AGENT_LAB_BASELINE_VIEW"] = "1"
        log = directory / f"verification-{index}.log"
        with log.open("wb") as stream:
            try:
                code, timed_out = run_command(
                    command["argv"],
                    cwd=cwd,
                    environment=command_environment,
                    stream=stream,
                    timeout=command.get("timeout_seconds", 120),
                    lock_fd=lock_fd,
                )
            except VerificationError as error:
                raise RunError(str(error)) from error
        record = {
            "argv": command["argv"],
            "returncode": code,
            "timed_out": timed_out,
            "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        }
        if fingerprint is not None:
            try:
                _, after = verification_workspace(
                    directory, task, index, command, restore=False
                )
                integrity_error = after != fingerprint
            except (RunError, OSError):
                integrity_error = True
            record.update(
                baseline_files=baseline_verification_files(command),
                verification_view=str(workspace.relative_to(directory)),
                view_patch_sha256=fingerprint,
                view_integrity_error=integrity_error,
            )
        records = records[:index] + [record]
        atomic_json(
            records_path,
            {"patch_sha256": hashlib.sha256(patch).hexdigest(), "commands": records},
        )
        if code or timed_out or record.get("view_integrity_error"):
            raise RunError(f"Verification command {index} failed; review its log.")
    return records


def run(
    repo: Path,
    directory: Path,
    task: dict,
    hold: str | None = None,
    *,
    shared_budget=None,
) -> dict:
    with run_lock(directory) as lock_fd:
        names = validate_task(task)
        if task.get("max_repair_attempts", 0):
            raise RunError("Use agent_lab.repair for tasks with extra repair attempts.")
        manifest = prepare_manifest(repo, directory, task, shared_budget)
        request_budget = open_request_budget(directory, task, manifest, shared_budget)
        if (directory / "result.json").exists():
            try:
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
                    if len(result["verification"]) != len(task["verify"]):
                        raise RunError("Completed verification is incomplete.")
                    validate_python_syntax(
                        task,
                        {
                            name: (directory / "worktree" / name).read_text()
                            for name in task.get("python_syntax_files", [])
                        },
                    )
                    for index, record in enumerate(result["verification"]):
                        validate_verification_record(directory, task, index, record)
                    return result
            except Exception as error:
                atomic_json(
                    directory / "status.json",
                    {"status": "failed", "error_type": type(error).__name__},
                )
                raise
        atomic_json(directory / "status.json", {"status": "running"})
        try:
            result = execute(
                repo, directory, task, names, manifest, hold, lock_fd, request_budget
            )
        except Exception as error:
            atomic_json(
                directory / "status.json",
                {"status": "failed", "error_type": type(error).__name__},
            )
            raise
        atomic_json(directory / "result.json", result)
        atomic_json(directory / "status.json", {"status": result["status"]})
        return result


def execute(repo, directory, task, names, manifest, hold, lock_fd, request_budget=None):
    state = agent_phase(repo, directory, task, names, hold, request_budget)
    patch = materialize(repo, directory, task, names, state)
    if not patch:
        raise RunError(
            "Agent produced no patch; this is not a completed maintenance result."
        )
    emit("materialized", hold, patch_sha256=hashlib.sha256(patch).hexdigest())
    commands = verify(directory, task, patch, hold, lock_fd)
    if git(directory / "worktree", "diff", "--no-ext-diff", "--binary") != patch:
        raise RunError(
            "Verification changed tracked files; patch requires a new review."
        )
    messages = state.get("messages", [])
    result = {
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
    if request_budget is not None:
        result["model_request_budget_snapshot"] = request_budget.summary()
    return result


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
