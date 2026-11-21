# Google ADK focused CPU trial — request budget exhausted, no edit

One actual Qwen3-4B-Instruct-2507 Q4_K_M normal maintenance trajectory on the existing public ADK duplicate-delete defect. It used the real model and generic existing-tool navigation guidance, not a reference implementation or scripted plan. Production-only edit scope and both original operator-owned acceptance commands were unchanged from the prepared ADK task.

The worker stopped after **913.965 seconds**, return code **2**, without a case timeout. All **eight** admitted HTTP requests completed with 200; the next call was rejected before network send. **No virtual changes, exported patch or acceptance execution. Zero verified trials.** This is one known public problem, not a held-out benchmark or a success rate.

The saved sequence is four distinct directory queries (`/src`, `/src/google`, `/src/google/adk`, `/src/google/adk/artifacts`), then four `inspect_python` calls: module outline, `FileArtifactService._delete_artifact_sync`, `FileArtifactService.list_versions`, and the first page of `FileArtifactService`. The model reached the deletion implementation but did not edit. The directory queries are distinct traversal steps, not an identical-query loop. Tool availability alone is not treated as use.

- [Full result and limits](report.json), [protocol sealed before loading](protocol.json), [exact task](task.json).
- [Saved checkpoint metadata and tool choices](audit/report.json), [terminal worker error](normal/resumed.stderr.log), [durable request ledger](normal/model-requests.json).
- [Native log](logs/server.log), [launch identity](service/service.json), [shutdown](service/shutdown.json), [closed-port / absent-child proof](service/stopped.json), [runtime](runtime.json).
- [Original and public artifact hashes](artifacts.json). No SQLite, full conversation, weights, headers or whole worktree is published. Private local/server paths and terminal formatting are normalized only in allowlisted receipts/logs. Task, protocol, request ledger and source-only candidate text remain byte-identical.

CPU-only on the authorized GPU3 node: four threads, nice19, 64GiB available-memory admission, 48GiB address-space cap, 36GiB RSS guard. Active checkpoint, worktree and scratch storage was node-local ext4; code and selected logs remained on NFS. No GPU used. Maximum admitted JSON body 22509 bytes, total 119155 of the 262144-byte cap. Request count, not total bytes or the 1800-second case wall limit, caused termination. Limits were not reset or extended.

Saved usage: input29591 / cache-read24026 / output451 tokens. The difference5565 matches the sum of eight completed native prefill records (2654,35,21,23,27,1828,565,412). These are saved-response counters and native diagnostics, not a billed-cost or general latency/capability comparison. The service exited0, no forced cleanup, sampled peak RSS9243697152bytes; listener closed and owned native child absent. Collector found no owned worker/verifier left.

Pinned model source `cdbee75f17c01a7cc42f958dc650907174af0554`, derived model SHA256 `9f1c9b5bd32d1c37502b525a677b3245a1b91fb7b71c7464f4264647998e7a06`; official llama.cpp b12576 commit `4783b1145c7073bb809f4c282ff4853cbfe42954`. Sampling0.7/top-p0.8/top-k20/min-p0/presence0, output cap1536; this is a resource-bounded configuration, not the model card's longer-output benchmark setting. [Official model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507).

Acceptance remains the pinned original ADK group (previously1863passed/26expected failures) and four reused independent filesystem contracts. **They were not executed in this failed neural trajectory**, and are not new tests. Current project100-test evidence is unchanged and not rerun. Prior three-repository scripted recovery controls and earlier neural failures remain separate; this trial does not validate recovery or migration.

Next hypothesis: a task with a complete explicit file inventory may benefit from a task-scoped tool palette that avoids unnecessary directory traversal. This is unproven and would need a new declared trial; increasing this trial's budget retrospectively is not a success.

ADK source/candidate context: [Apache-2.0](UPSTREAM_LICENSE); runner framework: [MIT](FRAMEWORK_LICENSE); model: [Apache-2.0](MODEL_LICENSE); native backend: [MIT](BACKEND_LICENSE).
