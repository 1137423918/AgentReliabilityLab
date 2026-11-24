from pathlib import Path
import json,hashlib,os,sys,shutil
B=Path('[SERVER_WORKSPACE]');O=B/'outputs/fullpass-driver-stage80-gpu-20261124-v1';E=O/'experiment';C=O/'source';sys.path.insert(0,str(C));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
from benchmarks.training_journal import TrainingJournal
spec=json.loads((O/'protocol.json').read_text());assert json.loads((O/'comparison.json').read_text())['status']=='failed';journals={};workers={}
for variant in ['baseline','split-prefix','split-resume']:
 r=json.loads((O/(variant+'-controller.json')).read_text());assert r['terminal'] and r['status']=='completed' and r['own_GPU_context_absent'] and not r['shutdown']['remaining_owned_processes'] and r['closed_ledgers_unchanged'] and r['source_and_inputs_unchanged'];workers[variant]=r['accounting']
for role in ['continuous','split']:
 plan=spec['trajectories'][role];identity={'spec_sha256':sha(O/'protocol.json'),'source_sha256':spec['source_sha256'],'seed':plan['seed'],'profile':plan['profile'],'trajectory':role,'schedule_sha256':spec['schedules_sha256'][str(plan['seed'])]};definition={'identity':identity,'segments':plan['segments'],'forward_cap':sum(s['forwards'] for s in plan['segments']),'optimizer_cap':2};p=TrainingJournal(E/role/'journal',definition);journals[role]=p.snapshot();p.close();assert journals[role]['status']=='clean' and journals[role]['next_segment']==len(plan['segments'])
for key,total in [('forward_reserved',84),('forward_completed',84),('backward_reserved',78),('backward_completed',78),('optimizer_reserved',4),('optimizer_completed',4)]:assert sum(j[key] for j in journals.values())==total
closure={'overall_status':'FAILED_bitwise_continuation_control','control_CLOSED':True,'all_workers_terminal_clean_GPU_context_absent':True,'logical_forward_reserved':84,'logical_forward_completed':84,'backward_reserved':78,'backward_completed':78,'optimizer_reserved':4,'optimizer_completed':4,'unknown_still_charged':0,'text_generations':0,'retries':0,'journal_sha256':{str((E/role/'journal/events.jsonl').relative_to(B)):sha(E/role/'journal/events.jsonl') for role in journals},'first_difference_before_restore':True,'same_initial_parameters_and_first_update_loss':True,'first_update_gradient_norm_difference':2.205371856689453e-05,'interpretation':'Different gradients/weights before any restoration;consistentwithdefaultnondeterministicGPUbackward,not evidence thatrestorecausedfirstdifference. No metric/tolerance relaxation. Fullstudy remains unallocated.'}
(O/'closure.json').write_text(json.dumps(closure,indent=2)+'\n');os.umask(0o077);dest=B/'studies/fullpass-driver-stage80-20261124';dest.mkdir(mode=0o700,exist_ok=False);files={}
for root,prefix in [(C,'source'),(E,'experiment'),(O,'operator')]:
 for p in root.rglob('*'):
  if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts or p.name.endswith('.lock'):continue
  if prefix=='operator' and (len(p.relative_to(root).parts)!=1 or p.suffix not in ['.json','.py','.log','.jsonl']):continue
  n=prefix+'/'+str(p.relative_to(root));q=dest/n;q.parent.mkdir(mode=0o700,parents=True,exist_ok=True);shutil.copyfile(p,q);q.chmod(0o400);assert sha(q)==sha(p);files[n]={'sha256':sha(q),'bytes':q.stat().st_size}
p=dest/'manifest.json';p.write_text(json.dumps({'files':files,'closure':closure,'failure_preserved':True,'control_weights_never_fullstudy_initialization':True},indent=2)+'\n');p.chmod(0o400)
r={'relative_path':str(dest.relative_to(B)),'manifest_sha256':sha(p),'files':len(files),'bytes':sum(v['bytes'] for v in files.values()),'FAILED_control_preserved':True};(O/'private-archive-receipt.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'closure':closure,'archive':r}))
