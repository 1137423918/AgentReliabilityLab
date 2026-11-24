"""Actual process kill after durable collect checkpoints; no neural/provider work."""
from pathlib import Path
import hashlib,json,os,signal,subprocess,sys,time
CODE=Path(sys.argv[1]);OUT=Path(sys.argv[2]);OUT.mkdir(mode=0o700,exist_ok=False);PY=sys.executable
root=CODE/'evidence/dependency-upgrade/corpus';manifest=root/'catalog.json';compat=CODE/'examples/dependency-workbench/compatibility.json';reference=OUT/'reference';interrupted=OUT/'interrupted'
def run(name,args):
 with (OUT/(name+'.log')).open('wb') as log:r=subprocess.run(args,cwd=CODE,stdout=log,stderr=subprocess.STDOUT,timeout=45)
 assert r.returncode==0,name
run('reference',[PY,'-m','agent_lab.review_workbench','--root',str(root),'--manifest',str(manifest),'--compatibility-manifest',str(compat),'--run-dir',str(reference)])
ready=OUT/'ready.json'
child_code='''from pathlib import Path
import json,os,sys,time
from agent_lab.review_workbench import run_workbench
r=run_workbench(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]),compatibility_manifest=Path(sys.argv[4]),_interrupt_after=['collect'])
assert not r['completed'] and len(r['pending'])==2
p=Path(sys.argv[5]);q=p.with_suffix('.tmp')
with q.open('w') as f:json.dump(r,f);f.flush();os.fsync(f.fileno())
os.replace(q,p)
while True:time.sleep(1)
'''
process=None;start_ticks=None
try:
 with (OUT/'interrupted.log').open('wb') as log:
  process=subprocess.Popen([PY,'-c',child_code,str(root),str(manifest),str(interrupted),str(compat),str(ready)],cwd=CODE,stdout=log,stderr=subprocess.STDOUT)
  stat=Path('/proc')/str(process.pid)/'stat';start_ticks=int(stat.read_text().rsplit(')',1)[1].split()[19]);deadline=time.monotonic()+45
  while not ready.exists():
   assert process.poll() is None,'child exited before persisted checkpoint marker'
   assert time.monotonic()<deadline,'checkpoint marker timeout';time.sleep(.1)
  assert int(stat.read_text().rsplit(')',1)[1].split()[19])==start_ticks
  os.kill(process.pid,signal.SIGKILL);assert process.wait(timeout=10)==-signal.SIGKILL
 restart='''from pathlib import Path
from unittest.mock import patch
from agent_lab.evidence_audit import EvidenceCatalog
from agent_lab.review_workbench import run_workbench
import json,sys
with patch.object(EvidenceCatalog,'read_report',side_effect=RuntimeError('completed read reran after process death')):
 r=run_workbench(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]),compatibility_manifest=Path(sys.argv[4]))
assert r['completed'] and r['reports']==2 and r['model_calls']==0
print(json.dumps(r))
'''
 run('new-process-resume',[PY,'-c',restart,str(root),str(manifest),str(interrupted),str(compat)])
 paths=['summary.md','reviews/browser_use_1_0_8.json','reviews/browser_use_1_0_8.md','reviews/fastmcp_2_12_4.json','reviews/fastmcp_2_12_4.md']
 hashes={}
 for name in paths:
  a=(reference/name).read_bytes();b=(interrupted/name).read_bytes();assert a==b,name;hashes[name]=hashlib.sha256(a).hexdigest()
 report={'passed':True,'scope':'SIGKILL after bothcollectnodes committed;newPythonprocess resumes without rereading reports. Not activeSQLitewrite/powerloss/hostileprocess test.', 'actual_child_exit_code':-9,'same_review_and_batch_markdown_bytes':hashes,'new_process_read_reexecution_rejected':True,'reports':2,'model_calls':0,'GPU_used':False,'only_owned_child_signaled':True}
 (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
finally:
 if process is not None and process.poll() is None:
  p=Path('/proc')/str(process.pid)/'stat'
  if p.exists() and int(p.read_text().rsplit(')',1)[1].split()[19])==start_ticks:
   process.kill();process.wait(timeout=10)
