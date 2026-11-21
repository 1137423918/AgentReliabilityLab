from pathlib import Path
import hashlib,json,os,resource,signal,subprocess,tarfile,tempfile,time

OUT=Path(__file__).resolve().parent
BASE=Path('__SERVER_BASE__')
spec=json.loads((OUT/'protocol.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(Path(__file__))==spec['operator_sha256']
assert sha(OUT/'source.tar.gz')==spec['archive_sha256']
assert not (OUT/'run-report.json').exists()
affinity=sorted(os.sched_getaffinity(0));assert len(affinity)>=4
os.sched_setaffinity(0,affinity[:4]);os.nice(19)
resource.setrlimit(resource.RLIMIT_AS,(32*2**30,32*2**30))
available=lambda:next(int(x.split()[1])*1024 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))
assert available()>=12*2**30
ROOT=Path(tempfile.mkdtemp(prefix='agentlab-mcp-cleanup-stage43-'))
CODE=ROOT/'code';CODE.mkdir()
(OUT/'control-location.json').write_text(json.dumps({'local_root':str(ROOT)})+'\n')
(OUT/'control-location.json').chmod(0o600)
with tarfile.open(OUT/'source.tar.gz') as t:t.extractall(CODE,filter='data')
for name,expected in spec['source_files_sha256'].items():assert sha(CODE/name)==expected,name
boot=json.loads((BASE/'outputs/mcp-agent-20261121/control-location.json').read_text())
SDK=Path(boot['local_root'])/'isolated-sdk/bin/python'
assert (SDK.parent.parent).resolve().name=='isolated-sdk-v2'
env={k:v for k,v in os.environ.items() if not k.startswith(('LLAMA_ARG_','GGML_')) and k not in ['LD_PRELOAD','OPENAI_LOG','HTTPX_LOG_LEVEL','AGENT_LAB_EVIDENCE_KEY','OPENAI_API_KEY']}
env.update(PYTHONPATH=str(CODE),CUDA_VISIBLE_DEVICES='',PYTHONUNBUFFERED='1',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',TMPDIR=str(ROOT))
report={'variant':spec['variant'],'protocol_sha256':sha(OUT/'protocol.json'),'phases':[],'GPU_used':False,'model_started':False,'neural_requests':0,'terminal':False}
save=lambda:(OUT/'run-report.json').write_text(json.dumps(report,indent=2)+'\n')
save();process=None;start_ticks=None;started=time.monotonic()
def ticks(pid):
 try:return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
 except (OSError,IndexError):return None
def stop():
 if process is not None and process.poll() is None:
  assert ticks(process.pid)==start_ticks
  os.killpg(process.pid,signal.SIGTERM)
  try:process.wait(timeout=15)
  except subprocess.TimeoutExpired:
   assert ticks(process.pid)==start_ticks
   os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=10)
def rss(sid):
 total=0
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   fields=(p/'stat').read_text().rsplit(')',1)[1].split()
   if int(fields[3])==sid:total+=int(fields[21])*os.sysconf('SC_PAGE_SIZE')
  except (OSError,IndexError,ValueError):pass
 return total
def run(name,args,cap,allowed=(0,)):
 global process,start_ticks
 begin=time.monotonic();guard=None;peak=0
 with (OUT/(name+'.log')).open('wb') as log,(OUT/(name+'-monitor.jsonl')).open('w') as mon:
  process=subprocess.Popen([str(x) for x in args],cwd=CODE,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);start_ticks=ticks(process.pid)
  while process.poll() is None:
   elapsed=time.monotonic()-begin;memory=available();sample=rss(process.pid);peak=max(peak,sample)
   mon.write(json.dumps({'elapsed_seconds':round(elapsed,3),'available_memory_bytes':memory,'owned_session_rss_bytes':sample})+'\n');mon.flush()
   if elapsed>cap or time.monotonic()-started>600 or memory<8*2**30 or sample>8*2**30:
    guard='phase_deadline' if elapsed>cap else 'job_deadline' if time.monotonic()-started>600 else 'memory_floor' if memory<8*2**30 else 'owned_rss';stop();break
   time.sleep(.5)
  rc=process.wait()
 row={'phase':name,'returncode':rc,'wall_seconds':round(time.monotonic()-begin,3),'guard_reason':guard,'peak_sampled_owned_session_rss_bytes':peak};report['phases'].append(row);save();print(json.dumps(row),flush=True);process=None;start_ticks=None
 if guard or rc not in allowed:raise RuntimeError('Phase failed: '+name)
 return row
def signal_stop(sig,frame):raise KeyboardInterrupt('Operator signal '+str(sig))
for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(sig,signal_stop)
try:
 identity="import json,importlib.metadata as m;from llama_index.core.agent.workflow import FunctionAgent;from mcp import Client;from mcp.server import MCPServer;print(json.dumps({d.metadata['Name']:d.version for d in m.distributions()}))"
 run('sdk-identity-before',[SDK,'-c',identity],180)
 versions=json.loads((OUT/'sdk-identity-before.log').read_text())
 assert versions['mcp']=='2.3.0' and versions['llama-index-core']=='0.14.26' and versions['httpx2']=='2.16.2'
 ruff=BASE/'envs/langflow-lfx-20261121/bin/ruff'
 run('ruff',[ruff,'check','benchmarks/llamaindex_mcp_audit.py','benchmarks/mcp_cleanup_controls.py'],60)
 control_args=[SDK,'-m','benchmarks.mcp_cleanup_controls','--code',CODE,'--state',ROOT/'controls','--owner',sha(OUT/'protocol.json')]
 if spec['variant'].endswith('tool-error-v2'):control_args+=['--case','status_tool_error']
 run('controls',control_args,300,allowed=(0,2))
 report['controls']=json.loads((ROOT/'controls/report.json').read_text())
 run('sdk-identity-after',[SDK,'-c',identity],60)
 report['SDK_distribution_versions_unchanged']=versions==json.loads((OUT/'sdk-identity-after.log').read_text())
 assert report['SDK_distribution_versions_unchanged']
 report['all_frozen_sources_unchanged']=all(sha(CODE/name)==expected for name,expected in spec['source_files_sha256'].items())
 assert report['all_frozen_sources_unchanged']
except BaseException as exc:report['operator_error']={'type':type(exc).__name__,'message':str(exc)}
finally:
 stop();owned=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   if str(ROOT).encode() in (p/'cmdline').read_bytes() or (p/'cwd').resolve().is_relative_to(ROOT):owned.append(int(p.name))
  except (OSError,ValueError):pass
 report.update(terminal=True,owned_processes_after=owned,wall_seconds=round(time.monotonic()-started,3));save()
 print(json.dumps({'terminal':True,'variant':spec['variant'],'passed':report.get('controls',{}).get('passed'),'failed':report.get('controls',{}).get('failed'),'operator_error':report.get('operator_error'),'owned_processes_after':len(owned)}),flush=True)
raise SystemExit(0 if not report.get('operator_error') and not owned and (spec['variant'].startswith('baseline') or report.get('controls',{}).get('failed')==0) else 2)
