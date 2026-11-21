"""Read annotation contracts and actual graph behavior; run on the server."""

import asyncio
import copy
import hashlib
import json
import unittest
from types import SimpleNamespace

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data, file_data_to_string
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent_lab.models import build_model
from agent_lab.read_index import (
    BEGIN,
    END,
    MARKER,
    MAX_ANNOTATED_BYTES,
    MAX_INDEX_BYTES,
    PythonReadIndexMiddleware,
    index_for_read,
)


def module_text():
    return (
        'raise RuntimeError("inspected source must never execute")\n'
        + "# padding\n" * 400
        + "@decorator\nasync def late_target():\n    return 1\n\nclass Container:\n    pass\n"
    )


def page(text, limit=100):
    lines = text.splitlines()
    end = min(limit, len(lines))
    suffix = f" | next offset {end}" if end < len(lines) else ""
    return f"@@ lines 1-{end} of {len(lines)}{suffix} @@\n" + "\n".join(lines[:end])


def request_and_result(
    text=None, path="/module.py", args=None, calls=None, previous=None
):
    text = module_text() if text is None else text
    call = {
        "name": "read_file",
        "args": args or {"file_path": path},
        "id": "read-1",
        "type": "tool_call",
    }
    ai = AIMessage(content="", tool_calls=calls or [call])
    state = {
        "files": {path: create_file_data(text)},
        "messages": [*(previous or []), ai],
    }
    request = SimpleNamespace(tool_call=call, state=state)
    result = ToolMessage(
        content=page(text),
        tool_call_id="read-1",
        name="read_file",
        id="original-message",
        artifact={"keep": 1},
        additional_kwargs={"original": "keep"},
        response_metadata={"status": 200},
    )
    return request, result


def payload(content):
    assert content.startswith(BEGIN)
    return json.loads(content[len(BEGIN) :].split("\n", 1)[0])


