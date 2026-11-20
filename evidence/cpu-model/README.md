# Real CPU model pilot — all failed attempts retained

Qwen3-4B-Instruct-2507 generated real neural outputs on an authorized Linux CPU server.
Two separately declared variants (FP32 and dynamic INT8) each attempted normal and
checkpoint-resume modes on **one public Deep Agents maintenance problem**. All four
attempts produced **no patch** and never reached official acceptance. These are not
four independent benchmark problems or evidence of successful autonomous repair.

- [Report, request summaries and file hashes](report.json)
- [Protocol, runtime and reproduction](../../docs/cpu-model-pilot.md)
- [Pinned canonical model files](model-files.json) and [12-file verification](snapshot-verification.json)
- [FP32 protocol](fp32/protocol.json) / [INT8 protocol](int8/protocol.json)
- Exact service implementations: [FP32](sources/fp32-service.py) / [INT8](sources/int8-service.py)

Seven genuine generations are retained: two transport smokes, four maintenance
requests and one separately labelled posthoc format diagnostic. Every maintenance
request reached the generation time limit with zero parsed tool calls. Both
interruption cases had zero tool results, so model tool-progress recovery remains
unvalidated. The short diagnostic returned parenthesized JSON without native tool
tags; the strict parser returned ordinary content and executed no tool.

Do not infer intrinsic model capability, general throughput improvement or a
benchmark success rate from this time-censored, single-problem experiment. INT8
also changes numerical behavior. Both owned model services were intentionally
stopped after collection; exit 137 for FP32 records forced operator cleanup, not OOM.

Private workspace paths are replaced in public copies. The report distinguishes
original and public hashes; original request hashes are retained without full
maintenance requests, checkpoint databases, credentials or worktrees. Output
text and archived service sources retain their original bytes. The original
task is public and unchanged; model weights are not included in this repository.
