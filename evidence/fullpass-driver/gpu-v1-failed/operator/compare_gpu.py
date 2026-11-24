"""Close the dedicated control only after all three physical processes exit."""
from pathlib import Path
import hashlib,json,sys,os,shutil,time
BASE=Path('[SERVER_WORKSPACE]');OUT=BASE/'outputs/fullpass-driver-stage80-gpu-20261124-v1';CODE=OUT/'source';EXP=OUT/'experiment';sys.path.insert(0,str(CODE));sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
from benchmarks.training_journal import TrainingJournal
from benchmarks.training_checkpoint import inspect_checkpoint
spec=json.loads((OUT/'protocol.json').read_text());result={'status':'checking','fullstudy_training_completed':False,'text_generations':0};rows={};controllers={};journals={}
try:
 for variant in ['baseline','split-prefix','split-resume']:
  controller=json.loads((OUT/(variant+'-controller.json')).read_text());controllers[variant]=controller
  assert controller['terminal'] and controller['status']=='completed' and not controller['shutdown']['remaining_owned_processes'] and controller['own_GPU_context_absent']
  assert controller['source_and_inputs_unchanged'] and controller['closed_ledgers_unchanged']
  work=Path(json.loads((OUT/(variant+'-location.json')).read_text())['root']);r=json.loads((work/'run/report.json').read_text());rows[variant]=r
  assert r['status']=='completed' and r['standard_sparse_canary']['RNG_unchanged'] and r['frozen_parameters_unchanged'] and r['inputs_and_sources_unchanged']
 for role,lastvariant in [('continuous','baseline'),('split','split-resume')]:
  identity=rows[lastvariant]['identity'];plan=spec['trajectories'][role]
  definition={'identity':identity,'segments':plan['segments'],'forward_cap':sum(s['forwards'] for s in plan['segments']),'optimizer_cap':plan['segments'][-1]['end']}
  p=TrainingJournal(EXP/role/'journal',definition);j=p.snapshot();p.close();journals[role]=j
  assert j['status']=='clean' and j['next_segment']==len(plan['segments']) and j['updates']==2
  assert j['forward_reserved']==j['forward_completed']==definition['forward_cap']
  assert j['backward_reserved']==j['backward_completed']==39 and j['optimizer_reserved']==j['optimizer_completed']==2
  assert rows[lastvariant]['counters']=={'completed_optimizer_updates':2,'training_labels':4105,'training_sequences':39,'training_input_token_exposures':29431}
 left=rows['baseline'];right=rows['split-resume'];prefix=rows['split-prefix']
 assert left['updates']==prefix['updates']+right['updates'],'Update losses/gradient norms/scales/parameter hashes differ'
 assert left['final_adapter_sha256']==right['final_adapter_sha256']
 assert left['initial_adapter_sha256']==prefix['initial_adapter_sha256']==right['initial_adapter_sha256']
 checks={};metadata={}
 for role,report in [('continuous',left),('split',right)]:
  receipt=journals[role]['checkpoint'];directory=EXP/role/'checkpoints'/receipt['directory'];metadata[role]=inspect_checkpoint(directory,receipt['manifest_sha256'],report['identity'])
  checks[role]={'parameters_sha256':sha(directory/'parameters.safetensors'),'state_tensor_sha256':sha(directory/'state.safetensors'),'manifest_sha256':receipt['manifest_sha256']}
 assert checks['continuous']['parameters_sha256']==checks['split']['parameters_sha256'],'Final parameter tensors differ'
 assert checks['continuous']['state_tensor_sha256']==checks['split']['state_tensor_sha256'],'Optimizer or RNG tensors differ'
 for field in ['schema','counters','parameter_order','cuda_devices','state']:assert metadata['continuous'][field]==metadata['split'][field],field
 for field in ['spec_sha256','source_sha256','seed','profile','schedule_sha256']:assert left['identity'][field]==right['identity'][field]
 assert left['identity']['trajectory']=='continuous' and right['identity']['trajectory']=='split'
 actual={'logical_forward_reserved':sum(v['forward_reserved'] for v in journals.values()),'logical_forward_completed':sum(v['forward_completed'] for v in journals.values()),'backward_reserved':sum(v['backward_reserved'] for v in journals.values()),'backward_completed':sum(v['backward_completed'] for v in journals.values()),'optimizer_reserved':sum(v['optimizer_reserved'] for v in journals.values()),'optimizer_completed':sum(v['optimizer_completed'] for v in journals.values())}
 assert actual=={'logical_forward_reserved':84,'logical_forward_completed':84,'backward_reserved':78,'backward_completed':78,'optimizer_reserved':4,'optimizer_completed':4}
 assert all(sha(CODE/n)==d for n,d in spec['source_sha256'].items())
 runtime=Path('[MODEL_RUNTIME]')
 for n,d in spec['data_sha256'].items():assert sha(runtime/'data'/n)==d
 ledgers={Path('/tmp/agentlab-generation-recovery-stage52-4dmrtpsd/progress/generation-progress.json'):spec['old_ledger_sha256'],BASE/'studies/bfcl-generation-fixed250-stage75-20261124/experiment/progress/generation-progress.json':spec['closed250_ledger_sha256'],BASE/'studies/loss-parts-stage78-20261124/prepared/experiment/progress/generation-progress.json':spec['closed_loss_parts_ledger_sha256']}
 for p,d in ledgers.items():assert sha(p)==d
 result.update(status='passed',control_CLOSED=True,protocol_sha256=sha(OUT/'protocol.json'),journal_sha256={str((EXP/role/'journal/events.jsonl').relative_to(BASE)):sha(EXP/role/'journal/events.jsonl') for role in ['continuous','split']},actual=actual,unknown_charged=0,bitwise_equal_final_parameters_optimizer_scaler_all_seeded_RNG=True,per_update_loss_gradient_scale_adapter_hashes_equal=True,final_checkpoint_hashes=checks,final_adapter_sha256=left['final_adapter_sha256'],initial_adapter_sha256=left['initial_adapter_sha256'],counters_per_trajectory=left['counters'],extra_canary_calls_kept={'continuous':2,'split':4},all_three_processes_terminal_owned_zero_GPU_context_absent=True,sources_data_old_ledgers_unchanged=True,limitations='Dedicated reference seed42 first2updates only;not six-arm fullpass completion,generation accuracy or masked-benefit evidence. Clean planned boundary only,not resource/crash recovery. Controlweights never initialize fullstudy.')
