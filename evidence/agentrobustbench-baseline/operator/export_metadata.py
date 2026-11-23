"""Export allowlisted metadata only; do not invoke a model or rescore answers."""
from pathlib import Path
from collections import defaultdict
import hashlib,json,os,resource,statistics,tarfile
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2]);os.nice(19)
resource.setrlimit(resource.RLIMIT_AS,(2*2**30,2*2**30));resource.setrlimit(resource.RLIMIT_CPU,(90,90))
BASE=Path('/authorized/agent-lab');OUT=BASE/'outputs/neural-clean-stage49-v1-20261123'
BOOTOUT=BASE/'outputs/neural-bootstrap-stage49-v1-20261123';RUNOUT=BASE/'outputs/neural-runtime-stage49-v2-20261123';INGEST=BASE/'outputs/neural-model-ingest-stage49-v2-20261123'
BOOT=Path(json.loads((BOOTOUT/'control-location.json').read_text())['local_root']);WORK=Path(json.loads((OUT/'control-location.json').read_text())['local_root']);DEST=WORK/'public-export';DEST.mkdir(exist_ok=False)
sha=lambda b:hashlib.sha256(b).hexdigest()
report=json.loads((OUT/'run-report.json').read_text());assert report['terminal'] and not report['shutdown']['remaining_owned_processes']
model=json.loads((WORK/'run/report.json').read_text());admission=json.loads((WORK/'admission.json').read_text());spec=json.loads((OUT/'protocol.json').read_text())
assert sha((OUT/'run.py').read_bytes())==spec['operator_sha256'] and sha((OUT/'driver.py').read_bytes())==spec['driver_sha256']
assert sha((OUT/'exec_child.py').read_bytes())==spec['wrapper_sha256']
rows=[json.loads(x) for x in (WORK/'run/predictions.jsonl').read_text().splitlines()]
events=[json.loads(x) for x in (WORK/'run/calls.jsonl').read_text().splitlines()]
reserved={x['sequence']:x for x in events if x['event']=='reserved'};complete={x['sequence']:x for x in events if x['event']=='completed'}
assert len(reserved)==sum(x['event']=='reserved' for x in events) and len(complete)==sum(x['event']=='completed' for x in events)
metrics=[];aggregate=defaultdict(lambda:{'n':0,'correct':0,'score_sum':0.0});input_tokens=generated_tokens=0
for i,row in enumerate(rows):
 if not row.get('scored',True):continue
 seq=i+1;a=admission['cases'][i];c=complete[seq];r=reserved[seq];m=row['generation_metadata']
 assert row['id']==a['id']==c['case']==r['case']==m['case'] and row['sample_sha256']==a['sample_sha256']
 assert len(r['prompt_token_ids'])==m['input_tokens']==a['input_tokens']
 assert c['input_tokens']==m['input_tokens'] and m['sequence']==seq
 encode=lambda x:json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
 assert sha(encode(r['messages']))==a['messages_sha256'] and sha(encode(r['prompt_token_ids']))==a['prompt_token_ids_sha256']
 assert c['raw_output']==row['prediction']['raw_output']
 for key in m:assert m[key]==c[key],key
 input_tokens+=m['input_tokens'];generated_tokens+=len(c['generated_token_ids'])
 s=row['official_score']
 for name in ['overall',row['benchmark']]:
  aggregate[name]['n']+=1;aggregate[name]['correct']+=bool(s['correct']);aggregate[name]['score_sum']+=s['score']
 metrics.append({'case_index':seq,'id_sha256':sha(row['id'].encode()),'benchmark':row['benchmark'],'category':row.get('category'),'sample_sha256':row['sample_sha256'],
  'official_score':s,'required_key_screen':row['required_key_screen'],'parsed_tool_call_count':len(row['prediction']['tool_calls']),
  'prediction_error':row['prediction']['error'],'prediction_sha256':sha(encode(row['prediction'])),
  'raw_output_sha256':sha(c['raw_output'].encode()),'generated_token_ids_sha256':sha(encode(c['generated_token_ids'])),
  'generated_token_count':len(c['generated_token_ids']),'generation_metadata':{k:v for k,v in m.items() if k!='case'}})
assert len(metrics)==model['completed_cases']
assert input_tokens==model['input_tokens'] and generated_tokens==model['generated_token_ids']
if report.get('all_cases_completed'):
 assert len(metrics)==len(reserved)==len(complete)==199 and dict(aggregate)==model['scores']
 assert report['all_cases_completed'] and model['status']=='completed' and report['own_GPU_context_absent']
