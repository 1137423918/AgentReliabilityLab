"""Offline scoring of a fully committed, fixed three-role generation cohort.

This module has no model callback. Raw outputs, input schemas and references
remain private; public case rows contain identities and scorer flags only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import hashlib
import json
import math
from pathlib import Path

from benchmarks.bfcl_generation import validate_cached, validate_inputs
from benchmarks.bfcl_transfer_scoring import digest, load_python_scorer
from benchmarks.generation_progress import GenerationProgress

ROLES = ['base', 'reference32', 'masked32']
CATEGORIES = ['live_simple', 'live_multiple', 'parallel', 'parallel_multiple', 'irrelevance']


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(rows):
    assert rows
    values = [row['score']['guarded_valid'] for row in rows]
    assert all(value is None or type(value) is bool for value in values)
    successes = sum(value is True for value in values)
    undefined = sum(value is None for value in values)
    return {'cases': len(rows), 'observed_successes': successes,
            'defined_cases': len(rows)-undefined, 'undefined_cases': undefined,
            'accuracy': successes/len(rows) if not undefined else None,
            'guard_rejected': sum(row['score']['guard_rejected'] for row in rows),
            'decode_success': sum(row['score']['decode_success'] for row in rows),
            'decoder_failure_after_guard': sum(not row['score']['guard_rejected']
                and not row['score']['decode_success'] and 'scorer_error_type' not in row['score'] for row in rows),
            'explicit_empty_call_list': sum(row['score']['explicit_empty_call_list'] for row in rows),
            'irrelevance_credit_with_decode_failure': sum(row['category'] == 'irrelevance'
                and row['score']['guarded_valid'] is True and not row['score']['decode_success'] for row in rows),
            'scorer_errors': dict(Counter(row['score']['scorer_error_type'] for row in rows
                if 'scorer_error_type' in row['score'])),
            'eval_attempts': sum(row['score']['eval_attempts'] for row in rows)}


def paired(left, right):
    """Two-sided exact conditional McNemar; positive change favors right."""
    assert len(left) == len(right) and left
    counts = Counter()
    for a, b in zip(left, right):
        assert a['id'] == b['id'] and a['category'] == b['category']
        av, bv = a['score']['guarded_valid'], b['score']['guarded_valid']
        if av is None or bv is None:
            counts['undefined_pairs'] += 1
        else:
            assert type(av) is type(bv) is bool
            counts['both_correct' if av and bv else 'right_only' if bv else
                   'left_only' if av else 'both_wrong'] += 1
    lost, gained = counts['left_only'], counts['right_only']
    discordant = lost+gained
    p = min(1.0, 2*sum(math.comb(discordant, k) for k in range(min(lost, gained)+1))/2**discordant) if discordant else 1.0
    valid = counts['undefined_pairs'] == 0
    return {'cases': len(left), **{key: counts[key] for key in
            ['both_correct', 'left_only', 'right_only', 'both_wrong', 'undefined_pairs']},
            'accuracy_difference_right_minus_left': (gained-lost)/len(left) if valid else None,
            'exact_two_sided_McNemar_p': p if valid else None,
            'inference_limit': 'Single fixed stratified subset and seed; no full benchmark or population generalization claim.'}


def require_complete(state, definition):
    assert definition['variants'] == ROLES and len(definition['cases']) == 250
    expected = {role+':'+str(index) for role in ROLES for index in range(1, 251)}
    assert set(state['results']) == expected, 'All750 results must be committed before scoring'


def run(args):
    spec = json.loads(args.protocol.read_text())
    for name, expected in spec['source_sha256'].items():
        assert file_sha(args.source/name) == expected, name
    assert file_sha(args.experiment/'definition.json') == spec['definition_sha256']
    assert file_sha(args.experiment/'inputs-tokenized.jsonl') == spec['tokenized_inputs_sha256']
    assert file_sha(args.inputs) == spec['private_inputs_sha256']
    assert file_sha(args.gold) == spec['bound_gold_sha256']
    assert file_sha(args.scorer_identity) == spec['scorer_identity_sha256']
    assert file_sha(args.controllers/'protocol.json') == spec['generation_protocol_sha256']
    definition = json.loads((args.experiment/'definition.json').read_text())
    inputs = [json.loads(line) for line in args.inputs.read_text().splitlines()]
    tokenized = [json.loads(line) for line in (args.experiment/'inputs-tokenized.jsonl').read_text().splitlines()]
    gold = [json.loads(line) for line in args.gold.read_text().splitlines()]
    validate_inputs(tokenized, definition)
    assert len(inputs) == len(gold) == 250
    assert [row['id'] for row in inputs] == [row['id'] for row in tokenized] == [row['id'] for row in gold]
    assert digest([row['id'] for row in inputs]) == spec['selection_order_sha256']
    assert Counter(row['category'] for row in inputs) == {category: 50 for category in CATEGORIES}
    for inp, tok, reference in zip(inputs, tokenized, gold):
        assert inp['category'] == tok['category'] == reference['category']
        assert digest(inp['row']) == tok['sample_sha256']
        assert digest({'id': reference['id'], 'ground_truth': reference['gold']}) == reference['gold_row_sha256']
        assert reference['witness_control']['guarded_valid'] is True
    controllers = [json.loads(path.read_text()) for path in sorted(args.controllers.glob('*-controller.json'))]
    assert controllers
    for controller in controllers:
        assert controller['terminal'] and controller['own_GPU_context_absent']
        assert not controller['shutdown']['remaining_owned_processes']
        assert controller['protocol_sha256'] == spec['generation_protocol_sha256']
        assert controller['source_and_inputs_unchanged'] and controller['old_generation_ledger_unchanged']
        assert controller['prior_results_preserved']
    for role in ROLES:
        scoped = [row for row in controllers if row['variant'] == role]
        assert scoped and max(scoped, key=lambda row: row['segment'])['all_cases_completed']
    progress = GenerationProgress(args.experiment/'progress', definition)
    assert progress.owner == spec['definition_owner_sha256']
    with ExitStack() as locks:
        for role in ROLES:
            locks.enter_context(progress.worker(role))
        journal_before = file_sha(progress.path)
        state = progress.snapshot()
        require_complete(state, definition)
        score, identities = load_python_scorer(args.source/'upstream')
        assert identities == json.loads(args.scorer_identity.read_text())
        args.output.mkdir(mode=0o700, exist_ok=False)
        rows = []
        for role in ROLES:
            for index, (inp, tok, reference) in enumerate(zip(inputs, tokenized, gold), 1):
                stored = state['results'][role+':'+str(index)]
                row = stored['row']
                validate_cached(row, tok, role, index)
                assert digest(row) == stored['row_sha256']
                value = score(row['prediction']['raw_output'], inp['row'], reference['gold'], inp['category'])
                rows.append({'id': inp['id'], 'category': inp['category'], 'variant': role,
                    'case_index': index, 'sample_sha256': tok['sample_sha256'],
                    'request_sha256': tok['request_sha256'], 'result_row_sha256': stored['row_sha256'],
                    'raw_output_sha256': hashlib.sha256(row['prediction']['raw_output'].encode()).hexdigest(),
                    'generated_token_ids_sha256': digest(row['generated_token_ids']),
                    'gold_row_sha256': reference['gold_row_sha256'], 'score': value})
        grouped = {role: [row for row in rows if row['variant'] == role] for role in ROLES}
        results = {role: {'positive200': summarize([row for row in values if row['category'] != 'irrelevance']),
            'irrelevance50': summarize([row for row in values if row['category'] == 'irrelevance']),
            'balanced250_diagnostic': summarize(values),
            'categories': {category: summarize([row for row in values if row['category'] == category]) for category in CATEGORIES}}
            for role, values in grouped.items()}
        select = lambda role: [row for row in grouped[role] if row['category'] != 'irrelevance']
        report = {'protocol_sha256': file_sha(args.protocol), 'generation_protocol_sha256': spec['generation_protocol_sha256'],
            'journal_sha256': journal_before, 'definition_owner_sha256': progress.owner,
            'cases_per_role': 250, 'committed_model_results': len(state['results']),
            'charged_attempts': len(state['attempts']), 'unknown_still_charged': sum(row['state'] == 'reserved' for row in state['attempts']),
            'results': results, 'primary_positive200_reference32_to_masked32': paired(select('reference32'), select('masked32')),
            'diagnostic_positive200_base_to_reference32': paired(select('base'), select('reference32')),
            'diagnostic_positive200_base_to_masked32': paired(select('base'), select('masked32')),
            'constant_no_call_baseline': {'positive200_successes': 0, 'irrelevance50_successes': 50,
                'balanced250_accuracy': .2, 'derived_rule_baseline_not_neural': True},
            'model_calls_during_scoring': 0, 'actual_tool_execution': False,
            'limitations': 'Guarded BFCL-derived Python AST subset, not full BFCL or tool execution. Guard rejects get no credit; unrestricted official outcome unknown. Undefined scorer errors retained. Irrelevance parse-failure credit retained and counted separately. No checkpoint/prompt selection or semantic/pretraining isolation claim.'}
        assert all(row['score']['eval_attempts'] == 0 for row in rows)
        assert file_sha(progress.path) == journal_before
        assert progress.snapshot() == state
        assert file_sha(args.inputs) == spec['private_inputs_sha256'] and file_sha(args.gold) == spec['bound_gold_sha256']
        assert all(file_sha(args.source/name) == expected for name, expected in spec['source_sha256'].items())
        report['journal_inputs_and_sources_unchanged'] = True
        (args.output/'case-flags.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
        (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'experiment', 'inputs', 'gold', 'scorer-identity', 'controllers', 'protocol', 'output']:
        parser.add_argument('--'+name, type=Path, required=True)
    run(parser.parse_args())
