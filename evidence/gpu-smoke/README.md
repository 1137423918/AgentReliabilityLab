# CUDA model and tool transport: raw-text check failed

The pinned community Qwen3.5-9B Q4_K_M artifact was loaded on one freshly admitted RTX3090. Native logs report33/33 layers offloaded and a32768 context; an owned GPU compute process was observed. **Three HTTP200 replies were saved, but the declared smoke validation did not pass overall.** This is not autonomous repository maintenance or a repair score.

## Exact three-request result

| Check | Actual result |
| --- | --- |
| Return exactly READY | Failed. Raw content includes an empty think block before READY. |
| Function-call arguments | Passed. Function selection was forced; the model emitted the declared build_id. |
| Tool result to final JSON | Passed. A read-only handler read the actual build report, and a constrained final response matched source_files4496/source_unchangedtrue. |

The raw first response is`<think>\n\n</think>\n\nREADY`, not READY. It is not stripped or regraded. The fixed [server documentation](https://github.com/ggml-org/llama.cpp/blob/4783b1145c7073bb809f4c282ff4853cbfe42954/tools/server/README.md?plain=1#L227) says reasoning-format none leaves thought tags unparsed. The visible block is empty; this is a serving-format compatibility finding, not evidence of a successful autonomous task. A future output-mode change needs its own protocol; no fourth request was sent here.

Exactly3 durable reservations,2209 request-body bytes, all200, no unobserved reservation; body hashes match saved requests. The journal is owned by protocol3c3e4503b95322cd63999396e0978099bb237651fbf8a564245771d478b9e28e. Saved usage input798/cache-read389/output59 excludes model initialization/warmup and is not total compute, billing or a throughput comparison. The model/context/compiler/resource profile differs from earlier CPU trials.

## Earlier attempts are retained

The [first service attempt](preflight-failed/outcome.json) was stopped by its own supervisor after a global nvidia-smi query timed out. No model HTTP request was sent, no layer loading was confirmed; the native process received SIGTERM(-15), then its port/process/context cleanup was observed.

The [second attempt](offload-observation-failed/outcome.json) used selected-GPU asynchronous sampling, reached health/model listing and sampled5075MiB device memory, but lacked the required layer-count log. Default service verbosity3 excludes library INFO that the pinned common/log.cpp548 maps to TRACE4. It stopped before HTTP; its native exit code was not captured and remains null. Port/owned-process/context cleanup was observed. Neither attempt is silently converted to a pass.

The final protocol enables trace4 metadata, parses the actual context fields, and waits/reaps the child. It retains the original model, inference prompts, three-request cap and numerical model settings. Both earlier attempts completed zero HTTP requests and have separate directories/protocols; no existing ledger was reset.

## Resource and cleanup scope

Two idle observations at least5s apart plus an immediate prelaunch check required architecture8.6, <=64MiB, utilization0 and no compute clients. One UUID was visible to CUDA; an owned file lock does not reserve against other users. Foreign-client observation stops only this service. Model server bound loopback with an ephemeral owner-only key file, deleted after shutdown; no credential or header is published.

Four logical CPUs/nice19,32GiB host admission/16GiB available floor, sampled16GiB tree RSS/18432MiB device ceiling;900s service/300s readiness/120s request. Host monitoring is independent of selected-GPU queries; transient diagnostic gaps are bounded to30s. CUDA virtual address space was not capped. Sampled maxima:1833648128bytes host tree RSS and6343MiB device used memory. These are not exact allocator peaks, unique physical RAM or a general model VRAM requirement. The263MiB sample at readiness may be aged and is not a model-footprint measurement.

Native exit0, no wait timeout/SIGKILL/remaining owned processes; port18851 closed, owned GPU context absent and sampler stopped. No resource guard fired. Parent-death and forced-kill branches were not fault-injected. State/journal were on local ext4.

## Evidence and limits

[Final summary](report.json), [protocol](protocol.json), [22-file runtime manifest](runtime-manifest.json), [journal](normal/model-requests.json), [checks](normal/checks.json), [request1](normal/request-1.json), [response1](normal/response-1.json), [response2](normal/response-2.json), [response3](normal/response-3.json), [selected native log](normal/server-public.log), [monitor](normal/monitor.jsonl), [shutdown report](normal/report.json). Hashes/normalization are in[artifacts.json](artifacts.json); earlier attempts have their own manifests. Task-controlled fixture wire bodies/replies and journal retain original bytes. Native public log is a selected, auth-redacted derivative; complete raw logs remain private. No binary, header, key or weight is published. Licenses accompany the evidence.

The exact source-weight revision behind community quantization remains unknown; [existing provenance](../qwen35-cpu/native-manifest.json) is retained. Function selection/final JSON are constrained, only one model and short inputs were tried; allocating32K does not test long-context accuracy.106 existing core checks were not rerun. No new upstream PR, neural patch, general success rate or production-readiness claim follows from this validation.
