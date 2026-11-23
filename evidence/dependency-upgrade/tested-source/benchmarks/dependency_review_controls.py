"""Real MCP/FunctionAgent controls for upgrade reviews, with scripted LLM replies."""

import argparse
import asyncio
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

from benchmarks.evidence_audit_case import grade_case
from benchmarks.llamaindex_mcp_audit import audit_via_mcp


async def control(args, case, scenario, other=None):
    identifier = case["id"] + "-" + scenario
    data_case = other if scenario == "wrong_project" else case
    report_id, fields = next(iter(data_case["required_facts"].items()))
    supported = case["expected_supported"]
    assessment = {
        "claim_supported": not supported if scenario == "wrong_verdict" else supported,
        "explanation": "Scripted transport/grading control, not a neural model result.",
        "facts": [{"report_id": report_id, "pointer": pointer} for pointer in fields],
    }
    plan = [
        ("list_reports", {}),
        ("read_report", {"report_id": report_id, "pointers": list(fields)}),
        ("submit_assessment", assessment),
    ]
    bodies, errors = [], []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                body = json.loads(raw)
                bodies.append(raw)
                index = len(bodies) - 1
                assert index < len(plan), "Unexpected model retry or formatting call"
                assert [t["function"]["name"] for t in body["tools"]] == [
                    "list_reports",
                    "read_report",
                    "submit_assessment",
                ]
                assert set(
                    body["tools"][2]["function"]["parameters"]["properties"]
                ) == {"claim_supported", "explanation", "facts"}
                name, payload = plan[index]
                encoded = json.dumps(
                    {
                        "id": "scripted-" + str(index),
                        "object": "chat.completion",
                        "created": 0,
                        "model": "explicit-fake-dependency-review",
                        "choices": [
                            {
                                "index": 0,
                                "finish_reason": "tool_calls",
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "scripted-" + str(index),
                                            "type": "function",
                                            "function": {
                                                "name": name,
                                                "arguments": json.dumps(payload),
                                            },
                                        }
                                    ],
                                },
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
    directory = args.state / identifier
    try:
        result = await audit_via_mcp(
            args.mcp_url,
            directory,
            case["question"],
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            model="explicit-fake-dependency-review",
            owner_sha256=args.owner,
            timeout=120,
            submission_mode="references",
        )
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=5)
    assert not errors, errors
    assert len(bodies) == 3 and result["evidence_verified"]
    assert result["mcp_close"] == {"closed": True}
    grading = grade_case(result, case)
    assert grading["case_passed"] is (scenario == "normal"), grading
    if scenario == "wrong_project":
        assert grading["required_fact_failures"]
    elif scenario == "wrong_verdict":
        assert not grading["verdict_correct"] and not grading["required_fact_failures"]
    journal = json.loads((directory / "model-requests.json").read_text())
    assert len(journal["reservations"]) == len(bodies)
    for reservation, raw in zip(journal["reservations"], bodies):
        assert reservation["request_body_sha256"] == hashlib.sha256(raw).hexdigest()
        assert (
            reservation["request_body_bytes"] == len(raw)
            and reservation["http_status"] == 200
        )
        assert result["mcp_context"]["audit_id"].encode() not in raw
        assert all(
            receipt.encode() not in raw for receipt in result["receipts_received"]
        )
    # Full private result includes capability/receipt material and is not the public control summary.
    (args.state / (identifier + "-private-result.json")).write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return {
        "case": case["id"],
        "scenario": scenario,
        "control_passed": True,
        "evidence_verified": True,
        "grading": grading,
        "MCP_closed": True,
        "scripted_model_POSTs": len(bodies),
        "actual_model_requests": 0,
        "journal_body_hashes_match": True,
        "capabilities_excluded_from_model_requests": True,
    }


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--mcp-url", required=True)
    parser.add_argument("--owner", required=True)
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text())
    assert len(cases) == 2
    args.state.mkdir()
    rows = [await control(args, case, "normal") for case in cases]
    rows.append(await control(args, cases[0], "wrong_project", other=cases[1]))
    rows.append(await control(args, cases[0], "wrong_verdict"))
    report = {
        "cases": rows,
        "control_scenarios_passed": len(rows),
        "scripted_model_POSTs": sum(r["scripted_model_POSTs"] for r in rows),
        "neural_requests": 0,
        "scope": "Real MCP/TCP/FunctionAgent and canonical source binding/grading; explicitly scripted model replies, not task accuracy.",
    }
    (args.state / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    asyncio.run(main())
