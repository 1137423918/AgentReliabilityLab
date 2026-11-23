from pathlib import Path
import hashlib,json,os,resource,tarfile
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2]);os.nice(19);resource.setrlimit(resource.RLIMIT_AS,(2*2**30,2*2**30));resource.setrlimit(resource.RLIMIT_CPU,(90,90))
BASE=Path('/authorized/agent-lab');V1=BASE/'outputs/training-design-stage50-v1-20261123';V2=Path(__file__).resolve().parent;sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();report=json.loads((V2/'run-report.json').read_text());assert report['terminal'] and report['prepared_successfully'] and not report['shutdown']['remaining_owned_processes']
WORK=Path(json.loads((V2/'control-location.json').read_text())['local_root']);OLDWORK=Path(json.loads((V1/'control-location.json').read_text())['local_root']);DATA=WORK/'prepared';RESULT=json.loads((DATA/'report.json').read_text());DEST=WORK/'public-export';DEST.mkdir(exist_ok=False)
for r in RESULT['private_artifacts']:
 p=DATA/r['file'];assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256']
metadata=[json.loads(x) for x in (DATA/'row-metadata.jsonl').read_text().splitlines()];index={(r['variant'],r['id_sha256']):r for r in metadata};assert len(index)==len(metadata)==7889
selected=[];ids={};components={};private={}
for name in ['train','mixed_train','dev_clean','test']:
 variant='mixed_train' if name=='dev_clean' else name;ids[name]=[];components[name]=set();private[name]={}
 with (DATA/(name+'-tokenized.jsonl')).open() as f:
  for i,line in enumerate(f):
   row=json.loads(line);k=row['id_sha256'];m=index[variant,k];assert len(row['input_ids'])==m['sequence_tokens']
   assert row['labels'][:m['prompt_tokens']]==[-100]*m['prompt_tokens'] and row['labels'][m['prompt_tokens']:]==row['input_ids'][m['prompt_tokens']:]
   assert sum(x!=-100 for x in row['labels'][1:])==m['target_tokens']
   assert hashlib.sha256(json.dumps(row['input_ids'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()==m['full_token_ids_sha256']
   if name=='dev_clean':assert m['perturbation_type']=='none'
   selected.append({'dataset':name,'output_position':i,'source_variant':variant,'source_input_position':m['input_position'],'id_sha256':k,'full_row_sha256':m['full_row_sha256'],'component_sha256':m['component_sha256']})
   ids[name].append(k);components[name].add(m['component_sha256']);private[name][k]=row
assert ids['train']==ids['mixed_train'] and len(ids['train'])==3700 and len(ids['dev_clean'])==197 and len(ids['test'])==79
assert not components['train']&(components['dev_clean']|components['test'])
checks={};orders={}
for variant in ['train','mixed_train']:
 schedule=json.loads((DATA/(variant+'-schedule.json')).read_text());positions={};total=forwards=inputs=0;orders[variant]=[]
 for step in schedule['steps']:
  actual=0
  for s in step['segments']:
   r=private[variant][s['id_sha256']];p=r['prompt_tokens'];a,b=s['label_start'],s['label_end'];key=(s['cycle'],s['id_sha256'])
   assert s['target_start']==positions.get(key,0) and s['target_end']<=r['target_tokens'];positions[key]=s['target_end']
   assert a==p+s['target_start'] and b==p+s['target_end'] and a>=1
   masked=[-100]*a+r['labels'][a:b]+[-100]*(len(r['labels'])-b)
   n=sum(x!=-100 for x in masked[1:]);assert n==s['supervised_tokens']==b-a
   actual+=n;forwards+=1;inputs+=len(r['input_ids'])
   if not orders[variant] or orders[variant][-1]!=s['id_sha256']:orders[variant].append(s['id_sha256'])
  assert actual==step['loss_tokens']==2048;total+=actual
 assert total==65536 and len(schedule['steps'])==32 and forwards==schedule['sequence_forwards'] and inputs==schedule['input_token_exposures']
 checks[variant]={'actual_shifted_supervised_labels_in_plan':total,'optimizer_updates_planned':32,'segments_checked':forwards,'input_token_exposures':inputs,'all_label_spans_contiguous_per_ID_cycle':True,'optimizer_or_model_executed':False}
n=min(map(len,orders.values()));assert orders['train'][:n]==orders['mixed_train'][:n]
(DEST/'results').mkdir();(DEST/'results/selected-rows.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in selected));(DEST/'results/consumption-check.json').write_text(json.dumps({'variants':checks,'paired_training_ID_order_identical':True,'same_seed_schedule_ID_prefix_length':n,'train_dev_validation_component_overlap':0,'public_selected_rows':len(selected),'private_artifact_hashes_verified':len(RESULT['private_artifacts']),'training_run':False},indent=2)+'\n')
files=[]
def add(p,name,normalize=False):
 original=sha(p);b=p.read_bytes()
 if normalize:
  t=b.decode()
  for old,new in [(str(BASE),'/authorized/agent-lab'),(str(WORK),'/isolated/study-v2'),(str(OLDWORK),'/isolated/study-v1'),('/isolated/tokenizer-runtime','/isolated/tokenizer-runtime')]:t=t.replace(old,new)
  b=t.encode()
 q=DEST/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(b);files.append({'path':name,'original_sha256':original,'public_sha256':hashlib.sha256(b).hexdigest(),'public_bytes':len(b),'paths_normalized':normalize})
for folder,prefix in [(V1,'failed-v1'),(V2,'candidate-v2')]:
 for name in ['run.py','prepare.py','exec_child.py','protocol.json','run-report.json','prepare.log','monitor.jsonl']:
  add(folder/name,prefix+'/'+name,normalize=name.endswith('.py') or name.endswith('.log'))
add(V1/'transfer.py','transfer/run.py',True);add(V1/'transfer-report.json','transfer/report.json')
for name in ['report.json','row-metadata.jsonl','near-edges.jsonl','train-schedule.json','mixed_train-schedule.json']:add(DATA/name,'results/'+name)
add(Path(__file__),'operator/export_metadata.py',True)
for name in ['results/selected-rows.jsonl','results/consumption-check.json']:
 p=DEST/name;files.append({'path':name,'original_sha256':None,'public_sha256':sha(p),'public_bytes':p.stat().st_size,'derived_metadata':True})
(DEST/'artifacts.json').write_text(json.dumps({'normalization':'Only marked operator source/log paths normalized. Original/public SHA separately bound. Reports/protocols/row-metadata/schedules retain original bytes. Selection and consumption checks are derived from private tokenized files, with no model/loss/optimizer execution. No raw IDs, full prompts, targets, token vectors, Parquets, weights, credentials or environments exported. Failed-v1 remains unchanged.','files':files},indent=2)+'\n')
archive=WORK/'public-export.tar.gz'
with tarfile.open(archive,'w:gz') as t:
 for p in sorted(DEST.rglob('*')):
  if p.is_file():t.add(p,arcname=p.relative_to(DEST))
print(json.dumps({'archive':str(archive),'bytes':archive.stat().st_size,'sha256':sha(archive),'manifest_files':len(files),'consumption_checks':checks,'report':RESULT}))
