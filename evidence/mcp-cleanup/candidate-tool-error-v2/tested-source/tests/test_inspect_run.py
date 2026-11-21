"""Read-only graph inspection contracts; execute on the authorized server."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver

from agent_lab.inspect_run import InspectionError, encoded, inspect_run, main
from agent_lab.models import ScriptedMaintenanceModel, build_model
from agent_lab.read_index import PythonReadIndexMiddleware
from agent_lab.source_tools import make_source_tool


SECRET = "private-prompt-source-arguments-must-not-appear"


class InspectRunTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="inspect-run-")
        self.directory = Path(self.temporary.name)
        self.text = (
            f'private = "{SECRET}"\n'
            + "# padding\n" * 400
            + "def target():\n    return 1\n"
        )
        self.task = {
            "base_commit": "0" * 40,
            "files": ["module.py"],
            "prompt": SECRET,
            "model": {"mode": "local-openai", "model": "must-not-construct"},
            "required_features": ["python_source_v1", "python_read_index_v1"],
            "verify": [
                {"argv": ["python", "-c", 'raise AssertionError("never execute")']}
            ],
        }
        self.save_manifest()
        self.connection = sqlite3.connect(
            self.directory / "checkpoints.sqlite", check_same_thread=False
        )
        self.saver = SqliteSaver(self.connection)
        self.model = build_model(
            {
                "mode": "scripted",
                "plan": [
                    {"tool": "read_file", "args": {"file_path": "/module.py"}},
                    {
                        "tool": "edit_file",
                        "args": {
                            "file_path": "/module.py",
                            "old_string": "return 1",
                            "new_string": "return 2",
                        },
                    },
                ],
            }
        )
        self.graph = create_deep_agent(
            model=self.model,
            backend=StateBackend(),
            checkpointer=self.saver,
            tools=[make_source_tool(self.task["files"])],
            middleware=[PythonReadIndexMiddleware(self.task["files"])],
        )
        self.config = {"configurable": {"thread_id": "maintenance"}}

    def tearDown(self):
        self.connection.close()
        self.temporary.cleanup()

    def save_manifest(self):
        manifest = {
            "task": self.task,
            "base_commit": self.task["base_commit"],
            "task_sha256": hashlib.sha256(
                json.dumps(self.task, sort_keys=True).encode()
            ).hexdigest(),
        }
        (self.directory / "manifest.json").write_text(json.dumps(manifest))

    def first_checkpoint(self, files=None):
        self.graph.invoke(
            {
                "messages": [HumanMessage(content=SECRET)],
                "files": files or {"/module.py": create_file_data(self.text)},
            },
            self.config,
            interrupt_after=["tools"],
            durability="sync",
        )

    def test_live_graph_delta_messages_and_edited_virtual_revision(self):
        self.first_checkpoint()
        before = inspect_run(self.directory)
        self.assertEqual((before["model_turns"], before["tool_results"]), (1, 1))
        self.assertEqual(before["pending"], ["model"])
        self.assertEqual(before["indexed_read_result_markers"], 1)
        self.graph.invoke(
            None, self.config, interrupt_after=["tools"], durability="sync"
        )
        after = inspect_run(self.directory)
        self.assertEqual((after["model_turns"], after["tool_results"]), (2, 2))
        self.assertEqual(
            after["virtual_files"][0]["sha256"],
            hashlib.sha256(
                self.text.replace("return 1", "return 2").encode()
            ).hexdigest(),
        )
        self.assertNotEqual(
            before["virtual_files"][0]["sha256"], after["virtual_files"][0]["sha256"]
        )

    def test_inspection_never_invokes_declared_or_scripted_models_or_commands(self):
        self.first_checkpoint()
        with (
            patch.object(
                ScriptedMaintenanceModel,
                "_generate",
                side_effect=AssertionError("No inference"),
            ),
            patch("agent_lab.inspect_run.build_model", wraps=build_model) as builder,
        ):
            result = inspect_run(self.directory)
        builder.assert_called_once_with({"mode": "scripted", "plan": []})
        self.assertFalse(result["model_invoked"])
        self.assertEqual(result["tool_results"], 1)

    def test_database_and_run_artifacts_remain_byte_identical(self):
        self.first_checkpoint()
        before = {
            p.name: p.read_bytes()
            for p in self.directory.iterdir()
            if p.is_file() and not p.name.endswith("-shm")
        }
        inspect_run(self.directory)
        inspect_run(self.directory)
        after = {
            p.name: p.read_bytes()
            for p in self.directory.iterdir()
            if p.is_file() and not p.name.endswith("-shm")
        }
        self.assertEqual(before, after)
        # A quiescent WAL database can need fresh coordination files on read.
        self.connection.close()
        data_before = {
            p.name: p.read_bytes()
            for p in self.directory.iterdir()
            if p.is_file() and not p.name.endswith(("-shm", "-wal"))
        }
        wal = self.directory / "checkpoints.sqlite-wal"
        wal_before = wal.read_bytes() if wal.exists() else b""
        summary = inspect_run(self.directory)
        self.assertEqual(summary["tool_results"], 1)
        self.assertEqual(
            data_before,
            {
                p.name: p.read_bytes()
                for p in self.directory.iterdir()
                if p.is_file() and not p.name.endswith(("-shm", "-wal"))
            },
        )
        self.assertEqual(wal.read_bytes() if wal.exists() else b"", wal_before)

    def test_missing_database_does_not_create_it(self):
        missing = self.directory / "missing"
        missing.mkdir()
        (missing / "manifest.json").write_bytes(
            (self.directory / "manifest.json").read_bytes()
        )
        with self.assertRaises(InspectionError):
            inspect_run(missing)
        self.assertEqual([p.name for p in missing.iterdir()], ["manifest.json"])

    def test_tampered_manifest_is_rejected_before_opening_database(self):
        self.first_checkpoint()
        p = self.directory / "manifest.json"
        manifest = json.loads(p.read_text())
        manifest["task"]["prompt"] = "tampered"
        p.write_text(json.dumps(manifest))
        with patch(
            "agent_lab.inspect_run.sqlite3.connect",
            side_effect=AssertionError("Must not connect"),
        ):
            with self.assertRaises(InspectionError):
                inspect_run(self.directory)

    def test_bounded_unicode_metadata_excludes_prompt_arguments_and_source(self):
        files = {"/module.py": create_file_data(self.text)}
        files.update(
            {
                "/" + "中文" * 100 + str(i) + ".py": create_file_data(SECRET)
                for i in range(100)
            }
        )
        self.first_checkpoint(files)
        result = inspect_run(self.directory)
        self.assertLessEqual(len(encoded(result)), 8192)
        self.assertEqual(result["virtual_file_count"], 101)
        self.assertEqual(result["unexpected_virtual_file_count"], 100)
        self.assertGreater(result["virtual_files_omitted"], 0)
        self.assertNotIn(SECRET, encoded(result).decode())
        self.assertTrue(any("中" in row["path"] for row in result["virtual_files"]))

    def test_empty_checkpoint_and_cli_error_do_not_claim_success(self):
        self.saver.setup()
        with self.assertRaises(InspectionError):
            inspect_run(self.directory)
        out, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(errors):
            code = main(["--run-dir", str(self.directory)])
        self.assertEqual(code, 1)
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(json.loads(errors.getvalue())["error"], "InspectionError")
        self.assertNotIn(SECRET, errors.getvalue())

    def test_result_status_is_an_observation_not_acceptance_revalidation(self):
        self.first_checkpoint()
        (self.directory / "result.json").write_text(
            json.dumps({"status": "ready_for_review", "secret": SECRET})
        )
        result = inspect_run(self.directory)
        self.assertEqual(result["observed_result_status"], "ready_for_review")
        self.assertFalse(result["artifacts_observed_not_revalidated"]["patch.diff"])
        self.assertFalse(
            result["artifacts_observed_not_revalidated"]["verification.json"]
        )
        out, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(errors):
            self.assertEqual(main(["--run-dir", str(self.directory)]), 0)
        self.assertEqual(json.loads(out.getvalue())["tool_results"], 1)
        self.assertNotIn(SECRET, out.getvalue())
        self.assertEqual(errors.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
