from pathlib import Path
import ctypes,hashlib,importlib.metadata,json,os,resource,signal,subprocess,tempfile,time,tarfile,shutil
OUT=Path(__file__).resolve().parent;BASE=Path('/authorized/agent-lab');CORE=BASE/'envs/model-request-budget-20261121/bin/python';spec=json.loads((OUT/'protocol.json').read_text());assert not (OUT/'run-report.json').exists();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();assert sha(Path(__file__))==spec['operator_sha256'] and sha(OUT/'source.tar.gz')==spec['source_archive_sha256']
def memory():return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
assert memory()>=24*2**30 and shutil.disk_usage('/tmp').free>=30*2**30 and os.getloadavg()[0]<len(os.sched_getaffinity(0))*.9
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:4]);os.nice(19);resource.setrlimit(resource.RLIMIT_AS,(32*2**30,32*2**30));WORK=Path(tempfile.mkdtemp(prefix='agentlab-neural-bootstrap-stage49-'));WORK.chmod(0o700);(OUT/'control-location.json').write_text(json.dumps({'local_root':str(WORK)})+'\n');(OUT/'control-location.json').chmod(0o600)
mounts=[(x.split(' - ')[0].split()[4],x.split(' - ')[1].split()[0]) for x in Path('/proc/self/mountinfo').read_text().splitlines()];fstype=max([(len(p),f) for p,f in mounts if str(WORK).startswith(p.rstrip('/')+'/')])[1];assert fstype in ['ext4','xfs','btrfs']
with tarfile.open(OUT/'source.tar.gz') as t:t.extractall(WORK,filter='data')
for n,d in spec['source_files_sha256'].items():assert sha(WORK/n)==d,n
(WORK/'pip-cache').mkdir();(WORK/'model-cache').mkdir();versions=lambda:sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions());before=versions()
env={k:v for k,v in os.environ.items() if not k.startswith('PIP_') and k not in ['PYTHONPATH','LD_PRELOAD','OPENAI_API_KEY','AGENT_LAB_EVIDENCE_KEY','HF_TOKEN','HUGGING_FACE_HUB_TOKEN']};env.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1',PIP_INDEX_URL='https://pypi.org/simple',PIP_CONFIG_FILE='/dev/null',PIP_CACHE_DIR=str(WORK/'pip-cache'),PIP_DISABLE_PIP_VERSION_CHECK='1',HF_HOME=str(WORK/'model-cache'))
model_target=BASE/'models/Qwen2.5-3B-Instruct-aa8e7253-stage49-v1';assert not model_target.exists();report={'terminal':False,'protocol_sha256':sha(OUT/'protocol.json'),'source_archive_sha256':sha(OUT/'source.tar.gz'),'operator_sha256':sha(Path(__file__)),'filesystem':fstype,'GPU_work_started':False,'model_loaded':False,'training_run':False,'phases':[]};job_started=time.monotonic();active=[];known={}
def save():(OUT/'run-report.json').write_text(json.dumps(report,indent=2)+'\n')
def tree():
 rows={}
 for p in Path('/proc').glob('[0-9]*'):
  try:
   if p.stat().st_uid!=os.getuid():continue
   a=(p/'stat').read_text().rsplit(')',1)[1].split();rows[int(p.name)]={'ppid':int(a[1]),'start':int(a[19]),'state':a[0],'rss':next((int(x.split()[1])*1024 for x in (p/'status').read_text().splitlines() if x.startswith('VmRSS:')),0)}
  except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 ids={p.pid for p in active if p.poll() is None and p.pid in rows};ids.update(p for p,start in known.items() if p in rows and rows[p]['start']==start)
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
  for pid,row in owned.items():
   if tree().get(pid,{}).get('start')==row['start']:
    try:os.kill(pid,sig)
    except ProcessLookupError:pass
  end=time.monotonic()+cap
  while time.monotonic()<end and tree():time.sleep(.2)
 for p in active:
  try:p.wait(timeout=3)
  except subprocess.TimeoutExpired:pass
 return {'forced_cleanup':forced,'remaining_owned_processes':list(tree())}
def pdeath():
 ctypes.CDLL(None).prctl(1,signal.SIGTERM)
 if os.getppid()==1:os._exit(2)
