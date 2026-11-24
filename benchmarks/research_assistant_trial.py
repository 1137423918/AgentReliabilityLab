"""Three frozen known-collection CPU Agent trajectories, with actual MCP and native model.

No retries, no model warmup, no re-indexing. Mechanical citation checks are not semantic scores.
"""
from pathlib import Path
import hashlib,json,os,secrets,socket,subprocess,sys,threading,time,traceback,urllib.request
from agentlab_research.research_embeddings import LocalE5Embedding
from agentlab_research.research_mcp import create_app

STAGED,MODEL,INPUT,OUT,CODE=map(Path,sys.argv[1:]);OUT.mkdir(mode=0o700,exist_ok=False)
counts={'reserved_forwards':0,'completed_forwards':0,'text_inputs':0,'query_inputs':0};caps={'reserved_forwards':24,'text_inputs':0,'query_inputs':24}
ledger=OUT/'query-embedding-events.jsonl';ledger.touch(exist_ok=False)
spec=json.loads(INPUT.read_text());assert len(spec['cases'])==3 and spec['max_model_requests_per_case']==6 and spec['max_output_tokens_per_request']==256
report={'ready':False,'scope':spec['scope'],'GPU_used':False,'model':'Qwen3-4B-Instruct-2507, existing fixed Q4_K_M','model_warmup_disabled':True,'model_prompt_cache_enabled':True,'whole_request_deadline_seconds':180,'terminal_format_policy':'one response-schema constrained final arguments request with tool_choice none within unchanged6-turn budget; exact JSON object passed through same citation validator, raw response preserved; searches/reads remain model-selected','max_generation_requests':18,'max_generation_requests_per_case':6,'max_output_tokens_per_request':256,'embedding_caps':caps,'cases':[],'remaining_cases':'not yet run'}
started=time.monotonic();native=None;server=None;thread=None;keyfile=OUT/'service-key';key=secrets.token_urlsafe(32)
def save(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def observe(phase,event):
 if phase=='reserved':
  field=event['kind']+'_inputs';assert counts['reserved_forwards']+1<=caps['reserved_forwards'] and counts[field]+event['inputs']<=caps[field]
  counts['reserved_forwards']+=1;counts[field]+=event['inputs']
 else:counts['completed_forwards']+=1
 with ledger.open('a') as f:f.write(json.dumps({'phase':phase,**event,'counts':dict(counts)},sort_keys=True)+'\n');f.flush();os.fsync(f.fileno())
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None
health=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

def free_port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
try:
 import torch,uvicorn
 assert torch.__version__=='2.6.0+cpu' and not torch.cuda.is_initialized()
 model=LocalE5Embedding(MODEL,observer=observe,batch_size=4)
 assert all(p.device.type=='cpu' for p in model._model.parameters())
 mcp_port=free_port();server=uvicorn.Server(uvicorn.Config(create_app(STAGED/'library',model),host='127.0.0.1',port=mcp_port,log_level='error',access_log=False));thread=threading.Thread(target=server.run,daemon=True);thread.start();deadline=time.monotonic()+20
 while not server.started:assert thread.is_alive() and time.monotonic()<deadline;time.sleep(.05)
 model_port=free_port();assert model_port!=mcp_port;keyfile.write_text(key+'\n');keyfile.chmod(0o600)
 model_id='agentlab-research-qwen3-4b-cpu'
 argv=[str(STAGED/'bin/llama-server'),'--model',str(STAGED/'model.gguf'),'--alias',model_id,'--host','127.0.0.1','--port',str(model_port),'--api-key-file',str(keyfile),'--device','none','--n-gpu-layers','0','--fit','off','--threads','2','--threads-batch','2','--threads-http','1','--parallel','1','--ctx-size','4096','--n-predict','256','--timeout','180','--temp','0','--seed','42','--jinja','--reasoning-format','none','--chat-template-kwargs','{"enable_thinking":false}','--no-context-shift','--cache-prompt','--no-warmup','--no-webui','--no-slots']
 env=dict(os.environ);env['LD_LIBRARY_PATH']=str(STAGED/'lib')+':'+str(STAGED/'bin');env['CUDA_VISIBLE_DEVICES']='';env['AGENT_LAB_RESEARCH_KEY']=key
 log=(OUT/'native-server.log').open('wb');native=subprocess.Popen(argv,cwd=OUT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);deadline=time.monotonic()+120
 while True:
  assert native.poll() is None,'Native model exited during startup'
  try:
   req=urllib.request.Request('http://127.0.0.1:'+str(model_port)+'/health',headers={'Authorization':'Bearer '+key})
   with health.open(req,timeout=2) as response:
    if response.status==200:break
  except Exception:pass
  assert time.monotonic()<deadline,'Native readiness deadline';time.sleep(.25)
 assert 'warming up the model' not in (OUT/'native-server.log').read_text().lower(),'Unexpected model warmup'
 report['native_ready']=True;save('trial-report.json',report)
 for case in spec['cases']:
  report['active_case']=case['id'];save('trial-report.json',report)
  assert time.monotonic()-started<1400,'Trial wall budget'
  run=OUT/'cases'/case['id'];run.parent.mkdir(exist_ok=True)
  args=[sys.executable,'-m','agent_lab.research_assistant','--question',case['question'],'--run-dir',str(run),'--mcp-url','http://127.0.0.1:'+str(mcp_port)+'/mcp','--model-url','http://127.0.0.1:'+str(model_port)+'/v1','--model',model_id,'--model-fingerprint','9f1c9b5bd32d1c37502b525a677b3245a1b91fb7b71c7464f4264647998e7a06','--max-turns','6','--max-output-tokens','256','--request-seconds','180']
  before=dict(counts);t=time.monotonic()
  with (OUT/(case['id']+'.log')).open('wb') as output:
   proc=subprocess.run(args,cwd=CODE,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=450)
  result_file=run/'result.json'
  row={'id':case['id'],'returncode':proc.returncode,'wall_seconds':round(time.monotonic()-t,3),'embedding_delta':{k:counts[k]-before[k] for k in counts}}
  if result_file.exists():
   result=json.loads(result_file.read_text());final=result.get('final');row.update(status=result['status'],final=final,model_requests=result['model_requests'],model_turns=result['model_turns'],finalization_requests=result.get('finalization_requests',0),final_transport=result.get('final_transport'),complete_responses=result['saved_complete_response_files'],requests_without_complete_response=result['reservations_without_complete_saved_response'])
   distinct=len({c['pdf']['sha256'] for c in (final or {}).get('citations',[]) if c.get('pdf')})
   row['mechanical_contract_passed']=bool(result['status']=='submitted' and final['status']==case['expected_submission'] and distinct>=case['required_distinct_PDFs']);row['semantic_review']='not yet reviewed'
  else:row.update(status='no_terminal_result',mechanical_contract_passed=False)
  report['cases'].append(row);save('trial-report.json',report)
  if proc.returncode not in [0,2] or not result_file.exists() or row.get('requests_without_complete_response',0):
   report['remaining_cases']='not started after transport/process/incomplete-response failure';raise RuntimeError('Abort remaining cases after nonsemantic failure')
  # Completion replay is a new process against the same immutable identity. It may
  # list MCP sources but must cause no new model or embedding requests.
  if case['id']==spec['cases'][0]['id']:
   journal=run/'requests/model-requests.json';before_hash=hashlib.sha256(journal.read_bytes()).hexdigest();before_embeddings=dict(counts);cached=run/'responses';before_responses={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in cached.glob('*.json')}
   with (OUT/'completed-replay.log').open('wb') as output:replay=subprocess.run(args,cwd=CODE,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=60)
   assert replay.returncode==proc.returncode and hashlib.sha256(journal.read_bytes()).hexdigest()==before_hash and counts==before_embeddings
   assert before_responses=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in cached.glob('*.json')}
   report['completed_run_new_process_replay_zero_generation_and_embedding']=True
 assert counts==model.counts and counts['reserved_forwards']==counts['completed_forwards'];assert not torch.cuda.is_initialized()
 report['remaining_cases']='all declared cases executed';report['active_case']=None;report['ready']=True
