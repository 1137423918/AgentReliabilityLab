import hashlib,importlib.metadata as m,json,torch,transformers,accelerate,openai,pyarrow,psutil
from pathlib import Path
assert torch.__version__=='2.6.0+cu124' and torch.version.cuda=='12.4';flags=torch._C._cuda_getArchFlags();assert 'sm_60' in flags
from transformers.models.qwen2.modeling_qwen2 import Qwen2ForCausalLM
import inspect
print(json.dumps({'versions':{d.metadata['Name']:d.version for d in m.distributions()},'torch':torch.__version__,'CUDA_build':torch.version.cuda,'compiled_arch_flags':flags,'Qwen2ForCausalLM_imported':True,'module_source_sha256':{o.__name__:hashlib.sha256(Path(inspect.getfile(o)).read_bytes()).hexdigest() for o in [Qwen2ForCausalLM]},'GPU_model_started':False}))
