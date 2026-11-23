from pathlib import Path, PurePosixPath
import hashlib,json,os,signal,subprocess,tarfile,tempfile,time,shutil,xml.etree.ElementTree as ET
OUT=Path(__file__).resolve().parent;BASE=Path('/path/to/private-agent-lab');CORE=BASE/'envs/model-request-budget-20261121/bin/python';UV=BASE/'tools/uv-x86_64-unknown-linux-gnu/uv';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();spec=json.loads((OUT/'protocol.json').read_text());assert sha(Path(__file__))==spec['controller_sha256'] and sha(OUT/'exec_child.py')==spec['wrapper_sha256'];assert not (OUT/'run-report.json').exists()
os.umask(0o077);os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:4]);os.nice(19);ROOT=Path(tempfile.mkdtemp(prefix='agentlab-lightning-validation-stage53-'));ROOT.chmod(0o700);start=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]);source=ROOT/'source';source.mkdir();(OUT/'control-location.json').write_text(json.dumps({'root':str(ROOT),'source':str(source)})+'\n')
env={k:v for k,v in os.environ.items() if k not in ['PYTHONPATH','LD_PRELOAD','LD_LIBRARY_PATH','OPENAI_API_KEY','HF_TOKEN','HUGGING_FACE_HUB_TOKEN','AGENT_LAB_EVIDENCE_KEY']};env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',UV_CACHE_DIR=str(ROOT/'uv-cache'),UV_PYTHON_INSTALL_DIR=str(ROOT/'pythons'),UV_LINK_MODE='copy',UV_NO_PROGRESS='1',TMPDIR=str(ROOT),XDG_CACHE_HOME=str(ROOT/'cache'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
began=time.monotonic();child=None;known={};report={'terminal':False,'protocol_sha256':sha(OUT/'protocol.json'),'model_or_GPU_or_training':False,'phases':[]}
def memory():return int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
def save():
 p=OUT/'run-report.tmp';p.write_text(json.dumps(report,indent=2)+'\n');os.replace(p,OUT/'run-report.json')
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
def run(name,command,cap,expected=0):
 global child
 phase=time.monotonic();peak=0;report['active_phase']=name;save()
 with (OUT/(name+'.log')).open('wb') as log:
  child=subprocess.Popen([str(CORE),str(OUT/'exec_child.py'),str(os.getpid()),str(start),'cpu',*[str(x) for x in command]],cwd=source,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  while child.poll() is None:
   rss=sum(x['rss'] for x in owned().values());peak=max(peak,rss)
   if time.monotonic()-phase>cap or time.monotonic()-began>1200 or rss>6*2**30 or memory()<4*2**30:raise RuntimeError('CPU wall/RSS/memory guard: '+name)
   time.sleep(.2)
  rc=child.wait()
 report['phases'].append({'phase':name,'returncode':rc,'wall_seconds':round(time.monotonic()-phase,3),'peak_sampled_owned_RSS_bytes':peak});save();assert rc==expected,name
try:
 assert memory()>=8*2**30
 PRIOR=BASE/'outputs/lightning-terminal-candidate-v3-stage53-20261123'
 prior=json.loads((PRIOR/'run-report.json').read_text());oldspec=json.loads((PRIOR/'protocol.json').read_text());assert prior['terminal'] and prior['owned_after']==0 and prior['focused_passed']==5 and prior['related_passed']==53 and prior['source_files_unchanged'] and sha(PRIOR/'protocol.json')==spec['prior_protocol_sha256']
 assert {p['phase']:p['returncode'] for p in prior['phases']}['ruff-format-diff']==0
 source=Path(json.loads((PRIOR/'control-location.json').read_text())['source']);assert all(sha(source/n)==v['sha256'] for n,v in spec['files'].items())
 PY=source/'.venv/bin/python';env['PYTHONPATH']=str(source);report['inherited_same_source_checks']={'focused_passed':5,'related_passed':53,'ruff_and_format_passed':True,'original_prior_report_sha256':sha(PRIOR/'run-report.json'),'prior_failed_profile_remains_failed':True}
 manifest=json.loads((OUT/'node-manifest.json').read_text());assert sha(OUT/'node-manifest.json')==spec['node_manifest_sha256']
 binary=ROOT/'node/bin/node';binary.parent.mkdir(parents=True)
 code="from pathlib import Path;import urllib.request,hashlib,tarfile,json,os; spec=json.loads(Path("+repr(str(OUT/'node-manifest.json'))+").read_text());p=Path("+repr(str(ROOT/'node.tar.xz'))+");r=urllib.request.urlopen(spec['pinned_url'],timeout=30);total=0;f=p.open('xb');h=hashlib.sha256();exec(\"while True:\\n b=r.read(1024*1024)\\n if not b:break\\n total+=len(b)\\n assert total<=100*1024**2\\n f.write(b);h.update(b)\");f.close();assert h.hexdigest()==spec['sha256'];t=tarfile.open(p);member=t.getmember(spec['file'].removesuffix('.tar.xz')+'/bin/node');assert member.isfile() and member.size<150*1024**2;out=Path("+repr(str(binary))+");out.write_bytes(t.extractfile(member).read());out.chmod(0o700);print(json.dumps({'archive_sha256':h.hexdigest(),'archive_bytes':total,'node_binary_sha256':hashlib.sha256(out.read_bytes()).hexdigest()}))"
 run('node-download',[CORE,'-c',code],180);report['node_artifact']=json.loads((OUT/'node-download.log').read_text())
 run('node-identity',[binary,'--version'],30);assert (OUT/'node-identity.log').read_text().strip()==manifest['version']
 env['PATH']=str(binary.parent)+os.pathsep+env.get('PATH','')
 run('pyright-version',[PY,'-m','pyright','--version'],60)
 run('pyright-selected',[PY,'-m','pyright',*spec['changed_files']],180)
 run('headers',[PY,'scripts/check_headers.py'],60)
 report['ready']=True
except BaseException as e:report['error']={'type':type(e).__name__,'message':str(e)}
finally:
 stop();report.update(terminal=True,owned_after=len(owned()),source_files_unchanged=all((source/n).is_file() and sha(source/n)==v['sha256'] for n,v in spec['files'].items()),wall_seconds=round(time.monotonic()-began,3));save();print(json.dumps(report),flush=True)
raise SystemExit(0 if report.get('ready') and not report.get('error') and report['owned_after']==0 and report['source_files_unchanged'] else 2)
