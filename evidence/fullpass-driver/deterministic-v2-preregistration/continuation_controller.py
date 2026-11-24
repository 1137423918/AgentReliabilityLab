"""One non-replayable physical GPU process of a training continuation control."""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,resource,signal,subprocess,sys,tempfile,time
from gpu_ownership import start_ticks,classify_compute_pids
from cpu_admission import measure_compute_headroom
parser=argparse.ArgumentParser();parser.add_argument('--variant',choices=['baseline','split-prefix','split-resume'],required=True);a=parser.parse_args()
OUT=Path(__file__).resolve().parent;BASE=Path('[SERVER_WORKSPACE]');CORE=BASE/'envs/model-request-budget-20261121/bin/python'
spec=json.loads((OUT/'protocol.json').read_text());assert spec['phase']=='gpu_checkpoint_continuation_control'
RUN=OUT/(a.variant+'-controller.json');assert not RUN.exists();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert resource.getrlimit(resource.RLIMIT_AS)==(-1,-1)
CPUOUT=BASE/'outputs/fullpass-driver-stage80-cpu-20261124-v1';CODE=OUT/'source';EXPERIMENT=OUT/'experiment';DATA=Path('[MODEL_RUNTIME]/data')
assert all(sha(CODE/n)==d for n,d in spec['source_sha256'].items());sys.path.insert(0,str(CODE))
from benchmarks.training_journal import TrainingJournal
role,segment={'baseline':('continuous',0),'split-prefix':('split',0),'split-resume':('split',1)}[a.variant]
plan=spec['trajectories'][role];identity={'spec_sha256':sha(OUT/'protocol.json'),'source_sha256':spec['source_sha256'],'seed':plan['seed'],'profile':plan['profile'],'trajectory':role,'schedule_sha256':spec['schedules_sha256'][str(plan['seed'])]}
definition={'identity':identity,'segments':plan['segments'],'forward_cap':sum(s['forwards'] for s in plan['segments']),'optimizer_cap':plan['segments'][-1]['end']}
progress=TrainingJournal(EXPERIMENT/role/'journal',definition);initial=progress.snapshot();owner=progress.owner;progress.close();assert initial['next_segment']==segment and initial['status'] in ['idle','clean']
if a.variant!='baseline':
 previous='baseline' if a.variant=='split-prefix' else 'split-prefix';p=json.loads((OUT/(previous+'-controller.json')).read_text());assert p['terminal'] and p['status']=='completed' and p['own_GPU_context_absent'] and not p['shutdown']['remaining_owned_processes']
