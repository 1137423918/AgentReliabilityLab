"""Real CPU process controls for stale telemetry at the child-exit boundary."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile
from gpu_ownership import start_ticks,classify_compute_pids

OUT=Path(__file__).resolve().parent
spec=json.loads((OUT/'ownership-test-protocol.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(Path(__file__))==spec['test_source_sha256']
assert sha(OUT/'gpu_ownership.py')==spec['ownership_source_sha256']
assert not (OUT/'ownership-test-report.json').exists()
children=[];cases=[]
try:
 for _ in range(2):children.append(subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']))
 own,other=children;known={own.pid:start_ticks(own.pid)}
 assert classify_compute_pids([own.pid],known)=={'foreign':[],'cached_exited_owned':[]};cases.append('live_owned_start_identity')
 assert classify_compute_pids([other.pid],known)['foreign']==[other.pid];cases.append('unrelated_live_process_is_foreign')
 wrong={own.pid:known[own.pid]+1};assert classify_compute_pids([own.pid],wrong)['foreign']==[own.pid];cases.append('mismatched_start_identity_is_foreign')
 old_foreign=set([own.pid])-set();assert old_foreign=={own.pid}
 own.terminate();own.wait(timeout=5);assert not (Path('/proc')/str(own.pid)).exists()
 assert classify_compute_pids([own.pid],known)=={'foreign':[],'cached_exited_owned':[own.pid]};cases.append('cached_exited_owned_process_is_not_foreign')
 assert classify_compute_pids([own.pid,other.pid],known)=={'foreign':[other.pid],'cached_exited_owned':[own.pid]};cases.append('cached_exit_does_not_hide_unrelated_process')
 assert other.poll() is None;cases.append('unrelated_process_left_running_by_classifier')
 report={'terminal':True,'passed':True,'cases':cases,'old_set_difference_misclassifies_exited_owned_PID':True,'no_model_or_GPU_or_training':True,'source_sha256':spec['ownership_source_sha256'],'test_source_sha256':spec['test_source_sha256']}
finally:
 for p in children:
  if p.poll() is None:p.terminate()
  p.wait(timeout=5)
report['owned_after']=0
(OUT/'ownership-test-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
