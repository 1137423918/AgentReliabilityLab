"""Bounded audit contexts and read receipts for a local evidence tool service.

Audit handles are process-local capabilities, not authenticated user identities.
The trusted report manifest and exact-value checks come from EvidenceCatalog.
"""

import hashlib
import json
import secrets
import threading
import time
from pathlib import Path

from agent_lab.evidence_audit import EvidenceCatalog, EvidenceError


class EvidenceService:
    """Separate read provenance for bounded, expiring audit capabilities."""

    def __init__(
        self,
        root,
        manifest,
        *,
        max_audits=32,
        max_operations=16,
        max_reads=8,
        ttl_seconds=600,
        clock=time.monotonic,
    ):
        for value, upper in [
            (max_audits, 128),
            (max_operations, 128),
            (max_reads, 32),
            (ttl_seconds, 3600),
        ]:
            if type(value) is not int or not 1 <= value <= upper:
                raise ValueError("Service limits must be bounded positive integers")
        self.root = root
        self.manifest = manifest
        self.manifest_sha256 = hashlib.sha256(Path(manifest).read_bytes()).hexdigest()
        self.max_audits = max_audits
        self.max_operations = max_operations
        self.max_reads = max_reads
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._audits = {}
        self._lock = threading.RLock()

    @staticmethod
    def _bounded(value):
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        if len(encoded.encode()) > 8192:
            raise EvidenceError("Business result exceeds8192 bytes")
        return value

    def _purge(self):
        now = self.clock()
        for handle in list(self._audits):
            if self._audits[handle]["expires"] <= now:
                del self._audits[handle]

    def _get(self, handle, *, charge=True):
        self._purge()
        if not isinstance(handle, str) or handle not in self._audits:
            raise EvidenceError("Unknown or expired audit capability")
        audit = self._audits[handle]
        if charge:
            if audit["operations"] >= self.max_operations:
                raise EvidenceError("Audit operation budget exhausted")
            audit["operations"] += 1
        return audit

    def begin(self):
        """Create a fresh audit capability; never reuse a lost or expired context."""
        with self._lock:
            self._purge()
            if len(self._audits) >= self.max_audits:
                raise EvidenceError("Active audit capacity exhausted")
            catalog = EvidenceCatalog(self.root, self.manifest, max_output_bytes=7168)
            manifest_bytes = Path(self.manifest).read_bytes()
            if (
                json.loads(manifest_bytes) != catalog.manifest
                or hashlib.sha256(manifest_bytes).hexdigest() != self.manifest_sha256
            ):
                raise EvidenceError("Manifest changed during audit creation")
            handle = secrets.token_urlsafe(24)
            self._audits[handle] = {
                "catalog": catalog,
                "expires": self.clock() + self.ttl_seconds,
                "operations": 0,
                "receipts": {},
            }
            return {
                "audit_id": handle,
                "expires_in_seconds": self.ttl_seconds,
                "max_operations": self.max_operations,
                "max_reads": self.max_reads,
                "snapshot": catalog.manifest["source_commit"],
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            }

    def list_reports(self, handle):
        """List the fixed report catalog, charging one operation."""
        with self._lock:
            audit = self._get(handle)
            return json.loads(audit["catalog"].list_reports())

    def read_report(self, handle, report_id, pointers):
        """Read report fields and issue a receipt required by later verification."""
        with self._lock:
            audit = self._get(handle)
            if len(audit["receipts"]) >= self.max_reads:
                raise EvidenceError("Audit read budget exhausted")
            row = json.loads(audit["catalog"].read_report(report_id, pointers))
            receipt = secrets.token_urlsafe(24)
            result = self._bounded({"receipt": receipt, "report": row})
            audit["receipts"][receipt] = row
            return result

    def verify_assessment(self, handle, assessment, receipts):
        """Verify exact facts only when the caller presents matching read receipts."""
        with self._lock:
            audit = self._get(handle)
            if (
                not isinstance(receipts, list)
                or not 1 <= len(receipts) <= self.max_reads
                or any(not isinstance(r, str) for r in receipts)
                or len(set(receipts)) != len(receipts)
            ):
                raise EvidenceError("Provide distinct bounded read receipts")
            if any(r not in audit["receipts"] for r in receipts):
                raise EvidenceError("Receipt was not issued by this audit")
            # Run the common structural/type/value checks before using fact keys.
            verified = audit["catalog"].verify_assessment(assessment)
            for fact in assessment["facts"]:
                if not any(
                    row["report_id"] == fact["report_id"]
                    and any(
                        fact["pointer"] == pointer
                        or fact["pointer"].startswith(pointer + "/")
                        for pointer in row["values"]
                    )
                    for row in (audit["receipts"][r] for r in receipts)
                ):
                    raise EvidenceError("Fact lacks a presented read receipt")
            return self._bounded(
                {
                    "evidence_verified": True,
                    "verification": verified,
                    "free_prose_semantics_verified": False,
                    "verdict_truth_verified": False,
                }
            )

    def status(self, handle):
        """Return counters without charging another operation or exposing receipts."""
        with self._lock:
            audit = self._get(handle, charge=False)
            return {
                "operations_spent": audit["operations"],
                "reads_completed": len(audit["receipts"]),
                "max_operations": self.max_operations,
                "max_reads": self.max_reads,
            }

    def close(self, handle):
        """Discard one context even when its operation budget is exhausted."""
        with self._lock:
            self._get(handle, charge=False)
            del self._audits[handle]
            return {"closed": True}
