"""Run controlled Pydantic AI tool/HTTP budget cases, never a neural benchmark.

Install the separately built budget wheel and pinned framework dependencies in an
isolated environment. Pass a local output directory and an existing public report.
"""

import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from durable_agent_budget import (
    RequestBudgetError,
    make_async_http_client,
    open_budget,
)
from durable_agent_budget.storage import admit_state_directory
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai_compatible import OpenAICompatibleProvider


def budget_cause(error):
    stack, seen = [error], set()
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, RequestBudgetError):
            return True
        stack.extend(x for x in (current.__cause__, current.__context__) if x)
        if isinstance(current, BaseExceptionGroup):
            stack.extend(current.exceptions)
    return False


class Fixture:
    def __init__(self, expected):
        self.expected = expected
        self.requests = []
        self.request_lock = threading.Lock()
        self.tool_reads = []
        self.gate = threading.Event()
        self.gate.set()
        self.arrived = threading.Event()
        self.status = 200
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                request = json.loads(raw)
                with fixture.request_lock:
                    fixture.requests.append({"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                                             "body": request})
                    request_index = len(fixture.requests)
                fixture.arrived.set()
                fixture.gate.wait(timeout=10)
                if fixture.status != 200:
                    payload = {"error": {"message": "Controlled fake 503", "type": "server_error"}}
                else:
                    used = any(m["role"] == "tool" for m in request["messages"])
                    message = {"role": "assistant", "content": json.dumps(fixture.expected)} if used else {
                        "role": "assistant", "content": None,
                        "tool_calls": [{"id": "fixture-" + str(request_index), "type": "function",
                                        "function": {"name": "read_lifecycle_report", "arguments": "{}"}}]}
                    payload = {"id": "fixture-response", "object": "chat.completion", "created": 0,
                               "model": "agentlab-fixture", "choices": [{"index": 0, "message": message,
                               "finish_reason": "stop" if used else "tool_calls"}],
                               "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}
                body = json.dumps(payload).encode()
                try:
                    self.send_response(fixture.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"

    async def close(self):
        self.gate.set()
        await asyncio.to_thread(self.server.shutdown)
        self.server.server_close()
        self.thread.join(timeout=3)


@asynccontextmanager
async def client_agent(budget, fixture, report_file, *, sdk_retries=0):
    async with make_async_http_client(budget) as guarded:
        async with AsyncOpenAI(base_url=fixture.url, api_key="local-fixture-only",
                               max_retries=sdk_retries, timeout=10, http_client=guarded) as sdk:
            provider = OpenAICompatibleProvider("agentlab-controlled-fixture", openai_client=sdk)
            agent = Agent(OpenAIChatModel("agentlab-fixture", provider=provider), retries=0)

            @agent.tool_plain
            async def read_lifecycle_report() -> dict:
                """Read the actual operator-owned verification lifecycle report."""
                raw = await asyncio.to_thread(report_file.read_bytes)
                data = json.loads(raw)
                result = {"source_report_sha256": hashlib.sha256(raw).hexdigest(),
                          "full_suite_passed": data["full_suite_passed"]}
                fixture.tool_reads.append(result)
                return result

            yield agent


def checked_journal(directory, fixture, limit):
    state = json.loads((directory / "model-requests.json").read_text())
    entries = state["reservations"]
    assert len(entries) == len(fixture.requests) == limit
    assert sorted((r["request_body_sha256"], r["request_body_bytes"]) for r in entries) == sorted(
        (r["sha256"], r["bytes"]) for r in fixture.requests)
    return {"http_requests": len(entries), "request_body_bytes": sum(x["request_body_bytes"] for x in entries),
            "http_statuses": [x["http_status"] for x in entries],
            "unobserved": sum(x["transport_observation"] == "reserved" for x in entries),
            "journal_id": state["identity"]["journal_id"]}


async def run_case(name, root, report_file, expected):
    fixture = Fixture(expected)
    counts = {"normal_reopen": 2, "cancel_inflight": 1, "concurrent_agents": 3, "sdk_retries": 2}
    limit = counts[name]
    limits = {"max_requests": limit, "max_request_bytes": 65536, "max_total_request_bytes": 262144}
    owner = hashlib.sha256(json.dumps({"case": name, "report": expected, "limits": limits},
                                     sort_keys=True).encode()).hexdigest()
    directory = root / name
    budget = open_budget(directory, owner, limits, create=True)
    try:
        if name == "normal_reopen":
            async with client_agent(budget, fixture, report_file) as agent:
                result = await agent.run("Read the lifecycle report and return its source hash and full test count.")
                assert json.loads(result.output) == expected
            assert fixture.tool_reads == [expected]
            assert any(x["role"] == "tool" for x in fixture.requests[1]["body"]["messages"])
            assert expected["source_report_sha256"] in json.dumps(fixture.requests[1]["body"])
            resumed = open_budget(directory, owner, limits)
            async with client_agent(resumed, fixture, report_file) as agent:
                try:
                    await agent.run("Read the same report again.")
                except Exception as error:
                    assert budget_cause(error), type(error).__name__
                else:
                    raise AssertionError("Reopen bypassed the quota")
        elif name == "cancel_inflight":
            fixture.gate.clear()
            async with client_agent(budget, fixture, report_file) as agent:
                job = asyncio.create_task(agent.run("Read the lifecycle report."))
                try:
                    assert await asyncio.to_thread(fixture.arrived.wait, 5)
                    job.cancel()
                    try:
                        await job
                    except asyncio.CancelledError:
                        pass
                    else:
                        raise AssertionError("Agent did not propagate cancellation")
                finally:
                    fixture.gate.set()
                    if not job.done():
                        job.cancel()
                        await asyncio.gather(job, return_exceptions=True)
            resumed = open_budget(directory, owner, limits)
            async with client_agent(resumed, fixture, report_file) as agent:
                try:
                    await agent.run("Try after cancellation.")
                except Exception as error:
                    assert budget_cause(error), type(error).__name__
                else:
                    raise AssertionError("Cancellation refunded an unknown attempt")
            assert resumed.summary()["unobserved_reservations"] == 1
        elif name == "concurrent_agents":
            async with client_agent(budget, fixture, report_file) as agent:
                results = await asyncio.gather(*(agent.run("Read the report.") for _ in range(4)),
                                               return_exceptions=True)
            completed = [x for x in results if not isinstance(x, BaseException)]
            assert len(completed) <= 1
            assert all(json.loads(x.output) == expected for x in completed)
            assert all(budget_cause(x) for x in results if isinstance(x, BaseException))
            assert len(fixture.tool_reads) + len(completed) == 3
        else:
            fixture.status = 503
            async with client_agent(budget, fixture, report_file, sdk_retries=2) as agent:
                try:
                    await agent.run("Read the report.")
                except Exception as error:
                    assert budget_cause(error), type(error).__name__
                else:
                    raise AssertionError("SDK retries bypassed the quota")
            assert not fixture.tool_reads
        observed = checked_journal(directory, fixture, limit)
        assert observed["http_statuses"] == ([None] if name == "cancel_inflight" else
                                            [503] * limit if name == "sdk_retries" else [200] * limit)
        return {"case": name, "passed": True, **observed, "actual_report_tool_reads": len(fixture.tool_reads),
                "sdk_max_retries": 2 if name == "sdk_retries" else 0,
                "neural_inference": False, "explicit_fake_model": True}
    finally:
        await fixture.close()


async def main(args):
    admit_state_directory(args.output)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    raw = args.report_file.read_bytes()
    source = json.loads(raw)
    expected = {"source_report_sha256": hashlib.sha256(raw).hexdigest(),
                "full_suite_passed": source["full_suite_passed"]}
    report = {"scope": "Four actual PydanticAI/SDK/tool HTTP cases against an explicitly fake loopback service; not a neural benchmark.",
              "versions": {p: version(p) for p in ["pydantic-ai-slim", "openai", "httpx2", "agentlab-durable-budget"]},
              "expected_tool_payload": expected, "cases": [], "real_neural_requests": 0, "gpu_used": False}
    for name in ["normal_reopen", "cancel_inflight", "concurrent_agents", "sdk_retries"]:
        try:
            row = await asyncio.wait_for(run_case(name, args.output, args.report_file, expected), 45)
        except Exception as error:
            row = {"case": name, "passed": False, "error_type": type(error).__name__, "error": str(error)}
        report["cases"].append(row)
        report["success"] = len(report["cases"]) == 4 and all(x["passed"] for x in report["cases"])
        (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(row), flush=True)
        if not row["passed"]:
            raise RuntimeError("Integration case failed: " + name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report-file", type=Path, required=True)
    asyncio.run(main(parser.parse_args()))
