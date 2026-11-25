"""Prepare private offline source review and validate portable reviewer notes.

Uses stopped research runs and archived citations. It neither executes the graph
nor generates or grades answers. Notes are declarations, not signed attestations.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

from .request_budget import digest
from .research_report import ReportError, build_report


MAX_BUNDLE_BYTES = 2 * 1024**2
MAX_NOTES_BYTES = 1024**2


def build_review(directories, store):
    """Embed only the exact passages cited by the recorded accepted answers."""
    from agentlab_research.research_library import citation

    report = build_report(directories, store)
    entries = []
    for position, run in enumerate(report['runs']):
        passages = []
        error = None
        try:
            for reference in run['references']:
                actual = citation(store, reference['citation_id'])
                if any(actual.get(key) != value for key, value in reference.items() if key != 'ref'):
                    raise ReportError('Citation changed while preparing review')
                excerpt = actual['excerpt']
                passages.append({'ref': reference['ref'], 'citation_id': actual['citation_id'],
                                 'excerpt': excerpt,
                                 'excerpt_sha256': hashlib.sha256(excerpt.encode()).hexdigest()})
        except (OSError, ValueError, KeyError, TypeError):
            passages = []
            error = 'citation_unavailable'
        identity = {'position': position, 'run': run, 'passages': passages, 'evidence_error': error}
        entries.append({'entry_id': digest(identity), 'answer_sha256': digest(run.get('answer')),
                        'reviewable': run['export_status'] == 'ready' and run['recorded_status'] == 'submitted' and error is None,
                        'run': copy.deepcopy(run), 'passages': passages, 'evidence_error': error})
    payload = {'version': 1, 'scope': 'Private source passages and separate reviewer declarations; no answer regeneration or automatic semantic judgment.',
               'semantic_entailment_checked': False, 'entries': entries}
    bundle = {**payload, 'bundle_sha256': digest(payload)}
    if len(json.dumps(bundle, ensure_ascii=False).encode()) > MAX_BUNDLE_BYTES:
        raise ReportError('Review bundle exceeds 2MiB')
    return bundle


def check_bundle(bundle):
    if not isinstance(bundle, dict) or set(bundle) != {'version', 'scope', 'semantic_entailment_checked', 'entries', 'bundle_sha256'}:
        raise ReportError('Unsupported review bundle')
    payload = {k: v for k, v in bundle.items() if k != 'bundle_sha256'}
    if type(bundle['version']) is not int or bundle['version'] != 1 or bundle['semantic_entailment_checked'] is not False or digest(payload) != bundle['bundle_sha256']:
        raise ReportError('Review bundle identity differs')
    entries = bundle['entries']
    if not isinstance(entries, list) or not 1 <= len(entries) <= 16 or any(not isinstance(e, dict) for e in entries):
        raise ReportError('Expected 1 to 16 review entries')
    for position, entry in enumerate(entries):
        if set(entry) != {'entry_id', 'answer_sha256', 'reviewable', 'run', 'passages', 'evidence_error'}:
            raise ReportError('Unsupported review bundle entry')
        run = entry['run']
        passages = entry['passages']
        if not isinstance(run, dict) or not isinstance(passages, list) or len(passages) > 6 or entry['evidence_error'] not in (None, 'citation_unavailable'):
            raise ReportError('Invalid source review record')
        expected = run['export_status'] == 'ready' and run['recorded_status'] == 'submitted' and entry['evidence_error'] is None
        if type(entry['reviewable']) is not bool or entry['reviewable'] != expected:
            raise ReportError('Review availability differs from recorded status')
        refs = {ref['citation_id']: ref for ref in run['references']}
        seen = set()
        for passage in passages:
            if not isinstance(passage, dict) or set(passage) != {'ref', 'citation_id', 'excerpt', 'excerpt_sha256'}:
                raise ReportError('Invalid embedded source passage')
            citation_id = passage['citation_id']
            if not isinstance(citation_id, str) or citation_id not in refs or citation_id in seen or passage['ref'] != refs[citation_id]['ref']:
                raise ReportError('Embedded source passage does not belong to answer')
            seen.add(citation_id)
            if not isinstance(passage['excerpt'], str) or hashlib.sha256(passage['excerpt'].encode()).hexdigest() != passage['excerpt_sha256']:
                raise ReportError('Embedded source text fingerprint differs')
        if (entry['evidence_error'] is None and seen != set(refs)) or (entry['evidence_error'] is not None and passages):
            raise ReportError('Embedded citation inventory differs')
        identity = {'position': position, 'run': entry['run'], 'passages': entry['passages'], 'evidence_error': entry['evidence_error']}
        if entry['entry_id'] != digest(identity) or entry['answer_sha256'] != digest(entry['run'].get('answer')):
            raise ReportError('Review entry identity differs')
    if len({e['entry_id'] for e in entries}) != len(entries):
        raise ReportError('Repeated review entry')


def initial_decisions(bundle):
    check_bundle(bundle)
    return {'version': 1, 'bundle_sha256': bundle['bundle_sha256'], 'reviewer': '',
            'entries': [{'entry_id': e['entry_id'], 'answer_sha256': e['answer_sha256'],
                         'decision': 'pending' if e['reviewable'] else 'unavailable', 'notes': ''}
                        for e in bundle['entries']]}


def validate_decisions(bundle, decisions):
    """Reject stale/mixed bundles atomically, without altering either input."""
    check_bundle(bundle)
    if not isinstance(decisions, dict) or set(decisions) != {'version', 'bundle_sha256', 'reviewer', 'entries'}:
        raise ReportError('Unsupported review notes fields')
    if type(decisions['version']) is not int or decisions['version'] != 1 or decisions['bundle_sha256'] != bundle['bundle_sha256']:
        raise ReportError('Notes belong to a different review bundle')
    if not isinstance(decisions['reviewer'], str) or len(decisions['reviewer']) > 120:
        raise ReportError('Reviewer label exceeds 120 characters')
    rows = decisions['entries']
    if not isinstance(rows, list) or len(rows) != len(bundle['entries']):
        raise ReportError('Review notes must cover every entry exactly once')
    by_id = {entry['entry_id']: entry for entry in bundle['entries']}
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'entry_id', 'answer_sha256', 'decision', 'notes'}:
            raise ReportError('Unsupported review entry fields')
        key = row['entry_id']
        if not isinstance(key, str) or key not in by_id or key in seen:
            raise ReportError('Unknown or repeated review entry')
        seen.add(key)
        entry = by_id[key]
        choices = ('pending', 'checked', 'needs_changes') if entry['reviewable'] else ('unavailable',)
        if row['answer_sha256'] != entry['answer_sha256'] or row['decision'] not in choices:
            raise ReportError('Answer identity or review decision differs')
        if not isinstance(row['notes'], str) or len(row['notes']) > 1000:
            raise ReportError('Use notes up to 1000 characters')
    # Original order is restored, even if a portable file reordered its entries.
    ordered = {r['entry_id']: r for r in rows}
    return {'version': 1, 'bundle_sha256': bundle['bundle_sha256'], 'reviewer': decisions['reviewer'],
            'entries': [copy.deepcopy(ordered[e['entry_id']]) for e in bundle['entries']]}


def write_review(bundle, output):
    from .research_review_view import review_html

    check_bundle(bundle)
    artifacts = {
        'source-review.json': (json.dumps(bundle, ensure_ascii=False, indent=2) + '\n').encode(),
        'source-review.html': review_html(bundle).encode(),
        'review-notes.json': (json.dumps(initial_decisions(bundle), ensure_ascii=False, indent=2) + '\n').encode(),
    }
    if len(artifacts['source-review.json']) > MAX_BUNDLE_BYTES or len(artifacts['source-review.html']) > 4 * 1024**2:
        raise ReportError('Review output exceeds size limit')
    manifest = {'files': {name: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                          for name, raw in artifacts.items()}}
    artifacts['review-manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    output = Path(output)
    output.mkdir(mode=0o700, exist_ok=False)
    for name, raw in artifacts.items():
        with (output / name).open('xb') as stream:
            (output / name).chmod(0o600)
            stream.write(raw)


def load_object(path, limit):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ReportError('Review input is missing or too large')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ReportError('Expected a review object')
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare', help='Prepare a private source review from stopped local runs')
    prepare.add_argument('--run-dir', type=Path, action='append', required=True)
    prepare.add_argument('--store', type=Path, required=True)
    prepare.add_argument('--output', type=Path, required=True)
    check = sub.add_parser('check-notes', help='Validate saved notes against their exact source bundle')
    check.add_argument('--bundle', type=Path, required=True)
    check.add_argument('--notes', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'check-notes':
        notes = validate_decisions(load_object(args.bundle, MAX_BUNDLE_BYTES), load_object(args.notes, MAX_NOTES_BYTES))
        print(json.dumps({'entries': len(notes['entries']), 'decisions': {name: sum(e['decision'] == name for e in notes['entries'])
                          for name in ['pending', 'checked', 'needs_changes', 'unavailable']}, 'reviewer_identity_verified': False}))
        return 0
    output = args.output.resolve()
    if any(root.resolve() == output or root.resolve() in output.parents for root in [*args.run_dir, args.store]):
        parser.error('Write review bundles outside run/store directories')
    bundle = build_review(args.run_dir, args.store)
    write_review(bundle, output)
    unavailable = sum(not e['reviewable'] for e in bundle['entries'])
    print(json.dumps({'entries': len(bundle['entries']), 'reviewable': len(bundle['entries']) - unavailable,
                      'unavailable': unavailable, 'model_calls': 0}))
    return 2 if any(e['run']['export_status'] == 'error' or e['evidence_error'] for e in bundle['entries']) else 0


if __name__ == '__main__':
    raise SystemExit(main())
