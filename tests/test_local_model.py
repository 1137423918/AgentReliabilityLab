"""Exercise the real OpenAI-compatible transport using an explicitly fake server.

These checks establish adapter behavior, never model-inference capability.
"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch


@unittest.skipUnless(
    importlib.util.find_spec("langchain_openai"), "Install local-model extra"
)
class LocalModelTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        for args in [
            ["init", "-b", "main"],
            ["config", "user.name", "Adapter fixture"],
            ["config", "user.email", "fixture@example.invalid"],
        ]:
            self.git(*args)
        (self.repo / "module.py").write_text("value = 1\n")
        self.git("add", "module.py")
        self.git("commit", "-m", "baseline")
        self.requests = []
        self.response_status = 200
        self.response_gate = threading.Event()
        self.response_gate.set()
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fixture.requests.append({"path": self.path, "body": body})
                fixture.response_gate.wait(timeout=15)
                if fixture.response_status != 200:
                    response = {
                        "error": {
                            "message": "Fixture service unavailable",
                            "type": "server_error",
                        }
                    }
                else:
                    tool_done = any(
                        message["role"] == "tool" for message in body["messages"]
                    )
                    message = {
                        "role": "assistant",
                        "content": "Prepared for review." if tool_done else "",
                    }
                    if not tool_done:
                        message["tool_calls"] = [
                            {
                                "id": "fixture-edit-1",
                                "type": "function",
                                "function": {
                                    "name": "edit_file",
                                    "arguments": json.dumps(
                                        {
                                            "file_path": "/module.py",
                                            "old_string": "value = 1",
                                            "new_string": "value = 2",
                                        }
                                    ),
                                },
                            }
                        ]
                    response = {
                        "id": "fixture-completion",
                        "object": "chat.completion",
                        "created": 1,
                        "model": body["model"],
                        "choices": [
                            {
                                "index": 0,
                                "message": message,
                                "finish_reason": "stop" if tool_done else "tool_calls",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 11,
                            "completion_tokens": 7,
                            "total_tokens": 18,
                        },
                    }
                encoded = json.dumps(response).encode()
                try:
                    self.send_response(fixture.response_status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.task = {
            "base_commit": self.git("rev-parse", "HEAD"),
            "files": ["module.py"],
            "prompt": "Set value to 2.",
            "max_graph_steps": 20,
            "model": {
                "mode": "local-openai",
                "model": "fixture-model",
                "max_output_tokens": 64,
                "timeout_seconds": 2,
                "seed": 42,
            },
            "verify": [
                {
                    "argv": [
                        sys.executable,
                        "-c",
                        "import os,module; assert module.value == 2; assert 'AGENT_LAB_MODEL_KEY' not in os.environ",
                    ]
                }
            ],
        }

    def stop_server(self):
        self.response_gate.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())
        self.temporary.cleanup()

    def git(self, *args):
        return (
            subprocess.check_output(
                ["git", "-C", str(self.repo), *args], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )

    def call(self):
        task_path = self.root / "task.json"
        task_path.write_text(json.dumps(self.task))
        environment = dict(os.environ)
        environment.update(
            AGENT_LAB_MODEL_URL=f"http://127.0.0.1:{self.server.server_port}/v1",
            AGENT_LAB_MODEL_KEY="fixture-local-key",
        )
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_lab.worker",
                "--repo",
                str(self.repo),
                "--task",
                str(task_path),
                "--run-dir",
                str(self.root / "run"),
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_http_tool_roundtrip_edits_verifies_and_replays_without_requests(self):
        first = self.call()
        self.assertEqual(first.returncode, 0, first.stderr)
        result = json.loads((self.root / "run/result.json").read_text())
        self.assertEqual(result["status"], "ready_for_review")
        self.assertEqual(result["model_mode"], "local-openai")
        self.assertEqual(
            (self.root / "run/worktree/module.py").read_text(), "value = 2\n"
        )
        self.assertEqual(len(self.requests), 2)
        body = self.requests[0]["body"]
        self.assertEqual(self.requests[0]["path"], "/v1/chat/completions")
        self.assertEqual(body.get("max_completion_tokens", body.get("max_tokens")), 64)
        self.assertEqual(body["seed"], 42)
        self.assertTrue(
            any(
                message["role"] == "tool"
                for message in self.requests[1]["body"]["messages"]
            )
        )
        names = {tool["function"]["name"] for tool in body["tools"]}
        self.assertIn("edit_file", names)
        self.assertFalse(names & {"task", "execute", "write_todos"})
        self.assertEqual(self.call().returncode, 0)
        self.assertEqual(len(self.requests), 2)

    def test_unavailable_endpoint_does_not_retry_or_create_success(self):
        self.response_status = 503
        result = self.call()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.requests), 1)
        self.assertFalse((self.root / "run/result.json").exists())
        self.assertEqual(
            json.loads((self.root / "run/status.json").read_text())["status"], "failed"
        )

    def test_read_timeout_does_not_retry_or_create_success(self):
        self.response_gate.clear()
        self.task["model"]["timeout_seconds"] = 0.1
        result = self.call()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.requests), 1)
        self.assertFalse((self.root / "run/result.json").exists())

    def test_non_loopback_endpoint_is_rejected_before_request(self):
        from agent_lab.models import build_model

        with patch.dict(os.environ, AGENT_LAB_MODEL_URL="https://example.invalid/v1"):
            with self.assertRaisesRegex(ValueError, "loopback"):
                build_model(self.task["model"])
        self.assertEqual(self.requests, [])

    def test_pilot_resumes_after_last_tool_without_demanding_another_tool(self):
        task_path = self.root / "pilot-task.json"
        task_path.write_text(json.dumps(self.task))
        environment = dict(os.environ)
        environment.update(
            AGENT_LAB_MODEL_URL=f"http://127.0.0.1:{self.server.server_port}/v1",
            AGENT_LAB_MODEL_KEY="fixture-local-key",
        )
        script = Path(__file__).resolve().parents[1] / "benchmarks/model_pilot.py"
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--repo",
                str(self.repo),
                "--task",
                str(task_path),
                "--output",
                str(self.root / "pilot"),
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((self.root / "pilot/report.json").read_text())
        self.assertEqual(report["verified_trials"], 2)
        self.assertTrue(report["same_patch"])
        recovered = report["cases"][1]
        self.assertEqual(recovered["checkpoint_interruption"]["tool_results"], 1)
        self.assertEqual(recovered["result"]["tool_results"], 1)
        self.assertEqual(len(self.requests), 4)


if __name__ == "__main__":
    unittest.main()
