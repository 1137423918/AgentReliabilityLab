"""One predeclared, charged training segment; no failed-update replay.

The same production driver supports a separately budgeted GPU continuation
control and later full-pass arms. A clean planned boundary is the only resume.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import time
from benchmarks.fixed_reason_objective import active_causal_targets
from benchmarks.fullpass_schedule import validate_fullpass
from benchmarks.training_checkpoint import commit_checkpoint, restore_checkpoint, fsync_dir, write_json
from benchmarks.training_journal import TrainingJournal


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    temporary = path.with_name(path.name+'.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path); fsync_dir(path.parent)


def train(args):
    import torch
    import torch.nn.functional as F
    import peft
    import transformers
    from transformers import AutoModelForCausalLM, set_seed
    from peft import LoraConfig, get_peft_model
    spec = json.loads(args.spec.read_text())
    assert spec['phase'] in ['gpu_checkpoint_continuation_control', 'gpu_fullpass_training']
    for name, expected in spec['source_sha256'].items(): assert sha(args.source/name) == expected, name
    assert sha(Path(__file__)) == spec['source_sha256']['benchmarks/train_fullpass_segment.py']
    assert torch.__version__ == '2.6.0+cu124' and transformers.__version__ == '4.57.6' and peft.__version__ == '0.18.0'
    role = spec['trajectories'][args.role]; seed = role['seed']; profile = role['profile']
    assert profile in ['reference', 'masked'] and sha(args.schedule) == spec['schedules_sha256'][str(seed)]
    for name, expected in spec['data_sha256'].items(): assert sha(args.data/name) == expected, name
    assert sha(args.masked) == spec['masked_data_sha256']
    load = lambda p: [json.loads(line) for line in p.read_text().splitlines()]
    original, masked = load(args.data/'train-tokenized.jsonl'), load(args.masked)
    schedule = json.loads(args.schedule.read_text()); validate_fullpass(schedule, original, masked)
    assert len(original) == 3700 and schedule['seed'] == seed and schedule['updates'] == 164
    assert role['segments'][-1]['end'] <= schedule['updates']
    for segment in role['segments']:
        assert segment['forwards'] == 2+sum(len(s['segments']) for s in schedule['steps'][segment['start']:segment['end']])
    rows = original if profile == 'reference' else masked; index = {row['id_sha256']: row for row in rows}
    identity = {'spec_sha256': sha(args.spec), 'source_sha256': spec['source_sha256'],
                'seed': seed, 'profile': profile, 'trajectory': args.role, 'schedule_sha256': sha(args.schedule)}
    definition = {'identity': identity, 'segments': role['segments'],
                  'forward_cap': sum(s['forwards'] for s in role['segments']), 'optimizer_cap': role['segments'][-1]['end']}
    trajectory = args.experiment/args.role; journal = TrainingJournal(trajectory/'journal', definition)
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'starting', 'model_loaded': False, 'role': args.role, 'segment': args.segment,
              'spec_sha256': sha(args.spec), 'identity': identity, 'definition_owner_sha256': journal.owner}
    began = time.monotonic()
    def save(): write(args.output/'report.json', report)
    def operation(kind, **data): write(args.output/'current-operation.json', {'kind': kind, 'started_unix': time.time(), **data})
    def tensor_hash(named):
        h = hashlib.sha256()
        for name, parameter in sorted(named):
            h.update(json.dumps([name, list(parameter.shape), str(parameter.dtype)], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())
            flat = parameter.detach().reshape(-1)
            for a in range(0, flat.numel(), 8*1024*1024):
                cpu = flat[a:a+8*1024*1024].to('cpu', copy=True).contiguous().view(torch.uint8)
                h.update(memoryview(cpu.numpy()))
        return h.hexdigest()
    save()
    try:
        state = journal.snapshot(); assert state['next_segment'] == args.segment
        if args.segment:
            previous = json.loads((trajectory/('segment-%03d.json'%(args.segment-1))).read_text())
            assert previous['status'] == 'completed' and previous['checkpoint'] == state['checkpoint']
        journal.event('segment_begin', {'index': args.segment}); segment = role['segments'][args.segment]
        torch.set_num_threads(4); torch.backends.cuda.matmul.allow_tf32 = False; torch.backends.cudnn.allow_tf32 = False
        assert torch.cuda.is_available() and torch.cuda.device_count() == 1 and torch.cuda.get_device_capability(0) == (8, 6)
        operation('model_load'); set_seed(seed)
        model = AutoModelForCausalLM.from_pretrained(str(args.model), torch_dtype=torch.float16, device_map={'': 'cuda:0'},
            local_files_only=True, trust_remote_code=False, use_safetensors=True, attn_implementation='sdpa').eval()
        model.config.use_cache = False
        assert {p.dtype for p in model.parameters()} == {torch.float16}
        # Loading a fresh base must not change paired adapter RNG initialization.
        set_seed(seed)
        model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.0, target_modules=['q_proj', 'v_proj'],
            bias='none', task_type='CAUSAL_LM', init_lora_weights=True)).eval()
        trainable = [(n, p) for n, p in model.named_parameters() if p.requires_grad]
        frozen = [(n, p) for n, p in model.named_parameters() if not p.requires_grad]
        assert trainable and all('lora_' in n and p.dtype == torch.float32 for n, p in trainable)
        assert sum(p.numel() for _, p in frozen) == 3085938688 and float(model.config.attention_dropout) == 0.0
        assert all(int(torch.count_nonzero(p)) == 0 for n, p in trainable if '.lora_B.' in n)
        initial_adapter = tensor_hash(trainable); initial_frozen = tensor_hash(frozen)
        assert initial_frozen == spec['expected_initial_frozen_parameters_sha256']
        if str(seed) in spec['expected_initial_adapter_by_seed']:
            assert initial_adapter == spec['expected_initial_adapter_by_seed'][str(seed)]
        initial = {'seed': seed, 'adapter_sha256': initial_adapter, 'frozen_parameters_sha256': initial_frozen}
        initial_path = args.experiment/('initial-seed-%d.json'%seed)
        if initial_path.exists(): assert json.loads(initial_path.read_text()) == initial
        else: write_json(initial_path, initial); fsync_dir(initial_path.parent)
        optimizer = torch.optim.AdamW([p for _, p in trainable], lr=2e-4, betas=(.9, .999), eps=1e-8, weight_decay=0.0, foreach=False)
        scaler = torch.amp.GradScaler('cuda', init_scale=1024.0, growth_interval=2000)
        counters = {'completed_optimizer_updates': 0, 'training_labels': 0, 'training_sequences': 0, 'training_input_token_exposures': 0}
        if args.segment:
            receipt = state['checkpoint']
            counters = restore_checkpoint(trajectory/'checkpoints'/receipt['directory'], receipt['manifest_sha256'],
                trainable, optimizer, scaler, identity, cuda_devices=[0])
        previous_steps = schedule['steps'][:segment['start']]
        expected = {'completed_optimizer_updates': segment['start'],
                    'training_labels': sum(s['active_labels'][profile] for s in previous_steps),
                    'training_sequences': sum(len(s['segments']) for s in previous_steps),
                    'training_input_token_exposures': sum(t['sequence_tokens'] for s in previous_steps for t in s['segments'])}
        assert counters == expected
        report.update(model_loaded=True, initial_adapter_sha256=initial_adapter, initial_frozen_parameters_sha256=initial_frozen,
            trainable_parameter_count=sum(p.numel() for _, p in trainable), load_seconds=round(time.monotonic()-began, 3), restored_start=counters.copy())
        save()
        def forward(row, phase, update=None, position=None, standard=False):
            positions, targets = active_causal_targets(row, row['prompt_tokens'], len(row['input_ids']))
            n = len(targets); assert n > 0
            reserved = journal.event('forward_reserved', {'phase': phase, 'update': update, 'position': position, 'id_sha256': row['id_sha256']})
            sequence = reserved['forward_reserved']; operation('forward', sequence=sequence, phase=phase)
            ids = torch.tensor([row['input_ids']], dtype=torch.long, device='cuda:0'); mask = torch.ones_like(ids)
            if standard:
                labels = torch.full_like(ids, -100); labels[0, torch.tensor([p+1 for p in positions], device='cuda:0')] = torch.tensor(targets, device='cuda:0')
                loss = model(input_ids=ids, attention_mask=mask, labels=labels, use_cache=False).loss*n
            else:
                logits = model(input_ids=ids, attention_mask=mask, logits_to_keep=torch.tensor(positions, device='cuda:0'), use_cache=False).logits
                assert logits.shape == (1, n, model.config.vocab_size)
                loss = F.cross_entropy(logits[0].float(), torch.tensor(targets, device='cuda:0'), reduction='sum')
            assert bool(torch.isfinite(loss)); torch.cuda.synchronize(); value = float(loss.detach())
            journal.event('forward_completed', {'sequence': sequence, 'loss_sum': value, 'active_labels': n})
            return loss, value, n, sequence
        canary = index[schedule['steps'][0]['segments'][0]['id_sha256']]
        cpu_rng = torch.get_rng_state().clone(); cuda_rng = torch.cuda.get_rng_state(0).clone()
        with torch.no_grad():
            _, ordinary, n, _ = forward(canary, 'canary_standard', standard=True)
            _, sparse, _, _ = forward(canary, 'canary_sparse')
        assert math.isclose(ordinary/n, sparse/n, rel_tol=1e-4, abs_tol=1e-3)
        assert torch.equal(cpu_rng, torch.get_rng_state()) and torch.equal(cuda_rng, torch.cuda.get_rng_state(0)), 'Evaluation canary consumed RNG'
        report['standard_sparse_canary'] = {'standard_loss_sum': ordinary, 'sparse_loss_sum': sparse, 'labels': n, 'RNG_unchanged': True}; save()
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant': False}); model.enable_input_require_grads(); model.train()
        losses = []
        for step in schedule['steps'][segment['start']:segment['end']]:
            number = step['optimizer_step']+1; denominator = step['active_labels'][profile]
            journal.event('update_begin', {'update': number}); optimizer.zero_grad(set_to_none=True); count = 0; total = 0.0
            for position, item in enumerate(step['segments']):
                row = index[item['id_sha256']]
                loss, value, n, sequence = forward(row, 'training', number, position)
                assert n == item['active_labels'][profile]; count += n; total += value
                journal.event('backward_reserved', {'forward_sequence': sequence}); operation('backward', update=number, position=position)
                scaler.scale(loss/denominator).backward(); torch.cuda.synchronize()
                journal.event('backward_completed', {'forward_sequence': sequence}); del loss
            assert count == denominator and all(p.grad is None for _, p in frozen)
            assert all(p.grad is not None and bool(torch.isfinite(p.grad).all()) for _, p in trainable)
            scaler.unscale_(optimizer); norm = torch.nn.utils.clip_grad_norm_([p for _, p in trainable], 1.0, error_if_nonfinite=True)
            assert float(norm) > 0; scale = scaler.get_scale()
            journal.event('optimizer_reserved', {'update': number}); operation('optimizer_step', update=number)
            scaler.step(optimizer); scaler.update(); torch.cuda.synchronize()
            assert scaler.get_scale() >= scale, 'Skipped update, no retry'
            assert all(int(optimizer.state[p]['step']) == number for _, p in trainable)
            journal.event('optimizer_completed', {'update': number, 'gradient_norm': float(norm), 'mean_NLL': total/count})
            counters['completed_optimizer_updates'] = number; counters['training_labels'] += count
            counters['training_sequences'] += len(step['segments'])
            counters['training_input_token_exposures'] += sum(t['sequence_tokens'] for t in step['segments'])
            operation('checkpoint', update=number)
            receipt = commit_checkpoint(trajectory/'checkpoints'/('step-%03d'%number), trainable, optimizer, scaler, identity, counters, cuda_devices=[0])
            journal.event('checkpoint_committed', receipt)
            row = {'update': number, 'loss_sum': total, 'active_labels': count, 'mean_NLL': total/count,
                   'gradient_norm': float(norm), 'loss_scale': scaler.get_scale(), 'adapter_sha256': tensor_hash(trainable)}
            losses.append(row); print(json.dumps(row), flush=True)
        operation('final_parameter_check')
        assert tensor_hash(frozen) == initial_frozen
        for name, expected_sha in spec['source_sha256'].items(): assert sha(args.source/name) == expected_sha
        for name, expected_sha in spec['data_sha256'].items(): assert sha(args.data/name) == expected_sha
        assert sha(args.masked) == spec['masked_data_sha256'] and sha(args.schedule) == identity['schedule_sha256']
        report.update(status='completed', counters=counters, checkpoint=journal.snapshot()['checkpoint'],
            updates=losses, final_adapter_sha256=tensor_hash(trainable), frozen_parameters_unchanged=True,
            inputs_and_sources_unchanged=True, logical_forward_accounting='Explicit model.forward calls; autograd checkpoint recomputation is not an extra logical call, no equal-FLOPs claim.',
            wall_seconds=round(time.monotonic()-began, 3))
        write(trajectory/('segment-%03d.json'%args.segment), report)
        journal.event('segment_clean'); report['journal'] = journal.snapshot(); report['journal_sha256'] = sha(journal.path)
        operation('completed'); save(); return 0
    except BaseException as error:
        report.update(status='failed', error={'type': type(error).__name__, 'message': str(error)[:600]}, journal=journal.snapshot())
        if journal.snapshot()['status'] == 'running': journal.event('failed', report['error'])
        save(); raise
    finally:
        journal.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['model', 'data', 'masked', 'source', 'schedule', 'experiment', 'spec', 'output']:
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--role', required=True); p.add_argument('--segment', type=int, required=True)
    raise SystemExit(train(p.parse_args()))
