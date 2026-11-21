"""Bounded, revision-checked Python navigation over current virtual files only."""

import ast
import hashlib
import json
import sys

from deepagents.backends.utils import file_data_to_string
from langchain.tools import ToolRuntime, tool

PARSER = f"Python {sys.version_info.major}.{sys.version_info.minor} AST"
MAX_RESPONSE_BYTES = 8192
MAX_SOURCE_BYTES = 2 * 1024 * 1024


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def failure(code, **fields):
    return encode({"status": "error", "error": code, **fields})


class Symbols(ast.NodeVisitor):
    def __init__(self):
        self.scope = []
        self.entries = []

    def definition(self, node):
        qualified = ".".join([*self.scope, node.name])
        self.entries.append(
            {
                "id": f"L{node.lineno}:{node.col_offset}",
                "name": qualified[:160],
                "name_truncated": len(qualified) > 160,
                "kind": type(node).__name__,
                "start_line": min(
                    [node.lineno, *(d.lineno for d in node.decorator_list)]
                ),
                "end_line": node.end_lineno,
            }
        )
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_ClassDef = definition
    visit_FunctionDef = definition
    visit_AsyncFunctionDef = definition


def inspect_source(
    files, allowed, file_path, symbol_id="", offset=0, limit=40, expected_sha256=""
):
    """Return a complete JSON page; never execute or import the inspected code."""
    if file_path not in allowed or file_path not in files:
        return failure("file_outside_task_scope")
    if not file_path.endswith(".py"):
        return failure("python_files_only")
    if (
        type(offset) is not int
        or type(limit) is not int
        or offset < 0
        or not 1 <= limit <= 120
    ):
        return failure("invalid_page", max_limit=120)
    if not isinstance(symbol_id, str) or len(symbol_id) > 80:
        return failure("invalid_symbol_id")
    text = file_data_to_string(files[file_path])
    if len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
        return failure("source_exceeds_2_mib")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if (symbol_id or offset) and not expected_sha256:
        return failure("source_hash_required", source_sha256=digest)
    if expected_sha256 and expected_sha256 != digest:
        return failure("source_changed", source_sha256=digest)
    try:
        tree = ast.parse(text)
        visitor = Symbols()
        visitor.visit(tree)
    except (SyntaxError, ValueError, RecursionError) as error:
        return failure(
            "python_parse_failed",
            source_sha256=digest,
            parser=PARSER,
            line=getattr(error, "lineno", None),
        )
    header = {
        "status": "ok",
        "source_sha256": digest,
        "file_lines": len(text.splitlines()),
        "parser": PARSER,
        "mode": "source" if symbol_id else "outline",
        "offset": offset,
    }
    if symbol_id:
        matches = [entry for entry in visitor.entries if entry["id"] == symbol_id]
        if not matches:
            return failure("symbol_not_found", source_sha256=digest)
        entry = matches[0]
        header["symbol"] = entry
        lines = text.splitlines()[entry["start_line"] - 1 : entry["end_line"]]
        items = [
            {"line": entry["start_line"] + index, "text": line}
            for index, line in enumerate(lines)
        ]
    else:
        items = visitor.entries
    if offset > len(items):
        return failure("offset_out_of_range", source_sha256=digest, total=len(items))
    page = []
    header.update(total=len(items), items=page, next_offset=None)
    for item in items[offset : offset + limit]:
        next_offset = offset + len(page) + 1
        candidate = {
            **header,
            "items": [*page, item],
            "next_offset": next_offset if next_offset < len(items) else None,
        }
        if len(encode(candidate).encode("utf-8")) > MAX_RESPONSE_BYTES:
            if not page:
                return failure(
                    "single_item_exceeds_response_budget",
                    source_sha256=digest,
                    offset=offset,
                    max_response_bytes=MAX_RESPONSE_BYTES,
                )
            break
        page.append(item)
    next_offset = offset + len(page)
    header["next_offset"] = next_offset if next_offset < len(items) else None
    return encode(header)


def make_source_tool(paths):
    allowed = frozenset("/" + path for path in paths)

    @tool
    def inspect_python(
        file_path: str,
        runtime: ToolRuntime,
        symbol_id: str = "",
        offset: int = 0,
        limit: int = 40,
        expected_sha256: str = "",
    ) -> str:
        """Locate Python definitions in current virtual files without execution.

        First omit symbol_id for a paginated outline (functions/classes, including
        nested methods and decorators). Select a returned id and copy its
        source_sha256 into expected_sha256 to read that symbol's exact lines.
        offset is zero-based within the outline or selected symbol; limit is at
        most 120 items. Responses are at most 8192 UTF-8 bytes with next_offset.
        Any continuation requires expected_sha256; after an edit, refresh the
        outline. Uses the worker Python AST grammar. Other file types use grep/read_file.
        """
        return inspect_source(
            runtime.state.get("files", {}),
            allowed,
            file_path,
            symbol_id,
            offset,
            limit,
            expected_sha256,
        )

    return inspect_python
