"""Offline report application against three frozen, previously completed CPU runs.

No graph/model replay or new grading. Export each recorded status unchanged.
"""
from pathlib import Path
import hashlib
import json
import socket
import sys
from unittest.mock import patch

from agent_lab.research_report import main


def files(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def run(cases_root, store, output):
    output.mkdir(mode=0o700, exist_ok=False)
    case_ids = ['lightrag_retrieval', 'compare_indexing', 'missing_paper']
    cases = [cases_root / key for key in case_ids]
    before = [files(path) for path in cases]
    original_statuses = [json.loads((path / 'result.json').read_text())['status'] for path in cases]
    store_before = files(store)
    attempts = []

    def blocked(*args, **kwargs):
        attempts.append(True)
        raise AssertionError('Report export must not connect to any service')

    with patch.object(socket.socket, 'connect', blocked), patch.object(socket.socket, 'connect_ex', blocked):
        for label in ['first', 'repeat']:
            args = ['--store', str(store), '--output', str(output / label)]
            for path in cases:
                args += ['--run-dir', str(path)]
            assert main(args) == 0
    first = output / 'first'
    report = json.loads((first / 'reading-report.json').read_text())
    assert report['summary'] == {'runs': 3, 'recorded_submissions': 2, 'recorded_uncompleted': 1, 'export_errors': 0}
    assert [row['recorded_status'] for row in report['runs']] == original_statuses == ['submitted', 'submitted', 'turn_limit']
    assert report['runs'][2]['answer'] is None
    assert report['runs'][2]['diagnostics'] == ['empty_answer', 'insufficient_evidence_with_citations', 'submission_rejected']
    assert all(row['requests'] == {'reserved': 6, 'saved_complete': 6, 'without_saved_complete_response': 0, 'limit': 6} for row in report['runs'])
    refs = [ref for row in report['runs'] for ref in row['references']]
    assert len(refs) == 4 and all(ref.get('pdf') for ref in refs)
    assert all(not ref['is_current_generation'] for ref in refs)
    assert {row['source_generation'] for row in report['runs']} == {'80bdd57f5e68d682a5b04c7e799c55f6b8979e75445a2ce744e39c88acce88ca'}
    assert files(first) == files(output / 'repeat')
    assert before == [files(path) for path in cases] and store_before == files(store)
    assert not attempts
    assert 'torch' not in sys.modules and 'transformers' not in sys.modules
    for path in first.iterdir():
        text = path.read_text()
        assert all(part not in text for part in ['"excerpt"', '"choices"', '"messages"', '/data1/', '/tmp/agentlab-', 'http://127.0.0.1'])
    result = {
        'ready': True, 'scope': 'New offline report application using unchanged closed model artifacts; no model replay or regrading.',
        'recorded_model_statuses_preserved': original_statuses,
        'application_summary': report['summary'], 'exact_PDF_references_read_back': 4,
        'references_from_retained_historical_generation': True,
        'new_generation_HTTP_requests': 0, 'new_embedding_forwards': 0,
        'blocked_network_connect_attempts': len(attempts), 'model_modules_not_loaded': True,
        'original_case_and_source_store_hashes_unchanged': True,
        'repeat_export_bytes_identical': True, 'GPU_used': False,
        'report_files': {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
                         for p in first.iterdir()},
    }
    (output / 'application-result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    run(*map(Path, sys.argv[1:]))
