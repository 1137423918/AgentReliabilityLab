# One longer-budget real-model CPU maintenance trial

This is a new, separately declared trial of the same public Deep Agents path-normalization problem. It retains the symptom prompt, allowed two-file scope, Python syntax protection, fixed original tests and 28 independent contracts. It does not replace the earlier 180-second-request failures or establish a general repair rate.

The [completed trial](../evidence/long-cpu/README.md) reaches the 1800-second case limit after five saved model replies and six tool results, with no virtual edit, patch or acceptance. The model chooses five reads and one grep, never the available `inspect_python`. Six requests and 174278 request-body bytes remain within transport limits. The incomplete sixth request is charged rather than refunded.

Five saved responses report 32015 input tokens, 23338 cache-read tokens and 415 output tokens. The 8677 input-minus-cache-read tokens match the native completed-request prompt-evaluation totals. This is incomplete response-level accounting, excluding canceled work, not money or whole-trial compute. The actual first request's SHA and 2732 reported input tokens match the earlier AST-capable reference control; that does not make the model follow its operator-defined retrieval plan.

The [task](../tasks/deepagents-path-model-long-cpu.json) combines the existing `python_source_v1` tool with persistent request-budget accounting. Its [protocol](../benchmarks/long_cpu_protocol.json) fixes one **normal** trial, 600 seconds per non-streaming request, 1800 seconds for the case, 1536 output tokens per request, 40 graph steps, zero retries and no repair rounds. HTTP limits are eight requests, 65536 bytes per request and 262144 cumulative request-body bytes. No interruption is injected, so this trial cannot demonstrate model-progress recovery.

## Model and resource identity

The existing Qwen3.5-9B Q4_K_M bytes and original official llama.cpp b12576 libraries are unchanged. Model SHA is `cd76ec205963b3b33350093e6904d9de16c4e666fd104e1f632d25c7f15f2a13`; backend commit is `4783b1145c7073bb809f4c282ff4853cbfe42954`. Thinking is disabled, text only, with no GPU layers. Sampling stays temperature 0.7, top_p 0.8, presence_penalty 1.5, top_k 20, min_p 0, repeat_penalty 1 and seed 42.

The existing launcher gates require at least 64 GiB available RAM and sufficient CPU headroom. One checked host failed memory admission and another failed CPU admission; the selected authorized host passed both. It uses four compute threads at nice19, one HTTP thread, one inference slot, a 32768-token context, 48 GiB address-space limit and 36 GiB sampled RSS guard. The service is restricted to loopback and a 2400-second lifetime. No occupied GPU is used, including cards with zero utilization but allocated memory.

The selected CPU host differs from the earlier pilot. Additional tools, persistent HTTP limits and larger budgets also differ. Progress or wall-time differences therefore do not isolate a model-capability, tool-effectiveness or CPU-performance cause. No warm-up generation is performed; only health and model-identity endpoints precede the task. Logical reference token counts remain separate from actual response usage and native timing logs.

## Execution and interpretation

Start the verified service with the existing [launcher](../benchmarks/serve_llama_cpu.py), then point the worker's `AGENT_LAB_MODEL_URL` at its loopback `/v1` endpoint and run:

```sh
PATH=/path/to/verification-env/bin:$PATH /path/to/worker-env/bin/python \
  benchmarks/single_model_trial.py --repo /path/to/deepagents \
  --task tasks/deepagents-path-model-long-cpu.json \
  --protocol benchmarks/long_cpu_protocol.json --output /path/to/fresh-trial
```

The driver checks its protocol/task/source hashes before execution. It records success only if the actual worker exits 0 with a `ready_for_review` result; a generated edit, tool call or passed syntax check is insufficient. Patch review must still check whether the full prompt, including requested regression coverage, was satisfied. Failure, in-flight request reservations and partial virtual state remain evidence rather than being replaced by an operator patch.

The recorded orchestration starts and cleans up its own identity-checked service and driver. An independently read-only checkpoint audit retrieves state without invoking any model, retaining only selected tool/usage metadata and candidate text rather than full private dialogs. The worker core is unchanged; this adds an experiment entry point and task, without enlarging or rerunning the previous 74-test suite.
