# AutoGen cancellation callback lock scope

A real public-API deadlock reproduction and a tested **fork candidate**. The upstream repository is archived/read-only: new PR creation returned HTTP 403. **No AutoGen upstream PR was created.** [Publication receipt](upstream-status.json) · [Candidate branch](https://github.com/1137423918/autogen/tree/fix/cancellation-callback-deadlock).

- Base: `8390985108cb1e3881f5f7297765758d8ad2540c`, autogen-core 0.7.5; candidate `2475b3c` (full identity in report).
- Original cancellation file with final regressions: **6 failed / 4 passed**, 33.23 seconds. Six failures cover callbacks reading state, nested registration/repeated cancel, and waiting for another thread reading state, both before and after cancellation. The added late-future compatibility test also passes on the original.
- Candidate complete **autogen-core test directory: 233 passed / 3 warnings**, 7.86 seconds, Python 3.11.4, two workers. Seven added checks are included, not added again. Warnings are existing trusted FunctionTool config-loading warnings. This is not all AutoGen packages, the complete CI matrix, or a model score.
- Changed-file Ruff 0.4.8 checks pass; Mypy 1.13.0 has no issues in the two changed files; Pyright 1.1.389 reports zero errors/warnings/informations for those files.

## Real runtime probe

[Original](cases/baseline/report.json) starts an actual `SingleThreadedAgentRuntime`, enters a controlled pending request, then emits cleanup-entry and hangs while reading its token. A delayed [stack dump](cases/baseline/stderr.log) identifies `is_cancelled()` called from the callback under `cancel()`. The parent reaps its owned child after its 20-second budget; return -9 is intentional containment, not normal shutdown.

[Candidate](cases/candidate/report.json), with the same driver and final interpreter, completes: one cleanup invocation, pending request cancelled, agent handler cancelled, runtime closed. The controlled work is synthetic but the SDK/runtime and token are real. No model, GPU, paid API or external Agent service. The original is censored by a timeout; this is not a speedup/throughput comparison.

## Evidence and scope

- [report.json](report.json), [runtime.json](runtime.json), [tooling.json](tooling.json): result and source/tool/environment identities.
- [fix.patch](fix.patch): minimal production/test change, retained under [upstream MIT](UPSTREAM_LICENSE).
- [logs/baseline-tests.log](logs/baseline-tests.log), [logs/candidate-core.log](logs/candidate-core.log): scopes differ; no full-original-suite comparison is claimed.
- [logs/format.log](logs/format.log), [logs/mypy.log](logs/mypy.log), [logs/pyright.log](logs/pyright.log).
- [artifacts.json](artifacts.json): explicit transfer allowlist, original/private and normalized public hashes. Generated summary/license/publication receipt are outside that transfer manifest.
- `preflight/` and `cases/preflight/` retain initial tests and runtime attempts. The first broader test run had 157 passes and two collection errors from missing email-validator/asyncio_atexit; it is not counted as a successful full run. Initial Pyright failed because its task-local Node could not load libatomic; only that process's library path was changed to existing task-local libraries, leaving the system and other environments unchanged.

Initial runtime installation used uv's frozen core selection; later optional test dependencies re-resolved compatible transitives. Final installed versions are recorded; this is not an exact frozen all-extras workspace. An isolated original source tree repeats the baseline in the final interpreter/environment.

Callbacks remain synchronous. A callback can still block itself or raise before later callbacks run; no timeout, exception isolation or forced thread termination was added. Cross-thread asyncio future loop-affinity is a separate open [PR #8359](https://github.com/microsoft/autogen/pull/8359); its inspected diff did not fix user callback re-entry. This patch does not claim to solve that separate issue. No neural repair or additional Agent-runtime adapter was implemented. [Protocol and reproduction](../../docs/autogen-cancellation.md).