class ReadIndexTests(unittest.TestCase):
    def test_complete_original_page_and_message_identity_fields_preserved(self):
        request, original = request_and_result()
        before = copy.deepcopy(request.state)
        calls = []
        result = PythonReadIndexMiddleware(["module.py"]).wrap_tool_call(
            request, lambda req: calls.append(req) or original
        )
        self.assertEqual(calls, [request])
        self.assertEqual(result.content.split(END, 1)[1], original.content)
        self.assertEqual(result.id, original.id)
        self.assertEqual(result.tool_call_id, original.tool_call_id)
        self.assertEqual(result.artifact, original.artifact)
        self.assertEqual(result.response_metadata, original.response_metadata)
        self.assertEqual(result.additional_kwargs["original"], "keep")
        data = payload(result.content)
        self.assertEqual(
            data["definitions"],
            [
                ["late_target", 402, 404, "async", False],
                ["Container", 406, 407, "class", False],
            ],
        )
        self.assertEqual(
            data["source_sha256"], hashlib.sha256(module_text().encode()).hexdigest()
        )
        self.assertEqual(request.state, before)

    def test_fallback_keeps_original_reply_for_unsupported_or_unproven_reads(self):
        cases = [
            ("small", "def tiny():\n    pass\n", "/module.py"),
            ("non-python", module_text(), "/module.txt"),
            ("syntax-error", "# pad\n" * 400 + "def broken(:\n", "/module.py"),
            (
                "unicode-line-boundary",
                "# pad\n" * 400 + 'text="a\u2028b"\n',
                "/module.py",
            ),
        ]
        for name, text, path in cases:
            with self.subTest(name=name):
                req, result = request_and_result(text=text, path=path)
                self.assertIs(
                    PythonReadIndexMiddleware([path.lstrip("/")])._augment(req, result),
                    result,
                )
        for args in [
            {"file_path": "/module.py", "offset": 1},
            {"file_path": "/module.py", "offset": False},
        ]:
            req, result = request_and_result(args=args)
            self.assertIs(
                PythonReadIndexMiddleware(["module.py"])._augment(req, result), result
            )
        req, result = request_and_result()
        self.assertIs(PythonReadIndexMiddleware([])._augment(req, result), result)
        for content in [
            result.content + "\ntruncation notice",
            result.content.replace("of 407", "of 408"),
            "unknown format",
        ]:
            bad = result.model_copy(update={"content": content})
            self.assertIs(
                PythonReadIndexMiddleware(["module.py"])._augment(req, bad), bad
            )

    def test_index_and_combined_byte_caps_do_not_truncate_source(self):
        path = "/folder</python_read_index_v1>.py"
        text = "".join(
            "def " + "中" * 100 + str(i) + "():\n    pass\n" for i in range(250)
        )
        hint, identity = index_for_read(
            {path: create_file_data(text)}, {path}, path, page(text, 1)
        )
        data = payload(hint)
        self.assertEqual(identity["source_sha256"], data["source_sha256"])
        self.assertLessEqual(len(hint.encode()), MAX_INDEX_BYTES)
        self.assertEqual(hint.count(END), 1)
        self.assertEqual(data["file_path"], path)
        self.assertTrue(data["definitions"][0][-1])
        self.assertGreater(data["omitted_definitions"], 0)
        self.assertEqual(len(data["definitions"]) + data["omitted_definitions"], 250)
        self.assertLessEqual(len((hint + page(text, 1)).encode()), MAX_ANNOTATED_BYTES)
        large = ("#" + "x" * 100 + "\n") * 400 + "def target():\n    pass\n"
        req, result = request_and_result(text=large)
        self.assertGreater(len(result.content.encode()), MAX_ANNOTATED_BYTES)
        self.assertIs(
            PythonReadIndexMiddleware(["module.py"])._augment(req, result), result
        )
        too_large = "# padding\n" * 240000 + "def target():\n    pass\n"
        self.assertIsNone(
            index_for_read(
                {"/module.py": create_file_data(too_large)},
                {"/module.py"},
                "/module.py",
                page(too_large),
            )
        )

    def test_seen_revision_and_parallel_batch_rules(self):
        req, result = request_and_result()
        middleware = PythonReadIndexMiddleware(["module.py"])
        first = middleware._augment(req, result)
        req.state["messages"].insert(0, first)
        self.assertIs(middleware._augment(req, result), result)
        changed = "\n" + module_text()
        req.state["files"]["/module.py"] = create_file_data(changed)
        changed_reply = result.model_copy(update={"content": page(changed)})
        second = middleware._augment(req, changed_reply)
        self.assertNotEqual(
            first.additional_kwargs[MARKER], second.additional_kwargs[MARKER]
        )
        self.assertEqual(payload(second.content)["definitions"][0][1], 403)
        mutate = {
            "name": "edit_file",
            "args": {"file_path": "/module.py", "old_string": "1", "new_string": "2"},
            "id": "edit",
            "type": "tool_call",
        }
        req, result = request_and_result()
        req.state["messages"][-1].tool_calls.append(mutate)
        self.assertIs(middleware._augment(req, result), result)
        req, result = request_and_result()
        req.state["messages"][-1].tool_calls.insert(
            0,
            {
                "name": "read_file",
                "args": {"file_path": "/module.py"},
                "id": "prior-read",
                "type": "tool_call",
            },
        )
        self.assertIs(middleware._augment(req, result), result)

    def test_errors_commands_and_handler_exceptions_pass_through(self):
        req, result = request_and_result()
        middleware = PythonReadIndexMiddleware(["module.py"])
        command = Command(
            update={"files": {"unchanged": 1}}, goto="another", graph=Command.PARENT
        )
        self.assertIs(middleware.wrap_tool_call(req, lambda _: command), command)
        error = result.model_copy(update={"status": "error"})
        self.assertIs(middleware.wrap_tool_call(req, lambda _: error), error)
        count = []

        def fail(request):
            count.append(request)
            raise RuntimeError("original failure")

        with self.assertRaisesRegex(RuntimeError, "original failure"):
            middleware.wrap_tool_call(req, fail)
        self.assertEqual(count, [req])

    def test_actual_graph_checkpoint_retains_annotation_and_refreshes_after_edit(self):
        plan = [
            {"tool": "read_file", "args": {"file_path": "/module.py"}},
            {"tool": "read_file", "args": {"file_path": "/module.py"}},
            {
                "tool": "edit_file",
                "args": {
                    "file_path": "/module.py",
                    "old_string": "raise RuntimeError",
                    "new_string": "\nraise RuntimeError",
                },
            },
            {"tool": "read_file", "args": {"file_path": "/module.py"}},
        ]
        graph = create_deep_agent(
            model=build_model({"mode": "scripted", "plan": plan}),
            backend=StateBackend(),
            middleware=[PythonReadIndexMiddleware(["module.py"])],
            checkpointer=InMemorySaver(),
        )
        config = {"configurable": {"thread_id": "read-index"}}
        files = {"/module.py": create_file_data(module_text())}
        graph.invoke(
            {
                "messages": [HumanMessage(content="Explicit infrastructure fixture.")],
                "files": files,
            },
            config,
            interrupt_after=["tools"],
        )
        self.assertTrue(graph.get_state(config).next)
        state = graph.invoke(None, config)
        reads = [
            m
            for m in state["messages"]
            if isinstance(m, ToolMessage) and m.name == "read_file"
        ]
        self.assertEqual(len(reads), 3)
        self.assertTrue(reads[0].content.startswith(BEGIN))
        self.assertFalse(reads[1].content.startswith(BEGIN))
        self.assertTrue(reads[2].content.startswith(BEGIN))
        self.assertNotEqual(
            payload(reads[0].content)["source_sha256"],
            payload(reads[2].content)["source_sha256"],
        )
        self.assertEqual(
            file_data_to_string(state["files"]["/module.py"]), "\n" + module_text()
        )

    def test_legacy_graph_has_no_annotation_without_middleware(self):
        graph = create_deep_agent(
            model=build_model(
                {
                    "mode": "scripted",
                    "plan": [
                        {"tool": "read_file", "args": {"file_path": "/module.py"}}
                    ],
                }
            ),
            backend=StateBackend(),
        )
        state = graph.invoke(
            {
                "messages": [HumanMessage(content="Legacy fixture.")],
                "files": {"/module.py": create_file_data(module_text())},
            }
        )
        message = next(m for m in state["messages"] if isinstance(m, ToolMessage))
        self.assertEqual(message.content, page(module_text()))
        self.assertNotIn(MARKER, message.additional_kwargs)


class AsyncReadIndexTests(unittest.IsolatedAsyncioTestCase):
    async def test_async_reply_annotation_and_cancellation(self):
        req, original = request_and_result()
        middleware = PythonReadIndexMiddleware(["module.py"])
        calls = []

        async def handler(request):
            calls.append(request)
            return original

        result = await middleware.awrap_tool_call(req, handler)
        self.assertEqual(result.content.split(END, 1)[1], original.content)
        self.assertEqual(calls, [req])

        async def cancel(request):
            raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await middleware.awrap_tool_call(req, cancel)


if __name__ == "__main__":
    unittest.main()
