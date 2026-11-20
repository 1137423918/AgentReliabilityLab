"""Exercise native-service ownership and rejection without loading a model."""

from contextlib import ExitStack
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "llama_launcher_under_test",
    Path(__file__).resolve().parents[1] / "benchmarks/serve_llama_cpu.py",
)
LAUNCHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LAUNCHER)


@unittest.skipUnless(
    sys.platform == "linux", "Linux process/resource integration checks"
)
class LlamaServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.binary = self.root / "fixture-server"
        self.binary.write_text(
            "#!"
            + sys.executable
            + "\nimport time\nprint('fixture only, no weights', flush=True)\ntime.sleep(60)\n"
        )
        self.binary.chmod(0o700)
        self.model = self.root / "fixture.gguf"
        self.model.write_bytes(b"explicit non-model process fixture")
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "server_sha256": LAUNCHER.digest(self.binary),
                    "model_sha256": LAUNCHER.digest(self.model),
                    "runtime_libraries": {},
                }
            )
        )
        self.output = self.root / "run"
        self.argv = [
            "serve_llama_cpu.py",
            "--server",
            str(self.binary),
            "--model",
            str(self.model),
            "--manifest",
            str(self.manifest),
            "--library-dir",
            str(self.root),
            "--output",
            str(self.output),
            "--wall-seconds",
            "1",
        ]
        self.processes = []

    def run_launcher(self, fail_record=False):
        original_read, original_write, original_popen = (
            Path.read_text,
            Path.write_text,
            subprocess.Popen,
        )

        def read(path, *args, **kwargs):
            if str(path) == "/proc/meminfo":
                return "MemAvailable: 100000000 kB\n"
            return original_read(path, *args, **kwargs)

        def write(path, *args, **kwargs):
            if fail_record and path.name == "service.json":
                raise OSError("Injected provenance write failure")
            return original_write(path, *args, **kwargs)

        def spawn(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            self.processes.append(process)
            self.addCleanup(lambda: process.kill() if process.poll() is None else None)
            return process

        with ExitStack() as stack:
            stack.enter_context(patch.object(sys, "argv", self.argv))
            stack.enter_context(patch.object(Path, "read_text", read))
            stack.enter_context(patch.object(Path, "write_text", write))
            stack.enter_context(
                patch.object(LAUNCHER.os, "getloadavg", return_value=(0, 0, 0))
            )
            stack.enter_context(
                patch.object(
                    LAUNCHER.os, "sched_getaffinity", return_value=set(range(16))
                )
            )
            stack.enter_context(patch.object(LAUNCHER.os, "nice"))
            stack.enter_context(patch.object(LAUNCHER.resource, "setrlimit"))
            stack.enter_context(patch.object(LAUNCHER.signal, "signal"))
            stack.enter_context(patch.object(LAUNCHER.subprocess, "Popen", spawn))
            return LAUNCHER.main()

    def test_wall_guard_terminates_owned_service_process(self):
        self.assertLess(self.run_launcher(), 0)
        self.assertEqual(len(self.processes), 1)
        self.assertIsNotNone(self.processes[0].poll())
        self.assertFalse(Path(f"/proc/{self.processes[0].pid}").exists())
        result = json.loads((self.output / "shutdown.json").read_text())
        self.assertEqual(result["guard_reason"], "service_wall_limit")
        self.assertFalse(result["forced_cleanup"])

    def test_altered_model_rejected_before_child_starts(self):
        self.model.write_bytes(b"changed fixture")
        with self.assertRaisesRegex(ValueError, "hash"):
            self.run_launcher()
        self.assertEqual(self.processes, [])

    def test_provenance_write_failure_cannot_orphan_started_service(self):
        with self.assertRaisesRegex(OSError, "provenance"):
            self.run_launcher(fail_record=True)
        self.assertEqual(len(self.processes), 1)
        self.assertIsNotNone(self.processes[0].poll())
        self.assertFalse(Path(f"/proc/{self.processes[0].pid}").exists())
        self.assertTrue((self.output / "shutdown.json").exists())


if __name__ == "__main__":
    unittest.main()
