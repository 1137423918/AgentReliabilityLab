"""Receive public artifact routes through stdin; never persist signed URLs."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import base64,hashlib,json,os,resource,shutil,sys,tempfile,time,urllib.request
OUT=Path(__file__).resolve().parent;BASE=Path('/authorized/agent-lab');spec=json.loads((OUT/'protocol.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();assert sha(Path(__file__))==spec['operator_sha256'] and not (OUT/'run-report.json').exists();old=BASE/'outputs/neural-bootstrap-stage49-v1-20261123';SOURCE=Path(json.loads((old/'control-location.json').read_text())['local_root']);assert sha(SOURCE/'model-manifest.json')==spec['model_manifest_sha256'];manifest=json.loads((SOURCE/'model-manifest.json').read_text());CACHE=BASE/'models/Qwen2.5-3B-Instruct-aa8e7253-stage49-v1';assert json.loads((CACHE/'agentlab-owner.json').read_text())['revision']==manifest['revision']
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:4]);os.nice(19);resource.setrlimit(resource.RLIMIT_AS,(8*2**30,8*2**30));assert shutil.disk_usage('/tmp').free>=16*2**30
WORK=Path(tempfile.mkdtemp(prefix='agentlab-model-ingest-stage49-'));WORK.chmod(0o700);MODEL=WORK/'model';MODEL.mkdir();(OUT/'control-location.json').write_text(json.dumps({'local_root':str(WORK),'model_root':str(MODEL)})+'\n');(OUT/'control-location.json').chmod(0o600)
mounts=[(x.split(' - ')[0].split()[4],x.split(' - ')[1].split()[0]) for x in Path('/proc/self/mountinfo').read_text().splitlines()];assert max([(len(p),f) for p,f in mounts if str(WORK).startswith(p.rstrip('/')+'/')])[1] in ['ext4','xfs','btrfs']
report={'terminal':False,'protocol_sha256':sha(OUT/'protocol.json'),'operator_sha256':sha(Path(__file__)),'model_manifest_sha256':spec['model_manifest_sha256'],'local_model_execution':False,'GPU_model_started':False,'files':[]};started=time.monotonic();data=None
def save():(OUT/'run-report.json').write_text(json.dumps(report,indent=2)+'\n')
save()
def verify(p,row):
 h=hashlib.sha256() if row['lfs_sha256'] else hashlib.sha1();digest=hashlib.sha256();size=0
 if not row['lfs_sha256']:h.update(('blob '+str(row['bytes'])+'\0').encode())
 with p.open('rb') as f:
  while block:=f.read(2*1024*1024):h.update(block);digest.update(block);size+=len(block)
 assert size==row['bytes'] and h.hexdigest()==(row['lfs_sha256'] or row['git_blob_sha1'])
 return digest.hexdigest()
try:
 data=json.load(sys.stdin);assert set(data)=={x['path'] for x in manifest['files']}
 def receive(row):
  n=row['path'];payload=data[n];p=MODEL/n;assert p.parent==MODEL;part=p.with_name(n+'.part');prefix=CACHE/('.stage49-prefix-'+n);offset=0;begin=time.monotonic()
  if payload['kind']=='inline':part.write_bytes(base64.b64decode(payload['body']))
  else:
   assert row['lfs_sha256'] and payload['kind']=='cdn'
   if prefix.exists():shutil.copyfile(prefix,part);offset=part.stat().st_size
   assert offset<row['bytes'];headers={'Range':'bytes='+str(offset)+'-','User-Agent':'AgentLab-ResearchArtifact'}
   with urllib.request.urlopen(urllib.request.Request(payload['url'],headers=headers),timeout=45) as response:
    if offset:assert response.status==206 and response.headers.get('Content-Range','').startswith('bytes '+str(offset)+'-')
    size=offset
    with part.open('ab' if offset else 'wb') as f:
     while block:=response.read(2*1024*1024):
      size+=len(block)
      if size>row['bytes'] or time.monotonic()-begin>1200 or time.monotonic()-started>1800:raise TimeoutError('Artifact guard')
      f.write(block);(WORK/(n+'.progress.json')).write_text(json.dumps({'bytes':size,'expected':row['bytes']})+'\n')
   payload['url']=None
  digest=verify(part,row);os.replace(part,p)
  result={'path':n,'bytes':row['bytes'],'sha256':digest,'upstream_digest_verified':True,'resumed_prefix_bytes':offset,'route':'official-primary-CDN-through-SSH-stdin' if row['lfs_sha256'] else 'official-primary-inline-through-SSH-stdin','wall_seconds':round(time.monotonic()-begin,3)};print(json.dumps(result),flush=True);return result
 with ThreadPoolExecutor(max_workers=2) as pool:report['files']=list(pool.map(receive,manifest['files']))
 validated={'repo_id':manifest['repo_id'],'revision':manifest['revision'],'files':report['files'],'all_files_verified':True,'total_bytes':sum(x['bytes'] for x in report['files']),'model_loaded':False,'GPU_used':False,'no_local_model_execution':True,'signed_URLs_persisted':False}
 (MODEL/'agentlab-validated.json').write_text(json.dumps(validated,indent=2)+'\n')
 for row in manifest['files']:
  p=CACHE/row['path'];tmp=CACHE/('.verified-ingest-'+row['path']);assert not tmp.exists()
  if p.exists():assert verify(p,row)==next(x['sha256'] for x in report['files'] if x['path']==row['path'])
  else:shutil.copyfile(MODEL/row['path'],tmp);verify(tmp,row);os.replace(tmp,p)
 (CACHE/'agentlab-validated.json').write_text(json.dumps(validated,indent=2)+'\n');report['all_artifacts_verified']=True;report['shared_cache_copy_verified']=True
except BaseException as error:report['error_type']=type(error).__name__
finally:
 if data:
  for v in data.values():v.pop('url',None)
 data=None;report.update(terminal=True,wall_seconds=round(time.monotonic()-started,3));save();print(json.dumps({'terminal':True,'all_artifacts_verified':report.get('all_artifacts_verified',False),'shared_cache_copy_verified':report.get('shared_cache_copy_verified',False),'error_type':report.get('error_type'),'signed_URLs_persisted':False}),flush=True)
raise SystemExit(0 if report.get('all_artifacts_verified') and report.get('shared_cache_copy_verified') and not report.get('error_type') else 2)
