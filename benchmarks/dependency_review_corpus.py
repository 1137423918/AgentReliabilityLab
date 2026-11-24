"""Expose prepared external-project upgrade facts to the unchanged MCP auditor.

The model sees observed inputs and outcomes, not the preparer's derived verdict.
Known-task grading is generated separately and is never in the MCP catalog.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re


def make_document(report):
    before = report["baseline"]
    candidate = report["candidate"]
    after = candidate.get("scan") if candidate else None
    chosen = report["selected_target"]
    target_name = before["findings"][chosen]["package"] if chosen else None
    review = report["review"]
    remaining = (
        [f for f in after["findings"].values() if f["package"] == target_name]
        if after
        else None
    )
    document = {
        "project": {
            k: report["snapshot"][k] for k in ["id", "repository", "tag", "commit"]
        },
        "scope": report["inventory"]["scope"],
        "baseline_statistics": {
            k: before[k]
            for k in [
                "scanned_registry_resolutions",
                "expected_registry_resolutions",
                "affected_resolutions",
            ]
        },
        "coverage": {
            "before_registry_complete": before["registry_coverage_complete"],
            "after_registry_complete": after["registry_coverage_complete"]
            if after
            else None,
            "local_or_other_source_entries": report["inventory"]["nonregistry_entries"],
            "nonregistry_scanner_records": before["nonregistry_scanner_records"],
        },
        "execution": {
            "candidate_prepared": after is not None,
            "project_environment_installed": False,
            "resolver_metadata_backend_may_run": True,
            "compatibility_tests_run": False,
        },
        "resolution": {
            "exit_code": candidate["resolver"]["exit_code"] if candidate else None,
            "timed_out": candidate["resolver"]["timed_out"] if candidate else None,
            "original_requirements_changed": candidate["original_requirements_changed"]
            if candidate
            else None,
        },
        "target": {
            "name": target_name,
            "declared_requirements": before["findings"][chosen]["declared_requirements"]
            if chosen
            else [],
            "before_versions": review.get("target_before", [chosen] if chosen else []),
            "after_versions": review.get("target_after"),
            "version_changed": review.get("target_version_changed"),
            "advisory_ids_before": before["findings"][chosen]["advisory_ids"]
            if chosen
            else [],
            "remaining_advisory_match_count": sum(
                len(f["advisory_ids"]) for f in remaining
            )
            if remaining is not None
            else None,
        },
        "delta": {
            "new_package_advisory_match_count": len(review["new_advisory_matches"])
            if after
            else None,
            "new_package_advisory_matches": review.get("new_advisory_matches"),
            "remaining_affected_registry_resolutions": after["affected_resolutions"]
            if after
            else None,
        },
        "provenance": {
            "original_files": report["snapshot"]["files"],
            "database": report["database"],
            "baseline_scan_sha256": before["receipt"]["raw_sha256"],
            "candidate_scan_sha256": after["receipt"]["raw_sha256"] if after else None,
            "candidate_lock_sha256": candidate.get("lock_sha256")
            if candidate
            else None,
            "original_inputs_unchanged": report["original_inputs_unchanged"],
            "candidate_source": candidate.get("source_materialization")
            if candidate
            else None,
        },
    }
    # Recompute the claim from observations rather than exposing/copying the preparer's answer.
    expected = bool(
        document["execution"]["candidate_prepared"]
        and document["resolution"]["exit_code"] == 0
        and document["resolution"]["original_requirements_changed"] is False
        and document["coverage"]["before_registry_complete"] is True
        and document["coverage"]["after_registry_complete"] is True
        and document["target"]["version_changed"] is True
        and document["target"]["remaining_advisory_match_count"] == 0
        and document["delta"]["new_package_advisory_match_count"] == 0
    )
    if expected != review["ready_for_integration_tests"]:
        raise ValueError("Independent observation gate and pipeline verdict disagree")
    report_id = re.sub(r"[^a-z0-9_]", "_", report["snapshot"]["id"].lower())
    fields = {
        "/execution/candidate_prepared": document["execution"]["candidate_prepared"],
        "/resolution/exit_code": document["resolution"]["exit_code"],
        "/resolution/original_requirements_changed": document["resolution"][
            "original_requirements_changed"
        ],
        "/coverage/before_registry_complete": document["coverage"][
            "before_registry_complete"
        ],
        "/coverage/after_registry_complete": document["coverage"][
            "after_registry_complete"
        ],
        "/target/version_changed": document["target"]["version_changed"],
        "/target/remaining_advisory_match_count": document["target"][
            "remaining_advisory_match_count"
        ],
        "/delta/new_package_advisory_match_count": document["delta"][
            "new_package_advisory_match_count"
        ],
    }
    question = (
        "Audit this prepared dependency-upgrade claim for "
        + report["snapshot"]["repository"]
        + " release "
        + report["snapshot"]["tag"]
        + ": "
        "'The isolated candidate satisfies the gate for integration testing.' The gate requires a prepared/rescanned candidate, "
        "resolver exit0, unchanged original requirements, complete registry inventory coverage before and after, a changed target version, "
        "zero remaining target advisory matches and zero newly introduced package/advisory matches. "
        "Verify every condition from this project's report, including null/unperformed outcomes. "
        "This is not deployment approval or proof of exploitability; optional/development resolutions are included. "
        "Return one evidence-backed verdict with references covering all eight conditions."
    )
    case = {
        "id": report_id + "_integration_gate",
        "question": question,
        "expected_supported": expected,
        "required_facts": {report_id: fields},
    }
    return report_id, document, case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--source-base", required=True)
    parser.add_argument(
        "--expected-count", type=int, default=2,
        help="Predeclared snapshot count (default: 2)",
    )
    args = parser.parse_args()
    if not 1 <= args.expected_count <= 32:
        parser.error("Expected count must be between 1 and 32")
    args.output.mkdir(mode=0o700)
    catalog, cases = [], []
    for path in sorted(args.reviews.glob("*-review.json")):
        report_id, document, case = make_document(json.loads(path.read_text()))
        raw = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode()
        if len(raw) > 262144:
            raise ValueError("Prepared report exceeds canonical MCP catalog bound")
        filename = report_id + ".json"
        (args.output / filename).write_bytes(raw)
        catalog.append(
            {
                "id": report_id,
                "path": filename,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "description": "Prepared dependency upgrade observations for "
                + document["project"]["repository"]
                + " "
                + document["project"]["tag"]
                + "; isolated resolver, fixed-database scans and target facts. No deployment approval.",
                "fields": [
                    "/execution",
                    "/resolution",
                    "/coverage",
                    "/target",
                    "/delta",
                    "/provenance",
                ],
            }
        )
        cases.append(case)
    if len(catalog) != args.expected_count:
        raise ValueError("Prepared reports differ from the predeclared snapshot count")
    (args.output / "catalog.json").write_text(
        json.dumps(
            {
                "version": 1,
                "source_commit": args.snapshot,
                "source_base": args.source_base,
                "reports": catalog,
            },
            indent=2,
        )
        + "\n"
    )
    # Gold is adjacent to, never inside, the served evidence root.
    cases_path = args.output.parent / (args.output.name + "-cases.json")
    cases_path.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "reports": len(catalog),
                "cases": len(cases),
                "derived_verdict_exposed_in_catalog": False,
                "gold_outside_served_root": True,
            }
        )
    )


if __name__ == "__main__":
    main()
