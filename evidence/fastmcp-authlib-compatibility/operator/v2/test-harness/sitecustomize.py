import os,socket
if os.environ.get('COMPAT_REPORT_ROOT'):
 original=socket.socket.connect
 original_ex=socket.socket.connect_ex
 def allowed(address):
  return not isinstance(address,tuple) or address[0] in ('127.0.0.1','localhost','::1')
 def connect(self,address):
  if not allowed(address):raise RuntimeError('External network denied in compatibility tests')
  return original(self,address)
 def connect_ex(self,address):
  if not allowed(address):raise RuntimeError('External network denied in compatibility tests')
  return original_ex(self,address)
 socket.socket.connect=connect;socket.socket.connect_ex=connect_ex
