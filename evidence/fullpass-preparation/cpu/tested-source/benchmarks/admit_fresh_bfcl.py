"""Freeze unused BFCL prediction inputs from an immutable question-only graph.

The parent graph already includes all candidate and protected text components.
Reusing it requires unchanged question/protected-data hashes. No answers opened.
"""
from __future__ import annotations
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path

from benchmarks.prepare_bfcl_transfer import choose, digest, file_sha, make_prompt, prompt_constants


def fresh_selection(rows, previous, quotas, seed):
    assert not any(set(row)&{'score', 'correct', 'gold', 'ground_truth', 'prediction', 'official_score'} for row in rows)
    ids = {row['id'] for row in previous}
    components = {row['component_sha256'] for row in previous}
    candidates = copy.deepcopy(rows)
    for row in candidates:
        if row['id'] in ids or row['component_sha256'] in components:
            row['eligible'] = False
            row['exclusions'] = list(row['exclusions'])+['previously_admitted_component']
    selected = choose(candidates, quotas, seed)
    assert not ids & {row['id'] for row in selected}
    assert not components & {row['component_sha256'] for row in selected}
    assert len({row['component_sha256'] for row in selected}) == len(selected)
    return selected, candidates


def admit(args):
    from transformers import AutoTokenizer
    spec = json.loads(args.protocol.read_text())
    for name, expected in spec['source_sha256'].items():
        assert file_sha(args.source/name) == expected
    for name, expected in spec['protected_data_sha256'].items():
        assert file_sha(args.data/name) == expected
    assert file_sha(args.parent/'admission.json') == spec['parent_admission_sha256']
    assert file_sha(args.parent/'candidate-metadata.jsonl') == spec['parent_candidates_sha256']
    assert file_sha(args.old_benchmark) == spec['old_benchmark_sha256']
    assert not list(args.questions.glob('*possible_answer*'))
    parent = json.loads((args.parent/'admission.json').read_text())
    assert parent['gold_files_read'] == parent['model_calls'] == 0
    rows = [json.loads(line) for line in (args.parent/'candidate-metadata.jsonl').read_text().splitlines()]
    assert len(rows) == 1951
    selected, candidates = fresh_selection(rows, parent['selected'], spec['quotas'], spec['selection_seed'])
    lookup = {}
    for name, expected in spec['question_files'].items():
        raw = (args.questions/name).read_bytes()
        assert len(raw) == expected['bytes']
        assert hashlib.sha1(('blob '+str(len(raw))+'\0').encode()+raw).hexdigest() == expected['git_blob_sha1']
        for line in raw.splitlines():
            if line.strip():
                row = json.loads(line); assert row['id'] not in lookup; lookup[row['id']] = row
    tokenizer = AutoTokenizer.from_pretrained(str(args.model), local_files_only=True, trust_remote_code=False)
    constants = prompt_constants(args.source/'upstream/default_prompts.py')
    prompts = []
    for meta in selected:
        row = lookup[meta['id']]
        assert digest(row) == meta['source_row_sha256']
        messages = make_prompt(row, constants)
        token_ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        assert digest(messages) == meta['prompt_sha256'] and digest(token_ids) == meta['prompt_token_ids_sha256']
        assert len(token_ids) == meta['prompt_tokens'] <= spec['max_prompt_tokens']
        assert len(token_ids)+1536 <= 32768
        prompts.append({'id': meta['id'], 'category': meta['category'], 'row': row, 'messages': messages})
    args.output.mkdir(mode=0o700, exist_ok=False)
    private = args.output/'private'; private.mkdir(mode=0o700)
    admission = {'protocol_sha256': file_sha(args.protocol),
        'parent_admission_sha256': spec['parent_admission_sha256'],
        'parent_candidates_sha256': spec['parent_candidates_sha256'],
        'quotas': spec['quotas'], 'selected': selected,
        'selection_order_sha256': digest([row['id'] for row in selected]),
        'old250_IDs_and_components_excluded': True, 'parent_protected_graph_reused_without_changes': True,
        'gold_files_read_this_phase': 0, 'new_model_outputs_generated': 0,
        'limitations': 'Unused prediction cohort under same text graph,not semantic/pretraining isolation. Older answerfiles already existed from prior study;none opened by this admission. Not full BFCL.'}
    (args.output/'admission.json').write_text(json.dumps(admission, indent=2)+'\n')
    path = private/'selected-inputs.jsonl'
    path.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in prompts)); path.chmod(0o600)
    report = {'admission_sha256': file_sha(args.output/'admission.json'),
        'private_input_sha256': file_sha(path), 'cases': len(selected),
        'by_category': dict(Counter(row['category'] for row in selected)),
        'remaining_eligible_by_category': dict(Counter(row['category'] for row in candidates if row['eligible'])),
        'unique_selected_components': len({row['component_sha256'] for row in selected}),
        'max_prompt_tokens': max(row['prompt_tokens'] for row in selected),
        'gold_reads_new_model_forwards_or_training': 0,
        'frozen_before_new_study_weights_or_prediction_outcomes': True}
    for name, expected in spec['protected_data_sha256'].items():
        assert file_sha(args.data/name) == expected
    assert file_sha(args.parent/'admission.json') == spec['parent_admission_sha256']
    assert file_sha(args.parent/'candidate-metadata.jsonl') == spec['parent_candidates_sha256']
    assert file_sha(args.old_benchmark) == spec['old_benchmark_sha256']
    (args.output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'data', 'model', 'questions', 'parent', 'old-benchmark', 'protocol', 'output']:
        p.add_argument('--'+name, type=Path, required=True)
    admit(p.parse_args())
