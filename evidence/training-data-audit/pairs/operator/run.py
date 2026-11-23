from pathlib import Path
import hashlib,json,os,resource,shutil,signal,subprocess,tempfile,time,ctypes
OUT=Path(__file__).resolve().parent;BASE=Path('<SERVER_BASE>');spec=json.loads((OUT/'protocol.json').read_text());assert not (OUT/'run-report.json').exists();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();assert sha(Path(__file__))==spec['operator_sha256'] and sha(OUT/'prepare.py')==spec['source_sha256']
old=BASE/'outputs/training-audit-stage47-v1-20261123';prior=json.loads((old/'run-report.json').read_text());assert prior['terminal'] and prior['audit_completed'] and prior['source_files_unchanged']
ROOT=Path(json.loads((old/'control-location.json').read_text())['local_root']);PY=ROOT/'runtime/bin/python'
def available():return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
assert available()>=12*2**30
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:4]);os.nice(19);resource.setrlimit(resource.RLIMIT_AS,(8*2**30,8*2**30));WORK=Path(tempfile.mkdtemp(prefix='agentlab-training-pairs-stage47-'));WORK.chmod(0o700);(OUT/'control-location.json').write_text(json.dumps({'local_root':str(WORK)})+'\n');(OUT/'control-location.json').chmod(0o600);(WORK/'input').mkdir()
mounts=[(x.split(' - ')[0].split()[4],x.split(' - ')[1].split()[0]) for x in Path('/proc/self/mountinfo').read_text().splitlines()];fstype=max([(len(p),f) for p,f in mounts if str(WORK).startswith(p.rstrip('/')+'/')])[1];assert fstype in ['ext4','xfs','btrfs']
for n,d in spec['input_sha256'].items():
 src=ROOT/'upstream/training/data'/n;assert sha(src)==d;shutil.copyfile(src,WORK/'input'/n);assert sha(WORK/'input'/n)==d
shutil.copyfile(OUT/'prepare.py',WORK/'prepare.py')
report={'terminal':False,'protocol_sha256':sha(OUT/'protocol.json'),'operator_sha256':sha(Path(__file__)),'source_sha256':sha(WORK/'prepare.py'),'filesystem':fstype,'model_inference':False,'training_run':False,'GPU_work_started':False};start=time.monotonic();peak=0;guard=None
def save():(OUT/'run-report.json').write_text(json.dumps(report,indent=2)+'\n')
save();env=dict(os.environ);env.pop('PYTHONPATH',None);env.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTHONDONTWRITEBYTECODE='1')
def pdeath():
 ctypes.CDLL(None).prctl(1,signal.SIGTERM)
 if os.getppid()==1:os._exit(2)
with (OUT/'prepare.log').open('wb') as log,(OUT/'monitor.jsonl').open('w') as mon:
 child=subprocess.Popen([str(PY),str(WORK/'prepare.py'),'--source',str(WORK/'input'),'--output',str(WORK/'prepared')],cwd=WORK,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=pdeath)
 while child.poll() is None:
  elapsed=time.monotonic()-start
  try:rss=int(next(x.split()[1] for x in Path(f'/proc/{child.pid}/status').read_text().splitlines() if x.startswith('VmRSS:')))*1024
  except (FileNotFoundError,StopIteration):rss=0
  peak=max(peak,rss);mem=available();mon.write(json.dumps({'elapsed_seconds':round(elapsed,3),'RSS_bytes':rss,'available_memory_bytes':mem})+'\n');mon.flush()
  if elapsed>180 or rss>4*2**30 or mem<8*2**30:
   guard='wall' if elapsed>180 else 'RSS' if rss>4*2**30 else 'memory_floor';child.terminate();break
  time.sleep(.2)
 try:rc=child.wait(timeout=10)
 except subprocess.TimeoutExpired:child.kill();rc=child.wait(timeout=5)
unchanged=all(sha(WORK/'input'/n)==d and sha(ROOT/'upstream/training/data'/n)==d for n,d in spec['input_sha256'].items()) and sha(WORK/'prepare.py')==spec['source_sha256'];report.update(terminal=True,returncode=rc,guard_reason=guard,wall_seconds=round(time.monotonic()-start,3),peak_sampled_RSS_bytes=peak,input_and_source_unchanged=unchanged,child_reaped=child.poll() is not None);save();print(json.dumps(report),flush=True)
raise SystemExit(0 if rc==0 and not guard and unchanged else 2)
