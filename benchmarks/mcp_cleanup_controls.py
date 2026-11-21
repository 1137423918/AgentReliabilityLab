"""Fault controls using real MCP/LlamaIndex transports and scripted model HTTP.

No neural inference. Protocol faults are injected only at the explicit test
server boundary; audit capabilities, expiry, reads and closure remain real.
"""

import argparse
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import socket
import threading
import time
from types import SimpleNamespace

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
import uvicorn

from benchmarks.llamaindex_mcp_audit import audit_via_mcp
from benchmarks.mcp_agent_controls import run_case
from benchmarks.mcp_evidence_server import create_app


class FaultBoundary:
    """Record real tool calls; inject a status error or delay before dispatch."""

    def __init__(self, app, scenario):
        self.app = app
        self.scenario = scenario
        self.calls = []
        self.handles = []

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST':
            return await self.app(scope, receive, send)
        messages = []
        body = b''
        while True:
            message = await receive()
            messages.append(message)
            body += message.get('body', b'')
            if not message.get('more_body', False):
                break
        request = json.loads(body)
        name = request.get('params', {}).get('name')
        if request.get('method') == 'tools/call':
            self.calls.append(name)
        if name == 'audit_status' and self.scenario in {'status_error', 'status_tool_error'}:
            result = {
                    'isError': True,
                    'content': [{'type': 'text', 'text': 'Injected status-only failure'}],
            }
            if self.scenario == 'status_tool_error':
                result['resultType'] = 'complete'
            payload = json.dumps({'jsonrpc': '2.0', 'id': request['id'], 'result': result}).encode()
            await send({'type': 'http.response.start', 'status': 200, 'headers': [
                (b'content-type', b'application/json'),
                (b'content-length', str(len(payload)).encode()),
            ]})
            await send({'type': 'http.response.body', 'body': payload})
            return
        if name == 'audit_status' and self.scenario == 'status_timeout':
            await asyncio.sleep(3)

        async def replay():
            return messages.pop(0) if messages else await receive()

        response_body = b''

        async def record(message):
            nonlocal response_body
            if message['type'] == 'http.response.body':
                response_body += message.get('body', b'')
                if not message.get('more_body', False) and name == 'begin_audit':
                    value = json.loads(response_body)['result']['structuredContent']
                    self.handles.append(value['audit_id'])
            await send(message)

        return await self.app(scope, replay, record)


async def call_status(url, handle):
    async with httpx2.AsyncClient(trust_env=False, timeout=3) as http:
        async with Client(streamable_http_client(url, http_client=http), cache=None) as remote:
            result = await remote.call_tool('audit_status', {'audit_id': handle})
            return {'is_error': result.is_error, 'content': [x.text for x in result.content if hasattr(x, 'text')]}