except BaseException as e:
 report['remaining_cases']='not started after '+type(e).__name__;report['error']={'type':type(e).__name__,'message':str(e)[:1000]};traceback.print_exc()
finally:
 if native and native.poll() is None:
  native.terminate()
  try:native.wait(timeout=15)
  except subprocess.TimeoutExpired:native.kill();native.wait(timeout=10)
 if server:server.should_exit=True
 if thread:thread.join(timeout=15)
 keyfile.unlink(missing_ok=True)
 reservations=0;complete=0;usage={'prompt_tokens':0,'completion_tokens':0};native_tokens={'evaluated_prompt_tokens':0,'cached_prefix_tokens':0,'predicted_tokens':0}
 for path in (OUT/'cases').glob('*/requests/model-requests.json'):
  reservations+=len(json.loads(path.read_text())['reservations'])
 for path in (OUT/'cases').glob('*/responses/*.json'):
  result=json.loads(path.read_text())['response'];complete+=1
  for field in usage:usage[field]+=result.get('usage',{}).get(field,0)
  for field,key in [('evaluated_prompt_tokens','prompt_n'),('cached_prefix_tokens','cache_n'),('predicted_tokens','predicted_n')]:native_tokens[field]+=result.get('timings',{}).get(key,0)
 report.update(generation_HTTP_reservations=reservations,complete_model_responses=complete,reservations_without_saved_response=reservations-complete,saved_usage=usage,saved_native_token_counts=native_tokens,embedding_counts=counts,embedding_unknown=counts['reserved_forwards']-counts['completed_forwards'],embedding_ledger_sha256=hashlib.sha256(ledger.read_bytes()).hexdigest(),budgets_status='CLOSED',native_server_closed=native is None or native.poll() is not None,MCP_closed=thread is None or not thread.is_alive(),ephemeral_key_removed=not keyfile.exists(),wall_seconds=round(time.monotonic()-started,3))
 save('trial-report.json',report);print(json.dumps({k:report.get(k) for k in ['ready','error','generation_HTTP_reservations','complete_model_responses','embedding_counts','embedding_unknown','native_server_closed','MCP_closed','wall_seconds']}),flush=True)
raise SystemExit(0 if report['ready'] else 2)
