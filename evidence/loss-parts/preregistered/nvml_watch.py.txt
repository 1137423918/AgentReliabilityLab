from pathlib import Path
import argparse,hashlib,json,os,signal,sys,time
p=argparse.ArgumentParser();p.add_argument('--sdk',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--uuid-sha',required=True);p.add_argument('--index',type=int,default=1);p.add_argument('--seconds',type=int,default=3300);a=p.parse_args();sys.path.insert(0,str(a.sdk));import pynvml as nv
assert Path(nv.__file__).resolve()==a.sdk/'pynvml.py';assert hashlib.sha256(Path(nv.__file__).read_bytes()).hexdigest()=='5b7d66009922a16f382d88241c37a01faa82a1ac3aa28776041cd228f5801f13'
def txt(x):return x.decode() if isinstance(x,bytes) else x
def write(p,r):
 t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(r)+'\n');os.replace(t,p)
def end(signum,frame):raise SystemExit(0)
signal.signal(signal.SIGTERM,end);began=time.monotonic();seq=0;nv.nvmlInit()
try:
 h=nv.nvmlDeviceGetHandleByIndex(a.index);uuid=txt(nv.nvmlDeviceGetUUID(h));assert hashlib.sha256(uuid.encode()).hexdigest()==a.uuid_sha;cap=nv.nvmlDeviceGetCudaComputeCapability(h);base={'index':a.index,'uuid':uuid,'name':txt(nv.nvmlDeviceGetName(h)),'capability':'.'.join(map(str,cap)),'driver_version':txt(nv.nvmlSystemGetDriverVersion()),'watcher_pid':os.getpid(),'initialization_seconds':round(time.monotonic()-began,6)}
 while time.monotonic()-began<a.seconds:
  t=time.monotonic()
  try:
   m=nv.nvmlDeviceGetMemoryInfo(h);u=nv.nvmlDeviceGetUtilizationRates(h);procs=nv.nvmlDeviceGetComputeRunningProcesses(h);seq+=1;r={**base,'total_MiB':int(m.total//2**20),'used_MiB':int((m.used+2**20-1)//2**20),'utilization':int(u.gpu),'pids':[int(x.pid) for x in procs],'sequence':seq,'observed_monotonic':time.monotonic(),'observed_unix':time.time(),'sample_seconds':round(time.monotonic()-t,6),'process_query_scope':'cached_handle_matched_GPU_only'};write(a.output,r)
  except nv.NVMLError as e:write(a.output.with_name(a.output.name+'.error.json'),{'error_type':type(e).__name__,'observed_unix':time.time(),'last_success_sequence':seq})
  time.sleep(2)
finally:nv.nvmlShutdown()
