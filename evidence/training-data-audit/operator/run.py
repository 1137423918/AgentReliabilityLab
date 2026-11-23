from pathlib import Path
import ctypes,hashlib,importlib.metadata,json,os,resource,signal,subprocess,tempfile,time,tarfile,urllib.request
OUT=Path(__file__).resolve().parent;spec=json.loads((OUT/'protocol.json').read_text());assert not (OUT/'run-report.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(Path(__file__))==spec['operator_sha256'] and sha(OUT/'source.tar.gz')==spec['source_archive_sha256']
CORE=Path('<SERVER_BASE>/envs/model-request-budget-20261121/bin/python')
def available():return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
assert available()>=12*2**30
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:4]);os.nice(19);resource.setrlimit(resource.RLIMIT_AS,(8*2**30,8*2**30))
WORK=Path(tempfile.mkdtemp(prefix='agentlab-training-audit-stage47-'));WORK.chmod(0o700);(OUT/'control-location.json').write_text(json.dumps({'local_root':str(WORK)})+'\n');(OUT/'control-location.json').chmod(0o600)
mounts=[(x.split(' - ')[0].split()[4],x.split(' - ')[1].split()[0]) for x in Path('/proc/self/mountinfo').read_text().splitlines()];fstype=max([(len(p),f) for p,f in mounts if str(WORK).startswith(p.rstrip('/')+'/')])[1];assert fstype in ['ext4','xfs','btrfs']
with tarfile.open(OUT/'source.tar.gz') as t:t.extractall(WORK,filter='data')
for n,d in spec['source_files_sha256'].items():assert sha(WORK/n)==d,n
versions=lambda:sorted((d.metadata['Name'],d.version) for d in importlib.metadata.distributions())
before=versions();env=dict(os.environ);env.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1',PIP_DISABLE_PIP_VERSION_CHECK='1');env.pop('PYTHONPATH',None)
report={'terminal':False,'protocol_sha256':sha(OUT/'protocol.json'),'source_archive_sha256':sha(OUT/'source.tar.gz'),'operator_sha256':sha(Path(__file__)),'filesystem':fstype,'GPU_work_started':False,'model_inference':False,'training_run':False,'phases':[]};job_started=time.monotonic();child=None
def save():(OUT/'run-report.json').write_text(json.dumps(report,indent=2)+'\n')
def pdeath():
 ctypes.CDLL(None).prctl(1,signal.SIGTERM)
 if os.getppid()==1:os._exit(2)
def owned_tree(root):
 rows={}
 for p in Path('/proc').glob('[0-9]*'):
  try:
   if p.stat().st_uid!=os.getuid():continue
   s=(p/'stat').read_text().rsplit(')',1)[1].split();rows[int(p.name)]={'ppid':int(s[1]),'state':s[0],'start':int(s[19]),'rss':next((int(l.split()[1])*1024 for l in (p/'status').read_text().splitlines() if l.startswith('VmRSS:')),0)}
  except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 keep={root} if root in rows else set()
 for _ in range(16):
  old=len(keep);keep.update(pid for pid,r in rows.items() if r['ppid'] in keep)
  if len(keep)==old:break
 return {p:rows[p] for p in keep if rows[p]['state']!='Z'}
def run(name,args,cap):
 global child
 start=time.monotonic();guard=None;peak=0;known={}
 with (OUT/(name+'.log')).open('wb') as log,(OUT/(name+'-monitor.jsonl')).open('w') as mon:
  child=subprocess.Popen([str(x) for x in args],cwd=WORK,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=pdeath)
  while child.poll() is None:
   tree=owned_tree(child.pid);known.update({p:r['start'] for p,r in tree.items()});rss=sum(r['rss'] for r in tree.values());peak=max(peak,rss);elapsed=time.monotonic()-start;mem=available();mon.write(json.dumps({'elapsed_seconds':round(elapsed,3),'tree_RSS_bytes':rss,'available_memory_bytes':mem})+'\n');mon.flush()
   if elapsed>cap or time.monotonic()-job_started>900 or rss>4*2**30 or mem<8*2**30:
    guard='phase_wall' if elapsed>cap else 'job_wall' if time.monotonic()-job_started>900 else 'RSS' if rss>4*2**30 else 'memory_floor'
    child.terminate();break
   time.sleep(.3)
  try:rc=child.wait(timeout=10)
  except subprocess.TimeoutExpired:child.kill();rc=child.wait(timeout=5)
  remaining=owned_tree(child.pid)
  if remaining:
   for pid,r in remaining.items():
    if known.get(pid)==r['start']:
     try:os.kill(pid,signal.SIGTERM)
     except ProcessLookupError:pass
  row={'phase':name,'returncode':rc,'guard_reason':guard,'wall_seconds':round(time.monotonic()-start,3),'peak_sampled_tree_RSS_bytes':peak,'remaining_observed_owned_processes':list(owned_tree(child.pid))};report['phases'].append(row);save();child=None;print(json.dumps(row),flush=True)
  if rc or guard or row['remaining_observed_owned_processes']:raise RuntimeError('Phase failed: '+name)
save()
try:
 download_code="""import hashlib,json,time,urllib.request
from pathlib import Path
s=json.loads(Path('wheel.json').read_text());p=Path(s['filename']);started=time.monotonic();h=hashlib.sha256();size=0
with urllib.request.urlopen(s['url'],timeout=30) as r,p.open('wb') as f:
 while block:=r.read(1024*1024):
  if time.monotonic()-started>240:raise TimeoutError('Download deadline')
  size+=len(block)
  if size>s['bytes']:raise ValueError('Unexpected download length')
  h.update(block);f.write(block)
assert size==s['bytes'] and h.hexdigest()==s['sha256']
print(json.dumps({'bytes':size,'sha256':h.hexdigest()}))
"""
 (WORK/'wheel.json').write_text(json.dumps(spec['pyarrow_wheel'])+'\n')
 run('download-pinned-wheel',[CORE,'-c',download_code],270)
 run('new-isolated-venv',[CORE,'-m','venv',WORK/'runtime'],120)
 py=WORK/'runtime/bin/python';wheel=WORK/spec['pyarrow_wheel']['filename']
 run('install-pinned-wheel',[py,'-m','pip','install','--no-index','--no-deps',wheel],120)
 run('installed-integrity',[py,'-m','pip','check'],30)
 run('audit-training-parquets',[py,WORK/'audit_toolrl_training.py','--source',WORK/'upstream','--output',WORK/'results'],180)
 report['audit_completed']=True
except BaseException as error:report['operator_error']={'type':type(error).__name__,'message':str(error)}
finally:
 if child is not None and child.poll() is None:
  child.terminate()
  try:child.wait(timeout=10)
  except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
 report.update(terminal=True,source_files_unchanged=all(sha(WORK/n)==d for n,d in spec['source_files_sha256'].items()),core_distribution_pairs_unchanged=before==versions(),wall_seconds=round(time.monotonic()-job_started,3),owned_processes_after=list(owned_tree(os.getpid())))
 report['owned_processes_after']=[p for p in report['owned_processes_after'] if p!=os.getpid()];save();print(json.dumps({'terminal':True,'audit_completed':report.get('audit_completed',False),'operator_error':report.get('operator_error'),'source_files_unchanged':report['source_files_unchanged'],'core_distribution_pairs_unchanged':report['core_distribution_pairs_unchanged'],'owned_after':len(report['owned_processes_after'])}),flush=True)
raise SystemExit(0 if report.get('audit_completed') and not report.get('operator_error') and report['source_files_unchanged'] and report['core_distribution_pairs_unchanged'] and not report['owned_processes_after'] else 2)
