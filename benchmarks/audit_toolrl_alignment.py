"""Audit fixed scaffold supervision and completed saved tool-call outcomes.

CPU-only: no model/scorer/response-parser import, and no modification of input
data or completed generation records. Prepared loss masks remain private.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re
import time


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(packed(value)).hexdigest()


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def constant_reason_span(answer, constants):
    match = re.match(r"<think>(.*?)</think>", answer, re.S)
    if not match or match.group(1).strip() not in constants:
        return None
    text = match.group(1)
    start = match.start(1) + len(text) - len(text.lstrip())
    return start, start + len(text.strip())


def mask_constant_offsets(labels, offsets, span):
    result = list(labels)
    if span is None:
        return result
    start, end = span
    assert len(labels) == len(offsets)
    for index, (left, right) in enumerate(offsets):
        if result[index] != -100 and start <= left < right <= end:
            result[index] = -100
    return result


def validate_progress(raw, expected):
    state = json.loads(raw)
    checksum = state.pop('checksum')
    assert digest(state) == checksum
    assert state['owner_sha256'] == expected['owner_sha256']
    assert len(state['attempts']) == expected['attempts']
    assert len(state['results']) == sum(expected['known_by_variant'].values())
    for sequence, attempt in enumerate(state['attempts'], 1):
        assert attempt['sequence'] == sequence
        assert attempt['state'] in {'reserved', 'completed'}
    counts = Counter()
    for key, item in state['results'].items():
        variant, ordinal = key.split(':')
        ordinal = int(ordinal)
        assert variant in expected['known_by_variant']
        assert 1 <= ordinal <= expected['known_by_variant'][variant]
        assert digest(item['row']) == item['row_sha256']
        attempt = state['attempts'][item['attempt_sequence'] - 1]
        assert attempt['sequence'] == item['attempt_sequence']
        assert attempt['state'] == 'completed'
        assert attempt['variant'] == variant and attempt['case_index'] == ordinal
        counts[variant] += 1
    assert dict(counts) == expected['known_by_variant']
    unknown = sum(item['state'] == 'reserved' for item in state['attempts'])
    assert unknown == expected['unknown_still_charged']
    assert len(state['attempts']) - len(state['results']) == unknown
    return state


def output_features(row, constants):
    prediction = row['prediction']
    text = prediction['raw_output']
    calls = prediction['tool_calls']
    assert type(row['official_score']['correct']) is bool
    assert math.isfinite(row['official_score']['score'])
    return {
        'stored_official_correct': row['official_score']['correct'],
        'stored_official_score': row['official_score']['score'],
        'parsed_call_count': len(calls),
        'no_parsed_calls': not calls,
        'has_think_marker': '<think>' in text,
        'has_tool_call_marker': '<tool_call>' in text,
        'has_response_marker': '<response>' in text,
        'contains_published_fixed_reasoning': any(value in text for value in constants),
        'raw_output_sha256': hashlib.sha256(text.encode()).hexdigest(),
        'prediction_sha256': digest(prediction),
        'required_key_screen': row['required_key_screen'],
        'ended_with_eos': row['generation_metadata']['ended_with_eos'],
        'generation_error_present': bool(prediction.get('error')),
    }


def summarize_outputs(rows):
    flags = ['no_parsed_calls', 'has_think_marker', 'has_tool_call_marker',
             'has_response_marker', 'contains_published_fixed_reasoning',
             'generation_error_present']
    return {'n': len(rows), 'correct': sum(r['stored_official_correct'] for r in rows),
            **{flag: sum(r[flag] for r in rows) for flag in flags},
            'correct_without_parsed_calls': sum(r['stored_official_correct'] and r['no_parsed_calls'] for r in rows)}


def save(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def jsonl(path, values):
    path.write_text(''.join(json.dumps(value)+'\n' for value in values))


def run(args):
    import pyarrow.parquet as pq
    from transformers import AutoTokenizer

    began = time.monotonic()
    spec = json.loads(args.protocol.read_text())
    for name, expected in spec['data_sha256'].items():
        assert file_sha(args.data/name) == expected, name
    assert file_sha(args.ledger) == spec['ledger_sha256']
    assert file_sha(args.converter) == spec['converter_sha256']
    constants = set()
    for node in ast.parse(args.converter.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {'THINK_TOOL_CALL', 'THINK_RESPONSE'} for t in node.targets):
            constants.add(ast.literal_eval(node.value))
    assert len(constants) == 2 and all(isinstance(text, str) and text for text in constants)
    state = validate_progress(args.ledger.read_bytes(), spec['progress'])
    args.output.mkdir(mode=0o700, exist_ok=False)
    private = args.output/'private'
    private.mkdir(mode=0o700)
    tokenizer = AutoTokenizer.from_pretrained(str(args.model), local_files_only=True, trust_remote_code=False)
    assert tokenizer.is_fast
    metadata = []
    reports = {}
    for variant, expected_count in spec['data_rows'].items():
        rows = pq.ParquetFile(args.data/(variant+'.parquet')).read(use_threads=False).to_pylist()
        cached = [json.loads(line) for line in (args.data/(variant+'-tokenized.jsonl')).read_text().splitlines()]
        assert len(rows) == len(cached) == expected_count
        totals = Counter()
        shapes = Counter()
        masked_rows = []
        for index, (row, original) in enumerate(zip(rows, cached)):
            answer = row['reward_model']['ground_truth']
            assert hashlib.sha256(row['extra_info']['original_id'].encode()).hexdigest() == original['id_sha256']
            prompt_text = tokenizer.apply_chat_template(row['prompt'], tokenize=False, add_generation_prompt=True)
            full_text = tokenizer.apply_chat_template(row['prompt']+[{'role': 'assistant', 'content': answer}], tokenize=False, add_generation_prompt=False)
            assert full_text.startswith(prompt_text+answer)
            encoded = tokenizer(full_text, add_special_tokens=False, return_offsets_mapping=True)
            assert encoded['input_ids'] == original['input_ids']
            p = original['prompt_tokens']
            assert original['labels'] == [-100]*p + original['input_ids'][p:]
            relative = constant_reason_span(answer, constants)
            span = tuple(len(prompt_text)+value for value in relative) if relative else None
            labels = mask_constant_offsets(original['labels'], encoded['offset_mapping'], span)
            removed = sum(a != -100 and b == -100 for a, b in zip(original['labels'], labels))
            active = sum(value != -100 for value in labels[1:])
            assert active + removed == original['target_tokens'] and active > 0
            assert all(b in (-100, a) for a, b in zip(original['labels'], labels))
            if '<tool_call>' in answer:
                shape = 'tool_call'
            elif '<response>' in answer:
                shape = 'response_without_tool_call'
            else:
                shape = 'other'
            shapes[shape] += 1
            totals.update(rows=1, original_supervised_labels=original['target_tokens'],
                          exact_constant_reason_rows=relative is not None, masked_constant_labels=removed,
                          retained_supervised_labels=active)
            metadata.append({'variant': variant, 'ordinal': index+1, 'id_sha256': original['id_sha256'],
                             'component_sha256': original['component_sha256'], 'shape': shape,
                             'original_labels': original['target_tokens'], 'masked_constant_labels': removed,
                             'retained_labels': active, 'source_row_sha256': digest(row),
                             'input_ids_sha256': digest(original['input_ids']),
                             'original_labels_sha256': digest(original['labels']), 'masked_labels_sha256': digest(labels)})
            masked_rows.append({**original, 'labels': labels, 'effective_target_tokens': active,
                                'masked_fixed_reason_tokens': removed})
        report = {**dict(totals), 'target_shapes': dict(shapes),
                  'masked_label_fraction': totals['masked_constant_labels']/totals['original_supervised_labels']}
        if variant in {'train', 'mixed_train'}:
            lookup = {row['id_sha256']: row for row in masked_rows}
            plan = json.loads((args.data/(variant+'-schedule.json')).read_text())
            assert len(plan['steps']) == 32 and plan['loss_tokens_total'] == 65536
            steps = []
            for step in plan['steps']:
                assert sum(s['supervised_tokens'] for s in step['segments']) == 2048
                active = segments_without_labels = exposures = 0
                for segment in step['segments']:
                    row = lookup[segment['id_sha256']]
                    a, b = segment['label_start'], segment['label_end']
                    n = sum(value != -100 for value in row['labels'][a:b])
                    active += n
                    segments_without_labels += n == 0
                    exposures += len(row['input_ids'])
                assert active > 0
                steps.append({'update': step['optimizer_step']+1, 'original_labels': 2048,
                              'retained_labels': active, 'zero_label_segments': segments_without_labels,
                              'planned_input_token_exposures': exposures,
                              'segments': len(step['segments'])})
            report['fixed32_schedule'] = {
                'updates': len(steps), 'original_labels': 65536,
                'retained_labels': sum(step['retained_labels'] for step in steps),
                'input_token_exposures': sum(step['planned_input_token_exposures'] for step in steps),
                'zero_label_segments': sum(step['zero_label_segments'] for step in steps), 'steps': steps,
                'input_ids_order_and_segment_boundaries_unchanged': True,
                'optimizer_or_training_run': False,
            }
            jsonl(private/(variant+'-masked-tokenized.jsonl'), masked_rows)
        reports[variant] = report
        print(json.dumps({'phase': 'supervision', 'variant': variant, 'report': {k: v for k, v in report.items() if k != 'fixed32_schedule'}}), flush=True)
    saved = []
    by_variant = {}
    for variant, n in spec['progress']['known_by_variant'].items():
        part = []
        for ordinal in range(1, n+1):
            row = state['results'][variant+':'+str(ordinal)]['row']
            features = {'variant': variant, 'ordinal': ordinal, 'benchmark': row['benchmark'],
                        'id_sha256': hashlib.sha256(row['id'].encode()).hexdigest(),
                        'sample_sha256': row['sample_sha256'], **output_features(row, constants)}
            part.append(features)
        by_variant[variant] = part
        assert sum(r['stored_official_correct'] for r in part) == spec['progress']['correct_by_variant'][variant]
        saved.extend(part)
    paired = {}
    for candidate, reference in [('full32', 'base'), ('mixed32', 'base'), ('mixed32', 'full32')]:
        groups = defaultdict(Counter)
        for c, r in zip(by_variant[candidate], by_variant[reference]):
            assert all(c[key] == r[key] for key in ['ordinal', 'id_sha256', 'sample_sha256', 'benchmark'])
            for group in ['overall', c['benchmark']]:
                counts = groups[group]
                counts['n'] += 1
                counts['reference_correct_candidate_wrong'] += r['stored_official_correct'] and not c['stored_official_correct']
                counts['reference_wrong_candidate_correct'] += not r['stored_official_correct'] and c['stored_official_correct']
                counts['lost_correct_and_now_no_calls'] += r['stored_official_correct'] and not c['stored_official_correct'] and c['no_parsed_calls']
                counts['lost_correct_and_now_response_marker'] += r['stored_official_correct'] and not c['stored_official_correct'] and c['has_response_marker']
                counts['lost_correct_and_fixed_reasoning'] += r['stored_official_correct'] and not c['stored_official_correct'] and c['contains_published_fixed_reasoning']
        paired[candidate+'-vs-'+reference] = dict(groups)
    outcomes = {variant: {'overall': summarize_outputs(part),
                         'by_benchmark': {name: summarize_outputs([r for r in part if r['benchmark'] == name])
                                          for name in sorted({r['benchmark'] for r in part})}}
                for variant, part in by_variant.items()}
    result = {'scope': spec['scope'], 'supervision': reports, 'stored_outcomes': outcomes, 'paired': paired,
              'diagnostic_markers_are_not_semantic_refusal_labels': True,
              'association_is_not_causation': True, 'known_development_outcomes_already_seen': True,
              'no_model_training_or_inference': True, 'no_scorer_or_raw_output_parser_calls': True,
              'original_unknown_attempts_still_charged': spec['progress']['unknown_still_charged'],
              'loss_mask_policy': 'Only tokens wholly inside exact published fixed leading-think prose; preserve tags, variable reasoning, tool/response payloads, EOS, inputs and original segment boundaries.',
              'next_method_is_prepared_not_trained': True}
    save(args.output/'report.json', result)
    jsonl(args.output/'supervision-metadata.jsonl', metadata)
    jsonl(args.output/'stored-output-metadata.jsonl', saved)
    for name, expected in spec['data_sha256'].items():
        assert file_sha(args.data/name) == expected
    assert file_sha(args.ledger) == spec['ledger_sha256']
    save(args.output/'receipt.json', {'protocol_sha256': file_sha(args.protocol), 'input_data_and_ledger_unchanged': True,
                                    'training_or_model_calls': 0, 'wall_seconds': round(time.monotonic()-began, 3),
                                    'private_loss_mask_files': {p.name: {'sha256': file_sha(p), 'bytes': p.stat().st_size} for p in private.iterdir()}})
    print(json.dumps({'complete': True, 'stored_outcomes': outcomes, 'paired': paired}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['data', 'model', 'ledger', 'converter', 'protocol', 'output']:
        parser.add_argument('--'+name, type=Path, required=True)
    run(parser.parse_args())
