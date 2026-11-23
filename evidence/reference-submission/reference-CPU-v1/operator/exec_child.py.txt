import ctypes,os,resource,signal,sys
parent,start,mode=int(sys.argv[1]),int(sys.argv[2]),sys.argv[3]
ctypes.CDLL(None).prctl(1,signal.SIGTERM)
assert os.getppid()==parent and int(open('/proc/'+str(parent)+'/stat').read().rsplit(')',1)[1].split()[19])==start
if mode=='cpu':resource.setrlimit(resource.RLIMIT_AS,(32*2**30,32*2**30))
else:assert mode=='gpu' and resource.getrlimit(resource.RLIMIT_AS)==(-1,-1)
os.execv(sys.argv[4],sys.argv[4:])
