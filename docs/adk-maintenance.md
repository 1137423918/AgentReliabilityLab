# A third real repository for the maintenance worker

This task applies the existing Deep Agents editing worker to **Google ADK's filesystem artifact service**. It is a repository integration, not an implementation of an ADK agent runner or a new framework adapter. The same worker already has Deep Agents path-normalization and OpenHands editor-undo tasks.

The target is fixed at `google/adk-python` commit `c81876a49911745248f2b774c02770ed211ff460`. Two service instances can race while deleting one artifact: files disappear between an existence check and recursive deletion. A correct change tolerates missing entries, preserves permission errors and leaves nested artifacts intact on Python 3.11 and newer.

The completed [four-case reference matrix](../evidence/adk-maintenance/README.md) produces identical patches with three completed tool operations each. Each case passes 1863 original tests (26 expected failures) and four external contracts. The full matrix takes 470.386 seconds; those are repeated cases of one task, and the contracts overlap the earlier upstream regressions. No neural repair or new core-test count is claimed.

## Task and acceptance

Only `src/google/adk/artifacts/file_artifact_service.py` is editable. The [reference task](../tasks/adk-artifact-delete-maintenance.json) supplies three explicit text edits corresponding to the already validated upstream candidate. It is a deterministic infrastructure control; the model does not discover a solution. The [separate model task](../tasks/adk-artifact-delete-model.json) contains a symptom prompt and file inventory, with no edit plan, and is prepared but unrun.

Both tasks require Python syntax checks and baseline verification. The worker exports into a detached worktree, creates a verification view containing the original `test_artifact_service.py`, checks its exact hash, and requires imports from that view's own `src`. A second command runs four operator-owned real-filesystem contracts outside the editable scope: permission errors, a disappearing payload, and duplicate deletion in user and session scopes. The contract code is embedded in the task, independent of the candidate file. It comes from the existing upstream contribution and does not add four new unique regressions.

The direct acceptance self-check compares unchanged production code with the reference production patch. It runs the original tests in both worktrees and rejects the original through the independent contracts. That self-check does not exercise a frozen verification view; the worker fault matrix separately exercises that feature. No new dependency environment is installed or changed.

## Fault protocol

The [fixed protocol](../benchmarks/adk_maintenance_protocol.json) binds source and task hashes. Four cases use the same task, three tool operations and acceptance commands:

1. Uninterrupted execution.
2. SIGKILL of the owned worker after its first emitted tool checkpoint, then resume the same run directory.
3. SIGKILL after patch materialization, then resume.
4. SIGKILL immediately before verification, then resume.

The existing harness allows 180 seconds to observe a fault stage, then at most 600 seconds for the resumed worker. The protocol field named `case_seconds` refers to that resumed-worker cap; it is not a strict combined 600-second deadline for observation plus resume. The source is pinned and this timer-label ambiguity is retained explicitly, rather than changing the declaration after execution. The experiment must preserve its actual failures and prove the final patches are identical; a timeout or a partially written report is not a completed matrix. No neural model, cloud call or GPU is involved in this reference matrix. A prepared model task is not a model result.

## Reproduce on an authorized CPU server

Use the already prepared ADK dependency environment for verification and the separate worker environment for the editing graph. Task commands explicitly insert the current worktree's `src` and assert the imported source path.

```sh
PATH=/path/to/adk-env/bin:$PATH /path/to/worker-env/bin/python \
  benchmarks/validate_model_task.py --repo /path/to/adk-checkout \
  --task tasks/adk-artifact-delete-maintenance.json \
  --reference-patch /path/to/production-only-reference.patch \
  --output /path/to/fresh-selfcheck
PATH=/path/to/adk-env/bin:$PATH /path/to/worker-env/bin/python \
  benchmarks/recovery_matrix.py --repo /path/to/adk-checkout \
  --task tasks/adk-artifact-delete-maintenance.json \
  --output /path/to/fresh-matrix
```

The production-only reference patch is the production file's diff from the fixed base to candidate `c71ca6a2d993ede60f9fd873b768a6d452db116f`. The upstream [draft PR #8278](https://github.com/google/adk-python/pull/8278) is separate from this worker experiment; no merge, CLA signature or maintainer approval is implied. The [original contribution evidence](../evidence/adk-artifact-cleanup/README.md) retains its broader Python 3.11/3.13 tests and public-API concurrency trials. Do not add repeated matrix tests to those historical totals or to the worker's previous 74-test suite.
