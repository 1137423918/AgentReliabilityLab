from pathlib import Path
import csv,fcntl,hashlib,json,os,resource,signal,socket,subprocess,tempfile,time
OUT=Path(__file__).resolve().parent;BASE=Path('/authorized/agent-lab');CORE=BASE/'envs/model-request-budget-20261121/bin/python';spec=json.loads((OUT/'protocol.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();assert not (OUT/'run-report.json').exists();assert sha(Path(__file__))==spec['operator_sha256'] and sha(OUT/'driver.py')==spec['driver_sha256'] and sha(OUT/'exec_child.py')==spec['wrapper_sha256'];assert resource.getrlimit(resource.RLIMIT_AS)==(-1,-1)
boot=BASE/'outputs/neural-bootstrap-stage49-v1-20261123';BOOT=Path(json.loads((boot/'control-location.json').read_text())['local_root']);runtime=BASE/'outputs/neural-runtime-stage49-v2-20261123';r=json.loads((runtime/'run-report.json').read_text());assert r['terminal'] and r['runtime_ready_CPU_identity'] and not r.get('operator_error');PY=BOOT/'runtime/bin/python';identity=json.loads((runtime/'CPU-runtime-identity.log').read_text());assert identity['torch']=='2.6.0+cu124' and 'sm_60' in identity['compiled_arch_flags']
ingest=BASE/'outputs/neural-model-ingest-stage49-v2-20261123';r=json.loads((ingest/'run-report.json').read_text());assert r['terminal'] and r['all_artifacts_verified'] and r['shared_cache_copy_verified'];MODEL=Path(json.loads((ingest/'control-location.json').read_text())['model_root']);manifest=json.loads((BOOT/'model-manifest.json').read_text());assert manifest['revision']==spec['model_revision']
UP=BOOT/'upstream';WORK=Path(tempfile.mkdtemp(prefix='agentlab-neural-clean-stage49-'));WORK.chmod(0o700);(OUT/'control-location.json').write_text(json.dumps({'local_root':str(WORK)})+'\n');(OUT/'control-location.json').chmod(0o600);mounts=[(x.split(' - ')[0].split()[4],x.split(' - ')[1].split()[0]) for x in Path('/proc/self/mountinfo').read_text().splitlines()];assert max([(len(p),f) for p,f in mounts if str(WORK).startswith(p.rstrip('/')+'/')])[1] in ['ext4','xfs','btrfs']
def memory():return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
assert memory()>=24*2**30
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:4]);os.nice(19);parent_start=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]);env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','OPENAI_API_KEY','HF_TOKEN','HUGGING_FACE_HUB_TOKEN','AGENT_LAB_EVIDENCE_KEY']};env.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TMPDIR=str(WORK))
for var,n in [('HF_HOME','hf-cache'),('TORCH_HOME','torch-cache'),('XDG_CACHE_HOME','xdg-cache'),('CUDA_CACHE_PATH','cuda-cache')]:
 p=WORK/n;p.mkdir();env[var]=str(p)
report={'terminal':False,'protocol_sha256':sha(OUT/'protocol.json'),'operator_sha256':sha(Path(__file__)),'driver_sha256':sha(OUT/'driver.py'),'model_started':False,'GPU_work_started':False,'training_run':False,'declared_cases':199,'phases':[]};job_started=time.monotonic();driver=None;known={};gpu_uuid=None;gpu_last=None;gpu_last_at=0;GPU_seen=False;lock=None
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
def stop_owned():
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
def probe(uuid=None):
 def call(args):
  p=subprocess.run(['nvidia-smi']+(['--id='+uuid] if uuid else [])+args,capture_output=True,text=True,timeout=5);p.check_returncode();return list(csv.reader(p.stdout.splitlines(),skipinitialspace=True))
 cards=call(['--query-gpu=index,uuid,name,compute_cap,memory.total,memory.used,utilization.gpu','--format=csv,noheader,nounits']);ps=call(['--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits']);return [{'index':int(x[0]),'uuid':x[1],'name':x[2],'capability':x[3],'total_MiB':int(x[4]),'used_MiB':int(x[5]),'utilization':int(x[6]),'pids':[int(p[1]) for p in ps if p and p[0]==x[1]]} for x in cards]
