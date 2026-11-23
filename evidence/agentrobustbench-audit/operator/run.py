from pathlib import Path
import ctypes,hashlib,json,os,resource,signal,subprocess,tempfile,time,tarfile
OUT=Path(__file__).resolve().parent
spec=json.loads((OUT/'protocol.json').read_text())
assert not (OUT/'run-report.json').exists()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(OUT/'source.tar.gz')==spec['source_archive_sha256']
WORK=Path(tempfile.mkdtemp(prefix='agentlab-robust-audit-stage46-'));WORK.chmod(0o700)
(OUT/'control-location.json').write_text(json.dumps({'local_root':str(WORK)})+'\n')
(OUT/'control-location.json').chmod(0o600)
mounts=[(x.split(' - ')[0].split()[4],x.split(' - ')[1].split()[0]) for x in Path('/proc/self/mountinfo').read_text().splitlines()]
fstype=max([(len(p),f) for p,f in mounts if str(WORK).startswith(p.rstrip('/')+'/')])[1]
assert fstype in ['ext4','xfs','btrfs']
def available():return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
assert available()>=12*2**30
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:4]);os.nice(19);resource.setrlimit(resource.RLIMIT_AS,(8*2**30,8*2**30))
with tarfile.open(OUT/'source.tar.gz') as t:t.extractall(WORK,filter='data')
for n,d in spec['source_sha256'].items():assert sha(WORK/n)==d,n
def parent_death():
 ctypes.CDLL(None).prctl(1,signal.SIGTERM)
 if os.getppid()==1:os._exit(2)
start=time.monotonic();guard=None;peak=0
report={'terminal':False,'protocol_sha256':sha(OUT/'protocol.json'),'source_archive_sha256':sha(OUT/'source.tar.gz'),'operator_sha256':sha(Path(__file__)),'filesystem':fstype,'GPU_used':False,'model_inference':False,'training_run':False}
def save(): (OUT/'run-report.json').write_text(json.dumps(report,indent=2)+'\n')
save()
env=dict(os.environ);env.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1');env.pop('PYTHONPATH',None)
with (OUT/'audit.log').open('wb') as log,(OUT/'monitor.jsonl').open('w') as monitor:
 child=subprocess.Popen(['<SERVER_BASE>/envs/model-request-budget-20261121/bin/python',str(WORK/'audit_agentrobustbench.py'),'--source',str(WORK/'upstream'),'--output',str(WORK/'results')],cwd=WORK,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=parent_death)
 while child.poll() is None:
  elapsed=time.monotonic()-start
  try:rss=int(next(x.split()[1] for x in Path(f'/proc/{child.pid}/status').read_text().splitlines() if x.startswith('VmRSS:')))*1024
  except (FileNotFoundError,StopIteration):rss=0
  peak=max(peak,rss);memory=available();monitor.write(json.dumps({'elapsed_seconds':round(elapsed,3),'RSS_bytes':rss,'available_memory_bytes':memory})+'\n');monitor.flush()
  if elapsed>180 or rss>4*2**30 or memory<8*2**30:
   guard='wall' if elapsed>180 else 'RSS' if rss>4*2**30 else 'host_memory_floor';child.terminate();break
  time.sleep(.2)
 try:rc=child.wait(timeout=10)
 except subprocess.TimeoutExpired:child.kill();rc=child.wait(timeout=5)
report.update(terminal=True,returncode=rc,guard_reason=guard,wall_seconds=round(time.monotonic()-start,3),peak_sampled_child_RSS_bytes=peak,source_files_unchanged=all(sha(WORK/n)==d for n,d in spec['source_sha256'].items()),child_reaped=child.poll() is not None)
save();print(json.dumps(report),flush=True)
raise SystemExit(0 if rc==0 and not guard and report['source_files_unchanged'] else 2)