except BaseException as error:
 result.update(status='failed',control_CLOSED=True,error={'type':type(error).__name__,'message':str(error)[:600]},no_retries_or_tolerance_relaxation=True)
(OUT/'comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if result['status']!='passed':raise SystemExit(2)
# Independent immutable backup of private control states; no base model is copied.
os.umask(0o077);dest=BASE/'studies/fullpass-driver-stage80-20261124';dest.mkdir(mode=0o700,exist_ok=False);files={}
for root,prefix in [(CODE,'source'),(EXP,'experiment'),(OUT,'operator')]:
 for p in root.rglob('*'):
  if not p.is_file() or p.is_symlink() or '__pycache__' in p.parts or p.name.endswith('.lock'):continue
  if prefix=='operator' and (len(p.relative_to(root).parts)!=1 or p.suffix not in ['.json','.py','.log','.jsonl']):continue
  key=prefix+'/'+str(p.relative_to(root));target=dest/key;target.parent.mkdir(mode=0o700,parents=True,exist_ok=True);shutil.copyfile(p,target);target.chmod(0o400);assert sha(target)==sha(p);files[key]={'bytes':p.stat().st_size,'sha256':sha(p)}
m=dest/'manifest.json';m.write_text(json.dumps({'files':files,'control_CLOSED':True,'logical_forwards':84,'optimizer_dispatches':4,'unknown_charged':0,'scope':'Private continuation-control states only, never full-study training initialization.'},indent=2)+'\n');m.chmod(0o400)
receipt={'relative_path':str(dest.relative_to(BASE)),'files':len(files),'bytes':sum(v['bytes'] for v in files.values()),'manifest_sha256':sha(m),'control_weights_private_not_fullstudy':True};(OUT/'private-archive-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'private_archive':receipt}),flush=True)
