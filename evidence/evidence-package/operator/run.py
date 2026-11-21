from pathlib import Path
import hashlib,json,os,resource,shutil,signal,subprocess,tarfile,tempfile,time

OUT=Path(__file__).resolve().parent;BASE=Path('__SERVER_BASE__');CORE=BASE/'envs/model-request-budget-20261121/bin/python';UV=BASE/'tools/uv-x86_64-unknown-linux-gnu/uv'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();spec=json.loads((OUT/'protocol.json').read_text())
assert not (OUT/'run-report.json').exists() and sha(Path(__file__))==spec['operator_sha256'] and sha(OUT/'source.tar.gz')==spec['source_archive_sha256']
ROOT=Path(tempfile.mkdtemp(prefix='agentlab-evidence-package-stage44-'));ROOT.chmod(0o700);CODE=ROOT/'code';CODE.mkdir();assert subprocess.check_output(['stat','-f','-c','%T',str(ROOT)],text=True).strip() in ['ext2/ext3','xfs','btrfs']
(OUT/'control-location.json').write_text(json.dumps({'local_root':str(ROOT)})+'\n');(OUT/'control-location.json').chmod(0o600)
with tarfile.open(OUT/'source.tar.gz') as t:t.extractall(CODE,filter='data')
for name,expected in spec['source_files_sha256'].items():assert sha(CODE/name)==expected,name
boot=json.loads((BASE/'outputs/mcp-agent-20261121/control-location.json').read_text());SDK=Path(boot['local_root'])/'isolated-sdk/bin/python';assert SDK.parent.parent.resolve().name=='isolated-sdk-v2'
affinity=sorted(os.sched_getaffinity(0));assert len(affinity)>=4;os.sched_setaffinity(0,affinity[:4]);os.nice(19);resource.setrlimit(resource.RLIMIT_AS,(32*2**30,32*2**30))
available=lambda:next(int(s.split()[1])*1024 for s in Path('/proc/meminfo').read_text().splitlines() if s.startswith('MemAvailable:'));assert available()>=12*2**30
env={k:v for k,v in os.environ.items() if not k.startswith(('LLAMA_ARG_','GGML_')) and k not in ['LD_PRELOAD','OPENAI_LOG','HTTPX_LOG_LEVEL','AGENT_LAB_EVIDENCE_KEY','OPENAI_API_KEY']};env.update(PYTHONPATH=str(CODE),TMPDIR=str(ROOT),CUDA_VISIBLE_DEVICES='',PYTHONUNBUFFERED='1',OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',MKL_NUM_THREADS='4',UV_PYTHON=str(CORE),UV_PROJECT_ENVIRONMENT=str(ROOT/'runtime'),UV_DEFAULT_INDEX='https://pypi.org/simple',UV_LINK_MODE='copy')
project=ROOT/'runtime-project';project.mkdir()
for name in ['pyproject.toml','uv.lock']:shutil.copyfile(CODE/'extras/mcp-evidence'/name,project/name)
assert sha(project/'uv.lock')==spec['runtime_lock_sha256']
runtime=ROOT/'runtime/bin/python';work=ROOT/'installed-work';work.mkdir();shutil.copytree(CODE/'corpus',work/'catalog');shutil.copyfile(CODE/'benchmarks/evidence_package_controls.py',ROOT/'installed-controls.py')
expected={n:sha(CODE/'agent_lab'/n) for n in ['evidence_audit.py','evidence_service.py','evidence_mcp.py']};(ROOT/'expected-source.json').write_text(json.dumps(expected)+'\n')
report={'protocol_sha256':sha(OUT/'protocol.json'),'source_archive_sha256':spec['source_archive_sha256'],'phases':[],'terminal':False,'neural_requests':0,'GPU_used':False,'model_started':False};driver=None;identity=None;groups=set();started=time.monotonic()
save=lambda:(OUT/'run-report.json').write_text(json.dumps(report,indent=2)+'\n')
def ticks(pid):
 try:return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
 except (OSError,IndexError):return None
def owned():
 result=[]
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   if str(ROOT).encode() in (p/'cmdline').read_bytes() or (p/'cwd').resolve().is_relative_to(ROOT):
    fields=(p/'stat').read_text().rsplit(')',1)[1].split();result.append({'pid':int(p.name),'pgrp':int(fields[2]),'sid':int(fields[3]),'start_ticks':fields[19]})
  except (OSError,ValueError,IndexError):pass
 return result
def stop():
 if driver is not None and driver.poll() is None:
  assert ticks(driver.pid)==identity;os.killpg(driver.pid,signal.SIGTERM)
  try:driver.wait(timeout=15)
  except subprocess.TimeoutExpired:
   assert ticks(driver.pid)==identity;os.killpg(driver.pid,signal.SIGKILL);driver.wait(timeout=10)
def run(name,args,cap,cwd=CODE,clean=False):
 global driver,identity
 begin=time.monotonic();guard=None;peak=0;child_env=dict(env)
 if clean:child_env.pop('PYTHONPATH',None)
 with (OUT/(name+'.log')).open('wb') as log,(OUT/(name+'-monitor.jsonl')).open('w') as monitor:
  driver=subprocess.Popen([str(x) for x in args],cwd=cwd,env=child_env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);identity=ticks(driver.pid);groups.add(driver.pid)
  while driver.poll() is None:
   memory=available();rss=0
   for p in Path('/proc').iterdir():
    if not p.name.isdigit():continue
    try:
     fields=(p/'stat').read_text().rsplit(')',1)[1].split()
     if int(fields[3])==driver.pid:rss+=int(fields[21])*os.sysconf('SC_PAGE_SIZE')
    except (OSError,ValueError,IndexError):pass
   elapsed=time.monotonic()-begin;peak=max(peak,rss);monitor.write(json.dumps({'elapsed_seconds':round(elapsed,3),'available_memory_bytes':memory,'owned_session_rss_bytes':rss})+'\n');monitor.flush()
   if elapsed>cap or time.monotonic()-started>1500 or memory<8*2**30 or rss>8*2**30:
    guard='phase_deadline' if elapsed>cap else 'job_deadline' if time.monotonic()-started>1500 else 'memory_floor' if memory<8*2**30 else 'owned_rss';stop();break
   time.sleep(.5)
  rc=driver.wait()
 row={'phase':name,'returncode':rc,'wall_seconds':round(time.monotonic()-begin,3),'guard_reason':guard,'peak_sampled_owned_session_rss_bytes':peak};report['phases'].append(row);save();print(json.dumps(row),flush=True);driver=None;identity=None
 if rc or guard:raise RuntimeError('Phase failed: '+name)
def interrupted(sig,frame):raise KeyboardInterrupt('Operator signal '+str(sig))
for sig in [signal.SIGTERM,signal.SIGINT,signal.SIGHUP]:signal.signal(sig,interrupted)
save()
try:
 metadata="import json,importlib.metadata as m;print(json.dumps({d.metadata['Name']:d.version for d in m.distributions()}))"
 run('core-identity-before',[CORE,'-c',metadata],60);run('builder-identity-before',[SDK,'-c',metadata],60)
 ruff=BASE/'envs/langflow-lfx-20261121/bin/ruff';run('ruff',[ruff,'check','agent_lab/evidence_mcp.py','agent_lab/evidence_service.py','benchmarks/mcp_evidence_server.py','benchmarks/evidence_package_controls.py','packages/evidence-service'],90)
 run('runtime-sync',[UV,'sync','--project',project,'--frozen','--no-install-project','--no-default-groups'],360,cwd=ROOT,clean=True)
 run('runtime-identity-before',[runtime,'-I','-c',metadata],60,cwd=work,clean=True)
 run('build',[SDK,CODE/'packages/evidence-service/build.py','--output',ROOT/'wheel'],90)
 receipt=json.loads((ROOT/'wheel/build-receipt.json').read_text());wheel=ROOT/'wheel'/receipt['wheel'];assert receipt['all_canonical_module_bytes_identical'] and sha(wheel)==receipt['sha256'];report['wheel']=receipt;save()
 run('wheel-install',[UV,'pip','install','--python',runtime,'--offline','--no-deps',wheel],30,cwd=work,clean=True)
 run('installed-dependency-check',[UV,'pip','check','--python',runtime],30,cwd=work,clean=True)
 run('installed-controls',[runtime,'-I',ROOT/'installed-controls.py','--work',work,'--expected-source',ROOT/'expected-source.json'],180,cwd=work,clean=True)
 report['installed_controls']=json.loads((work/'report.json').read_text());assert report['installed_controls']['passed']==8 and report['installed_controls']['failed']==0
 run('full-core',[CORE,'-m','unittest','discover','-s','tests','-v'],600)
 full=(OUT/'full-core.log').read_text();assert 'Ran 130 tests' in full and full.rstrip().endswith('OK');report.update(full_core_passed=130,full_core_skipped=0,new_core_test_count=0)
 run('core-identity-after',[CORE,'-c',metadata],60);run('builder-identity-after',[SDK,'-c',metadata],60);run('runtime-identity-after',[runtime,'-I','-c',metadata],60,cwd=work,clean=True)
 for name in ['core','builder']:
  assert json.loads((OUT/(name+'-identity-before.log')).read_text())==json.loads((OUT/(name+'-identity-after.log')).read_text())
 before=json.loads((OUT/'runtime-identity-before.log').read_text());after=json.loads((OUT/'runtime-identity-after.log').read_text());assert after.pop('agentlab-evidence')=='0.1.0' and before==after
 report.update(original_core_and_builder_SDK_versions_unchanged=True,new_runtime_only_added_own_wheel=True,all_frozen_sources_unchanged=all(sha(CODE/n)==d for n,d in spec['source_files_sha256'].items()),runtime_lock_unchanged=sha(project/'uv.lock')==spec['runtime_lock_sha256'],installed_corpus_unchanged=all(sha(work/'catalog'/n.relative_to(CODE/'corpus'))==sha(n) for n in (CODE/'corpus').rglob('*') if n.is_file()));assert report['all_frozen_sources_unchanged'] and report['installed_corpus_unchanged'] and report['runtime_lock_unchanged']
except BaseException as exc:report['operator_error']={'type':type(exc).__name__,'message':str(exc)}
finally:
 stop();left=owned();report['cleanup_owned_groups']=sorted({x['pgrp'] for x in left if x['sid'] in groups})
 for group in report['cleanup_owned_groups']:
  try:os.killpg(group,signal.SIGTERM)
  except ProcessLookupError:pass
 deadline=time.monotonic()+10
 while owned() and time.monotonic()<deadline:time.sleep(.2)
 report.update(owned_processes_after=owned(),terminal=True,wall_seconds=round(time.monotonic()-started,3));save();print(json.dumps({'terminal':True,'full_core_passed':report.get('full_core_passed'),'installed_controls_passed':report.get('installed_controls',{}).get('passed'),'operator_error':report.get('operator_error'),'owned_processes_after':len(report['owned_processes_after'])}),flush=True)
raise SystemExit(0 if report.get('full_core_passed')==130 and report.get('installed_controls',{}).get('passed')==8 and not report.get('operator_error') and not report['owned_processes_after'] else 2)
