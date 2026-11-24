"""Partition existing assistant targets without changing context or labels.

Parts are syntactic spans, not semantic correctness labels. Tokens crossing a
span boundary, markup and termination remain in structure_or_boundary.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from benchmarks.audit_toolrl_alignment import constant_reason_span, mask_constant_offsets
from benchmarks.generation_progress import GenerationProgress, atomic_save

PARTS = ['fixed_reason_prose', 'answer_payload', 'other_reason_or_whitespace', 'structure_or_boundary']


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(packed(value)).hexdigest()


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def target_parts(answer, prefix_chars, labels, offsets, constants):
    assert len(labels) == len(offsets)
    think = re.match(r'<think>(.*?)</think>', answer, re.S)
    assert think, 'Expected the unchanged converter think envelope'
    tail = answer[think.end():]
    start = think.end()+len(tail)-len(tail.lstrip())
    end = len(answer.rstrip())
    shape = None
    for tag in ['tool_call', 'response']:
        opening, closing = '<'+tag+'>', '</'+tag+'>'
        if answer[start:end].startswith(opening) and answer[start:end].endswith(closing):
            payload = (prefix_chars+start+len(opening), prefix_chars+end-len(closing))
            shape = tag
            break
    assert shape is not None, 'Unexpected answer envelope; do not guess or drop the row'
    relative = constant_reason_span(answer, constants)
    fixed = tuple(prefix_chars+x for x in relative) if relative else None
    reasoning = (prefix_chars+think.start(1), prefix_chars+think.end(1))
    inside = lambda span, a, b: span is not None and span[0] <= a < b <= span[1]
    overlaps = lambda span, a, b: span is not None and max(span[0], a) < min(span[1], b)
    result = []
    for label, (a, b) in zip(labels, offsets):
        if label == -100:
            result.append(-1)
        elif inside(fixed, a, b):
            result.append(0)
        elif inside(payload, a, b):
            result.append(1)
        elif inside(reasoning, a, b) and not overlaps(fixed, a, b):
            result.append(2)
        else:
            result.append(3)
    masked = mask_constant_offsets(labels, offsets, fixed)
    assert sum(part == 0 for part in result) == sum(a != -100 and b == -100 for a, b in zip(labels, masked))
    return result, shape


def causal_selection(row):
    ids, labels, parts = row['input_ids'], row['labels'], row['parts']
    assert len(ids) == len(labels) == len(parts)
    positions = [i for i in range(1, len(ids)) if labels[i] != -100]
    assert len(positions) == row['target_tokens'] > 0
    assert all(labels[i] == ids[i] and 0 <= parts[i] < len(PARTS) for i in positions)
    assert all(part == -1 for label, part in zip(labels, parts) if label == -100)
    return [i-1 for i in positions], [labels[i] for i in positions], [parts[i] for i in positions]


def summarize_token_losses(losses, parts):
    import math
    assert len(losses) == len(parts) > 0
    assert all(math.isfinite(x) and x >= 0 for x in losses)
    result = {}
    for index, name in enumerate(PARTS):
        values = [value for value, part in zip(losses, parts) if part == index]
        total = math.fsum(values)
        result[name] = {'tokens': len(values), 'loss_sum': total,
                        'token_weighted_NLL': total/len(values) if values else None}
    assert sum(v['tokens'] for v in result.values()) == len(losses)
    assert math.isclose(math.fsum(v['loss_sum'] for v in result.values()), math.fsum(losses), rel_tol=1e-12, abs_tol=1e-9)
    return result


def prepare(args):
    import pyarrow.parquet as pq
    from transformers import AutoTokenizer
    spec = json.loads(args.protocol.read_text())
    for name, expected in spec['data_sha256'].items():
        assert file_sha(args.data/name) == expected, name
    assert file_sha(args.converter) == spec['converter_sha256']
    constants = set()
    for node in ast.parse(args.converter.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {'THINK_TOOL_CALL', 'THINK_RESPONSE'} for t in node.targets):
            constants.add(ast.literal_eval(node.value))
    assert len(constants) == 2
    tokenizer = AutoTokenizer.from_pretrained(str(args.model), local_files_only=True, trust_remote_code=False)
    assert tokenizer.is_fast
    args.output.mkdir(mode=0o700, exist_ok=False)
    private = args.output/'private'; private.mkdir(mode=0o700)
    metadata, report, combined = [], {}, []
    for split, count in [('dev_clean', 197), ('test', 79)]:
        original = [json.loads(line) for line in (args.data/(split+'-tokenized.jsonl')).read_text().splitlines()]
        source = pq.ParquetFile(args.data/(split+'.parquet')).read(use_threads=False).to_pylist()
        assert len(original) == len(source) == count
        prepared, totals, shapes = [], Counter(), Counter()
        for ordinal, (row, cached) in enumerate(zip(source, original), 1):
            answer = row['reward_model']['ground_truth']
            prefix = tokenizer.apply_chat_template(row['prompt'], tokenize=False, add_generation_prompt=True)
            text = tokenizer.apply_chat_template(row['prompt']+[{'role': 'assistant', 'content': answer}], tokenize=False, add_generation_prompt=False)
            assert text.startswith(prefix+answer)
            encoded = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
            assert encoded['input_ids'] == cached['input_ids']
            assert cached['labels'] == [-100]*cached['prompt_tokens']+cached['input_ids'][cached['prompt_tokens']:]
            assert hashlib.sha256(row['extra_info']['original_id'].encode()).hexdigest() == cached['id_sha256']
            assert all(0 <= a <= b <= len(text) for a, b in encoded['offset_mapping'])
            parts, shape = target_parts(answer, len(prefix), cached['labels'], encoded['offset_mapping'], constants)
            enriched = {**cached, 'parts': parts}
            _, _, selected = causal_selection(enriched)
            counts = {name: selected.count(index) for index, name in enumerate(PARTS)}
            totals.update(counts); shapes[shape] += 1; prepared.append(enriched)
            metadata.append({'split': split, 'ordinal': ordinal, 'id_sha256': cached['id_sha256'],
                'component_sha256': cached['component_sha256'], 'source_row_sha256': digest(row),
                'input_ids_sha256': digest(cached['input_ids']), 'labels_sha256': digest(cached['labels']),
                'parts_sha256': digest(parts), 'part_tokens': counts, 'target_tokens': cached['target_tokens'], 'shape': shape})
        path = private/(split+'-parts.jsonl')
        path.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in prepared)); path.chmod(0o600)
        assert sum(totals.values()) == sum(row['target_tokens'] for row in original)
        report[split] = {'cases': count, 'part_tokens': dict(totals), 'target_shapes': dict(shapes),
                         'target_tokens': sum(totals.values()), 'private_file_sha256': file_sha(path)}
        historical = {role: json.loads((args.source/'historical'/role/(split+'.json')).read_text())['cases']
                      for role in ['base', 'reference32', 'masked32']}
        assert all([row['id_sha256'] for row in prepared] == [row['id_sha256'] for row in values]
                   for values in historical.values())
        for index, row in enumerate(prepared):
            legacy = {role: values[index]['loss_sum'] for role, values in historical.items()}
            assert all(values[index]['target_tokens'] == row['target_tokens'] for values in historical.values())
            combined.append({**row, 'split': split, 'kind': 'parts', 'legacy_loss_sum': legacy})
    for name, expected in spec['data_sha256'].items():
        assert file_sha(args.data/name) == expected
    (args.output/'part-metadata.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in metadata))
    cases = [{**combined[0], 'kind': 'standard_canary'}]+combined
    for row in cases:
        row['id'] = row['kind']+':'+row['split']+':'+row['id_sha256']
        row['sample_sha256'] = digest({key: row[key] for key in ['input_ids', 'labels', 'parts']})
        row['request_sha256'] = digest({'sample_sha256': row['sample_sha256'], 'kind': row['kind'],
                                        'settings': spec['evaluation_settings']})
    assert len(cases) == len({row['id'] for row in cases}) == 277
    experiment = args.output/'experiment'; experiment.mkdir(mode=0o700)
    definition = {'variants': ['base', 'reference32', 'masked32'],
        'scope': 'Teacher-forced known-data objective diagnostic; 277forwards per role, no training/text generation/retry/resume.',
        'limits': {'total_attempts': 831, 'variant_attempts': 277, 'case_attempts': 1},
        'settings': spec['evaluation_settings'], 'models': spec['models'],
        'source_sha256': spec['source_sha256'], 'data_sha256': spec['data_sha256'],
        'cases': [{'id_sha256': hashlib.sha256(row['id'].encode()).hexdigest(),
                   'sample_sha256': row['sample_sha256'], 'request_sha256': row['request_sha256']} for row in cases]}
    atomic_save(experiment/'definition.json', definition)
    casepath = experiment/'cases-private.jsonl'
    casepath.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in cases)); casepath.chmod(0o600)
    progress = GenerationProgress(experiment/'progress', definition, create=True)
    assert not progress.snapshot()['attempts'] and not progress.snapshot()['results']
    value = {'protocol_sha256': file_sha(args.protocol), 'splits': report, 'parts': PARTS,
        'original_context_labels_and_order_unchanged': True, 'fixed_part_exactly_matches_original_mask_policy': True,
        'definition_sha256': file_sha(experiment/'definition.json'), 'definition_owner_sha256': progress.owner,
        'cases_sha256': file_sha(casepath), 'prospective_teacher_forward_limits': definition['limits'],
        'training_generation_and_model_forwards': 0, 'known_data_teacher_forced_diagnostic_not_new_task_score': True}
    (args.output/'report.json').write_text(json.dumps(value, indent=2)+'\n')
    print(json.dumps(value), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['data', 'model', 'converter', 'protocol', 'output', 'source']:
        parser.add_argument('--'+name, type=Path, required=True)
    prepare(parser.parse_args())
