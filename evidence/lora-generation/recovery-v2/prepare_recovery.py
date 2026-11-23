from pathlib import Path,PurePosixPath
import hashlib,json,os,signal,subprocess,tarfile,tempfile,time,shutil
OUT=Path(__file__).resolve().parent;BASE=Path('/path/to/private-agent-lab');CORE=BASE/'envs/model-request-budget-20261121/bin/python';OLD=BASE/'outputs/lora-generation-stage52-20261123';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();spec=json.loads((OUT/'protocol.json').read_text())
assert sha(Path(__file__))==spec['setup_source_sha256'] and sha(OUT/'source.tar')==spec['source_tar_sha256'];assert sha(OUT/'assemble_study.py')==spec['assemble_source_sha256'] and sha(OUT/'exec_child.py')==spec['wrapper_sha256'];assert not (OUT/'setup-report.json').exists()
os.umask(0o077);os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:4]);os.nice(19);ROOT=Path(tempfile.mkdtemp(prefix='agentlab-generation-recovery-stage52-'));ROOT.chmod(0o700);start=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]);old_location=json.loads((OLD/'study-location.json').read_text());PY=Path(old_location['runtime'])/'runtime/bin/python';MODEL=Path(old_location['model'])
mounts=[(x.split(' - ')[0].split()[4],x.split(' - ')[1].split()[0]) for x in Path('/proc/self/mountinfo').read_text().splitlines()];assert max([(len(p),f) for p,f in mounts if str(ROOT).startswith(p.rstrip('/')+'/')])[1] in ['ext4','xfs','btrfs']
(OUT/'control-location.json').write_text(json.dumps({'root':str(ROOT),'source':str(ROOT/'source'),'runtime':old_location['runtime'],'model':str(MODEL),'upstream':str(Path(old_location['root'])/'upstream'),'sdk':old_location['sdk']})+'\n');(OUT/'control-location.json').chmod(0o600)
env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','HF_TOKEN','HUGGING_FACE_HUB_TOKEN','OPENAI_API_KEY']};env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TMPDIR=str(ROOT),HF_HOME=str(ROOT/'hf-cache'),XDG_CACHE_HOME=str(ROOT/'xdg-cache'))
report={'terminal':False,'protocol_sha256':sha(OUT/'protocol.json'),'model_or_GPU_or_training':False,'phases':[]};began=time.monotonic();child=None;known={}
def owned():
 rows={}
 for p in Path('/proc').glob('[0-9]*'):
  try:
   if p.stat().st_uid!=os.getuid():continue
   s=(p/'stat').read_text().rsplit(')',1)[1].split();rows[int(p.name)]={'parent':int(s[1]),'start':int(s[19]),'state':s[0],'rss':int(s[21])*os.sysconf('SC_PAGE_SIZE')}
  except (OSError,ValueError):pass
 ids={child.pid} if child and child.poll() is None and child.pid in rows else set();ids.update(p for p,v in known.items() if p in rows and rows[p]['start']==v)
 for _ in range(16):
  old=len(ids);ids.update(p for p,r in rows.items() if r['parent'] in ids)
  if len(ids)==old:break
 ids={p for p in ids if rows[p]['state']!='Z'};known.update({p:rows[p]['start'] for p in ids});return {p:rows[p] for p in ids}
def stop():
 for sig in [signal.SIGTERM,signal.SIGKILL]:
  for pid,r in owned().items():
   if owned().get(pid,{}).get('start')==r['start']:
    try:os.kill(pid,sig)
    except ProcessLookupError:pass
  if child and child.poll() is None:
   try:child.wait(timeout=3)
   except subprocess.TimeoutExpired:pass
  if not owned():break
