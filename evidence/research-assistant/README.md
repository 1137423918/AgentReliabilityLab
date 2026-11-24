# Local model research assistant evidence

The application connects an actual local Qwen3-4B-Instruct-2507 Q4_K_M model to the installed research MCP service, using LangGraph and an async SQLite checkpointer. The collection contains two full, versioned papers: 32 page sources and 148 indexed passages. LightRAG and MiniRAG are input papers, not graph retrieval implementations reproduced by this application.

All tests, environment setup and model execution ran on the authorized compute server. Each model profile used two sampled CPU cores, no GPU, no model warmup and no HTTP retry. Existing verified model/runtime and paper-index files were reused without re-indexing. Model and source versions are recorded in `model-and-index-provenance.json`; the original conversion receipt is [here](../native-cpu/native-manifest.json).

## Results and retained failures

The three [frozen cases](../../examples/research-assistant/tasks.json) cover a method explanation, a comparison across papers and an absent-paper request. Only the question is sent to the model; expected status and required PDF count are evaluator inputs. These are operator-authored, known-collection workflow diagnostics, not held-out QA or general Agent accuracy.

| Profile | Change | Complete replies / reserved HTTP requests | Final reference contracts |
| --- | --- | --- | --- |
| [v1](trial-v1.json) | Cold prompt processing, automatic tool selection | 4 / 5; one unknown remains charged | First case hit the 450s case deadline; two not started |
| [v2](trial-v2.json) | Native prefix cache and whole-request deadline | 16 / 16 | 0/3; free text was not accepted as final submission |
| [v3](trial-v3.json) | At most one named final function request within six turns | 18 / 18 | 0/3; final output still arrived in `content` |
| [v4](trial-v4.json) | Exact argument-only content adapter, same reference validator | 18 / 18 | 1/3; comparison and absence cases still returned plain text |
| [v5](trial-v5.json) | Final argument schema constraint with tool selection disabled for that step | 18 / 18 | 2/3; explanation and comparison submitted, absence case rejected and reached turn limit |

The final profile used four query-embedding forwards, no text encoding and zero unknown requests. First-case completion replay in a new process added zero generation/embedding requests. Case wall times were 241.489s, 201.224s and 175.250s on two CPU cores. No isolated causal timing comparison was performed.

[Source review](source-review.json) checked extracted text and four rendered physical pages. Both accepted answers have support for their core summaries; the comparison is partial and its qualitative efficiency wording is not a measured result here. The absence case chose `insufficient_evidence` but produced an empty answer and nonempty irrelevant-paper citations, so the unchanged validator rejected it. This is not successful model abstention or a 2/3 QA accuracy estimate.

[Current source controls](logs/controls-v5.log) contain 16 passing tests using real LangGraph/SQLite with scripted replies and fixture evidence, not a neural model. [Tested source hashes](tested-source-sha256.json) and [actual trial protocol](protocols/trial-v5.json) bind the published source/case bytes and budgets. Isolated runtime paths in public test logs are normalized; raw logs remain private.

The initial setup controller also stopped while copying native assets, after environment setup had succeeded and before any inference. Its [original failure](runs/setup-v1.json) and [separate bounded asset continuation](runs/assets-v2.json) are retained. Earlier engineering controls are superseded iterations and are not added together as independent tests.

A separate page-QA controller first referenced the wrong existing renderer-environment path and stopped before reading PDFs ([failure](runs/render-v2.json)). The corrected, independent [renderer profile](runs/render-v3.json) reused PyMuPDF1.26.6 and rendered four cited pages with zero neural calls. All 14 attempted operator profiles are terminal with no owned processes; the [frozen private archive receipt](private-archive-receipt.json) records 351 payloads and preserves earlier closed budgets and archives. A prepared but never-started renderer packet is not counted as an attempt.

## What the contracts establish

A supported submission must cite references actually read in an earlier tool turn. A coverage/evidence read is required before an insufficient-evidence submission, which must have no citations. Source generation and source/PDF hashes are retained. These checks establish reference lineage; they do not prove semantic entailment. The model chooses the status, prose and reference IDs.

Finalization is constrained by the application. Current code sends the original final-argument schema through the pinned backend's JSON Schema response format and disables further tool selection for that one step. It remains within the six-request case budget. Exact structured content then passes the same final-tool validator; raw responses stay private. This is not fully unforced model termination, inferred citations or acceptance of arbitrary free text.

Complete responses are durably saved before model-node checkpointing. Committed checkpoints and identical saved requests can be reused, but a tool query interrupted before its node commits can be repeated. The application does not claim exactly-once arbitrary-crash behavior, independent human answer evaluation or production/multitenant readiness.

## Published scope

Public files contain selected run metadata, scoped results, provenance, brief accepted-answer samples/source review and scripted-provider engineering test logs. The private frozen archive preserves complete model requests/responses, SQLite state, query journals and every attempted profile. Unknown calls remain charged; earlier failed profiles are not silently regraded, retried or refunded. Paper pages, full excerpts, raw model wire data, keys and mutable runtime state are not distributed here.

[Application and usage](../../docs/research-assistant.md) · [Frozen CPU runtime](../../extras/research-assistant/README.md) · [Resume project shortlist](../../portfolio/resume-shortlist-2026-11-25.md).
