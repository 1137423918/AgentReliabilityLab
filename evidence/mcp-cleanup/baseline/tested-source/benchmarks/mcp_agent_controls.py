"""Explicitly scripted model replies with real LlamaIndex/MCP SDKs and TCP tools."""

import argparse
import asyncio
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

from benchmarks.llamaindex_mcp_audit import audit_via_mcp


async def run_case(args, scenario):
    catalog = json.loads(
        (args.code / "corpus/catalog.json").read_text(encoding="utf-8")
    )
    entry = next(x for x in catalog["reports"] if x["id"] == "patch_move")
    document = json.loads(
        (args.code / "corpus" / entry["path"]).read_text(encoding="utf-8")
    )
    pointers = [
        "/baseline_new_checks_failed",
        "/related_suite_passed",
        "/focused_passed",
        "/new_checks_included",
        "/real_public_executor",
        "/neural_requests",
        "/overlapping_suites_not_added",
    ]
    facts = [
        {"report_id": "patch_move", "pointer": p, "value": document[p[1:]]}
        for p in pointers
    ]
    if scenario == "forged_fact":
        facts[1]["value"] = True
    assessment = {
        "claim_supported": True,
        "explanation": "Fixed data for explicitly scripted integration control.",
        "facts": facts,
        "citations": [{"report_id": "patch_move", "sha256": entry["sha256"]}],
    }
    plan = [
        ("list_reports", {}),
        ("read_report", {"report_id": "patch_move", "pointers": pointers}),
        ("submit_assessment", assessment),
    ]
    if scenario == "unread_submission":
        plan = [plan[0], plan[-1]]
    if scenario == "plain_answer":
        plan = [(None, None)]
    bodies = []
    errors = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                body = json.loads(raw)
                bodies.append(raw)
                index = len(bodies) - 1
                assert [x["function"]["name"] for x in body["tools"]] == [
                    "list_reports",
                    "read_report",
                    "submit_assessment",
                ]
                assert index < len(plan), "Unexpected model retry/extra formatting call"
                name, payload = plan[index]
                message = {
                    "role": "assistant",
                    "content": "A free-text answer is not a verified submission.",
                }
                if name:
                    message.update(
                        content=None,
                        tool_calls=[
                            {
                                "id": "scripted-" + str(index),
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(payload),
                                },
                            }
                        ],
                    )
                encoded = json.dumps(
                    {
                        "id": "scripted-" + str(index),
                        "object": "chat.completion",
                        "created": 0,
                        "model": "explicit-fake-mcp-agent",
                        "choices": [
                            {
                                "index": 0,
                                "message": message,
                                "finish_reason": "tool_calls" if name else "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 1,
                            "completion_tokens": 1,
                            "total_tokens": 2,
                        },
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except Exception as exc:
                errors.append(type(exc).__name__ + ":" + str(exc))
                self.send_error(500)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = await audit_via_mcp(
            args.mcp_url,
            args.state / scenario,
            "Check the fixed report facts in this integration control.",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            model="explicit-fake-mcp-agent",
            owner_sha256=args.owner,
            timeout=120,
        )
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=5)
    (args.state / (scenario + "-result.json")).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    assert not errors, errors
    assert len(bodies) == len(plan), result
    assert result["evidence_verified"] == (scenario == "normal"), result
    if scenario != "normal":
        assert result["error"]["type"] == "EvidenceError", result
    assert result["mcp_close"] == {"closed": True}, result
    journal = json.loads(
        (args.state / scenario / "model-requests.json").read_text(encoding="utf-8")
    )
    assert len(journal["reservations"]) == len(plan)
    for row, raw in zip(journal["reservations"], bodies):
        assert (
            row["request_body_sha256"] == hashlib.sha256(raw).hexdigest()
            and row["request_body_bytes"] == len(raw)
            and row["http_status"] == 200
        )
    for raw in bodies:
        assert result["mcp_context"]["audit_id"].encode() not in raw
        for receipt in result["receipts_received"]:
            assert receipt.encode() not in raw
    result.update(
        explicit_fake_model=True,
        neural_requests=0,
        actual_fake_model_posts=len(bodies),
        fake_bodies_match_journal=True,
        capabilities_and_receipts_absent_from_model_requests=True,
    )
    (args.state / (scenario + "-result.json")).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "case": scenario,
        "passed": True,
        "backend_evidence_verified": result["evidence_verified"],
        "fake_model_posts": len(bodies),
        "mcp_context_closed": True,
    }


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
        rows.append(await run_case(args, scenario))
    (args.state / "report.json").write_text(
        json.dumps(
            {"cases": rows, "explicit_fake_model": True, "neural_requests": 0}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"cases": rows, "neural_requests": 0}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