def run(name,command,cap):
 global child
 start_phase=time.monotonic();peak=0
 with (OUT/(name+'.log')).open('wb') as log:
  child=subprocess.Popen([str(CORE),str(OUT/'exec_child.py'),str(os.getpid()),str(start),'cpu',*[str(x) for x in command]],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  while child.poll() is None:
   rss=sum(x['rss'] for x in owned().values());peak=max(peak,rss)
   if time.monotonic()-start_phase>cap or rss>4*2**30:raise RuntimeError('CPU phase wall/RSS guard: '+name)
   time.sleep(.1)
  rc=child.wait()
 report['phases'].append({'phase':name,'returncode':rc,'wall_seconds':round(time.monotonic()-start_phase,3),'peak_sampled_owned_RSS_bytes':peak});assert rc==0,name
try:
 assert int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024>=32*2**30
 source=ROOT/'source';source.mkdir()
 with tarfile.open(OUT/'source.tar','r:') as t:
  for m in t:
   p=PurePosixPath(m.name);assert m.isfile() and not p.is_absolute() and '..' not in p.parts;q=source/m.name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(t.extractfile(m).read())
 assert all(sha(source/n)==x['sha256'] for n,x in spec['files'].items())
 run('CPU-progress-and-dispatch-controls',[CORE,'-I','-m','unittest','discover','-s',source/'extras/lora-training','-p','test_generation_*.py','-v'],120)
 # Immutable fixed-step artifacts are backed up privately, never redistributed.
 backup=BASE/'models/paired-lora-fixed32-stage51-20261123';backup.mkdir(mode=0o700,exist_ok=True);locations={}
 for role,key in [('full32','full'),('mixed32','mixed')]:
  origin=Path(old_location[key]);manifest=json.loads((origin/'manifest.json').read_text());assert sha(origin/'manifest.json')==spec['checkpoint_manifest_sha256'][role];target=backup/role;target.mkdir(mode=0o700,exist_ok=True)
  for n,d in {**manifest,'manifest.json':sha(origin/'manifest.json')}.items():
   assert sha(origin/n)==d;q=target/n;q.parent.mkdir(parents=True,exist_ok=True)
   if q.exists():assert not q.is_symlink() and sha(q)==d
   else:
    tmp=q.with_name(q.name+'.copy-'+str(os.getpid()));assert not tmp.exists()
    with (origin/n).open('rb') as f,tmp.open('xb') as g:shutil.copyfileobj(f,g,2*1024*1024);g.flush();os.fsync(g.fileno())
    os.replace(tmp,q)
   assert sha(q)==d and sha(origin/n)==d
  locations[key]=str(target)
 report['private_fixed_checkpoint_backup_verified']=True
 run('new-tokenizer-admission',[PY,source/'benchmarks/agentrobustbench_baseline.py','prepare','--upstream',Path(old_location['root'])/'upstream','--model',MODEL,'--output',ROOT/'admission.json','--max-context','32768','--max-tokens','1024'],180)
 run('legacy-import-and280-cache-controls',[CORE,OUT/'assemble_study.py','--source',source,'--admission',ROOT/'admission.json','--output',ROOT,'--spec',OUT/'protocol.json','--binding',OUT/'legacy-binding.json'],300)
 assembled=json.loads((ROOT/'assembly-report.json').read_text());assert assembled['ready'] and assembled['legacy_attempts_imported']==281 and assembled['legacy_results_imported']==280 and assembled['unknown_attempts_retained']==1 and assembled['model_or_scorer_callbacks']==0
 location=json.loads((OUT/'control-location.json').read_text());location.update(locations);(OUT/'control-location.json').write_text(json.dumps(location)+'\n')
 report.update(ready=True,assembly=assembled,source_files_unchanged=all(sha(source/n)==x['sha256'] for n,x in spec['files'].items()))
except BaseException as e:report['error']={'type':type(e).__name__,'message':str(e)}
finally:
 stop();report.update(terminal=True,owned_after=len(owned()),wall_seconds=round(time.monotonic()-began,3));(OUT/'setup-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
raise SystemExit(0 if report.get('ready') and report['owned_after']==0 and report['source_files_unchanged'] and not report.get('error') else 2)
