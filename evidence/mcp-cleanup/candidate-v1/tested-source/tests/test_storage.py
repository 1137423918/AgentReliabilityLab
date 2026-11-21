"""Filesystem admission and no-write rejection; execute on supported servers."""

import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from agent_lab import repair, storage, worker


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="agentlab-storage-")
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def task(self):
        return {
            "base_commit": "0" * 40,
            "files": ["module.py"],
            "prompt": "review",
            "verify": [
                {"argv": ["python", "-c", 'raise AssertionError("never execute")']}
            ],
        }

    def test_native_adapters_use_argument_arrays_and_identify_local_types(self):
        path = self.root / "中文 with spaces"
        with (
            patch("agent_lab.storage.sys.platform", "linux"),
            patch(
                "agent_lab.storage.subprocess.run",
                return_value=SimpleNamespace(stdout="ext4\n"),
            ) as run,
        ):
            self.assertEqual(storage.filesystem_type(path), "ext4")
        args, kwargs = run.call_args
        self.assertEqual(args[0][-2:], ["--target", str(path)])
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["timeout"], 10)
        with (
            patch("agent_lab.storage.sys.platform", "darwin"),
            patch(
                "agent_lab.storage.subprocess.run",
                side_effect=[
                    SimpleNamespace(
                        stdout="Filesystem 512-blocks Used Available Capacity Mounted on\n/dev/disk3s5 1 1 1 1% /System/Volumes/Data\n"
                    ),
                    SimpleNamespace(stdout=plistlib.dumps({"FilesystemType": "apfs"})),
                ],
            ) as run,
        ):
            self.assertEqual(storage.filesystem_type(path), "apfs")
        self.assertEqual(
            run.call_args_list[-1].args[0],
            ["/usr/sbin/diskutil", "info", "-plist", "/dev/disk3s5"],
        )

    def test_native_metadata_failure_is_closed_without_fallback(self):
        for response in ["ext4\nnfs4\n", "", "ext4 unexpected"]:
            with (
                self.subTest(response=response),
                patch("agent_lab.storage.sys.platform", "linux"),
                patch(
                    "agent_lab.storage.subprocess.run",
                    return_value=SimpleNamespace(stdout=response),
                ),
            ):
                with self.assertRaises(storage.StorageError):
                    storage.filesystem_type(self.root)
        for error in [
            FileNotFoundError(),
            subprocess.TimeoutExpired(["findmnt"], 10),
            subprocess.CalledProcessError(1, ["findmnt"]),
        ]:
            with (
                self.subTest(error=type(error).__name__),
                patch("agent_lab.storage.sys.platform", "linux"),
                patch("agent_lab.storage.subprocess.run", side_effect=error),
            ):
                with self.assertRaises(storage.StorageError):
                    storage.filesystem_type(self.root)
        with (
            patch("agent_lab.storage.sys.platform", "darwin"),
            patch(
                "agent_lab.storage.subprocess.run",
                return_value=SimpleNamespace(
                    stdout="header\nserver:/remote 1 1 1 1% /remote\n"
                ),
            ) as run,
        ):
            with self.assertRaises(storage.StorageError):
                storage.filesystem_type(self.root)
            self.assertEqual(run.call_count, 1)
        with (
            patch("agent_lab.storage.sys.platform", "unknown"),
            patch(
                "agent_lab.storage.subprocess.run",
                side_effect=AssertionError("No fallback"),
            ),
        ):
            with self.assertRaises(storage.StorageError):
                storage.filesystem_type(self.root)

    def test_new_unsupported_run_is_rejected_before_directory_or_task_execution(self):
        for kind in [
            "nfs",
            "nfs4",
            "cifs",
            "fuse.sshfs",
            "ceph",
            "overlay",
            "unrecognized",
        ]:
            directory = self.root / kind / "new-run"
            with (
                self.subTest(kind=kind),
                patch("agent_lab.storage.filesystem_type", return_value=kind),
                patch(
                    "agent_lab.worker.validate_task",
                    side_effect=AssertionError("No task execution"),
                ),
            ):
                with self.assertRaises(storage.StorageError):
                    worker.run(self.root, directory, {})
                self.assertFalse(directory.parent.exists())

    def test_existing_unsupported_run_is_unchanged_including_cached_result(self):
        directory = self.root / "old-run"
        directory.mkdir()
        for name in [
            "checkpoints.sqlite",
            "worker.lock",
            "manifest.json",
            "model-requests.json",
            "result.json",
        ]:
            (directory / name).write_bytes(b"old-progress")
        before = {
            p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()
        }
        with patch("agent_lab.storage.filesystem_type", return_value="nfs4"):
            with self.assertRaises(storage.StorageError):
                worker.run(self.root, directory, {})
        after = {
            p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in directory.iterdir()
        }
        self.assertEqual(before, after)

    def test_admitted_local_lock_and_fresh_resume_probe(self):
        directory = self.root / "local" / "run"
        with patch("agent_lab.storage.filesystem_type", return_value="ext4"):
            with worker.run_lock(directory) as fd:
                self.assertTrue(directory.is_dir())
                self.assertEqual(
                    os.fstat(fd).st_ino, (directory / "worker.lock").stat().st_ino
                )
        before = (directory / "worker.lock").stat().st_mtime_ns
        with patch("agent_lab.storage.filesystem_type", return_value="nfs4"):
            with self.assertRaises(storage.StorageError):
                with worker.run_lock(directory):
                    self.fail("Resume must reprobe storage")
        self.assertEqual(before, (directory / "worker.lock").stat().st_mtime_ns)

    def test_control_links_special_files_and_separate_mount_are_rejected(self):
        target = self.root / "target"
        target.write_bytes(b"preserve")
        for i, name in enumerate(storage.STATE_FILES):
            directory = self.root / str(i)
            directory.mkdir()
            (directory / name).symlink_to(target if i % 2 else self.root / "absent")
            with (
                self.subTest(name=name),
                patch("agent_lab.storage.filesystem_type", return_value="ext4"),
            ):
                with self.assertRaises(storage.StorageError):
                    with worker.run_lock(directory):
                        self.fail("Control links must not be opened")
        self.assertEqual(target.read_bytes(), b"preserve")
        directory = self.root / "fifo"
        directory.mkdir()
        os.mkfifo(directory / "checkpoints.sqlite")
        with patch("agent_lab.storage.filesystem_type", return_value="ext4"):
            with self.assertRaises(storage.StorageError):
                storage.admit_state_directory(directory)
        directory = self.root / "separate-mount"
        directory.mkdir()
        (directory / "checkpoints.sqlite").write_bytes(b"old")
        with patch(
            "agent_lab.storage.filesystem_type",
            side_effect=lambda p: "nfs4" if p.name == "checkpoints.sqlite" else "ext4",
        ):
            with self.assertRaises(storage.StorageError):
                with worker.run_lock(directory):
                    self.fail("Component filesystem must be checked")
        self.assertFalse((directory / "worker.lock").exists())

    def test_directory_alias_resolves_target_and_dangling_alias_does_not_create_it(
        self,
    ):
        target = self.root / "target-directory"
        target.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(target, target_is_directory=True)
        with patch("agent_lab.storage.filesystem_type", return_value="ext4") as probe:
            with worker.run_lock(alias):
                pass
        self.assertTrue(
            all(call.args[0].is_relative_to(target) for call in probe.call_args_list)
        )
        with patch("agent_lab.storage.filesystem_type", return_value="nfs4"):
            with self.assertRaises(storage.StorageError):
                storage.admit_state_directory(alias)
        alias = self.root / "dangling"
        alias.symlink_to(self.root / "missing-target", target_is_directory=True)
        with self.assertRaises(storage.StorageError):
            storage.admit_state_directory(alias)
        self.assertFalse((self.root / "missing-target").exists())

    def test_admission_is_rechecked_while_holding_the_lock_before_body(self):
        directory = self.root / "changing"
        with patch(
            "agent_lab.storage.filesystem_type", side_effect=["ext4", "ext4", "nfs4"]
        ):
            with self.assertRaises(storage.StorageError):
                with worker.run_lock(directory):
                    self.fail("Storage changed before guarded work")
        self.assertEqual([p.name for p in directory.iterdir()], ["worker.lock"])

    def test_repair_parent_and_nested_attempt_use_same_admission(self):
        directory = self.root / "repair-blocked"
        with patch("agent_lab.storage.filesystem_type", return_value="nfs4"):
            with self.assertRaises(storage.StorageError):
                repair.execute(self.root, directory, self.task())
        self.assertFalse(directory.exists())
        directory = self.root / "repair-local"
        directory.mkdir()
        foreign = self.root / "foreign"
        foreign.mkdir()
        (directory / "attempts").symlink_to(foreign, target_is_directory=True)

        def kind(path):
            return "nfs4" if path.is_relative_to(foreign) else "ext4"

        with (
            patch("agent_lab.storage.filesystem_type", side_effect=kind),
            patch("agent_lab.repair.prepare_manifest", return_value={}),
            patch("agent_lab.repair.open_request_budget", return_value=None),
        ):
            with self.assertRaises(storage.StorageError):
                repair.execute(self.root, directory, self.task())
        self.assertEqual(list(foreign.iterdir()), [])

    def test_native_probe_and_lock_on_real_temporary_storage(self):
        kind = storage.admit_state_directory(self.root / "new-run")
        self.assertIn(kind, storage.LOCAL_TYPES)
        with worker.run_lock(self.root / "new-run"):
            self.assertEqual(storage.filesystem_type(self.root / "new-run"), kind)


if __name__ == "__main__":
    unittest.main()
