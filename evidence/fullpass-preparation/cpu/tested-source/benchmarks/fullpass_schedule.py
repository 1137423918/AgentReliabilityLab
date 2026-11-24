"""One-pass, whole-example paired schedules with measured loss denominators.

The reference token target is a soft grouping goal, never a truncation cap.
Whole-example cuts avoid zero-active fragments introduced by splitting prose.
"""
from __future__ import annotations
import argparse
from bisect import bisect_left
from collections import Counter
import hashlib
import json
import math
from pathlib import Path


def packed(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(packed(value)).hexdigest()


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paired_rows(original, masked):
    assert original and len(original) == len(masked)
    assert len({r['id_sha256'] for r in original}) == len(original)
    pairs = {}
    for left, right in zip(original, masked):
        for key in ['id_sha256', 'component_sha256', 'input_ids', 'prompt_tokens', 'target_tokens']:
            assert left[key] == right[key], key
        p = left['prompt_tokens']; ids = left['input_ids']
        assert 1 <= p < len(ids) <= 4096
        assert left['labels'] == [-100]*p+ids[p:]
        assert len(right['labels']) == len(ids) and right['labels'][:p] == [-100]*p
        assert all(b == -100 or b == a for a, b in zip(left['labels'], right['labels']))
        full = sum(v != -100 for v in left['labels'][1:])
        active = sum(v != -100 for v in right['labels'][1:])
        assert full == left['target_tokens'] and active > 0, 'Never drop an empty-mask row'
        assert active == right['effective_target_tokens']
        assert full-active == right['masked_fixed_reason_tokens']
        pairs[left['id_sha256']] = (left, right, full, active)
    return pairs


def make_fullpass(original, masked, seed, target_labels=2048):
    assert type(seed) is int and target_labels > 0
    pairs = paired_rows(original, masked)
    order = sorted(pairs, key=lambda key: digest(['agentlab-fullpass-order-v1', seed, key]))
    cumulative = [0]
    for key in order:
        cumulative.append(cumulative[-1]+pairs[key][2])
    total = cumulative[-1]
    updates = min(len(order), max(1, math.ceil(total/target_labels)))
    cuts = [0]
    for step in range(1, updates):
        low, high = cuts[-1]+1, len(order)-(updates-step)
        insertion = bisect_left(cumulative, (total*step+updates-1)//updates)
        candidates = {max(low, min(high, insertion-1)), max(low, min(high, insertion))}
        cut = min(candidates, key=lambda i: (abs(cumulative[i]*updates-total*step), i))
        assert low <= cut <= high
        cuts.append(cut)
    cuts.append(len(order))
    steps = []
    for number, (a, b) in enumerate(zip(cuts, cuts[1:])):
        segments = []
        for key in order[a:b]:
            left, right, full, active = pairs[key]
            segments.append({'id_sha256': key, 'component_sha256': left['component_sha256'],
                'label_start': left['prompt_tokens'], 'label_end': len(left['input_ids']),
                'target_start': 0, 'target_end': full, 'sequence_tokens': len(left['input_ids']),
                'supervised_tokens': full, 'active_labels': {'reference': full, 'masked': active}})
        counts = {role: sum(s['active_labels'][role] for s in segments) for role in ['reference', 'masked']}
        assert segments and all(n > 0 for n in counts.values())
        steps.append({'optimizer_step': number, 'segments': segments, 'active_labels': counts})
    plan = {'seed': seed, 'scope': 'Exactly one whole-example pass; paired inputs/order/segments/updates, unequal active labels by design.',
        'reference_label_soft_target': target_labels, 'updates': updates, 'steps': steps,
        'order_sha256': digest(order), 'sequence_forwards': len(order), 'unique_examples': len(order),
        'input_token_exposures': sum(len(pairs[key][0]['input_ids']) for key in order),
        'training_active_labels': {role: sum(s['active_labels'][role] for s in steps) for role in ['reference', 'masked']},
        'all_original_supervised_labels_covered_once': True, 'no_target_or_context_truncation': True,
        'no_empty_rows_or_segments_dropped': True, 'last_update_actual_labels': steps[-1]['active_labels']}
    validate_fullpass(plan, original, masked)
    return plan


def validate_fullpass(plan, original, masked):
    pairs = paired_rows(original, masked)
    covered = Counter()
    exposures = 0
    totals = Counter()
    for number, step in enumerate(plan['steps']):
        assert step['optimizer_step'] == number and step['segments']
        actual = Counter()
        for segment in step['segments']:
            key = segment['id_sha256']; left, right, full, active = pairs[key]
            assert segment['component_sha256'] == left['component_sha256']
            assert segment['label_start'] == left['prompt_tokens']
            assert segment['label_end'] == len(left['input_ids'])
            assert segment['target_start'] == 0 and segment['target_end'] == full
            assert segment['supervised_tokens'] == full
            assert segment['sequence_tokens'] == len(left['input_ids'])
            assert segment['active_labels'] == {'reference': full, 'masked': active}
            actual.update(segment['active_labels']); covered[key] += 1; exposures += len(left['input_ids'])
        assert dict(actual) == step['active_labels'] and all(v > 0 for v in actual.values())
        totals.update(actual)
    assert covered == Counter({key: 1 for key in pairs}), 'Missing or repeated original example'
    assert len(plan['steps']) == plan['updates']
    assert len(covered) == plan['sequence_forwards'] == plan['unique_examples']
    assert exposures == plan['input_token_exposures']
    assert dict(totals) == plan['training_active_labels']
    assert sum(p[2] for p in pairs.values()) == totals['reference']
    assert sum(p[3] for p in pairs.values()) == totals['masked']
    flattened = [s['id_sha256'] for step in plan['steps'] for s in step['segments']]
    assert digest(flattened) == plan['order_sha256']
    assert plan['last_update_actual_labels'] == plan['steps'][-1]['active_labels']


def prepare(args):
    spec = json.loads(args.protocol.read_text())
    for name, expected in spec['data_sha256'].items():
        assert file_sha(args.data/name) == expected
    assert file_sha(args.masked) == spec['masked_data_sha256']
    load = lambda p: [json.loads(line) for line in p.read_text().splitlines()]
    original, masked = load(args.data/'train-tokenized.jsonl'), load(args.masked)
    assert len(original) == len(masked) == 3700
    args.output.mkdir(mode=0o700, exist_ok=False)
    summaries = {}
    for seed in spec['training_seeds']:
        plan = make_fullpass(original, masked, seed, spec['reference_label_soft_target'])
        assert plan['updates'] == 164 and plan['sequence_forwards'] == 3700
        assert plan['training_active_labels'] == {'reference': 335822, 'masked': 279751}
        path = args.output/('seed-%d-schedule.json'%seed)
        path.write_text(json.dumps(plan, indent=2)+'\n')
        summaries[str(seed)] = {k: v for k, v in plan.items() if k != 'steps'}
        summaries[str(seed)].update(schedule_sha256=file_sha(path),
            reference_per_update_labels=[s['active_labels']['reference'] for s in plan['steps']],
            masked_per_update_labels=[s['active_labels']['masked'] for s in plan['steps']],
            examples_per_update=[len(s['segments']) for s in plan['steps']])
    assert len({v['order_sha256'] for v in summaries.values()}) == len(spec['training_seeds'])
    for name, expected in spec['data_sha256'].items():
        assert file_sha(args.data/name) == expected
    assert file_sha(args.masked) == spec['masked_data_sha256']
    report = {'protocol_sha256': file_sha(args.protocol), 'seeds': summaries,
        'fresh_training_runs_executed': 0, 'model_forwards': 0, 'optimizer_updates': 0,
        'only_preparation_not_model_accuracy': True, 'old32step_schedules_unchanged': True}
    (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'seeds'}), flush=True)
    print(json.dumps({'seeds': {s: {k:v for k,v in row.items() if not k.endswith('labels') and k != 'examples_per_update'} for s,row in summaries.items()}}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['data', 'masked', 'protocol', 'output']:
        p.add_argument('--'+name, type=Path, required=True)
    prepare(p.parse_args())
