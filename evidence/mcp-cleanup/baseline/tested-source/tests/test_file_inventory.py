"""Real graph and HTTP contracts with an explicitly fake model, on the server."""

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_local_model as fixture_module

from deepagents.backends import StateBackend

from agent_lab.file_inventory import inventory_prompt
from agent_lab.inspect_run import inspect_run
from agent_lab.worker import RunError, run, validate_task


class FileInventoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.LocalModelTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture

    def enable(self, requests=2):
        self.f.task["required_features"] = [
            "file_inventory_v1",
            "model_request_budget_v1",
        ]
        self.f.task["model"]["request_budget"] = {
            "max_requests": requests,
            "max_request_bytes": 65536,
            "max_total_request_bytes": 262144,
        }

    def environment(self):
        return {
            "AGENT_LAB_MODEL_URL": f"http://127.0.0.1:{self.f.server.server_port}/v1",
            "AGENT_LAB_MODEL_KEY": "fixture-local-key",
        }

    def names(self, index):
        return {
            tool["function"]["name"] for tool in self.f.requests[index]["body"]["tools"]
        }

    def test_complete_quoted_unicode_inventory_edits_and_replays_with_bound_quota(self):
        note = 'notes/中文 "draft".txt'
        (self.f.repo / note).parent.mkdir()
        (self.f.repo / note).write_text("Keep this note unchanged.\n")
        (self.f.repo / "module.py").write_text(
            "value = 1\n" + "# padding\n" * 400 + "def target():\n    return 1\n"
        )
        self.f.git("add", note, "module.py")
        self.f.git("commit", "-m", "add note fixture")
        self.f.task["base_commit"] = self.f.git("rev-parse", "HEAD")
        self.f.task["files"].append(note)
        self.enable(requests=3)
        self.f.task["required_features"] += ["python_source_v1", "python_read_index_v1"]

        def response(body):
            done = {
                m.get("tool_call_id") for m in body["messages"] if m["role"] == "tool"
            }
            if "inventory-edit" in done:
                return {"role": "assistant", "content": "Prepared for review."}
            name, identifier, args = (
                (
                    "edit_file",
                    "inventory-edit",
                    {
                        "file_path": "/module.py",
                        "old_string": "value = 1",
                        "new_string": "value = 2",
                    },
                )
                if "inventory-read" in done
                else (
                    "read_file",
                    "inventory-read",
                    {"file_path": "/module.py", "offset": 0, "limit": 100},
                )
            )
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": identifier,
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                ],
            }

        self.f.response_script = response
        first = self.f.call()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(len(self.f.requests), 3)
        for i in range(3):
            self.assertNotIn("ls", self.names(i))
            self.assertTrue(
                {"read_file", "edit_file", "grep", "glob", "inspect_python"}
                <= self.names(i)
            )
        read = next(
            m
            for m in self.f.requests[1]["body"]["messages"]
            if m.get("tool_call_id") == "inventory-read"
        )
        self.assertTrue(read["content"].startswith("<python_read_index_v1>\n"))
        self.assertIn('"target"', read["content"])
        systems = "\n".join(
            m["content"]
            for m in self.f.requests[0]["body"]["messages"]
            if m["role"] == "system"
        )
        catalog = systems.split("Complete editable file inventory (JSON):\n", 1)[
            1
        ].split("\n", 1)[0]
        self.assertEqual(json.loads(catalog), ["/module.py", "/" + note])
        self.assertEqual(
            (self.f.root / "run/worktree" / note).read_text(),
            "Keep this note unchanged.\n",
        )
        self.assertEqual(self.f.call().returncode, 0)
        self.assertEqual(len(self.f.requests), 3)
        self.f.task["required_features"].remove("file_inventory_v1")
        self.assertNotEqual(self.f.call().returncode, 0)
        self.assertEqual(len(self.f.requests), 3)

    def test_unadvertised_ls_is_rejected_without_backend_execution_then_edit_is_verified(
        self,
    ):
        self.enable(requests=3)

        def response(body):
            done = {
                m.get("tool_call_id") for m in body["messages"] if m["role"] == "tool"
            }
            if "inventory-edit" in done:
                return {"role": "assistant", "content": "Prepared for review."}
            name, identifier, args = (
                (
                    "edit_file",
                    "inventory-edit",
                    {
                        "file_path": "/module.py",
                        "old_string": "value = 1",
                        "new_string": "value = 2",
                    },
                )
                if "inventory-ls" in done
                else ("ls", "inventory-ls", {"path": "/"})
            )
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": identifier,
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                ],
            }

        self.f.response_script = response
        with (
            patch.dict(os.environ, self.environment()),
            patch.object(
                StateBackend,
                "ls",
                side_effect=AssertionError("Listing must not execute"),
            ) as listing,
            patch.object(
                StateBackend,
                "als",
                side_effect=AssertionError("Async listing must not execute"),
            ) as async_listing,
        ):
            result = run(self.f.repo, self.f.root / "run", self.f.task)
        listing.assert_not_called()
        async_listing.assert_not_called()
        self.assertEqual(result["status"], "ready_for_review")
        self.assertEqual(
            (self.f.root / "run/worktree/module.py").read_text(), "value = 2\n"
        )
        self.assertEqual(len(self.f.requests), 3)
        for i in range(3):
            self.assertNotIn("ls", self.names(i))
        denied = [
            m
            for m in self.f.requests[1]["body"]["messages"]
            if m.get("tool_call_id") == "inventory-ls"
        ]
        self.assertEqual(len(denied), 1)
        self.assertIn("Directory listing is unavailable", denied[0]["content"])
        inspected = inspect_run(self.f.root / "run")
        self.assertEqual(inspected["tool_errors"], 1)
        self.assertEqual(inspected["tool_results"], 2)

    def test_same_model_alias_keeps_default_tools_before_and_after_opt_in_graph(self):
        default = copy.deepcopy(self.f.task)
        self.enable()
        inventory = copy.deepcopy(self.f.task)
        with patch.dict(os.environ, self.environment()):
            for i, task in enumerate([default, inventory, default]):
                result = run(self.f.repo, self.f.root / f"run-{i}", task)
                self.assertEqual(result["status"], "ready_for_review")
        self.assertEqual(len(self.f.requests), 6)
        self.assertIn("ls", self.names(0))
        self.assertNotIn("ls", self.names(2))
        self.assertIn("ls", self.names(4))

    def test_actual_checkpoint_sigkill_resumes_opt_in_graph_without_repeating_edit(
        self,
    ):
        self.enable()
        task = self.f.root / "pilot-task.json"
        task.write_text(json.dumps(self.f.task))
        script = Path(__file__).resolve().parents[1] / "benchmarks/model_pilot.py"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--repo",
                str(self.f.repo),
                "--task",
                str(task),
                "--output",
                str(self.f.root / "pilot"),
            ],
            env={**os.environ, **self.environment()},
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((self.f.root / "pilot/report.json").read_text())
        self.assertEqual(report["verified_trials"], 2)
        self.assertTrue(report["same_patch"])
        self.assertEqual(
            report["cases"][1]["checkpoint_interruption"]["tool_results"], 1
        )
        self.assertEqual(report["cases"][1]["result"]["tool_results"], 1)
        self.assertEqual(len(self.f.requests), 4)
        for i in range(4):
            self.assertNotIn("ls", self.names(i))
        ledger = json.loads(
            (self.f.root / "pilot/checkpoint-resume/model-requests.json").read_text()
        )
        self.assertEqual(len(ledger["reservations"]), 2)

    def test_oversized_inventory_is_rejected_whole_before_model_send(self):
        self.enable()
        files = [f"nested/module_{i:04d}.py" for i in range(400)]
        self.f.task["files"] = files
        with self.assertRaisesRegex(RunError, "Complete file inventory exceeds"):
            validate_task(self.f.task)
        with self.assertRaisesRegex(ValueError, "Complete file inventory exceeds"):
            inventory_prompt(files)
        self.assertEqual(self.f.requests, [])

    def test_scripted_plan_cannot_request_ls_under_the_inventory_contract(self):
        task = copy.deepcopy(self.f.task)
        task["model"] = {
            "mode": "scripted",
            "plan": [{"tool": "ls", "args": {"path": "/"}}],
        }
        self.assertEqual(validate_task(task), ["module.py"])
        task["required_features"] = ["file_inventory_v1"]
        with self.assertRaisesRegex(RunError, "Scripted plans only support"):
            validate_task(task)
