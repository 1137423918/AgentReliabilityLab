"""Independent, predeclared fact-coverage grading for known fixed audit cases."""

import argparse
import asyncio
import json
from pathlib import Path


def _leaves(value, pointer):
    if isinstance(value, dict):
        for key, child in value.items():
            escaped = key.replace("~", "~0").replace("/", "~1")
            yield from _leaves(child, pointer + "/" + escaped)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _leaves(child, pointer + "/" + str(index))
    else:
        yield pointer, value


def grade_case(result, case):
    assessment = result.get("assessment") or {}
    observed = {}
    for fact in assessment.get("facts", []):
        for pointer, value in _leaves(fact["value"], fact["pointer"]):
            observed[(fact["report_id"], pointer)] = value
    failures = []
    for report_id, required in case["required_facts"].items():
        for pointer, expected in required.items():
            pair = report_id, pointer
            if pair not in observed:
                failures.append(
                    {"report_id": report_id, "pointer": pointer, "reason": "missing"}
                )
            elif json.dumps(observed[pair], sort_keys=True) != json.dumps(
                expected, sort_keys=True
            ):
                failures.append(
                    {
                        "report_id": report_id,
                        "pointer": pointer,
                        "reason": "wrong_value",
                    }
                )
    verdict_correct = (
        type(assessment.get("claim_supported")) is bool
        and assessment["claim_supported"] is case["expected_supported"]
    )
    return {
        "evidence_verified": result.get("evidence_verified", False),
        "verdict_correct": verdict_correct,
        "required_fact_failures": failures,
        "case_passed": bool(
            result.get("evidence_verified") and verdict_correct and not failures
        ),
        "free_prose_semantics_verified": False,
        "scope": "Known fixed query; structured verdict, exact fact coverage and source/read lineage only",
    }


async def main():
    from benchmarks.llamaindex_evidence_agent import audit

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "--strategy", choices=["two_step", "submit_tool"], default="two_step"
    )
    args = parser.parse_args()
    case = next(c for c in json.loads(args.cases.read_text()) if c["id"] == args.case)
    args.state_dir.mkdir(exist_ok=False)
    result = await audit(
        args.root,
        args.root / "catalog.json",
        args.state_dir / "journal",
        case["question"],
        base_url=args.base_url,
        model=args.model,
        owner_sha256=args.owner,
        timeout=args.timeout,
        max_requests=8,
        max_iterations=7,
        strategy=args.strategy,
    )
    result["grading"] = grade_case(result, case)
    (args.state_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "case": case["id"],
                "grading": result["grading"],
                "tool_calls": len(result["tool_trace"]),
                "error_type": result.get("error", {}).get("type"),
            }
        )
    )
    raise SystemExit(0 if result["grading"]["case_passed"] else 2)


if __name__ == "__main__":
    asyncio.run(main())
