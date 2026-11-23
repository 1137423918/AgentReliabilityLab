"""Bind reference answers only after validating the frozen question admission.

Reads no model predictions. Reference-derived witnesses are private checker
controls, not model outcomes; no case is replaced after seeing references.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from benchmarks.bfcl_transfer_scoring import canonical_witness, digest, load_python_scorer


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def run(args):
    spec = json.loads(args.protocol.read_text())
    assert file_sha(args.admission/'admission.json') == spec['admission_sha256']
    assert file_sha(args.admission/'private/selected-inputs.jsonl') == spec['private_inputs_sha256']
    admission = json.loads((args.admission/'admission.json').read_text())
    selected = admission['selected']
    assert digest([r['id'] for r in selected]) == spec['selection_order_sha256']
    assert admission['gold_files_read'] == admission['model_calls'] == 0
    inputs = [json.loads(line) for line in (args.admission/'private/selected-inputs.jsonl').read_text().splitlines()]
    assert [r['id'] for r in inputs] == [r['id'] for r in selected]
    assert len(inputs) == 250
    for inp, meta in zip(inputs, selected):
        assert digest(inp['row']) == meta['source_row_sha256']
        assert digest(inp['messages']) == meta['prompt_sha256']
    # Complete admission/source identity checks BEFORE opening any answer file.
    for name, expected in spec['source_sha256'].items():
        assert file_sha(args.source/name) == expected, name
    args.output.mkdir(mode=0o700, exist_ok=False)
    private = args.output/'private'
    private.mkdir(mode=0o700)
    lookup = {}
    reference_counts = {}
    for name, expected in spec['gold_files'].items():
        raw = (args.gold/name).read_bytes()
        assert len(raw) == expected['bytes']
        assert hashlib.sha1(('blob '+str(len(raw))+'\0').encode()+raw).hexdigest() == expected['git_blob_sha1']
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        reference_counts[name] = len(rows)
        for row in rows:
            assert isinstance(row['id'], str) and isinstance(row['ground_truth'], list)
            assert row['id'] not in lookup
            lookup[row['id']] = row
    score, identities = load_python_scorer(args.source/'upstream')
    bound = []
    metadata = []
    controls = Counter()
    for inp, meta in zip(inputs, selected):
        category = inp['category']
        if category == 'irrelevance':
            gold_row = {'id': inp['id'], 'ground_truth': []}
            witness = '[]'
        else:
            gold_row = lookup[inp['id']]
            witness = canonical_witness(gold_row['ground_truth'], inp['row']['function'])
        result = score(witness, inp['row'], gold_row['ground_truth'], category)
        controls['cases'] += 1
        controls['witness_matches'] += result['guarded_valid'] is True
        controls['guard_rejections'] += result['guard_rejected']
        controls['scorer_errors'] += 'scorer_error_type' in result
        controls['eval_attempts'] += result['eval_attempts']
        bound.append({'id': inp['id'], 'category': category, 'gold': gold_row['ground_truth'],
                      'gold_row_sha256': digest(gold_row), 'witness': witness, 'witness_control': result})
        metadata.append({'id': inp['id'], 'category': category,
                         'source_input_sha256': meta['source_row_sha256'],
                         'gold_row_sha256': digest(gold_row), 'witness_sha256': hashlib.sha256(witness.encode()).hexdigest(),
                         'witness_control': result, 'reference_derived_not_model': True})
    (private/'bound-gold-and-witnesses.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in bound))
    (args.output/'binding-metadata.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in metadata))
    save(args.output/'checker-source-identity.json', identities)
    report = {'admission_sha256': spec['admission_sha256'], 'selection_order_sha256': spec['selection_order_sha256'],
              'protocol_sha256': file_sha(args.protocol), 'bound_cases': len(bound),
              'by_category': dict(Counter(r['category'] for r in bound)), 'reference_file_rows': reference_counts,
              'reference_derived_checker_controls': dict(controls),
              'private_bound_gold_sha256': file_sha(private/'bound-gold-and-witnesses.jsonl'),
              'no_model_predictions_or_training': True, 'no_cases_replaced_or_gold_changed': True,
              'not_full_official_BFCL_harness': True,
              'metric_policy': 'Guarded BFCL-derived Python AST match. Outer guard rejects BinOp/Lambda or response/AST resource overages with no credit; other decoding/matching functions unchanged. Preserve official irrelevance parse-failure credit and report decode/empty-list counts separately.',
              'scorer_ready': controls['cases'] == controls['witness_matches'] == 250 and not controls['guard_rejections'] and not controls['scorer_errors'] and not controls['eval_attempts']}
    assert file_sha(args.admission/'admission.json') == spec['admission_sha256']
    assert file_sha(args.admission/'private/selected-inputs.jsonl') == spec['private_inputs_sha256']
    save(args.output/'report.json', report)
    print(json.dumps(report), flush=True)
    assert report['scorer_ready'], 'Reference controls failed; keep all frozen cases, no model inference or replacement'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'admission', 'gold', 'protocol', 'output']:
        parser.add_argument('--'+name, type=Path, required=True)
    run(parser.parse_args())
