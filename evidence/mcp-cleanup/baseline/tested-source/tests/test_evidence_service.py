"""Core receipt and bounded-context contracts; no optional MCP import required."""

import copy
import hashlib
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent_lab.evidence_audit import EvidenceError
from agent_lab.evidence_service import EvidenceService


class EvidenceServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        report = self.root / "report.json"
        report.write_text(
            json.dumps({"passed": 116, "nested": {"value": 0}, "large": "x" * 7200}),
            encoding="utf-8",
        )
        self.sha = hashlib.sha256(report.read_bytes()).hexdigest()
        self.manifest = self.root / "catalog.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "version": 1,
                    "source_commit": "f" * 40,
                    "source_base": "https://example.org/",
                    "reports": [
                        {
                            "id": "core",
                            "path": "report.json",
                            "description": "core",
                            "sha256": self.sha,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def service(self, **limits):
        return EvidenceService(self.root, self.manifest, **limits)

    def assessment(self):
        return {
            "claim_supported": True,
            "explanation": "Known count",
            "facts": [{"report_id": "core", "pointer": "/passed", "value": 116}],
            "citations": [{"report_id": "core", "sha256": self.sha}],
        }

    def test_read_receipts_cannot_be_guessed_or_borrowed_between_audits(self):
        s = self.service()
        a = s.begin()["audit_id"]
        b = s.begin()["audit_id"]
        row = s.read_report(a, "core", ["/passed"])
        self.assertTrue(
            s.verify_assessment(a, self.assessment(), [row["receipt"]])[
                "evidence_verified"
            ]
        )
        for owner, receipts in [(a, []), (a, ["missing"]), (b, [row["receipt"]])]:
            with self.subTest(owner=owner), self.assertRaises(EvidenceError):
                s.verify_assessment(owner, self.assessment(), receipts)

    def test_presented_receipt_must_cover_the_claimed_field(self):
        s = self.service()
        a = s.begin()["audit_id"]
        first = s.read_report(a, "core", ["/passed"])
        second = s.read_report(a, "core", ["/nested"])
        proposal = self.assessment()
        proposal["facts"] = [
            {"report_id": "core", "pointer": "/nested/value", "value": 0}
        ]
        with self.assertRaises(EvidenceError):
            s.verify_assessment(a, proposal, [first["receipt"]])
        self.assertTrue(
            s.verify_assessment(a, proposal, [second["receipt"]])["evidence_verified"]
        )
        bad = copy.deepcopy(proposal)
        bad["facts"][0]["value"] = False
        with self.assertRaises(EvidenceError):
            s.verify_assessment(a, bad, [second["receipt"]])

    def test_concurrent_attempts_share_a_hard_operation_cap(self):
        s = self.service(max_operations=3)
        a = s.begin()["audit_id"]

        def operation(_):
            try:
                s.list_reports(a)
                return True
            except EvidenceError:
                return False

        with ThreadPoolExecutor(max_workers=6) as pool:
            result = list(pool.map(operation, range(6)))
        self.assertEqual(sum(result), 3)
        self.assertEqual(s.status(a)["operations_spent"], 3)
        self.assertTrue(s.close(a)["closed"])
        with self.assertRaises(EvidenceError):
            s.status(a)

    def test_invalid_and_oversize_reads_are_charged_without_receipts(self):
        s = self.service()
        a = s.begin()["audit_id"]
        for pointers in [["/missing"], ["/large"]]:
            with self.assertRaises(EvidenceError):
                s.read_report(a, "core", pointers)
        self.assertEqual(s.status(a)["operations_spent"], 2)
        self.assertEqual(s.status(a)["reads_completed"], 0)
        with self.assertRaises(EvidenceError):
            s.verify_assessment(a, self.assessment(), ["unknown"])
        self.assertEqual(s.status(a)["operations_spent"], 3)

    def test_expiry_capacity_close_and_restart_invalidate_old_capabilities(self):
        clock = [10.0]
        s = self.service(max_audits=1, ttl_seconds=5, clock=lambda: clock[0])
        a = s.begin()["audit_id"]
        with self.assertRaises(EvidenceError):
            s.begin()
        clock[0] = 15.0
        with self.assertRaises(EvidenceError):
            s.status(a)
        b = s.begin()["audit_id"]
        self.assertNotEqual(a, b)
        with self.assertRaises(EvidenceError):
            self.service().status(b)
        s.close(b)
        self.assertTrue(s.begin()["audit_id"])

    def test_read_cap_and_report_hash_tampering_do_not_issue_extra_receipts(self):
        s = self.service(max_reads=1)
        a = s.begin()["audit_id"]
        s.read_report(a, "core", ["/passed"])
        with self.assertRaises(EvidenceError):
            s.read_report(a, "core", ["/passed"])
        self.assertEqual(s.status(a)["reads_completed"], 1)
        b = s.begin()["audit_id"]
        (self.root / "report.json").write_text('{"passed":999}', encoding="utf-8")
        with self.assertRaises(EvidenceError):
            s.read_report(b, "core", ["/passed"])
        self.assertEqual(s.status(b)["reads_completed"], 0)
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        data["source_commit"] = "e" * 40
        self.manifest.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(EvidenceError):
            s.begin()


if __name__ == "__main__":
    unittest.main()
