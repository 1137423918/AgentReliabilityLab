# Protected ADK GPU maintenance: not started

A separate task/protocol was declared and pushed before each launch. The first check failed on a missing model.sha256 protocol alias before starting a model. The corrected declaration retained the same task, model, sampling and numerical budgets; fresh admission then found no eligible idle compute8.6 GPU. Both attempts sent zero model HTTP requests and created no request journal. No model editing, patch, acceptance or106-core-test result is claimed. Both failures are retained here; no GPU was allocated.

Prepared task: `tasks/adk-artifact-delete-model-gpu.json`; first declaration `benchmarks/adk_gpu_protocol.json`, corrected declaration `benchmarks/adk_gpu_observed_protocol.json`. A future launch needs new admission and a new immutable output root; these completed attempts must not be restarted or their records overwritten.
