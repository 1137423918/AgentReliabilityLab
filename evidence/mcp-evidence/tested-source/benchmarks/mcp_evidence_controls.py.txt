"""Real MCP/HTTP lifecycle controls on public reports; no model or fake replies.

The response gate below is a benchmark-only network fault fixture, not part of
the product app. It withholds a completed read response until the client cancels.
"""

import argparse
import asyncio
import base64
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
import uvicorn

from benchmarks.mcp_evidence_server import create_app


class ResponseGate:
    """Hold one actual read-result body while allowing a release/status channel."""

    def __init__(self, app):
        self.app = app
        self.entered = False
        self.released = asyncio.Event()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["path"].startswith("/test-gate/"):
            if scope["path"].endswith("/release"):
                self.released.set()
            data = json.dumps({"entered": self.entered}).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            return await send({"type": "http.response.body", "body": data})
        headers = dict(scope.get("headers", []))
        if headers.get(b"x-evidence-test-gate") != b"cancel-read":
            return await self.app(scope, receive, send)
        messages = []
        body = b""
        while True:
            message = await receive()
            messages.append(message)
            body += message.get("body", b"")
            if not message.get("more_body", False):
                break
        try:
            request = json.loads(body)
        except ValueError:
            request = {}
        target = (
            request.get("method") == "tools/call"
            and request.get("params", {}).get("name") == "read_report"
            and not self.entered
        )

        async def replay():
            return messages.pop(0) if messages else await receive()

        async def gated_send(message):
            if (
                target
                and message["type"] == "http.response.body"
                and b"receipt" in message.get("body", b"")
            ):
                self.entered = True
                await self.released.wait()
            await send(message)

        await self.app(scope, replay, gated_send)


