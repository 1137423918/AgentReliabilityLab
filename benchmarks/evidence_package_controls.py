"""Exercise an installed evidence wheel from outside the source checkout.

Run with the new environment's python -I. Only MCP/client dependencies and the
installed package may resolve; no source checkout or model SDK is required.
"""

import argparse
import asyncio
import base64
import copy
import hashlib
import importlib.metadata
import importlib.util
import inspect
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

import agentlab_evidence
from agentlab_evidence import evidence_audit, evidence_mcp, evidence_service


def port_open(port):
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(('127.0.0.1', port)) == 0


async def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--expected-source', type=Path, required=True)
    args = p.parse_args()
    assert args.work.resolve() == Path.cwd().resolve()
    assert sys.flags.isolated == 1
    assert agentlab_evidence.__version__ == '0.1.0'
    expected = json.loads(args.expected_source.read_text())
    for name in ['agent_lab', 'benchmarks', 'deepagents', 'llama_index']:
        assert importlib.util.find_spec(name) is None, name
    identities = {}
    for module in [evidence_audit, evidence_service, evidence_mcp]:
        source = Path(inspect.getfile(module))
        assert source.is_relative_to(Path(sys.prefix))
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        assert digest == expected[source.name]
        identities[source.name] = {'sha256': digest, 'inside_new_environment': True}
    cli = Path(sys.executable).parent / 'agentlab-evidence'
    assert cli.is_file()
    catalog_root = args.work / 'catalog'
    manifest = catalog_root / 'catalog.json'
    catalog = json.loads(manifest.read_text())
    entry = next(row for row in catalog['reports'] if row['id'] == 'patch_move')
    report_path = catalog_root / entry['path']
    original = report_path.read_bytes()
    document = json.loads(original)
    common = [str(cli), '--root', str(catalog_root), '--manifest', str(manifest)]
    env = dict(os.environ)
    env.pop('PYTHONPATH', None)
    rows = []
    wire = []

    def command(name, argv, code):
        result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=30)
        (args.work / (name + '.log')).write_text(result.stdout + result.stderr)
        assert result.returncode == code, (name, result.returncode, result.stderr)
        rows.append({'case': name, 'passed': True, 'returncode': code})
        return result

    checked = command('installed_cli_catalog_check', common + ['--check'], 0)
    assert json.loads(checked.stdout)['reports'] == len(catalog['reports']) == 9
    command('installed_module_help', [sys.executable, '-I', '-m', 'agentlab_evidence', '--help'], 0)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    assert not port_open(port)
    try:
        report_path.write_bytes(original + b'\n')
        command('modified_catalog_check_rejected', common + ['--check'], 2)
        command('modified_catalog_start_rejected', common + ['--port', str(port)], 2)
        assert not port_open(port)
    finally:
        report_path.write_bytes(original)

    async def request_hook(request):
        raw = await request.aread()
        wire.append({'kind': 'request', 'method': request.method, 'path': request.url.path, 'body_base64': base64.b64encode(raw).decode(), 'body_sha256': hashlib.sha256(raw).hexdigest(), 'body_bytes': len(raw)})

    async def response_hook(response):
        raw = await response.aread()
        wire.append({'kind': 'response', 'status': response.status_code, 'body_base64': base64.b64encode(raw).decode(), 'body_sha256': hashlib.sha256(raw).hexdigest(), 'body_bytes': len(raw)})

    old_handle = None
    lifetimes = []
    for lifetime, cap in [(1, 16), (2, 3)]:
        with (args.work / ('server-' + str(lifetime) + '.log')).open('wb') as log:
            process = subprocess.Popen(common + ['--port', str(port), '--max-operations', str(cap)], env=env, stdout=log, stderr=subprocess.STDOUT)
            ticks = Path(f'/proc/{process.pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
            started = time.monotonic()
            forced = False
            try:
                async with httpx2.AsyncClient(trust_env=False, timeout=5, event_hooks={'request': [request_hook], 'response': [response_hook]}) as http:
                    async with asyncio.timeout(30):
                        while True:
                            assert process.poll() is None, 'Installed CLI exited before health'
                            try:
                                health = await http.get(f'http://127.0.0.1:{port}/health')
                                if health.status_code == 200 and health.json()['status'] == 'ok':
                                    break
                            except httpx2.TransportError:
                                pass
                            await asyncio.sleep(.05)
                    async with Client(streamable_http_client(f'http://127.0.0.1:{port}/mcp', http_client=http), cache=None) as remote:
                        async def call(name, args=None, error=False):
                            value = await remote.call_tool(name, args or {})
                            assert value.is_error == error, (name, value)
                            if error:
                                return '\n'.join(x.text for x in value.content if hasattr(x, 'text'))
                            assert isinstance(value.structured_content, dict)
                            return value.structured_content

                        tools = await remote.list_tools()
                        assert {x.name for x in tools.tools} == {'begin_audit', 'list_reports', 'read_report', 'verify_assessment', 'audit_status', 'close_audit'}
                        a = (await call('begin_audit'))['audit_id']
                        if lifetime == 1:
                            b = (await call('begin_audit'))['audit_id']
                            listing = await call('list_reports', {'audit_id': a})
                            assert len(listing['reports']) == 9
                            read = await call('read_report', {'audit_id': a, 'report_id': 'patch_move', 'pointers': ['/related_suite_passed']})
                            assert read['report']['values']['/related_suite_passed'] == document['related_suite_passed']
                            proposal = {'claim_supported': True, 'explanation': 'Exact report value, not a general verdict proof.', 'facts': [{'report_id': 'patch_move', 'pointer': '/related_suite_passed', 'value': document['related_suite_passed']}], 'citations': [{'report_id': 'patch_move', 'sha256': entry['sha256']}]}
                            args_a = {'audit_id': a, 'assessment': proposal, 'receipts': [read['receipt']]}
                            verified = await call('verify_assessment', args_a)
                            assert verified['evidence_verified'] is True and verified['verdict_truth_verified'] is False and verified['free_prose_semantics_verified'] is False
                            rows.append({'case': 'installed_cli_real_report_receipt_verification', 'passed': True})
                            stolen = await call('verify_assessment', {**args_a, 'audit_id': b}, error=True)
                            assert 'not issued by this audit' in stolen
                            forged = copy.deepcopy(args_a)
                            forged['assessment']['facts'][0]['value'] = True
                            rejected = await call('verify_assessment', forged, error=True)
                            assert 'differs from actual report' in rejected
                            rows.append({'case': 'cross_audit_receipt_and_wrong_JSON_type_rejected', 'passed': True})
                            try:
                                report_path.write_bytes(original + b'\n')
                                changed = await call('read_report', {'audit_id': a, 'report_id': 'patch_move', 'pointers': ['/related_suite_passed']}, error=True)
                                assert 'pinned snapshot' in changed
                            finally:
                                report_path.write_bytes(original)
                            rows.append({'case': 'installed_cli_rechecks_changed_report', 'passed': True})
                            assert await call('close_audit', {'audit_id': a}) == {'closed': True}
                            assert 'Unknown or expired' in await call('audit_status', {'audit_id': a}, error=True)
                            assert await call('close_audit', {'audit_id': b}) == {'closed': True}
                            old_handle = (await call('begin_audit'))['audit_id']
                        else:
                            assert 'Unknown or expired' in await call('audit_status', {'audit_id': old_handle}, error=True)
                            for _ in range(cap):
                                await call('list_reports', {'audit_id': a})
                            assert 'budget exhausted' in await call('list_reports', {'audit_id': a}, error=True)
                            status = await call('audit_status', {'audit_id': a})
                            assert status['operations_spent'] == status['max_operations'] == cap
                            assert await call('close_audit', {'audit_id': a}) == {'closed': True}
                            rows.append({'case': 'installed_cli_restart_invalidates_handles_and_exhausted_context_closes', 'passed': True})
            finally:
                if process.poll() is None:
                    assert Path(f'/proc/{process.pid}/stat').read_text().rsplit(')', 1)[1].split()[19] == ticks
                    process.send_signal(signal.SIGTERM)
                    try:
                        await asyncio.to_thread(process.wait, timeout=10)
                    except subprocess.TimeoutExpired:
                        forced = True
                        process.kill()
                        await asyncio.to_thread(process.wait, timeout=5)
                closed = not port_open(port)
                lifetimes.append({'lifetime': lifetime, 'returncode': process.returncode, 'forced_kill': forced, 'port_closed': closed, 'wall_seconds': round(time.monotonic() - started, 3)})
                assert process.returncode in [0, -15, 143] and not forced and closed
    (args.work / 'wire.json').write_text(json.dumps(wire, indent=2) + '\n')
    report = {'cases': rows, 'passed': len(rows), 'failed': 0, 'canonical_installed_source': identities, 'isolated_python': True, 'source_checkout_importable': False, 'deepagents_or_llamaindex_installed': False, 'installed_version': importlib.metadata.version('agentlab-evidence'), 'catalog_reports': 9, 'planned_server_lifetimes': lifetimes, 'model_HTTP_requests': 0, 'neural_requests': 0, 'GPU_used': False, 'corpus_bytes_restored': report_path.read_bytes() == original}
    (args.work / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': len(rows), 'failed': 0, 'planned_lifetimes': lifetimes, 'model_requests': 0}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
