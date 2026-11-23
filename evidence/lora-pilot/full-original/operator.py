from pathlib import Path
import csv,fcntl,hashlib,json,os,resource,signal,subprocess,tempfile,time
OUT=Path(__file__).resolve().parent;BASE=Path('/path/to/private-agent-lab');CORE=BASE/'envs/model-request-budget-20261121/bin/python';spec=json.loads((OUT/'train-protocol.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();assert not (OUT/'training-report.json').exists();assert sha(Path(__file__))==spec['operator_sha256'] and sha(OUT/'train_driver.py')==spec['driver_sha256'] and sha(OUT/'exec_child.py')==spec['wrapper_sha256'];assert resource.getrlimit(resource.RLIMIT_AS)==(-1,-1)
SETUP=BASE/'outputs/lora-training-stage51-20261123';ready=json.loads((SETUP/'setup-report.json').read_text());assert ready['terminal'] and ready['runtime_ready'] and not ready.get('operator_error') and ready['setup_protocol_sha256']==spec['setup_protocol_sha256'];ROOT=Path(json.loads((SETUP/'runtime-location.json').read_text())['local_root']);PY=ROOT/'runtime/bin/python';DATA=ROOT/'data';MODEL=ROOT/'model';identity=json.loads((SETUP/'CPU-runtime-identity.log').read_text());assert identity['peft']=='0.18.0' and identity['torch']=='2.6.0+cu124' and 'sm_86' in identity['compiled_arch_flags']
def streamsha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(2*1024*1024):h.update(b)
 return h.hexdigest()
for n,d in spec['data_sha256'].items():assert streamsha(DATA/n)==d,n
manifest=json.loads((SETUP/'model-manifest.json').read_text());assert sha(SETUP/'model-manifest.json')==spec['model_manifest_sha256']
for x in manifest['files']:
 p=MODEL/x['path'];h=hashlib.sha256() if x['lfs_sha256'] else hashlib.sha1();assert p.stat().st_size==x['bytes']
 if not x['lfs_sha256']:h.update(('blob '+str(x['bytes'])+'\0').encode())
 with p.open('rb') as f:
  while b:=f.read(2*1024*1024):h.update(b)
 assert h.hexdigest()==(x['lfs_sha256'] or x['git_blob_sha1'])
def memory():return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
assert memory()>=32*2**30
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:4]);os.nice(19);parent_start=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]);WORK=Path(tempfile.mkdtemp(prefix='agentlab-lora-training-stage51-'));WORK.chmod(0o700);mounts=[(x.split(' - ')[0].split()[4],x.split(' - ')[1].split()[0]) for x in Path('/proc/self/mountinfo').read_text().splitlines()];assert max([(len(p),f) for p,f in mounts if str(WORK).startswith(p.rstrip('/')+'/')])[1] in ['ext4','xfs','btrfs'];(OUT/'training-location.json').write_text(json.dumps({'local_root':str(WORK),'runtime_root':str(ROOT)})+'\n');(OUT/'training-location.json').chmod(0o600)
env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','HF_TOKEN','HUGGING_FACE_HUB_TOKEN','OPENAI_API_KEY','AGENT_LAB_EVIDENCE_KEY']};env.update(OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TMPDIR=str(WORK),HF_HOME=str(WORK/'hf-cache'),XDG_CACHE_HOME=str(WORK/'xdg-cache'),TORCH_HOME=str(WORK/'torch-cache'),CUDA_CACHE_PATH=str(WORK/'cuda-cache'))
report={'terminal':False,'protocol_sha256':sha(OUT/'train-protocol.json'),'driver_sha256':spec['driver_sha256'],'training_started':False,'GPU_work_started':False,'phases':[],'completed_variants':[]};began=time.monotonic();driver=None;known={};uuid=None;lock=None;GPU_seen=False;lastGPU=None;lastGPUat=0

def save():(OUT/'training-report.json').write_text(json.dumps(report,indent=2)+'\n')
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
def probe(g=None,timeout=5):
 def call(args):
  p=subprocess.run(['nvidia-smi']+(['--id='+g] if g else [])+args,capture_output=True,text=True,timeout=timeout);p.check_returncode();return list(csv.reader(p.stdout.splitlines(),skipinitialspace=True))
 cards=call(['--query-gpu=index,uuid,name,compute_cap,memory.total,memory.used,utilization.gpu','--format=csv,noheader,nounits']);ps=call(['--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits']);return [{'index':int(x[0]),'uuid':x[1],'name':x[2],'capability':x[3],'total_MiB':int(x[4]),'used_MiB':int(x[5]),'utilization':int(x[6]),'pids':[int(p[1]) for p in ps if p and p[0]==x[1]]} for x in cards]
