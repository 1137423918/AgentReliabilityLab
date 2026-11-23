"""Source binding against the real canonical receipt verifier, no model needed."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from agent_lab.evidence_audit import EvidenceError
from agent_lab.evidence_service import EvidenceService
from agent_lab.evidence_submission import bind_read_references


class EvidenceSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        documents = {
            "current": {
                "runs": [{"passed": 3}],
                "enabled": False,
                "a/b": {"~key": [7, True]},
            },
            "history": {"passed": 2},
        }
        reports = []
        for name, document in documents.items():
            raw = json.dumps(document).encode()
            (self.root / (name + ".json")).write_bytes(raw)
            reports.append(
                {
                    "id": name,
                    "path": name + ".json",
                    "description": name,
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
        manifest = self.root / "catalog.json"
        manifest.write_text(
            json.dumps(
                {
                    "version": 1,
                    "source_commit": "a" * 40,
                    "source_base": "https://example.invalid/",
                    "reports": reports,
                }
            )
        )
        self.service = EvidenceService(self.root, manifest)
        self.handle = self.service.begin()["audit_id"]
        self.read = self.service.read_report(
            self.handle, "current", ["/runs", "/enabled", "/a~1b"]
        )

    def draft(self, *refs):
        return {
            "claim_supported": False,
            "explanation": "Observed facts only.",
            "facts": [
                {"report_id": report_id, "pointer": pointer}
                for report_id, pointer in refs
            ],
        }

    def verify(self, bound, reads):
        return self.service.verify_assessment(
            self.handle, bound, [r["receipt"] for r in reads]
        )

    def test_descendant_values_and_types_come_from_real_reads(self):
        bound = bind_read_references(
            self.draft(("current", "/runs/0/passed"), ("current", "/enabled")),
            [self.read],
        )
        self.assertEqual(bound["facts"][0]["value"], 3)
        self.assertIs(bound["facts"][1]["value"], False)
        self.assertTrue(self.verify(bound, [self.read])["evidence_verified"])
        self.assertFalse(self.verify(bound, [self.read])["verdict_truth_verified"])

    def test_unused_read_is_not_cited_and_no_extra_read_is_performed(self):
        extra = self.service.read_report(self.handle, "history", ["/passed"])
        spent = self.service.status(self.handle)["operations_spent"]
        bound = bind_read_references(
            self.draft(("current", "/runs")), [self.read, extra]
        )
        self.assertEqual([c["report_id"] for c in bound["citations"]], ["current"])
        self.assertEqual(self.service.status(self.handle)["operations_spent"], spent)
        self.assertTrue(self.verify(bound, [self.read, extra])["evidence_verified"])

    def test_parent_objects_are_copied_without_mutating_the_receipt(self):
        original = deepcopy(self.read)
        bound = bind_read_references(self.draft(("current", "/runs")), [self.read])
        self.assertTrue(self.verify(bound, [self.read])["evidence_verified"])
        bound["facts"][0]["value"][0]["passed"] = 99
        self.assertEqual(self.read, original)
        with self.assertRaises(EvidenceError):
            self.verify(bound, [self.read])

    def test_escaped_keys_and_array_children(self):
        bound = bind_read_references(
            self.draft(("current", "/a~1b/~0key/1")), [self.read]
        )
        self.assertIs(bound["facts"][0]["value"], True)
        self.assertTrue(self.verify(bound, [self.read])["evidence_verified"])

    def test_unread_missing_and_prefix_sibling_references_are_rejected(self):
        for report_id, pointer in [
            ("history", "/passed"),
            ("current", "/run"),
            ("current", "/runs/9/passed"),
            ("unknown", "/runs"),
        ]:
            with self.subTest(report_id=report_id, pointer=pointer):
                with self.assertRaises(EvidenceError):
                    bind_read_references(self.draft((report_id, pointer)), [self.read])

    def test_model_values_citations_invalid_and_duplicate_refs_are_rejected(self):
        draft = self.draft(("current", "/enabled"))
        draft["facts"][0]["value"] = True
        with self.assertRaises(EvidenceError):
            bind_read_references(draft, [self.read])
        draft = self.draft(("current", "/enabled"))
        draft["citations"] = []
        with self.assertRaises(EvidenceError):
            bind_read_references(draft, [self.read])
        for pointer in ["", "/a~2b", "/" + "x" * 256]:
            with self.assertRaises(EvidenceError):
                bind_read_references(self.draft(("current", pointer)), [self.read])
        with self.assertRaises(EvidenceError):
            bind_read_references(
                self.draft(("current", "/enabled"), ("current", "/enabled")),
                [self.read],
            )

    def test_compiler_does_not_override_verdict_or_weaken_receipt_authority(self):
        draft = self.draft(("current", "/enabled"))
        draft["claim_supported"] = "false"
        with self.assertRaises(EvidenceError):
            self.verify(bind_read_references(draft, [self.read]), [self.read])
        other = self.service.begin()["audit_id"]
        bound = bind_read_references(self.draft(("current", "/enabled")), [self.read])
        with self.assertRaises(EvidenceError):
            self.service.verify_assessment(other, bound, [self.read["receipt"]])

    def test_mixed_source_revisions_are_rejected(self):
        changed = deepcopy(self.read)
        changed["report"]["sha256"] = "b" * 64
        with self.assertRaises(EvidenceError):
            bind_read_references(
                self.draft(("current", "/enabled")), [self.read, changed]
            )


if __name__ == "__main__":
    unittest.main()
