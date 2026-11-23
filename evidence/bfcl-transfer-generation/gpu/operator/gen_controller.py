"""One bounded, unscored segment of the immutable250case generation cohort."""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,resource,signal,subprocess,sys,tempfile,time
from gpu_ownership import start_ticks,classify_compute_pids
from cpu_admission import measure_compute_headroom

parser=argparse.ArgumentParser()
parser.add_argument('--variant',choices=['base','reference32','masked32'],required=True)
parser.add_argument('--segment',type=int,required=True)
a=parser.parse_args();assert 1<=a.segment<=32
OUT=Path(__file__).resolve().parent;BASE=Path('[SERVER_WORKSPACE]')
CORE=BASE/'envs/model-request-budget-20261121/bin/python'
spec=json.loads((OUT/'protocol.json').read_text());assert spec['phase']=='bfcl_generation'
RUN=OUT/(a.variant+'-segment-%03d-controller.json'%a.segment);assert not RUN.exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert resource.getrlimit(resource.RLIMIT_AS)==(-1,-1)
CPUOUT=BASE/'outputs/bfcl-generation-stage75-cpu-20261124-v1'
CPUR=Path(json.loads((CPUOUT/'location.json').read_text())['root'])
CODE=CPUR/'source';EXPERIMENT=CPUR/'experiment'
assert all(sha(CODE/n)==expected for n,expected in spec['source_sha256'].items())
sys.path.insert(0,str(CODE))
from benchmarks.generation_progress import GenerationProgress
assert sha(EXPERIMENT/'definition.json')==spec['definition_sha256']
definition=json.loads((EXPERIMENT/'definition.json').read_text())
progress=GenerationProgress(EXPERIMENT/'progress',definition)
assert progress.owner==spec['definition_owner_sha256']
initial=progress.snapshot();initial_cached=sum(k.startswith(a.variant+':') for k in initial['results'])
assert initial_cached<250,'This role is already complete; do not start another model'
for role in definition['variants'][:definition['variants'].index(a.variant)]:assert sum(k.startswith(role+':') for k in initial['results'])==250
prior_reports=[]
for n in range(1,a.segment):
 path=OUT/(a.variant+'-segment-%03d-controller.json'%n);r=json.loads(path.read_text());assert r['terminal'] and r['protocol_sha256']==sha(OUT/'protocol.json') and r.get('own_GPU_context_absent') and not r['shutdown']['remaining_owned_processes'];prior_reports.append(r)
prior_neural_seconds=sum(sum(p['wall_seconds'] for p in r['phases']) for r in prior_reports)
assert prior_neural_seconds<28800
os.umask(0o077);os.nice(19);allowed_cpus=set(os.sched_getaffinity(0))
WORK=Path(tempfile.mkdtemp(prefix='agentlab-bfcl-'+a.variant+'-stage75-'));WORK.chmod(0o700)
(OUT/(a.variant+'-segment-%03d-location.json'%a.segment)).write_text(json.dumps({'root':str(WORK),'experiment':str(EXPERIMENT)})+'\n')
RUNTIME=Path('[MODEL_RUNTIME]');PY=RUNTIME/'runtime/bin/python';MODEL=RUNTIME/'model'
SDK=Path(json.loads((BASE/'outputs/lora-nvml-stage51-20261123/monitor-location.json').read_text())['local_root'])/'sdk'
CK=None if a.variant=='base' else BASE/spec['checkpoint_archive_relative']/a.variant
parent_start=start_ticks(os.getpid())
env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH'] and not k.endswith(('_KEY','_TOKEN','_SECRET'))}
env.update(PYTHONPATH=str(CODE),OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TMPDIR=str(WORK),HF_HOME=str(WORK/'hf-cache'),XDG_CACHE_HOME=str(WORK/'xdg-cache'),CUDA_CACHE_PATH=str(WORK/'cuda-cache'))
report={'terminal':False,'status':'starting','variant':a.variant,'segment':a.segment,
        'protocol_sha256':sha(OUT/'protocol.json'),'initial_cached_cases':initial_cached,
        'initial_total_attempts':len(initial['attempts']),'initial_total_committed':len(initial['results']),
        'declared_cases_per_role':250,'max_NEW_cases_this_segment':125,'phases':[],
        'scoring_or_training':False,'generation_budget':definition['limits']}
