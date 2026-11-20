# Protected grading: scripted real-repository controls

The same intentionally regressing 2,807-byte patch passes the old mutable-test policy, but fails a specific original regression under the new baseline-file view. A legitimate 1,573-byte scripted reference still passes. This is **operator-scripted infrastructure evidence, not a neural repair score**. The protected local-model task has not been run.

| Case | Candidate tests | Fixed original tests | Independent path contracts | Worker outcome |
| --- | --- | --- | --- | --- |
| Mutable grader, intentional regression | 96 passed / 23 skipped | not configured | 28 passed | ready_for_review |
| Baseline grader, identical regression | not reached | 112 passed / 1 failed | not reached | rejected |
| Protected reference | 119 passed | 113 passed | 28 passed | ready_for_review |
| Protected task on preserved old worker | not reached | capability marker rejected | not reached | rejected |

The bad candidate includes the valid path fix, replaces `regex_literal_hint` with `return None`, and marks `TestLooksLikeRegex` skipped. Its patch SHA is identical under the two policies: `41d742b5eab96ca8aa31fbe246aaa8f20ad20c1bcf979b32334e9b74375c871b`. The protected run fails `TestLooksLikeRegex::test_hint_present_for_regex`, not an unrelated setup error. Original and candidate tests overlap; their counts are not added as unique coverage.

- [Machine-readable report](report.json): fixed base, task/source hashes, patch identity, command records and actual earlier invalid text replay.
- [Final remote/local source identities](source-identities.json), including the six-check test source.
- [Artifact hashes](artifacts.json): original and public copy SHA-256 for the explicit allowlist.
- [Full server regression](logs/full-tests.log): 56 tests, **42 passed and 14 skipped**, 159.414 seconds; worker environment lacks jsonschema. The 42 comprise the previous 33, three launcher checks, and six new protection checks. Fourteen parser checks previously passed in another environment; they are not counted as passed here.
- [Six targeted protection checks](logs/targeted-tests.log): baseline-preserving grading, valid new tests and cached replay, stale-view rejection, partial view setup recovery, exit-zero verifier writes, failed-feedback integrity and invalid export.
- [Case snapshots, logs and patches](cases/): each `task.json` contains its explicit scripted plan; stage logs contain no full model dialogs.
- [Protocol and reproduction](../../docs/protected-grading.md).

The original 900-byte invalid virtual model text is replayed unchanged, with its hash in the report. The syntax policy rejects it **before worktree creation or patch export**. This is a replay of an earlier real failure, not fresh inference or a successful model repair. Python parsing uses the worker's Python 3.11 grammar, requires explicit task configuration, and does not prove semantic correctness or prevent all destructive edits.

The preserved old worker is project commit `9c2dfe7ce0859df6b83ee62f2e9915706cd5e3ba`, source SHA `d5d989872c92f5f311f41f16538cf8d2b212ac5920a711d446cc9e958d8a7384`. It ignores new fields, but the protected verifier's capability marker fails at verification; this is not startup rejection.

An earlier preflight imported Deep Agents and called `pytest.main` in the same interpreter, triggering `PytestAssertRewriteWarning` for langsmith before tests ran. The legitimate reference also failed, so **that result is not credited as successful regression rejection**. [Preflight logs and task](preflight/) are retained. The final invocation checks imports, then execs a fresh Python interpreter for pytest; the complete controls were rerun with specific failure and pass-count assertions.

These views are not OS-level read-only mounts or a hostile-code sandbox. Tracked-state, HEAD, allowed-scope and log checks protect this controlled worker protocol, not every untracked file or host/dependency side effect. No GPU, model service or neural generation was used for these controls. Historical model failures are unchanged. Private workspace/environment paths and terminal progress formatting are normalized in public copies; original/public hashes remain separate. Full worktrees, checkpoint databases, dialogs, credentials and host details are excluded. Upstream source and patch contexts retain the [MIT license](UPSTREAM_LICENSE).
