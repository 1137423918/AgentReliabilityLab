"""Real process-boundary cleanup checks; run on the authorized Linux server."""

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest

from agent_lab.verification import run_command


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux subreaper contract")
class VerificationTreeTests(unittest.TestCase):
    def run_verifier(self, root, code, timeout):
        with (root / "lock").open("a") as lock, (root / "log").open("wb") as log:
            return run_command(
                [sys.executable, "-c", code, str(root)],
                cwd=root,
                environment=os.environ.copy(),
                stream=log,
                timeout=timeout,
                lock_fd=lock.fileno(),
            )

    def test_double_fork_reaped_after_successful_leader_exit(self):
        code = """
import os, time
from pathlib import Path
first = os.fork()
if first == 0:
    os.setsid()
    if os.fork() == 0:
        Path('grandchild.pid').write_text(str(os.getpid()))
        time.sleep(30)
    os._exit(0)
os.waitpid(first, 0)
while not Path('grandchild.pid').exists():
    time.sleep(0.01)
"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pid = None
            cleaned = False
            try:
                self.assertEqual(self.run_verifier(root, code, 5), (0, False))
                pid = int((root / "grandchild.pid").read_text())
                self.assertFalse(Path(f"/proc/{pid}").exists(), "Child not reaped")
                cleaned = True
            finally:
                marker = root / "grandchild.pid"
                if not cleaned and marker.exists():
                    pid = int(marker.read_text())
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_timeout_cleans_detached_child_and_preserves_unrelated_process(self):
        code = """
import subprocess, sys, time
from pathlib import Path
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                         start_new_session=True)
Path('child.pid').write_text(str(child.pid))
time.sleep(30)
"""
        sentinel = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True,
        )
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                cleaned = False
                try:
                    self.assertEqual(self.run_verifier(root, code, 3), (-9, True))
                    pid = int((root / "child.pid").read_text())
                    self.assertFalse(Path(f"/proc/{pid}").exists(), "Child not reaped")
                    cleaned = True
                    self.assertIsNone(sentinel.poll(), "Unrelated process was killed")
                finally:
                    marker = root / "child.pid"
                    if not cleaned and marker.exists():
                        try:
                            os.kill(int(marker.read_text()), signal.SIGKILL)
                        except ProcessLookupError:
                            pass
        finally:
            sentinel.kill()
            sentinel.wait(timeout=5)
