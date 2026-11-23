"""Real MCP/TCP process-death controls with explicitly scripted model replies."""

import argparse
import asyncio
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
import uvicorn

from benchmarks.llamaindex_mcp_audit import audit_via_mcp, call_tool
from benchmarks.mcp_cleanup_controls import FaultBoundary
from benchmarks.mcp_evidence_server import create_app


async def child(args):
    result = await audit_via_mcp(
        args.mcp_url, args.state / "journal", "Read the pinned patch_move report.",
        base_url=args.base_url, model="explicit-wire-control", owner_sha256=args.owner,
        timeout=120,
    )
    (args.state / "unexpected-result.json").write_text(json.dumps(result) + "\n")


async def killed_agent(args):
    """Hold the third POST in flight; kill only the spawned agent process."""
    args.state.mkdir(exist_ok=False)
    reached = threading.Event()
    release = threading.Event()
    bodies, replies, errors = [], [], []
    key = os.urandom(24).hex()
    plan = [
        ("list_reports", {}),
        ("read_report", {"report_id": "patch_move", "pointers": ["/related_suite_passed"]}),
    ]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *unused):
            pass

        def do_POST(self):
            try:
                assert self.headers.get("Authorization") == "Bearer " + key
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                bodies.append(raw)
                index = len(bodies) - 1
                assert index <= 2, "Unexpected retry"
                if index == 2:
                    reached.set()
                    release.wait(30)
                    return  # No HTTP headers/body for this deliberately unknown request.
                name, arguments = plan[index]
                value = {
                    "id": "explicit-wire-control-" + str(index), "object": "chat.completion",
                    "created": 0, "model": "explicit-wire-control",
                    "choices": [{"index": 0, "message": {
                        "role": "assistant", "content": None,
                        "tool_calls": [{"id": "control-" + str(index), "type": "function",
                                        "function": {"name": name, "arguments": json.dumps(arguments)}}],
                    }, "finish_reason": "tool_calls"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
                encoded = json.dumps(value).encode()
                replies.append(encoded)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except Exception as exc:
                errors.append(type(exc).__name__)
                self.send_error(500)

    app = FaultBoundary(create_app(args.code / "corpus", args.code / "corpus/catalog.json"), "wire")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    model = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    model.daemon_threads = True
    thread = threading.Thread(target=model.serve_forever, daemon=True)
    thread.start()
    process = None
    report = {"scenario": "SIGKILL_after_two_bodies_during_third_POST", "passed": False,
              "explicit_scripted_model": True, "neural_requests": 0, "GPU_used": False}
    started = time.monotonic()
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if serving.done():
                    await serving
                    raise AssertionError("MCP server exited before startup")
                await asyncio.sleep(0.01)
        env = dict(os.environ, AGENT_LAB_EVIDENCE_KEY=key)
        with (args.state / "child.log").open("wb") as log:
            process = subprocess.Popen([
                sys.executable, "-m", "benchmarks.mcp_wire_controls", "--child",
                "--state", str(args.state), "--owner", args.owner,
                "--mcp-url", f"http://127.0.0.1:{port}/mcp",
                "--base-url", f"http://127.0.0.1:{model.server_port}/v1",
            ], env=env, stdout=log, stderr=subprocess.STDOUT)
            async with asyncio.timeout(90):
                while not reached.is_set():
                    if process.poll() is not None:
                        raise AssertionError("Agent exited before third controlled POST")
                    await asyncio.sleep(0.02)
            os.kill(process.pid, signal.SIGKILL)
            rc = await asyncio.to_thread(process.wait, 10)
        assert rc == -signal.SIGKILL and len(bodies) == 3 and len(replies) == 2 and not errors
        assert len(app.handles) == 1 and app.calls.count("read_report") == 1
        assert app.calls.count("close_audit") == 0
        budget_path = args.state / "journal/model-requests.json"
        before = hashlib.sha256(budget_path.read_bytes()).hexdigest()
        budget = json.loads(budget_path.read_text())
        attempts = budget["reservations"]
        assert len(attempts) == 3 and [x["http_status"] for x in attempts] == [200, 200, None]
        assert not (args.state / "unexpected-result.json").exists()
        path = args.state / "journal/wire-events.jsonl"
        report.update(agent_returncode=rc, model_attempts=3, model_complete_reply_bodies=2,
                      budget_unknown_still_charged=1, result_file_exists=False,
                      durable_trace_exists=path.exists(), child_close_calls_before_kill=0)
        if path.exists():
            from agent_lab.wire_journal import read_wire_journal

            recovered = read_wire_journal(path, args.owner, budget["identity"]["journal_id"])
            events = recovered["events"]
            requests = [x for x in events if x["channel"] == "model" and x["kind"] == "client_request_attempt"]
            responses = [x for x in events if x["channel"] == "model" and x["kind"] == "client_response"]
            assert len(requests) == 3 and len(responses) == 2 and recovered["tail_bytes"] == 0
            assert [base64.b64decode(x["body_base64"]) for x in requests] == bodies
            assert [base64.b64decode(x["body_base64"]) for x in responses] == replies
            assert key.encode() not in path.read_bytes() and path.stat().st_mode & 0o777 == 0o600
            mcp_reads = []
            for event in events:
                if event["channel"] != "mcp" or event["kind"] != "client_request_attempt":
                    continue
                body = json.loads(base64.b64decode(event["body_base64"]))
                if body.get("method") == "tools/call":
                    mcp_reads.append(body["params"]["name"])
            assert mcp_reads.count("read_report") == 1
            report.update(passed=True, recovered_events=len(events), recovered_model_requests=3,
                          recovered_complete_model_bodies=2, recovered_read_report_requests=1,
                          response_body_hashes=[hashlib.sha256(b).hexdigest() for b in replies],
                          synthetic_authorization_key_absent=True, journal_mode="0600")
        else:
            report["failure"] = "Complete wire bodies were memory-only and disappeared with SIGKILL"
        assert hashlib.sha256(budget_path.read_bytes()).hexdigest() == before
        report["budget_unchanged_by_recovery"] = True
        async with httpx2.AsyncClient(trust_env=False, timeout=5) as http:
            async with Client(streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=http), cache=None) as remote:
                closed = await call_tool(remote, "close_audit", {"audit_id": app.handles[0]})
                assert closed == {"closed": True}
        report["operator_closed_abandoned_context"] = True
        report["agent_close_confirmed"] = False
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            await asyncio.to_thread(process.wait, 10)
        release.set()
        await asyncio.to_thread(model.shutdown)
        model.server_close()
        thread.join(timeout=5)
        server.should_exit = True
        await asyncio.wait_for(serving, timeout=10)
        sock.close()
        report.update(wall_seconds=round(time.monotonic() - started, 3), server_terminal=serving.done())
        (args.state / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)
    return 0 if report["passed"] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--code", type=Path)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--mcp-url")
    parser.add_argument("--base-url")
    args = parser.parse_args()
    return asyncio.run(child(args) if args.child else killed_agent(args))


if __name__ == "__main__":
    raise SystemExit(main())
