"""Verify saved Full32 read-only, then run the first Mixed32; no Full retry."""
from pathlib import Path
import fcntl,hashlib,json,os,resource,signal,subprocess,tempfile,time

OUT=Path(__file__).resolve().parent
BASE=Path('/path/to/private-agent-lab')
CORE=BASE/'envs/model-request-budget-20261121/bin/python'
SETUP=BASE/'outputs/lora-training-stage51-20261123'
OLD=BASE/'outputs/lora-training-stage51-admit-v2-20261123'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
spec=json.loads((OUT/'followup-protocol.json').read_text())
assert not (OUT/'followup-report.json').exists()
for n,key in [('followup_controller.py','operator_sha256'),('train_driver.py','driver_sha256'),('audit_full_checkpoint.py','full_audit_driver_sha256'),('nvml_watch.py','watcher_sha256'),('exec_child.py','wrapper_sha256')]:
 assert sha(OUT/n)==spec[key],n
assert resource.getrlimit(resource.RLIMIT_AS)==(-1,-1)
assert sha(OLD/'train-protocol.json')==spec['original_full_protocol_sha256']
oldparent=json.loads((OLD/'training-report.json').read_text())
assert oldparent['terminal'] and oldparent['status']=='failed'
ready=json.loads((SETUP/'setup-report.json').read_text())
assert ready['terminal'] and ready['runtime_ready'] and not ready.get('operator_error') and ready['setup_protocol_sha256']==spec['setup_protocol_sha256']
ROOT=Path(json.loads((SETUP/'runtime-location.json').read_text())['local_root'])
PY=ROOT/'runtime/bin/python';DATA=ROOT/'data';MODEL=ROOT/'model'
ORIGINAL=Path(json.loads((OLD/'training-location.json').read_text())['local_root'])/'train'
SDK=Path(json.loads((BASE/'outputs/lora-nvml-stage51-20261123/monitor-location.json').read_text())['local_root'])/'sdk'
assert sha(SDK/'pynvml.py')==spec['pynvml_sha256']

def streamsha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(2*1024*1024):h.update(b)
 return h.hexdigest()

for n,d in spec['data_sha256'].items():assert streamsha(DATA/n)==d,n
manifest=json.loads((SETUP/'model-manifest.json').read_text())
assert sha(SETUP/'model-manifest.json')==spec['model_manifest_sha256']
for x in manifest['files']:
 p=MODEL/x['path'];h=hashlib.sha256() if x['lfs_sha256'] else hashlib.sha1()
 assert p.stat().st_size==x['bytes']
 if not x['lfs_sha256']:h.update(('blob '+str(x['bytes'])+'\0').encode())
 with p.open('rb') as f:
  while b:=f.read(2*1024*1024):h.update(b)
 assert h.hexdigest()==(x['lfs_sha256'] or x['git_blob_sha1'])
original_files={str(p.relative_to(ORIGINAL)):streamsha(p) for p in sorted(ORIGINAL.rglob('*')) if p.is_file()}
old_controller_hash=sha(OLD/'training-report.json')

def memory():return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024

assert memory()>=32*2**30
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:4]);os.nice(19)
parent_start=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19])
WORK=Path(tempfile.mkdtemp(prefix='agentlab-lora-followup-stage51-'));WORK.chmod(0o700)
mounts=[(x.split(' - ')[0].split()[4],x.split(' - ')[1].split()[0]) for x in Path('/proc/self/mountinfo').read_text().splitlines()]
assert max([(len(p),f) for p,f in mounts if str(WORK).startswith(p.rstrip('/')+'/')])[1] in ['ext4','xfs','btrfs']
(OUT/'followup-location.json').write_text(json.dumps({'local_root':str(WORK),'runtime_root':str(ROOT),'original_full':str(ORIGINAL)})+'\n')
(OUT/'followup-location.json').chmod(0o600)
env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','HF_TOKEN','HUGGING_FACE_HUB_TOKEN','OPENAI_API_KEY','AGENT_LAB_EVIDENCE_KEY']}
env.update(OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TMPDIR=str(WORK),HF_HOME=str(WORK/'hf-cache'),XDG_CACHE_HOME=str(WORK/'xdg-cache'),TORCH_HOME=str(WORK/'torch-cache'),CUDA_CACHE_PATH=str(WORK/'cuda-cache'))
report={'terminal':False,'protocol_sha256':sha(OUT/'followup-protocol.json'),'phases':[],'status':'starting','original_Full_run_remains_failed':True,'Full_optimizer_updates_executed_this_controller':0,'original_Full_in_memory_final_hash_gap_remains':True,'Mixed_training_started':False,'GPU_work_started':False}
began=time.monotonic();driver=None;watcher=None;known={};lock=None;lastGPU=None;GPU_seen=False

