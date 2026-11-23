from pathlib import Path
import hashlib,json,os
BASE=Path('<SERVER_BASE>');OUT=BASE/'outputs/mcp-agent-gpu-stage46-v1-20261122';spec=json.loads((OUT/'protocol.json').read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (OUT/'run-report.json').exists()
assert sha(OUT/'prior-sdk-identity.json')==spec['prior_sdk_identity_sha256']
print(json.dumps({'launch_precheck':True,'same_prior_SDK_identity':True,'new_protocol':sha(OUT/'protocol.json'),'GPU7_excluded':True}),flush=True)
python=BASE/'envs/model-request-budget-20261121/bin/python';os.execv(str(python),[str(python),str(OUT/'run.py')])
