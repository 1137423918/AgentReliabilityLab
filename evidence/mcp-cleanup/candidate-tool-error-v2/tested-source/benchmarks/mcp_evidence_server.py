"""Expose fixed public evidence through the real MCP2 Streamable HTTP transport.

The optional SDK is installed in its own environment. This service binds only
loopback. It does not call a model or expose arbitrary filesystem operations.
"""

import argparse
from functools import partial
from pathlib import Path
from typing import Any

import anyio
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from starlette.responses import JSONResponse
from starlette.routing import Route
import uvicorn

from agent_lab.evidence_audit import EvidenceError
from agent_lab.evidence_service import EvidenceService


def create_app(root: Path, manifest: Path, **limits):
    """Build a local MCP app with expiring, receipt-checked audit contexts."""
    service = EvidenceService(root, manifest, **limits)
    server = MCPServer("AgentLab Evidence", version="0.1.0")

    async def call(function, *args):
        try:
            # Default thread cancellation waits for a short filesystem operation
            # to finish. A canceled client may never receive its read receipt.
            return await anyio.to_thread.run_sync(partial(function, *args))
        except EvidenceError as exc:
            raise ToolError(str(exc)) from exc

    @server.tool()
    async def begin_audit() -> dict[str, Any]:
        """Create a bounded audit capability for the fixed report snapshot."""
        return await call(service.begin)

    @server.tool()
    async def list_reports(audit_id: str) -> dict[str, Any]:
        """List pinned reports; catalog metadata is not factual evidence."""
        return await call(service.list_reports, audit_id)

    @server.tool()
    async def read_report(
        audit_id: str, report_id: str, pointers: list[str]
    ) -> dict[str, Any]:
        """Read1–8 JSON pointers; keep the returned receipt for verification."""
        return await call(service.read_report, audit_id, report_id, pointers)

    @server.tool()
    async def verify_assessment(
        audit_id: str, assessment: dict[str, Any], receipts: list[str]
    ) -> dict[str, Any]:
        """Verify exact facts and receipt lineage, not verdict truth or free prose."""
        return await call(service.verify_assessment, audit_id, assessment, receipts)

    @server.tool()
    async def audit_status(audit_id: str) -> dict[str, Any]:
        """Inspect spent operations and completed reads without resetting limits."""
        return await call(service.status, audit_id)

    @server.tool()
    async def close_audit(audit_id: str) -> dict[str, Any]:
        """Discard a capability, including one whose operation budget is exhausted."""
        return await call(service.close, audit_id)

    app = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        max_request_body_size=16384,
        host="127.0.0.1",
    )

    async def health(request):
        return JSONResponse({"status": "ok"})

    app.routes.append(Route("/health", health))
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18856)
    parser.add_argument("--max-operations", type=int, default=16)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Choose an unprivileged local port")
    app = create_app(args.root, args.manifest, max_operations=args.max_operations)
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        workers=1,
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
