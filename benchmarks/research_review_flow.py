"""Export exact archived passages for existing stopped runs, without inference."""
from pathlib import Path
import asyncio
import hashlib
import json
import socket
import sys
import time
from unittest.mock import patch

from agent_lab.research_review import build_review, initial_decisions, write_review


def files(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def run(old_cases, new_case, store, output):
    output.mkdir(mode=0o700, exist_ok=False)
    cases = [old_cases / n for n in ['lightrag_retrieval', 'compare_indexing', 'missing_paper']] + [new_case]
    before = [files(p) for p in cases]; store_before = files(store); connections = []
    def blocked(*args, **kwargs):
        connections.append(True)
        raise AssertionError('Review export must stay offline')
    started = time.monotonic()
    with patch.object(socket.socket, 'connect', blocked), patch.object(socket.socket, 'connect_ex', blocked):
        bundle = build_review(cases, store)
        write_review(bundle, output / 'real'); write_review(bundle, output / 'real-repeat')
    entries = bundle['entries']
    statuses = [e['run']['recorded_status'] for e in entries]
    assert statuses == ['submitted', 'submitted', 'turn_limit', 'submitted']
    assert [e['reviewable'] for e in entries] == [True, True, False, True]
    assert entries[2]['run']['answer'] is None and not entries[2]['passages']
    assert sum(len(e['passages']) for e in entries) == 6
    assert all(not r['is_current_generation'] for e in entries[:2] for r in e['run']['references'])
    assert all(r['is_current_generation'] for r in entries[3]['run']['references'])
    assert [e['decision'] for e in initial_decisions(bundle)['entries']] == ['pending', 'pending', 'unavailable', 'pending']
    assert files(output / 'real') == files(output / 'real-repeat')
    assert before == [files(p) for p in cases] and store_before == files(store) and not connections
    assert 'torch' not in sys.modules and 'transformers' not in sys.modules
    result = {'ready': True, 'real_stopped_runs': 4, 'source_passages': 6,
              'recorded_statuses_preserved': statuses, 'reviewable': 3,
              'real_annotations_all_pending_or_unavailable': True,
              'historical_and_current_source_versions_read': True,
              'repeat_outputs_exact': True, 'original_runs_and_store_unchanged': True,
              'new_generation_requests': 0, 'new_embedding_forwards': 0,
              'network_connection_attempts': len(connections), 'GPU_used': False,
              'model_modules_not_loaded': True, 'bundle_sha256': bundle['bundle_sha256'],
              'wall_seconds': round(time.monotonic() - started, 3)}
    (output / 'application-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


async def demo(output):
    # Owned text and scripted model responses only. Never presented as a real
    # model quality sample or a human review of the four historical runs.
    from test_research_report import ReportWorkflows
    fixture = ReportWorkflows('runTest')
    await fixture.asyncSetUp()
    try:
        good = await fixture.make_run('example', question='中断后如何继续已提交的任务？（脚本化演示）')
        failed = await fixture.make_run('unfinished', failed=True, question='未完成任务如何展示？（脚本化演示）')
        bundle = build_review([good, failed, fixture.root / 'missing-demo-run'], fixture.store)
        bundle['scope'] = 'Owned synthetic source and scripted replies for UI demonstration; not real model evaluation or reviewer judgment.'
        from agent_lab.request_budget import digest
        bundle['bundle_sha256'] = digest({k: v for k, v in bundle.items() if k != 'bundle_sha256'})
        write_review(bundle, output)
        assert [e['reviewable'] for e in bundle['entries']] == [True, False, False]
    finally:
        await fixture.asyncTearDown()


if __name__ == '__main__':
    if sys.argv[1] == 'demo':
        asyncio.run(demo(Path(sys.argv[2])))
    else:
        run(*map(Path, sys.argv[1:]))
