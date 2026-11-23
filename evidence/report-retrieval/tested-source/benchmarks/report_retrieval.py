"""CPU-only metadata retrieval diagnostics over pinned real project reports.

Queries/judgments are operator-authored and unblinded. Report coverage is not
fact correctness, end-to-end model success, inference tokens or monetary cost.
"""

import argparse
import hashlib
import json
from pathlib import Path
import statistics

from agent_lab.evidence_audit import EvidenceCatalog
from agent_lab.report_retrieval import encoded, rank_reports


def evaluate(root, manifest, cases, output):
    output.mkdir(exist_ok=False)
    catalog = json.loads(
        EvidenceCatalog(root, manifest, max_output_bytes=7168).list_reports()
    )
    queries = json.loads(cases.read_text())["queries"]
    assert len({q["id"] for q in queries}) == len(queries)
    ids = {r["id"] for r in catalog["reports"]}
    rows = []
    for q in queries:
        required = set(q["required_reports"])
        assert required and required <= ids
        policies = {}
        for policy in ["all", "overlap", "bm25"]:
            value = (
                catalog
                if policy == "all"
                else rank_reports(catalog, q["query"], policy=policy)
            )
            selected = [r["id"] for r in value["reports"]]
            recalled = sorted(required & set(selected))
            policies[policy] = {
                "selected": selected,
                "required_recalled": recalled,
                "all_required_present": required <= set(selected),
                "required_recall": len(recalled) / len(required),
                "serialized_result_bytes": len(encoded(value).encode()),
                "within_4096_bytes": len(encoded(value).encode()) <= 4096,
            }
        rows.append({**q, "policies": policies})
    summary = {
        "scope": "Unblinded metadata report-selection diagnostics; not model task scores.",
        "corpus_reports": len(catalog["reports"]),
        "queries": len(queries),
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "cases_sha256": hashlib.sha256(cases.read_bytes()).hexdigest(),
        "source_snapshot": catalog["snapshot"],
        "ranking": {
            "max_reports": 4,
            "serialized_response_limit_bytes": 4096,
            "BM25_k1": 1.2,
            "BM25_b": 0.75,
        },
        "policies": {},
        "neural_calls": 0,
        "score_or_schema_feedback": False,
    }
    for policy in ["all", "overlap", "bm25"]:
        data = [row["policies"][policy] for row in rows]
        summary["policies"][policy] = {
            "all_required_present": sum(d["all_required_present"] for d in data),
            "macro_required_recall": statistics.mean(
                d["required_recall"] for d in data
            ),
            "mean_serialized_result_bytes": statistics.mean(
                d["serialized_result_bytes"] for d in data
            ),
            "maximum_serialized_result_bytes": max(
                d["serialized_result_bytes"] for d in data
            ),
            "within_4096_bytes": sum(d["within_4096_bytes"] for d in data),
            "mean_reports_returned": statistics.mean(len(d["selected"]) for d in data),
        }
    (output / "cases.json").write_text(json.dumps(rows, indent=2) + "\n")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    evaluate(args.root, args.manifest, args.cases, args.output)


if __name__ == "__main__":
    main()
