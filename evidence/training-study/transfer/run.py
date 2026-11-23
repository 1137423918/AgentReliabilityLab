from pathlib import Path
import hashlib,json,os,resource,shutil,time
OUT=Path(__file__).resolve().parent;spec=json.loads((OUT/'protocol.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(Path(__file__))==spec['transfer_sha256'];assert not (OUT/'transfer-report.json').exists()
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2]);os.nice(19);resource.setrlimit(resource.RLIMIT_AS,(2*2**30,2*2**30));resource.setrlimit(resource.RLIMIT_CPU,(60,60))
SOURCE=Path('/private/prepared-pairs-stage47/prepared');TARGET=OUT/'inputs';TARGET.mkdir(mode=0o700)
rows=[];began=time.monotonic()
for n,d in spec['paired_input_sha256'].items():
 src=SOURCE/n;assert sha(src)==d;dst=TARGET/n;shutil.copyfile(src,dst);dst.chmod(0o600);assert sha(dst)==d and sha(src)==d
 rows.append({'file':n,'bytes':dst.stat().st_size,'sha256':d,'source_and_copy_verified':True})
r={'terminal':True,'files':rows,'source_unchanged':True,'no_model_or_training':True,'wall_seconds':round(time.monotonic()-began,3)};(OUT/'transfer-report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