async def interrupted_case(args, scenario):
    received = threading.Event()
    release = threading.Event()
    bodies = []
    errors = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            bodies.append(raw)
            received.set()
            if not release.wait(20):
                errors.append('Control response release deadline expired')
            encoded = json.dumps({
                'id': 'explicit-cleanup-control', 'object': 'chat.completion',
                'created': 0, 'model': 'explicit-fake-cleanup',
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'Unverified control answer.'}, 'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
            }).encode()
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError):
                pass  # The model request is deliberately canceled before release.

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    task = asyncio.create_task(audit_via_mcp(
        args.mcp_url, args.state / 'journal', 'Explicit cleanup fault control.',
        base_url=f'http://127.0.0.1:{server.server_port}/v1',
        model='explicit-fake-cleanup', owner_sha256=args.owner,
        timeout=6 if scenario == 'model_timeout' else 30,
    ))
    result = None
    try:
        async with asyncio.timeout(10):
            while not received.is_set():
                if task.done():
                    result = await task
                    raise AssertionError('Agent finished before the controlled model POST')
                await asyncio.sleep(0.01)
        if scenario == 'external_cancel':
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=15)
            except asyncio.CancelledError:
                result = {'external_cancellation_propagated': True}
            else:
                raise AssertionError('External cancellation was swallowed')
        else:
            if scenario == 'expired':
                await asyncio.sleep(1.5)
                release.set()
            result = await asyncio.wait_for(task, timeout=20)
        assert len(bodies) == 1 and not errors, (len(bodies), errors)
        if scenario != 'external_cancel':
            assert result['evidence_verified'] is False
            if scenario == 'model_timeout':
                assert result.get('error'), result
                assert result.get('mcp_close') == {'closed': True}, result
            else:
                assert result.get('error', {}).get('type') == 'EvidenceError', result
                assert result.get('mcp_close') != {'closed': True}, result
                assert result.get('mcp_cleanup_error'), result
        journal = json.loads((args.state / 'journal/model-requests.json').read_text())
        assert len(journal['reservations']) == 1
        reservation = journal['reservations'][0]
        if scenario != 'expired':
            assert reservation['http_status'] is None, reservation
        else:
            assert reservation['http_status'] == 200, reservation
        return result
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        release.set()
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()
        if result is not None:
            (args.state / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


async def one(args, scenario):
    state = args.state / scenario
    state.mkdir()
    app = create_app(args.code / 'corpus', args.code / 'corpus/catalog.json', ttl_seconds=1 if scenario == 'expired' else 600)
    boundary = FaultBoundary(app, scenario)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(boundary, log_level='error', access_log=False))
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    row = {'case': scenario, 'passed': False}
    started = time.monotonic()
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if serving.done():
                    await serving
                    raise AssertionError('Control MCP server exited before startup')
                await asyncio.sleep(0.01)
        child = SimpleNamespace(code=args.code, state=state, owner=args.owner, mcp_url=f'http://127.0.0.1:{port}/mcp')
        if scenario in {'model_timeout', 'external_cancel', 'expired'}:
            result = await interrupted_case(child, scenario)
        else:
            behavior = scenario if scenario in {'normal', 'forged_fact', 'unread_submission', 'plain_answer'} else 'normal'
            await run_case(child, behavior)
            result = json.loads((state / (behavior + '-result.json')).read_text())
        assert len(boundary.handles) == 1, boundary.calls
        # Switch off the injected status fault for independent postcondition inspection.
        boundary.scenario = 'inspection'
        status = await call_status(child.mcp_url, boundary.handles[0])
        assert status['is_error'] and any('Unknown or expired' in text for text in status['content']), status
        assert boundary.calls.count('begin_audit') == 1
        assert boundary.calls.count('close_audit') == 1, boundary.calls
        if scenario in {'status_error', 'status_tool_error', 'status_timeout'}:
            assert result.get('mcp_cleanup_status_error'), result
            assert result.get('mcp_close') == {'closed': True}, result
        if scenario == 'external_cancel':
            assert result['external_cancellation_propagated']
        row.update(passed=True, independent_status_unknown_or_expired=True)
    except Exception as exc:
        row['error'] = {'type': type(exc).__name__, 'message': str(exc)[:300]}
    finally:
        server.should_exit = True
        await asyncio.wait_for(serving, timeout=10)
        sock.close()
        row.update(wall_seconds=round(time.monotonic() - started, 3), tool_calls=boundary.calls, audit_contexts_created=len(boundary.handles), close_attempts=boundary.calls.count('close_audit'), server_terminal=serving.done())
        (state / 'control-report.json').write_text(json.dumps(row, indent=2) + '\n')
    return row


async def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--code', type=Path, required=True)
    p.add_argument('--state', type=Path, required=True)
    p.add_argument('--owner', required=True)
    p.add_argument('--case', choices=['status_tool_error'])
    args = p.parse_args()
    args.state.mkdir(exist_ok=False)
    rows = []
    scenarios = [args.case] if args.case else ['normal', 'forged_fact', 'unread_submission', 'plain_answer', 'status_error', 'status_timeout', 'model_timeout', 'external_cancel', 'expired']
    for scenario in scenarios:
        row = await one(args, scenario)
        rows.append(row)
        print(json.dumps(row), flush=True)
    report = {'cases': rows, 'passed': sum(row['passed'] for row in rows), 'failed': sum(not row['passed'] for row in rows), 'explicit_fake_model': True, 'neural_requests': 0, 'GPU_used': False}
    (args.state / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    raise SystemExit(0 if report['failed'] == 0 else 2)


if __name__ == '__main__':
    asyncio.run(main())
