from pathlib import Path
import base64,resource,ctypes,fcntl,importlib.util,json,os,re,secrets,signal,socket,subprocess,tempfile,threading,time,urllib.request,tarfile,hashlib
from gpu_runtime import BASE,ROOT,BIN,MODEL,probe,public_card,available,descendants,stop_owned,sha,write,now

OUT=Path(__file__).resolve().parent;spec=json.loads((OUT/'protocol.json').read_text());owner=sha(OUT/'protocol.json')
assert 'gpu7' not in socket.gethostname().lower() and not (OUT/'run-report.json').exists()
for name,expected in spec['operator_sha256'].items():assert sha(OUT/name)==expected,name
assert sha(OUT/'source.tar.gz')==spec['source_archive_sha256'] and sha(OUT/'cases.json')==spec['cases_sha256']
assert sha(OUT/'gpu-runtime-manifest.json')==spec['gpu_runtime_manifest_sha256']
WORK=Path(tempfile.mkdtemp(prefix='agentlab-mcp-agent-gpu-stage46-'));WORK.chmod(0o700);CODE=WORK/'code';CODE.mkdir();(WORK/'cuda-cache').mkdir();(WORK/'cases').mkdir();write(OUT/'control-location.json',{'local_root':str(WORK)});(OUT/'control-location.json').chmod(0o600)
with tarfile.open(OUT/'source.tar.gz') as t:t.extractall(CODE,filter='data')
for name,expected in spec['source_files_sha256'].items():assert sha(CODE/name)==expected,name
BOOT=BASE/'outputs/mcp-agent-20261121';SDK=Path(json.loads((BOOT/'control-location.json').read_text())['local_root'])/'isolated-sdk/bin/python';assert SDK.parent.parent.resolve().name=='isolated-sdk-v2'
SERVICE_ROOT=Path(json.loads((BASE/'outputs/evidence-package-stage44-v1-20261122/control-location.json').read_text())['local_root']);MCP_PY=SERVICE_ROOT/'runtime/bin/python';MCP_CLI=SERVICE_ROOT/'runtime/bin/agentlab-evidence';CORE=BASE/'envs/model-request-budget-20261121/bin/python';PORT=18860;MCP_PORT=18861
affinity=sorted(os.sched_getaffinity(0));assert len(affinity)>=4;os.sched_setaffinity(0,affinity[:4]);os.nice(19)
env={k:v for k,v in os.environ.items() if not k.startswith(('LLAMA_ARG_','GGML_')) and k not in ['LD_PRELOAD','OPENAI_LOG','HTTPX_LOG_LEVEL','OPENAI_API_KEY','AGENT_LAB_EVIDENCE_KEY']};env.update(PYTHONPATH=str(CODE),CUDA_VISIBLE_DEVICES='',TMPDIR=str(WORK),PYTHONUNBUFFERED='1',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4')
report={'protocol_sha256':owner,'source_archive_sha256':spec['source_archive_sha256'],'terminal':False,'model_started':False,'model_ready':False,'MCP_installed_service':True,'phases':[],'cases':[],'GPU7_excluded':True,'address_space':'CPU phases48GiB; CUDA model virtual address space uncapped, bounded by sampled host RSS/device memory/wall guards.'};driver=model=mcp=None;driver_known={};model_known={};mcp_known={};key=None;keyfile=WORK/'model-api-key';lock=None;monitor=None;sampler=None;stop=threading.Event();mutex=threading.Lock();telemetry={'guard_reason':None,'errors':[]};job_started=time.monotonic();service_started=None
def save():write(OUT/'run-report.json',report)
def port_open(port):
 with socket.socket() as s:s.settimeout(1);return s.connect_ex(('127.0.0.1',port))==0
def pid_start(pid):return int(Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19])
def cpu_argv(args):return [str(CORE),str(OUT/'cpu_exec.py'),str(os.getpid()),*[str(x) for x in args]]
def run(name,args,cap,clean=False,cwd=CODE,allowed=(0,)):
 global driver,driver_known
 begin=time.monotonic();guard=None;peak=0;child_env=dict(env)
 if clean:child_env.pop('PYTHONPATH',None)
 with (OUT/(name+'.log')).open('wb') as log,(OUT/(name+'-monitor.jsonl')).open('w') as mon:
  driver=subprocess.Popen(cpu_argv(args),cwd=cwd,env=child_env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);driver_known={driver.pid:pid_start(driver.pid)}
  while driver.poll() is None:
   tree=descendants(driver.pid,driver_known);rss=sum(x['rss'] for x in tree.values());peak=max(peak,rss);elapsed=time.monotonic()-begin;memory=available()
   with mutex:gpu_guard=telemetry.get('guard_reason')
   mon.write(json.dumps({'elapsed_seconds':round(elapsed,3),'available_memory_bytes':memory,'driver_tree_rss_bytes':rss})+'\n');mon.flush()
   if elapsed>cap or time.monotonic()-job_started>2400 or memory<16*2**30 or rss>8*2**30 or gpu_guard or (model is not None and model.poll() is not None) or (mcp is not None and mcp.poll() is not None):
    guard='phase_deadline' if elapsed>cap else 'job_deadline' if time.monotonic()-job_started>2400 else 'memory_floor' if memory<16*2**30 else 'driver_rss' if rss>8*2**30 else gpu_guard or 'service_exited';stop_owned(driver,driver_known);break
   time.sleep(.5)
  rc=driver.wait()
 row={'phase':name,'returncode':rc,'wall_seconds':round(time.monotonic()-begin,3),'guard_reason':guard,'peak_sampled_driver_tree_rss_bytes':peak};report['phases'].append(row);save();print(json.dumps(row),flush=True);driver=None;driver_known={}
 if guard or rc not in allowed:raise RuntimeError('Phase failed: '+name)
 return row
