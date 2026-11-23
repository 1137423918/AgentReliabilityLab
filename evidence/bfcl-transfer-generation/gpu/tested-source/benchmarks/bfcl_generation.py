"""Unscored fixed-input generation with charged, immutable case results.

No reference answers or scorer are imported by this module. Completed failures
are final too. Cooperative segments retain the full experiment definition.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

from benchmarks.generation_progress import GenerationProgress, ProgressError, atomic_save, digest

SETTINGS = {'max_context': 32768, 'max_prompt_tokens': 8192, 'max_new_tokens': 1536,
            'temperature': 0, 'seed': 42, 'batch_size': 1, 'dtype': 'float16',
            'do_sample': False, 'num_beams': 1, 'use_cache': True, 'repetition_penalty': 1.0,
            'soft_generation_seconds': 90, 'TF32_matmul': False, 'attention_implementation': 'sdpa'}


def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def request_digest(meta, settings):
    return digest({'messages_sha256': meta['prompt_sha256'],
                   'prompt_token_ids_sha256': meta['prompt_token_ids_sha256'],
                   'settings': settings})


def validate_inputs(inputs, definition):
    assert len(inputs) == len(definition['cases'])
    assert len({r['id'] for r in inputs}) == len(inputs)
    for row, case in zip(inputs, definition['cases']):
        assert hashlib.sha256(row['id'].encode()).hexdigest() == case['id_sha256']
        assert row['sample_sha256'] == case['sample_sha256']
        assert row['request_sha256'] == case['request_sha256']
        assert row['request_sha256'] == request_digest(row, definition['settings'])
        assert digest(row['input_ids']) == row['prompt_token_ids_sha256']
        assert len(row['input_ids']) == row['prompt_tokens'] > 0
        assert row['prompt_tokens'] <= definition['settings']['max_prompt_tokens']
        assert row['prompt_tokens'] + definition['settings']['max_new_tokens'] <= definition['settings']['max_context']


def validate_cached(row, expected, variant, index):
    assert row['id'] == expected['id'] and row['sample_sha256'] == expected['sample_sha256']
    assert row['request_sha256'] == expected['request_sha256']
    assert row['variant'] == variant and row['case_index'] == index
    assert row['progress_metadata']['variant'] == variant
    assert row['progress_metadata']['case_index'] == index
    assert row['prediction']['error'] is None


def generate_segment(progress, variant, inputs, generate, *, max_new_cases=125,
                     deadline=None, reserve_margin=120, clock=time.monotonic,
                     on_event=lambda event: None):
    validate_inputs(inputs, progress.definition)
    assert 1 <= max_new_cases <= 125
    state = progress.snapshot()
    previous = progress.definition['variants'][:progress.definition['variants'].index(variant)]
    for role in previous:
        assert sum(key.startswith(role+':') for key in state['results']) == len(inputs), 'Previous role incomplete'
    generated = cached = 0
    stop = 'all_cases_completed'
    for index, expected in enumerate(inputs, 1):
        stored = progress.cached(variant, index)
        if stored is not None:
            validate_cached(stored, expected, variant, index)
            cached += 1
            continue
        if generated >= max_new_cases or (deadline is not None and clock()+reserve_margin >= deadline):
            stop = 'cooperative_segment_end'
            break
        sequence = progress.reserve(variant, index, expected['request_sha256'])
        on_event({'event': 'reserved', 'sequence': sequence, 'variant': variant,
                  'case_index': index, 'request_sha256': expected['request_sha256']})
        payload = generate(expected, sequence)
        assert isinstance(payload['raw_output'], str)
        assert isinstance(payload['generated_token_ids'], list)
        assert all(type(x) is int and x >= 0 for x in payload['generated_token_ids'])
        assert len(payload['generated_token_ids']) <= progress.definition['settings']['max_new_tokens']
        row = {'id': expected['id'], 'category': expected['category'], 'variant': variant,
               'case_index': index, 'sample_sha256': expected['sample_sha256'],
               'request_sha256': expected['request_sha256'],
               'prediction': {'raw_output': payload['raw_output'], 'error': None},
               'generated_token_ids': payload['generated_token_ids'],
               'generation_metadata': payload['metadata'],
               'progress_metadata': {'variant': variant, 'case_index': index,
                                     'attempt_sequence': sequence}}
        progress.complete(sequence, row)
        generated += 1
        on_event({'event': 'committed', 'sequence': sequence, 'variant': variant,
                  'case_index': index, 'row_sha256': digest(row)})
    final = progress.snapshot()
    known = sum(key.startswith(variant+':') for key in final['results'])
    return {'new_model_calls': generated, 'cached_cases_visited': cached,
            'variant_committed_cases': known, 'all_cases_completed': known == len(inputs),
            'stop_reason': stop, 'total_attempts': len(final['attempts']),
            'unknown_still_charged': sum(r['state'] == 'reserved' for r in final['attempts'])}


def canonical_base_name(name):
    if name.startswith('base_model.model.'):
        name = name[len('base_model.model.'):]
    return name.replace('.base_layer.', '.')


def run_model(args):
    import torch
    import peft
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
    from peft import PeftModel

    spec = json.loads(args.protocol.read_text())
    assert spec['phase'] == 'bfcl_generation'
    assert file_sha(Path(__file__)) == spec['driver_sha256']
    definition_path = args.experiment/'definition.json'
    assert file_sha(definition_path) == spec['definition_sha256']
    definition = json.loads(definition_path.read_text())
    assert definition['settings'] == SETTINGS
    assert file_sha(args.experiment/'inputs-tokenized.jsonl') == spec['tokenized_inputs_sha256']
    inputs = [json.loads(line) for line in (args.experiment/'inputs-tokenized.jsonl').read_text().splitlines()]
    validate_inputs(inputs, definition)
    progress = GenerationProgress(args.experiment/'progress', definition)
    assert progress.owner == spec['definition_owner_sha256']
    assert torch.__version__ == '2.6.0+cu124' and transformers.__version__ == '4.57.6' and peft.__version__ == '0.18.0'
    args.output.mkdir(mode=0o700, exist_ok=False)
    began = time.monotonic()
    report = {'status': 'starting', 'variant': args.variant, 'protocol_sha256': file_sha(args.protocol),
              'declared_cases': len(inputs), 'training_updates': 0, 'new_model_calls': 0,
              'no_gold_or_scoring': True, 'definition_owner_sha256': progress.owner}
    save = lambda: atomic_save(args.output/'report.json', report)
    operation = lambda kind, **kw: atomic_save(args.output/'current-operation.json',
        {'kind': kind, 'started_unix': time.time(), **kw})
    save()

    def tensor_hash(named):
        h = hashlib.sha256()
        for name, parameter in sorted(named):
            h.update(json.dumps([name, list(parameter.shape), str(parameter.dtype)], ensure_ascii=False,
                                sort_keys=True, separators=(',', ':')).encode())
            flat = parameter.detach().reshape(-1)
            for start in range(0, flat.numel(), 8*1024*1024):
                cpu = flat[start:start+8*1024*1024].to('cpu', copy=True).contiguous().view(torch.uint8)
                h.update(memoryview(cpu.numpy()))
        return h.hexdigest()

    with progress.worker(args.variant):
        try:
            state = progress.snapshot()
            for role in definition['variants'][:definition['variants'].index(args.variant)]:
                assert sum(k.startswith(role+':') for k in state['results']) == 250
            assert sum(k.startswith(args.variant+':') for k in state['results']) < 250
            set_seed(42)
            torch.set_num_threads(4)
            torch.backends.cuda.matmul.allow_tf32 = False
            torch.backends.cudnn.allow_tf32 = False
            assert torch.cuda.is_available() and torch.cuda.device_count() == 1
            assert torch.cuda.get_device_capability(0) == (8, 6)
            operation('model_load')
            tokenizer = AutoTokenizer.from_pretrained(str(args.model), local_files_only=True, trust_remote_code=False)
            model = AutoModelForCausalLM.from_pretrained(str(args.model), torch_dtype=torch.float16,
                device_map={'': 'cuda:0'}, local_files_only=True, trust_remote_code=False,
                use_safetensors=True, attn_implementation='sdpa').eval()
            assert {p.dtype for p in model.parameters()} == {torch.float16}
            fixed = definition['models'][args.variant]
            if args.variant != 'base':
                assert args.checkpoint is not None
                for name, expected in fixed['checkpoint_files_sha256'].items():
                    assert file_sha(args.checkpoint/name) == expected
                model = PeftModel.from_pretrained(model, str(args.checkpoint/'adapter'), is_trainable=False).eval()
                adapter_hash = tensor_hash([(n, p) for n, p in model.named_parameters() if 'lora_' in n])
                assert adapter_hash == fixed['adapter_parameter_sha256']
                assert all(p.dtype == (torch.float32 if 'lora_' in n else torch.float16) for n, p in model.named_parameters())
                assert tensor_hash([(n, p) for n, p in model.named_parameters() if 'lora_' not in n]) == definition['expected_adapted_frozen_sha256']
                report['adapter_sha256'] = adapter_hash
            else:
                assert args.checkpoint is None
            model.requires_grad_(False)
            base = [(canonical_base_name(n), p) for n, p in model.named_parameters() if 'lora_' not in n]
            assert len({n for n, p in base}) == len(base)
            assert sum(p.numel() for n, p in base) == 3085938688
            initial = tensor_hash(base)
            identity_path = args.experiment/'base-identity.json'
            with progress.lock():
                if identity_path.exists():
                    identity = json.loads(identity_path.read_text())
                    assert identity == {'owner_sha256': progress.owner, 'canonical_base_sha256': initial}
                else:
                    assert args.variant == 'base' and not state['attempts']
                    atomic_save(identity_path, {'owner_sha256': progress.owner, 'canonical_base_sha256': initial})
            report.update(model_loaded=True, initial_canonical_base_sha256=initial,
                          status='generating', load_seconds=round(time.monotonic()-began, 3))
            save()

            def event(value):
                with (args.output/'events.jsonl').open('a') as stream:
                    stream.write(json.dumps(value)+'\n')
                    stream.flush()
                    __import__('os').fsync(stream.fileno())
                if value['event'] == 'reserved':
                    operation('generating', case_index=value['case_index'], attempt_sequence=value['sequence'])
                else:
                    report['new_model_calls'] += 1
                    report['last_committed_case'] = value['case_index']
                    operation('committed', case_index=value['case_index'], attempt_sequence=value['sequence'])
                    save()
                    if report['new_model_calls'] % 10 == 0:
                        print(json.dumps({'variant': args.variant, 'new_committed': report['new_model_calls'],
                                          'last_case': value['case_index']}), flush=True)

            def generate(expected, sequence):
                ids = torch.tensor([expected['input_ids']], dtype=torch.long, device='cuda:0')
                attention = torch.ones_like(ids)
                started = time.monotonic()
                with torch.inference_mode():
                    output = model.generate(input_ids=ids, attention_mask=attention,
                        max_new_tokens=1536, do_sample=False, temperature=None, top_p=None, top_k=None,
                        repetition_penalty=1.0, num_beams=1, use_cache=True, max_time=90)
                torch.cuda.synchronize()
                generated = output[0, len(expected['input_ids']):].tolist()
                eos = model.generation_config.eos_token_id
                eos = {eos} if isinstance(eos, int) else set(eos or [])
                return {'raw_output': tokenizer.decode(generated, skip_special_tokens=True),
                        'generated_token_ids': generated,
                        'metadata': {'input_tokens': len(expected['input_ids']), 'generated_tokens': len(generated),
                                     'ended_with_eos': bool(generated and generated[-1] in eos),
                                     'generation_seconds': round(time.monotonic()-started, 4),
                                     'prompt_token_ids_sha256': expected['prompt_token_ids_sha256']}}

            result = generate_segment(progress, args.variant, inputs, generate,
                max_new_cases=125, deadline=began+1200, on_event=event)
            operation('final_base_hash')
            assert tensor_hash(base) == initial
            report.update(result, status='completed', frozen_base_unchanged=True,
                          wall_seconds=round(time.monotonic()-began, 3))
            operation('completed')
            save()
        except BaseException as error:
            report.update(status='failed', error={'type': type(error).__name__, 'message': str(error)[:500]},
                          wall_seconds=round(time.monotonic()-began, 3))
            save()
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['model', 'experiment', 'protocol', 'output']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--variant', choices=['base', 'reference32', 'masked32'], required=True)
    run_model(parser.parse_args())
