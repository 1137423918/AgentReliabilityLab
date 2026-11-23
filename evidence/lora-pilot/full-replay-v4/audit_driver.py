"""Read-only verification of a completed step32 artifact, not training resume."""
from pathlib import Path
import argparse,hashlib,json,math,os,time

def packed(x):return json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,r):
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(r,indent=2)+'\n');os.replace(t,p)
def append(p,r):
 with p.open('a') as f:f.write(json.dumps(r)+'\n');f.flush();os.fsync(f.fileno())


def run(a):
 import torch
 import torch.nn.functional as F
 from transformers import AutoModelForCausalLM,set_seed
 from peft import PeftModel
 from safetensors.torch import load_file
 spec=json.loads(a.spec.read_text());assert sha(Path(__file__))==spec['full_audit_driver_sha256'];a.output.mkdir(exist_ok=False);began=time.monotonic();original=json.loads((a.original/'report.json').read_text());ck=a.original/'step-032';manifest=json.loads((ck/'manifest.json').read_text())
 for n,d in manifest.items():assert sha(ck/n)==d,n
 state=json.loads((ck/'training-state.json').read_text());assert state['completed_optimizer_updates']==32 and state['training_labels']==65536;assert state['spec_sha256']==spec['original_full_protocol_sha256'];assert all('lora_' in n for n in state['parameter_order'])
 opt=load_file(str(ck/'optimizer-and-rng.safetensors'),device='cpu');assert all(int(opt['p%04d.step'%i])==32 for i in range(len(state['parameter_order'])));assert all(bool(torch.isfinite(t).all()) for k,t in opt.items() if not k.startswith('rng.'));del opt
 for n,d in spec['data_sha256'].items():assert sha(a.data/n)==d,n
 dev=[json.loads(x) for x in (a.data/'dev_clean-tokenized.jsonl').read_text().splitlines()];val=[json.loads(x) for x in (a.data/'test-tokenized.jsonl').read_text().splitlines()];assert len(dev)==197 and len(val)==79
 report={'status':'starting','training_run':False,'optimizer_updates_executed':0,'original_Full_updates':32,'original_Full_training_labels':65536,'original_run_remains_terminal2':True,'original_in_memory_final_base_hash_not_recorded':True,'forward_reserved':0,'forward_completed':0,'checkpoint_manifest_verified':True,'all_optimizer_step_tensors32':True}
 def save():write(a.output/'report.json',report)
 def status(kind):write(a.output/'current-operation.json',{'kind':kind,'started_unix':time.time()})
 def fingerprint(named):
  h=hashlib.sha256()
  for n,p in sorted(named):
   h.update(packed([n,list(p.shape),str(p.dtype)]));flat=p.detach().reshape(-1)
   for i in range(0,flat.numel(),8*1024*1024):h.update(memoryview(flat[i:i+8*1024*1024].to('cpu',copy=True).contiguous().view(torch.uint8).numpy()))
  return h.hexdigest()
 save();status('model_load');torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False;set_seed(42)
 model=AutoModelForCausalLM.from_pretrained(str(a.model),torch_dtype=torch.float16,device_map={'':'cpu'},use_safetensors=True,local_files_only=True,trust_remote_code=False,attn_implementation='sdpa');model.config.use_cache=False;model=PeftModel.from_pretrained(model,str(ck/'adapter'),is_trainable=False).eval();assert not any(p.requires_grad for p in model.parameters())
 base=[(n,p) for n,p in model.named_parameters() if 'lora_' not in n];adapter=[(n,p) for n,p in model.named_parameters() if 'lora_' in n];assert fingerprint(base)==original['initial_frozen_parameters_sha256'];assert fingerprint(adapter)==state['adapter_sha256'];report.update(reconstructed_base_matches_original_initial=True,reloaded_adapter_parameter_hash=state['adapter_sha256']);save();model.to('cuda:0');report['model_loaded']=True;save()
 def evaluate(row,role):
  seq=report['forward_reserved']+1;assert seq<=277;append(a.output/'events.jsonl',{'event':'forward_reserved','sequence':seq,'role':role,'id_sha256':row['id_sha256']});report['forward_reserved']=seq;status('forward');p=row['prompt_tokens'];ids=torch.tensor([row['input_ids']],dtype=torch.long,device='cuda:0');pos=torch.arange(p-1,len(row['input_ids'])-1,device='cuda:0');logits=model(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False,logits_to_keep=pos).logits;loss=F.cross_entropy(logits[0].float(),ids[0,p:],reduction='sum');assert bool(torch.isfinite(loss));torch.cuda.synchronize();v=float(loss);report['forward_completed']+=1;append(a.output/'events.jsonl',{'event':'forward_completed','sequence':seq,'role':role,'id_sha256':row['id_sha256'],'loss_sum':v,'target_tokens':row['target_tokens']});return v
 try:
  with torch.no_grad():
   for name,rows in [('dev',dev),('val',val)]:
    old=json.loads((a.original/('after_'+name+'.json')).read_text());assert len(old['cases'])==len(rows);out=[];total=tokens=0;max_difference=0
    for row,expected in zip(rows,old['cases']):
     assert row['id_sha256']==expected['id_sha256'] and row['target_tokens']==expected['target_tokens'];v=evaluate(row,name);n=row['target_tokens'];delta=abs(v-expected['loss_sum'])/n;assert math.isclose(v/n,expected['loss_sum']/n,rel_tol=1e-4,abs_tol=1e-3);max_difference=max(max_difference,delta);total+=v;tokens+=n;out.append({'id_sha256':row['id_sha256'],'target_tokens':n,'original_loss_sum':expected['loss_sum'],'reloaded_loss_sum':v,'mean_NLL_absolute_difference':delta})
    r={'count':len(rows),'target_tokens':tokens,'loss_sum':total,'token_weighted_NLL':total/tokens,'max_case_mean_NLL_difference':max_difference,'all_cases_match_tolerance':True,'cases':out};write(a.output/(name+'.json'),r);report[name]={k:v for k,v in r.items() if k!='cases'};save()
   with model.disable_adapter():v=evaluate(dev[0],'disabled_adapter_base_canary')
   expected=original['sparse_vs_standard_loss']['selected_positions_sum'];assert math.isclose(v/dev[0]['target_tokens'],expected/dev[0]['target_tokens'],rel_tol=1e-4,abs_tol=1e-3)
  assert report['forward_reserved']==report['forward_completed']==277;assert all(sha(ck/n)==d for n,d in manifest.items());report.update(status='completed',read_only_checkpoint_verified=True,disabled_adapter_matches_original_base_canary=True,checkpoint_files_unchanged=True,wall_seconds=round(time.monotonic()-began,3),limitations=['This is a separate read-only reconstruction/replay, not completion of the original interrupted process.','The original in-memory post-training frozen-parameter hash remains missing; no retrospective pass is claimed.','Teacher-forced NLL is not generated tool accuracy.']);status('completed');save();return 0
 except BaseException as e:report.update(status='failed',error={'type':type(e).__name__,'message':str(e)});save();raise


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--original',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--spec',type=Path,required=True);a=p.parse_args();raise SystemExit(run(a))
