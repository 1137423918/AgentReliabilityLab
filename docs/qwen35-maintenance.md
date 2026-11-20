# Qwen3.5-9B under protected maintenance grading

This experiment evaluates a newer pinned local text model on the existing public Deep Agents path-normalization problem. The prompt, editable files, fixed base and four protected acceptance commands match `deepagents-path-model-protected.json`; only the model preset and declared sampling change. Two predeclared operational trials use normal execution and a checkpoint interruption/resume. They are not independent benchmark tasks or a general success rate.

## Identity and generation policy

- GGUF publisher: `lmstudio-community/Qwen3.5-9B-GGUF`, revision `1379f25c6b505a3fc737bd7818cb09389cf807c1`.
- File: `Qwen3.5-9B-Q4_K_M.gguf`, 5,627,044,256 bytes, SHA-256 `cd76ec205963b3b33350093e6904d9de16c4e666fd104e1f632d25c7f15f2a13`. A public mirror transfers bytes; pinned metadata from the official Hugging Face host supplies size and LFS hash.
- The publisher identifies Qwen3.5-9B and llama.cpp b8185 as its sources, but does not state the exact source-weight revision. The fetched original card/config revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a` is a reference identity, not proof of quantization lineage.
- Read-only GGUF inspection: architecture `qwen35`, 427 tensors, 8,953,803,264 parameters, mixed Q4_K/Q5_K/Q6_K/F32 storage. The template SHA `a4aee8afcf2e0711942cf848899be66016f8d14a889ff9ede07bca099c28f715` matches the pinned original template. Chat EOS 248046 (`<|im_end|>`) matches the tokenizer. The model config separately uses 248044 (`<|endoftext|>`); these identify different termination markers.
- Runtime: unchanged official llama.cpp b12576, commit `4783b1145c7073bb809f4c282ff4853cbfe42954`, with the same hash-verified binary bundle and task-local runtime libraries. Runtime/library changes are not hidden behind a model swap.
- Text only: no vision projector or image input. Thinking is disabled by the declared template kwargs. The pinned runtime accepts this setting with a deprecation warning; the warning is retained.
- HTTP alias `agentlab-qwen35-9b-q4km` prevents labeling this service as the earlier 4B model. Requests use temperature 0.7, top_p 0.8, presence_penalty 1.5, top_k 20, min_p 0, repeat_penalty 1, seed 42. The standard parameters and provider `extra_body` are explicitly declared in the task. Historical task defaults remain temperature 0 without added sampling fields.

The sampling choice follows a published non-thinking preset, not the publisher's full coding benchmark conditions. Each short tool turn has a 1,536-token cap, which differs from its long-reasoning output recommendations. The 32K context, four CPU threads, single slot and other shared-node work further limit interpretation.

## Fixed limits and acceptance

One service listens only on loopback port 18845, uses `--device none` and zero GPU layers, four compute/prefill threads, one HTTP thread and one slot, nice 19, a 48 GiB address-space limit, a 36 GiB sampled RSS guard and a 2,400-second service cap. The launcher checks available memory, CPU load, model/runtime hashes and port occupancy before loading.

Each case has 600 wall seconds, 40 graph steps, at most 1,536 generated tokens per request, a 180-second client request limit, no transport retries and no extra repair round. The trials share one sequential service with prompt caching enabled; timing is not a causal comparison. In recovery, the worker is SIGKILLed at its first emitted checkpoint and resumes the same run directory within the same case budget. Only actually persisted messages/tool results can support recovery claims; a checkpoint alone does not establish edited-file recovery.

Acceptance still checks actual worktree imports, a fixed original test-file view, candidate tests, 28 operator-owned path contracts and declared Python syntax before export. The candidate test count depends on the model's edits; it is not forced to the reference patch's 119 tests. No reference patch or fixed edit plan is given to the model.

## Server preparation and execution

Use the pinned native source/binary/library preparation described in [the earlier native CPU protocol](native-cpu-pilot.md). Keep the new third-party GGUF outside this repository. With the artifact and runtime files available:

```sh
python benchmarks/inspect_qwen35_model.py \
  --llama-source /path/to/llama.cpp-4783b114 \
  --model /path/to/Qwen3.5-9B-Q4_K_M.gguf \
  --runtime-manifest /path/to/previous-native-manifest.json \
  --server /path/to/llama-server --library-directory /path/to/runtime-libs/lib \
  --source-template /path/to/pinned/chat_template.jinja \
  --output /path/to/fresh-native-manifest.json
python benchmarks/serve_llama_cpu.py \
  --server /path/to/llama-server --model /path/to/Qwen3.5-9B-Q4_K_M.gguf \
  --manifest /path/to/fresh-native-manifest.json \
  --library-dir /path/to/runtime-libs/lib --output /path/to/fresh-service \
  --alias agentlab-qwen35-9b-q4km --port 18845 --threads 4
# In another server session, put the upstream verification environment on PATH.
AGENT_LAB_MODEL_URL=http://127.0.0.1:18845/v1 \
python benchmarks/model_pilot.py --repo /path/to/deepagents \
  --task tasks/deepagents-path-model-qwen35.json \
  --output /path/to/fresh-pilot --case-deadline-seconds 600
```

Use the worker environment for `model_pilot.py` and a separately prepared upstream verification environment for task commands. Model metadata/template/config/license files and the GGUF are bound before any generation. The private prelaunch receipt records protocol SHA, task SHA, native manifest SHA and exact worker/launcher/model-adapter sources.

## Observed outcome

Both trials failed on the individual 180-second request timeout: normal after 185.324 seconds, recovery after 376.219 seconds. The 600-second case wall limits were not reached. Normal persisted no model reply; recovery retained two replies / four successful read_file results, including the first two across the deliberate SIGKILL. Neither case edited virtual files, exported a patch or ran official acceptance. The protected policies were configured but did not grade a neural candidate.

Normal prompt processing alone took 172.58 seconds for 2,442 tokens. Two replies completed on the sequential cached service; two requests were cancelled. This identifies an operational budget bottleneck, not an isolated model-quality result. Read-state continuation is observed; edited-file recovery is not exercised. The owned launcher was stopped, with a forced native-child cleanup after its ten-second grace period; the port and both processes were verified absent.

Before generation, 57 project checks ran on the authorized server: 43 passed, 14 skipped because jsonschema is absent in that worker environment. This includes an explicit fake-HTTP sampling/tool roundtrip and the launcher cleanup checks; fixtures are not model inference. The fourteen parser checks had passed in another environment and are not counted as passed here.

[Evidence and final trial outcomes](../evidence/qwen35-cpu/README.md) retain failures and distinguish metadata inspection, framework validation, actual model calls and acceptance. Historical 4B failures remain unchanged. No weights, full dialogs or checkpoint databases are included.

Sources: [Qwen's pinned model card](https://huggingface.co/Qwen/Qwen3.5-9B/tree/c202236235762e1c871ad0ccb60c8ee5ba337b9a), [the quantizer's pinned card](https://huggingface.co/lmstudio-community/Qwen3.5-9B-GGUF/tree/1379f25c6b505a3fc737bd7818cb09389cf807c1), [LangChain's `extra_body` guidance](https://reference.langchain.com/python/langchain-openai/ChatOpenAI).
