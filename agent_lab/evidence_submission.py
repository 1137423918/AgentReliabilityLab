"""Bind model-selected references to this audit's actual read responses.

Selection, verdict and explanation belong to the caller. This helper does not
read files, invoke tools, select missing facts, infer a verdict or use answers.
The canonical remote verifier must still validate values, hashes and receipts.
"""

from copy import deepcopy
import re

from .evidence_audit import EvidenceError, _pointer


def bind_read_references(draft, reads):
    """Compile exact observed JSON values and one source digest per used report.

    ``reads`` contains trusted ``read_report`` results, before hiding receipts
    from the model. A reference must be an exact read pointer or its descendant.
    Extra reads are never cited unless the model actually selects them. Nothing
    is coerced or repaired, including an invalid or missing reference.
    """
    if not isinstance(draft, dict) or set(draft) != {
        "claim_supported",
        "explanation",
        "facts",
    }:
        raise EvidenceError("Reference submission contains unexpected fields")
    refs = draft["facts"]
    if not isinstance(refs, list) or not 1 <= len(refs) <= 8:
        raise EvidenceError("Select1 to8 explicit fact references")
    facts = []
    sources = {}
    seen = set()
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != {"report_id", "pointer"}:
            raise EvidenceError("Reference must contain only report_id and pointer")
        report_id, pointer = ref["report_id"], ref["pointer"]
        if (
            not isinstance(report_id, str)
            or not isinstance(pointer, str)
            or not pointer.startswith("/")
            or len(pointer) > 256
            or re.search(r"~(?![01])", pointer)
        ):
            raise EvidenceError("Invalid explicit reference")
        if (report_id, pointer) in seen:
            raise EvidenceError("Duplicate fact reference")
        candidates = []
        for read in reads:
            report = read["report"]
            if report["report_id"] != report_id:
                continue
            source = report["sha256"]
            if report_id in sources and sources[report_id] != source:
                raise EvidenceError("Observed report revisions disagree")
            for selected, observed in report["values"].items():
                if pointer == selected:
                    candidates.append((source, observed))
                elif pointer.startswith(selected + "/"):
                    try:
                        candidates.append(
                            (source, _pointer(observed, pointer[len(selected) :]))
                        )
                    except EvidenceError:
                        # Another successful read may cover this child pointer.
                        continue
        if not candidates:
            raise EvidenceError("Reference was not covered by this audit's reads")
        source, value = candidates[0]
        # Only hash identity is checked here; equality/type/receipt authority
        # remains with the unchanged canonical assessment verifier.
        if any(candidate_source != source for candidate_source, _ in candidates):
            raise EvidenceError("Observed report revisions disagree")
        sources[report_id] = source
        facts.append(
            {"report_id": report_id, "pointer": pointer, "value": deepcopy(value)}
        )
        seen.add((report_id, pointer))
    return {
        "claim_supported": draft["claim_supported"],
        "explanation": draft["explanation"],
        "facts": facts,
        "citations": [
            {"report_id": report_id, "sha256": sources[report_id]}
            for report_id in sorted(sources)
        ],
    }
