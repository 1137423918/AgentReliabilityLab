from pathlib import Path
import json,tempfile,sys,hashlib
from openhands.tools.apply_patch.definition import ApplyPatchAction,ApplyPatchExecutor
import openhands.tools.apply_patch.definition as definition
rows=[]
for case,target in [('literal','source.txt'),('dot_alias','./source.txt'),('symlink_alias','source-link.txt'),('distinct_move','renamed.txt')]:
 with tempfile.TemporaryDirectory(prefix='apply-move-workspace-') as tmp:
  root=Path(tmp);source=root/'source.txt';source.write_text('before\n',encoding='utf-8')
  if case=='symlink_alias':(root/target).symlink_to('source.txt')
  patch='*** Begin Patch\n*** Add File: earlier.txt\n+queued\n*** Update File: source.txt\n*** Move to: '+target+'\n@@\n-before\n+after\n*** End Patch'
  result=ApplyPatchExecutor(tmp)(ApplyPatchAction(patch=patch));rows.append({'case':case,'error':result.is_error,'message':result.text,'source_exists':source.exists(),'source_content':source.read_text() if source.exists() else None,'target_exists':(root/target).exists(),'target_content':(root/target).read_text() if (root/target).exists() else None,'earlier_add_exists':(root/'earlier.txt').exists()})
report={'python':sys.version,'executor_sha256':hashlib.sha256(Path(definition.__file__).read_bytes()).hexdigest(),'cases':rows,'real_public_executor':True,'mocked_file_io':False,'neural_inference':False}
Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
