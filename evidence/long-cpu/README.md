# Longer-budget real CPU model trial: no patch

One newly declared normal trial of the public Deep Agents path-normalization task reached its **1800-second case limit** (observed 1800.069s). The worker was killed/reaped at that cap; this is different from the historical 180-second individual-request failures. **Zero virtual edits, exported patch or maintenance acceptance.** No operator patch was substituted.

Five model replies and six successful tool results were saved: **five `read_file` and one `grep`**. Although `inspect_python` was declared and its use requested in the system instruction, it was never selected. Six HTTP requests were reserved: five received 200 headers, the last was interrupted and remains charged. Total request-body bytes 174278 are within the declared 262144 limit; neither the request count nor byte budget was exhausted.

| Persisted reply | Reported input tokens | Reported cache read | Output tokens |
| --- | ---: | ---: | ---: |
| 1 | 2732 | 0 | 94 |
| 2 | 4487 | 2825 | 82 |
| 3 | 6889 | 4568 | 93 |
| 4 | 8883 | 6981 | 82 |
| 5 | 9024 | 8964 | 64 |

These five replies report 32015 input tokens, 23338 cache reads and 415 output tokens. Input minus cache reads is 8677; native completed-request prompt-evaluation counters agree. **This excludes the canceled sixth request's incomplete work** and is not a full-trial compute, billed-token or money total. The first actual HTTP body exactly matches the historical AST-capable context control (SHA `e2ce33815b5be194a967159c9edeb2a621de1b8edba3b1ccd4e5ac659cd5e245`); its reported 2732 input tokens also match that reference prefix count. The subsequent retrieval path is model-chosen and differs from the operator-planned controls.

- [report.json](report.json), [pilot.json](pilot.json), [protocol.json](protocol.json), [task.json](task.json): declared budgets, actual outcome and input/source identity.
- [audit/report.json](audit/report.json): read-only graph-state audit, selected per-turn tool arguments/usage, hashes, no changed files and no new model requests. It reconstructs graph channel state rather than treating a raw delta checkpoint as a complete message list.
- [request journal](normal/model-requests.json), [worker trace](normal/resumed.stdout.jsonl), [worker error log](normal/resumed.stderr.log): persistent transport charges and five completed tool checkpoints. `status.json` was last written as running before SIGKILL; it is a historical snapshot, not evidence of a live process.
- [native log](logs/server.log), [runtime](runtime.json), [service identity](service/service.json), [shutdown](service/shutdown.json), [stopped receipt](service/stopped.json): actual weight loading/inference, resource guards, final request cancellation and graceful native shutdown. Sampled peak RSS 10529038336 bytes; no RSS/service-wall guard triggered. The launcher exited 143 after the orchestrator's termination signal, its native child exited 0, and the task port is closed.
- [artifacts.json](artifacts.json): 18 allowlisted transfers; protocol, task and request journal are byte-identical. Private paths are normalized in logs/receipts. No checkpoint database, full dialog, weight or whole worktree is published.

No GPU, fault injection, model-progress recovery, new core-test count or autonomous patch success. The driver itself exits 0 after recording a failed trial; the worker's actual exit is -9 and `verified_trials` is 0. A longer request budget and an available source tool did not make this one run complete. Different host, tools and budgets prevent causal comparison with older attempts. The separate ADK model task is prepared and was not run.

[Reproduction and scope](../../docs/long-cpu-maintenance.md). Historical failures remain at [qwen35-cpu](../qwen35-cpu/README.md). Referenced source and backend retain the accompanying [upstream](UPSTREAM_LICENSE) and [backend](BACKEND_LICENSE) licenses.
