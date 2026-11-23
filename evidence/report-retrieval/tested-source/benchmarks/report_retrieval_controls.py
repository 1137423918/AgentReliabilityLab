"""Real MCP/FunctionAgent controls; only model replies are scripted."""

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
    question = "Audit the OpenHands same-path patch move: verify the related and focused tests, new failures and neural requests."
    rows = []
    for name, queries in [
        ("ranked", None),
        ("full_fallback", ["*"]),
        ("zero_match_then_full", ["zzzzunmatchedtoken", "*"]),
    ]:
        state = args.state / name
        state.mkdir()
        call_args = SimpleNamespace(
            code=args.code, state=state, mcp_url=args.mcp_url, owner=args.owner
        )
        row = await run_case(
            call_args,
            "normal",
            catalog_policy="bm25",
            question=question,
            listing_queries=queries,
        )
        result = json.loads((state / "normal-result.json").read_text())
        ranked = [t for t in result["tool_trace"] if t["tool"] == "rank_report_catalog"]
        assert result["evidence_verified"] and result["mcp_close"] == {"closed": True}
        if name == "ranked":
            assert len(ranked) == 1 and "patch_move" in ranked[0]["selected_ids"]
        elif name == "full_fallback":
            assert not ranked
        else:
            assert len(ranked) == 1 and ranked[0]["selected_ids"] == []
        rows.append({"scenario": name, **row, "ranked_catalog_events": ranked})
    out = {
        "scenarios": rows,
        "passed": len(rows),
        "neural_requests": 0,
        "scripted_model": True,
    }
    (args.state / "report.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out))


if __name__ == "__main__":
    asyncio.run(main())
