"""Source navigation boundaries and real graph state; run on the Linux server."""

import copy
import hashlib
import json
import unittest

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from agent_lab.models import build_model
from agent_lab.source_tools import MAX_RESPONSE_BYTES, inspect_source, make_source_tool


class SourceToolTests(unittest.TestCase):
    def setUp(self):
        self.text = '@dec\nclass Outer:\n    async def work(self):\n        def inner():\n            return "中文"\n        return inner()\n\ndef duplicate():\n    return 1\n\ndef duplicate():\n    return 2\n'
        self.files = {"/module.py": create_file_data(self.text)}
        self.allowed = {"/module.py"}
        self.digest = hashlib.sha256(self.text.encode()).hexdigest()

    def inspect(self, **kwargs):
        result = inspect_source(
            self.files, self.allowed, kwargs.pop("file_path", "/module.py"), **kwargs
        )
        self.assertLessEqual(len(result.encode()), MAX_RESPONSE_BYTES)
        return json.loads(result)

    def test_nested_decorated_async_and_duplicate_definitions_have_exact_ranges(self):
        outline = self.inspect()
        self.assertEqual(
            [x["name"] for x in outline["items"]],
            ["Outer", "Outer.work", "Outer.work.inner", "duplicate", "duplicate"],
        )
        self.assertEqual(len({x["id"] for x in outline["items"]}), 5)
        outer = self.inspect(
            symbol_id=outline["items"][0]["id"], expected_sha256=self.digest
        )
        self.assertEqual(outer["items"][0], {"line": 1, "text": "@dec"})
        self.assertEqual(outer["items"][-1]["line"], 6)
        self.assertEqual(outline["items"][1]["kind"], "AsyncFunctionDef")

    def test_pages_cover_symbols_and_lines_without_silent_loss(self):
        first = self.inspect(limit=2)
        rest = self.inspect(
            offset=first["next_offset"], limit=120, expected_sha256=self.digest
        )
        self.assertEqual(len(first["items"] + rest["items"]), 5)
        sid = first["items"][0]["id"]
        lines = []
        offset = 0
        while True:
            page = self.inspect(
                symbol_id=sid, offset=offset, limit=2, expected_sha256=self.digest
            )
            lines.extend(page["items"])
            offset = page["next_offset"]
            if offset is None:
                break
        self.assertEqual([x["line"] for x in lines], list(range(1, 7)))

    def test_changed_virtual_source_rejects_stale_ids_and_pages(self):
        initial = self.inspect()
        sid = initial["items"][0]["id"]
        self.files["/module.py"] = create_file_data("\n" + self.text)
        self.assertEqual(
            self.inspect(symbol_id=sid, expected_sha256=self.digest)["error"],
            "source_changed",
        )
        self.assertEqual(
            self.inspect(offset=1, expected_sha256=self.digest)["error"],
            "source_changed",
        )
        updated = self.inspect()
        self.assertNotEqual(updated["source_sha256"], self.digest)
        self.assertNotEqual(updated["items"][0]["id"], sid)

    def test_scope_hash_syntax_and_page_errors_do_not_mutate_state(self):
        before = copy.deepcopy(self.files)
        for path in ["/etc/passwd", "/../module.py", "module.py", "/missing.py"]:
            self.assertEqual(
                self.inspect(file_path=path)["error"], "file_outside_task_scope"
            )
        self.assertEqual(self.inspect(offset=1)["error"], "source_hash_required")
        self.assertEqual(
            self.inspect(symbol_id="L2:0")["error"], "source_hash_required"
        )
        for offset, limit in [(-1, 10), (0, 0), (0, 121), (True, 10)]:
            self.assertEqual(
                self.inspect(offset=offset, limit=limit)["error"], "invalid_page"
            )
        self.assertEqual(
            self.inspect(offset=99, expected_sha256=self.digest)["error"],
            "offset_out_of_range",
        )
        self.assertEqual(self.files, before)
        self.files["/module.py"] = create_file_data("def broken(:\n")
        self.assertEqual(self.inspect()["error"], "python_parse_failed")

    def test_unicode_byte_cap_and_oversized_line_are_explicit(self):
        self.files["/module.py"] = create_file_data(
            "def big():\n"
            + "".join('    value = "' + ("中" * 100) + '"\n' for _ in range(120))
        )
        outline = self.inspect()
        page = self.inspect(
            symbol_id=outline["items"][0]["id"],
            limit=120,
            expected_sha256=outline["source_sha256"],
        )
        self.assertLess(len(page["items"]), 120)
        self.assertIsNotNone(page["next_offset"])
        self.files["/module.py"] = create_file_data(
            'def big():\n    value = "' + ("中" * 4000) + '"\n'
        )
        outline = self.inspect()
        page = self.inspect(
            symbol_id=outline["items"][0]["id"],
            offset=1,
            expected_sha256=outline["source_sha256"],
        )
        self.assertEqual(page["error"], "single_item_exceeds_response_budget")

    def test_actual_graph_tool_reads_current_edited_state_after_checkpoint(self):
        model = build_model(
            {
                "mode": "scripted",
                "plan": [
                    {"tool": "inspect_python", "args": {"file_path": "/module.py"}},
                    {
                        "tool": "edit_file",
                        "args": {
                            "file_path": "/module.py",
                            "old_string": "return 1",
                            "new_string": "return 3",
                        },
                    },
                    {"tool": "inspect_python", "args": {"file_path": "/module.py"}},
                ],
            }
        )
        tool = make_source_tool(["module.py"])
        self.assertNotIn("runtime", tool.args)
        graph = create_deep_agent(
            model=model,
            backend=StateBackend(),
            tools=[tool],
            checkpointer=InMemorySaver(),
        )
        config = {"configurable": {"thread_id": "source-test"}}
        graph.invoke(
            {
                "messages": [HumanMessage(content="Run explicit source-tool fixture.")],
                "files": self.files,
            },
            config,
            interrupt_after=["tools"],
        )
        self.assertTrue(graph.get_state(config).next)
        state = graph.invoke(None, config)
        replies = [
            json.loads(m.content)
            for m in state["messages"]
            if isinstance(m, ToolMessage) and m.name == "inspect_python"
        ]
        self.assertEqual(len(replies), 2)
        self.assertEqual(replies[0]["source_sha256"], self.digest)
        self.assertEqual(
            replies[1]["source_sha256"],
            hashlib.sha256(
                self.text.replace("return 1", "return 3").encode()
            ).hexdigest(),
        )
        self.assertEqual(
            self.files["/module.py"]["content"], create_file_data(self.text)["content"]
        )


if __name__ == "__main__":
    unittest.main()
