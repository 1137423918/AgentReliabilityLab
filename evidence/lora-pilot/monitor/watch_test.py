from pathlib import Path
import hashlib,json,os,subprocess,tempfile,time
OUT=Path(__file__).resolve().parent;spec=json.loads((OUT/'watch-test-protocol.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();assert not (OUT/'watch-test-report.json').exists();assert sha(Path(__file__))==spec['operator_sha256'];assert sha(OUT/'nvml_watch.py')==spec['watcher_sha256'];assert sha(OUT/'exec_child.py')==spec['wrapper_sha256'];CORE='/path/to/private-agent-lab/envs/model-request-budget-20261121/bin/python';sdk=Path(json.loads(Path('/path/to/private-agent-lab/outputs/lora-nvml-stage51-20261123/monitor-location.json').read_text())['local_root'])/'sdk';ROOT=Path(tempfile.mkdtemp(prefix='agentlab-nvml-watch-test-stage51-'));ROOT.chmod(0o700);start=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]);samples=[];began=time.monotonic();child=None;report={'terminal':False,'protocol_sha256':sha(OUT/'watch-test-protocol.json'),'no_model_or_training':True}
try:
 with (OUT/'watcher.log').open('wb') as log:
  child=subprocess.Popen([CORE,str(OUT/'exec_child.py'),str(os.getpid()),str(start),'cpu',CORE,str(OUT/'nvml_watch.py'),'--sdk',str(sdk),'--output',str(ROOT/'telemetry.json'),'--uuid-sha',spec['expected_GPU_UUID_sha256'],'--seconds','16'],stdout=log,stderr=subprocess.STDOUT)
  while child.poll() is None:
   p=ROOT/'telemetry.json'
   if p.exists():
    r=json.loads(p.read_text());assert r['watcher_pid']==child.pid;assert hashlib.sha256(r['uuid'].encode()).hexdigest()==spec['expected_GPU_UUID_sha256']
    if not samples or r['sequence']!=samples[-1]['sequence']:samples.append(r)
   if time.monotonic()-began>40:raise TimeoutError('watcher test40s')
   time.sleep(.25)
  assert child.wait()==0;assert len(samples)>=4;assert all(x['sample_seconds']<2 for x in samples);assert all(0<=b['observed_monotonic']-a['observed_monotonic']<5 for a,b in zip(samples,samples[1:]));report.update(test_passed=True,samples=samples,source_unchanged=sha(OUT/'nvml_watch.py')==spec['watcher_sha256'])
except BaseException as e:report['error']={'type':type(e).__name__,'message':str(e)}
finally:
 if child and child.poll() is None:
  child.terminate()
  try:child.wait(timeout=5)
  except subprocess.TimeoutExpired:child.kill();child.wait()
 report.update(terminal=True,watcher_returncode=child.returncode if child else None,wall_seconds=round(time.monotonic()-began,3),owned_after=0 if not child or child.poll() is not None else 1);(OUT/'watch-test-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='samples'}),flush=True)
raise SystemExit(0 if report.get('test_passed') and report['owned_after']==0 else 2)
