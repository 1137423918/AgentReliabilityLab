"""Real Git/worktree and process checks for baseline grading and export policy."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from agent_lab.repair import failed_candidate
from agent_lab.worker import (
    RunError,
    baseline_files,
    create_file_data,
    materialize,
    verification_workspace,
)

ROOT = Path(__file__).resolve().parents[1]


class ProtectedVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Verification fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.original_test = (
            "import unittest\nfrom pathlib import Path\nimport logic\n\n"
            "class LogicTests(unittest.TestCase):\n"
            "    def test_stable(self):\n"
            "        self.assertEqual(Path(logic.__file__).resolve(), (Path.cwd() / 'logic.py').resolve())\n"
            "        self.assertEqual(logic.stable(), 1)\n"
        )
        for name, text in {
            "logic.py": "def stable():\n    return 1\n",
            "helper.py": "flag = 0\n",
            "test_logic.py": self.original_test,
        }.items():
            (self.repo / name).write_text(text)
        self.git("add", ".")
        self.git("commit", "-m", "baseline")
        self.task = {
            "base_commit": self.git("rev-parse", "HEAD"),
            "files": ["helper.py", "logic.py", "test_logic.py"],
            "prompt": "Add a reviewed marker and regression coverage; preserve stable behavior.",
            "max_graph_steps": 100,
            "required_features": ["python_syntax_v1", "baseline_verification_v1"],
            "python_syntax_files": ["helper.py", "logic.py", "test_logic.py"],
            "model": {"mode": "scripted", "plan": []},
            "verify": [self.command(), self.command(frozen=True)],
        }

    def git(self, *args):
        return (
            subprocess.check_output(
                ["git", "-C", str(self.repo), *args], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )

    def command(self, frozen=False):
        code = (
            "import os,sys,unittest; from pathlib import Path; "
            + (
                "assert os.environ.get('AGENT_LAB_BASELINE_VIEW') == '1'; "
                if frozen
                else ""
            )
            + "p=Path('.verify-count'); p.write_text(str(int(p.read_text())+1) if p.exists() else '1'); "
            "r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName('test_logic')); "
            "sys.exit(not r.wasSuccessful())"
        )
        value = {"argv": [sys.executable, "-c", code], "timeout_seconds": 20}
        if frozen:
            value["baseline_files"] = ["test_logic.py"]
        return value

    def edit(self, file, old, new):
        return {
            "tool": "edit_file",
            "args": {"file_path": "/" + file, "old_string": old, "new_string": new},
        }

    def good_plan(self):
        return [
            self.edit("logic.py", "return 1", "return 1  # reviewed"),
            self.edit(
                "test_logic.py",
                self.original_test,
                self.original_test
                + "\n    def test_added(self):\n        self.assertIsInstance(logic.stable(), int)\n",
            ),
        ]

    def call(self, task, name):
        path = self.root / (name + ".json")
        path.write_text(json.dumps(task))
        directory = self.root / name
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_lab.worker",
                "--repo",
                str(self.repo),
                "--task",
                str(path),
                "--run-dir",
                str(directory),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return process, directory

    def test_weakened_candidate_tests_cannot_replace_original_regression(self):
        task = copy.deepcopy(self.task)
        task["model"]["plan"] = [
            self.edit("logic.py", "return 1", "return 2"),
            self.edit(
                "test_logic.py",
                "self.assertEqual(logic.stable(), 1)",
                "self.assertEqual(logic.stable(), 2)",
            ),
        ]
        control = copy.deepcopy(task)
        control["verify"] = [self.command()]
        before, _ = self.call(control, "mutable-control")
        self.assertEqual(before.returncode, 0, before.stderr)
        guarded, directory = self.call(task, "guarded")
        self.assertEqual(guarded.returncode, 2, guarded.stderr)
        self.assertFalse((directory / "result.json").exists())
        self.assertIn("2 != 1", (directory / "verification-1.log").read_text())
        self.assertIn("stable(), 2", (directory / "worktree/test_logic.py").read_text())
        record = json.loads((directory / "verification.json").read_text())["commands"][
            1
        ]
        frozen_test = directory / record["verification_view"] / "test_logic.py"
        self.assertEqual(frozen_test.read_text(), self.original_test)
        self.assertIsNotNone(failed_candidate(self.repo, directory, task))
        frozen_test.write_text(
            self.original_test + "\n# outside change after failure\n"
        )
        with self.assertRaisesRegex(RunError, "verification content changed"):
            failed_candidate(self.repo, directory, task)

    def test_legitimate_test_addition_and_cached_replay_keep_both_suites(self):
        task = copy.deepcopy(self.task)
        task["model"]["plan"] = self.good_plan()
        first, directory = self.call(task, "valid")
        self.assertEqual(first.returncode, 0, first.stderr)
        result = json.loads((directory / "result.json").read_text())
        view = directory / result["verification"][1]["verification_view"]
        self.assertIn("Ran 2 tests", (directory / "verification-0.log").read_text())
        self.assertIn("Ran 1 test", (directory / "verification-1.log").read_text())
        self.assertEqual((view / "test_logic.py").read_text(), self.original_test)
        second, _ = self.call(task, "valid")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual((view / ".verify-count").read_text(), "1")
        self.assertEqual((directory / "worktree/.verify-count").read_text(), "1")

    def test_changed_frozen_view_rejects_stale_success_without_rerunning(self):
        task = copy.deepcopy(self.task)
        task["model"]["plan"] = self.good_plan()
        first, directory = self.call(task, "tampered")
        self.assertEqual(first.returncode, 0, first.stderr)
        result = json.loads((directory / "result.json").read_text())
        view = directory / result["verification"][1]["verification_view"]
        (view / "test_logic.py").write_text(self.original_test + "\n# outside edit\n")
        second, _ = self.call(task, "tampered")
        self.assertEqual(second.returncode, 2)
        self.assertIn("verification content changed", second.stderr)
        self.assertEqual((view / ".verify-count").read_text(), "1")

    def test_recorded_invalid_model_write_is_rejected_before_any_export(self):
        directory = self.root / "syntax"
        directory.mkdir()
        files = baseline_files(self.repo, self.task["base_commit"], self.task["files"])
        files["/helper.py"] = create_file_data("flag = 1\n")
        sample = (
            ROOT
            / "evidence/native-cpu/audit/normal/libs/deepagents/deepagents/backends/utils.py.txt"
        )
        self.assertEqual(sample.stat().st_size, 900)
        files["/logic.py"] = create_file_data(sample.read_text())
        with self.assertRaisesRegex(RunError, "syntax rejected before export"):
            materialize(
                self.repo, directory, self.task, self.task["files"], {"files": files}
            )
        self.assertFalse((directory / "worktree").exists())
        self.assertEqual((self.repo / "helper.py").read_text(), "flag = 0\n")

    def test_partial_verification_view_setup_recovers_known_file_states(self):
        directory = self.root / "partial"
        directory.mkdir()
        files = baseline_files(self.repo, self.task["base_commit"], self.task["files"])
        files["/helper.py"] = create_file_data("flag = 1\n")
        files["/logic.py"] = create_file_data(
            "def stable():\n    return 1  # reviewed\n"
        )
        materialize(
            self.repo, directory, self.task, self.task["files"], {"files": files}
        )
        real_replace = Path.replace
        count = 0

        def interrupted(source, target):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("Injected setup interruption")
            return real_replace(source, target)

        with patch.object(Path, "replace", interrupted):
            with self.assertRaisesRegex(OSError, "setup interruption"):
                verification_workspace(
                    directory, self.task, 1, self.task["verify"][1], restore=True
                )
        view, fingerprint = verification_workspace(
            directory, self.task, 1, self.task["verify"][1], restore=True
        )
        self.assertEqual((view / "helper.py").read_text(), "flag = 1\n")
        self.assertIn("# reviewed", (view / "logic.py").read_text())
        self.assertEqual(
            verification_workspace(
                directory, self.task, 1, self.task["verify"][1], restore=False
            )[1],
            fingerprint,
        )

    def test_verifier_tracked_write_is_rejected_even_with_zero_exit(self):
        task = copy.deepcopy(self.task)
        task["model"]["plan"] = self.good_plan()
        task["verify"] = [
            {
                "argv": [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; p=Path('.count'); p.write_text(str(int(p.read_text())+1) if p.exists() else '1'); Path('logic.py').write_text('tampered = True\\n')",
                ],
                "baseline_files": ["test_logic.py"],
                "timeout_seconds": 20,
            }
        ]
        first, directory = self.call(task, "mutating-verifier")
        self.assertEqual(first.returncode, 2)
        record = json.loads((directory / "verification.json").read_text())["commands"][
            0
        ]
        self.assertEqual(record["returncode"], 0)
        self.assertTrue(record["view_integrity_error"])
        second, _ = self.call(task, "mutating-verifier")
        self.assertEqual(second.returncode, 2)
        view = directory / record["verification_view"]
        self.assertEqual((view / ".count").read_text(), "1")


if __name__ == "__main__":
    unittest.main()
