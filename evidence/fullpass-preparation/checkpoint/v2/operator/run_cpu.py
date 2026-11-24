"""Frozen guarded BFCL scorer and admitted-ID reference binding on an authorized server."""
from pathlib import Path, PurePosixPath
import ast
import hashlib
import json
import os
import shutil
import signal
import subprocess
import tarfile
import tempfile
import time

OUT=Path(__file__).resolve().parent
spec=json.loads((OUT/'protocol.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (OUT/'run-report.json').exists()
assert sha(OUT/'run_cpu.py')==spec['controller_sha256'] and sha(OUT/'exec_child.py')==spec['wrapper_sha256']
assert sha(OUT/'cpu_admission.py')==spec['cpu_admission_sha256']
BASE=Path('[SERVER_WORKSPACE]');CORE=BASE/'envs/model-request-budget-20261121/bin/python';UV=BASE/'tools/uv-x86_64-unknown-linux-gnu/uv'
assert CORE.is_file() and UV.is_file()
os.umask(0o077);os.nice(19)
ROOT=Path(tempfile.mkdtemp(prefix='agentlab-fullpass-checkpoint-controls-stage79-'))
(OUT/'location.json').write_text(json.dumps({'root':str(ROOT)})+'\n')
parent_start=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19])
env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH'] and not k.endswith(('_KEY','_TOKEN','_SECRET'))}
env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',MKL_NUM_THREADS='2',TMPDIR=str(ROOT),XDG_CACHE_HOME=str(ROOT/'cache'),UV_CACHE_DIR=str(ROOT/'cache/uv'),UV_PYTHON_INSTALL_DIR=str(ROOT/'pythons'),UV_CONCURRENT_DOWNLOADS='4',UV_CONCURRENT_BUILDS='1',UV_CONCURRENT_INSTALLS='4',ANONYMIZED_TELEMETRY='false',BROWSER_USE_AUTO_LOGIN='0',PRE_COMMIT_HOME=str(ROOT/'cache/pre-commit'))
env['PATH']=str(UV.parent)+':'+str(CORE.parent)+':'+env.get('PATH','/usr/bin:/bin')
report={'terminal':False,'protocol_sha256':sha(OUT/'protocol.json'),'phases':[],'pretrained_model_forwards':0,'real_remote_credentials_used':False,'GPU_used':False,'CPU_affinity':sorted(os.sched_getaffinity(0))}
child=None;known={};began=time.monotonic()
memory=lambda:int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024

def save():
 tmp=OUT/'run-report.tmp';tmp.write_text(json.dumps(report,indent=2)+'\n');os.replace(tmp,OUT/'run-report.json')
def owned():
 rows={}
 for p in Path('/proc').glob('[0-9]*'):
  try:
   if p.stat().st_uid!=os.getuid():continue
   s=(p/'stat').read_text().rsplit(')',1)[1].split();rows[int(p.name)]={'parent':int(s[1]),'start':int(s[19]),'state':s[0],'rss':int(s[21])*os.sysconf('SC_PAGE_SIZE')}
  except (OSError,ValueError):pass
 ids={child.pid} if child is not None and child.poll() is None and child.pid in rows else set()
 ids.update(p for p,start in known.items() if p in rows and rows[p]['start']==start)
 for _ in range(24):
  old=len(ids);ids.update(p for p,v in rows.items() if v['parent'] in ids)
  if len(ids)==old:break
 ids={p for p in ids if rows[p]['state']!='Z'};known.update({p:rows[p]['start'] for p in ids})
 return {p:rows[p] for p in ids}
def stop():
 for sig in [signal.SIGTERM,signal.SIGKILL]:
  for pid,v in owned().items():
   if owned().get(pid,{}).get('start')==v['start']:
    try:os.kill(pid,sig)
    except ProcessLookupError:pass
  if child and child.poll() is None:
   try:child.wait(timeout=3)
   except subprocess.TimeoutExpired:pass
  if not owned():break

def run(name,command,cwd,cap=300,allowed=(0,)):
 global child
 env['PYTHONPATH']=str(cwd);env['GPTR_BLOCK_NETWORK']='1';env['TIKTOKEN_CACHE_DIR']=str(ROOT/'cache/tiktoken')
 report['active_phase']=name;save();start=time.monotonic();peak=0;guard=None
 argv=[str(CORE),str(OUT/'exec_child.py'),str(os.getpid()),str(parent_start),'cpu',*[str(x) for x in command]]
 with (OUT/(name+'.log')).open('wb') as log:
  child=subprocess.Popen(argv,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  while child.poll() is None:
   rss=sum(v['rss'] for v in owned().values());peak=max(peak,rss)
   if time.monotonic()-start>cap or time.monotonic()-began>900 or rss>4*2**30 or memory()<8*2**30 or shutil.disk_usage('/tmp').free<4*2**30:
    guard='phase/resource/job cap';stop();break
   time.sleep(.5)
  rc=child.wait()
 row={'name':name,'exit_code':rc,'guard':guard,'wall_seconds':round(time.monotonic()-start,3),'peak_owned_RSS_bytes':peak};report['phases'].append(row);save();print(json.dumps(row),flush=True)
 assert not guard and rc in allowed,name
 return rc


try:
 assert memory()>=16*2**30 and shutil.disk_usage('/tmp').free>=2*2**30
 from cpu_admission import measure_compute_headroom
 report['CPU_admission']=measure_compute_headroom(os.sched_getaffinity(0),interval_seconds=5,count=2,minimum=.8);save()
 assert len(report['CPU_admission']['selected_cpus'])==2;os.sched_setaffinity(0,report['CPU_admission']['selected_cpus']);report['CPU_affinity']=sorted(os.sched_getaffinity(0))
 assert sha(OUT/'input.tar.gz')==spec['input_bundle_sha256']
 code=ROOT/'source';code.mkdir()
 with tarfile.open(OUT/'input.tar.gz') as archive:
  for m in archive:
   p=PurePosixPath(m.name);assert m.isfile() and not p.is_absolute() and '..' not in p.parts
   target=code/m.name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(archive.extractfile(m).read())
 assert all(sha(code/n)==d for n,d in spec['source_sha256'].items())
 python=Path('[MODEL_RUNTIME]/runtime/bin/python')
 run('checkpoint-controls',[python,code/'extras/lora-training/test_training_checkpoint.py','-v'],code,120)
 log=(OUT/'checkpoint-controls.log').read_text();assert 'Ran 6 tests' in log
 numeric=json.loads(log.splitlines()[-1]);assert numeric=={'tiny_CPU_forward_calls':18,'tiny_CPU_optimizer_updates':18,'pretrained_model_forwards':0,'CUDA_initialized':False};report['actual_numeric_controls']=numeric
 assert all(sha(code/n)==d for n,d in spec['source_sha256'].items());report['inputs_and_sources_unchanged']=True;report['ready']=True
except BaseException as error:
 report['error']={'type':type(error).__name__,'message':str(error)[:500]}
finally:
 stop();report.update(terminal=True,owned_after=len(owned()),wall_seconds=round(time.monotonic()-began,3));save();print(json.dumps({k:report.get(k) for k in ['terminal','ready','error','actual_numeric_controls','owned_after','wall_seconds']}),flush=True)
raise SystemExit(0 if report.get('ready') and not report.get('error') and not report['owned_after'] else 2)
