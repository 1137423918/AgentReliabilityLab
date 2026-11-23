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
ROOT=Path(tempfile.mkdtemp(prefix='agentlab-fastmcp-compat-stage77-v2-'))
(OUT/'location.json').write_text(json.dumps({'root':str(ROOT)})+'\n')
parent_start=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19])
env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH'] and not k.endswith(('_KEY','_TOKEN','_SECRET'))}
env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',PYTHONUNBUFFERED='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2',MKL_NUM_THREADS='2',TMPDIR=str(ROOT),XDG_CACHE_HOME=str(ROOT/'cache'),UV_CACHE_DIR=str(ROOT/'cache/uv'),UV_PYTHON_INSTALL_DIR=str(ROOT/'pythons'),UV_CONCURRENT_DOWNLOADS='4',UV_CONCURRENT_BUILDS='1',UV_CONCURRENT_INSTALLS='4',ANONYMIZED_TELEMETRY='false',BROWSER_USE_AUTO_LOGIN='0',PRE_COMMIT_HOME=str(ROOT/'cache/pre-commit'))
env['PATH']=str(UV.parent)+':'+str(CORE.parent)+':'+env.get('PATH','/usr/bin:/bin')
report={'terminal':False,'protocol_sha256':sha(OUT/'protocol.json'),'phases':[],'neural_calls':0,'real_remote_credentials_used':False,'GPU_used':False,'CPU_affinity':sorted(os.sched_getaffinity(0))}
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
 env['PYTHONPATH']=str(OUT/'test-harness');env['GPTR_BLOCK_NETWORK']='1';env['TIKTOKEN_CACHE_DIR']=str(ROOT/'cache/tiktoken')
 report['active_phase']=name;save();start=time.monotonic();peak=0;guard=None
 argv=[str(CORE),str(OUT/'exec_child.py'),str(os.getpid()),str(parent_start),'cpu',*[str(x) for x in command]]
 with (OUT/(name+'.log')).open('wb') as log:
  child=subprocess.Popen(argv,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  while child.poll() is None:
   rss=sum(v['rss'] for v in owned().values());peak=max(peak,rss)
   if time.monotonic()-start>cap or time.monotonic()-began>2400 or rss>8*2**30 or memory()<24*2**30 or shutil.disk_usage('/tmp').free<4*2**30:
    guard='phase/resource/job cap';stop();break
   time.sleep(.5)
  rc=child.wait()
 row={'name':name,'exit_code':rc,'guard':guard,'wall_seconds':round(time.monotonic()-start,3),'peak_owned_RSS_bytes':peak};report['phases'].append(row);save();print(json.dumps(row),flush=True)
 assert not guard and rc in allowed,name
 return rc

try:
 assert all(sha(OUT/name)==expected for name,expected in spec['harness_sha256'].items())
 assert memory()>=32*2**30 and shutil.disk_usage('/tmp').free>=8*2**30
 from cpu_admission import measure_compute_headroom
 report['CPU_admission']=measure_compute_headroom(os.sched_getaffinity(0),interval_seconds=5,count=2,minimum=.8);save()
 assert len(report['CPU_admission']['selected_cpus'])==2;os.sched_setaffinity(0,report['CPU_admission']['selected_cpus']);report['CPU_affinity']=sorted(os.sched_getaffinity(0))
 parent=Path(spec['candidate_source']);assert sha(parent/'uv.lock')==spec['candidate_lock_sha256'] and sha(parent/'pyproject.toml')==spec['pyproject_sha256']
 assert subprocess.check_output(['git','-C',str(parent),'rev-parse','HEAD'],text=True).strip()==spec['commit']
 assert subprocess.check_output(['git','-C',str(parent),'diff','--name-only'],text=True).splitlines()==['uv.lock']
 assert not subprocess.check_output(['git','-C',str(parent),'diff','--cached','--name-only'],text=True).strip()
 env.update(UV_PYTHON_DOWNLOADS='never',UV_CONCURRENT_DOWNLOADS='4',UV_CONCURRENT_BUILDS='1',UV_CONCURRENT_INSTALLS='2',UV_CACHE_DIR=str(ROOT/'uv-cache'),UV_NO_PROGRESS='1')
 python=Path('[MODEL_RUNTIME]/runtime/bin/python')
 reports={}
 for role in ['baseline','candidate']:
  env.pop('COMPAT_REPORT_ROOT',None)
  project=ROOT/role
  run(role+'-clone',[shutil.which('git'),'clone','--quiet','--local','--no-hardlinks',parent,project],ROOT,90)
  run(role+'-checkout',[shutil.which('git'),'-C',project,'checkout','--quiet','--detach',spec['commit']],ROOT,30)
  assert subprocess.check_output(['git','-C',str(project),'rev-parse','HEAD'],text=True).strip()==spec['commit']
  assert sha(project/'pyproject.toml')==spec['pyproject_sha256']
  if role=='candidate':shutil.copyfile(parent/'uv.lock',project/'uv.lock')
  assert sha(project/'uv.lock')==spec[role+'_lock_sha256']
  tracked=subprocess.check_output(['git','-C',str(project),'ls-files'],text=True).splitlines()
  before={name:sha(project/name) for name in tracked}
  env['UV_PROJECT_ENVIRONMENT']=str(project/'.venv')
  run(role+'-install',[UV,'sync','--frozen','--all-extras','--python',python],project,900)
  py=project/'.venv/bin/python'
  identity="import importlib.metadata as m,json;print(json.dumps({p.metadata['Name'].lower():p.version for p in m.distributions()},sort_keys=True))"
  run(role+'-versions',[py,'-c',identity],project,60)
  versions=json.loads((OUT/(role+'-versions.log')).read_text());assert versions['authlib']==spec['authlib_versions'][role]
  env['COMPAT_REPORT_ROOT']=str(ROOT/(role+'-test-report'))
  Path(env['COMPAT_REPORT_ROOT']).mkdir()
  code=run(role+'-auth-tests',[py,'-m','pytest','-p','compat_plugin','-m','not integration and not client_process','--junitxml='+str(ROOT/(role+'-tests.xml')),*spec['test_paths']],project,600,allowed=(0,1,2,3,4,5))
  after={name:sha(project/name) for name in tracked};assert after==before,'Upstream tracked files changed'
  ids=Path(env['COMPAT_REPORT_ROOT'])/'collection.json';outcomes=Path(env['COMPAT_REPORT_ROOT'])/'outcomes.jsonl'
  reports[role]={'pytest_exit_code':code,'versions':versions,'lock_sha256':sha(project/'uv.lock'),'tracked_source_tree_sha256':hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),'tracked_sources_unchanged':True,'collection':json.loads(ids.read_text()) if ids.exists() else None,'outcomes':[json.loads(line) for line in outcomes.read_text().splitlines()] if outcomes.exists() else []}
  save()
 assert sha(parent/'uv.lock')==spec['candidate_lock_sha256'] and sha(parent/'pyproject.toml')==spec['pyproject_sha256']
 assert reports['baseline']['collection']==reports['candidate']['collection'],'Selected test node IDs differ'
 summary={'commit':spec['commit'],'protocol_sha256':sha(OUT/'protocol.json'),'arms':reports,'same_collection':True,'no_source_or_test_edits':True,'test_network_policy':'External TCP/UDP connects denied during tests; loopback permitted, installation may access registries.','scope':'Historical FastMCP2.12.4 upstream auth/client auth/HTTP auth suite; not full repository CI, security proof, deployment approval or neural evaluation.'}
 (ROOT/'report.json').write_text(json.dumps(summary,indent=2)+'\n')
 report['compatibility_summary']={role:{'pytest_exit_code':reports[role]['pytest_exit_code'],'collected':len(reports[role]['collection'] or []),'authlib':reports[role]['versions']['authlib']} for role in reports}
 report['inputs_and_sources_unchanged']=True;report['ready']=True
except BaseException as error:
 report['error']={'type':type(error).__name__,'message':str(error)[:500]}
finally:
 stop();report.update(terminal=True,owned_after=len(owned()),wall_seconds=round(time.monotonic()-began,3));save();print(json.dumps({k:report.get(k) for k in ['terminal','ready','error','owned_after','wall_seconds','inputs_and_sources_unchanged','compatibility_summary']}),flush=True)
raise SystemExit(0 if report.get('ready') and not report.get('error') and not report['owned_after'] else 2)
