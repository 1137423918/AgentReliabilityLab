"""Opt-in Python declaration hints beside an unchanged first read-file page."""

import ast
import asyncio
import hashlib
import json
import re
from collections.abc import Mapping

from deepagents.backends.utils import file_data_to_string
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, ToolMessage

MARKER = "python_read_index_v1"
BEGIN = "<python_read_index_v1>\n"
END = "</python_read_index_v1>\n"
MIN_LINES = 400
MAX_SOURCE_BYTES = 2 * 1024**2
MAX_INDEX_BYTES = 2048
MAX_ANNOTATED_BYTES = 8192
HEADER = re.compile(r"@@ lines 1-(\d+) of (\d+)(?: \| next offset \d+)? @@")
NON_PHYSICAL_BREAKS = "\v\f\x1c\x1d\x1e\x85\u2028\u2029"


def _render(payload):
    value = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    value = value.replace("<", "\\u003c").replace(">", "\\u003e")
    return (
        BEGIN + value + "\nDirect module-body declarations only. Lines are one-based; "
        "read_file offset=start_line-1. Original requested page follows unchanged.\n"
        + END
    )


def index_for_read(files, allowed, path, original):
    """Return a bounded hint only when the complete displayed page matches state.

    Unknown/truncated reply formats, non-physical line separators, failed parses
    and over-budget annotations retain the original tool reply without a hint.
    """
    if (
        not isinstance(files, Mapping)
        or path not in allowed
        or path not in files
        or not path.endswith(".py")
    ):
        return None
    first, separator, body = original.partition("\n")
    match = HEADER.fullmatch(first)
    if not separator or not match:
        return None
    text = file_data_to_string(files[path])
    try:
        source_bytes = text.encode("utf-8")
    except UnicodeError:
        return None
    if len(source_bytes) > MAX_SOURCE_BYTES or any(
        c in text for c in NON_PHYSICAL_BREAKS
    ):
        return None
    lines = text.splitlines()
    end, total = map(int, match.groups())
    if (
        len(lines) < MIN_LINES
        or total != len(lines)
        or not 1 <= end <= total
        or body != "\n".join(lines[:end])
    ):
        return None
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return None
    kinds = {
        ast.FunctionDef: "def",
        ast.AsyncFunctionDef: "async",
        ast.ClassDef: "class",
    }
    nodes = [node for node in tree.body if type(node) in kinds]
    if not nodes:
        return None
    identity = {
        "version": 1,
        "file_path": path,
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
    }
    payload = {
        **identity,
        "file_lines": len(lines),
        "columns": ["name", "start_line", "end_line", "kind", "name_truncated"],
        "definitions": [],
        "omitted_definitions": len(nodes),
    }
    for node in nodes:
        start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
        row = [
            node.name[:80],
            start,
            node.end_lineno,
            kinds[type(node)],
            len(node.name) > 80,
        ]
        candidate = {
            **payload,
            "definitions": [*payload["definitions"], row],
            "omitted_definitions": len(nodes) - len(payload["definitions"]) - 1,
        }
        if len(_render(candidate).encode("utf-8")) > MAX_INDEX_BYTES:
            break
        payload = candidate
    if not payload["definitions"]:
        return None
    hint = _render(payload)
    if len((hint + original).encode("utf-8")) > MAX_ANNOTATED_BYTES:
        return None
    return hint, identity


class PythonReadIndexMiddleware(AgentMiddleware):
    """Add a declaration hint once per visible file revision, without a new tool.

    Filesystem argument validation, source text, pagination, errors and Command
    updates remain owned by the original read_file handler. Annotation is skipped
    for a batch containing mutations, avoiding snapshot/pending-write ambiguity.
    """

    def __init__(self, paths):
        self.allowed = frozenset("/" + path for path in paths)

    def _augment(self, request, result):
        call = request.tool_call
        if (
            call.get("name") != "read_file"
            or not isinstance(result, ToolMessage)
            or result.name != "read_file"
            or result.status != "success"
            or not isinstance(result.content, str)
            or MARKER in result.additional_kwargs
            or not isinstance(request.state, Mapping)
        ):
            return result
        args = call.get("args", {})
        path, offset = args.get("file_path"), args.get("offset", 0)
        if not isinstance(path, str) or type(offset) is not int or offset != 0:
            return result
        messages = request.state.get("messages", [])
        latest = next((m for m in reversed(messages) if isinstance(m, AIMessage)), None)
        if latest is None or not any(
            c["id"] == call.get("id") for c in latest.tool_calls
        ):
            return result
        if any(c["name"] in {"edit_file", "write_file"} for c in latest.tool_calls):
            return result
        for other in latest.tool_calls:
            if other["id"] == call["id"]:
                break
            if (
                other["name"] == "read_file"
                and other["args"].get("file_path") == path
                and type(other["args"].get("offset", 0)) is int
                and other["args"].get("offset", 0) == 0
            ):
                return result
        hint = index_for_read(
            request.state.get("files", {}), self.allowed, path, result.content
        )
        if hint is None:
            return result
        text, identity = hint
        if any(
            isinstance(m, ToolMessage)
            and m.name == "read_file"
            and m.additional_kwargs.get(MARKER) == identity
            for m in messages
        ):
            return result
        return result.model_copy(
            update={
                "content": text + result.content,
                "additional_kwargs": {**result.additional_kwargs, MARKER: identity},
            }
        )

    def wrap_tool_call(self, request, handler):
        return self._augment(request, handler(request))

    async def awrap_tool_call(self, request, handler):
        result = await handler(request)
        return await asyncio.to_thread(self._augment, request, result)
