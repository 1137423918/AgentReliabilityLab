"""Run the fixed paired SFT pilot with durable forward/update accounting.

Private data and checkpoints only. Labels, not examples or sequence tokens,
set the optimizer-update denominator. No resume or generation retries.
"""
from __future__ import annotations
import argparse,contextlib,hashlib,json,math,os,time
from pathlib import Path


def packed(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(x,indent=2)+'\n');os.replace(t,p)
def append(p,x):
 with p.open('a') as f:f.write(json.dumps(x)+'\n');f.flush();os.fsync(f.fileno())
def load(p):return [json.loads(x) for x in p.read_text().splitlines()]


def train(args):
 import torch
 import torch.nn.functional as F
 import peft,transformers
 from transformers import AutoModelForCausalLM,set_seed
 from peft import LoraConfig,get_peft_model,PeftModel
 from safetensors.torch import save_file
 spec=json.loads(args.spec.read_text());assert sha(Path(__file__))==spec['driver_sha256']
 assert torch.__version__=='2.6.0+cu124' and transformers.__version__=='4.57.6' and peft.__version__=='0.18.0'
 for name,d in spec['data_sha256'].items():assert sha(args.data/name)==d,name
 args.output.mkdir(parents=True,exist_ok=False);began=time.monotonic();journal=args.output/'events.jsonl';current=args.output/'current-operation.json'
 schedule=json.loads((args.data/(args.variant+'-schedule.json')).read_text());rows=load(args.data/(args.variant+'-tokenized.jsonl'));index={r['id_sha256']:r for r in rows};dev=load(args.data/'dev_clean-tokenized.jsonl');val=load(args.data/'test-tokenized.jsonl');assert len(index)==3700 and len(dev)==197 and len(val)==79
 assert len(schedule['steps'])==32 and all(sum(s['supervised_tokens'] for s in p['segments'])==2048 for p in schedule['steps'])
 for r in rows+dev+val:
  p=r['prompt_tokens'];assert p>=1 and len(r['labels'])==len(r['input_ids']) and r['labels'][:p]==[-100]*p and r['labels'][p:]==r['input_ids'][p:]
  assert sum(x!=-100 for x in r['labels'][1:])==r['target_tokens']
 assert not {r['component_sha256'] for r in rows}&{r['component_sha256'] for r in dev+val}
 report={'status':'starting','variant':args.variant,'spec_sha256':sha(args.spec),'driver_sha256':sha(Path(__file__)),'model_revision':spec['model_revision'],'training_run':False,'completed_optimizer_updates':0,'completed_training_labels':0,'logical_forward_reserved':0,'logical_forward_completed':0,'training_segments_backward_completed':0,'training_input_token_exposures':0,'role_counts':{},'resume_supported':False}
 def save():write(args.output/'report.json',report)
 def status(kind,**kw):write(current,{'kind':kind,'started_unix':time.time(),**kw})
 def tensor_hash(named):
  h=hashlib.sha256()
  for n,p in sorted(named):
   h.update(packed([n,list(p.shape),str(p.dtype)]));flat=p.detach().reshape(-1)
   for a in range(0,flat.numel(),8*1024*1024):
    cpu=flat[a:a+8*1024*1024].to('cpu',copy=True).contiguous().view(torch.uint8);h.update(memoryview(cpu.numpy()))
  return h.hexdigest()
 def close(a,b):return math.isclose(a,b,rel_tol=1e-4,abs_tol=1e-3)
 torch.set_num_threads(4);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False;set_seed(42)
 assert torch.cuda.is_available() and torch.cuda.device_count()==1;assert torch.cuda.get_device_capability(0)==(8,6)
 save();status('model_load')
 model=AutoModelForCausalLM.from_pretrained(str(args.model),torch_dtype=torch.float16,device_map={'':'cuda:0'},local_files_only=True,trust_remote_code=False,use_safetensors=True,attn_implementation='sdpa').eval();model.config.use_cache=False
 assert {p.dtype for p in model.parameters()}=={torch.float16} and {str(p.device) for p in model.parameters()}=={'cuda:0'}
 report.update(model_loaded=True,model_parameter_count=sum(p.numel() for p in model.parameters()),load_seconds=round(time.monotonic()-began,3),GPU_name=torch.cuda.get_device_name(0));save()
 def forward(row,role,a=None,b=None,standard=False):
  a=row['prompt_tokens'] if a is None else a;b=len(row['input_ids']) if b is None else b;assert 1<=a<b<=len(row['input_ids']);n=b-a;seq=report['logical_forward_reserved']+1
  assert seq<=spec['forward_cap_per_variant'];event={'event':'forward_reserved','sequence':seq,'role':role,'id_sha256':row['id_sha256'],'label_start':a,'label_end':b,'supervised_labels':n,'input_tokens':len(row['input_ids']),'started_unix':time.time()};append(journal,event);report['logical_forward_reserved']=seq;status('forward',sequence=seq,role=role)
  t=time.monotonic();ids=torch.tensor([row['input_ids']],dtype=torch.long,device='cuda:0');mask=torch.ones_like(ids)
  if standard:
   labels=torch.full_like(ids,-100);labels[:,a:b]=ids[:,a:b]
   loss=model(input_ids=ids,attention_mask=mask,labels=labels,use_cache=False).loss*n
  else:
   positions=torch.arange(a-1,b-1,dtype=torch.long,device='cuda:0')
   logits=model(input_ids=ids,attention_mask=mask,logits_to_keep=positions,use_cache=False).logits
   assert logits.shape==(1,n,model.config.vocab_size)
   loss=F.cross_entropy(logits[0].float(),ids[0,a:b],reduction='sum')
  assert bool(torch.isfinite(loss));torch.cuda.synchronize();value=float(loss.detach());report['logical_forward_completed']+=1;report['role_counts'][role]=report['role_counts'].get(role,0)+1
  append(journal,{'event':'forward_completed','sequence':seq,'role':role,'id_sha256':row['id_sha256'],'loss_sum':value,'supervised_labels':n,'wall_seconds':round(time.monotonic()-t,4)});status('forward_returned',sequence=seq)
  if report['logical_forward_completed']%20==0:save()
  return loss,value
 def evaluation(data,phase):
  model.eval();total=tokens=0;out=[]
  with torch.no_grad():
   for row in data:
    _,value=forward(row,phase);n=row['target_tokens'];total+=value;tokens+=n;out.append({'id_sha256':row['id_sha256'],'component_sha256':row['component_sha256'],'target_tokens':n,'loss_sum':value,'mean_NLL':value/n})
  write(args.output/(phase+'.json'),{'cases':out,'count':len(out),'target_tokens':tokens,'loss_sum':total,'token_weighted_NLL':total/tokens,'perplexity':math.exp(total/tokens)});return {'count':len(out),'target_tokens':tokens,'loss_sum':total,'token_weighted_NLL':total/tokens,'perplexity':math.exp(total/tokens)}
 try:
  canary=dev[0]
  with torch.no_grad():
   _,ordinary=forward(canary,'canary_standard',standard=True);_,sparse=forward(canary,'canary_sparse')
  assert close(ordinary/canary['target_tokens'],sparse/canary['target_tokens']);report['sparse_vs_standard_loss']={'standard_sum':ordinary,'selected_positions_sum':sparse,'target_tokens':canary['target_tokens'],'passed':True};save()
  set_seed(42);config=LoraConfig(r=8,lora_alpha=16,lora_dropout=0.0,target_modules=['q_proj','v_proj'],bias='none',task_type='CAUSAL_LM',init_lora_weights=True);model=get_peft_model(model,config);model.eval()
  trainable=[(n,p) for n,p in model.named_parameters() if p.requires_grad];frozen=[(n,p) for n,p in model.named_parameters() if not p.requires_grad]
  assert trainable and all('lora_' in n and p.dtype==torch.float32 for n,p in trainable);assert sum(p.numel() for n,p in frozen)==3085938688
  assert all(int(torch.count_nonzero(p))==0 for n,p in trainable if '.lora_B.' in n)
  initial_adapter=tensor_hash(trainable);initial_frozen=tensor_hash(frozen)
  with torch.no_grad():_,noop=forward(canary,'canary_zero_adapter')
  assert close(noop/canary['target_tokens'],sparse/canary['target_tokens'])
  report.update(status='evaluating_before',initial_adapter_sha256=initial_adapter,initial_frozen_parameters_sha256=initial_frozen,trainable_parameter_count=sum(p.numel() for n,p in trainable),frozen_parameter_count=sum(p.numel() for n,p in frozen),trainable_dtypes=sorted({str(p.dtype) for n,p in trainable}),zero_adapter_forward_equal=True);save()
  report['before_dev']=evaluation(dev,'before_dev');report['before_val']=evaluation(val,'before_val');save()
  model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False});model.enable_input_require_grads();model.train()
  assert float(model.config.attention_dropout)==0.0
  optimizer=torch.optim.AdamW([p for n,p in trainable],lr=2e-4,betas=(0.9,0.999),eps=1e-8,weight_decay=0.0,foreach=False)
  scaler=torch.amp.GradScaler('cuda',init_scale=1024.0,growth_interval=2000);report['status']='training';report['training_run']=True;save();status('training')
  def checkpoint(step):
   status('checkpoint',optimizer_updates=step);tmp=args.output/('.step-%03d.tmp'%step);tmp.mkdir();model.save_pretrained(tmp/'adapter',safe_serialization=True,save_embedding_layers=False)
   tensors={};non_tensor={}
   for i,(n,p) in enumerate(trainable):
    assert p in optimizer.state
    for k,v in optimizer.state[p].items():
     if torch.is_tensor(v):tensors['p%04d.%s'%(i,k)]=v.detach().cpu().contiguous()
     else:non_tensor['p%04d.%s'%(i,k)]=v
   tensors['rng.cpu']=torch.get_rng_state();tensors['rng.cuda0']=torch.cuda.get_rng_state(0).cpu();save_file(tensors,str(tmp/'optimizer-and-rng.safetensors'))
   write(tmp/'training-state.json',{'completed_optimizer_updates':step,'training_labels':report['completed_training_labels'],'data_sha256':spec['data_sha256'],'spec_sha256':sha(args.spec),'adapter_sha256':tensor_hash(trainable),'scaler_state':scaler.state_dict(),'optimizer_groups':optimizer.state_dict()['param_groups'],'optimizer_non_tensor_state':non_tensor,'parameter_order':[n for n,p in trainable],'resume_implemented':False})
   manifest={str(p.relative_to(tmp)):sha(p) for p in sorted(tmp.rglob('*')) if p.is_file()};write(tmp/'manifest.json',manifest);final=args.output/('step-%03d'%step);os.replace(tmp,final);append(journal,{'event':'checkpoint_committed','completed_optimizer_updates':step,'manifest_sha256':sha(final/'manifest.json')});return final
  previous_adapter=initial_adapter;last=None
  for step in schedule['steps']:
   number=step['optimizer_step']+1;assert number==report['completed_optimizer_updates']+1;append(journal,{'event':'optimizer_update_reserved','update':number,'labels':2048});optimizer.zero_grad(set_to_none=True);actual=0;step_loss=0;t=time.monotonic()
   for position,segment in enumerate(step['segments']):
    row=index[segment['id_sha256']];a,b=segment['label_start'],segment['label_end'];assert a==row['prompt_tokens']+segment['target_start'] and b==row['prompt_tokens']+segment['target_end'];assert b-a==segment['supervised_tokens'];assert len(row['input_ids'])<=4096
    loss,value=forward(row,'training',a,b);status('backward',update=number,segment=position,forward_sequence=report['logical_forward_reserved']);scaler.scale(loss/2048).backward();torch.cuda.synchronize();n=b-a;actual+=n;step_loss+=value;report['training_segments_backward_completed']+=1;report['training_input_token_exposures']+=len(row['input_ids']);append(journal,{'event':'backward_completed','update':number,'segment':position,'forward_sequence':report['logical_forward_reserved'],'supervised_labels':n});del loss
   assert actual==2048;assert all(p.grad is None for n,p in frozen);assert all(p.grad is not None and bool(torch.isfinite(p.grad).all()) for n,p in trainable)
   scaler.unscale_(optimizer);norm=torch.nn.utils.clip_grad_norm_([p for n,p in trainable],1.0,error_if_nonfinite=True);assert float(norm)>0;old_scale=scaler.get_scale();status('optimizer_step',update=number);scaler.step(optimizer);scaler.update();torch.cuda.synchronize();assert scaler.get_scale()>=old_scale,'Overflow skipped optimizer update; no retry'
   assert all(int(optimizer.state[p]['step'])==number for n,p in trainable)
   new=tensor_hash(trainable);assert new!=previous_adapter;previous_adapter=new;report['completed_optimizer_updates']=number;report['completed_training_labels']+=actual
   event={'event':'optimizer_update_completed','update':number,'supervised_labels':actual,'mean_training_NLL':step_loss/actual,'gradient_norm_before_clip':float(norm),'loss_scale':scaler.get_scale(),'adapter_sha256':new,'wall_seconds':round(time.monotonic()-t,3)};append(journal,event);save();print(json.dumps(event),flush=True)
   if number%8==0:last=checkpoint(number)
  assert report['completed_optimizer_updates']==32 and report['completed_training_labels']==65536
  assert report['training_segments_backward_completed']==schedule['sequence_forwards'] and report['training_input_token_exposures']==schedule['input_token_exposures']
  model.gradient_checkpointing_disable();model.eval();report['status']='evaluating_after';save();report['after_dev']=evaluation(dev,'after_dev');report['after_val']=evaluation(val,'after_val')
  assert tensor_hash(frozen)==initial_frozen;report['frozen_parameters_unchanged']=True
  with model.disable_adapter(),torch.no_grad():_,disabled=forward(canary,'canary_disable_after_training')
  assert close(disabled/canary['target_tokens'],sparse/canary['target_tokens']);report['disabled_adapter_matches_base']=True
  final_adapter=tensor_hash(trainable);model=model.unload();model=PeftModel.from_pretrained(model,str(last/'adapter'),is_trainable=False).eval();loaded=[(n,p) for n,p in model.named_parameters() if 'lora_' in n];assert tensor_hash(loaded)==final_adapter
  with torch.no_grad():_,reloaded=forward(canary,'canary_reloaded_checkpoint')
  expected=json.loads((args.output/'after_dev.json').read_text())['cases'][0]['loss_sum'];assert close(reloaded/canary['target_tokens'],expected/canary['target_tokens'])
  expected_calls=schedule['sequence_forwards']+2*(197+79)+5;assert report['logical_forward_reserved']==report['logical_forward_completed']==expected_calls
  report.update(status='completed',adapter_reload_verified=True,final_adapter_sha256=final_adapter,checkpoint_directory=last.name,logical_forward_unknown=0,wall_seconds=round(time.monotonic()-began,3),limitations=['Fixed32-update SFT pilot, not GRPO or original ToolRL-DR reproduction.','Teacher-forced held-out NLL is not generated tool-call accuracy or actual tool execution.','Equal supervised labels and update counts do not equalize prompt exposures, coverage or FLOPs.','Text-grouped development uses released training sources; semantic/pretraining isolation unknown.','Only LoRA and optimizer/RNG states saved privately; no base weights or checkpoints published.'])
  status('completed');save();return 0
 except BaseException as e:
  report.update(status='failed',error={'type':type(e).__name__,'message':str(e)},logical_forward_unknown=report['logical_forward_reserved']-report['logical_forward_completed'],wall_seconds=round(time.monotonic()-began,3));save();raise


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--spec',type=Path,required=True);p.add_argument('--variant',choices=['train','mixed_train'],required=True);a=p.parse_args()
 try:raise SystemExit(train(a))
 except BaseException as e:
  path=a.output/'report.json'
  if path.exists() and not isinstance(e,SystemExit):
   report=json.loads(path.read_text());report.update(status='failed',error={'type':type(e).__name__,'message':str(e)});write(path,report)
  raise