def get(path,port,key=None):
 request=urllib.request.Request(f'http://127.0.0.1:{port}'+path,headers={'Authorization':'Bearer '+key} if key else {})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=3) as response:return json.load(response)
def wait_health(proc,port,limit,key=None):
 deadline=time.monotonic()+limit
 while True:
  assert proc.poll() is None,'Service exited before readiness'
  with mutex:guard=telemetry.get('guard_reason')
  assert not guard,guard
  assert available()>=16*2**30,'Host memory floor'
  try:
   if get('/health',port,key).get('status')=='ok':return
  except (OSError,ValueError):pass
  if time.monotonic()>deadline:raise TimeoutError('Service readiness deadline')
  time.sleep(.5)
def interrupted(sig,frame):raise KeyboardInterrupt('Operator signal '+str(sig))
for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(sig,interrupted)
save()
try:
 sdk_code="""import inspect,hashlib,json,importlib.metadata as m
from pathlib import Path
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.agent.workflow.base_agent import BaseWorkflowAgent
from llama_index.llms.openai_like import OpenAILike
from llama_index.llms.openai import OpenAI
from workflows.handler import WorkflowHandler
from mcp import Client
from mcp.server import MCPServer
objects=[FunctionAgent,BaseWorkflowAgent,OpenAILike,OpenAI,WorkflowHandler,Client,MCPServer]
print(json.dumps({'versions':{d.metadata['Name']:d.version for d in m.distributions()},'module_source_sha256':{o.__name__:hashlib.sha256(Path(inspect.getfile(o)).read_bytes()).hexdigest() for o in objects}}))
"""
 run('agent-sdk-identity',[SDK,'-c',sdk_code],180);identity=json.loads((OUT/'agent-sdk-identity.log').read_text());old=json.loads((OUT/'prior-sdk-identity.json').read_text());assert identity['versions']==old['versions'] and identity['module_source_sha256']==old['module_source_sha256'];report['same_locked_agent_SDK_as_CPU_snapshot']=True;save()
 service_code="""import inspect,hashlib,json,importlib.metadata as m,importlib.util
from pathlib import Path
from agentlab_evidence import evidence_audit,evidence_service,evidence_mcp
assert importlib.util.find_spec('agent_lab') is None and importlib.util.find_spec('benchmarks') is None
print(json.dumps({'version':m.version('agentlab-evidence'),'source_sha256':{Path(inspect.getfile(o)).name:hashlib.sha256(Path(inspect.getfile(o)).read_bytes()).hexdigest() for o in [evidence_audit,evidence_service,evidence_mcp]}}))
"""
 run('installed-service-identity',[MCP_PY,'-I','-c',service_code],60,clean=True,cwd=WORK);installed=json.loads((OUT/'installed-service-identity.log').read_text());assert installed['version']=='0.1.0' and installed['source_sha256']==spec['installed_service_source_sha256'];report['installed_wheel_identity_verified']=True;save()
 artifact_code="""from pathlib import Path
import hashlib,json
out=Path(OUT);spec=json.loads((out/'protocol.json').read_text());base=Path('<SERVER_BASE>');private=json.loads((base/'outputs/gpu-smoke-20261121/runtime-manifest-private.json').read_text());public=json.loads((out/'gpu-runtime-manifest.json').read_text())
assert [{k:v for k,v in row.items() if k!='path'} for row in private['runtime_files']]==public['runtime_files']
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while block:=f.read(1048576):h.update(block)
 return h.hexdigest()
for row in private['runtime_files']:assert digest(Path(row['path']))==row['sha256']
model=base/'models/Qwen3.5-9B-LMStudio-1379f25c/Qwen3.5-9B-Q4_K_M.gguf';assert digest(model)==spec['model_sha256']==private['model_sha256']
print(json.dumps({'runtime_files_verified':len(private['runtime_files']),'server_sha256':private['server_sha256'],'model_sha256':private['model_sha256'],'model_bytes':model.stat().st_size}))
""".replace('OUT',repr(str(OUT)))
 run('native-artifact-identity',[CORE,'-c',artifact_code],180);artifacts=json.loads((OUT/'native-artifact-identity.log').read_text());assert artifacts['runtime_files_verified']==22 and artifacts['server_sha256']==spec['server_sha256'];report['native_runtime_and_model_hashes_verified']=True;save()
 assert available()>=32*2**30 and os.getloadavg()[0]<=len(affinity)-4,'Fresh host admission failed'
 assert resource.getrlimit(resource.RLIMIT_AS)==(resource.RLIM_INFINITY,resource.RLIM_INFINITY),'CUDA needs unbounded inherited virtual address space'
 assert not port_open(PORT) and not port_open(MCP_PORT),'Task port occupied'
 first=probe();time.sleep(5);second=probe()
 def idle(c):return c['index'] in [3,6] and c['compute_capability']=='8.6' and c['total_mib']>=24000 and c['total_mib']-c['used_mib']>=22000 and c['utilization']<=5 and not c['pids']
 candidates=sorted([c for c in second['cards'] if idle(c) and any(x['uuid']==c['uuid'] and idle(x) for x in first['cards'])],key=lambda c:c['index']);assert candidates,'No eligible idle GPU at final admission'
 locks=BASE/'locks';locks.mkdir(exist_ok=True);selected=None
 for c in candidates:
  candidate_lock=(locks/('gpu-'+c['uuid']+'.lock')).open('a')
  try:fcntl.flock(candidate_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:candidate_lock.close();continue
  latest=next(x for x in probe(c['uuid'])['cards'] if x['uuid']==c['uuid'])
  if idle(latest):selected=latest;lock=candidate_lock;break
  candidate_lock.close()
 assert selected is not None,'No unreserved idle GPU';uuid=selected['uuid'];report['GPU']=public_card(selected);report['admission']=[{'at':x['observed_utc'],'card':public_card(next(c for c in x['cards'] if c['uuid']==uuid))} for x in [first,second]];save()
 mcp_env=dict(env);mcp_env.pop('PYTHONPATH',None)
 mcp_log=(WORK/'mcp-server.log').open('wb');mcp=subprocess.Popen(cpu_argv([MCP_CLI,'--root',CODE/'corpus','--manifest',CODE/'corpus/catalog.json','--port',MCP_PORT]),cwd=WORK,env=mcp_env,stdout=mcp_log,stderr=subprocess.STDOUT,start_new_session=True);mcp_known={mcp.pid:pid_start(mcp.pid)};wait_health(mcp,MCP_PORT,60);report['mcp_ready']=True;save()
 key=secrets.token_urlsafe(32);keyfile.write_text(key+'\n');keyfile.chmod(0o600);env['AGENT_LAB_EVIDENCE_KEY']=key
 model_env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','CUDA_VISIBLE_DEVICES':uuid,'CUDA_DEVICE_ORDER':'PCI_BUS_ID','CUDA_CACHE_PATH':str(WORK/'cuda-cache'),'TMPDIR':str(WORK),'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'4','MKL_NUM_THREADS':'4','LD_LIBRARY_PATH':str(ROOT/'toolchain/lib')+':'+str(BIN)+':/usr/local/cuda-12.9/lib64'}
 argv=[str(BIN/'llama-server'),'--model',str(MODEL),'--alias',spec['model_alias'],'--host','127.0.0.1','--port',str(PORT),'--device','CUDA0','--n-gpu-layers','all','--split-mode','none','--fit','off','--threads','4','--threads-batch','4','--threads-http','1','--parallel','1','--ctx-size','8192','--n-predict','1024','--log-verbosity','4','--timeout','180','--temp','0','--seed','42','--jinja','--reasoning-format','none','--chat-template-kwargs','{"enable_thinking":false}','--no-context-shift','--cache-prompt','--no-webui','--no-slots','--api-key-file',str(keyfile)]
 parent=os.getpid()
 def parent_death():
  assert ctypes.CDLL(None).prctl(1,signal.SIGTERM,0,0,0)==0
  if os.getppid()!=parent:os._exit(127)
 model_log=(WORK/'server.log').open('wb');model=subprocess.Popen(argv,cwd=BIN,env=model_env,stdout=model_log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=parent_death);model_known={model.pid:pid_start(model.pid)};service_started=time.monotonic();report.update(model_started=True,model_argv=argv);save()
 telemetry.update(card=selected,at=time.monotonic())
 def sample_gpu():
  while not stop.is_set() and model.poll() is None:
   try:
    card=next(c for c in probe(uuid)['cards'] if c['uuid']==uuid)
    with mutex:telemetry.update(card=card,at=time.monotonic())
   except Exception as error:
    with mutex:telemetry['errors'].append({'at':now(),'type':type(error).__name__})
   stop.wait(2)
 def watch():
  peak_rss=peak_vram=0;reason=None
  with (WORK/'gpu-monitor.jsonl').open('w') as log:
   while not stop.is_set() and model.poll() is None:
    try:
     tree=descendants(model.pid,model_known);rss=sum(x['rss'] for x in tree.values());peak_rss=max(peak_rss,rss)
     with mutex:card=telemetry['card'];age=time.monotonic()-telemetry['at']
     peak_vram=max(peak_vram,card['used_mib']);foreign=set(card['pids'])-set(tree);elapsed=time.monotonic()-service_started
     log.write(json.dumps({'elapsed_seconds':round(elapsed,3),'host_tree_rss_bytes':rss,'gpu_used_MiB':card['used_mib'],'GPU_observation_age_seconds':round(age,3),'foreign_compute_clients':len(foreign),'own_compute_client_seen':bool(set(card['pids'])&set(tree))})+'\n');log.flush()
     if elapsed>1800:reason='model_service_wall'
     elif time.monotonic()-job_started>2400:reason='global_job_wall'
     elif available()<16*2**30:reason='host_memory_floor'
     elif rss>16*2**30:reason='model_host_RSS'
     elif age>30:reason='GPU_observation_stale'
     elif card['used_mib']>18432:reason='GPU_memory_limit'
     elif foreign:reason='foreign_compute_client'
    except Exception as error:reason='monitor_error:'+type(error).__name__
    if reason:
     with mutex:telemetry['guard_reason']=reason
     stop_owned(model,model_known);break
    stop.wait(2)
  with mutex:telemetry['monitor']={'peak_host_tree_RSS_bytes':peak_rss,'peak_GPU_used_MiB':peak_vram,'guard_reason':reason}
 sampler=threading.Thread(target=sample_gpu,daemon=True);monitor=threading.Thread(target=watch,daemon=True);sampler.start();monitor.start();print(json.dumps({'model_started':True,'GPU_index':selected['index'],'MCP_installed_service':True}),flush=True)
 wait_health(model,PORT,240,key);models=get('/v1/models',PORT,key);assert spec['model_alias'] in [x['id'] for x in models['data']]
 text=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',(WORK/'server.log').read_text());offload=re.findall(r'offloaded (\d+)/(\d+) layers to GPU',text);assert offload and offload[-1]==('33','33');contexts=[int(x) for x in re.findall(r'\bn_ctx(?:_slot)?\s*=\s*(\d+)',text)];assert 8192 in contexts
 deadline=time.monotonic()+30
 while True:
  with mutex:card=telemetry['card'];age=time.monotonic()-telemetry['at']
  if age<=30 and model.pid in card['pids'] and set(card['pids'])<=set(descendants(model.pid,model_known)):break
  assert time.monotonic()<deadline,'GPU process identity confirmation deadline';time.sleep(.5)
 report.update(model_ready=True,offloaded_layers=33,total_layers=33,context_observed=8192,own_GPU_compute_process_seen=True);save();print(json.dumps({'model_ready':True,'full_GPU_offload':'33/33','context':8192}),flush=True)
 for case in json.loads((OUT/'cases.json').read_text()):
  if time.monotonic()-service_started>1080:report['aborted_remaining']='Insufficient remaining1800s service budget for full690s case';break
  state=WORK/'cases'/case['id'];phase=run('case-'+case['id'],[SDK,'-m','benchmarks.llamaindex_mcp_audit','--mcp-url',f'http://127.0.0.1:{MCP_PORT}/mcp','--state-dir',state,'--cases',OUT/'cases.json','--case',case['id'],'--base-url',f'http://127.0.0.1:{PORT}/v1','--model',spec['model_alias'],'--owner',owner],690,allowed=(0,2))
  result=json.loads((state/'result.json').read_text());journal=json.loads((state/'journal/model-requests.json').read_text());row={'case':case['id'],'grading':result['grading'],'model_HTTP_reservations':len(journal['reservations']),'model_request_body_bytes':sum(x['request_body_bytes'] for x in journal['reservations']),'http_statuses':[x['http_status'] for x in journal['reservations']],'wall_seconds':phase['wall_seconds'],'error':result.get('error'),'MCP_close':result.get('mcp_close')};report['cases'].append(row);save();print(json.dumps(row),flush=True)
  if (result.get('error') and result['error']['type']!='EvidenceError') or result.get('workflow_cancel_wait_expired'):report['aborted_remaining']='Transport/workflow failure; no repeated query or unknown work';break
 report.update(declared_cases=2,completed_cases=len(report['cases']),cases_passed=sum(x['grading']['case_passed'] for x in report['cases']));report['all_cases_passed']=report['completed_cases']==report['cases_passed']==2
