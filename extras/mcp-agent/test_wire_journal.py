"""Stdlib CPU controls for private wire prefix recovery; no model requests."""

import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent_lab.wire_journal import (  # noqa: E402 - standalone optional-runtime control
    DurableWireEvents,
    WireJournalError,
    read_wire_journal,
)

OWNER, JOURNAL = "a" * 64, "b" * 32


def event(body=b'{"audit_id":"private-control-capability"}'):
    return {
        "channel": "model",
        "kind": "client_request_attempt",
        "path": "/v1/chat/completions",
        "method": "POST",
        "protocol_version": None,
        "body_base64": base64.b64encode(body).decode(),
        "body_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
    }


class WireControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agentlab-wire-control-")
        self.root = Path(self.temp.name)
        self.path = self.root / "wire-events.jsonl"
        self.writers = []

    def tearDown(self):
        for writer in self.writers:
            writer.close()
        self.temp.cleanup()

    def writer(self, path=None, **kwargs):
        writer = DurableWireEvents(path or self.path, OWNER, JOURNAL, **kwargs)
        self.writers.append(writer)
        return writer

    def test_private_file_deep_copy_roundtrip_and_no_reopen(self):
        writer = self.writer()
        item = event()
        writer.append(item)
        item["path"] = "/changed-after-commit"
        writer.close()
        writer.close()
        before = self.path.read_bytes()
        recovered = read_wire_journal(self.path, OWNER, JOURNAL)
        self.assertEqual(recovered["events"], [event()])
        self.assertEqual(writer.events, [event()])
        self.assertEqual(recovered["tail_bytes"], 0)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            self.writer()
        with self.assertRaises(WireJournalError):
            writer.append(event())
        self.assertEqual(self.path.read_bytes(), before)

    def test_partial_write_keeps_prefix_and_never_repairs_or_reuses_file(self):
        writer = self.writer()
        writer.append(event(b"first"))
        original = __import__("os").write
        count = 0

        def broken(fd, data):
            nonlocal count
            if fd != writer._fd:
                return original(fd, data)
            count += 1
            if count == 1:
                return original(fd, data[:13])
            raise OSError("Injected partial-write failure")

        with (
            patch("agent_lab.wire_journal.os.write", side_effect=broken),
            self.assertRaises(OSError),
        ):
            writer.append(event(b"second"))
        writer.close()
        before = self.path.read_bytes()
        recovered = read_wire_journal(self.path, OWNER, JOURNAL)
        self.assertEqual(recovered["events"], [event(b"first")])
        self.assertEqual(recovered["tail_bytes"], 13)
        self.assertTrue(writer.status()["write_failed"])
        self.assertEqual(self.path.read_bytes(), before)
        with self.assertRaises(FileExistsError):
            self.writer()

    def test_newline_terminated_corruption_rejects_instead_of_skipping(self):
        writer = self.writer()
        writer.append(event())
        writer.close()
        self.path.write_bytes(
            self.path.read_bytes().replace(
                b"client_request_attempt", b"client_request_attempX"
            )
        )
        before = self.path.read_bytes()
        with self.assertRaises(WireJournalError):
            read_wire_journal(self.path, OWNER, JOURNAL)
        self.assertEqual(self.path.read_bytes(), before)

    def test_owner_or_budget_identity_mismatch_fails_closed(self):
        self.writer().close()
        for owner, journal in [("c" * 64, JOURNAL), (OWNER, "d" * 32)]:
            with self.subTest(owner=owner), self.assertRaises(WireJournalError):
                read_wire_journal(self.path, owner, journal)

    def test_missing_or_torn_header_and_symlink_are_not_accepted(self):
        with self.assertRaises(FileNotFoundError):
            read_wire_journal(self.path, OWNER, JOURNAL)
        self.path.write_bytes(b'{"partial":')
        with self.assertRaises(WireJournalError):
            read_wire_journal(self.path, OWNER, JOURNAL)
        link = self.root / "link"
        link.symlink_to(self.path)
        with self.assertRaises(OSError):
            read_wire_journal(link, OWNER, JOURNAL)

    def test_count_and_byte_bounds_preserve_previous_commits(self):
        writer = self.writer(max_events=1)
        writer.append(event())
        before = self.path.read_bytes()
        with self.assertRaises(WireJournalError):
            writer.append(event(b"second"))
        self.assertEqual(self.path.read_bytes(), before)
        bounded = self.writer(self.root / "bounded", max_bytes=1024)
        before = bounded.path.read_bytes()
        with self.assertRaises(WireJournalError):
            bounded.append(event(b"x" * 1200))
        self.assertEqual(bounded.path.read_bytes(), before)

    def test_extra_headers_or_wrong_body_digest_never_enter_journal(self):
        bad = [
            dict(event(), Authorization="not-a-real-key"),
            dict(event(), body_sha256="0" * 64),
        ]
        for i, item in enumerate(bad):
            writer = self.writer(self.root / ("bad%d" % i))
            before = writer.path.read_bytes()
            with self.assertRaises(WireJournalError):
                writer.append(item)
            self.assertEqual(writer.path.read_bytes(), before)
            self.assertTrue(writer.failed)

    def test_cli_emits_metadata_without_raw_capability_body(self):
        writer = self.writer()
        writer.append(event())
        writer.close()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "agent_lab.wire_journal",
                str(self.path),
                "--owner",
                OWNER,
                "--journal-id",
                JOURNAL,
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        public = json.loads(result.stdout)
        self.assertEqual(public["events"][0]["body_sha256"], event()["body_sha256"])
        self.assertNotIn("body_base64", result.stdout)
        self.assertNotIn("private-control-capability", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
