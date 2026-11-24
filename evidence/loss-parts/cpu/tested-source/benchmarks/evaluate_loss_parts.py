"""Charged teacher-forced loss decomposition; no training or text generation."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import time

from benchmarks.bfcl_generation import canonical_base_name
from benchmarks.causal_loss_parts import PARTS, causal_selection, digest, file_sha, summarize_token_losses
from benchmarks.generation_progress import GenerationProgress, atomic_save


def evaluate_case(progress, variant, index, case, callback):
    assert progress.cached(variant, index) is None, 'Closed/completed forward cannot be replayed'
    sequence = progress.reserve(variant, index, case['request_sha256'])
    value = callback(case, sequence)
    assert math.isfinite(value['loss_sum']) and value['loss_sum'] >= 0
    row = {'id': case['id'], 'sample_sha256': case['sample_sha256'],
           'request_sha256': case['request_sha256'], 'variant': variant,
           'case_index': index, 'kind': case['kind'], 'split': case['split'],
           'id_sha256': case['id_sha256'], 'component_sha256': case['component_sha256'],
           'target_tokens': case['target_tokens'], **value}
    progress.complete(sequence, row)
    return row


def run(args):
    import torch
    import torch.nn.functional as F
    import peft, transformers
    from transformers import AutoModelForCausalLM, set_seed
    from peft import PeftModel
    spec = json.loads(args.protocol.read_text())
    assert spec['phase'] == 'gpu_loss_parts' and file_sha(Path(__file__)) == spec['driver_sha256']
    assert torch.__version__ == '2.6.0+cu124' and transformers.__version__ == '4.57.6' and peft.__version__ == '0.18.0'
    assert file_sha(args.experiment/'definition.json') == spec['definition_sha256']
    assert file_sha(args.experiment/'cases-private.jsonl') == spec['cases_sha256']
    definition = json.loads((args.experiment/'definition.json').read_text())
    cases = [json.loads(line) for line in (args.experiment/'cases-private.jsonl').read_text().splitlines()]
    assert len(cases) == 277
    progress = GenerationProgress(args.experiment/'progress', definition)
    assert progress.owner == spec['definition_owner_sha256']
    args.output.mkdir(mode=0o700, exist_ok=False)
    began = time.monotonic()
    report = {'status': 'starting', 'variant': args.variant, 'teacher_forward_reserved': 0,
              'teacher_forward_completed': 0, 'training_updates': 0, 'text_generations': 0,
              'protocol_sha256': file_sha(args.protocol), 'owner_sha256': progress.owner}
    save = lambda: atomic_save(args.output/'report.json', report)
    operation = lambda kind, **kw: atomic_save(args.output/'current-operation.json',
        {'kind': kind, 'started_unix': time.time(), **kw})
    def tensor_hash(named):
        h = hashlib.sha256()
        for name, p in sorted(named):
            h.update(json.dumps([name, list(p.shape), str(p.dtype)], ensure_ascii=False,
                sort_keys=True, separators=(',', ':')).encode())
            flat = p.detach().reshape(-1)
            for start in range(0, flat.numel(), 8*1024*1024):
                data = flat[start:start+8*1024*1024].to('cpu', copy=True).contiguous().view(torch.uint8)
                h.update(memoryview(data.numpy()))
        return h.hexdigest()
    save()
    with progress.worker(args.variant):
        try:
            state = progress.snapshot()
            assert not any(row['variant'] == args.variant for row in state['attempts']), 'No role restart or retry'
            for previous in definition['variants'][:definition['variants'].index(args.variant)]:
                assert sum(key.startswith(previous+':') for key in state['results']) == 277
            set_seed(42); torch.set_num_threads(4)
            torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
            assert torch.cuda.is_available() and torch.cuda.device_count() == 1 and torch.cuda.get_device_capability(0) == (8, 6)
            operation('model_load')
            model = AutoModelForCausalLM.from_pretrained(str(args.model), torch_dtype=torch.float16,
                device_map={'': 'cuda:0'}, local_files_only=True, trust_remote_code=False,
                use_safetensors=True, attn_implementation='sdpa').eval()
            assert {p.dtype for p in model.parameters()} == {torch.float16}
            checkpoint = definition['models'][args.variant]
            if args.variant != 'base':
                assert args.checkpoint is not None
                assert all(file_sha(args.checkpoint/name) == expected for name, expected in checkpoint['checkpoint_files_sha256'].items())
                model = PeftModel.from_pretrained(model, str(args.checkpoint/'adapter'), is_trainable=False).eval()
            else:
                assert args.checkpoint is None
            model.requires_grad_(False); model.config.use_cache = False
            base = [(canonical_base_name(n), p) for n, p in model.named_parameters() if 'lora_' not in n]
            adapters = [(n, p) for n, p in model.named_parameters() if 'lora_' in n]
            assert sum(p.numel() for n, p in base) == 3085938688
            assert all(p.dtype == torch.float16 for n, p in base) and all(p.dtype == torch.float32 for n, p in adapters)
            initial_base = tensor_hash(base); initial_adapter = tensor_hash(adapters) if adapters else None
            assert initial_base == spec['canonical_base_sha256']
            assert initial_adapter == checkpoint['adapter_parameter_sha256']
            report.update(model_loaded=True, canonical_base_sha256=initial_base, adapter_sha256=initial_adapter,
                          status='evaluating', load_seconds=round(time.monotonic()-began, 3)); save()
            rows, standard = [], None
            def forward(case, sequence):
                report['teacher_forward_reserved'] += 1
                operation('teacher_forward', sequence=sequence, kind_of_forward=case['kind'])
                save()
                assert digest({'input_ids': case['input_ids'], 'labels': case['labels'], 'parts': case['parts']}) == case['sample_sha256']
                positions, targets, parts = causal_selection(case)
                assert len(case['input_ids']) <= 4096
                ids = torch.tensor([case['input_ids']], dtype=torch.long, device='cuda:0')
                mask = torch.ones_like(ids)
                started = time.monotonic()
                with torch.inference_mode():
                    if case['kind'] == 'standard_canary':
                        labels = torch.tensor([case['labels']], dtype=torch.long, device='cuda:0')
                        value = float((model(input_ids=ids, attention_mask=mask, labels=labels, use_cache=False).loss*len(targets)).float())
                        result = {'loss_sum': value, 'parts': None}
                    else:
                        chosen = torch.tensor(positions, dtype=torch.long, device='cuda:0')
                        logits = model(input_ids=ids, attention_mask=mask, logits_to_keep=chosen, use_cache=False).logits
                        assert logits.shape == (1, len(targets), model.config.vocab_size)
                        values = F.cross_entropy(logits[0].float(), torch.tensor(targets, device='cuda:0'), reduction='none').double().tolist()
                        result = {'loss_sum': math.fsum(values), 'parts': summarize_token_losses(values, parts)}
                torch.cuda.synchronize()
                return {**result, 'wall_seconds': round(time.monotonic()-started, 5)}
            for index, case in enumerate(cases, 1):
                row = evaluate_case(progress, args.variant, index, case, forward)
                report['teacher_forward_completed'] += 1
                if row['kind'] == 'standard_canary':
                    assert index == 1; standard = row
                else:
                    expected = case['legacy_loss_sum'][args.variant]
                    assert math.isclose(row['loss_sum']/row['target_tokens'], expected/row['target_tokens'], rel_tol=1e-4, abs_tol=1e-3), 'Whole-answer NLL differs from archived check; no retry'
                    if index == 2:
                        assert standard['id_sha256'] == row['id_sha256']
                        assert math.isclose(standard['loss_sum']/row['target_tokens'], row['loss_sum']/row['target_tokens'], rel_tol=1e-4, abs_tol=1e-3)
                    rows.append(row)
                operation('forward_committed', sequence=index)
                if index % 40 == 0:
                    save(); print(json.dumps({'variant': args.variant, 'committed_forwards': index}), flush=True)
            operation('final_parameter_hash')
            assert tensor_hash(base) == initial_base
            assert (tensor_hash(adapters) if adapters else None) == initial_adapter
            assert all(p.grad is None and not p.requires_grad for p in model.parameters())
            results = {}
            for split in ['dev_clean', 'test']:
                selected = [row for row in rows if row['split'] == split]
                tokens = sum(row['target_tokens'] for row in selected)
                total = math.fsum(row['loss_sum'] for row in selected)
                components = {}
                for name in PARTS:
                    n = sum(row['parts'][name]['tokens'] for row in selected)
                    loss = math.fsum(row['parts'][name]['loss_sum'] for row in selected)
                    components[name] = {'tokens': n, 'loss_sum': loss, 'token_weighted_NLL': loss/n if n else None}
                assert sum(v['tokens'] for v in components.values()) == tokens
                assert math.isclose(math.fsum(v['loss_sum'] for v in components.values()), total, rel_tol=1e-12, abs_tol=1e-8)
                results[split] = {'cases': len(selected), 'target_tokens': tokens, 'loss_sum': total,
                    'token_weighted_NLL': total/tokens, 'parts': components}
            assert report['teacher_forward_reserved'] == report['teacher_forward_completed'] == 277
            atomic_save(args.output/'case-loss-parts.json', {'cases': rows})
            report.update(status='completed', results=results, standard_canary_matches=True,
                archived_whole_NLL_matches=True, all_parameters_unchanged=True, no_gradients_or_updates=True,
                wall_seconds=round(time.monotonic()-began, 3))
            operation('completed'); save()
        except BaseException as error:
            report.update(status='failed', error={'type': type(error).__name__, 'message': str(error)[:500]},
                          forward_unknown_still_charged=report['teacher_forward_reserved']-report['teacher_forward_completed'])
            save(); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['model', 'experiment', 'protocol', 'output']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--variant', choices=['base', 'reference32', 'masked32'], required=True)
    run(parser.parse_args())
