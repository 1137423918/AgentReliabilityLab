"""Process-level recovery tests. Run on the authorized Linux compute server."""

import json
import fcntl
import os
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


def commit(repo, *args):
    return (
        subprocess.check_output(
            ["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL
        )
        .decode()
        .strip()
    )


def invoke(repo, task_path, run_dir, hold=None):
    argv = [
        sys.executable,
        "-m",
        "agent_lab.worker",
        "--repo",
        str(repo),
        "--task",
        str(task_path),
        "--run-dir",
        str(run_dir),
    ]
    if hold:
        argv += ["--hold-after", hold]
    return argv


def wait_stage(process, wanted, seconds=120):
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + seconds
    buffered = b""
    try:
        while time.monotonic() < deadline:
            if selector.select(timeout=1):
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                buffered += chunk
                while b"\n" in buffered:
                    line, buffered = buffered.split(b"\n", 1)
                    event = json.loads(line)
                    if event.get("stage") == wanted:
                        return event
        raise AssertionError(
            f"Worker did not reach {wanted}; returncode={process.poll()}"
        )
    finally:
        selector.close()


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        commit(self.repo, "init", "-b", "main")
        commit(self.repo, "config", "user.email", "worker-test@example.invalid")
        commit(self.repo, "config", "user.name", "Worker test")
        (self.repo / "module.py").write_text("value = 1\n")
        commit(self.repo, "add", "module.py")
        commit(self.repo, "commit", "-m", "baseline")
        self.task = {
            "base_commit": commit(self.repo, "rev-parse", "HEAD"),
            "files": ["module.py"],
            "prompt": "Set value to 2 and add a reviewed marker.",
            "max_graph_steps": 100,
            "model": {
                "mode": "scripted",
                "plan": [
                    {
                        "tool": "edit_file",
                        "args": {
                            "file_path": "/module.py",
                            "old_string": "value = 1",
                            "new_string": "value = 2",
                        },
                    },
                    {
                        "tool": "edit_file",
                        "args": {
                            "file_path": "/module.py",
                            "old_string": "value = 2",
                            "new_string": "value = 2  # reviewed",
                        },
                    },
                ],
            },
            "verify": [
                {
                    "argv": [
                        sys.executable,
                        "-c",
                        "from pathlib import Path; p=Path('.verify-count'); p.write_text(str(int(p.read_text())+1) if p.exists() else '1'); import module; assert module.value == 2",
                    ],
                    "timeout_seconds": 15,
                }
            ],
        }
        self.task_path = self.root / "task.json"
        self.save_task()

    def tearDown(self):
        self.temporary.cleanup()

    def save_task(self):
        self.task_path.write_text(json.dumps(self.task))

    def call(self, run_dir):
        return subprocess.run(
            invoke(self.repo, self.task_path, run_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )

    def paused(self, run_dir, stage):
        process = subprocess.Popen(
            invoke(self.repo, self.task_path, run_dir, stage),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            event = wait_stage(process, stage)
        except BaseException:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise
        return process, event

    def kill(self, process):
        os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=10)
        self.assertEqual(process.returncode, -signal.SIGKILL)

    def assert_ready(self, directory):
        result = json.loads((directory / "result.json").read_text())
        self.assertEqual(result["status"], "ready_for_review")
        self.assertEqual(result["tool_results"], 2)
        self.assertEqual(
            (directory / "worktree/module.py").read_text(), "value = 2  # reviewed\n"
        )
        self.assertEqual((self.repo / "module.py").read_text(), "value = 1\n")
        return result

    def test_recovers_after_actual_sigkill_at_durable_stages(self):
        reference = self.root / "reference"
        result = self.call(reference)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = self.assert_ready(reference)
        for stage in ("checkpoint", "materialized", "before_verification"):
            with self.subTest(stage=stage):
                directory = self.root / stage
                process, event = self.paused(directory, stage)
                self.kill(process)
                resumed = self.call(directory)
                self.assertEqual(resumed.returncode, 0, resumed.stderr)
                actual = self.assert_ready(directory)
                self.assertEqual(actual["patch_sha256"], expected["patch_sha256"])
                if stage == "checkpoint":
                    self.assertEqual(event["tool_results"], 1)

    def test_terminal_replay_does_not_repeat_verification(self):
        directory = self.root / "replay"
        first = self.call(directory)
        second = self.call(directory)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((directory / "worktree/.verify-count").read_text(), "1")

    def test_changed_manifest_is_rejected_on_resume(self):
        directory = self.root / "changed"
        self.assertEqual(self.call(directory).returncode, 0)
        self.task["prompt"] += " Different task."
        self.save_task()
        result = self.call(directory)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Resume rejected", result.stderr)

    def test_concurrent_worker_cannot_take_over_live_run(self):
        directory = self.root / "locked"
        process, _ = self.paused(directory, "checkpoint")
        try:
            contender = self.call(directory)
            self.assertEqual(contender.returncode, 2)
            self.assertIn("Another worker owns", contender.stderr)
        finally:
            self.kill(process)
        self.assertEqual(self.call(directory).returncode, 0)
        self.assert_ready(directory)

    def test_export_rejects_files_outside_manifest(self):
        self.task["model"]["plan"] = [
            {
                "tool": "write_file",
                "args": {"file_path": "/unexpected.py", "content": "value = 2"},
            }
        ]
        self.save_task()
        directory = self.root / "scope"
        result = self.call(directory)
        self.assertEqual(result.returncode, 2)
        self.assertIn("allowed file set", result.stderr)
        self.assertFalse((directory / "worktree").exists())

    def test_user_changes_in_worktree_survive_failed_resume(self):
        directory = self.root / "manual"
        process, _ = self.paused(directory, "materialized")
        self.kill(process)
        path = directory / "worktree/module.py"
        path.write_text("manual review edit\n")
        resumed = self.call(directory)
        self.assertEqual(resumed.returncode, 2)
        self.assertEqual(path.read_text(), "manual review edit\n")

    def test_failed_verification_never_produces_review_ready_result(self):
        self.task["verify"] = [{"argv": [sys.executable, "-c", "raise SystemExit(3)"]}]
        self.save_task()
        directory = self.root / "failed"
        result = self.call(directory)
        self.assertEqual(result.returncode, 2)
        self.assertFalse((directory / "result.json").exists())
        self.assertEqual(
            json.loads((directory / "status.json").read_text())["status"], "failed"
        )

    def test_verification_timeout_stops_its_process_group(self):
        code = "import subprocess,sys,time; from pathlib import Path; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True); Path('child.pid').write_text(str(p.pid)); time.sleep(60)"
        self.task["verify"] = [
            {"argv": [sys.executable, "-c", code], "timeout_seconds": 5}
        ]
        self.save_task()
        directory = self.root / "timeout"
        result = self.call(directory)
        self.assertEqual(result.returncode, 2)
        records = json.loads((directory / "verification.json").read_text())
        self.assertTrue(records["commands"][0]["timed_out"])
        pid = int((directory / "worktree/child.pid").read_text())
        status = Path(f"/proc/{pid}/stat")
        if status.exists():
            self.assertEqual(status.read_text().rsplit(")", 1)[1].split()[0], "Z")

    def test_parent_sigkill_stops_verification_before_resume(self):
        code = """
import json, os, subprocess, sys, time
from pathlib import Path
attempt = Path('.verify-attempt')
if not attempt.exists():
    attempt.write_text('1')
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
    marker = Path('verification-pids.tmp')
    marker.write_text(json.dumps([os.getpid(), child.pid]))
    marker.replace('verification-pids.json')
    time.sleep(60)
else:
    attempt.write_text(str(int(attempt.read_text()) + 1))
    import module
    assert module.value == 2
"""
        self.task["verify"] = [
            {"argv": [sys.executable, "-c", code], "timeout_seconds": 90}
        ]
        self.save_task()
        directory = self.root / "parent-kill"
        process = subprocess.Popen(
            invoke(self.repo, self.task_path, directory),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        pids = []

        def alive(pid):
            status = Path(f"/proc/{pid}/stat")
            return (
                status.exists()
                and status.read_text().rsplit(")", 1)[1].split()[0] != "Z"
            )

        try:
            wait_stage(process, "before_verification")
            marker = directory / "worktree/verification-pids.json"
            deadline = time.monotonic() + 15
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(marker.exists(), "Verification did not start")
            pids = json.loads(marker.read_text())
            self.assertTrue(all(alive(pid) for pid in pids))
            os.kill(process.pid, signal.SIGKILL)
            process.communicate(timeout=10)
            self.assertEqual(process.returncode, -signal.SIGKILL)
            # A new owner must not enter until the old verifier has stopped.
            with (directory / "worker.lock").open("a") as lock:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        self.assertFalse(any(alive(pid) for pid in pids))
                        break
                    except BlockingIOError:
                        self.assertLess(
                            time.monotonic(), deadline, "Cleanup kept the run locked"
                        )
                        time.sleep(0.02)
            self.assertFalse((directory / "result.json").exists())
            self.assertEqual(self.call(directory).returncode, 0)
            result = self.assert_ready(directory)
            self.assertEqual(result["verification"][0]["returncode"], 0)
            self.assertEqual((directory / "worktree/.verify-attempt").read_text(), "2")
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.communicate(timeout=10)
            if pids and alive(pids[0]):
                os.killpg(pids[0], signal.SIGKILL)

    def test_completed_verifier_does_not_leave_background_children(self):
        code = "import subprocess,sys; from pathlib import Path; child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],start_new_session=True); Path('child.pid').write_text(str(child.pid))"
        self.task["verify"] = [{"argv": [sys.executable, "-c", code]}]
        self.save_task()
        directory = self.root / "background"
        result = self.call(directory)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_ready(directory)
        pid = int((directory / "worktree/child.pid").read_text())
        status = Path(f"/proc/{pid}/stat")
        try:
            if status.exists():
                self.assertEqual(status.read_text().rsplit(")", 1)[1].split()[0], "Z")
        finally:
            if (
                status.exists()
                and status.read_text().rsplit(")", 1)[1].split()[0] != "Z"
            ):
                os.kill(pid, signal.SIGKILL)

    def test_missing_verifier_is_recorded_as_failed(self):
        self.task["verify"] = [{"argv": ["/nonexistent/agentlab-verifier"]}]
        self.save_task()
        directory = self.root / "missing-command"
        result = self.call(directory)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse((directory / "result.json").exists())
        self.assertEqual(
            json.loads((directory / "status.json").read_text())["status"], "failed"
        )
        self.assertIn("supervisor failed", result.stderr)

    def test_graph_budget_is_not_reset_by_resume(self):
        self.task["max_graph_steps"] = 1
        self.save_task()
        directory = self.root / "budget"
        for _ in range(2):
            result = self.call(directory)
            self.assertEqual(result.returncode, 2)
            self.assertIn("graph-step budget", result.stderr)
        self.assertFalse((directory / "result.json").exists())

    def test_initial_contents_cannot_expand_scope_or_exceed_the_text_budget(self):
        from agent_lab.worker import RunError, validate_task

        for initial in (
            {"outside.py": "x"},
            {"module.py": 2},
            {"module.py": "x" * (2 * 1024 * 1024 + 1)},
        ):
            with self.subTest(initial_type=type(initial[next(iter(initial))]).__name__):
                with self.assertRaises(RunError):
                    validate_task({**self.task, "initial_contents": initial})

    def test_modified_completed_patch_is_not_reported_as_success(self):
        directory = self.root / "tampered"
        self.assertEqual(self.call(directory).returncode, 0)
        (directory / "patch.diff").write_text("changed patch")
        result = self.call(directory)
        self.assertEqual(result.returncode, 2)
        self.assertIn("stale success", result.stderr)

    def test_cached_verification_logs_cannot_be_replaced(self):
        directory = self.root / "changed-log"
        self.assertEqual(self.call(directory).returncode, 0)
        (directory / "verification-0.log").write_text("modified evidence")
        self.assertEqual(self.call(directory).returncode, 2)
        (directory / "result.json").unlink()
        result = self.call(directory)
        self.assertEqual(result.returncode, 2)
        self.assertIn("Saved verification evidence changed", result.stderr)
        self.assertEqual((directory / "worktree/.verify-count").read_text(), "1")


if __name__ == "__main__":
    unittest.main()
