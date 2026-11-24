"""Classify cached compute PIDs with durable ownership and Linux start times."""
from pathlib import Path

def start_ticks(pid):
 return int((Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[19])

def classify_compute_pids(pids,known):
 foreign=[];exited_owned=[]
 for pid in pids:
  expected=known.get(pid)
  if expected is None:
   foreign.append(pid);continue
  try:current=start_ticks(pid)
  except (FileNotFoundError,ProcessLookupError):
   exited_owned.append(pid);continue
  except (PermissionError,OSError,ValueError,IndexError):
   foreign.append(pid);continue
  if current!=expected:foreign.append(pid)
 return {'foreign':foreign,'cached_exited_owned':exited_owned}