async def run_controls(args):
    state = args.state
    state.mkdir(exist_ok=False)
    wire = []
    cases = []
    servers = []
    owned = []
    current = None

    async def request_hook(request):
        raw = await request.aread()
        wire.append(
            {
                "kind": "client_request_attempt",
                "method": request.method,
                "path": request.url.path,
                "protocol_version": request.headers.get("mcp-protocol-version"),
                "body_base64": base64.b64encode(raw).decode(),
                "body_bytes": len(raw),
                "body_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )

    async def response_hook(response):
        wire.append(
            {
                "kind": "response_headers",
                "status": response.status_code,
                "request_body_sha256": hashlib.sha256(
                    response.request.content
                ).hexdigest(),
            }
        )
        raw = await response.aread()
        wire.append(
            {
                "kind": "client_response",
                "status": response.status_code,
                "request_body_sha256": hashlib.sha256(
                    response.request.content
                ).hexdigest(),
                "body_base64": base64.b64encode(raw).decode(),
                "body_bytes": len(raw),
                "body_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )

    url = f"http://127.0.0.1:{args.port}"

    @asynccontextmanager
    async def client(gated=False):
        headers = {"x-evidence-test-gate": "cancel-read"} if gated else {}
        async with httpx2.AsyncClient(
            headers=headers,
            trust_env=False,
            follow_redirects=False,
            timeout=10,
            event_hooks={"request": [request_hook], "response": [response_hook]},
        ) as http:
            async with Client(
                streamable_http_client(url + "/mcp", http_client=http), cache=None
            ) as c:
                listing = await c.list_tools()
                assert sorted(t.name for t in listing.tools) == [
                    "audit_status",
                    "begin_audit",
                    "close_audit",
                    "list_reports",
                    "read_report",
                    "verify_assessment",
                ]
                yield c

    async def tool(c, name, params=None, error=False):
        result = await c.call_tool(name, params or {})
        assert bool(result.is_error) == error, (name, result.model_dump(mode="json"))
        return result.model_dump(mode="json") if error else result.structured_content

    def assessment(value=116, pointer="/full_suite_passed"):
        catalog = json.loads((args.root / "catalog.json").read_text(encoding="utf-8"))
        row = next(x for x in catalog["reports"] if x["id"] == "core_current")
        return {
            "claim_supported": True,
            "explanation": "Exact field from the fixed historical catalog.",
            "facts": [
                {"report_id": "core_current", "pointer": pointer, "value": value}
            ],
            "citations": [{"report_id": "core_current", "sha256": row["sha256"]}],
        }

    def save(name, data):
        cases.append({"case": name, "passed": True, **data})
        (state / (name + ".json")).write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps({"case": name, "passed": True}), flush=True)

    async def start(gated):
        with socket.socket() as sock:
            assert sock.connect_ex(("127.0.0.1", args.port)) != 0
        label = "gated" if gated else "plain"
        log = (state / (label + "-server.log")).open("wb")
        command = (
            [sys.executable, "-m", "benchmarks.mcp_evidence_controls", "--serve-gated"]
            if gated
            else [sys.executable, "-m", "benchmarks.mcp_evidence_server"]
        )
        command += [
            "--root",
            str(args.root),
            "--manifest",
            str(args.root / "catalog.json"),
            "--port",
            str(args.port),
        ]
        p = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        owned.append(p)
        log.close()
        servers.append({"mode": label, "pid": p.pid})
        deadline = time.monotonic() + 90
        async with httpx2.AsyncClient(trust_env=False, timeout=2) as h:
            while True:
                if p.poll() is not None:
                    raise RuntimeError("Server exited before health")
                try:
                    response = await h.get(url + "/health")
                    if response.status_code == 200:
                        break
                except (httpx2.ConnectError, httpx2.ReadTimeout):
                    pass
                if time.monotonic() > deadline:
                    raise TimeoutError("Server health deadline")
                await asyncio.sleep(0.1)
        return p

    def stop(p):
        forced = False
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=25)
            except subprocess.TimeoutExpired:
                forced = True
                p.kill()
                p.wait(timeout=5)
        if p is not None:
            row = next(x for x in servers if x["pid"] == p.pid)
            row["returncode"] = p.returncode
            row["forced_kill"] = row.get("forced_kill", False) or forced

    try:
        current = await start(False)
        async with client() as c:
            a = (await tool(c, "begin_audit"))["audit_id"]
            listing = await tool(c, "list_reports", {"audit_id": a})
            assert len(listing["reports"]) == 8
            read = await tool(
                c,
                "read_report",
                {
                    "audit_id": a,
                    "report_id": "core_current",
                    "pointers": ["/full_suite_passed"],
                },
            )
            verified = await tool(
                c,
                "verify_assessment",
                {
                    "audit_id": a,
                    "assessment": assessment(),
                    "receipts": [read["receipt"]],
                },
            )
            assert (
                verified["evidence_verified"]
                and not verified["verdict_truth_verified"]
                and not verified["free_prose_semantics_verified"]
            )
            save(
                "normal",
                {
                    "listing": listing,
                    "read": read,
                    "verification": verified,
                    "status": await tool(c, "audit_status", {"audit_id": a}),
                },
            )
            b = (await tool(c, "begin_audit"))["audit_id"]
            own = await tool(
                c,
                "read_report",
                {
                    "audit_id": b,
                    "report_id": "core_current",
                    "pointers": ["/full_suite_passed"],
                },
            )
            rejected = await tool(
                c,
                "verify_assessment",
                {
                    "audit_id": b,
                    "assessment": assessment(),
                    "receipts": [read["receipt"]],
                },
                error=True,
            )
            accepted = await tool(
                c,
                "verify_assessment",
                {
                    "audit_id": b,
                    "assessment": assessment(),
                    "receipts": [own["receipt"]],
                },
            )
            save(
                "receipt_isolation",
                {
                    "foreign_receipt_rejected": rejected,
                    "own_receipt_accepted": accepted,
                },
            )
            bad = (await tool(c, "begin_audit"))["audit_id"]
            errors = []
            for report, pointers in [
                ("../report.json", ["/full_suite_passed"]),
                ("core_current", [""]),
            ]:
                errors.append(
                    await tool(
                        c,
                        "read_report",
                        {"audit_id": bad, "report_id": report, "pointers": pointers},
                        error=True,
                    )
                )
            row = await tool(
                c,
                "read_report",
                {
                    "audit_id": bad,
                    "report_id": "core_current",
                    "pointers": ["/full_suite_passed"],
                },
            )
            errors.append(
                await tool(
                    c,
                    "verify_assessment",
                    {
                        "audit_id": bad,
                        "assessment": assessment(True),
                        "receipts": [row["receipt"]],
                    },
                    error=True,
                )
            )
            protocol = next(
                x["protocol_version"]
                for x in reversed(wire)
                if x.get("protocol_version")
            )
            async with httpx2.AsyncClient(trust_env=False, timeout=10) as h:
                oversized = await h.post(
                    url + "/mcp",
                    headers={
                        "mcp-protocol-version": protocol,
                        "accept": "application/json, text/event-stream",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": "oversize",
                        "method": "tools/call",
                        "params": {
                            "name": "read_report",
                            "arguments": {
                                "audit_id": bad,
                                "report_id": "core_current",
                                "pointers": ["x" * 17000],
                            },
                        },
                    },
                )
            assert oversized.status_code == 413
            counter = await tool(c, "audit_status", {"audit_id": bad})
            assert counter["operations_spent"] == 4 and counter["reads_completed"] == 1
            save(
                "rejections",
                {
                    "errors": errors,
                    "oversize_http_status": oversized.status_code,
                    "counter": counter,
                },
            )
            quota = (await tool(c, "begin_audit"))["audit_id"]
            for _ in range(15):
                await tool(c, "list_reports", {"audit_id": quota})
            raced = await asyncio.gather(
                *(c.call_tool("list_reports", {"audit_id": quota}) for _ in range(6))
            )
            assert sum(not x.is_error for x in raced) == 1
            counter = await tool(c, "audit_status", {"audit_id": quota})
            assert counter["operations_spent"] == 16
            closed = await tool(c, "close_audit", {"audit_id": quota})
            save(
                "concurrent_cap",
                {
                    "successful_of_six": 1,
                    "rejected_of_six": 5,
                    "counter": counter,
                    "close_after_exhaustion": closed,
                },
            )
        async with client() as c:
            reused = await tool(
                c,
                "verify_assessment",
                {
                    "audit_id": a,
                    "assessment": assessment(),
                    "receipts": [read["receipt"]],
                },
            )
            counter = await tool(c, "audit_status", {"audit_id": a})
            assert counter["operations_spent"] == 4
            save(
                "reconnect",
                {
                    "same_capability_still_charged": counter,
                    "verification": reused,
                    "capability_sharing_is_not_user_authentication": True,
                },
            )
        stop(current)
        assert current.returncode in (0, -15, 143) and not servers[-1]["forced_kill"]
        current = None
        current = await start(True)
        async with client(True) as c:
            old_rejected = await tool(c, "audit_status", {"audit_id": a}, error=True)
            handle = (await tool(c, "begin_audit"))["audit_id"]
            task = asyncio.create_task(
                c.call_tool(
                    "read_report",
                    {
                        "audit_id": handle,
                        "report_id": "core_current",
                        "pointers": ["/full_suite_skipped"],
                    },
                )
            )
            async with httpx2.AsyncClient(trust_env=False, timeout=5) as h:
                try:
                    async with asyncio.timeout(20):
                        while not (await h.get(url + "/test-gate/status")).json()[
                            "entered"
                        ]:
                            await asyncio.sleep(0.05)
                    task.cancel()
                    try:
                        await asyncio.wait_for(task, 5)
                    except asyncio.CancelledError:
                        pass
                    else:
                        raise AssertionError("Read returned despite held body")
                finally:
                    await h.post(url + "/test-gate/release")
        async with client() as c:
            before = await tool(c, "audit_status", {"audit_id": handle})
            assert before["operations_spent"] == 1 and before["reads_completed"] == 1
            rejected = await tool(
                c,
                "verify_assessment",
                {
                    "audit_id": handle,
                    "assessment": assessment(0, "/full_suite_skipped"),
                    "receipts": [],
                },
                error=True,
            )
            row = await tool(
                c,
                "read_report",
                {
                    "audit_id": handle,
                    "report_id": "core_current",
                    "pointers": ["/full_suite_skipped"],
                },
            )
            verified = await tool(
                c,
                "verify_assessment",
                {
                    "audit_id": handle,
                    "assessment": assessment(0, "/full_suite_skipped"),
                    "receipts": [row["receipt"]],
                },
            )
            after = await tool(c, "audit_status", {"audit_id": handle})
            assert after["operations_spent"] == 4 and after["reads_completed"] == 2
            save(
                "cancel_unknown",
                {
                    "prior_server_capability_invalidated": old_rejected,
                    "held_body_canceled": True,
                    "before_reread": before,
                    "missing_receipt_rejected": rejected,
                    "reread": row,
                    "verification": verified,
                    "after_reread": after,
                    "fixture": "Actual response body withheld after receipt production; no synthetic tool response",
                },
            )
    finally:
        for p in owned:
            stop(p)
        with socket.socket() as sock:
            port_closed = sock.connect_ex(("127.0.0.1", args.port)) != 0
        report = {
            "cases": cases,
            "wire_events": wire,
            "server_lifetimes": servers,
            "port_closed": port_closed,
            "model_requests": 0,
            "synthetic_replies": False,
            "fault_fixture_only_in_benchmark": True,
        }
        (state / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    assert (
        len(cases) == 6
        and port_closed
        and all(
            x["returncode"] in (0, -15, 143) and not x["forced_kill"] for x in servers
        )
    )
    print(
        json.dumps(
            {
                "network_cases_passed": 6,
                "model_requests": 0,
                "planned_server_lifetimes": 2,
                "port_closed": port_closed,
            }
        ),
        flush=True,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--manifest", type=Path)
    p.add_argument("--state", type=Path)
    p.add_argument("--port", type=int, default=18856)
    p.add_argument("--serve-gated", action="store_true")
    args = p.parse_args()
    if args.serve_gated:
        uvicorn.run(
            ResponseGate(create_app(args.root, args.manifest)),
            host="127.0.0.1",
            port=args.port,
            log_level="warning",
            access_log=False,
        )
    else:
        asyncio.run(run_controls(args))


if __name__ == "__main__":
    main()
