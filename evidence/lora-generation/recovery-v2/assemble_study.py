"""CPU-only verified legacy migration; no models loaded or scores recomputed."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,shutil,sys
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--admission',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--spec',type=Path,required=True);p.add_argument('--binding',type=Path,required=True);a=p.parse_args()
sys.path.insert(0,str(a.source/'benchmarks'))
from generation_resume import import_legacy_profile,request_fingerprint,result_for_case
from generation_progress import atomic_save,digest
from agentrobustbench_baseline import inference_settings
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
spec=json.loads(a.spec.read_text());assert sha(Path(__file__))==spec['assemble_source_sha256'];assert sha(a.binding)==spec['legacy_binding_sha256'];binding=json.loads(a.binding.read_text());OLD=Path('/path/to/private-agent-lab/outputs/lora-generation-stage52-20261123');oldspec=json.loads((OLD/'protocol.json').read_text());assert sha(OLD/'protocol.json')==spec['legacy_protocol_sha256'];study=json.loads((OLD/'study-location.json').read_text());original_admission=Path(study['root'])/'admission.json';old=json.loads(original_admission.read_text());new=json.loads(a.admission.read_text());before=dict(old);after=dict(new);before.pop('driver_sha256');after.pop('driver_sha256');assert before==after
ready=json.loads((OLD/'setup-report.json').read_text());assert ready['ready'] and ready['terminal'];assert oldspec['checkpoint_manifest_sha256']==spec['checkpoint_manifest_sha256'];settings=inference_settings(argparse.Namespace(max_context=32768,max_tokens=1024))
models={'base':{'adapter_artifact_sha256':{}}}
for role in ['full32','mixed32']:
 files=ready['checkpoint_identities'][role]['files'];models[role]={'adapter_artifact_sha256':{n:files['adapter/'+n] for n in ['adapter_config.json','adapter_model.safetensors']}}
definition={'variants':['base','full32','mixed32'],'settings':settings,'model_repository':spec['model_repository'],'model_revision':spec['model_revision'],'data_sha256':new['data_sha256'],'legacy_driver_sha256':spec['legacy_driver_sha256'],'legacy_protocol_sha256':spec['legacy_protocol_sha256'],'models':models,'model_manifest_sha256':spec['model_manifest_sha256'],'checkpoint_manifest_sha256':spec['checkpoint_manifest_sha256'],'same_GPU_UUID_sha256':spec['expected_GPU_UUID_sha256'],'limits':spec['generation_limits'],'cases':[{'id_sha256':hashlib.sha256(c['id'].encode()).hexdigest(),'sample_sha256':c['sample_sha256'],'request_sha256':request_fingerprint(c,settings)} for c in new['cases']]}
sources=[]
for role in ['base','full32']:
 root=Path(json.loads((OLD/(role+'-location.json')).read_text())['root'])/'run';paths={'controller':str(OLD/(role+'-controller.json')),**{n:str(root/n) for n in ['calls.jsonl','predictions.jsonl','report.json']}};expected={'controller':binding['original_profile'][role]['controller_sha256'],**binding['original_profile'][role]['artifact_sha256']};assert all(sha(Path(paths[n]))==d for n,d in expected.items());sources.append({'variant':role,'paths':paths,'sha256':expected})
progress=import_legacy_profile(a.output/'progress',definition,new,sources);atomic_save(a.output/'progress/definition.json',definition);state=progress.snapshot();assert len(state['attempts'])==281 and len(state['results'])==280 and sum(x['state']=='reserved' for x in state['attempts'])==1;assert state['attempts'][280]['variant']=='full32' and state['attempts'][280]['case_index']==82 and state['attempts'][280].get('retry_permission')
callbacks=0;reuse=0
def forbidden():
 global callbacks
 callbacks+=1;raise AssertionError('Cached case invoked model/scorer callback')
for role,count in [('base',199),('full32',81)]:
 for index in range(1,count+1):
  row,cached=result_for_case(progress,role,index,new['cases'][index-1],forbidden);assert cached;reuse+=1
assert callbacks==0 and reuse==280
assert all(sha(Path(source['paths'][n]))==d for source in sources for n,d in source['sha256'].items())
report={'ready':True,'CPU_only_no_model_or_rescoring':True,'all199_old_new_admission_cases_equal':True,'new_admission_sha256':sha(a.admission),'definition_owner_sha256':progress.owner,'definition_file_sha256':sha(a.output/'progress/definition.json'),'legacy_attempts_imported':281,'legacy_results_imported':280,'unknown_attempts_retained':1,'cached_dispatch_controls':280,'model_or_scorer_callbacks':0,'legacy_inputs_unchanged':True,'legacy_sources':[{k:v for k,v in s.items() if k!='paths'} for s in sources],'next_Full_new_calls_required':118,'Mixed_new_calls_required':199};atomic_save(a.output/'assembly-report.json',report);print(json.dumps(report),flush=True)