def save():
 p=OUT/'followup-report.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(report,indent=2)+'\n');os.replace(tmp,p)

def tree(mode='all'):
 rows={}
 for p in Path('/proc').glob('[0-9]*'):
  try:
   if p.stat().st_uid!=os.getuid():continue
   s=(p/'stat').read_text().rsplit(')',1)[1].split()
   rows[int(p.name)]={'ppid':int(s[1]),'start':int(s[19]),'state':s[0],'rss':next((int(x.split()[1])*1024 for x in (p/'status').read_text().splitlines() if x.startswith('VmRSS:')),0)}
  except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 roots=[driver] if mode=='model' else [driver,watcher]
 ids={p.pid for p in roots if p is not None and p.poll() is None and p.pid in rows}
 if mode=='all':ids.update(p for p,start in known.items() if p in rows and rows[p]['start']==start)
 for _ in range(32):
  old=len(ids);ids.update(p for p,r in rows.items() if r['ppid'] in ids)
  if len(ids)==old:break
 ids={p for p in ids if rows[p]['state']!='Z'}
 known.update({p:rows[p]['start'] for p in ids})
 return {p:rows[p] for p in ids}

def stop(mode='all'):
 forced=False
 for sig,cap in [(signal.SIGTERM,10),(signal.SIGKILL,3)]:
  owned=tree(mode)
  if not owned:break
  forced|=sig==signal.SIGKILL
  for p,r in owned.items():
   if tree(mode).get(p,{}).get('start')==r['start']:
    try:os.kill(p,sig)
    except ProcessLookupError:pass
  end=time.monotonic()+cap
  while time.monotonic()<end and tree(mode):time.sleep(.2)
 for p in ([driver] if mode=='model' else [driver,watcher]):
  if p is not None:
   try:p.wait(timeout=3)
   except subprocess.TimeoutExpired:pass
 return {'forced_cleanup':forced,'remaining_owned_processes':list(tree(mode))}

def telemetry():
 assert watcher is not None and watcher.poll() is None,'NVML watcher exited'
 r=json.loads((WORK/'telemetry.json').read_text())
 assert r['watcher_pid']==watcher.pid and hashlib.sha256(r['uuid'].encode()).hexdigest()==spec['expected_GPU_UUID_sha256']
 age=time.monotonic()-r['observed_monotonic'];assert age>=-1
 return r,age

def public(c):return {**{k:v for k,v in c.items() if k not in ['uuid','pids','watcher_pid','observed_monotonic']},'UUID_sha256':hashlib.sha256(c['uuid'].encode()).hexdigest(),'compute_processes':len(c['pids'])}
def eligible(c):return '3090' in c['name'] and c['capability']=='8.6' and c['total_MiB']>=24000 and c['total_MiB']-c['used_MiB']>=23000 and c['utilization']<=5 and not c['pids']

def wait_fresh(after_sequence,timeout=10,after_monotonic=0):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  try:
   r,age=telemetry()
   if r['sequence']>after_sequence and r['observed_monotonic']>after_monotonic and age<=5:return r
  except FileNotFoundError:pass
  time.sleep(.2)
 raise TimeoutError('No fresh selected-GPU observation')