def public(c):return {**{k:v for k,v in c.items() if k not in ['uuid','pids']},'UUID_sha256':hashlib.sha256(c['uuid'].encode()).hexdigest(),'compute_processes':len(c['pids'])}
def eligible(c):return c['index']==3 and c['capability']=='6.0' and c['total_MiB']>=16000 and c['total_MiB']-c['used_MiB']>=15000 and c['utilization']<=5 and not c['pids']
def run(name,args,cap,gpu=False):
 global driver,gpu_last,gpu_last_at,GPU_seen
 began=time.monotonic();guard=None;peak=0;last_probe=0;child_env=dict(env)
 if gpu:child_env['CUDA_VISIBLE_DEVICES']=gpu_uuid
 with (OUT/(name+'.log')).open('wb') as log,(OUT/(name+'-monitor.jsonl')).open('w') as monitor:
  driver=subprocess.Popen([str(CORE),str(OUT/'exec_child.py'),str(os.getpid()),str(parent_start),'gpu' if gpu else 'cpu',*[str(x) for x in args]],cwd=WORK,env=child_env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  if gpu:report['neural_driver_started']=True;save()
  while driver.poll() is None:
   now=time.monotonic();elapsed=now-began;owned=tree();rss=sum(r['rss'] for r in owned.values());peak=max(peak,rss);mem=memory();row={'elapsed_seconds':round(elapsed,3),'owned_RSS_bytes':rss,'available_memory_bytes':mem}
   if gpu and now-last_probe>=2:
    try:gpu_last=next(x for x in probe(gpu_uuid) if x['uuid']==gpu_uuid);gpu_last_at=time.monotonic()
    except Exception as e:report.setdefault('GPU_probe_errors',[]).append({'elapsed_seconds':round(elapsed,3),'type':type(e).__name__})
    last_probe=now
   if gpu and gpu_last:
    foreign=set(gpu_last['pids'])-set(owned);GPU_seen|=bool(set(gpu_last['pids'])&set(owned));row.update(GPU_used_MiB=gpu_last['used_MiB'],foreign_compute_processes=len(foreign),own_GPU_context_seen=GPU_seen,observation_age_seconds=round(time.monotonic()-gpu_last_at,3))
    if foreign:guard='foreign_compute_client'
    elif gpu_last['used_MiB']>14336:guard='GPU_memory_limit'
    elif time.monotonic()-gpu_last_at>30:guard='GPU_observation_stale'
   if elapsed>cap:guard='phase_wall'
   elif now-job_started>3000:guard='job_wall'
   elif mem<16*2**30:guard='host_memory_floor'
   elif rss>(24 if gpu else 8)*2**30:guard='owned_RSS'
   if gpu:
    call=WORK/'run/current-call.json'
    if call.exists():
     state=json.loads(call.read_text())
     if state.get('status')=='generating' and time.time()-state['started_unix']>180:guard='single_call_watchdog'
    status=WORK/'run/report.json'
    model_status=json.loads(status.read_text()) if status.exists() else {}
    if model_status.get('model_parameter_count') and model_status.get('status') in ['running','completed']:
     report['model_started']=True;report['model_loaded']=True
    report['GPU_work_started']=GPU_seen
    if elapsed>300 and (not model_status or model_status.get('status')=='starting'):guard='model_load_watchdog'
   monitor.write(json.dumps(row)+'\n');monitor.flush()
   if guard:stop_owned();break
   time.sleep(.5)
  rc=driver.wait();row={'phase':name,'returncode':rc,'guard_reason':guard,'wall_seconds':round(time.monotonic()-began,3),'peak_sampled_owned_RSS_bytes':peak};report['phases'].append(row);save();print(json.dumps(row),flush=True)
 if rc or guard or tree():raise RuntimeError('Phase failed: '+name)
 driver=None
save()
try:
 check="""from pathlib import Path
import hashlib,json,sys
manifest=json.loads(Path(sys.argv[1]).read_text());root=Path(sys.argv[2]);rows=[]
for x in manifest['files']:
 p=root/x['path'];h=hashlib.sha256() if x['lfs_sha256'] else hashlib.sha1()
 if not x['lfs_sha256']:h.update(('blob '+str(x['bytes'])+'\\0').encode())
 with p.open('rb') as f:
  while b:=f.read(2*1024*1024):h.update(b)
 assert p.stat().st_size==x['bytes'] and h.hexdigest()==(x['lfs_sha256'] or x['git_blob_sha1']),x['path']
 rows.append(x['path'])
print(json.dumps({'verified_model_files':len(rows),'bytes':sum(x['bytes'] for x in manifest['files'])}))
"""
 run('model-identity',[CORE,'-c',check,BOOT/'model-manifest.json',MODEL],180)
 for n,d in spec['upstream_source_sha256'].items():assert sha(UP/n)==d,n
 run('tokenizer-admission',[PY,OUT/'driver.py','prepare','--upstream',UP,'--model',MODEL,'--output',WORK/'admission.json','--max-context','32768','--max-tokens','1024'],180)
 admission=json.loads((WORK/'admission.json').read_text());assert admission['all_within_context'] and admission['case_count']==199;report['token_admission']={k:admission[k] for k in ['case_count','max_input_tokens','max_context','max_new_tokens']};save()
 first=next(c for c in probe() if c['index']==3);time.sleep(5);second=next(c for c in probe() if c['index']==3);assert eligible(first) and eligible(second) and first['uuid']==second['uuid'],'No eligible idle P100';gpu_uuid=second['uuid'];(BASE/'locks').mkdir(exist_ok=True);lock=(BASE/'locks'/('gpu-'+gpu_uuid+'.lock')).open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);fresh=next(c for c in probe(gpu_uuid) if c['uuid']==gpu_uuid);assert eligible(fresh);gpu_last=fresh;gpu_last_at=time.monotonic()
 report.update(GPU=public(fresh),admission_snapshots=[public(first),public(second)]);save();print(json.dumps({'neural_driver_launch_next':True,'device':fresh['name'],'cases':199,'dtype':'float16'}),flush=True)
 run('neural-clean199',[PY,OUT/'driver.py','run','--upstream',UP,'--model',MODEL,'--output',WORK/'run','--admission',WORK/'admission.json','--max-context','32768','--max-tokens','1024'],2400,gpu=True)
 result=json.loads((WORK/'run/report.json').read_text());assert result['status']=='completed' and result['completed_cases']==result['model_calls']==199 and GPU_seen;report['all_cases_completed']=True;report['neural_summary']={k:result[k] for k in ['completed_cases','model_calls','input_tokens','generated_token_ids','scores','required_key_violation_cases','truncated_or_soft_time_stopped']}
