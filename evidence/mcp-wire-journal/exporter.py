"""Read-only allowlisted metadata export; raw bodies and capabilities stay private."""
from pathlib import Path
import hashlib,json,os,resource,sys,tarfile,tempfile
sys.dont_write_bytecode=True
BASE=Path('/path/to/private-agent-lab');OUT=Path(__file__).resolve().parent
OLD=BASE/'outputs/mcp-wire-baseline-stage54-20261123'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2]);os.nice(19);resource.setrlimit(resource.RLIMIT_AS,(512*2**20,512*2**20));resource.setrlimit(resource.RLIMIT_CPU,(90,90))
location=json.loads((OUT/'control-location.json').read_text());source=Path(location['source']);sys.path.insert(0,str(source))
from agent_lab.request_budget import RequestBudget
from agent_lab.wire_journal import read_wire_journal
DEST=Path(tempfile.mkdtemp(prefix='agentlab-mcp-wire-export-stage54-'));DEST.chmod(0o700)
def copy(name,p):
 q=DEST/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(p.read_bytes())
def write(name,data):
 q=DEST/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_text(json.dumps(data,indent=2)+'\n')
stats={};roots={};proofs=[]
for role,profile in [('baseline',OLD),('candidate',OUT)]:
 report=json.loads((profile/'run-report.json').read_text());assert report['terminal'] and report['ready'] and report['owned_after']==0 and report['source_files_unchanged'];root=Path(json.loads((profile/'control-location.json').read_text())['root']);roots[role]=str(root)
 for n in ['protocol.json','run-report.json','exec_child.py']:
  copy(role+'/'+n,profile/n)
 operator='run_wire_baseline.py' if role=='baseline' else 'run_wire_candidate.py';copy(role+'/'+operator,profile/operator)
 logs=['identity.log'] if role=='baseline' else ['identity-before.log','identity-after.log','ruff-version.log','ruff-check.log','ruff-format-check.log','wire-unit-controls.log']
 for n in logs:copy(role+'/'+n,profile/n)
 scopes=['crash-control'] if role=='baseline' else ['crash-control','cleanup-failure','cleanup-nine','cleanup-tool-error']
 reserved=responses=unknown=events=0;cases=[]
 for folder in scopes:
  for p in sorted((root/folder).rglob('model-requests.json')):
   before=sha(p);data=json.loads(p.read_text());ident=data['identity'];budget=RequestBudget(p.parent,ident['owner_sha256'],ident['limits'],ident['journal_id']);state=budget.read();assert data==state and sha(p)==before
   case=str(p.parent.relative_to(root));copy(role+'/budgets/'+case+'.json',p);entries=state['reservations'];n=len(entries);u=sum(x['http_status'] is None for x in entries);reserved+=n;unknown+=u
   summary={'case':case,'model_POSTs_reserved':n,'HTTP_status_unknown_still_charged':u,'budget_file_sha256':before,'wire_exists':(p.parent/'wire-events.jsonl').exists()}
   if summary['wire_exists']:
    wire_path=p.parent/'wire-events.jsonl';wire_before=sha(wire_path);wire=read_wire_journal(wire_path,ident['owner_sha256'],ident['journal_id']);assert sha(wire_path)==wire_before
    requests=[e for e in wire['events'] if e['channel']=='model' and e['kind']=='client_request_attempt'];complete=[e for e in wire['events'] if e['channel']=='model' and e['kind']=='client_response'];assert len(requests)==n
    for event,entry in zip(requests,entries):assert event['body_sha256']==entry['request_body_sha256'] and event['body_bytes']==entry['request_body_bytes']
    assert len(complete)==n-u;responses+=len(complete);events+=len(wire['events']);summary.update(wire_events=len(wire['events']),complete_model_bodies=len(complete),private_wire_sha256=wire_before,tail_bytes=wire['tail_bytes'])
    allowed={'channel','kind','method','path','status','protocol_version','body_bytes','body_sha256','request_body_sha256'}
    wire['events']=[{k:v for k,v in event.items() if k in allowed} for event in wire['events']];write(role+'/wire-prefixes/'+case+'.json',wire)
   cases.append(summary);assert sha(p)==before
  for p in sorted((root/folder).rglob('*report.json')):
   copy(role+'/controls/'+str(p.relative_to(root)),p)
 stats[role]={'model_POSTs_reserved':reserved,'HTTP_status_unknown_still_charged':unknown,'complete_wire_model_bodies_exported_as_hashes':responses,'wire_events_exported_as_metadata':events,'cases':cases}
assert stats['baseline']['model_POSTs_reserved']==3 and stats['baseline']['HTTP_status_unknown_still_charged']==1
assert stats['candidate']['model_POSTs_reserved']==27 and stats['candidate']['HTTP_status_unknown_still_charged']==3 and stats['candidate']['complete_wire_model_bodies_exported_as_hashes']==24 and len(stats['candidate']['cases'])==12
write('summary.json',{'scope':'RealMCP/SDK/TCP,explicitlyscriptedmodelHTTP,zero neural/GPU; recovery of observed wireprefix only,no workflow replay','variants':stats,'new_unit_controls_passed':8,'new_MCP_fault_controls_passed':2,'existing_MCP_cleanup_controls_passed':10,'neural_requests':0,'GPU_used':False,'core130_rerun':False,'old_real_model_runs_not_regraded':True,'homepage_updated':False})
identities={}
for p in sorted(DEST.rglob('*')):
 if p.is_file():
  raw=p.read_bytes();text=raw.decode().replace(str(BASE),'/path/to/private-agent-lab')
  for role,root in roots.items():text=text.replace(root,'/path/to/'+role+'-wire-work')
  text=text.replace('/path/to/existing-ruff-runtime','/path/to/existing-ruff-runtime');public=text.encode();p.write_bytes(public);identities[str(p.relative_to(DEST))]={'original_sha256':hashlib.sha256(raw).hexdigest(),'sha256':hashlib.sha256(public).hexdigest(),'bytes':len(public),'private_paths_normalized':raw!=public}
write('export-manifest.json',{'metadata_only':True,'files':identities,'exporter_source_sha256':sha(Path(__file__))})
archive=OUT/'wire-metadata.tar.gz';assert not archive.exists()
with tarfile.open(archive,'w:gz') as t:
 for p in sorted(DEST.rglob('*')):
  if p.is_file():t.add(p,arcname=str(p.relative_to(DEST)),recursive=False)
print(json.dumps({'archive':str(archive),'sha256':sha(archive),'bytes':archive.stat().st_size,'files':len(identities)+1,'stats':{role:{k:v for k,v in d.items() if k!='cases'} for role,d in stats.items()}}),flush=True)
