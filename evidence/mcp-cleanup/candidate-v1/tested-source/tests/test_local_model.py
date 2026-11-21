"""Exercise the real OpenAI-compatible transport using an explicitly fake server.

These checks establish adapter behavior, never model-inference capability.
"""

import importlib.util
import json
import os
import select
import signal
import subprocess
import sys
import tempfile
import threading
import time
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
        self.repair_value = None
        self.response_script = None
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
                    repairing = fixture.repair_value is not None and any(
                        message["role"] == "user"
                        and isinstance(message.get("content"), str)
                        and "The preceding candidate failed operator verification."
                        in message["content"]
                        for message in body["messages"]
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
                                            "old_string": "value = 2"
                                            if repairing
                                            else "value = 1",
                                            "new_string": f"value = {fixture.repair_value}"
                                            if repairing
                                            else "value = 2",
                                        }
                                    ),
                                },
                            }
                        ]
                    if fixture.response_script is not None:
                        message = fixture.response_script(body)
                    response = {
                        "id": "fixture-completion",
                        "object": "chat.completion",
                        "created": 1,
                        "model": body["model"],
                        "choices": [
                            {
                                "index": 0,
                                "message": message,
                                "finish_reason": "tool_calls"
                                if message.get("tool_calls")
                                else "stop",
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
        self.assertEqual(body["temperature"], 0)
        self.assertNotIn("top_p", body)
        self.assertNotIn("presence_penalty", body)
        self.assertNotIn("top_k", body)
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

    def test_declared_sampling_reaches_http_without_changing_tool_roundtrip(self):
        self.task["model"].update(
            temperature=0.7,
            top_p=0.8,
            presence_penalty=1.5,
            extra_body={"top_k": 20, "min_p": 0.0, "repeat_penalty": 1.0},
        )
        self.assertEqual(self.call().returncode, 0)
        self.assertEqual(len(self.requests), 2)
        for request in self.requests:
            body = request["body"]
            self.assertEqual(body["temperature"], 0.7)
            self.assertEqual(body["top_p"], 0.8)
            self.assertEqual(body["presence_penalty"], 1.5)
            self.assertEqual(body["top_k"], 20)
            self.assertEqual(body["min_p"], 0.0)
            self.assertEqual(body["repeat_penalty"], 1.0)
            self.assertEqual(body["seed"], 42)
            self.assertEqual(
                body.get("max_completion_tokens", body.get("max_tokens")), 64
            )

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

    def repair_task(self, expected=3, limit=1):
        self.repair_value = 3
        self.task["max_repair_attempts"] = limit
        self.task["verify"] = [
            {
                "argv": [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; p=Path('.checks'); "
                        "p.write_text(str(int(p.read_text())+1) if p.exists() else '1'); "
                        f"import module; assert module.value == {expected}, "
                        f"f'expected {expected}, got {{module.value}}'"
                    ),
                ]
            }
        ]

    def call_repair(self, paused=False):
        task = self.root / "repair-task.json"
        task.write_text(json.dumps(self.task))
        environment = dict(os.environ)
        environment.update(
            AGENT_LAB_MODEL_URL=f"http://127.0.0.1:{self.server.server_port}/v1",
            AGENT_LAB_MODEL_KEY="fixture-local-key",
        )
        argv = [
            sys.executable,
            "-m",
            "agent_lab.repair",
            "--repo",
            str(self.repo),
            "--task",
            str(task),
            "--run-dir",
            str(self.root / "repair"),
        ]
        if paused:
            return subprocess.Popen(
                argv + ["--hold-after", "repair_feedback"],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        return subprocess.run(
            argv, env=environment, capture_output=True, text=True, timeout=120
        )

    def test_failed_candidate_is_repaired_using_http_feedback_and_replay_is_free(self):
        self.repair_task()
        result = self.call_repair()
        self.assertEqual(result.returncode, 0, result.stderr)
        root = self.root / "repair"
        receipt = json.loads((root / "result.json").read_text())
        self.assertEqual(receipt["accepted_attempt"], 1)
        self.assertEqual(
            [r["status"] for r in receipt["attempts"]],
            ["verification_failed", "ready_for_review"],
        )
        self.assertEqual(
            (root / "attempts/000/worktree/module.py").read_text(), "value = 2\n"
        )
        self.assertEqual(
            (root / "attempts/001/worktree/module.py").read_text(), "value = 3\n"
        )
        self.assertIn(
            "expected 3, got 2", (root / "attempts/000/feedback.json").read_text()
        )
        self.assertTrue(
            any(
                "expected 3, got 2" in str(m.get("content"))
                for m in self.requests[2]["body"]["messages"]
            )
        )
        self.assertEqual(len(self.requests), 4)
        self.assertEqual(self.call_repair().returncode, 0)
        self.assertEqual(len(self.requests), 4)
        for number in ("000", "001"):
            self.assertEqual(
                (root / "attempts" / number / "worktree/.checks").read_text(), "1"
            )

    def test_repair_budget_exhaustion_persists_without_extra_model_or_verifier_calls(
        self,
    ):
        self.repair_task(expected=4)
        first = self.call_repair()
        self.assertEqual(first.returncode, 2)
        self.assertIn("Repair budget exhausted", first.stderr)
        self.assertEqual(self.call_repair().returncode, 2)
        self.assertEqual(len(self.requests), 4)
        root = self.root / "repair"
        self.assertFalse((root / "result.json").exists())
        self.assertEqual(
            json.loads((root / "status.json").read_text())["status"],
            "repair_budget_exhausted",
        )
        for number in ("000", "001"):
            self.assertEqual(
                (root / "attempts" / number / "worktree/.checks").read_text(), "1"
            )

    def test_feedback_sigkill_resumes_and_a_live_parent_keeps_exclusive_ownership(self):
        self.repair_task()
        process = self.call_repair(paused=True)
        buffered = b""
        try:
            deadline = time.monotonic() + 90
            while b'"stage": "repair_feedback"' not in buffered:
                self.assertLess(time.monotonic(), deadline)
                self.assertIsNone(process.poll())
                if select.select([process.stdout], [], [], 1)[0]:
                    buffered += os.read(process.stdout.fileno(), 65536)
            contender = self.call_repair()
            self.assertEqual(contender.returncode, 2)
            self.assertIn("Another worker owns", contender.stderr)
            os.kill(process.pid, signal.SIGKILL)
            process.communicate(timeout=10)
            self.assertEqual(process.returncode, -signal.SIGKILL)
            resumed = self.call_repair()
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(len(self.requests), 4)
            self.assertEqual(
                (self.root / "repair/attempts/000/worktree/.checks").read_text(), "1"
            )
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=10)

    def test_modified_failed_log_is_rejected_before_another_model_request(self):
        self.repair_task(limit=0)
        self.assertEqual(self.call_repair().returncode, 2)
        (self.root / "repair/attempts/000/verification-0.log").write_text("changed")
        result = self.call_repair()
        self.assertEqual(result.returncode, 2)
        self.assertIn("log changed", result.stderr)
        self.assertEqual(len(self.requests), 2)

    def test_single_candidate_entry_rejects_repair_tasks_before_model_requests(self):
        self.repair_task()
        result = self.call()
        self.assertEqual(result.returncode, 2)
        self.assertIn("Use agent_lab.repair", result.stderr)
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
