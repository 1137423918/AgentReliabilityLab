"""Set limits in a fresh child, avoiding preexec callbacks after monitor threads."""
import ctypes,os,resource,signal,sys
parent=int(sys.argv[1]);assert ctypes.CDLL(None).prctl(1,signal.SIGTERM,0,0,0)==0
if os.getppid()!=parent:os._exit(127)
resource.setrlimit(resource.RLIMIT_AS,(48*2**30,48*2**30))
os.execv(sys.argv[2],sys.argv[2:])
