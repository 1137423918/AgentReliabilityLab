# First neural run on external dependency reviews

Qwen3.5-9B Q4_K_M, 8192 context, 1024 output,33/33 layers on RTX3090. Two known, operator-authored tasks over independently selected real project snapshots; not held-out accuracy or a production security decision. The report catalog contains observed facts, not the derived gate answer. Gold is outside the MCP-served root. Both cases used the complete two-report catalog and optional reference submission; the canonical verifier, binder and task grader are unchanged.

| Case | Gate verdict | Evidence lineage | All8 required facts | Fixed task result | Charged model POSTs |
| --- | --- | --- | --- | --- | --- |
| Browser Use1.0.8 | Correct: cannot advance | Verified | Missed `/resolution/original_requirements_changed` | Failed |3|
| FastMCP2.12.4 | Correct: advance to compatibility testing | Verified | Complete | Passed |3|

The Browser case read the enclosing resolution object but omitted the required unchanged-requirements fact in its final selected references. The strict grader rejects the incomplete submission despite valid source/read lineage and a correct gate verdict. This is a useful observed application failure; no gold/schema/prompt fix or quality retry followed grading. The FastMCP result approves only a compatibility-test candidate:16 affected registry resolutions remain, upstream tests were not run, and no deployment/release approval is inferred.

[Per-case results](cases-summary.json), [terminal controller](controller-summary.json), [source and protocol](operator/), [native startup](native/startup-observations.json), [cleanup](cleanup.json), [export identities](export-manifest.json). Per-case directories retain budget/wire/submission/response **metadata**; request and response bodies, free prose, capabilities, weights and environments remain private. Model reported11077 prompt and1259 completion tokens across6 complete HTTP200 replies; these are backend usage fields, not an independent tokenizer measurement. Native warmup is outside HTTP-request counts.

Each case reserved3 of8 allowed POSTs,6 of16 for this new dependency-review task group. SDK retry count0; no workflow quality rerun. Every reservation matched a complete wire reply:0 unknown,0 missing wire reservations,0 tail bytes. The existing report-audit task group remains20 of32 charged, independently of this new domain; original3B generation limits/unknown charges are also independent. Its ledger was legitimately progressing concurrently on another device, never written by this application profile.

Server execution completed both tasks; successful experiment cleanup is not the same as passing both tasks. One transient GPU probe timeout was recorded without a guard breach.23 native/model files used the prior verified same-UID stat-fingerprint cache;0 files required a fresh full rehash. Processes/ports/GPU context were released, sources stayed unchanged. The exporter independently reread wire journals and recomputed only the unchanged saved-result grading, with no model call. The two-case observation does not establish general success rate, retrieval benefit or training improvement. Homepage/Profile/Pages remain frozen.