save()
try:
 with (OUT/'watcher.log').open('wb') as log:
  watcher=subprocess.Popen([str(CORE),str(OUT/'exec_child.py'),str(os.getpid()),str(parent_start),'cpu',str(CORE),str(OUT/'nvml_watch.py'),'--sdk',str(SDK),'--output',str(WORK/'telemetry.json'),'--uuid-sha',spec['expected_GPU_UUID_sha256'],'--index',str(spec['GPU_index']),'--seconds','3300'],cwd=WORK,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 admission=time.monotonic();first=None
 while True:
  tree()
  try:
   current,age=telemetry()
   if age<=5 and eligible(current):
    if first is None:first=current
    elif current['observed_monotonic']-first['observed_monotonic']>=5:
     (BASE/'locks').mkdir(exist_ok=True);candidate_lock=(BASE/'locks'/('gpu-'+current['uuid']+'.lock')).open('a')
     try:
      fcntl.flock(candidate_lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fresh=wait_fresh(current['sequence'])
      if eligible(fresh):lock=candidate_lock;lastGPU=fresh;report.update(GPU=public(fresh),admission_samples=[public(first),public(current)],status='running');save();break
      candidate_lock.close();first=None
     except BaseException:candidate_lock.close();raise
   else:first=None
  except (FileNotFoundError,BlockingIOError,TimeoutError):first=None
  elapsed=time.monotonic()-admission;report.update(admission_wait_seconds=round(elapsed,3),status='waiting_for_same_idle_GPU_and_fresh_NVML');save()
  if elapsed>=600:raise RuntimeError('Pinned RTX3090 not admitted within600s; no neural work started')
  time.sleep(.5)
 assert memory()>=32*2**30
 uuid=lastGPU['uuid']
 for phase in ['full_read_only_audit','mixed_train']:
  if phase=='mixed_train':
   fresh=wait_fresh(lastGPU['sequence'],after_monotonic=previous_phase_exit);assert eligible(fresh),'Prior phase CUDA context must be gone and GPU idle';lastGPU=fresh
  start=time.monotonic();guard=None;peak=0;output=WORK/phase;childenv=dict(env,CUDA_VISIBLE_DEVICES=uuid)
  command=[str(PY),str(OUT/'audit_full_checkpoint.py'),'--model',str(MODEL),'--data',str(DATA),'--original',str(ORIGINAL),'--output',str(output),'--spec',str(OUT/'followup-protocol.json')] if phase=='full_read_only_audit' else [str(PY),str(OUT/'train_driver.py'),'--model',str(MODEL),'--data',str(DATA),'--output',str(output),'--spec',str(OUT/'followup-protocol.json'),'--variant','mixed_train']
  with (OUT/(phase+'.log')).open('wb') as log,(OUT/(phase+'-monitor.jsonl')).open('w') as mon:
   driver=subprocess.Popen([str(CORE),str(OUT/'exec_child.py'),str(os.getpid()),str(parent_start),'gpu',*command],cwd=WORK,env=childenv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);report['current_phase']=phase;save()
   while driver.poll() is None:
    now=time.monotonic();elapsed=now-start;owned=tree();rss=sum(x['rss'] for x in owned.values());peak=max(peak,rss);mem=memory();row={'elapsed_seconds':round(elapsed,3),'owned_RSS_bytes':rss,'available_memory_bytes':mem}
    try:
     lastGPU,age=telemetry();foreign=set(lastGPU['pids'])-set(owned);GPU_seen|=bool(set(lastGPU['pids'])&set(owned));row.update(GPU_used_MiB=lastGPU['used_MiB'],foreign_compute_processes=len(foreign),own_GPU_context_seen=GPU_seen,observation_age_seconds=round(age,3),telemetry_sequence=lastGPU['sequence'],sample_seconds=lastGPU['sample_seconds'])
     if foreign:guard='foreign_compute_client'
     elif lastGPU['used_MiB']>22528:guard='GPU_memory_limit'
     elif age>30:guard='GPU_telemetry_stale'
    except BaseException as e:guard='GPU_monitor_unavailable';row['error_type']=type(e).__name__
    if GPU_seen:report['GPU_work_started']=True
    if elapsed>(600 if phase=='full_read_only_audit' else 1500):guard='phase_wall'
    elif now-began>3000:guard='job_wall'
    elif rss>24*2**30:guard='owned_RSS'
    elif mem<24*2**30:guard='host_memory_floor'
    state=json.loads((output/'report.json').read_text()) if (output/'report.json').exists() else {}
    if phase=='mixed_train' and state.get('training_run'):report['Mixed_training_started']=True
    if elapsed>300 and not state.get('model_loaded'):guard='model_load_watchdog'
    op=json.loads((output/'current-operation.json').read_text()) if (output/'current-operation.json').exists() else None
    if op and time.time()-op['started_unix']>300:guard='operation_watchdog'
    mon.write(json.dumps(row)+'\n');mon.flush()
    if guard:stop('model');break
    time.sleep(.5)
   rc=driver.wait();previous_phase_exit=time.monotonic();report['phases'].append({'phase':phase,'returncode':rc,'guard_reason':guard,'wall_seconds':round(time.monotonic()-start,3),'peak_sampled_owned_RSS_bytes':peak});save();print(json.dumps(report['phases'][-1]),flush=True)
  if rc or guard or tree('model'):raise RuntimeError('Follow-up phase failed: '+phase)
  result=json.loads((output/'report.json').read_text());assert result['status']=='completed'
  if phase=='full_read_only_audit':assert result['read_only_checkpoint_verified'] and result['optimizer_updates_executed']==0;report['Full_read_only_checkpoint_verified']=True
  else:
   assert result['completed_optimizer_updates']==32 and result['completed_training_labels']==65536 and result['frozen_parameters_unchanged'] and result['adapter_reload_verified'];report['Mixed_complete']=True
  driver=None;save()
 f=json.loads((ORIGINAL/'report.json').read_text());m=json.loads((WORK/'mixed_train/report.json').read_text())
 assert f['initial_adapter_sha256']==m['initial_adapter_sha256'] and f['initial_frozen_parameters_sha256']==m['initial_frozen_parameters_sha256']
 assert abs(f['before_dev']['token_weighted_NLL']-m['before_dev']['token_weighted_NLL'])<1e-3 and abs(f['before_val']['token_weighted_NLL']-m['before_val']['token_weighted_NLL'])<1e-3
 report.update(paired_initial_state_matched=True,followup_complete=True,Full_original_protocol_success=False)
except BaseException as e:report['operator_error']={'type':type(e).__name__,'message':str(e)}
finally:
 report['model_shutdown']=stop('model');report['own_GPU_context_seen']=GPU_seen
 if watcher is not None and watcher.poll() is None:
  try:
   sequence=lastGPU['sequence'] if lastGPU else 0;cleanup_started=time.monotonic()
   for _ in range(5):
    c=wait_fresh(sequence,timeout=10,after_monotonic=cleanup_started);sequence=c['sequence']
    if not set(c['pids'])&set(known):break
   report['own_GPU_context_absent']=not set(c['pids'])&set(known);report['GPU_after']=public(c)
  except BaseException as e:report['GPU_cleanup_observation_error']=type(e).__name__
 report['shutdown']=stop();summaries={}
 for phase in ['full_read_only_audit','mixed_train']:
  p=WORK/phase/'events.jsonl';events=[];bad=0
  if p.exists():
   for line in p.read_text().splitlines():
    try:events.append(json.loads(line))
    except json.JSONDecodeError:bad+=1
  counts={n:sum(x['event']==n for x in events) for n in ['forward_reserved','forward_completed','backward_completed','optimizer_update_reserved','optimizer_update_completed','checkpoint_committed']};counts['forward_unknown_still_charged']=counts['forward_reserved']-counts['forward_completed'];counts['optimizer_update_unknown_still_charged']=counts['optimizer_update_reserved']-counts['optimizer_update_completed'];counts['malformed_journal_lines']=bad;summaries[phase]=counts
 report.update(terminal=True,status='completed' if report.get('followup_complete') else 'failed',ledgers=summaries,original_Full_files_unchanged=all(streamsha(ORIGINAL/n)==d for n,d in original_files.items()) and sha(OLD/'training-report.json')==old_controller_hash,source_and_inputs_unchanged=sha(OUT/'train_driver.py')==spec['driver_sha256'] and sha(OUT/'exec_child.py')==spec['wrapper_sha256'] and sha(OUT/'audit_full_checkpoint.py')==spec['full_audit_driver_sha256'] and sha(OUT/'nvml_watch.py')==spec['watcher_sha256'] and all(streamsha(DATA/n)==d for n,d in spec['data_sha256'].items()),wall_seconds=round(time.monotonic()-began,3));save();print(json.dumps(report),flush=True)
raise SystemExit(0 if report.get('followup_complete') and not report.get('operator_error') and not report['shutdown']['remaining_owned_processes'] and report.get('own_GPU_context_absent') and report['source_and_inputs_unchanged'] and report['original_Full_files_unchanged'] else 2)