began=time.monotonic();driver=None;watcher=None;known={};lock=None;lastGPU=None;GPU_seen=False

def save():
 temp=RUN.with_suffix('.tmp');temp.write_text(json.dumps(report,indent=2)+'\n');os.replace(temp,RUN)

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

def eligible(c):return c['driver_version']==spec['expected_driver_version'] and '3090' in c['name'] and c['capability']=='8.6' and c['total_MiB']>=24000 and c['total_MiB']-c['used_MiB']>=23000 and c['utilization']<=5 and not c['pids']

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
 for name,key in [('gen_controller.py','operator_sha256'),('exec_gpu_child.py','wrapper_sha256'),('nvml_watch.py','watcher_sha256'),('gpu_ownership.py','ownership_source_sha256'),('cpu_admission.py','cpu_admission_sha256')]:assert sha(OUT/name)==spec[key],name
 assert sha(CPUOUT/'protocol.json')==spec['CPU_protocol_sha256']
 ready=json.loads((CPUOUT/'run-report.json').read_text());assert ready['terminal'] and ready['ready'] and not ready['owned_after'] and ready['inputs_and_sources_unchanged']
 assert sha(EXPERIMENT/'inputs-tokenized.jsonl')==spec['tokenized_inputs_sha256']
 assert sha(Path('/tmp/agentlab-generation-recovery-stage52-4dmrtpsd/progress/generation-progress.json'))==spec['old_ledger_sha256']
 assert sha(SDK/'pynvml.py')==spec['pynvml_sha256']
 assert memory()>=32*2**30
 report['CPU_admission']=measure_compute_headroom(allowed_cpus,interval_seconds=5,count=4,minimum=.8);assert len(report['CPU_admission']['selected_cpus'])==4;os.sched_setaffinity(0,report['CPU_admission']['selected_cpus']);save()
 mf=BASE/'outputs/lora-training-stage51-20261123/model-manifest.json';assert sha(mf)==spec['base_model_manifest_sha256']
 for item in json.loads(mf.read_text())['files']:
  path=MODEL/item['path'];assert path.stat().st_size==item['bytes'];h=hashlib.sha256() if item['lfs_sha256'] else hashlib.sha1()
  if not item['lfs_sha256']:h.update(('blob '+str(item['bytes'])+'\0').encode())
  with path.open('rb') as f:
   while block:=f.read(2*1024*1024):h.update(block)
  assert h.hexdigest()==(item['lfs_sha256'] or item['git_blob_sha1'])
 if CK:
  for name,expected in spec['models'][a.variant]['checkpoint_files_sha256'].items():assert sha(CK/name)==expected
 with (OUT/(a.variant+'-segment-%03d-watcher.log'%a.segment)).open('wb') as log:
  watcher=subprocess.Popen([str(CORE),str(OUT/'exec_gpu_child.py'),str(os.getpid()),str(parent_start),'cpu',str(CORE),str(OUT/'nvml_watch.py'),'--sdk',str(SDK),'--output',str(WORK/'telemetry.json'),'--uuid-sha',spec['expected_GPU_UUID_sha256'],'--index',str(spec['GPU_index']),'--seconds','2500'],cwd=WORK,env=dict(env,CUDA_VISIBLE_DEVICES=''),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 admission=time.monotonic();first=None
 while True:
  tree()
  try:
   current,age=telemetry()
   if age<=5 and eligible(current):
    if first is None:first=current
    elif current['observed_monotonic']-first['observed_monotonic']>=5:
     (BASE/'locks').mkdir(exist_ok=True);candidate=(BASE/'locks'/('gpu-'+current['uuid']+'.lock')).open('a')
     try:
      fcntl.flock(candidate,fcntl.LOCK_EX|fcntl.LOCK_NB);fresh=wait_fresh(current['sequence'])
      if eligible(fresh):lock=candidate;lastGPU=fresh;report.update(GPU=public(fresh),admission_samples=[public(first),public(current)],status='admitted');save();break
      candidate.close();first=None
     except BaseException:candidate.close();raise
   else:first=None
  except (FileNotFoundError,BlockingIOError,TimeoutError):first=None
  elapsed=time.monotonic()-admission;report.update(status='waiting_for_pinned_idle_GPU',admission_wait_seconds=round(elapsed,3));save()
  if elapsed>=600:raise RuntimeError('No pinned idleGPU within600s;zero modeldispatch')
  if memory()<32*2**30:raise RuntimeError('Host memory below admission')
  time.sleep(.5)
 report['fresh_CPU_admission']=measure_compute_headroom(allowed_cpus,interval_seconds=5,count=4,minimum=.8);assert len(report['fresh_CPU_admission']['selected_cpus'])==4;os.sched_setaffinity(0,report['fresh_CPU_admission']['selected_cpus']);save()
 fresh=wait_fresh(lastGPU['sequence']);assert eligible(fresh);lastGPU=fresh;assert memory()>=32*2**30
 output=WORK/'run';start=time.monotonic();peak=0;guard=None
 command=[str(PY),str(CODE/'benchmarks/bfcl_generation.py'),'--model',str(MODEL),'--experiment',str(EXPERIMENT),'--protocol',str(OUT/'protocol.json'),'--output',str(output),'--variant',a.variant]
 if CK:command+=['--checkpoint',str(CK)]
 with (OUT/(a.variant+'-segment-%03d.log'%a.segment)).open('wb') as log,(OUT/(a.variant+'-segment-%03d-monitor.jsonl'%a.segment)).open('w') as monitor:
  driver=subprocess.Popen([str(CORE),str(OUT/'exec_gpu_child.py'),str(os.getpid()),str(parent_start),'gpu',*command],cwd=CODE,env=dict(env,CUDA_VISIBLE_DEVICES=lastGPU['uuid']),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  known[driver.pid]=start_ticks(driver.pid);report['status']='running';report['driver_identity']={'pid':driver.pid,'start_ticks':known[driver.pid]};save()
  while driver.poll() is None:
   now=time.monotonic();elapsed=now-start;owned=tree();rss=sum(v['rss'] for v in owned.values());peak=max(peak,rss);row={'elapsed_seconds':round(elapsed,3),'owned_RSS_bytes':rss,'available_memory_bytes':memory()}
   try:
    lastGPU,age=telemetry();classification=classify_compute_pids(lastGPU['pids'],known);foreign=classification['foreign'];GPU_seen|=bool(set(lastGPU['pids'])&set(owned));row.update(GPU_used_MiB=lastGPU['used_MiB'],foreign_compute_processes=len(foreign),observation_age_seconds=round(age,3),telemetry_sequence=lastGPU['sequence'])
    if foreign:guard='foreign_compute_client'
    elif age>30:guard='GPU_telemetry_stale'
    elif lastGPU['used_MiB']>22528:guard='GPU_memory_limit'
   except BaseException as error:guard='GPU_monitor_unavailable';row['error_type']=type(error).__name__
   if elapsed>1500:guard='neural_phase_wall'
   elif now-began>2400:guard='controller_wall'
   elif elapsed+prior_neural_seconds>28800:guard='cumulative_neural_wall'
   elif rss>24*2**30:guard='owned_RSS'
   elif row['available_memory_bytes']<24*2**30:guard='host_memory_floor'
   state=json.loads((output/'report.json').read_text()) if (output/'report.json').exists() else {}
   if elapsed>300 and not state.get('model_loaded'):guard='model_load_watchdog'
   operation=json.loads((output/'current-operation.json').read_text()) if (output/'current-operation.json').exists() else {}
   if operation:
    ageop=time.time()-operation['started_unix']
    if ageop>(180 if operation['kind']=='generating' else 300):guard='operation_watchdog'
   monitor.write(json.dumps(row)+'\n');monitor.flush()
   if guard:stop('model');break
   time.sleep(.5)
  rc=driver.wait();report['phases'].append({'phase':a.variant,'returncode':rc,'guard_reason':guard,'wall_seconds':round(time.monotonic()-start,3),'peak_sampled_owned_RSS_bytes':peak});save();print(json.dumps(report['phases'][-1]),flush=True)
 if rc or guard or tree('model'):raise RuntimeError('Generation segment failed')
 result=json.loads((output/'report.json').read_text());assert result['status']=='completed' and result['frozen_base_unchanged'] and 0<=result['new_model_calls']<=125
 assert result['variant_committed_cases']==initial_cached+result['new_model_calls']
 report.update(segment_complete=True,all_cases_completed=result['all_cases_completed'],neural_summary=result)
except BaseException as error:report['operator_error']={'type':type(error).__name__,'message':str(error)[:600]}
finally:
 report['model_shutdown']=stop('model');report['own_GPU_context_seen']=GPU_seen
 if watcher is None and driver is None:report['own_GPU_context_absent']=True
 if watcher is not None and watcher.poll() is None:
  try:
   sequence=lastGPU['sequence'] if lastGPU else 0;cleanup_started=time.monotonic()
   for _ in range(5):
    current=wait_fresh(sequence,timeout=10,after_monotonic=cleanup_started);sequence=current['sequence']
    if not set(current['pids'])&set(known):break
   report['own_GPU_context_absent']=not set(current['pids'])&set(known);report['GPU_after']=public(current)
  except BaseException as error:report['GPU_cleanup_observation_error']=type(error).__name__
 report['shutdown']=stop();final=progress.snapshot();scoped=[r for r in final['attempts'] if r['variant']==a.variant]
 report['accounting']={'total_attempts':len(final['attempts']),'total_results':len(final['results']),'total_unknown_still_charged':sum(r['state']=='reserved' for r in final['attempts']),'variant_attempts':len(scoped),'variant_results':sum(k.startswith(a.variant+':') for k in final['results']),'variant_unknown_still_charged':sum(r['state']=='reserved' for r in scoped),'new_attempts_this_segment':len(final['attempts'])-len(initial['attempts'])}
 report['prior_results_preserved']=all(final['results'].get(k)==v for k,v in initial['results'].items())
 report['source_and_inputs_unchanged']=all(sha(CODE/n)==d for n,d in spec['source_sha256'].items()) and sha(EXPERIMENT/'definition.json')==spec['definition_sha256'] and sha(EXPERIMENT/'inputs-tokenized.jsonl')==spec['tokenized_inputs_sha256'] and (not CK or all(sha(CK/n)==d for n,d in spec['models'][a.variant]['checkpoint_files_sha256'].items()))
 old=Path('/tmp/agentlab-generation-recovery-stage52-4dmrtpsd/progress/generation-progress.json');report['old_generation_ledger_unchanged']=sha(old)==spec['old_ledger_sha256']
 report.update(terminal=True,status='completed' if report.get('segment_complete') else 'failed',wall_seconds=round(time.monotonic()-began,3));save()
 print(json.dumps({k:report.get(k) for k in ['terminal','status','variant','segment','all_cases_completed','operator_error','accounting','own_GPU_context_absent','source_and_inputs_unchanged','prior_results_preserved','wall_seconds']}),flush=True)
raise SystemExit(0 if report.get('segment_complete') and not report.get('operator_error') and not report['shutdown']['remaining_owned_processes'] and report.get('own_GPU_context_absent') and report['source_and_inputs_unchanged'] and report['prior_results_preserved'] and report['old_generation_ledger_unchanged'] else 2)
