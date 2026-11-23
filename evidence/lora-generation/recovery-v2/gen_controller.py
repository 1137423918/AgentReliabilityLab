from pathlib import Path
import argparse,fcntl,hashlib,json,os,resource,signal,subprocess,tempfile,time
from gpu_ownership import start_ticks,classify_compute_pids
p=argparse.ArgumentParser();p.add_argument('--variant',choices=['full32','mixed32'],required=True);a=p.parse_args()
OUT=Path(__file__).resolve().parent;BASE=Path('/path/to/private-agent-lab');CORE=BASE/'envs/model-request-budget-20261121/bin/python';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();spec=json.loads((OUT/'generation-protocol.json').read_text());RUN=OUT/(a.variant+'-controller.json');assert not RUN.exists()
for n,key in [('gen_controller.py','generation_source_sha256'),('driver.py','driver_sha256'),('nvml_watch.py','watcher_sha256'),('gpu_ownership.py','ownership_source_sha256'),('generation_progress.py','progress_source_sha256'),('generation_resume.py','resume_source_sha256'),('exec_child.py','wrapper_sha256')]:assert sha(OUT/n)==spec[key],n
assert resource.getrlimit(resource.RLIMIT_AS)==(-1,-1)
ready=json.loads((OUT/'setup-report.json').read_text());assert ready['terminal'] and ready['ready'] and ready['protocol_sha256']==spec['CPU_protocol_sha256']
order=spec['variants'];i=order.index(a.variant)
for v in order[:i]:
 r=json.loads((OUT/(v+'-controller.json')).read_text());assert r['terminal'] and r['all_cases_completed'] and r['protocol_sha256']==sha(OUT/'generation-protocol.json')
location=json.loads((OUT/'control-location.json').read_text());ROOT=Path(location['runtime']);PY=ROOT/'runtime/bin/python';MODEL=Path(location['model']);UP=Path(location['upstream']);ADMISSION=Path(location['root'])/'admission.json';SDK=Path(location['sdk']);assert sha(SDK/'pynvml.py')==spec['pynvml_sha256'];assert sha(ADMISSION)==ready['assembly']['new_admission_sha256']
CK=Path(location['full' if a.variant=='full32' else 'mixed']) if a.variant!='base' else None
from generation_progress import GenerationProgress
DEFINITION=Path(location['root'])/'progress/definition.json'
assert sha(DEFINITION)==spec['definition_file_sha256']
progress=GenerationProgress(DEFINITION.parent,json.loads(DEFINITION.read_text()));assert progress.owner==spec['definition_owner_sha256'];initial_state=progress.snapshot();assert sum(k.startswith('base:') for k in initial_state['results'])==199
initial_cached=sum(k.startswith(a.variant+':') for k in initial_state['results']);assert initial_cached<199
initial_scoped=[x for x in initial_state['attempts'] if x['variant']==a.variant]

os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:4]);os.nice(19);parent_start=start_ticks(os.getpid());WORK=Path(tempfile.mkdtemp(prefix='agentlab-generation-'+a.variant+'-stage52-'));WORK.chmod(0o700)
mounts=[(x.split(' - ')[0].split()[4],x.split(' - ')[1].split()[0]) for x in Path('/proc/self/mountinfo').read_text().splitlines()];assert max([(len(p),f) for p,f in mounts if str(WORK).startswith(p.rstrip('/')+'/')])[1] in ['ext4','xfs','btrfs']
(OUT/(a.variant+'-location.json')).write_text(json.dumps({'root':str(WORK)})+'\n');(OUT/(a.variant+'-location.json')).chmod(0o600)
env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','OPENAI_API_KEY','HF_TOKEN','HUGGING_FACE_HUB_TOKEN','AGENT_LAB_EVIDENCE_KEY']};env.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TMPDIR=str(WORK),HF_HOME=str(WORK/'hf-cache'),XDG_CACHE_HOME=str(WORK/'xdg-cache'),TORCH_HOME=str(WORK/'torch-cache'),CUDA_CACHE_PATH=str(WORK/'cuda-cache'))
report={'terminal':False,'status':'starting','variant':a.variant,'protocol_sha256':sha(OUT/'generation-protocol.json'),'driver_sha256':spec['driver_sha256'],'training_run':False,'declared_cases':199,'max_additional_calls_this_segment':199-initial_cached,'experiment_total_generation_calls':603,'original_no_retry_profile_remains_incomplete':True,'initial_cached_cases':initial_cached,'initial_variant_attempts':len(initial_scoped),'GPU_work_started':False,'phases':[]};began=time.monotonic();driver=None;watcher=None;known={};lock=None;lastGPU=None;GPU_seen=False

def save():
 t=RUN.with_suffix('.tmp');t.write_text(json.dumps(report,indent=2)+'\n');os.replace(t,RUN)
