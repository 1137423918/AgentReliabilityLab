"""Prepare the fixed250 inference inputs and empty charged journal on CPU."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from benchmarks.bfcl_generation import SETTINGS, request_digest, validate_inputs
from benchmarks.generation_progress import GenerationProgress, atomic_save, digest


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    from transformers import AutoTokenizer

    spec = json.loads(args.protocol.read_text())
    assert spec['phase'] == 'cpu_generation_preflight'
    for name, expected in spec['source_sha256'].items():
        assert file_sha(args.source/name) == expected, name
    assert file_sha(args.admission/'admission.json') == spec['admission_sha256']
    assert file_sha(args.admission/'private/selected-inputs.jsonl') == spec['private_inputs_sha256']
    admission = json.loads((args.admission/'admission.json').read_text())
    selected = admission['selected']
    inputs = [json.loads(line) for line in (args.admission/'private/selected-inputs.jsonl').read_text().splitlines()]
    assert len(inputs) == len(selected) == 250
    assert [r['id'] for r in inputs] == [r['id'] for r in selected]
    tokenizer = AutoTokenizer.from_pretrained(str(args.model), local_files_only=True, trust_remote_code=False)
    tokenized = []
    for row, meta in zip(inputs, selected):
        assert digest(row['row']) == meta['source_row_sha256']
        assert digest(row['messages']) == meta['prompt_sha256']
        ids = tokenizer.apply_chat_template(row['messages'], tokenize=True, add_generation_prompt=True)
        assert digest(ids) == meta['prompt_token_ids_sha256'] and len(ids) == meta['prompt_tokens']
        tokenized.append({'id': row['id'], 'category': row['category'],
                          'sample_sha256': meta['source_row_sha256'],
                          'prompt_sha256': meta['prompt_sha256'],
                          'prompt_token_ids_sha256': meta['prompt_token_ids_sha256'],
                          'prompt_tokens': len(ids), 'input_ids': ids,
                          'request_sha256': request_digest(meta, SETTINGS)})
    definition = {'version': 1, 'scope': 'Fixed250unscoredBFCL-derived inputs,three final models,offline scoring after all750outputs.',
                  'variants': ['base', 'reference32', 'masked32'], 'settings': SETTINGS,
                  'limits': {'total_attempts': 759, 'variant_attempts': 253, 'case_attempts': 2},
                  'models': spec['models'], 'model_repository': spec['model_repository'],
                  'model_revision': spec['model_revision'], 'base_model_manifest_sha256': spec['base_model_manifest_sha256'],
                  'expected_adapted_frozen_sha256': spec['expected_adapted_frozen_sha256'],
                  'generation_driver_sha256': spec['source_sha256']['benchmarks/bfcl_generation.py'],
                  'progress_source_sha256': spec['source_sha256']['benchmarks/generation_progress.py'],
                  'admission_sha256': spec['admission_sha256'],
                  'cases': [{'id_sha256': hashlib.sha256(r['id'].encode()).hexdigest(),
                             'sample_sha256': r['sample_sha256'], 'request_sha256': r['request_sha256']}
                            for r in tokenized]}
    validate_inputs(tokenized, definition)
    args.output.mkdir(mode=0o700, exist_ok=False)
    atomic_save(args.output/'definition.json', definition)
    path = args.output/'inputs-tokenized.jsonl'
    path.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in tokenized))
    path.chmod(0o600)
    progress = GenerationProgress(args.output/'progress', definition, create=True)
    assert progress.snapshot()['attempts'] == [] and progress.snapshot()['results'] == {}
    report = {'ready': True, 'declared_cases': 250, 'roles': definition['variants'],
              'definition_sha256': file_sha(args.output/'definition.json'), 'definition_owner_sha256': progress.owner,
              'tokenized_inputs_sha256': file_sha(path), 'max_prompt_tokens': max(r['prompt_tokens'] for r in tokenized),
              'all_prompt_and_token_hashes_match_frozen_admission': True,
              'group_prospective_limits': definition['limits'], 'neural_calls': 0, 'reference_files_read': 0,
              'no_model_weights_loaded': True, 'no_context_truncation_or_schema_repair': True,
              'source_sha256': spec['source_sha256'], 'private_prompts_and_vectors_not_exported': True}
    atomic_save(args.output/'preflight-report.json', report)
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['source', 'model', 'admission', 'protocol', 'output']:
        parser.add_argument('--'+name, type=Path, required=True)
    run(parser.parse_args())
