# Google ADK repository maintenance and recovery

**All four reference-plan worker cases finish `ready_for_review` with the same patch and three completed tool edits.** This is the third real target repository for the existing Deep Agents editing worker, after Deep Agents and OpenHands. It is not an ADK agent-runner adapter or a neural maintenance result.

The production-only candidate is byte-identical to the production file in the earlier ADK draft PR #8278. Each case passes **1863 original tests with 26 expected failures**, then four operator-owned filesystem contracts. These contracts are reused from the earlier upstream contribution; they are not four new unique regressions. Repeated cases and overlapping historical suites must not be summed.

| Case | Interruption | Final tool results | Patch |
| --- | --- | ---: | --- |
| Uninterrupted | None | 3 | Identical |
| Checkpoint | Real SIGKILL after first tool result | 3 | Identical |
| Materialized | Real SIGKILL after patch export | 3 | Identical |
| Before verification | Real SIGKILL at the emitted boundary | 3 | Identical |

The baseline/reference self-check runs unchanged original tests in both worktrees. The unchanged implementation fails three independent contracts and passes the permission-error control; the reference passes all four. The direct self-check does not exercise frozen verification; the four actual worker cases do. Their frozen test hashes and candidate source hashes are checked separately.

- [report.json](report.json), [matrix.json](matrix.json), [protocol.json](protocol.json): scope, results, task/source binding and fault observations.
- [source-proof.json](source-proof.json): each primary and frozen-view production file matches SHA `9aad80d134d1ebb4034d630cfbad0a546700920a16d5179bec761cc97abdcd7a`; each frozen test file matches the original base SHA.
- [selfcheck.json](selfcheck.json), `selfcheck/`, `cases/`: explicit negative control, reference acceptance, result/verification records, original logs, patches and actual interrupted/resumed traces.
- [execution.json](execution.json), [matrix log](logs/matrix.log): server commands and wall-time receipts. Full four-case matrix took 470.386 seconds. The legacy harness permits 180 seconds for fault observation plus 600 seconds for the resumed worker; it does not enforce a combined600-second deadline. The original protocol's `case_seconds` label is retained with that clarification. The observed complete matrix itself was below 600 seconds.
- [reference-task.json](reference-task.json), [prepared-model-task.json](prepared-model-task.json), [reference.patch](reference.patch), [artifacts.json](artifacts.json): exact task/patch bytes and 56 allowlisted transfer artifacts. The separate symptom-only model task is **prepared, unrun**.

No worker-core change, new model inference, cloud API, GPU, or rerun/increase of the prior 74-test core suite. Existing ADK dependency environments are unchanged. Original pytest plugin warnings remain in the logs; no whole-repository CI claim. Checkpoint databases, full worktrees and private dialogs are excluded. Source/tests retain the accompanying [upstream Apache 2.0 license](UPSTREAM_LICENSE).

[Architecture, reproduction and limits](../../docs/adk-maintenance.md).