def memory():return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024

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
 assert memory()>=32*2**30
 identity_code="import importlib.metadata as m,json;print(json.dumps({n:m.version(n) for n in ['torch','transformers','peft']}))"
 identity=subprocess.run([str(PY),'-c',identity_code],cwd=WORK,env=env,capture_output=True,text=True,timeout=30);assert identity.returncode==0;report['runtime_versions']=json.loads(identity.stdout);assert report['runtime_versions']==spec['runtime_versions']
 assert all(sha(UP/n)==d for n,d in spec['upstream_source_sha256'].items())
 model_manifest=json.loads((OUT/'model-manifest.json').read_text());assert sha(OUT/'model-manifest.json')==spec['model_manifest_sha256']
 for x in model_manifest['files']:
  path=MODEL/x['path'];assert path.stat().st_size==x['bytes'];h=hashlib.sha256() if x['lfs_sha256'] else hashlib.sha1()
  if not x['lfs_sha256']:h.update(('blob '+str(x['bytes'])+'\0').encode())
  with path.open('rb') as f:
   while b:=f.read(2*1024*1024):h.update(b)
  assert h.hexdigest()==(x['lfs_sha256'] or x['git_blob_sha1'])
 ckmanifest=json.loads((CK/'manifest.json').read_text()) if CK else {}
 if CK:
  assert sha(CK/'manifest.json')==spec['checkpoint_manifest_sha256'][a.variant];assert all(sha(CK/n)==d for n,d in ckmanifest.items())
 with (OUT/(a.variant+'-watcher.log')).open('wb') as log:
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
      if eligible(fresh):
       assert fresh['driver_version']==spec['GPU_driver_version']
       lock=candidate_lock;lastGPU=fresh;report.update(GPU=public(fresh),admission_samples=[public(first),public(current)],status='running');save();break
      candidate_lock.close();first=None
     except BaseException:candidate_lock.close();raise
   else:first=None
  except (FileNotFoundError,BlockingIOError,TimeoutError):first=None
  elapsed=time.monotonic()-admission;report.update(admission_wait_seconds=round(elapsed,3),status='waiting_for_fixed_idle_GPU');save()
  if elapsed>=600:raise RuntimeError('Pinned same-backend GPU not admitted600s; no model started')
  time.sleep(.5)
 assert memory()>=32*2**30
 childenv=dict(env,CUDA_VISIBLE_DEVICES=lastGPU['uuid']);output=WORK/'run';start=time.monotonic();guard=None;peak=0
 last_identity_sequence=None
 command=[str(PY),str(OUT/'driver.py'),'run','--upstream',str(UP),'--model',str(MODEL),'--output',str(output),'--admission',str(ADMISSION),'--max-context','32768','--max-tokens','1024','--progress-dir',str(DEFINITION.parent),'--variant',a.variant]
 if CK:command+=['--adapter',str(CK/'adapter')]
 with (OUT/(a.variant+'.log')).open('wb') as log,(OUT/(a.variant+'-monitor.jsonl')).open('w') as mon:
  driver=subprocess.Popen([str(CORE),str(OUT/'exec_child.py'),str(os.getpid()),str(parent_start),'gpu',*command],cwd=WORK,env=childenv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);known[driver.pid]=start_ticks(driver.pid);(OUT/(a.variant+'-owned-identities.json')).write_text(json.dumps({'driver_pid':driver.pid,'start_ticks':known[driver.pid]})+'\n');report['neural_driver_started']=True;save()
  while driver.poll() is None:
   now=time.monotonic();elapsed=now-start;owned=tree();rss=sum(x['rss'] for x in owned.values());peak=max(peak,rss);mem=memory();row={'elapsed_seconds':round(elapsed,3),'owned_RSS_bytes':rss,'available_memory_bytes':mem}
   try:
    lastGPU,age=telemetry();owned=tree();classification=classify_compute_pids(lastGPU['pids'],known);
    identities={}
    for pid in lastGPU['pids']:
     try:identity=start_ticks(pid)
     except (OSError,ValueError):identity=None
     identities[str(pid)]={'known_owned_start':known.get(pid),'observed_start':identity}
    packet={'telemetry':lastGPU,'classification':classification,'PID_start_identities':identities,'controller_monotonic':time.monotonic()}
    if last_identity_sequence!=lastGPU['sequence']:
     with (WORK/'GPU-identity-journal.jsonl').open('a') as identity_log:identity_log.write(json.dumps(packet)+'\n');identity_log.flush()
     last_identity_sequence=lastGPU['sequence']
    foreign=set(classification['foreign']);GPU_seen|=bool(set(lastGPU['pids'])&set(owned));row.update(cached_exited_owned_compute_count=len(classification['cached_exited_owned']),GPU_used_MiB=lastGPU['used_MiB'],foreign_compute_processes=len(foreign),own_GPU_context_seen=GPU_seen,observation_age_seconds=round(age,3),telemetry_sequence=lastGPU['sequence'],sample_seconds=lastGPU['sample_seconds'])
    if foreign:guard='foreign_compute_client'
    elif lastGPU['used_MiB']>22528:guard='GPU_memory_limit'
    elif age>30:guard='GPU_telemetry_stale'
   except BaseException as e:guard='GPU_monitor_unavailable';row['error_type']=type(e).__name__
   if elapsed>2400:guard='neural_phase_wall'
   elif now-began>3300:guard='controller_wall'
   elif elapsed+spec['prior_neural_seconds'][a.variant]>3600:guard='cumulative_neural_wall'
   elif rss>24*2**30:guard='owned_RSS'
   elif mem<24*2**30:guard='host_memory_floor'
   state=json.loads((output/'report.json').read_text()) if (output/'report.json').exists() else {}
   if state.get('model_parameter_count') and not report.get('model_loaded'):report.update(model_loaded=True,GPU_work_started=GPU_seen);save()
   if elapsed>300 and not state.get('model_parameter_count'):guard='model_load_watchdog'
   call=json.loads((output/'current-call.json').read_text()) if (output/'current-call.json').exists() else {}
   if call.get('status')=='generating' and time.time()-call['started_unix']>180:guard='single_call_watchdog'
   mon.write(json.dumps(row)+'\n');mon.flush()
   if guard:
    if 'packet' in locals():(WORK/'guard-trigger-private.json').write_text(json.dumps({'guard':guard,'trigger_unix':time.time(),'last_sample':packet})+'\n')
    stop('model');break
   time.sleep(.5)
  rc=driver.wait();report['phases'].append({'phase':a.variant,'returncode':rc,'guard_reason':guard,'wall_seconds':round(time.monotonic()-start,3),'peak_sampled_owned_RSS_bytes':peak});save();print(json.dumps(report['phases'][-1]),flush=True)
 if rc or guard or tree('model'):raise RuntimeError('Generation phase failed: '+a.variant)
 result=json.loads((output/'report.json').read_text());assert result['status']=='completed' and result['completed_cases']==199 and result['model_calls']+result['cached_cases']==199 and result['cached_cases']==initial_cached and result['adapter_used']==bool(CK)
 if CK:assert result['adapter_artifact_sha256']=={n:ckmanifest['adapter/'+n] for n in ['adapter_config.json','adapter_model.safetensors']}
 assert result['model_parameter_count']==(3087781888 if CK else 3085938688) and result['GPU_compute_capability']==[8,6]
 report.update(all_cases_completed=True,neural_summary={k:result[k] for k in ['completed_cases','model_calls','cached_cases','input_tokens','generated_token_ids','scores','required_key_violation_cases','truncated_or_soft_time_stopped','adapter_used','retries','progress_summary']})
