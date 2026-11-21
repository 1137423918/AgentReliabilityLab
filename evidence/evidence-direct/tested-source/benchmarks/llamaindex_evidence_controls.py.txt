"""Explicitly fake HTTP controls for the real LlamaIndex report-audit workflow."""

import argparse
import asyncio
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from benchmarks.llamaindex_evidence_agent import audit


async def run_control(
    code, root, owner, corrupt=False, strategy="two_step", scenario="normal"
):
    corpus = code / "corpus"
    manifest = json.loads((corpus / "catalog.json").read_text())
    entries = {x["id"]: x for x in manifest["reports"]}
    facts = [
        {"report_id": "core_current", "pointer": "/full_suite_passed", "value": 116},
        {"report_id": "patch_move", "pointer": "/related_suite_passed", "value": 203},
        {"report_id": "patch_move", "pointer": "/focused_passed", "value": 22},
        {
            "report_id": "patch_move",
            "pointer": "/overlapping_suites_not_added",
            "value": True,
        },
    ]
    if corrupt:
        facts[0]["value"] = True
    if scenario == "unread_fact":
        facts.append(
            {"report_id": "core_current", "pointer": "/full_suite_skipped", "value": 0}
        )
    assessment = {
        "claim_supported": False,
        "explanation": "These are distinct scopes and overlapping subsets.",
        "facts": facts,
        "citations": [
            {"report_id": name, "sha256": entries[name]["sha256"]}
            for name in ["core_current", "patch_move"]
        ],
    }
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
                index = len(bodies)
                assert body["messages"][0]["role"] == "system"
                if strategy == "submit_tool":
                    names = [t["function"]["name"] for t in body["tools"]]
                    assert names == ["list_reports", "read_report", "submit_assessment"]
                    schema = body["tools"][2]["function"]["parameters"]
                    assert set(schema["required"]) == {
                        "claim_supported",
                        "explanation",
                        "facts",
                        "citations",
                    }
                if index == 1:
                    name, args = "list_reports", {}
                elif index == 2:
                    name, args = (
                        "read_report",
                        {
                            "report_id": "core_current",
                            "pointers": ["/full_suite_passed"],
                        },
                    )
                elif index == 3:
                    name, args = (
                        "read_report",
                        {
                            "report_id": "patch_move",
                            "pointers": [
                                "/related_suite_passed",
                                "/focused_passed",
                                "/overlapping_suites_not_added",
                            ],
                        },
                    )
                elif index == 4:
                    if strategy == "submit_tool" and scenario != "plain_answer":
                        name, args = "submit_assessment", assessment
                    else:
                        name, args = None, None
                elif index == 5:
                    assert len(body["tools"]) == 1
                    name = body["tools"][0]["function"]["name"]
                    assert name == "AuditAssessment"
                    args = assessment
                else:
                    raise AssertionError("Unexpected extra model attempt")
                message = {
                    "role": "assistant",
                    "content": "The claim is unsupported; use the observed report fields.",
                }
                if name:
                    message.update(
                        content=None,
                        tool_calls=[
                            {
                                "id": "fake-call-" + str(index),
                                "type": "function",
                                "function": {
                                    "name": name,
                                    "arguments": json.dumps(args),
                                },
                            }
                        ],
                    )
                payload = {
                    "id": "explicit-fake-" + str(index),
                    "object": "chat.completion",
                    "created": 0,
                    "model": "explicit-fake-evidence",
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
                encoded = json.dumps(payload).encode()
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
    case = "forged_fact" if corrupt else scenario
    if strategy == "submit_tool":
        case = "direct_" + case
    try:
        result = await audit(
            corpus,
            corpus / "catalog.json",
            root / case,
            "Audit whether core and related/focused tests can be added into one core total.",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            model="explicit-fake-evidence",
            owner_sha256=owner,
            timeout=90,
            strategy=strategy,
        )
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=5)
    assert not errors, errors
    expected_posts = 4 if strategy == "submit_tool" else 5
    assert len(bodies) == expected_posts, result
    rejected = corrupt or scenario in {"unread_fact", "plain_answer"}
    assert result["evidence_verified"] is not rejected, result
    if rejected:
        assert result["error"]["type"] == "EvidenceError"
    else:
        assert result["verification"]["facts"] == 4
    journal = json.loads((root / case / "model-requests.json").read_text())
    assert len(journal["reservations"]) == len(bodies)
    for row, raw in zip(journal["reservations"], bodies):
        assert row["request_body_sha256"] == hashlib.sha256(raw).hexdigest()
        assert row["request_body_bytes"] == len(raw) and row["http_status"] == 200
    result.update(
        explicit_fake_model=True,
        neural_requests=0,
        actual_http_posts=len(bodies),
        full_request_bodies_matched_journal=True,
    )
    (root / (case + "-result.json")).write_text(json.dumps(result, indent=2) + "\n")
    return {
        "case": case,
        "passed": True,
        "evidence_verified": result["evidence_verified"],
        "http_posts": len(bodies),
        "tool_calls": len(result["tool_trace"]),
    }


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--owner", required=True)
    args = parser.parse_args()
    args.state.mkdir(exist_ok=False)
    rows = [
        await run_control(args.code, args.state, args.owner, corrupt=False),
        await run_control(args.code, args.state, args.owner, corrupt=True),
        await run_control(args.code, args.state, args.owner, strategy="submit_tool"),
        await run_control(
            args.code, args.state, args.owner, corrupt=True, strategy="submit_tool"
        ),
        await run_control(
            args.code,
            args.state,
            args.owner,
            strategy="submit_tool",
            scenario="unread_fact",
        ),
        await run_control(
            args.code,
            args.state,
            args.owner,
            strategy="submit_tool",
            scenario="plain_answer",
        ),
    ]
    (args.state / "report.json").write_text(
        json.dumps(
            {"cases": rows, "explicit_fake_model": True, "real_neural_requests": 0},
            indent=2,
        )
        + "\n"
    )
    print(json.dumps({"cases": rows, "real_neural_requests": 0}))


if __name__ == "__main__":
    asyncio.run(main())
