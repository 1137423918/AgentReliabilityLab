from pathlib import Path,PurePosixPath
import ctypes,hashlib,importlib.metadata,json,os,resource,shutil,signal,subprocess,tarfile,tempfile,time,urllib.request
OUT=Path(__file__).resolve().parent;BASE=Path('/path/to/private-agent-lab');CORE=BASE/'envs/model-request-budget-20261121/bin/python';spec=json.loads((OUT/'setup-protocol.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (OUT/'setup-report.json').exists();assert sha(Path(__file__))==spec['setup_operator_sha256'];archive=json.loads((OUT/'archive-report.json').read_text());assert archive['terminal'] and archive['operator_sha256']==spec['archive_operator_sha256']
def streamsha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(2*1024*1024):h.update(b)
 return h.hexdigest()
def memory():return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
assert memory()>=32*2**30 and shutil.disk_usage('/tmp').free>=40*2**30
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:4]);os.nice(19);resource.setrlimit(resource.RLIMIT_AS,(32*2**30,32*2**30));signal.alarm(1800)
ROOT=Path(tempfile.mkdtemp(prefix='agentlab-lora-runtime-stage51-'));ROOT.chmod(0o700);mounts=[(x.split(' - ')[0].split()[4],x.split(' - ')[1].split()[0]) for x in Path('/proc/self/mountinfo').read_text().splitlines()];fs=max([(len(p),f) for p,f in mounts if str(ROOT).startswith(p.rstrip('/')+'/')])[1];assert fs in ['ext4','xfs','btrfs'];(OUT/'runtime-location.json').write_text(json.dumps({'local_root':str(ROOT)})+'\n');(OUT/'runtime-location.json').chmod(0o600)
versions=lambda:sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions());before=versions();env={k:v for k,v in os.environ.items() if not k.startswith('PIP_') and k not in ['PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','HF_TOKEN','HUGGING_FACE_HUB_TOKEN','OPENAI_API_KEY','AGENT_LAB_EVIDENCE_KEY']};env.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1',PIP_CONFIG_FILE='/dev/null',PIP_DISABLE_PIP_VERSION_CHECK='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TMPDIR=str(ROOT))
def alarm_handler(signum,frame):raise TimeoutError('Setup wall alarm')
signal.signal(signal.SIGALRM,alarm_handler)
def pdeath():
 ctypes.CDLL(None).prctl(1,signal.SIGTERM)
 if os.getppid()==1:os._exit(2)
report={'terminal':False,'setup_protocol_sha256':sha(OUT/'setup-protocol.json'),'operator_sha256':sha(Path(__file__)),'GPU_or_model_or_training':False,'phases':[]};began=time.monotonic();active=None

def save():(OUT/'setup-report.json').write_text(json.dumps(report,indent=2)+'\n')
def run(name,args,cap):
 global active
 start=time.monotonic()
 with (OUT/(name+'.log')).open('wb') as log:
  active=subprocess.Popen([str(x) for x in args],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,preexec_fn=pdeath)
  try:rc=active.wait(timeout=cap)
  except subprocess.TimeoutExpired:
   active.terminate()
   try:active.wait(timeout=10)
   except subprocess.TimeoutExpired:active.kill();active.wait(timeout=3)
   raise
 report['phases'].append({'phase':name,'returncode':rc,'wall_seconds':round(time.monotonic()-start,3)});save();assert rc==0,name;active=None

def extract(name,dest,manifest):
 staged=ROOT/('staged-'+name);h=hashlib.sha256()
 with (OUT/name).open('rb') as source,staged.open('xb') as target:
  while b:=source.read(4*1024*1024):target.write(b);h.update(b)
 assert staged.stat().st_size==archive['archives'][name]['bytes']
 expected=archive['archives'][name]['sha256']
 if expected is not None:assert h.hexdigest()==expected
 report.setdefault('staged_container_sha256',{})[name]=h.hexdigest();save();dest.mkdir(parents=True,exist_ok=True)
 with tarfile.open(staged,'r:') as t:
  for m in t:
   p=PurePosixPath(m.name);assert not p.is_absolute() and '..' not in p.parts and m.isfile();q=dest/m.name;q.parent.mkdir(parents=True,exist_ok=True)
   with t.extractfile(m) as source,q.open('wb') as f:shutil.copyfileobj(source,f,2*1024*1024)
   q.chmod(m.mode&0o777)
 for e in manifest['files']:assert (dest/e['path']).stat().st_size==e['bytes'] and streamsha(dest/e['path'])==e['sha256'] and (dest/e['path']).stat().st_mode&0o777==e['mode']
 assert {str(p.relative_to(dest)) for p in dest.rglob('*') if p.is_file()}=={e['path'] for e in manifest['files']}
 staged.unlink()
