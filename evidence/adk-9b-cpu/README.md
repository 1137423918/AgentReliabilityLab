# ADK inventory task with Qwen3.5-9B on CPU

One declared normal trajectory, one known public defect; **no edit, patch or acceptance**. The worker stopped at its eight-request cap after **1721.383 seconds**, return code2, not the1800-second case deadline. No retry, repair round, fault injection or retrospective limit extension.

The same symptom prompt, editable file, ADK base c81876a49911745248f2b774c02770ed211ff460, inventory/source-tool features and protected acceptance were retained from the4B inventory trial. Model family, quantized artifact, template and presence penalty changed together; no size-only, latency, cost or causal comparison. The declaration was committed and pushed before model load. Protocol SHA256: `c99e6f7ad9976d60fd23aae66bab63237f58a696d602b26d6d6b7f19dbdaaba1`. Source hashes pin project0892198cfb2b53ce4d4e0c954c1a622f0e445134.

Eight saved AI replies each chose read_file, reading successive100-line pages1–800 of978. No inspect_python, search, ls or editing call was selected. All eight results contain source-page headers; no structured source-tool error was observed. Original file remains SHA256 `d0da937d1c32ae62bc5a7092597751151efab895431b2288b2bbad17f75b4e16`. Audit reconstructs stopped state read-only and invokes neither model nor tools. A pending model node records the denied next send, not a running model.

Eight HTTP200 reservations total201769 request-body bytes, maximum39392; the ninth send was denied before HTTP. All eight native generations completed. Saved usage: input49032, cache-read40062, output596; input-minus-cache8970 equals native logged prefill counts2717+839+957+930+907+937+875+808. These are saved-reply accounting, not full compute, billing or a general performance measure.

## Identity and unchanged limits

LMStudio-community/Qwen3.5-9B-GGUF revision1379f25c6b505a3fc737bd7818cb09389cf807c1, text-only Q4_K_M,5627044256bytes, SHA256cd76ec205963b3b33350093e6904d9de16c4e666fd104e1f632d25c7f15f2a13. Exact source-weight revision used by the quantizer remains unknown; official reference c202236235762e1c871ad0ccb60c8ee5ba337b9a is metadata only. [Existing provenance](../qwen35-cpu/native-manifest.json).

Non-thinking temperature0.7/top_p0.8/top_k20/min_p0/repeat1/presence1.5 follows the general [official model-card guidance](https://huggingface.co/Qwen/Qwen3.5-9B); output1536 and context32768 are our resource limits, not the card's longer benchmark setting. Native backend b12576/4783b1145c7073bb809f4c282ff4853cbfe42954 is the existing pinned CPU bundle.

Request600s/case1800s/service2400s; eight requests,65536single/262144cumulative bytes,40graph steps. Four CPU threads/nice19,64GiB available-memory admission,48GiB address-space/36GiB RSS limits; active checkpoint/worktree/temp on local ext4. **No GPU used**. Native server exited0 without forced cleanup, sampled peak RSS10820079616bytes; port18850 closed, native child absent, owned worker/verifier count0.

The existing106 engineering checks (six inventory checks included) were not rerun and are not neural successes. The protected original ADK1863pass/26expected-failure group and four external contracts were not executed because no candidate reached acceptance. No accepted neural patch is claimed.

## Artifacts and privacy

[Protocol](protocol.json), [task](task.json), [summary](report.json), [read-only audit](audit/report.json), [request journal](normal/model-requests.json), [stop reason](normal/resumed.stderr.log), [service cleanup](service/stopped.json), [native log](logs/server.log), [driver log](logs/trial.log).17 allowlisted artifacts are hash-listed in[artifacts.json](artifacts.json); only private paths/terminal formatting in metadata and logs are normalized. Task, protocol and journal retain original bytes. No SQLite, full conversation, headers, weights or full worktree is published. ADKApache2, frameworkMIT, backendMIT and modelApache2 notices accompany the evidence.

The stock38-library server bundle has no CUDA backend. A compiler was found by read-only inspection, but no GPU backend build, allocation, offload or acceleration test occurred in this stage. Next work can prepare a separate pinned GPU runtime using CPU; actual GPU validation still needs admitted idle resources. Existing CPU runtime, historical failures and dated PDF snapshot remain unchanged.
