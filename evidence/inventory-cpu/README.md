# Inventory-scoped ADK CPU trial — no ls, still no edit

One newly declared real Qwen3-4B Q4_K_M normal trajectory, with `file_inventory_v1` enabled. Same ADK symptom prompt, production-only file scope, model, sampling, budgets and protected acceptance as the previous focused trial. Worker-generated catalog and graph-local ls filtering/rejection change together. Code and protocol were pushed before model loading; no retrospective quota extension, retry, repair or fault injection.

**Worker return2 after1525.938seconds, not a case timeout. Eight HTTP200 replies, eight tool results; the next request was denied before network send. Zero virtual changes, patch or acceptance. Zero verified trials.** The result does not establish neural, token, latency or cost benefit.

Saved tools: inspect_python twice, read_file four times, grep twice, ls zero. The second inspection selected L754:2 but omitted expected_sha256 and returned structured error source_hash_required. SDK ToolMessage.status remained success, so the existing metadata inspector's tool_errors counter was0; this report separately records the one structured domain error. Earlier progress comments described only the SDK status count. Version binding was not weakened.

Subsequent reads cover lines1–200,751–950(including the deletion implementation),801–978 and1–50. Grep arguments return matching file paths, not context lines. The source SHA remains d0da937d1c32ae62bc5a7092597751151efab895431b2288b2bbad17f75b4e16 before/after; no edit tool was selected. Avoided directory discovery did not cause this trajectory to produce a repair.

- [Full result and observations](report.json), [pre-load public protocol](protocol.json), [exact task](task.json), [audit sequence](audit/report.json).
- [Request journal](normal/model-requests.json), [terminal error](normal/resumed.stderr.log), [native log](logs/server.log), [driver outcome](logs/trial.log).
- [Runtime](runtime.json), [launch identity](service/service.json), [clean shutdown](service/shutdown.json), [closed-port/absent-child proof](service/stopped.json), [artifact hashes](artifacts.json).
- [Task-local policy and106project checks](../file-inventory/README.md). Six fake-model checks are included within106, not neural success.

Eight admitted JSON bodies total205121bytes(max38243), below262144total/65536single caps. Request count caused termination, not bytes or the1800second case cap. Same per-request600seconds/service2400seconds/output1536tokens/graph40 and4CPU/nice19/64GiB admission/48GiB AS/36GiB RSS. Active checkpoints/worktree/scratch on localext4; no GPU. Native exit0/no forced cleanup/no guard hit, peak sampled RSS9242923008bytes; port18849closed, native child absent and no owned worker/verifier remained.

Eight saved responses report input50314/cache-read41454/output353 tokens. Difference8860 equals native completed prefill counts2585+1856+88+1651+1376+25+25+1254. All eight requests completed, no unknown in-flight reservation. Counters are not a billable-cost or general performance measurement. The previous focused trajectory's lower totals and elapsed time remain unchanged; one pair with different catalog/tool surface and host load cannot isolate causality.

Pinned ADK basec81876a49911745248f2b774c02770ed211ff460, worker coreb2afb4ae981567be60c8f6fda037e808a0601529; model/revision/native manifest unchanged from the earlier4B trial. Original1863pass26expected-failure group/four known independent filesystem contracts were preserved but not executed here, because no candidate reached acceptance. Do not add them to test scores or reference recovery controls.

No SQLite, complete conversations, headers, weights or full worktree is published. Selected metadata/log paths and terminal formatting normalized; task, protocol and request journal byte-identical. Candidate text is written only for exact task-owned paths. [ADK Apache2](UPSTREAM_LICENSE), [runner framework MIT](FRAMEWORK_LICENSE), [model Apache2](MODEL_LICENSE), [backend MIT](BACKEND_LICENSE).

Next work should change a declared model/resource hypothesis using the existing protected task; no unchanged4B repetition, relaxed source hash, fewer correctness contracts or retrospective budget reset. The successful engineering contract and failed neural trajectory remain different evidence.
