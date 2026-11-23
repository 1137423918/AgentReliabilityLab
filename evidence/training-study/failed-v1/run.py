from pathlib import Path
import hashlib,importlib.metadata,json,os,resource,signal,subprocess,tempfile,time
OUT=Path(__file__).resolve().parent;BASE=Path('/authorized/agent-lab');CORE=BASE/'envs/model-request-budget-20261121/bin/python';spec=json.loads((OUT/'protocol.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (OUT/'run-report.json').exists();assert sha(Path(__file__))==spec['operator_sha256'];assert sha(OUT/'prepare.py')==spec['source_sha256'];assert sha(OUT/'exec_child.py')==spec['wrapper_sha256'];assert json.loads((OUT/'transfer-report.json').read_text())['terminal']
BOOT=Path('/isolated/tokenizer-runtime');PY=BOOT/'runtime/bin/python';INGEST=BASE/'outputs/neural-model-ingest-stage49-v2-20261123';MODEL=Path(json.loads((INGEST/'control-location.json').read_text())['model_root']);assert json.loads((INGEST/'run-report.json').read_text())['all_artifacts_verified'];MANIFEST=json.loads((BOOT/'model-manifest.json').read_text());assert sha(BOOT/'model-manifest.json')==spec['model_manifest_sha256']
def tokenizer_identity():
 rows=[]
 for x in MANIFEST['files']:
  if x['path'].endswith('.safetensors'):continue
  p=MODEL/x['path'];b=p.read_bytes();assert len(b)==x['bytes'];digest=hashlib.sha1(('blob '+str(len(b))+'\0').encode()+b).hexdigest() if not x['lfs_sha256'] else hashlib.sha256(b).hexdigest();assert digest==(x['lfs_sha256'] or x['git_blob_sha1']);rows.append({'file':x['path'],'sha256':sha(p)})
 return rows
identity=tokenizer_identity()
def memory():return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
assert memory()>=16*2**30
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:4]);os.nice(19);resource.setrlimit(resource.RLIMIT_AS,(32*2**30,32*2**30));WORK=Path(tempfile.mkdtemp(prefix='agentlab-training-design-stage50-'));WORK.chmod(0o700);mounts=[(x.split(' - ')[0].split()[4],x.split(' - ')[1].split()[0]) for x in Path('/proc/self/mountinfo').read_text().splitlines()];fs=max([(len(p),f) for p,f in mounts if str(WORK).startswith(p.rstrip('/')+'/')])[1];assert fs in ['ext4','xfs','btrfs'];(OUT/'control-location.json').write_text(json.dumps({'local_root':str(WORK)})+'\n');(OUT/'control-location.json').chmod(0o600)
import shutil
(WORK/'inputs').mkdir()
for n,d in spec['paired_input_sha256'].items():
 assert sha(OUT/'inputs'/n)==d;shutil.copyfile(OUT/'inputs'/n,WORK/'inputs'/n);assert sha(WORK/'inputs'/n)==d
BENCH=BOOT/'upstream/hf_data/datasets/api_eval/clean.jsonl';assert sha(BENCH)==spec['benchmark_sha256'];shutil.copyfile(BENCH,WORK/'clean.jsonl');shutil.copyfile(OUT/'prepare.py',WORK/'prepare.py')
versions=lambda:sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions());before=versions();parent_start=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]);env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','OPENAI_API_KEY','HF_TOKEN','HUGGING_FACE_HUB_TOKEN','AGENT_LAB_EVIDENCE_KEY']};env.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TMPDIR=str(WORK),HF_HOME=str(WORK/'hf-cache'),XDG_CACHE_HOME=str(WORK/'xdg-cache'))
report={'terminal':False,'protocol_sha256':sha(OUT/'protocol.json'),'source_sha256':spec['source_sha256'],'operator_sha256':sha(Path(__file__)),'tokenizer_identity':identity,'model_inference':False,'training_run':False,'GPU_work_started':False,'filesystem':fs};started=time.monotonic();driver=None;known={};peak=0;guard=None

