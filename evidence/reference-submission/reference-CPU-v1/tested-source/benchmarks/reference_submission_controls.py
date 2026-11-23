"""Source-bound submissions through actual MCP tools and scripted model replies."""

import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from benchmarks.mcp_agent_controls import run_case


async def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--code", type=Path, required=True)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--mcp-url", required=True)
    p.add_argument("--owner", required=True)
    args = p.parse_args()
    args.state.mkdir(exist_ok=False)
    rows = []
    for scenario in ["normal", "forged_fact", "unread_submission", "plain_answer"]:
        row = await run_case(args, scenario, submission_mode="references")
        assert row["submission_schema_fields"] == [
            "claim_supported",
            "explanation",
            "facts",
        ]
        result = json.loads((args.state / (scenario + "-result.json")).read_text())
        if scenario == "normal":
            assert len(result["assessment"]["citations"]) == 1
            assert result["verification"]["verification"]["facts"] == 7
        rows.append(row)
    extra = args.state / "unused-read"
    extra.mkdir()
    extra_args = SimpleNamespace(
        code=args.code, state=extra, mcp_url=args.mcp_url, owner=args.owner
    )
    row = await run_case(
        extra_args,
        "normal",
        submission_mode="references",
        additional_reads=[
            {"report_id": "historical_core", "pointers": ["/full_suite_passed"]}
        ],
    )
    result = json.loads((extra / "normal-result.json").read_text())
    assert len(result["receipts_received"]) == 2
    assert [c["report_id"] for c in result["assessment"]["citations"]] == ["patch_move"]
    rows.append({"scenario": "unused_read_not_cited", **row})
    report = {
        "cases": rows,
        "passed": len(rows),
        "neural_calls": 0,
        "scripted_model_POSTs": sum(r["fake_model_posts"] for r in rows),
    }
    (args.state / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    asyncio.run(main())