except BaseException as error:report['operator_error']={'type':type(error).__name__,'message':str(error)}
finally:
 stop.set()
 if monitor:monitor.join(timeout=15)
 if sampler:sampler.join(timeout=25)
 report['monitor_thread_stopped']=monitor is None or not monitor.is_alive();report['sampler_thread_stopped']=sampler is None or not sampler.is_alive()
 with mutex:report['GPU_monitor']=telemetry.get('monitor');report['GPU_guard_reason']=telemetry.get('guard_reason');report['GPU_probe_errors']=telemetry['errors']
 if driver is not None:report['driver_shutdown']=stop_owned(driver,driver_known)
 if model is not None:report['model_shutdown']=stop_owned(model,model_known);model_log.close()
 if mcp is not None:report['mcp_shutdown']=stop_owned(mcp,mcp_known);mcp_log.close()
 if model is not None:
  try:after=next(c for c in probe(uuid)['cards'] if c['uuid']==uuid);report['GPU_after']=public_card(after);report['own_GPU_context_absent']=not(set(model_known)&set(after['pids']))
  except Exception as error:report['GPU_cleanup_observation_error']=type(error).__name__
 if key:
  native=(WORK/'server.log').read_text(errors='replace');(WORK/'server-public.log').write_text(native.replace(key,'__REDACTED_LOCAL_AUTH__'));report['server_log_auth_redactions']=native.count(key)
 keyfile.unlink(missing_ok=True)
 if lock:lock.close()
 report['ports_closed']={str(p):not port_open(p) for p in [PORT,MCP_PORT]};report['model_api_key_file_remaining']=keyfile.exists();report['service_wall_seconds']=None if service_started is None else round(time.monotonic()-service_started,3);owned=[]
 for p in Path('/proc').glob('[0-9]*'):
  try:
   if str(WORK).encode() in (p/'cmdline').read_bytes() or (p/'cwd').resolve().is_relative_to(WORK):owned.append(int(p.name))
  except (OSError,ValueError):pass
 report['owned_processes_after']=owned;report['all_frozen_source_files_unchanged']=all(sha(CODE/n)==d for n,d in spec['source_files_sha256'].items());report['secret_in_json_outputs']=False
 if key:
  for folder in [WORK,OUT]:
   for p in folder.rglob('*.json'):
    if key.encode() in p.read_bytes():report['secret_in_json_outputs']=True
    if p.name=='result.json':
     for event in json.loads(p.read_text()).get('wire_events',[]):
      if key.encode() in base64.b64decode(event['body_base64']):report['secret_in_json_outputs']=True
 report['terminal']=True;save();key=None;env.pop('AGENT_LAB_EVIDENCE_KEY',None);print(json.dumps({'terminal':True,'model_started':report['model_started'],'completed_cases':report.get('completed_cases',0),'cases_passed':report.get('cases_passed',0),'operator_error':report.get('operator_error'),'GPU_guard_reason':report.get('GPU_guard_reason'),'owned_after':len(owned),'ports_closed':report['ports_closed']}),flush=True)
raise SystemExit(0 if report.get('all_cases_passed') and not report.get('operator_error') and not report.get('GPU_guard_reason') and not owned and all(report['ports_closed'].values()) and report.get('own_GPU_context_absent') and not report['secret_in_json_outputs'] and report.get('model_shutdown',{}).get('returncode')==0 and report.get('mcp_shutdown',{}).get('returncode') in [0,-15,143] else 2)