except BaseException as e:report['operator_error']={'type':type(e).__name__,'message':str(e)}
finally:
 report['model_shutdown']=stop('model');report['own_GPU_context_seen']=GPU_seen
 if watcher is not None and watcher.poll() is None:
  try:
   seq=lastGPU['sequence'] if lastGPU else 0;cleanup_started=time.monotonic()
   for _ in range(5):
    card=wait_fresh(seq,timeout=10,after_monotonic=cleanup_started);seq=card['sequence']
    if not set(card['pids'])&set(known):break
   report['own_GPU_context_absent']=not set(card['pids'])&set(known);report['GPU_after']=public(card)
  except BaseException as e:report['GPU_cleanup_observation_error']=type(e).__name__
 report['shutdown']=stop();journal=WORK/'run/calls.jsonl';events=[json.loads(x) for x in journal.read_text().splitlines()] if journal.exists() else [];reserved=[x for x in events if x['event']=='reserved'];completed=[x for x in events if x['event']=='completed'];assert len(reserved)<=199
 state=progress.snapshot();scoped=[x for x in state['attempts'] if x['variant']==a.variant];report['shared_generation_accounting']={'all_attempts_reserved':len(state['attempts']),'all_results_committed':len(state['results']),'all_unknown_still_charged':sum(x['state']=='reserved' for x in state['attempts']),'variant_attempts_reserved':len(scoped),'variant_results_committed':sum(k.startswith(a.variant+':') for k in state['results']),'variant_unknown_still_charged':sum(x['state']=='reserved' for x in scoped)}
 report.update(terminal=True,status='completed' if report.get('all_cases_completed') else 'failed',local_generation_ledger={'reserved':len(reserved),'completed':len(completed),'unknown_still_charged':len(reserved)-len(completed)},source_and_inputs_unchanged=sha(OUT/'driver.py')==spec['driver_sha256'] and sha(OUT/'exec_child.py')==spec['wrapper_sha256'] and all(sha(UP/n)==d for n,d in spec['upstream_source_sha256'].items()) and (not CK or all(sha(CK/n)==d for n,d in ckmanifest.items())),wall_seconds=round(time.monotonic()-began,3));save();print(json.dumps(report),flush=True)
raise SystemExit(0 if report.get('all_cases_completed') and not report.get('operator_error') and not report['shutdown']['remaining_owned_processes'] and report.get('own_GPU_context_absent') and report['source_and_inputs_unchanged'] else 2)
