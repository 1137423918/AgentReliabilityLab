"""Admit BFCL question-only transfer cases before opening possible answers.

This is text decontamination and deterministic selection, not a BFCL score,
semantic isolation, model training, or proof of pretraining independence.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import copy
import hashlib
import json
from pathlib import Path
import re
import unicodedata


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(packed(value)).hexdigest()


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normal(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def sequence(messages):
    assert isinstance(messages, list) and messages
    assert all(isinstance(m, dict) and m.get('role') in {'system', 'user', 'assistant'}
               and isinstance(m.get('content'), str) for m in messages)
    result = tuple(normal(m['content']) for m in messages if m['role'] == 'user')
    assert result and any(result), 'No nonempty normalized user sequence'
    return result


class Union:
    def __init__(self):
        self.parent = {}

    def root(self, key):
        self.parent.setdefault(key, key)
        while key != self.parent[key]:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def join(self, left, right):
        a, b = self.root(left), self.root(right)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def text_components(nodes, pair_cap):
    union = Union()
    sequences = defaultdict(list)
    for key, seq in nodes:
        assert seq and any(seq)
        union.root(key)
        sequences[seq].append(key)
    for members in sequences.values():
        for key in members[1:]:
            union.join(members[0], key)
    ordered = sorted(sequences)
    grams = []
    postings = defaultdict(list)
    candidates = near = 0
    for i, seq in enumerate(ordered):
        words = re.findall(r'\w+', ' '.join(seq))
        group = {tuple(words[j:j+3]) for j in range(len(words)-2)} if len(words) >= 8 else set()
        grams.append(group)
        overlaps = Counter(j for term in group for j in postings[term])
        candidates += len(overlaps)
        assert candidates <= pair_cap, 'Lexical pair cap exceeded, no silently skipped pairs'
        for j, intersection in overlaps.items():
            total = len(group) + len(grams[j]) - intersection
            if 5 * intersection >= 4 * total:
                union.join(sequences[seq][0], sequences[ordered[j]][0])
                near += 1
        for term in group:
            postings[term].append(i)
    groups = defaultdict(list)
    for key in union.parent:
        groups[union.root(key)].append(key)
    components = {key: digest(sorted(group)) for group in groups.values() for key in group}
    return components, {'nodes': len(nodes), 'distinct_ids': len(union.parent),
                        'unique_sequences': len(sequences), 'components': len(groups),
                        'near_edges': near, 'candidate_pairs': candidates}


def question_messages(row):
    assert not {'answer', 'answers', 'ground_truth', 'possible_answer', 'result'} & row.keys()
    assert isinstance(row['id'], str) and row['id']
    assert isinstance(row['function'], list) and row['function']
    assert all(isinstance(f, dict) and isinstance(f.get('name'), str) and isinstance(f.get('parameters'), dict)
               for f in row['function'])
    turns = row['question']
    assert isinstance(turns, list) and len(turns) == 1, 'Only single-turn categories admitted'
    messages = turns[0]
    sequence(messages)
    assert messages[0]['role'] != 'assistant'
    assert all(m['role'] != 'system' for m in messages[1:]), 'System message must be first'
    return messages


def prompt_constants(path):
    # Only literal assignments; never import the broader BFCL module.
    wanted = {'OUTPUT_FORMAT_MAPPING', 'PARAM_TYPE_MAPPING', 'PROMPT_STYLE_TEMPLATES',
              '_PLAINTEXT_SYSTEM_PROMPT_TEMPLATE'}
    values = {}
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            key = node.targets[0].id
            if key in wanted:
                values[key] = ast.literal_eval(node.value)
    assert values.keys() == wanted
    return values


def make_prompt(row, values):
    # Pinned default classic/python/no-tag/json/plaintext branch. The legacy
    # _DEFAULT_SYSTEM_PROMPT is explicitly NOT USED in upstream either.
    style = values['PROMPT_STYLE_TEMPLATES']['classic']
    system = values['_PLAINTEXT_SYSTEM_PROMPT_TEMPLATE'].format(
        persona=style['persona'], task=style['task'],
        tool_call_format=style['tool_call_no_tag'].format(
            output_format=values['OUTPUT_FORMAT_MAPPING']['python'],
            param_types=values['PARAM_TYPE_MAPPING']['python']),
        multiturn_behavior=style['multiturn_behavior'],
        available_tools=style['available_tools'].format(
            format='json', functions=json.dumps(row['function'], indent=4)))
    messages = copy.deepcopy(question_messages(row))
    if messages[0]['role'] == 'system':
        messages[0]['content'] = system + '\n\n' + messages[0]['content']
    else:
        messages.insert(0, {'role': 'system', 'content': system})
    return messages


def choose(rows, quotas, seed):
    # Round-robin interleaving prevents an earlier category consuming every
    # shared component. Per-category order depends only on the frozen seed/ID.
    candidates = {name: sorted([r for r in rows if r['category'] == name and r['eligible']],
                              key=lambda r: digest([seed, name, r['id']])) for name in quotas}
    selected = []
    used = set()
    cursor = Counter()
    counts = Counter()
    for _ in range(max(quotas.values())):
        for name, quota in quotas.items():
            if counts[name] >= quota:
                continue
            before = counts[name]
            while cursor[name] < len(candidates[name]):
                item = candidates[name][cursor[name]]
                cursor[name] += 1
                if item['component_sha256'] not in used:
                    selected.append(item)
                    used.add(item['component_sha256'])
                    counts[name] += 1
                    break
            assert counts[name] > before, 'Insufficient distinct eligible components: '+name
    assert dict(counts) == quotas, 'Quota unmet; do not relax or replace after observing results'
    return selected


def save(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def run(args):
    import pyarrow.parquet as pq
    from transformers import AutoTokenizer

    spec = json.loads(args.protocol.read_text())
    for name, expected in spec['source_sha256'].items():
        assert file_sha(args.source/name) == expected, name
    for name, expected in spec['protected_data_sha256'].items():
        assert file_sha(args.data/name) == expected, name
    assert file_sha(args.old_benchmark) == spec['old_benchmark_sha256']
    for name, expected in spec['question_files'].items():
        raw = (args.questions/name).read_bytes()
        assert len(raw) == expected['bytes']
        assert hashlib.sha1(('blob '+str(len(raw))+'\0').encode()+raw).hexdigest() == expected['git_blob_sha1']
    assert not list(args.questions.glob('*possible_answer*')), 'Gold files must not be staged for admission'
    args.output.mkdir(mode=0o700, exist_ok=False)
    private = args.output/'private'
    private.mkdir(mode=0o700)
    nodes = []
    protected = set()
    protected_rows = {}
    for name, expected_n in spec['protected_rows'].items():
        rows = pq.ParquetFile(args.data/name).read(columns=['extra_info'], use_threads=False).to_pylist()
        assert len(rows) == expected_n
        protected_rows[name] = len(rows)
        for row in rows:
            info = row['extra_info']
            key = 'sample:'+info['original_id']
            seq = tuple(normal(x) for x in re.findall(r'<user>\s*(.*?)\s*</user>', info['input'], re.S))
            assert seq and any(seq)
            nodes.append((key, seq))
            protected.add(key)
    old = [json.loads(line) for line in args.old_benchmark.read_text().splitlines() if line.strip()]
    assert len(old) == 199
    for i, row in enumerate(old):
        conv = json.loads(row['conversation']) if isinstance(row['conversation'], str) else row['conversation']
        key = 'oldclean:'+str(i)
        nodes.append((key, sequence(conv)))
        protected.add(key)
    candidates = []
    for category, name in spec['category_files'].items():
        rows = [json.loads(line) for line in (args.questions/name).read_text().splitlines() if line.strip()]
        assert len(rows) == spec['expected_category_rows'][category]
        for row in rows:
            messages = question_messages(row)
            key = 'sample:'+row['id']
            nodes.append((key, sequence(messages)))
            candidates.append({'category': category, 'id': row['id'], 'key': key, 'row': row})
    assert len({r['key'] for r in candidates}) == len(candidates)
    components, grouping = text_components(nodes, spec['pair_cap'])
    quarantined = {components[key] for key in protected}
    tokenizer = AutoTokenizer.from_pretrained(str(args.model), local_files_only=True, trust_remote_code=False)
    constants = prompt_constants(args.source/'upstream/default_prompts.py')
    metadata = []
    for item in candidates:
        messages = make_prompt(item['row'], constants)
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        component = components[item['key']]
        reasons = []
        if component in quarantined:
            reasons.append('protected_text_component')
        if len(ids) > spec['max_prompt_tokens']:
            reasons.append('prompt_over_cap')
        row = {'category': item['category'], 'id': item['id'], 'source_row_sha256': digest(item['row']),
               'component_sha256': component, 'prompt_sha256': digest(messages),
               'prompt_token_ids_sha256': digest(ids), 'prompt_tokens': len(ids),
               'eligible': not reasons, 'exclusions': reasons}
        metadata.append(row)
        item.update(row, messages=messages)
    (args.output/'candidate-metadata.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in metadata))
    print(json.dumps({'phase': 'before_selection', 'grouping': grouping,
                      'eligible_by_category': dict(Counter(r['category'] for r in metadata if r['eligible'])),
                      'exclusions': dict(Counter(reason for r in metadata for reason in r['exclusions']))}), flush=True)
    selected_meta = choose(metadata, spec['quotas'], spec['selection_seed'])
    by_id = {r['id']: r for r in candidates}
    admission = {'protocol_sha256': file_sha(args.protocol), 'grouping': grouping,
                 'protected_rows': protected_rows, 'oldclean_rows': len(old),
                 'quotas': spec['quotas'], 'selected': selected_meta,
                 'selection_order_sha256': digest([r['id'] for r in selected_meta]),
                 'gold_files_read': 0, 'model_calls': 0, 'optimizer_updates': 0,
                 'not_pretraining_isolated_or_full_BFCL_score': True}
    # Durable ID admission is written before preparing any optional later gold
    # binding. This module never accepts or opens a possible_answer file.
    save(args.output/'admission.json', admission)
    prompts = [{k: by_id[r['id']][k] for k in ['category', 'id', 'row', 'messages']} for r in selected_meta]
    (private/'selected-inputs.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in prompts))
    report = {'admission_sha256': file_sha(args.output/'admission.json'), 'selected': len(prompts),
              'selected_by_category': dict(Counter(r['category'] for r in prompts)),
              'candidate_by_category': dict(Counter(r['category'] for r in metadata)),
              'exclusions': dict(Counter(reason for r in metadata for reason in r['exclusions'])),
              'private_input_sha256': file_sha(private/'selected-inputs.jsonl'),
              'protected_inputs_unchanged': all(file_sha(args.data/n) == s for n, s in spec['protected_data_sha256'].items()),
              'old_benchmark_unchanged': file_sha(args.old_benchmark) == spec['old_benchmark_sha256'],
              'no_gold_or_model_calls': True}
    assert report['protected_inputs_unchanged'] and report['old_benchmark_unchanged']
    save(args.output/'report.json', report)
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'data', 'model', 'old-benchmark', 'questions', 'protocol', 'output']:
        parser.add_argument('--'+name, type=Path, required=True)
    run(parser.parse_args())
