# LFX checkpoint numeric state and recomputation

A tested four-file repair, with public patch and evidence. **The Langflow candidate branch has not been pushed, and no upstream PR has been created.** GitHub rejected both Git push and the documented fork-branch sync because the existing `public_repo` token lacks `workflow` scope when importing release-branch workflow history. The repair itself changes no workflows. Permission is pending; [exact publication status](upstream-status.json) is separate from test validation.

- Upstream release base: `4d3b965c658ae147f3204b0a17bbb63b1f4f722e`, `release-1.14.0`; validated local commit `36ba5a3ae27e17f80acd7304cbdde4807652b174`. This local commit identity is not a claim that the commit is published in the fork.
- Original source plus final new test file: **12 failed / 2 passed**, 7.01 seconds. Nine encoder checks and three actual Graph/SQLite non-finite cases fail; finite Data and Graph controls pass.
- Candidate complete `graph/checkpoint` and `services/durable` directories: **105 passed / 5 existing deprecation warnings**, 8.70 seconds, Python 3.13.18. All 14 added checks are included, not added again. These are related directories, not full monorepo CI.
- Candidate broad graph + durable directories: **682 passed / 3 failed / 6 skipped / 1 xfailed / 5 warnings**, 247.93 seconds. This run is **not green**. Two catalog-policy identity failures reproduce on original source. One existing three-second scheduler wait times out in this broad run; both phases pass in isolation on original and candidate (2/2 each), but the broad timeout remains unresolved. No timing/speedup claim is made.
- Ruff / `make format_backend` pass, with 1,581 materialized Python files unchanged. Applicable commit hooks pass: case/line endings/whitespace, Ruff, logged-exception rules and secret detection. Unrelated hooks correctly skip.

## SQLite probe and connected Graph regression

The same [public driver](../../benchmarks/lfx_checkpoint_numeric.py) uses actual LFX tagged encoding, GraphCheckpoint and SQLite save/reopen/load. Nine non-finite cases (NaN and ±Infinity × scalar/nested/Data) lose their number to None without a drop marker in the original; three finite controls survive. The candidate explicitly marks those nine cases opaque and preserves the finite controls: 3/12 -> 12/12 meet checkpoint policy. This is a controlled serialization probe, not itself Graph execution or a model score.

The separate upstream regression connects producer and consumer components with `.set()`, executes the producer, saves to a real SQLite database, reopens it and resumes Graph. It verifies producer built/drop state, correct restored numeric output and the downstream comparison result. Component configurations use strings so the flow definition itself remains JSON-safe. Recompute preserves non-finite runtime results for downstream use rather than treating a saved null as completed state.

## Receipts

- [report.json](report.json), [runtime.json](runtime.json): scope, versions, source/driver hashes and installed package receipt.
- [fix.patch](fix.patch): four-file repair (production encoder, two regression helpers/tests, developer feature note), under [upstream MIT](UPSTREAM_LICENSE).
- [baseline tests](logs/baseline-tests.log), [105 focused tests](logs/candidate-focused.log), [broad suite including all failures](logs/candidate-broad.log).
- [original catalog checks](logs/catalog-baseline.log), [original scheduler checks](logs/scheduler-baseline.log), [candidate scheduler checks](logs/scheduler-candidate.log).
- [original probe](cases/baseline/report.json), [candidate probe](cases/candidate/report.json).
- [format](logs/format.log), [applicable commit hooks](logs/commit-hooks.log), [artifacts.json](artifacts.json): explicit allowlist and original/public hashes. Generated summary, README, license and publication status are outside that transfer manifest.

`preflight/` keeps the first cold baseline, an initial test-only mistake treating `_call_order` as an accumulating execution counter, the broad run missing sparse-checkout benchmark scripts, and hook setup. The test assertion was replaced with actual numeric outputs and the original rerun with the final test file; production was unchanged by this test correction. The scripts were restored from the same base before the final broad run. Missing pre-commit was handled with a separate task-owned persistent tool environment after an isolated temporary tool install; the frozen LFX runtime was not modified to add tooling.

All experiments run on the authorized Linux CPU server; no neural model, paid provider or GPU. Databases, credentials, private helpers and server identities are excluded. Public logs normalize private paths and terminal formatting; original/private hashes remain distinct from public hashes.

## Limits

Native floats in supported checkpoint containers/model fields only; this is not arbitrary serializer losslessness or support for every numeric library. Raw non-finite model fields are conservatively dropped even when a custom serializer intentionally represents them another way. Flow definitions must already be JSON-safe. Older null-corrupted checkpoints cannot recover their original numbers. Recomputing can repeat producer side effects and does not provide exactly-once execution. General API-output sanitization and checkpoint wire schema stay unchanged. No Agent-runtime adapter or autonomous model repair result was added. [Reproduction protocol](../../docs/lfx-checkpoint-numeric.md).
