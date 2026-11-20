# Google ADK: concurrent artifact cleanup

[Upstream draft PR #8278](https://github.com/google/adk-python/pull/8278) is open and **not merged**. Candidate source is [c71ca6a](https://github.com/1137423918/adk-python/commit/c71ca6a2d993ede60f9fd873b768a6d452db116f), against fixed main `c81876a49911745248f2b774c02770ed211ff460`. No issue or discussion was created. ADK's contribution guide permits describing the bug directly in the PR; The `cla/google` check has not found a matching agreement; signing or fixing the account association requires the account owner. Human maintainer review is also pending. [Observed upstream checks](upstream-status.json) are separate from server test results.

Two `FileArtifactService` instances sharing a root can both pass a versions-directory existence check. The second recursive deletion then encounters files already removed by the other call. The final fix ignores only `FileNotFoundError` through the appropriate Python-version callback; other errors still propagate. No public API, storage format or dependency changes.

| Verification | Original | Candidate |
| --- | --- | --- |
| Four new deterministic checks | 3 failed, 1 permission control passed | all 4 pass within related suites |
| Artifact service + util, Python 3.11.4 | not rerun in full | 2021 passed, 26 xfailed |
| Same suites, Python 3.13.18 | not rerun in full | 2021 passed, 26 xfailed |
| Unforced public API cleanup, 20 rounds | all 20 had missing-entry errors | 0 error rounds; parent versions removed; nested artifacts preserved |

The full suite executions overlap; four new checks are included in each 2021. No 4042-distinct-tests claim. Source-only mypy checks for Python targets 3.11 and 3.13 pass with `--follow-imports=silent --no-incremental`, not whole-repository checking. Cloud adapters in the related unit suite use the upstream fixtures' fake stores; no live cloud/model calls.

- [Report and precise scope](report.json)
- [Original/public artifact hashes](artifacts.json)
- [Candidate patch including regressions](fix.patch)
- [Original failures](logs/baseline-tests.log)
- [Python 3.11 related suite](logs/candidate-py311.log) / [Python 3.13 related suite](logs/candidate-py313.log)
- [All applicable pre-commit checks](logs/precommit.log)
- [Original public-API rounds](cases/baseline.json) / [final rounds](cases/candidate.json)
- [Runtime dependencies and exact pinned hook sources](runtime/)
- [Public reproduction script](../../benchmarks/adk_artifact_delete.py) / [protocol](../../docs/adk-artifact-cleanup.md)

An initial root-only candidate passed its narrow three-test run but [still failed all 20 unforced rounds](preflight/narrow-candidate.json) on missing descendants. It was not submitted. Those failures are retained, not relabeled as success.

Pre-commit first encountered a cache ownership mismatch, then GitHub HTTP/2 fetch failure. A later HTTP/1.1 tool download was intentionally stopped after a bounded independent network probe failed; it is not reported as successful completion. The final run uses seven configured tool tags fetched through local mirrors, with commit identities checked before transfer. Git rewrites apply only to the check process; the upstream hook configuration is unchanged. Unmatched-file hooks skip normally. The addlicense hook uses the repository's optional fallback because its executable is absent; both existing Apache header prefixes match the base byte-for-byte.

Deterministic tests use real files and control scheduling at the filesystem boundary. The standalone script makes unforced concurrent calls to the public API; the 20 rounds are not a general reliability rate or a performance comparison. Tests use two services in one Linux process, not a distributed transaction. Windows, concurrent save/delete and process crashes are untested. Recursive deletion has no blanket atomic rollback guarantee for I/O or permission errors. This is an ADK storage contribution, not a third maintenance Agent runtime adapter or neural task score.

Only explicit logs, patch, runtime receipts and JSON results are published. Private workspace/home paths and terminal formatting are normalized; original/public hashes remain separate. Generated artifact contents and directories, credentials, databases and full conversations are excluded. Google ADK code/patch context retains the [Apache-2.0 license](UPSTREAM_LICENSE).
