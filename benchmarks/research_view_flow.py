"""Deliver four stopped real reading runs as an offline view; no inference."""
from pathlib import Path
import copy,hashlib,json,socket,sys,time
from unittest.mock import patch
from agent_lab.research_report import build_report,write_report


def files(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def run(old_cases, new_case, store, output):
    output.mkdir(mode=0o700, exist_ok=False)
    cases = [old_cases / name for name in ['lightrag_retrieval', 'compare_indexing', 'missing_paper']] + [new_case]
    before = [files(p) for p in cases]; store_before = files(store); connections = []
    def blocked(*args, **kwargs):
        connections.append(True); raise AssertionError('Offline report must not connect to a service')
    started = time.monotonic()
    with patch.object(socket.socket, 'connect', blocked), patch.object(socket.socket, 'connect_ex', blocked):
        report = build_report(cases, store)
        for name in ['first', 'repeat']: write_report(report, output / name)
        # Separate QA fixture, never a fifth real reading case. It exercises a
        # missing artifact and markup-like text in the same renderer/browser.
        control = build_report(cases + [output / 'intentionally-missing-run'], store)
        attack = '</pre><script>window.attacked=1</script><img src="https://invalid.example/pixel" onerror="window.attacked=2">'
        control = copy.deepcopy(control)
        control['runs'][0]['question'] = attack
        control['runs'][0]['answer'] = attack
        control['runs'][0]['references'][0]['title'] = attack
        write_report(control, output / 'control-only')
    assert report['summary'] == {'runs': 4, 'recorded_submissions': 3, 'recorded_uncompleted': 1, 'export_errors': 0}
    statuses = [r['recorded_status'] for r in report['runs']]
    assert statuses == ['submitted', 'submitted', 'turn_limit', 'submitted']
    assert report['runs'][2]['answer'] is None and report['runs'][2]['diagnostics']
    assert sum(len(r['references']) for r in report['runs']) == 6
    assert all(not r['is_current_generation'] for row in report['runs'][:2] for r in row['references'])
    assert all(r['is_current_generation'] for r in report['runs'][3]['references'])
    assert files(output / 'first') == files(output / 'repeat')
    assert before == [files(p) for p in cases] and store_before == files(store) and not connections
    assert 'torch' not in sys.modules and 'transformers' not in sys.modules
    for path in (output / 'first').iterdir():
        text = path.read_text()
        assert all(part not in text for part in ['"excerpt"', '"choices"', '"messages"', '/data1/', '/tmp/agentlab-', 'http://127.0.0.1'])
    result = {'ready': True, 'real_closed_runs': 4, 'recorded_statuses_preserved': statuses,
              'application_summary': report['summary'], 'exact_PDF_references_read_back': 6,
              'old_historical_and_new_current_versions_preserved': True,
              'repeat_export_bytes_identical': True, 'original_runs_and_store_hashes_unchanged': True,
              'new_generation_requests': 0, 'new_embedding_forwards': 0,
              'network_connection_attempts': len(connections), 'GPU_used': False,
              'model_modules_not_loaded': True, 'wall_seconds': round(time.monotonic()-started, 3),
              'control_fixture_not_a_real_model_case': True,
              'report_files': {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size}
                               for p in (output / 'first').iterdir()}}
    (output / 'application-result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__': run(*map(Path, sys.argv[1:]))
