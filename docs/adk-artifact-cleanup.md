# Google ADK: concurrent artifact cleanup

Two `FileArtifactService` instances can share a filesystem root. When both delete the same artifact, `exists()` and `shutil.rmtree()` are separate operations: the other deleter can remove the version directory, a payload, or metadata between them. Original source at `c81876a49911745248f2b774c02770ed211ff460` reports `FileNotFoundError` instead of completing cleanup.

The candidate installs a missing-entry callback for `rmtree`: ignore only `FileNotFoundError` and let other errors propagate. Python 3.11 uses `onerror`'s exception tuple; 3.12+ uses `onexc`. It does not enable `ignore_errors`, change paths/metadata, add dependencies, or replace the service's existing pruning of empty parents.

The initial root-only candidate passed its narrow tests but still failed all 20 unforced concurrent trials on disappearing payload/metadata files. It was not submitted. The final change covers disappearance during traversal too; the initial failure is retained rather than relabeled as success.

[Upstream draft PR #8278](https://github.com/google/adk-python/pull/8278) is open, not merged. Prepared with Codex; no human review, CLA signature or maintainer approval is claimed.

## Server verification

- Original source with four new checks: three failures, one permission-error control passed. The new cases cover two deleters after the existence check in user/session scopes, a payload removed between listing and unlink, and an actual POSIX permission failure before payload removal.
- Final related suites (`test_artifact_service.py` and `test_artifact_util.py`): **2021 passed, 26 xfailed** on Python 3.11.4, and the same counts on Python 3.13.18. These are overlapping executions, not 4042 distinct tests; the four new checks are included in each 2021.
- Source-file mypy checks for Python 3.11 and 3.13: no issues, using `--follow-imports=silent --no-incremental`. This is not whole-repository type checking.
- Unforced public-API cleanup: two real service instances, three parent versions and a nested artifact, 20 rounds. Original: every round had a missing-entry error. Final: no error in any observed round, no parent versions left, all nested contents preserved. Thread scheduling is uncontrolled; this is not a general reliability rate or a performance comparison.

Use a fresh environment with the chosen ADK checkout installed and its artifact-test dependencies. Run on an authorized Linux CPU server:

```sh
python -m pytest tests/unittests/artifacts/test_artifact_service.py \
  tests/unittests/artifacts/test_artifact_util.py -q
python /path/to/AgentReliabilityLab/benchmarks/adk_artifact_delete.py \
  --output /path/to/fresh-output --rounds 20
```

The benchmark uses public `save_artifact`, `delete_artifact`, `load_artifact` and `list_versions`, and leaves generated files in its fresh output directory for inspection. No model, GPU, cloud API or user artifact is used. The upstream deterministic regressions control scheduling with a barrier/event and perform real filesystem operations.

The actual permission control verifies its error is reported and that its unreadable version's payload remains intact. Recursive filesystem deletion is not a transaction: this does not promise that every possible permission or I/O failure leaves every file unchanged. Concurrent save/delete, process crash during deletion, hostile-filesystem isolation, Windows and a full ADK repository test matrix were not evaluated.

This is a contribution to ADK's artifact service, not a third Agent runtime adapter for this project. The running maintenance adapter remains Deep Agents / LangGraph. [Evidence, original/public hashes and upstream status](../evidence/adk-artifact-cleanup/README.md).

The [Python shutil reference](https://docs.python.org/3/library/shutil.html#shutil.rmtree) documents `onexc` in 3.12 and the 3.13 behavior that ignores missing descendants but still raises for a missing top-level path.

All applicable configured pre-commit checks passed using the exact pinned hook sources supplied through process-only Git mirror rewrites after server GitHub networking failures. Unmatched-file hooks skipped normally. The optional addlicense executable was absent, so that hook used the repository fallback; the existing source/test license-header prefixes were checked unchanged against the base. [Tool identities](../evidence/adk-artifact-cleanup/runtime/tooling.json) and failed setup logs are retained.
