"""A traceable local-model baseline using the pinned upstream prompts/scorer.

Preparation tokenizes all clean single-turn cases without loading a model.
Inference makes exactly one greedy generation per case and never repairs it.
Full prompts and generated IDs belong in private, admitted local storage.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, value):
    temp = path.with_name(path.name+".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n")
    os.replace(temp, path)


def append(path, value):
    with path.open("a") as f:
        f.write(json.dumps(value, ensure_ascii=False)+"\n")
        f.flush()
        os.fsync(f.fileno())


def modules(root):
    sys.path.insert(0, str(root/'scripts'))
    import run_eval
    assert Path(inspect.getfile(run_eval)).resolve() == (root/'scripts/run_eval.py').resolve()
    path = root/'leaderboard/scoring/eval_results.py'
    spec = importlib.util.spec_from_file_location('official_tooluse_scorer', path)
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    return run_eval, scorer


def load(root):
    runner, scorer = modules(root)
    data = root/'hf_data/datasets/api_eval/clean.jsonl'
    samples = [s for s in runner.load_samples(data) if not runner.is_multi_turn(s)]
    assert len(samples) == 199 and len({s['id'] for s in samples}) == 199
    return runner, scorer, samples, data


def prepare(args):
    from transformers import AutoTokenizer
    if args.output.exists():
        raise FileExistsError('Admission output must be new')
    runner, _, samples, data = load(args.upstream)
    tokenizer = AutoTokenizer.from_pretrained(str(args.model), local_files_only=True, trust_remote_code=False)
    rows = []
    for sample in samples:
        messages = runner.build_messages(sample, use_fc=False)
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
        rows.append({'id': sample['id'], 'benchmark': sample['benchmark'],
                     'sample_sha256': sha(encoded(sample)), 'messages_sha256': sha(encoded(messages)),
                     'prompt_token_ids_sha256': sha(encoded(ids)), 'input_tokens': len(ids),
                     'within_context': len(ids)+args.max_tokens <= args.max_context})
    output = {'scope': 'All199 official clean single-turn cases; no model loaded or GPU work.',
              'cases': rows, 'data_sha256': sha(data.read_bytes()), 'case_count': len(rows),
              'max_input_tokens': max(r['input_tokens'] for r in rows),
              'max_context': args.max_context, 'max_new_tokens': args.max_tokens,
              'all_within_context': all(r['within_context'] for r in rows),
              'tokenizer_class': type(tokenizer).__name__,
              'runner_sha256': sha((args.upstream/'scripts/run_eval.py').read_bytes()),
              'scorer_sha256': sha((args.upstream/'leaderboard/scoring/eval_results.py').read_bytes()),
              'driver_sha256': sha(Path(__file__).read_bytes()), 'model_inference': False}
    write(args.output, output)
    print(json.dumps({k:output[k] for k in ['case_count','max_input_tokens','all_within_context','model_inference']}), flush=True)
    return 0 if output['all_within_context'] else 2


def required_key_screen(sample, prediction):
    result = {'predicted_calls': len(prediction['tool_calls']), 'known_name_calls': 0,
              'calls_missing_declared_required_keys': 0, 'unknown_name_calls': 0,
              'schema_unassessable_calls': 0}
    for call in prediction['tool_calls']:
        candidates = [t for t in sample['tools'] if t.get('name') == call.get('name')]
        if not candidates:
            result['unknown_name_calls'] += 1
            continue
        result['known_name_calls'] += 1
        params = call.get('parameters') or call.get('arguments') or {}
        schemas = [t.get('parameters') for t in candidates]
        if any(not isinstance(s,dict) or not isinstance(s.get('required',[]),list)
               or not all(isinstance(k,str) for k in s.get('required',[])) for s in schemas):
            result['schema_unassessable_calls'] += 1
            continue
        if not isinstance(params, dict) or all(not set(s.get('required',[])) <= set(params) for s in schemas):
            result['calls_missing_declared_required_keys'] += 1
    return result


def run(args):
    import importlib.metadata
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
    runner, scorer, samples, data = load(args.upstream)
    admission = json.loads(args.admission.read_text())
    assert admission['all_within_context'] and admission['data_sha256']==sha(data.read_bytes())
    assert admission['driver_sha256']==sha(Path(__file__).read_bytes())
    assert admission['max_context']==args.max_context and admission['max_new_tokens']==args.max_tokens
    assert [x['id'] for x in admission['cases']] == [s['id'] for s in samples]
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status':'starting','completed_cases':0,'declared_cases':199,'model_repository':args.model_id,
              'model_revision':args.revision,'data_sha256':sha(data.read_bytes()),
              'driver_sha256':sha(Path(__file__).read_bytes()),'runner_sha256':admission['runner_sha256'],
              'scorer_sha256':admission['scorer_sha256'],'dtype':'float16','temperature':0,
              'seed':42,'batch_size':1,'max_new_tokens':args.max_tokens,'max_context':args.max_context,
              'soft_generation_seconds':120,'retries':0,'parameter_feedback':False,'model_calls':0,
              'input_tokens':0,'generated_token_ids':0,'training_run':False,'all22_perturbations_evaluated':False}
    started = time.monotonic()
    write(args.output/'report.json', report)
    tokenizer = AutoTokenizer.from_pretrained(str(args.model), local_files_only=True, trust_remote_code=False)
    set_seed(42)
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    assert torch.cuda.is_available() and torch.cuda.device_count()==1
    model = AutoModelForCausalLM.from_pretrained(str(args.model), torch_dtype=torch.float16,
        device_map={'':'cuda:0'}, use_safetensors=True, local_files_only=True,
        trust_remote_code=False, attn_implementation='sdpa').eval()
    assert {str(p.device) for p in model.parameters()}=={'cuda:0'}
    assert {p.dtype for p in model.parameters()}=={torch.float16}
    report['adapter_used'] = args.adapter is not None
    if args.adapter is not None:
        from peft import PeftModel
        files = ['adapter_config.json', 'adapter_model.safetensors']
        report['adapter_artifact_sha256'] = {n: sha((args.adapter/n).read_bytes()) for n in files}
        model = PeftModel.from_pretrained(model, str(args.adapter), is_trainable=False).eval()
        assert {str(p.device) for p in model.parameters()}=={'cuda:0'}
        assert all(p.dtype == (torch.float32 if 'lora_' in n else torch.float16)
                   for n,p in model.named_parameters())
        assert not any(p.requires_grad for p in model.parameters())
    report.update(status='running', load_seconds=round(time.monotonic()-started,3),
                  model_parameter_count=sum(p.numel() for p in model.parameters()),
                  GPU_name=torch.cuda.get_device_name(0),GPU_compute_capability=torch.cuda.get_device_capability(0),
                  packages={d.metadata['Name']:d.version for d in importlib.metadata.distributions()})
    write(args.output/'report.json',report)
    case_state=args.output/'current-call.json'
    class Client:
        def __init__(self):
            self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))
            self.call=None
        def create(self, *, messages, max_tokens, temperature, **kwargs):
            assert not kwargs.get('tools') and temperature==0 and max_tokens==args.max_tokens
            assert report['model_calls'] < 199, 'Fixed generation budget exhausted; no retry'
            began=time.monotonic();inputs=tokenizer.apply_chat_template(messages,tokenize=True,
                add_generation_prompt=True,return_tensors='pt',return_dict=True)
            inputs.pop('token_type_ids',None);ids=inputs['input_ids'][0].tolist();expected=admission['cases'][report['completed_cases']]
            assert sha(encoded(messages))==expected['messages_sha256'] and sha(encoded(ids))==expected['prompt_token_ids_sha256']
            assert len(ids)+max_tokens<=args.max_context
            append(args.output/'calls.jsonl',{'event':'reserved','sequence':report['model_calls']+1,
                'case':expected['id'],'messages':messages,'prompt_token_ids':ids,'started_unix':time.time()})
            report['model_calls']+=1
            write(case_state,{'status':'generating','case':expected['id'],'started_unix':time.time()})
            inputs=inputs.to('cuda:0');torch.cuda.synchronize();gen_started=time.monotonic()
            with torch.inference_mode():
                output=model.generate(**inputs,max_new_tokens=max_tokens,do_sample=False,
                    temperature=None,top_p=None,top_k=None,repetition_penalty=1.0,
                    num_beams=1,use_cache=True,max_time=120)
            torch.cuda.synchronize();gen_seconds=time.monotonic()-gen_started
            generated=output[0,len(ids):].tolist();text=tokenizer.decode(generated,skip_special_tokens=True)
            eos=model.generation_config.eos_token_id; eos={eos} if isinstance(eos,int) else set(eos or [])
            self.call={'sequence':report['model_calls'],'case':expected['id'],'input_tokens':len(ids),
                'generated_token_ids':generated,'raw_output':text,'ended_with_eos':bool(generated and generated[-1] in eos),
                'generation_seconds':round(gen_seconds,4),'call_wall_seconds':round(time.monotonic()-began,4),
                'peak_GPU_allocated_bytes':torch.cuda.max_memory_allocated(),
                'peak_GPU_reserved_bytes':torch.cuda.max_memory_reserved()}
            append(args.output/'calls.jsonl',{'event':'completed',**self.call})
            write(case_state,{'status':'returned','case':expected['id']})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text,tool_calls=None))])
    client=Client();results=[]
    try:
        for sample, expected in zip(samples,admission['cases']):
            assert sha(encoded(sample))==expected['sample_sha256']
            prediction=runner.run_single_pass(sample,client,model_name=args.model_id,
                temperature=0,max_tokens=args.max_tokens,use_fc=False)
            if prediction['error']:
                append(args.output/'predictions.jsonl',{'id':sample['id'],'prediction':prediction,'scored':False})
                raise RuntimeError('Generation failed without retry: '+prediction['error'])
            score=scorer.score_record({'benchmark':sample['benchmark'],'eval_config':sample['eval_config'],
                'golden_answers':sample['golden_answers'],'prediction':prediction})
            row={'id':sample['id'],'benchmark':sample['benchmark'],'category':sample.get('category'),
                 'sample_sha256':expected['sample_sha256'],'prediction':prediction,'official_score':score,
                 'required_key_screen':required_key_screen(sample,prediction),
                 'generation_metadata':{k:v for k,v in client.call.items() if k not in ['raw_output','generated_token_ids']}}
            append(args.output/'predictions.jsonl',row);results.append(row)
            report['completed_cases']=len(results);report['input_tokens']+=client.call['input_tokens'];report['generated_token_ids']+=len(client.call['generated_token_ids'])
            write(args.output/'report.json',report)
            if len(results)%10==0:print(json.dumps({'completed':len(results),'declared':199,'model_calls':report['model_calls']}),flush=True)
        summary=defaultdict(lambda:{'n':0,'correct':0,'score_sum':0.0})
        for row in results:
            for name in ['overall',row['benchmark']]:
                summary[name]['n']+=1;summary[name]['correct']+=bool(row['official_score']['correct']);summary[name]['score_sum']+=row['official_score']['score']
        report.update(status='completed',scores=dict(summary),truncated_or_soft_time_stopped=sum(not x['generation_metadata']['ended_with_eos'] for x in results),
            required_key_violation_cases=sum(x['required_key_screen']['calls_missing_declared_required_keys']>0 for x in results),
            wall_seconds=round(time.monotonic()-started,3),model_inference=True,
            limitations=['199 clean single-turn tool-call predictions, not all3721 benchmark cases or autonomous repository repair.',
                'Original deterministic scorer includes omitted-argument/name-only compatibility; scores are not full schema validity, real tool execution or prose truth.',
                'The extra required-key screen is narrower than complete JSON Schema validation.',
                'Optional checkpoint evaluation preserves the provided saved LoRA weights; this driver never trains them.',
                'No evaluation-time retry/repair/training or scripted replies. FP16/backend differs from released paper settings.',
                'Token IDs are measured local generation counts, not billing; greedy seeded execution is not a bitwise reproducibility guarantee.'])
        assert report['model_calls']==report['completed_cases']==199
        return 0
    except BaseException as error:
        report.update(status='failed',error={'type':type(error).__name__,'message':str(error)},wall_seconds=round(time.monotonic()-started,3))
        raise
    finally:
        write(args.output/'report.json',report)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['prepare','run']);p.add_argument('--upstream',type=Path,required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--max-context',type=int,default=32768);p.add_argument('--max-tokens',type=int,default=1024);p.add_argument('--admission',type=Path);p.add_argument('--adapter',type=Path);p.add_argument('--model-id',default='Qwen/Qwen2.5-3B-Instruct');p.add_argument('--revision',default='aa8e72537993ba99e69dfaafa59ed015b17504d1');a=p.parse_args()
    try:
        return prepare(a) if a.mode=='prepare' else run(a)
    except BaseException as error:
        report_path = a.output/'report.json'
        if a.mode=='run' and report_path.exists():
            report = json.loads(report_path.read_text())
            report.update(status='failed',error={'type':type(error).__name__,'message':str(error)})
            write(report_path,report)
        raise


if __name__=='__main__':
    raise SystemExit(main())
