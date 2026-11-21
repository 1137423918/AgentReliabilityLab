"""Read a pinned report catalog and verify an agent's factual citations.

The manifest is trusted operator input, not an authenticated owner boundary.
Only JSON reports named in that manifest are available to the agent tools.
"""

import hashlib
import json
import re
from pathlib import Path


class EvidenceError(ValueError):
    """The selected evidence or proposed citation cannot be verified."""


def _encoded(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (ValueError, TypeError) as exc:
        raise EvidenceError("Evidence must contain finite JSON values") from exc


def _pointer(document, pointer):
    if not isinstance(pointer, str) or len(pointer) > 256:
        raise EvidenceError("JSON pointer must be a bounded string")
    if not pointer.startswith("/"):
        raise EvidenceError("Select an explicit JSON pointer, not a whole report")
    value = document
    for part in pointer[1:].split("/"):
        if re.search(r"~(?![01])", part):
            raise EvidenceError("Invalid JSON pointer escape")
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", key):
            index = int(key)
            if index >= len(value):
                raise EvidenceError("JSON array index is absent")
            value = value[index]
        else:
            raise EvidenceError("JSON pointer is absent")
    return value


class EvidenceCatalog:
    """A small curated catalog; each successful read is recorded for citations."""

    def __init__(self, root, manifest, *, max_output_bytes=8192):
        self.root = Path(root).resolve()
        if not isinstance(max_output_bytes, int) or not 256 <= max_output_bytes <= 8192:
            raise EvidenceError("Output bound must be between256 and8192 bytes")
        self.max_output_bytes = max_output_bytes
        self.manifest = json.loads(Path(manifest).read_text(encoding="utf-8"))
        if self.manifest.get("version") != 1:
            raise EvidenceError("Unsupported evidence manifest")
        self.entries = {}
        self.reads = []
        self._observed = set()
        reports = self.manifest["reports"]
        if not isinstance(reports, list) or not 1 <= len(reports) <= 32:
            raise EvidenceError("Catalog must contain1 to32 reports")
        for entry in reports:
            report_id = entry["id"]
            if not isinstance(report_id, str) or not re.fullmatch(
                r"[a-z0-9_-]{1,48}", report_id
            ):
                raise EvidenceError("Invalid report ID")
            if report_id in self.entries:
                raise EvidenceError("Duplicate report ID")
            if not re.fullmatch(r"[a-f0-9]{64}", entry["sha256"]):
                raise EvidenceError("Invalid report digest")
            self.entries[report_id] = dict(entry)
            self._load(report_id)
        if not 1 <= len(self.entries) <= 32:
            raise EvidenceError("Catalog must contain1 to32 reports")

    def _load(self, report_id):
        if not isinstance(report_id, str) or report_id not in self.entries:
            raise EvidenceError("Unknown report ID")
        entry = self.entries[report_id]
        relative = Path(entry["path"])
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.suffix != ".json"
        ):
            raise EvidenceError("Reports must be relative JSON paths")
        path = self.root
        for part in relative.parts:
            path = path / part
            if path.is_symlink():
                raise EvidenceError("Report symlinks are not admitted")
        if not path.resolve().is_relative_to(self.root):
            raise EvidenceError("Report escapes catalog root")
        try:
            with path.open("rb") as stream:
                raw = stream.read(262145)
        except OSError as exc:
            raise EvidenceError("Report is unavailable") from exc
        if len(raw) > 262144 or hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise EvidenceError("Report bytes differ from the pinned snapshot")
        try:
            document = json.loads(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise EvidenceError("Report is not valid JSON") from exc
        if not isinstance(document, dict):
            raise EvidenceError("Report root must be a JSON object")
        return document

    def _bounded(self, value):
        encoded = _encoded(value)
        if len(encoded.encode()) > self.max_output_bytes:
            raise EvidenceError("Result exceeds the byte bound; request fewer fields")
        return encoded

    def list_reports(self):
        """List available report IDs, descriptions and top-level JSON pointers."""
        rows = []
        for report_id, entry in self.entries.items():
            document = self._load(report_id)
            pointers = [
                "/" + key.replace("~", "~0").replace("/", "~1") for key in document
            ]
            rows.append(
                {
                    "id": report_id,
                    "description": entry["description"],
                    "fields": entry.get("fields", pointers),
                }
            )
        return self._bounded(
            {"snapshot": self.manifest["source_commit"], "reports": rows}
        )

    def read_report(self, report_id, pointers):
        """Read up to8 JSON pointers from a listed report, with its exact digest."""
        if (
            not isinstance(pointers, list)
            or not 1 <= len(pointers) <= 8
            or any(not isinstance(p, str) for p in pointers)
            or len(set(pointers)) != len(pointers)
        ):
            raise EvidenceError("Select1 to8 distinct JSON pointers")
        document = self._load(report_id)
        values = {p: _pointer(document, p) for p in pointers}
        entry = self.entries[report_id]
        row = {
            "report_id": report_id,
            "sha256": entry["sha256"],
            "source_url": self.manifest["source_base"] + entry["path"],
            "values": values,
        }
        result = self._bounded(row)
        self.reads.append(row)
        self._observed.update((report_id, p) for p in pointers)
        return result

    def verify_assessment(self, assessment):
        """Check factual values and lineage; this does not verify free prose."""
        if not isinstance(assessment, dict) or set(assessment) != {
            "claim_supported",
            "explanation",
            "facts",
            "citations",
        }:
            raise EvidenceError("Unexpected assessment fields")
        if type(assessment["claim_supported"]) is not bool:
            raise EvidenceError("Verdict must be a boolean")
        if (
            not isinstance(assessment["explanation"], str)
            or not 1 <= len(assessment["explanation"]) <= 1600
        ):
            raise EvidenceError("Explanation must be bounded text")
        citations = assessment["citations"]
        facts = assessment["facts"]
        if not isinstance(citations, list) or not 1 <= len(citations) <= 8:
            raise EvidenceError("Provide1 to8 citations")
        if not isinstance(facts, list) or not 1 <= len(facts) <= 8:
            raise EvidenceError("Provide1 to8 facts")
        cited = set()
        for citation in citations:
            if not isinstance(citation, dict) or set(citation) != {
                "report_id",
                "sha256",
            }:
                raise EvidenceError("Unexpected citation fields")
            report_id = citation["report_id"]
            self._load(report_id)
            if (
                report_id in cited
                or citation["sha256"] != self.entries[report_id]["sha256"]
            ):
                raise EvidenceError("Citation digest mismatch or duplicate")
            cited.add(report_id)
        used = set()
        seen = set()
        for fact in facts:
            if not isinstance(fact, dict) or set(fact) != {
                "report_id",
                "pointer",
                "value",
            }:
                raise EvidenceError("Unexpected fact fields")
            report_id, pointer = fact["report_id"], fact["pointer"]
            if not isinstance(report_id, str) or not isinstance(pointer, str):
                raise EvidenceError("Fact IDs and pointers must be strings")
            pair = report_id, pointer
            observed = any(
                report_id == seen_id
                and (pointer == selected or pointer.startswith(selected + "/"))
                for seen_id, selected in self._observed
            )
            if pair in seen or not observed or report_id not in cited:
                raise EvidenceError("Fact was not read, cited or is duplicated")
            if _encoded(_pointer(self._load(report_id), pointer)) != _encoded(
                fact["value"]
            ):
                raise EvidenceError("Claimed fact differs from actual report")
            seen.add(pair)
            used.add(report_id)
        if used != cited:
            raise EvidenceError("Every citation must support an observed fact")
        return {
            "fact_values_verified": True,
            "read_lineage_verified": True,
            "free_prose_verified": False,
            "facts": len(facts),
            "citations": len(cited),
        }
