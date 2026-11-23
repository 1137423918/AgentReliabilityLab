from pathlib import Path,PurePosixPath
import hashlib,json,os,resource,signal,subprocess,tarfile,tempfile,time
OUT=Path(__file__).resolve().parent;BASE=Path('/path/to/private-agent-lab');CORE=BASE/'envs/model-request-budget-20261121/bin/python'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
spec=json.loads((OUT/'protocol.json').read_text());assert sha(Path(__file__))==spec['setup_source_sha256'];assert not (OUT/'setup-report.json').exists();assert sha(OUT/'driver.py')==spec['driver_sha256'];assert sha(OUT/'exec_child.py')==spec['wrapper_sha256'];assert sha(OUT/'upstream.tar')==spec['upstream_tar_sha256']
roots=json.loads((OUT/'private-locations.json').read_text());ROOT=Path(roots['runtime']);PY=ROOT/'runtime/bin/python';MODEL=ROOT/'model';FULL=Path(roots['full']);MIXED=Path(roots['mixed'])
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:4]);os.nice(19);parent_start=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]);WORK=Path(tempfile.mkdtemp(prefix='agentlab-generation-study-stage52-'));WORK.chmod(0o700)
mounts=[(x.split(' - ')[0].split()[4],x.split(' - ')[1].split()[0]) for x in Path('/proc/self/mountinfo').read_text().splitlines()];assert max([(len(p),f) for p,f in mounts if str(WORK).startswith(p.rstrip('/')+'/')])[1] in ['ext4','xfs','btrfs']
location={'root':str(WORK),'runtime':str(ROOT),'model':str(MODEL),'full':str(FULL),'mixed':str(MIXED),'sdk':str(Path(roots['monitor'])/'sdk')};(OUT/'study-location.json').write_text(json.dumps(location)+'\n');(OUT/'study-location.json').chmod(0o600)
report={'terminal':False,'protocol_sha256':sha(OUT/'protocol.json'),'model_or_GPU_or_training':False};began=time.monotonic();child=None
def streamsha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(2*1024*1024):h.update(b)
 return h.hexdigest()
try:
 assert int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024>=32*2**30
 model=json.loads((OUT/'model-manifest.json').read_text());assert sha(OUT/'model-manifest.json')==spec['model_manifest_sha256']
 for x in model['files']:
  p=MODEL/x['path'];assert p.stat().st_size==x['bytes'];h=hashlib.sha256() if x['lfs_sha256'] else hashlib.sha1()
  if not x['lfs_sha256']:h.update(('blob '+str(x['bytes'])+'\0').encode())
  with p.open('rb') as f:
   while b:=f.read(2*1024*1024):h.update(b)
  assert h.hexdigest()==(x['lfs_sha256'] or x['git_blob_sha1'])
 report['verified_model_files']=len(model['files']);cks={}
 for name,path in [('full32',FULL),('mixed32',MIXED)]:
  manifest=json.loads((path/'manifest.json').read_text());assert sha(path/'manifest.json')==spec['checkpoint_manifest_sha256'][name];assert all(streamsha(path/n)==d for n,d in manifest.items());state=json.loads((path/'training-state.json').read_text());assert state['completed_optimizer_updates']==32 and state['training_labels']==65536 and state['adapter_sha256']==spec['adapter_parameter_sha256'][name];cks[name]={'manifest_sha256':sha(path/'manifest.json'),'files':manifest,'completed_updates':32,'supervised_labels':65536,'adapter_parameter_sha256':state['adapter_sha256']}
 report['checkpoint_identities']=cks
 up=WORK/'upstream';up.mkdir()
 with tarfile.open(OUT/'upstream.tar','r:') as t:
  assert {x.name for x in t}==set(spec['upstream_source_sha256'])
 with tarfile.open(OUT/'upstream.tar','r:') as t:
  for m in t:
   name=PurePosixPath(m.name);assert m.isfile() and not name.is_absolute() and '..' not in name.parts;q=up/m.name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(t.extractfile(m).read())
 assert all(sha(up/n)==d for n,d in spec['upstream_source_sha256'].items())
 env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','OPENAI_API_KEY','HF_TOKEN','HUGGING_FACE_HUB_TOKEN','AGENT_LAB_EVIDENCE_KEY']};env.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',PYTHONDONTWRITEBYTECODE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TMPDIR=str(WORK),HF_HOME=str(WORK/'hf-cache'),XDG_CACHE_HOME=str(WORK/'xdg-cache'))
 with (OUT/'token-admission.log').open('wb') as log:
  child=subprocess.Popen([str(CORE),str(OUT/'exec_child.py'),str(os.getpid()),str(parent_start),'cpu',str(PY),str(OUT/'driver.py'),'prepare','--upstream',str(up),'--model',str(MODEL),'--output',str(WORK/'admission.json'),'--max-context','32768','--max-tokens','1024'],env=env,cwd=WORK,stdout=log,stderr=subprocess.STDOUT)
  rc=child.wait(timeout=180);assert rc==0
 admission=json.loads((WORK/'admission.json').read_text());assert admission['case_count']==199 and admission['all_within_context'] and admission['driver_sha256']==spec['driver_sha256'];report.update(tokenizer_admission_sha256=sha(WORK/'admission.json'),token_admission={k:admission[k] for k in ['case_count','max_input_tokens','max_context','max_new_tokens','all_within_context']},ready=True)
except BaseException as e:report['error']={'type':type(e).__name__,'message':str(e)}
finally:
 if child and child.poll() is None:
  child.terminate()
  try:child.wait(timeout=5)
  except subprocess.TimeoutExpired:child.kill();child.wait()
 report.update(terminal=True,owned_child_reaped=not child or child.poll() is not None,wall_seconds=round(time.monotonic()-began,3));(OUT/'setup-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
raise SystemExit(0 if report.get('ready') and not report.get('error') and report['owned_child_reaped'] else 2)