missing=[m for m in metrics if m['required_key_screen']['calls_missing_declared_required_keys']]
latencies=[m['generation_metadata']['generation_seconds'] for m in metrics];times=sorted(latencies)
summary={'derived_from_existing_recorded_results_only':True,'no_new_model_calls_or_rescoring':True,'terminal_all_cases_completed':report.get('all_cases_completed',False),
 'declared_cases':199,'scored_cases':len(metrics),'scores':dict(aggregate),'local_generation_ledger':{'reserved':len(reserved),'completed':len(complete),'unknown_still_charged':len(reserved)-len(complete)},
 'input_tokens':input_tokens,'generated_token_ids':generated_tokens,'cases_without_parsed_tool_calls':sum(m['parsed_tool_call_count']==0 for m in metrics),
 'required_key_violation_cases':len(missing),'official_correct_with_required_key_violation':sum(bool(m['official_score']['correct']) for m in missing),
 'truncated_or_soft_time_stopped':sum(not m['generation_metadata']['ended_with_eos'] for m in metrics),
 'observed_generation_seconds':{'total':round(sum(latencies),4),'median':statistics.median(latencies) if latencies else None,'p95_nearest_rank':times[__import__('math').ceil(.95*len(times))-1] if times else None,'max':max(times) if times else None},
 'raw_private_artifacts_sha256':{n:sha((WORK/'run'/n).read_bytes()) for n in ['calls.jsonl','predictions.jsonl','report.json']},
 'limitations':model.get('limitations',[])}
(DEST/'results').mkdir();(DEST/'results/summary.json').write_text(json.dumps(summary,indent=2)+'\n');(DEST/'results/case-metrics.jsonl').write_text(''.join(json.dumps(m,ensure_ascii=False)+'\n' for m in metrics))
files=[]
def add(source,name,normalize=False):
 data=source.read_bytes();original=sha(data)
 if normalize:
  text=data.decode()
  for old,new in [(str(BASE),'/authorized/agent-lab'),(str(BOOT),'/isolated/bootstrap'),(str(WORK),'/isolated/neural-run')]:text=text.replace(old,new)
  data=text.encode()
 target=DEST/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
 files.append({'path':name,'original_sha256':original,'public_sha256':sha(data),'public_bytes':len(data),'paths_normalized':normalize})
for p in sorted(OUT.iterdir()):
 if p.is_file() and p.name not in ['control-location.json','export_metadata.py']:add(p,'operator/'+p.name,normalize=p.suffix in ['.py','.log'])
original_admission=(WORK/'admission.json').read_bytes()
public_admission=json.loads(original_admission)
for index,case in enumerate(public_admission['cases'],1):
 case['case_index']=index;case['id_sha256']=sha(case.pop('id').encode())
public_admission['case_ID_policy']='Original IDs may embed full question text; exported as ordinal and SHA256 of original UTF-8 ID.'
data=(json.dumps(public_admission,indent=2)+'\n').encode();(DEST/'results/admission.json').write_bytes(data)
files.append({'path':'results/admission.json','original_sha256':sha(original_admission),'public_sha256':sha(data),'public_bytes':len(data),'derived_metadata':True,'original_IDs_hashed':True})
add(WORK/'run/report.json','results/model-report.json')
for folder,prefix in [(BOOTOUT,'bootstrap'),(RUNOUT,'runtime'),(INGEST,'model-ingest')]:
 for name in ['run.py','protocol.json','run-report.json']+(['download-model.log'] if prefix=='bootstrap' else []):
  if (folder/name).exists():add(folder/name,prefix+'/'+name,normalize=name in ['run.py','download-model.log'])
for name in ['CPU-runtime-identity.log','runtime-integrity.log','freeze-resolved-lock.log','identity.py','install-frozen-runtime.log']:
 if (RUNOUT/name).exists():add(RUNOUT/name,'runtime/'+name,normalize=name.endswith('.py') or name=='install-frozen-runtime.log')
for name in ['model-manifest.json','requirements.lock','resolved-lock.json']:
 if (BOOT/name).exists():add(BOOT/name,'runtime/'+name)
add(Path(__file__),'operator/export_metadata.py',normalize=True)
for name in ['results/summary.json','results/case-metrics.jsonl']:
 p=DEST/name;files.append({'path':name,'original_sha256':None,'public_sha256':sha(p.read_bytes()),'public_bytes':p.stat().st_size,'derived_metadata':True})
(DEST/'artifacts.json').write_text(json.dumps({'normalization':'Operator source/log paths normalized only where marked; original/public SHA separately bound. Frozen protocols, manifests and result reports retain original bytes. Full prompts, raw generated answers, generated IDs, model weights, environment directories, signed transport URLs and server credentials stay private. Original case IDs are SHA256/ordinal because some IDs embed questions. Case metrics derived without new model calls or rerunning graders.','files':files},indent=2)+'\n')
archive=WORK/'public-export.tar.gz'
with tarfile.open(archive,'w:gz') as t:
 for p in sorted(DEST.rglob('*')):
  if p.is_file():t.add(p,arcname=p.relative_to(DEST))
print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive.read_bytes()),'files':len(files)+1,'summary':summary}))
