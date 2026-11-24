"""Durable LangGraph workbench for dependency-upgrade evidence.

Consumes pinned scanner reports and paired JUnit/source manifests. No model,
network provider, repository edits, test execution or deployment is implicit.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
from typing import TypedDict
import xml.etree.ElementTree as ET

from .evidence_audit import EvidenceCatalog, EvidenceError, _pointer
from .storage import admit_state_directory

GATE = {
    '/execution/candidate_prepared': True,
    '/resolution/exit_code': 0,
    '/resolution/original_requirements_changed': False,
    '/coverage/before_registry_complete': True,
    '/coverage/after_registry_complete': True,
    '/target/version_changed': True,
    '/target/remaining_advisory_match_count': 0,
    '/delta/new_package_advisory_match_count': 0,
}
ROOTS = ['/project', '/scope', '/coverage', '/execution', '/resolution', '/target', '/delta', '/provenance']


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def bounded(path, limit=5*1024**2):
    path = Path(path)
    if path.is_symlink(): raise ValueError('Evidence files must not be symlinks')
    with path.open('rb') as stream: raw = stream.read(limit+1)
    if len(raw) > limit: raise ValueError('Evidence file exceeds size limit')
    return raw


def atomic(path, raw):
    temporary = path.with_name(path.name+'.tmp')
    with temporary.open('wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)+'\n').encode()


def junit(raw):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper(): raise ValueError('DTD/entity declarations are not accepted')
    root = ET.fromstring(raw)
    if root.tag not in ['testsuite', 'testsuites']: raise ValueError('Expected JUnit test suite XML')
    cases = {}; counts = {'tests': 0, 'failures': 0, 'errors': 0, 'skipped': 0}
    for case in root.iter('testcase'):
        key = (case.get('classname', ''), case.get('name', ''))
        if not key[1] or key in cases: raise ValueError('Empty or repeated JUnit test identity')
        status = [tag for tag in ['failure', 'error', 'skipped'] if case.find(tag) is not None]
        if len(status) > 1: raise ValueError('Ambiguous JUnit test result')
        result = status[0] if status else 'passed'; cases[key] = result; counts['tests'] += 1
        if result != 'passed': counts[{'failure': 'failures', 'error': 'errors', 'skipped': 'skipped'}[result]] += 1
    if not cases or len(cases) > 100000: raise ValueError('JUnit must contain a bounded nonempty test set')
    return cases, counts


def load_compatibility(path, catalog):
    if path is None: return {}, {}
    path = Path(path); raw = bounded(path); spec = json.loads(raw)
    if spec.get('version') != 1 or not isinstance(spec.get('reports'), dict): raise ValueError('Unsupported compatibility manifest')
    if set(spec['reports'])-set(catalog.entries): raise ValueError('Compatibility manifest names unknown reports')
    observed = {}; binding = {'manifest': digest(raw)}
    for report_id, entry in spec['reports'].items():
        artifacts = {}
        for name in ['baseline_junit', 'candidate_junit', 'source_file_manifests']:
            item = entry[name]; content = bounded(path.parent/item['path'])
            if digest(content) != item['sha256']: raise ValueError('Compatibility artifact hash mismatch: '+name)
            artifacts[name] = content; binding[report_id+'/'+name] = digest(content)
        observed[report_id] = {'entry': entry, 'artifacts': artifacts}
    return observed, binding


def assess(document):
    facts = []
    for pointer, expected in GATE.items():
        try: value = _pointer(document, pointer)
        except EvidenceError: value = None
        if value is not None and type(value) is not type(expected): raise ValueError('Unexpected fact type at '+pointer)
        facts.append({'pointer': pointer, 'observed': value, 'required': expected,
                      'matched': value is not None and type(value) is type(expected) and value == expected})
    eligible = all(row['matched'] for row in facts)
    missing = any(row['observed'] is None for row in facts)
    return {'ready_for_scoped_tests': eligible, 'facts': facts,
            'status': 'ready_for_scoped_tests' if eligible else 'needs_evidence' if missing else 'blocked'}


def compatibility(document, supplied):
    if supplied is None: return {'status': 'not_recorded', 'tests_executed_by_workbench': False}
    entry, artifacts = supplied['entry'], supplied['artifacts']; project = document['project']; provenance = document['provenance']
    if entry['repository'] != project['repository'] or entry['commit'] != project['commit']: raise ValueError('Compatibility belongs to a different project snapshot')
    original = provenance['original_files']['uv.lock']['sha256']; candidate = provenance['candidate_lock_sha256']
    manifests = json.loads(artifacts['source_file_manifests'])
    if set(manifests) != {'baseline', 'candidate'}: raise ValueError('Expected both source manifests')
    before, after = manifests['baseline'], manifests['candidate']
    if set(before) != set(after) or before.get('uv.lock') != original or after.get('uv.lock') != candidate:
        raise ValueError('Source manifest and actual reviewed lock identities disagree')
    if not all(isinstance(v, str) and re.fullmatch('[a-f0-9]{64}', v) for side in [before, after] for v in side.values()):
        raise ValueError('Invalid source digest')
    differences = sorted(name for name in before if before[name] != after[name])
    if differences != ['uv.lock']: raise ValueError('Compatibility changed source or tests beyond the lock file')
    left, left_counts = junit(artifacts['baseline_junit']); right, right_counts = junit(artifacts['candidate_junit'])
    if set(left) != set(right): raise ValueError('Paired compatibility used different test identities')
    passed = all(status == 'passed' for status in [*left.values(), *right.values()])
    return {'status': 'passed_recorded_scope' if passed else 'failed_or_incomplete',
            'scope': entry['scope'], 'baseline': left_counts, 'candidate': right_counts,
            'same_test_identities': True, 'source_changes': differences, 'source_files': len(before),
            'artifact_sha256': {k: digest(v) for k, v in artifacts.items()},
            'tests_executed_by_workbench': False, 'deployment_approved': False}


def markdown(review):
    project = review['project']; gate = review['gate']; tests = review['compatibility']
    text = lambda value: str(value).replace('|', '\\|').replace('\n', ' ')
    lines = ['# Dependency review: '+text(project['repository']), '',
             'Snapshot: `'+text(project['tag'])+'` / `'+text(project['commit'])+'`', '',
             '**Status: '+review['status']+'**', '',
             'Target: '+text(review['target']['name'])+' — '+text(review['target']['before_versions'])+' → '+text(review['target']['after_versions']), '',
             '| Gate condition | Observed | Required | Matched |', '| --- | --- | --- | --- |']
    for row in gate['facts']:
        lines.append('| '+text(row['pointer'])+' | '+text(row['observed'])+' | '+text(row['required'])+' | '+text(row['matched'])+' |')
    lines += ['', 'Remaining affected registry resolutions: **'+text(review['remaining_affected_registry_resolutions'])+'**.', '',
              'Compatibility evidence: **'+tests['status']+'**.']
    if 'baseline' in tests:
        lines += ['', 'Same '+str(tests['baseline']['tests'])+' test identities in baseline and candidate; '+text(tests['scope']),
                  '', 'Baseline: '+text(tests['baseline'])+'; candidate: '+text(tests['candidate'])+'.']
    lines += ['', 'Next action: '+review['next_action'], '',
              'Source: ['+text(review['report_id'])+']('+review['source']['source_url']+')',
              'Report SHA256: `'+review['source']['sha256']+'`', '',
              'Historical locked-resolution evidence, including optional/development dependencies; advisory matches are not proof of exploitability. '
              'This workflow does not rescan current dependencies, run the recorded upstream tests, call a model, or approve deployment.', '']
    return '\n'.join(lines).encode()


class ReviewState(TypedDict, total=False):
    report_id: str
    document: dict
    source: dict
    gate: dict
    compatibility: dict
    review: dict


def run_workbench(root, manifest, run_dir, report_ids=None, compatibility_manifest=None, *, _interrupt_after=None):
    from langgraph.graph import StateGraph, START, END
    from langgraph.checkpoint.sqlite import SqliteSaver
    root, manifest, run_dir = Path(root), Path(manifest), Path(run_dir)
    catalog = EvidenceCatalog(root, manifest); selected = sorted(set(report_ids or catalog.entries))
    if not selected or set(selected)-set(catalog.entries): raise ValueError('Unknown or empty report selection')
    supplied, bound = load_compatibility(compatibility_manifest, catalog)
    admit_state_directory(run_dir); run_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    control_files = ['workbench.lock', 'workbench-manifest.json', 'workbench.sqlite', 'workbench.sqlite-wal',
                     'workbench.sqlite-shm', 'summary.json', 'summary.md', 'reviews']
    if any((run_dir/name).is_symlink() for name in control_files): raise ValueError('Run control files cannot be symlinks')
    lock = (run_dir/'workbench.lock').open('a'); fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        review_dir = run_dir/'reviews'; review_dir.mkdir(mode=0o700, exist_ok=True)
        identity = {'schema': 1, 'implementation_sha256': {
                'workbench': digest(Path(__file__).read_bytes()),
                'evidence_catalog': digest(Path(EvidenceCatalog.__init__.__code__.co_filename).read_bytes()),
                'storage': digest(Path(admit_state_directory.__code__.co_filename).read_bytes())},
            'catalog_sha256': digest(bounded(manifest)), 'selected': selected, 'compatibility': bound,
            'frameworks': {p: importlib.metadata.version(p) for p in ['langgraph', 'langgraph-checkpoint-sqlite']}}
        identity_path = run_dir/'workbench-manifest.json'
        if identity_path.exists():
            if json.loads(identity_path.read_text()) != identity: raise ValueError('Run inputs or implementation changed; use a new run directory')
        else:
            if (run_dir/'workbench.sqlite').exists() or any(review_dir.iterdir()):
                raise ValueError('Unbound prior state exists; use a new run directory')
            atomic(identity_path, json_bytes(identity))
        def collect(state):
            received = json.loads(catalog.read_report(state['report_id'], ROOTS))
            document = {name[1:]: value for name, value in received['values'].items()}
            if not isinstance(document.get('project'), dict): raise ValueError('Expected a dependency report project')
            return {'document': document, 'source': {k: received[k] for k in ['report_id', 'sha256', 'source_url']}}
        def evaluate(state):
            return {'gate': assess(state['document']), 'compatibility': compatibility(state['document'], supplied.get(state['report_id']))}
        def compose(state):
            gate, tests, document = state['gate'], state['compatibility'], state['document']
            status = gate['status']
            if gate['ready_for_scoped_tests']:
                if tests['status'] == 'passed_recorded_scope': status = 'scoped_tests_passed'
                elif tests['status'] == 'failed_or_incomplete': status = 'compatibility_failed_or_incomplete'
            next_action = {'blocked': 'Resolve the failed upgrade conditions before integration testing.',
                'needs_evidence': 'Collect missing scan/resolver evidence.',
                'ready_for_scoped_tests': 'Run and record relevant upstream compatibility tests.',
                'scoped_tests_passed': 'Review residual advisories and broader CI before a release decision.',
                'compatibility_failed_or_incomplete': 'Investigate failing or incomplete compatibility tests.'}[status]
            return {'review': {'report_id': state['report_id'], 'project': document['project'], 'source': state['source'],
                'target': {k: document['target'][k] for k in ['name', 'before_versions', 'after_versions']},
                'gate': gate, 'compatibility': tests, 'status': status, 'next_action': next_action,
                'remaining_affected_registry_resolutions': document['delta']['remaining_affected_registry_resolutions'],
                'model_calls': 0, 'deployment_approved': False}}
        builder = StateGraph(ReviewState); builder.add_node('collect', collect); builder.add_node('evaluate', evaluate); builder.add_node('compose', compose)
        builder.add_edge(START, 'collect'); builder.add_edge('collect', 'evaluate'); builder.add_edge('evaluate', 'compose'); builder.add_edge('compose', END)
        reviews = []; completed_reused = 0; paused = []
        with SqliteSaver.from_conn_string(str(run_dir/'workbench.sqlite')) as saver:
            graph = builder.compile(checkpointer=saver)
            for report_id in selected:
                config = {'configurable': {'thread_id': report_id}}
                before = graph.get_state(config); has_state = bool(before.values)
                if has_state and not before.next: completed_reused += 1
                else:
                    graph.invoke(None if has_state else {'report_id': report_id}, config,
                                 durability='sync', interrupt_after=_interrupt_after)
                snapshot = graph.get_state(config)
                if snapshot.next: paused.append(report_id); continue
                review = snapshot.values['review']; outputs = [(report_id+'.json', json_bytes(review)), (report_id+'.md', markdown(review))]
                for name, raw in outputs:
                    path = review_dir/name
                    if path.is_symlink(): raise ValueError('Review outputs cannot be symlinks')
                    if path.exists() and path.read_bytes() != raw: raise ValueError('Review output changed since checkpoint')
                    if not path.exists(): atomic(path, raw)
                reviews.append(review)
        result = {'completed': not paused, 'reports': len(reviews), 'reused_completed': completed_reused,
                  'pending': paused, 'reviews': [{'report_id': r['report_id'], 'status': r['status'],
                     'remaining_affected_registry_resolutions': r['remaining_affected_registry_resolutions']} for r in reviews],
                  'frameworks': identity['frameworks'], 'model_calls': 0, 'GPU_used': False}
        if not paused:
            atomic(run_dir/'summary.json', json_bytes(result))
            table = '# Dependency review batch\n\n| Report | Status | Remaining registry resolutions |\n| --- | --- | ---: |\n'
            table += ''.join('| ['+r['report_id']+'](reviews/'+r['report_id']+'.md) | '+r['status']+' | '+str(r['remaining_affected_registry_resolutions'])+' |\n' for r in reviews)
            atomic(run_dir/'summary.md', table.encode())
        return result
    finally:
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['root', 'manifest', 'run-dir']: parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--report', action='append'); parser.add_argument('--compatibility-manifest', type=Path)
    args = parser.parse_args()
    try:
        result = run_workbench(args.root, args.manifest, args.run_dir, args.report, args.compatibility_manifest)
    except (ValueError, EvidenceError, OSError, KeyError) as error:
        parser.exit(2, 'Review failed: '+str(error)+'\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