def run_group(jobs):
 global active
 started=time.monotonic();active=[];rows=[];logs=[];guard=None;peak=0
 for name,args,cap in jobs:
  f=(OUT/(name+'.log')).open('wb');logs.append(f);p=subprocess.Popen([str(x) for x in args],cwd=WORK,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=pdeath);active.append(p);rows.append({'phase':name,'cap':cap,'process':p,'end':None})
 with (OUT/(jobs[0][0]+'-group-monitor.jsonl')).open('w') as mon:
  while True:
   now=time.monotonic();elapsed=now-started;owned=tree();rss=sum(r['rss'] for r in owned.values());peak=max(peak,rss);mem=memory();mon.write(json.dumps({'elapsed_seconds':round(elapsed,3),'owned_tree_RSS_bytes':rss,'available_memory_bytes':mem})+'\n');mon.flush()
   for r in rows:
    if r['process'].poll() is not None and r['end'] is None:r['end']=now
   if all(r['end'] is not None for r in rows):break
   if any(r['process'].poll() not in [None,0] for r in rows):guard='peer_phase_failed'
   elif any(elapsed>r['cap'] and r['end'] is None for r in rows):guard='phase_wall'
   elif now-job_started>2400:guard='job_wall'
   elif rss>8*2**30:guard='owned_RSS'
   elif mem<16*2**30:guard='memory_floor'
   elif shutil.disk_usage(WORK).free<8*2**30:guard='disk_floor'
   if guard:stop_owned();break
   time.sleep(.5)
 for r in rows:
  p=r['process'];p.wait(timeout=3);row={'phase':r['phase'],'returncode':p.returncode,'guard_reason':guard,'wall_seconds':round((r['end'] or time.monotonic())-started,3),'peak_sampled_group_tree_RSS_bytes':peak};report['phases'].append(row);print(json.dumps(row),flush=True)
 for f in logs:f.close()
 save()
 if guard or any(p.returncode!=0 for p in active) or tree():raise RuntimeError('Bootstrap phase did not finish cleanly')
 active=[]
def run(name,args,cap):run_group([(name,args,cap)])
save()
try:
 run('isolated-venv',[CORE,'-m','venv',WORK/'runtime'],120);PY=WORK/'runtime/bin/python';pip=spec['pip_wheel'];run('pinned-installer',[PY,'-m','pip','install','--no-deps',pip['url']+'#sha256='+pip['sha256']],120)
 run_group([('resolve-runtime',[PY,'-m','pip','install','--dry-run','--ignore-installed','--only-binary=:all:','--report',WORK/'resolve.json','-r',WORK/'requirements.in'],1200),('download-model',[CORE,WORK/'download_model.py',WORK/'model-manifest.json',model_target],1200)])
 run('freeze-resolved-lock',[CORE,WORK/'make_lock.py',WORK],30)
 run('install-frozen-runtime',[PY,'-m','pip','install','--no-deps','--require-hashes','--report',WORK/'installed.json','-r',WORK/'requirements.lock'],600)
 run('runtime-integrity',[PY,'-m','pip','check'],60)
 identity="""import hashlib,importlib.metadata as m,json,torch,transformers,accelerate,openai,pyarrow,psutil
from pathlib import Path
assert torch.__version__=='2.6.0+cu124' and torch.version.cuda=='12.4';flags=torch._C._cuda_getArchFlags();assert 'sm_60' in flags
from transformers.models.qwen2.modeling_qwen2 import Qwen2ForCausalLM
import inspect
print(json.dumps({'versions':{d.metadata['Name']:d.version for d in m.distributions()},'torch':torch.__version__,'CUDA_build':torch.version.cuda,'compiled_arch_flags':flags,'Qwen2ForCausalLM_imported':True,'module_source_sha256':{o.__name__:hashlib.sha256(Path(inspect.getfile(o)).read_bytes()).hexdigest() for o in [Qwen2ForCausalLM]},'GPU_model_started':False}))
"""
 run('CPU-runtime-identity',[PY,'-c',identity],180)
 validated=json.loads((model_target/'agentlab-validated.json').read_text());assert validated['all_files_verified'] and validated['revision']==spec['model_revision'];report['model_artifacts_verified']=True;report['runtime_ready_CPU_identity']=True
except BaseException as e:report['operator_error']={'type':type(e).__name__,'message':str(e)}
finally:
 report['shutdown']=stop_owned();report.update(terminal=True,source_files_unchanged=all(sha(WORK/n)==d for n,d in spec['source_files_sha256'].items()),core_distribution_pairs_unchanged=before==versions(),wall_seconds=round(time.monotonic()-job_started,3));save();print(json.dumps({'terminal':True,'runtime_ready':report.get('runtime_ready_CPU_identity',False),'model_artifacts_verified':report.get('model_artifacts_verified',False),'operator_error':report.get('operator_error'),'owned_after':len(report['shutdown']['remaining_owned_processes'])}),flush=True)
raise SystemExit(0 if report.get('runtime_ready_CPU_identity') and not report.get('operator_error') and report['source_files_unchanged'] and report['core_distribution_pairs_unchanged'] and not report['shutdown']['remaining_owned_processes'] else 2)