def public(c):return {**{k:v for k,v in c.items() if k not in ['uuid','pids']},'UUID_sha256':hashlib.sha256(c['uuid'].encode()).hexdigest(),'compute_processes':len(c['pids'])}
def eligible(c):return '3090' in c['name'] and c['capability']=='8.6' and c['total_MiB']>=24000 and c['total_MiB']-c['used_MiB']>=23000 and c['utilization']<=5 and not c['pids']
save()
try:
 admission_started=time.monotonic()
 while True:
  try:
   first=probe(timeout=15);time.sleep(5);second=probe(timeout=15);a={c['uuid']:c for c in first if eligible(c)};choices=[c for c in second if eligible(c) and c['uuid'] in a];choices.sort(key=lambda c:(c['index']!=3,c['index']))
   for card in choices:
    candidate=card['uuid'];(BASE/'locks').mkdir(exist_ok=True);candidate_lock=(BASE/'locks'/('gpu-'+candidate+'.lock')).open('a')
    try:
     fcntl.flock(candidate_lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fresh=next(c for c in probe(candidate,timeout=15) if c['uuid']==candidate)
     if not eligible(fresh):candidate_lock.close();continue
     uuid=candidate;lock=candidate_lock;break
    except BaseException:candidate_lock.close();raise
   if uuid:
    assert memory()>=32*2**30;lastGPU=fresh;lastGPUat=time.monotonic();report.update(GPU=public(fresh),admission_samples=[public(a[uuid]),public(card)],status='running');save();break
  except (subprocess.TimeoutExpired,subprocess.CalledProcessError,BlockingIOError) as e:
   report.setdefault('admission_observation_errors',[]).append({'type':type(e).__name__,'elapsed_seconds':round(time.monotonic()-admission_started,3)})
  elapsed=time.monotonic()-admission_started;report.update(admission_wait_seconds=round(elapsed,3),status='waiting_for_idle_GPU_and_valid_telemetry');save()
  if elapsed>=600:raise RuntimeError('No eligible idle RTX3090 with valid telemetry within600s; no model started')
  time.sleep(10)
 for variant in ['train','mixed_train']:
  start=time.monotonic();guard=None;peak=0;lastprobe=0;output=WORK/variant;childenv=dict(env,CUDA_VISIBLE_DEVICES=uuid)
  with (OUT/(variant+'.log')).open('wb') as log,(OUT/(variant+'-monitor.jsonl')).open('w') as mon:
   driver=subprocess.Popen([str(CORE),str(OUT/'exec_child.py'),str(os.getpid()),str(parent_start),'gpu',str(PY),str(OUT/'train_driver.py'),'--model',str(MODEL),'--data',str(DATA),'--output',str(output),'--spec',str(OUT/'train-protocol.json'),'--variant',variant],cwd=WORK,env=childenv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);report['current_variant']=variant;save()
   while driver.poll() is None:
    now=time.monotonic();elapsed=now-start;owned=tree();rss=sum(x['rss'] for x in owned.values());peak=max(peak,rss);mem=memory();row={'elapsed_seconds':round(elapsed,3),'owned_RSS_bytes':rss,'available_memory_bytes':mem}
    if now-lastprobe>=2:
     try:lastGPU=next(c for c in probe(uuid) if c['uuid']==uuid);lastGPUat=time.monotonic()
     except Exception as e:report.setdefault('GPU_probe_errors',[]).append({'type':type(e).__name__,'elapsed_seconds':round(elapsed,3)})
     lastprobe=now
    foreign=set(lastGPU['pids'])-set(owned);GPU_seen|=bool(set(lastGPU['pids'])&set(owned));row.update(GPU_used_MiB=lastGPU['used_MiB'],foreign_compute_processes=len(foreign),own_GPU_context_seen=GPU_seen,observation_age_seconds=round(time.monotonic()-lastGPUat,3))
    if GPU_seen and not report['GPU_work_started']:report['GPU_work_started']=True;save()
    if foreign:guard='foreign_compute_client'
    elif lastGPU['used_MiB']>22528:guard='GPU_memory_limit'
    elif time.monotonic()-lastGPUat>30:guard='GPU_telemetry_stale'
    elif elapsed>1500:guard='variant_wall'
    elif now-began>3300:guard='job_wall'
    elif rss>24*2**30:guard='owned_RSS'
    elif mem<24*2**30:guard='host_memory_floor'
    state=json.loads((output/'report.json').read_text()) if (output/'report.json').exists() else {}
    if state.get('training_run') and not report['training_started']:report['training_started']=True;save()
    if elapsed>300 and not state.get('model_loaded'):guard='model_load_watchdog'
    op=json.loads((output/'current-operation.json').read_text()) if (output/'current-operation.json').exists() else None
    if op and time.time()-op['started_unix']>300:guard='operation_watchdog'
    mon.write(json.dumps(row)+'\n');mon.flush()
    if guard:stop();break
    time.sleep(.5)
   rc=driver.wait();report['phases'].append({'variant':variant,'returncode':rc,'guard_reason':guard,'wall_seconds':round(time.monotonic()-start,3),'peak_sampled_owned_RSS_bytes':peak});save();print(json.dumps(report['phases'][-1]),flush=True)
  if rc or guard or tree():raise RuntimeError('Training variant failed: '+variant)
  result=json.loads((output/'report.json').read_text());assert result['status']=='completed' and result['completed_optimizer_updates']==32 and result['completed_training_labels']==65536 and result['frozen_parameters_unchanged'] and result['adapter_reload_verified'];report['completed_variants'].append(variant);save();driver=None
 results={v:json.loads((WORK/v/'report.json').read_text()) for v in ['train','mixed_train']};f,m=results.values();assert f['initial_adapter_sha256']==m['initial_adapter_sha256'] and f['initial_frozen_parameters_sha256']==m['initial_frozen_parameters_sha256'];assert abs(f['before_dev']['token_weighted_NLL']-m['before_dev']['token_weighted_NLL'])<1e-3 and abs(f['before_val']['token_weighted_NLL']-m['before_val']['token_weighted_NLL'])<1e-3;report['paired_initial_state_matched']=True;report['complete_comparison']=True
except BaseException as e:report['operator_error']={'type':type(e).__name__,'message':str(e)}
finally:
 report['shutdown']=stop();report['own_GPU_context_seen']=GPU_seen
 if uuid:
  try:
   for _ in range(10):
    c=next(c for c in probe(uuid) if c['uuid']==uuid)
    if not set(c['pids'])&set(known):break
    time.sleep(.5)
   report['own_GPU_context_absent']=not set(c['pids'])&set(known);report['GPU_after']=public(c)
  except Exception as e:report['GPU_cleanup_observation_error']=type(e).__name__
 summaries={}
 for v in ['train','mixed_train']:
  p=WORK/v/'events.jsonl';events=[];bad=0
  if p.exists():
   for line in p.read_text().splitlines():
    try:events.append(json.loads(line))
    except json.JSONDecodeError:bad+=1
  counts={n:sum(x['event']==n for x in events) for n in ['forward_reserved','forward_completed','backward_completed','optimizer_update_reserved','optimizer_update_completed','checkpoint_committed']};counts['forward_unknown_still_charged']=counts['forward_reserved']-counts['forward_completed'];counts['optimizer_update_unknown_still_charged']=counts['optimizer_update_reserved']-counts['optimizer_update_completed'];counts['malformed_journal_lines']=bad;summaries[v]=counts
 report.update(terminal=True,status='completed' if report.get('complete_comparison') else 'failed',ledgers=summaries,source_and_inputs_unchanged=sha(OUT/'train_driver.py')==spec['driver_sha256'] and sha(OUT/'exec_child.py')==spec['wrapper_sha256'] and all(streamsha(DATA/n)==d for n,d in spec['data_sha256'].items()),wall_seconds=round(time.monotonic()-began,3));save();print(json.dumps(report),flush=True)
raise SystemExit(0 if report.get('complete_comparison') and not report.get('operator_error') and not report['shutdown']['remaining_owned_processes'] and report.get('own_GPU_context_absent') and report['source_and_inputs_unchanged'] else 2)