except BaseException as error:report['operator_error']={'type':type(error).__name__,'message':str(error)}
finally:
 report['shutdown']=stop_owned();report['own_GPU_compute_seen']=GPU_seen
 if gpu_uuid:
  try:c=next(x for x in probe(gpu_uuid) if x['uuid']==gpu_uuid);report['own_GPU_context_absent']=not set(c['pids'])&set(known);report['GPU_after']=public(c)
  except Exception as error:report['GPU_cleanup_observation_error']=type(error).__name__
 journal=WORK/'run/calls.jsonl'
 if journal.exists():
  events=[json.loads(x) for x in journal.read_text().splitlines()];reserved=[x for x in events if x['event']=='reserved'];completed=[x for x in events if x['event']=='completed'];report['local_generation_ledger']={'reserved':len(reserved),'completed':len(completed),'unknown_still_charged':len(reserved)-len(completed)};report['neural_generation_attempted']=bool(reserved);report['neural_generation_completed']=bool(completed)
 report.update(terminal=True,driver_and_wrapper_unchanged=sha(OUT/'driver.py')==spec['driver_sha256'] and sha(OUT/'exec_child.py')==spec['wrapper_sha256'],upstream_sources_unchanged=all(sha(UP/n)==d for n,d in spec['upstream_source_sha256'].items()),wall_seconds=round(time.monotonic()-job_started,3));save();print(json.dumps({'terminal':True,'all_cases_completed':report.get('all_cases_completed',False),'model_started':report['model_started'],'operator_error':report.get('operator_error'),'ledger':report.get('local_generation_ledger'),'owned_after':len(report['shutdown']['remaining_owned_processes']),'own_GPU_context_absent':report.get('own_GPU_context_absent')}),flush=True)
raise SystemExit(0 if report.get('all_cases_completed') and not report.get('operator_error') and not report['shutdown']['remaining_owned_processes'] and report.get('own_GPU_context_absent') and report['driver_and_wrapper_unchanged'] and report['upstream_sources_unchanged'] else 2)