os.umask(0o077);os.nice(19);allowed_cpus=set(os.sched_getaffinity(0));WORK=Path(tempfile.mkdtemp(prefix='agentlab-fullpass-'+a.variant+'-stage80-'));WORK.chmod(0o700)
(OUT/(a.variant+'-location.json')).write_text(json.dumps({'root':str(WORK),'experiment':str(EXPERIMENT)})+'\n')
RUNTIME=Path('[MODEL_RUNTIME]');PY=RUNTIME/'runtime/bin/python';MODEL=RUNTIME/'model';SDK=Path(json.loads((BASE/'outputs/lora-nvml-stage51-20261123/monitor-location.json').read_text())['local_root'])/'sdk';parent_start=start_ticks(os.getpid())
env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH'] and not k.endswith(('_KEY','_TOKEN','_SECRET'))};env.update(PYTHONPATH=str(CODE),OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TMPDIR=str(WORK),HF_HOME=str(WORK/'hf-cache'),XDG_CACHE_HOME=str(WORK/'xdg-cache'),CUDA_CACHE_PATH=str(WORK/'cuda-cache'),CUBLAS_WORKSPACE_CONFIG=':4096:8')
report={'terminal':False,'status':'starting','variant':a.variant,'trajectory':role,'segment':segment,'protocol_sha256':sha(OUT/'protocol.json'),'initial_journal':initial,'phases':[],'text_generations':0,'control_only_not_fullpass_training':True}
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
 for n,k in [('continuation_controller.py','operator_sha256'),('exec_gpu_child.py','wrapper_sha256'),('nvml_watch.py','watcher_sha256'),('gpu_ownership.py','ownership_source_sha256'),('cpu_admission.py','cpu_admission_sha256')]:assert sha(OUT/n)==spec[k]
 assert sha(CPUOUT/'protocol.json')==spec['CPU_protocol_sha256'];ready=json.loads((CPUOUT/'run-report.json').read_text());assert ready['terminal'] and ready['ready'] and not ready['owned_after'] and ready['inputs_and_sources_unchanged']
 assert sha(SDK/'pynvml.py')==spec['pynvml_sha256']
 for n,d in spec['data_sha256'].items():assert sha(DATA/n)==d
 masked=Path('/tmp/agentlab-alignment-stage71-eo81wexz/analysis/private/train-masked-tokenized.jsonl');assert sha(masked)==spec['masked_data_sha256']
 ledgers={Path('/tmp/agentlab-generation-recovery-stage52-4dmrtpsd/progress/generation-progress.json'):spec['old_ledger_sha256'],BASE/'studies/bfcl-generation-fixed250-stage75-20261124/experiment/progress/generation-progress.json':spec['closed250_ledger_sha256'],BASE/'studies/loss-parts-stage78-20261124/prepared/experiment/progress/generation-progress.json':spec['closed_loss_parts_ledger_sha256']}
 for rel,d in spec['prior_failed_control']['journal_sha256'].items():ledgers[BASE/rel]=d
 ledgers[BASE/'outputs/fullpass-driver-stage80-gpu-20261124-v1/comparison.json']=spec['prior_failed_control']['comparison_sha256']
 ledgers[BASE/'outputs/fullpass-driver-stage80-gpu-20261124-v1/closure.json']=spec['prior_failed_control']['closure_sha256']
 assert sha(BASE/'studies/fullpass-driver-stage80-20261124/manifest.json')==spec['prior_failed_control']['private_archive_manifest_sha256']
 for p,d in ledgers.items():assert sha(p)==d
 assert memory()>=32*2**30;report['CPU_admission']=measure_compute_headroom(allowed_cpus,interval_seconds=5,count=4,minimum=.8);assert len(report['CPU_admission']['selected_cpus'])==4;os.sched_setaffinity(0,report['CPU_admission']['selected_cpus']);save()
 mf=BASE/'outputs/lora-training-stage51-20261123/model-manifest.json';assert sha(mf)==spec['model_manifest_sha256']
 for item in json.loads(mf.read_text())['files']:
  path=MODEL/item['path'];assert path.stat().st_size==item['bytes'];h=hashlib.sha256() if item['lfs_sha256'] else hashlib.sha1()
  if not item['lfs_sha256']:h.update(('blob '+str(item['bytes'])+'\0').encode())
  with path.open('rb') as f:
   while block:=f.read(2*1024*1024):h.update(block)
  assert h.hexdigest()==(item['lfs_sha256'] or item['git_blob_sha1'])
 with (OUT/(a.variant+'-watcher.log')).open('wb') as log:
  watcher=subprocess.Popen([str(CORE),str(OUT/'exec_gpu_child.py'),str(os.getpid()),str(parent_start),'cpu',str(CORE),str(OUT/'nvml_watch.py'),'--sdk',str(SDK),'--output',str(WORK/'telemetry.json'),'--uuid-sha',spec['expected_GPU_UUID_sha256'],'--index',str(spec['GPU_index']),'--seconds','1900'],cwd=WORK,env=dict(env,CUDA_VISIBLE_DEVICES=''),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
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
  report.update(status='waiting_for_pinned_idle_GPU',admission_wait_seconds=round(time.monotonic()-admission,3));save()
  if time.monotonic()-admission>=600:raise RuntimeError('No pinned idleGPU within600s;zero teacherforward dispatch')
  if memory()<32*2**30:raise RuntimeError('Host memory below admission')
  time.sleep(.5)
 report['fresh_CPU_admission']=measure_compute_headroom(allowed_cpus,interval_seconds=5,count=4,minimum=.8);assert len(report['fresh_CPU_admission']['selected_cpus'])==4;os.sched_setaffinity(0,report['fresh_CPU_admission']['selected_cpus']);save()
 fresh=wait_fresh(lastGPU['sequence']);assert eligible(fresh) and memory()>=32*2**30;lastGPU=fresh;output=WORK/'run';start=time.monotonic();peak=0;guard=None
 command=[str(PY),str(CODE/'benchmarks/train_fullpass_segment.py'),'--model',str(MODEL),'--source',str(CODE),'--data',str(DATA),'--masked',str(masked),'--schedule',str(CODE/spec['schedule_relative']),'--experiment',str(EXPERIMENT),'--spec',str(OUT/'protocol.json'),'--output',str(output),'--role',role,'--segment',str(segment)]
 with (OUT/(a.variant+'.log')).open('wb') as log,(OUT/(a.variant+'-monitor.jsonl')).open('w') as monitor:
  driver=subprocess.Popen([str(CORE),str(OUT/'exec_gpu_child.py'),str(os.getpid()),str(parent_start),'gpu',*command],cwd=CODE,env=dict(env,CUDA_VISIBLE_DEVICES=lastGPU['uuid']),stdout=log,stderr=subprocess.STDOUT,start_new_session=True);known[driver.pid]=start_ticks(driver.pid);report.update(status='running',driver_identity={'pid':driver.pid,'start_ticks':known[driver.pid]});save()
  while driver.poll() is None:
   now=time.monotonic();elapsed=now-start;owned=tree();rss=sum(v['rss'] for v in owned.values());peak=max(peak,rss);row={'elapsed_seconds':round(elapsed,3),'owned_RSS_bytes':rss,'available_memory_bytes':memory()}
   try:
    lastGPU,age=telemetry();foreign=classify_compute_pids(lastGPU['pids'],known)['foreign'];GPU_seen|=bool(set(lastGPU['pids'])&set(owned));row.update(GPU_used_MiB=lastGPU['used_MiB'],foreign_compute_processes=len(foreign),observation_age_seconds=round(age,3),telemetry_sequence=lastGPU['sequence'])
    if foreign:guard='foreign_compute_client'
    elif age>30:guard='GPU_telemetry_stale'
    elif lastGPU['used_MiB']>22528:guard='GPU_memory_limit'
   except BaseException as error:guard='GPU_monitor_unavailable';row['error_type']=type(error).__name__
   if elapsed>900:guard='training_segment_wall'
   elif now-began>1800:guard='controller_wall'
   elif rss>24*2**30:guard='owned_RSS'
   elif row['available_memory_bytes']<24*2**30:guard='host_memory_floor'
   state=json.loads((output/'report.json').read_text()) if (output/'report.json').exists() else {}
   if elapsed>300 and not state.get('model_loaded'):guard='model_load_watchdog'
   operation=json.loads((output/'current-operation.json').read_text()) if (output/'current-operation.json').exists() else {}
   if operation and time.time()-operation['started_unix']>300:guard='operation_watchdog'
   monitor.write(json.dumps(row)+'\n');monitor.flush()
   if guard:stop('model');break
   time.sleep(.5)
  rc=driver.wait();report['phases'].append({'variant':a.variant,'returncode':rc,'guard_reason':guard,'wall_seconds':round(time.monotonic()-start,3),'peak_sampled_owned_RSS_bytes':peak});save();print(json.dumps(report['phases'][-1]),flush=True)
 if rc or guard or tree('model'):raise RuntimeError('Training continuation control failed')
 result=json.loads((output/'report.json').read_text());assert result['status']=='completed' and result['inputs_and_sources_unchanged'] and result['frozen_parameters_unchanged'] and result['standard_sparse_canary']['RNG_unchanged']
 assert result['journal']['status']=='clean' and result['journal']['next_segment']==segment+1
 assert result['journal']['forward_reserved']-initial['forward_reserved']==plan['segments'][segment]['forwards']
 assert result['journal']['forward_completed']==result['journal']['forward_reserved'] and result['journal']['optimizer_completed']==result['journal']['optimizer_reserved']==plan['segments'][segment]['end']
 report.update(role_complete=True,neural_summary=result)
except BaseException as error:report['operator_error']={'type':type(error).__name__,'message':str(error)[:600]}
finally:
 report['model_shutdown']=stop('model');report['own_GPU_context_seen']=GPU_seen
 if watcher is None and driver is None:report['own_GPU_context_absent']=True
 if watcher is not None and watcher.poll() is None:
  try:
   sequence=lastGPU['sequence'] if lastGPU else 0;cleanup=time.monotonic()
   for _ in range(5):
    current=wait_fresh(sequence,timeout=10,after_monotonic=cleanup);sequence=current['sequence']
    if not set(current['pids'])&set(known):break
   report['own_GPU_context_absent']=not set(current['pids'])&set(known);report['GPU_after']=public(current)
  except BaseException as error:report['GPU_cleanup_observation_error']=type(error).__name__
 report['shutdown']=stop()
 try:
  progress=TrainingJournal(EXPERIMENT/role/'journal',definition);final=progress.snapshot();progress.close();report['final_journal']=final
  report['accounting']={'forward_reserved_delta':final['forward_reserved']-initial['forward_reserved'],'forward_completed_delta':final['forward_completed']-initial['forward_completed'],'forward_unknown_still_charged':final['forward_reserved']-final['forward_completed'],'backward_reserved_delta':final['backward_reserved']-initial['backward_reserved'],'optimizer_reserved_delta':final['optimizer_reserved']-initial['optimizer_reserved'],'optimizer_completed_delta':final['optimizer_completed']-initial['optimizer_completed'],'optimizer_unknown_still_charged':final['optimizer_reserved']-final['optimizer_completed']}
 except BaseException as error:report['journal_integrity_error']=type(error).__name__;report['role_complete']=False
 report['source_and_inputs_unchanged']=all(sha(CODE/n)==d for n,d in spec['source_sha256'].items()) and all(sha(DATA/n)==d for n,d in spec['data_sha256'].items())
 report['closed_ledgers_unchanged']=all(sha(p)==d for p,d in ledgers.items()) if 'ledgers' in globals() else False
 report.update(terminal=True,status='completed' if report.get('role_complete') else 'failed',wall_seconds=round(time.monotonic()-began,3));save();print(json.dumps({k:report.get(k) for k in ['terminal','status','variant','operator_error','accounting','own_GPU_context_absent','source_and_inputs_unchanged','closed_ledgers_unchanged','wall_seconds']}),flush=True)
raise SystemExit(0 if report.get('role_complete') and not report.get('operator_error') and not report['shutdown']['remaining_owned_processes'] and report.get('own_GPU_context_absent') and report['source_and_inputs_unchanged'] and report['closed_ledgers_unchanged'] else 2)