def save():(OUT/'run-report.json').write_text(json.dumps(report,indent=2)+'\n')
def tree():
 rows={}
 for p in Path('/proc').glob('[0-9]*'):
  try:
   if p.stat().st_uid!=os.getuid():continue
   s=(p/'stat').read_text().rsplit(')',1)[1].split();rows[int(p.name)]={'ppid':int(s[1]),'start':int(s[19]),'state':s[0],'rss':next((int(x.split()[1])*1024 for x in (p/'status').read_text().splitlines() if x.startswith('VmRSS:')),0)}
  except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 ids={driver.pid} if driver is not None and driver.pid in rows and driver.poll() is None else set();ids.update(p for p,start in known.items() if p in rows and rows[p]['start']==start)
 for _ in range(32):
  old=len(ids);ids.update(p for p,r in rows.items() if r['ppid'] in ids)
  if len(ids)==old:break
 ids={p for p in ids if rows[p]['state']!='Z'};known.update({p:rows[p]['start'] for p in ids});return {p:rows[p] for p in ids}
def stop():
 forced=False
 for sig,cap in [(signal.SIGTERM,10),(signal.SIGKILL,3)]:
  owned=tree()
  if not owned:break
  forced|=sig==signal.SIGKILL
  for p,r in owned.items():
   if tree().get(p,{}).get('start')==r['start']:
    try:os.kill(p,sig)
    except ProcessLookupError:pass
  end=time.monotonic()+cap
  while time.monotonic()<end and tree():time.sleep(.2)
 if driver is not None:
  try:driver.wait(timeout=3)
  except subprocess.TimeoutExpired:pass
 return {'forced_cleanup':forced,'remaining_owned_processes':list(tree())}
save()
try:
 with (OUT/'prepare.log').open('wb') as log,(OUT/'monitor.jsonl').open('w') as mon:
  driver=subprocess.Popen([str(CORE),str(OUT/'exec_child.py'),str(os.getpid()),str(parent_start),'cpu',str(PY),str(WORK/'prepare.py'),'--source',str(WORK/'inputs'),'--model',str(MODEL),'--benchmark',str(WORK/'clean.jsonl'),'--output',str(WORK/'prepared')],cwd=WORK,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  report['CPU_child_started']=True;save();print(json.dumps({'CPU_preparation_started':True,'declared_rows':7889,'GPU_or_training':False}),flush=True)
  while driver.poll() is None:
   elapsed=time.monotonic()-started;rss=sum(x['rss'] for x in tree().values());peak=max(peak,rss);mem=memory();mon.write(json.dumps({'elapsed_seconds':round(elapsed,3),'owned_RSS_bytes':rss,'available_memory_bytes':mem})+'\n');mon.flush()
   if elapsed>1200:guard='phase_wall'
   elif rss>8*2**30:guard='owned_RSS'
   elif mem<12*2**30:guard='memory_floor'
   if guard:stop();break
   time.sleep(.5)
  rc=driver.wait();report.update(returncode=rc,guard_reason=guard)
  if rc or guard:raise RuntimeError('Preparation phase failed')
  result=json.loads((WORK/'prepared/report.json').read_text());assert result['tokenized_rows']==7889 and result['selected_training_pairs']>0 and result['clean_development_rows']>0
  assert all(x['loss_tokens_total']==65536 and x['updates']==32 for x in result['planned_exposure'].values());report['prepared_successfully']=True;report['preparation_summary']={k:result[k] for k in ['tokenized_rows','selected_training_pairs','clean_development_rows','released_validation_rows','overlength_pairs','text_grouping','training_variant_tokens','planned_exposure']}
except BaseException as e:report['operator_error']={'type':type(e).__name__,'message':str(e)}
finally:
 report['shutdown']=stop();report.update(terminal=True,peak_sampled_RSS_bytes=peak,wall_seconds=round(time.monotonic()-started,3),source_and_inputs_unchanged=sha(OUT/'prepare.py')==spec['source_sha256'] and sha(WORK/'prepare.py')==spec['source_sha256'] and sha(BENCH)==spec['benchmark_sha256'] and all(sha(WORK/'inputs'/n)==d and sha(OUT/'inputs'/n)==d for n,d in spec['paired_input_sha256'].items()),core_distribution_pairs_unchanged=before==versions(),tokenizer_identity_unchanged=identity==tokenizer_identity());save();print(json.dumps(report),flush=True)
raise SystemExit(0 if report.get('prepared_successfully') and not report.get('operator_error') and report['source_and_inputs_unchanged'] and report['core_distribution_pairs_unchanged'] and report['tokenizer_identity_unchanged'] and not report['shutdown']['remaining_owned_processes'] else 2)
