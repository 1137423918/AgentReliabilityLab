"""Causal target selection for matched full-context loss-mask ablations."""
from __future__ import annotations


def active_causal_targets(row, start, end):
    ids, labels = row['input_ids'], row['labels']
    assert len(ids) == len(labels) and 1 <= start < end <= len(ids)
    positions = [p for p in range(start, end) if labels[p] != -100]
    assert positions, 'Empty active-label segment is not admitted'
    assert all(labels[p] == ids[p] for p in positions)
    return [p-1 for p in positions], [labels[p] for p in positions]


def validate_pair(original, masked):
    assert len(original) == len(masked) == 3700
    assert len({r['id_sha256'] for r in original}) == 3700
    removed = active = 0
    for left, right in zip(original, masked):
        for key in ['id_sha256', 'component_sha256', 'input_ids', 'prompt_tokens', 'target_tokens']:
            assert left[key] == right[key], key
        assert len(left['labels']) == len(right['labels'])
        assert all(b == -100 or b == a for a, b in zip(left['labels'], right['labels']))
        n = sum(x != -100 for x in right['labels'][1:])
        cut = sum(a != -100 and b == -100 for a, b in zip(left['labels'], right['labels']))
        assert n == right['effective_target_tokens'] > 0
        assert cut == right['masked_fixed_reason_tokens']
        assert n + cut == left['target_tokens']
        active += n
        removed += cut
    return {'rows': len(original), 'removed_fixed_reason_labels': removed,
            'retained_full_dataset_labels': active, 'inputs_order_and_original_targets_unchanged': True}


def update_label_count(step, rows):
    total = 0
    for segment in step['segments']:
        row = rows[segment['id_sha256']]
        a, b = segment['label_start'], segment['label_end']
        positions, _ = active_causal_targets(row, a, b)
        total += len(positions)
    assert total > 0
    return total


if __name__ == '__main__':
    import argparse
    import hashlib
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['data', 'mask-data', 'protocol', 'output']:
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.protocol.read_text())
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    for name, expected in spec['data_sha256'].items():
        assert sha(args.data/name) == expected
    assert sha(args.mask_data/'train-masked-tokenized.jsonl') == spec['masked_data_sha256']
    load = lambda p: [json.loads(line) for line in p.read_text().splitlines()]
    original = load(args.data/'train-tokenized.jsonl')
    masked = load(args.mask_data/'train-masked-tokenized.jsonl')
    result = validate_pair(original, masked)
    schedule = json.loads((args.data/'train-schedule.json').read_text())
    result['profiles'] = {}
    for profile, rows in [('reference', original), ('masked', masked)]:
        index = {r['id_sha256']: r for r in rows}
        counts = [update_label_count(step, index) for step in schedule['steps']]
        assert counts == spec['step_active_labels'][profile]
        assert sum(counts) == spec['training_active_labels'][profile]
        result['profiles'][profile] = {'per_update_active_labels': counts, 'total_active_labels': sum(counts)}
    assert schedule['sequence_forwards'] == 774 and schedule['input_token_exposures'] == 573843
    result.update(training_segments=774, input_token_exposures=573843, optimizer_updates_planned=32,
                  optimizer_updates_executed=0, model_calls=0, no_empty_segments=True,
                  masked_file_sha256=spec['masked_data_sha256'])
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result), flush=True)
