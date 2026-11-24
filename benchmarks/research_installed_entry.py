"""Invoke the installed CLI callable with real E5 and durable test instrumentation.

No model substitution. This is the installation test harness, not a service quota.
The controller creates identity.json/events.jsonl once before this process starts.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
from agentlab_research.research_cli import main

budget=Path(sys.argv[1]);identity=json.loads((budget/'identity.json').read_text());pending=None

def observer(phase,event):
    global pending
    import torch
    assert torch.version.cuda is None and not torch.cuda.is_initialized()
    with (budget/'writer.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        assert json.loads((budget/'identity.json').read_text())==identity
        raw=(budget/'events.jsonl').read_bytes();assert len(raw)<1024**2 and (not raw or raw.endswith(b'\n'))
        rows=[json.loads(line) for line in raw.splitlines()];reserved=[r for r in rows if r['phase']=='reserved']
        totals={kind:sum(r['inputs'] for r in reserved if r['kind']==kind) for kind in ['text','query']}
        if phase=='reserved':
            assert pending is None and len(reserved)<identity['caps']['forwards']
            assert totals[event['kind']]+event['inputs']<=identity['caps'][event['kind']+'_inputs']
            pending=len(reserved)+1
        else:
            assert pending is not None and reserved[-1]['sequence']==pending and all(reserved[-1][k]==event[k] for k in event)
        row={'sequence':pending,'phase':phase,**event,'identity_sha256':hashlib.sha256((budget/'identity.json').read_bytes()).hexdigest()}
        with (budget/'events.jsonl').open('a') as stream:stream.write(json.dumps(row,sort_keys=True)+'\n');stream.flush();os.fsync(stream.fileno())
        if phase=='completed':pending=None

main(sys.argv[2:],embedding_observer=observer)