save()
try:
 PY=ROOT/'runtime/bin/python';run('new-venv',[CORE,'-m','venv','--without-pip',ROOT/'runtime'],60)
 assert sha(OUT/'site-manifest.json')==archive['archives']['site-manifest.json']['sha256'];site=json.loads((OUT/'site-manifest.json').read_text());extract('baseline-site.tar',ROOT/'runtime/lib/python3.11/site-packages',site);report['all_cloned_runtime_files_verified']=len(site['files']);save()
 assert sha(OUT/'data-manifest.json')==archive['archives']['data-manifest.json']['sha256'];data=json.loads((OUT/'data-manifest.json').read_text());extract('prepared-data.tar',ROOT/'data',data);report['all_copied_data_files_verified']=len(data['files']);save()
 model=json.loads((OUT/'model-manifest.json').read_text());assert sha(OUT/'model-manifest.json')==spec['model_manifest_sha256'];CACHE=BASE/'models/Qwen2.5-3B-Instruct-aa8e7253-stage49-v1';MODEL=ROOT/'model';MODEL.mkdir()
 for x in model['files']:
  p=CACHE/x['path'];q=MODEL/x['path'];assert p.stat().st_size==x['bytes'];shutil.copyfile(p,q)
  h=hashlib.sha256() if x['lfs_sha256'] else hashlib.sha1()
  if not x['lfs_sha256']:h.update(('blob '+str(x['bytes'])+'\0').encode())
  with q.open('rb') as f:
   while b:=f.read(2*1024*1024):h.update(b)
  assert h.hexdigest()==(x['lfs_sha256'] or x['git_blob_sha1'])
 report['all_model_files_verified']=11;save()
 assert sha(OUT/'peft-wheel.json')==spec['peft_metadata_sha256'];wheel=json.loads((OUT/'peft-wheel.json').read_text());w=ROOT/wheel['filename']
 with urllib.request.urlopen(wheel['url'],timeout=40) as source,w.open('wb') as f:shutil.copyfileobj(source,f)
 assert w.stat().st_size==wheel['bytes'] and sha(w)==wheel['sha256']
 run('install-pinned-peft',[PY,'-m','pip','install','--no-index','--no-deps',w],120);run('pip-check',[PY,'-m','pip','check'],60)
 code="""import importlib.metadata as m,inspect,json,sys,torch,transformers,peft
from pathlib import Path
from transformers.models.qwen2.modeling_qwen2 import Qwen2ForCausalLM
from peft import LoraConfig,get_peft_model
assert torch.__version__=='2.6.0+cu124' and transformers.__version__=='4.57.6' and peft.__version__=='0.18.0'
assert 'sm_86' in torch._C._cuda_getArchFlags() and Path(inspect.getfile(peft)).is_relative_to(Path(sys.prefix))
print(json.dumps({'python':sys.version.split()[0],'prefix':sys.prefix,'packages':{d.metadata['Name']:d.version for d in m.distributions()},'torch':torch.__version__,'CUDA':torch.version.cuda,'compiled_arch_flags':torch._C._cuda_getArchFlags(),'peft':peft.__version__,'GPU_model_started':False}))
"""
 run('CPU-runtime-identity',[PY,'-c',code],120);report['runtime_ready']=True
except BaseException as e:report['operator_error']={'type':type(e).__name__,'message':str(e)}
finally:
 if active is not None and active.poll() is None:active.terminate();active.wait(timeout=10)
 report.update(terminal=True,core_distribution_pairs_unchanged=before==versions(),owned_child_reaped=active is None or active.poll() is not None,wall_seconds=round(time.monotonic()-began,3));save();print(json.dumps(report),flush=True)
raise SystemExit(0 if report.get('runtime_ready') and not report.get('operator_error') and report['core_distribution_pairs_unchanged'] and report['owned_child_reaped'] else 2)
