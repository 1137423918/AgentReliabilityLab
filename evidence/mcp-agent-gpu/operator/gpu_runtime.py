from pathlib import Path
import csv,datetime,hashlib,json,os,signal,subprocess,time
BASE=Path('<SERVER_BASE>');ROOT=Path(json.loads((BASE/'outputs/cuda-build-20261121/local-control.json').read_text())['local_root']);BIN=ROOT/'build-run-2/build/bin';MODEL=BASE/'models/Qwen3.5-9B-LMStudio-1379f25c/Qwen3.5-9B-Q4_K_M.gguf'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while b:=f.read(1024*1024):h.update(b)
 return h.hexdigest()
def probe(uuid=None):
 def run(args):
  p=subprocess.run(['nvidia-smi']+(['--id='+uuid] if uuid else [])+args,capture_output=True,text=True,timeout=10);assert p.returncode==0,p.stderr;return list(csv.reader(p.stdout.splitlines(),skipinitialspace=True))
 cards=run(['--query-gpu=index,uuid,name,compute_cap,memory.total,memory.used,utilization.gpu','--format=csv,noheader,nounits']);processes=run(['--query-compute-apps=gpu_uuid,pid,used_memory','--format=csv,noheader,nounits'])
 return {'observed_utc':now(),'cards':[{'index':int(r[0]),'uuid':r[1],'name':r[2],'compute_capability':r[3],'total_mib':int(r[4]),'used_mib':int(r[5]),'utilization':int(r[6]),'pids':[int(p[1]) for p in processes if p and p[0]==r[1]]} for r in cards]}
def public_card(c):return {**{k:v for k,v in c.items() if k not in ['uuid','pids']},'uuid_sha256':hashlib.sha256(c['uuid'].encode()).hexdigest(),'compute_clients':len(c['pids'])}
def available():return int(next(l.split()[1] for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')))*1024
def descendants(root,known):
 rows={}
 for p in Path('/proc').glob('[0-9]*'):
  try:
   if p.stat().st_uid!=os.getuid():continue
   s=(p/'stat').read_text().rsplit(')',1)[1].split();rows[int(p.name)]={'ppid':int(s[1]),'start':int(s[19]),'state':s[0],'rss':next((int(l.split()[1])*1024 for l in (p/'status').read_text().splitlines() if l.startswith('VmRSS:')),0)}
  except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 keep={root} if root in rows and (root not in known or rows[root]['start']==known[root]) else set()
 for _ in range(32):
  before=len(keep);keep.update(pid for pid,row in rows.items() if row['ppid'] in keep)
  if len(keep)==before:break
 keep.update(pid for pid,start in list(known.items()) if pid in rows and rows[pid]['start']==start)
 keep={pid for pid in keep if pid in rows and rows[pid]['state']!='Z'}
 for pid in keep:known[pid]=rows[pid]['start']
 return {pid:rows[pid] for pid in keep}
def stop_owned(proc,known):
 forced=False
 for sig,wait in [(signal.SIGTERM,10),(signal.SIGKILL,3)]:
  tree=descendants(proc.pid,known)
  if not tree:break
  forced|=sig==signal.SIGKILL
  for pid,row in tree.items():
   try:
    current=descendants(proc.pid,known).get(pid)
    if current and current['start']==row['start']:os.kill(pid,sig)
   except (ProcessLookupError,PermissionError):pass
  end=time.monotonic()+wait
  while time.monotonic()<end and descendants(proc.pid,known):time.sleep(.2)
 wait_timeout=False
 try:proc.wait(timeout=3)
 except subprocess.TimeoutExpired:wait_timeout=True
 return {'wait_timeout':wait_timeout,'returncode':proc.poll(),'forced_cleanup':forced,'remaining_owned_processes':list(descendants(proc.pid,known))}
