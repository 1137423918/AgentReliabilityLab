"""Let a real FunctionAgent consume report tools through an external MCP2 server.

The adapter keeps audit capabilities and read receipts outside model prompts.
Facts are accepted only by the actual remote verifier. Model calls retain the
existing durable loopback HTTP attempt/body-byte budget.
"""

import argparse
import asyncio
import base64
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from agent_lab.async_request_budget import make_async_http_client, open_budget
from agent_lab.evidence_audit import EvidenceError
from benchmarks.llamaindex_evidence_agent import AuditAssessment, DIRECT_SYSTEM


class MCPToolFailure(EvidenceError):
    """The remote MCP tool rejected a request or returned an invalid result."""


def hooks(channel, wire):
    """Record bodies and protocol version, excluding all authentication headers."""

    async def request_hook(request):
        raw = await request.aread()
        wire.append(
            {
                "channel": channel,
                "kind": "client_request_attempt",
                "path": request.url.path,
                "method": request.method,
                "protocol_version": request.headers.get("mcp-protocol-version"),
                "body_base64": base64.b64encode(raw).decode(),
                "body_bytes": len(raw),
                "body_sha256": hashlib.sha256(raw).hexdigest(),
            }
        )

    async def response_hook(response):
        raw = await response.aread()
        wire.append(
            {
                "channel": channel,
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

    return {"request": [request_hook], "response": [response_hook]}


async def call_tool(remote, name, args=None):
    result = await remote.call_tool(name, args or {})
    if result.is_error:
        raise MCPToolFailure(
            "; ".join(x.text for x in result.content if hasattr(x, "text"))
        )
    if not isinstance(result.structured_content, dict):
        raise MCPToolFailure("Remote tool has no structured object result")
    return result.structured_content


async def cleanup_audit(mcp_url, handle, wire, outcome):
    """Close the same capability on a fresh transport within ten seconds.

    Status is optional and gets only two seconds of that budget. Neither a
    status error nor the workflow's canceled transport may skip the close.
    There is one close attempt, no replay, renewal or replacement audit.
    """
    try:
        async with asyncio.timeout(10):
            async with httpx2.AsyncClient(
                trust_env=False,
                follow_redirects=False,
                timeout=10,
                event_hooks=hooks("mcp", wire),
            ) as http:
                async with Client(
                    streamable_http_client(mcp_url, http_client=http), cache=None
                ) as remote:
                    try:
                        async with asyncio.timeout(2):
                            outcome["mcp_status_before_close"] = await call_tool(
                                remote, "audit_status", {"audit_id": handle}
                            )
                    except Exception as exc:
                        outcome["mcp_cleanup_status_error"] = {
                            "type": type(exc).__name__,
                            "message": str(exc),
                        }
                    closed = await call_tool(
                        remote, "close_audit", {"audit_id": handle}
                    )
                    if closed != {"closed": True}:
                        raise MCPToolFailure("Unexpected close acknowledgement")
                    outcome["mcp_close"] = closed
    except Exception as exc:
        outcome["mcp_cleanup_error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }


async def audit_via_mcp(
    mcp_url, state_dir, question, *, base_url, model, owner_sha256, timeout=600
):
    from llama_index.core.agent.workflow import FunctionAgent
    from llama_index.core.tools import FunctionTool
    from llama_index.llms.openai_like import OpenAILike

    parsed = urlsplit(mcp_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.path != "/mcp"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Use an explicit loopback MCP endpoint")
    limits = {
        "max_requests": 8,
        "max_request_bytes": 65536,
        "max_total_request_bytes": 262144,
    }
    budget = open_budget(state_dir, owner_sha256, limits, create=True)
    wire = []
    trace = []
    events = []
    receipts = []
    submissions = []
    handle = None
    outcome = {
        "question": question,
        "model": model,
        "limits": limits,
        "journal_id": budget.journal_id,
        "evidence_verified": False,
        "backend": "external_mcp2",
        "tool_trace": trace,
        "wire_events": wire,
        "workflow_events": events,
        "submissions": submissions,
    }
    try:
        async with asyncio.timeout(timeout):
            async with httpx2.AsyncClient(
                trust_env=False,
                follow_redirects=False,
                timeout=10,
                event_hooks=hooks("mcp", wire),
            ) as mcp_http:
                async with Client(
                    streamable_http_client(mcp_url, http_client=mcp_http), cache=None
                ) as remote:

                    async def call(name, args=None):
                        return await call_tool(remote, name, args)

                    listing = await remote.list_tools()
                    if {t.name for t in listing.tools} != {
                        "begin_audit",
                        "list_reports",
                        "read_report",
                        "verify_assessment",
                        "audit_status",
                        "close_audit",
                    }:
                        raise MCPToolFailure("Unexpected remote tool contract")
                    begin = await call("begin_audit")
                    handle = begin["audit_id"]
                    outcome["mcp_context"] = begin

                    async def list_reports() -> str:
                        """List pinned report IDs and suggested fields; metadata is not evidence."""
                        value = await call("list_reports", {"audit_id": handle})
                        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
                        trace.append(
                            {
                                "tool": "list_reports",
                                "result_sha256": hashlib.sha256(
                                    encoded.encode()
                                ).hexdigest(),
                            }
                        )
                        return encoded

                    async def read_report(report_id: str, pointers: list[str]) -> str:
                        """Read1–8 exact JSON pointers from one pinned report."""
                        try:
                            value = await call(
                                "read_report",
                                {
                                    "audit_id": handle,
                                    "report_id": report_id,
                                    "pointers": pointers,
                                },
                            )
                            if not isinstance(
                                value.get("receipt"), str
                            ) or not isinstance(value.get("report"), dict):
                                raise MCPToolFailure("Invalid read response")
                            receipts.append(value["receipt"])
                            encoded = json.dumps(
                                value["report"], ensure_ascii=False, sort_keys=True
                            )
                            trace.append(
                                {
                                    "tool": "read_report",
                                    "report_id": report_id,
                                    "pointers": pointers,
                                    "receipt": value["receipt"],
                                    "result_sha256": hashlib.sha256(
                                        encoded.encode()
                                    ).hexdigest(),
                                }
                            )
                            return encoded
                        except MCPToolFailure as exc:
                            trace.append(
                                {
                                    "tool": "read_report",
                                    "report_id": report_id,
                                    "pointers": pointers,
                                    "error": str(exc),
                                }
                            )
                            return json.dumps({"error": str(exc)})

                    async def submit_assessment(**payload) -> str:
                        """Submit the final typed verdict and exact facts for remote receipt verification."""
                        try:
                            assessment = AuditAssessment.model_validate(
                                payload
                            ).model_dump()
                            verification = await call(
                                "verify_assessment",
                                {
                                    "audit_id": handle,
                                    "assessment": assessment,
                                    "receipts": receipts,
                                },
                            )
                            if (
                                verification.get("evidence_verified") is not True
                                or verification.get("verdict_truth_verified")
                                is not False
                                or verification.get("free_prose_semantics_verified")
                                is not False
                            ):
                                raise MCPToolFailure("Unexpected verifier semantics")
                            submission = {
                                "status": "evidence_verified",
                                "assessment": assessment,
                                "verification": verification,
                            }
                        except ValueError as exc:
                            submission = {"status": "rejected", "error": str(exc)}
                        encoded = json.dumps(
                            submission, ensure_ascii=False, sort_keys=True
                        )
                        submissions.append(submission)
                        trace.append(
                            {
                                "tool": "submit_assessment",
                                "status": submission["status"],
                                "result_sha256": hashlib.sha256(
                                    encoded.encode()
                                ).hexdigest(),
                            }
                        )
                        return encoded

                    async with make_async_http_client(budget) as model_http:
                        for name, handlers in hooks("model", wire).items():
                            model_http.event_hooks[name].extend(handlers)
                        llm = OpenAILike(
                            model=model,
                            api_base=base_url,
                            api_key=os.environ.get(
                                "AGENT_LAB_EVIDENCE_KEY", "local-evidence-only"
                            ),
                            context_window=8192,
                            is_chat_model=True,
                            is_function_calling_model=True,
                            max_retries=0,
                            timeout=300,
                            max_tokens=1024,
                            temperature=0.7,
                            additional_kwargs={
                                "top_p": 0.8,
                                "presence_penalty": 1.5,
                                "extra_body": {
                                    "top_k": 20,
                                    "min_p": 0.0,
                                    "repeat_penalty": 1.0,
                                },
                            },
                            async_http_client=model_http,
                        )
                        agent = FunctionAgent(
                            tools=[
                                FunctionTool.from_defaults(async_fn=list_reports),
                                FunctionTool.from_defaults(async_fn=read_report),
                                FunctionTool.from_defaults(
                                    async_fn=submit_assessment,
                                    fn_schema=AuditAssessment,
                                    return_direct=True,
                                ),
                            ],
                            llm=llm,
                            system_prompt=DIRECT_SYSTEM,
                            streaming=False,
                            allow_parallel_tool_calls=False,
                            timeout=timeout,
                        )
                        handler = None
                        completed = False
                        try:
                            handler = agent.run(user_msg=question, max_iterations=7)
                            async for event in handler.stream_events():
                                events.append(
                                    {
                                        "type": type(event).__name__,
                                        "data": event.model_dump(mode="json"),
                                    }
                                )
                            result = await handler
                            completed = True
                            outcome["raw_answer"] = str(result.response)
                            final_response_content = result.response.content or ""
                        finally:
                            if handler is not None and not completed:
                                try:
                                    await asyncio.wait_for(
                                        handler.cancel_run(timeout=5), timeout=10
                                    )
                                except TimeoutError:
                                    outcome["workflow_cancel_wait_expired"] = True
        # Decide application-level acceptance after transport task groups exit.
        # Raising EvidenceError inside MCP's context can wrap it in ExceptionGroup.
        if (
            len(submissions) != 1
            or submissions[0]["status"] != "evidence_verified"
            or trace[-1]["tool"] != "submit_assessment"
            or hashlib.sha256(final_response_content.encode()).hexdigest()
            != trace[-1]["result_sha256"]
        ):
            raise EvidenceError("No single remotely validated submission")
        outcome["assessment"] = submissions[0]["assessment"]
        outcome["verification"] = submissions[0]["verification"]
        outcome["evidence_verified"] = True
    except Exception as exc:
        outcome["evidence_verified"] = False
        outcome["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        if handle is not None:
            await cleanup_audit(mcp_url, handle, wire, outcome)
    outcome["receipts_received"] = receipts
    outcome["versions"] = {
        n: importlib.metadata.version(n)
        for n in [
            "mcp",
            "mcp-types",
            "llama-index-core",
            "llama-index-llms-openai-like",
            "llama-index-workflows",
            "openai",
            "httpx2",
        ]
    }
    return outcome


async def main():
    from benchmarks.evidence_audit_case import grade_case

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mcp-url", required=True)
    p.add_argument("--state-dir", type=Path, required=True)
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--case", required=True)
    p.add_argument("--base-url", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--owner", required=True)
    args = p.parse_args()
    case = next(
        x
        for x in json.loads(args.cases.read_text(encoding="utf-8"))
        if x["id"] == args.case
    )
    args.state_dir.mkdir(exist_ok=False)
    result = await audit_via_mcp(
        args.mcp_url,
        args.state_dir / "journal",
        case["question"],
        base_url=args.base_url,
        model=args.model,
        owner_sha256=args.owner,
    )
    result["grading"] = grade_case(result, case)
    (args.state_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "case": case["id"],
                "grading": result["grading"],
                "error": result.get("error"),
            }
        )
    )
    raise SystemExit(0 if result["grading"]["case_passed"] else 2)


if __name__ == "__main__":
    asyncio.run(main())
