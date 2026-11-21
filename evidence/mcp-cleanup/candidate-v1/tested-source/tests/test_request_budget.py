"""Actual HTTP and process recovery checks, with an explicitly fake model."""

import asyncio
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

import test_local_model as fixture_module

from agent_lab.request_budget import RequestBudget, RequestBudgetError, task_limits


class RequestBudgetTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.LocalModelTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture

    def enable(self, count=2, single=131072, total=1048576):
        self.f.task["required_features"] = ["model_request_budget_v1"]
        self.f.task["model"]["request_budget"] = {
            "max_requests": count,
            "max_request_bytes": single,
            "max_total_request_bytes": total,
        }

    def ledger(self, directory=None):
        return json.loads(
            ((directory or self.f.root / "run") / "model-requests.json").read_text()
        )

    def test_http_errors_remain_charged_across_restarts_and_body_hash_matches(self):
        self.enable()
        self.f.response_status = 503
        for _ in range(4):
            result = self.f.call()
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.f.requests), 2)
        self.assertIn("budget exhausted", result.stderr)
        entries = self.ledger()["reservations"]
        self.assertEqual(len(entries), 2)
        for entry, request in zip(entries, self.f.requests):
            body = json.dumps(
                request["body"],
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
            self.assertEqual(entry["request_body_bytes"], len(body))
            self.assertEqual(
                entry["request_body_sha256"], hashlib.sha256(body).hexdigest()
            )
            self.assertEqual(entry["http_status"], 503)
        self.assertFalse((self.f.root / "run/result.json").exists())

    def test_sigkill_after_server_receives_request_cannot_reset_budget(self):
        self.enable(count=1)
        self.f.response_gate.clear()
        task_path = self.f.root / "task.json"
        task_path.write_text(json.dumps(self.f.task))
        environment = dict(
            os.environ,
            AGENT_LAB_MODEL_URL=f"http://127.0.0.1:{self.f.server.server_port}/v1",
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "agent_lab.worker",
                "--repo",
                str(self.f.repo),
                "--task",
                str(task_path),
                "--run-dir",
                str(self.f.root / "run"),
            ],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 60
            while not self.f.requests:
                self.assertIsNone(process.poll())
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.02)
            self.assertEqual(len(self.ledger()["reservations"]), 1)
            self.assertEqual(
                self.ledger()["reservations"][0]["transport_observation"], "reserved"
            )
            process.kill()
            self.assertEqual(process.wait(timeout=10), -9)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            self.f.response_gate.set()
        result = self.f.call()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("budget exhausted", result.stderr)
        self.assertEqual(len(self.f.requests), 1)
        self.assertEqual(len(self.ledger()["reservations"]), 1)
        self.assertFalse((self.f.root / "run/result.json").exists())

    def test_timeout_remains_charged_without_another_request(self):
        self.enable(count=1)
        self.f.task["model"]["timeout_seconds"] = 0.1
        self.f.response_gate.clear()
        self.assertNotEqual(self.f.call().returncode, 0)
        self.f.response_gate.set()
        self.assertNotEqual(self.f.call().returncode, 0)
        self.assertEqual(len(self.f.requests), 1)
        self.assertEqual(len(self.ledger()["reservations"]), 1)

    def test_success_and_cached_worker_replay_keep_the_same_request_receipt(self):
        self.enable(count=2)
        first = self.f.call()
        self.assertEqual(first.returncode, 0, first.stderr)
        receipt = json.loads((self.f.root / "run/result.json").read_text())
        self.assertEqual(
            receipt["model_request_budget_snapshot"]["reserved_requests"], 2
        )
        self.assertEqual(self.f.call().returncode, 0)
        self.assertEqual(len(self.f.requests), 2)
        self.assertEqual(len(self.ledger()["reservations"]), 2)

    def test_single_request_cap_blocks_before_network_and_consumes_nothing(self):
        self.enable(single=1)
        for _ in range(2):
            result = self.f.call()
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.f.requests, [])
        self.assertEqual(self.ledger()["reservations"], [])

    def test_total_json_body_cap_is_shared_across_restarts(self):
        self.f.response_status = 503
        self.assertNotEqual(self.f.call().returncode, 0)
        size = len(
            json.dumps(
                self.f.requests[0]["body"], ensure_ascii=False, separators=(",", ":")
            ).encode()
        )
        # A new run directory isolates this measured legacy control from budgeted work.
        (self.f.root / "run").rename(self.f.root / "legacy-control")
        self.f.requests.clear()
        self.enable(count=5, total=2 * size - 1)
        for _ in range(3):
            self.assertNotEqual(self.f.call().returncode, 0)
        self.assertEqual(len(self.f.requests), 1)
        self.assertEqual(len(self.ledger()["reservations"]), 1)
        self.assertEqual(self.ledger()["reservations"][0]["request_body_bytes"], size)

    def test_repair_attempts_share_cap_and_direct_child_resume_is_rejected(self):
        self.f.repair_task(expected=3)
        self.enable(count=2)
        first = self.f.call_repair()
        self.assertNotEqual(first.returncode, 0)
        root = self.f.root / "repair"
        self.assertEqual(len(self.f.requests), 2)
        self.assertEqual(len(self.ledger(root)["reservations"]), 2)
        self.assertTrue((root / "attempts/000/feedback.json").exists())
        self.assertEqual((root / "attempts/000/worktree/.checks").read_text(), "1")
        self.assertNotEqual(self.f.call_repair().returncode, 0)
        self.assertEqual(len(self.f.requests), 2)
        self.assertEqual((root / "attempts/000/worktree/.checks").read_text(), "1")
        child = root / "attempts/001"
        manifest = json.loads((child / "manifest.json").read_text())
        self.assertEqual(manifest["model_request_budget"]["scope"], "shared")
        path = self.f.root / "child-task.json"
        path.write_text(json.dumps(manifest["task"]))
        environment = dict(
            os.environ,
            AGENT_LAB_MODEL_URL=f"http://127.0.0.1:{self.f.server.server_port}/v1",
        )
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_lab.worker",
                "--repo",
                str(self.f.repo),
                "--task",
                str(path),
                "--run-dir",
                str(child),
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("original repair entry point", result.stderr)
        self.assertEqual(len(self.f.requests), 2)
        self.assertFalse((root / "result.json").exists())

    def test_accepted_repair_and_cached_replay_do_not_spend_again(self):
        self.f.repair_task(expected=3)
        self.enable(count=4)
        result = self.f.call_repair()
        self.assertEqual(result.returncode, 0, result.stderr)
        root = self.f.root / "repair"
        self.assertEqual(len(self.f.requests), 4)
        receipt = json.loads((root / "result.json").read_text())
        self.assertEqual(receipt["accepted_attempt"], 1)
        self.assertEqual(
            receipt["model_request_budget_snapshot"]["reserved_requests"], 4
        )
        self.assertEqual(self.f.call_repair().returncode, 0)
        self.assertEqual(len(self.f.requests), 4)
        self.assertEqual(len(self.ledger(root)["reservations"]), 4)

    def test_missing_or_corrupt_journal_and_changed_policy_cannot_reset(self):
        self.enable(count=1)
        self.f.response_status = 503
        self.assertNotEqual(self.f.call().returncode, 0)
        path = self.f.root / "run/model-requests.json"
        original = path.read_bytes()
        path.unlink()
        self.assertNotEqual(self.f.call().returncode, 0)
        self.assertFalse(path.exists())
        manifest_path = self.f.root / "run/manifest.json"
        manifest = manifest_path.read_bytes()
        manifest_path.unlink()
        self.assertNotEqual(self.f.call().returncode, 0)
        self.assertFalse(path.exists())
        self.assertFalse(manifest_path.exists())
        manifest_path.write_bytes(manifest)
        path.write_bytes(original)
        value = json.loads(original)
        value["reservations"] = []
        path.write_text(json.dumps(value))
        self.assertNotEqual(self.f.call().returncode, 0)
        path.write_bytes(original)
        self.f.task["model"]["request_budget"]["max_requests"] = 3
        self.assertNotEqual(self.f.call().returncode, 0)
        self.assertEqual(len(self.f.requests), 1)

    def test_feature_pairing_limits_and_async_fail_closed(self):
        original = copy.deepcopy(self.f.task)
        self.enable()
        for key, value in [
            ("max_requests", True),
            ("max_request_bytes", 0),
            ("max_total_request_bytes", -1),
        ]:
            task = copy.deepcopy(self.f.task)
            task["model"]["request_budget"][key] = value
            with self.assertRaises(RequestBudgetError):
                task_limits(task)
        task = copy.deepcopy(self.f.task)
        task["required_features"] = []
        with self.assertRaises(RequestBudgetError):
            task_limits(task)
        task = copy.deepcopy(original)
        task["required_features"] = ["model_request_budget_v1"]
        with self.assertRaises(RequestBudgetError):
            task_limits(task)
        from agent_lab.models import model_for_run

        budget = RequestBudget(
            self.f.root, "a" * 64, self.f.task["model"]["request_budget"], create=True
        )
        with patch.dict(
            os.environ,
            AGENT_LAB_MODEL_URL=f"http://127.0.0.1:{self.f.server.server_port}/v1",
        ):
            with model_for_run(self.f.task["model"], budget) as model:
                with self.assertRaisesRegex(RequestBudgetError, "synchronous"):
                    asyncio.run(model.ainvoke("Should not send"))

                async def try_stream():
                    async for _ in model.astream("Should not stream"):
                        self.fail("Unsupported async stream yielded a response")

                with self.assertRaisesRegex(RequestBudgetError, "synchronous"):
                    asyncio.run(try_stream())
        self.assertEqual(self.f.requests, [])
        self.assertEqual(budget.summary()["reserved_requests"], 0)

    def test_concurrent_process_reservations_cannot_overspend(self):
        limits = {
            "max_requests": 3,
            "max_request_bytes": 100,
            "max_total_request_bytes": 300,
        }
        budget = RequestBudget(self.f.root, "a" * 64, limits, create=True)
        code = """import json,sys
from agent_lab.request_budget import RequestBudget,RequestBudgetExhausted
b=RequestBudget(sys.argv[1],'a'*64,json.loads(sys.argv[2]),sys.argv[3])
try:b.reserve(b'{}','/v1/chat/completions')
except RequestBudgetExhausted:raise SystemExit(3)
"""
        jobs = [
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    code,
                    str(self.f.root),
                    json.dumps(limits),
                    budget.journal_id,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for _ in range(6)
        ]
        try:
            codes = []
            for job in jobs:
                _, errors = job.communicate(timeout=30)
                self.assertIn(job.returncode, (0, 3), errors)
                codes.append(job.returncode)
        finally:
            for job in jobs:
                if job.poll() is None:
                    job.kill()
                    job.communicate(timeout=10)
        self.assertEqual(codes.count(0), 3)
        self.assertEqual(codes.count(3), 3)
        self.assertEqual(budget.summary()["reserved_requests"], 3)
        self.assertEqual(budget.summary()["reserved_request_body_bytes"], 6)


if __name__ == "__main__":
    unittest.main()
