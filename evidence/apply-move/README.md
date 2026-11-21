# OpenHands apply_patch: prevent same-path move file loss

On base `885242b563b1d2695d6c7b3d4bfe642f1c8838a3`, `*** Move to:` can resolve to its source. The executor queues the edited write and source removal at the same resolved path: the public tool returns `Done!`, but the file is gone. Literal, `./` and in-workspace symlink aliases all reproduce this with actual files. The same four-case program is run before and after; a distinct-path move is the successful control. No filesystem calls are mocked and no model is involved.

The seven-line executor change rejects equal resolved paths before any queued operation executes. The existing `DiffError` observation reports the problem, source bytes and symlink stay intact, and an earlier queued Add File does not land. Normal moves, tool schemas and public constructors remain unchanged. This is not general I/O transaction rollback or concurrent-filesystem isolation.

## Observed server validation

- New self-move checks on original executor: **3 fail**,19 deselected. Original live tool independently reports success while deleting the source in all three cases.
- Candidate apply_patch suite: **22 pass** including four new checks.
- Related apply_patch/file_editor/default-tool parity suite: **203 pass / zero skipped**, one retained pytest-forked `CallSpec2` deprecation warning. The22 focused cases are included in203; do not add them together, or add either to the separate116 Agent Lab core checks.
- Four-case candidate live workflow: all three invalid moves return an error with source content retained and no earlier queued write; distinct-path move still updates the destination and removes its source.
- All applicable per-file pre-commit hooks pass for source and tests, including Ruff, Pyright and repository gates. YAML/agent-server hooks without matching files are normally skipped; no checks or revisions were removed.

Dedicated Linux/Python3.13.18 environment, committed lock unchanged,232 installed distributions recorded. Four CPU cores/nice19/private ext4,48GiB per-process address-space ceiling,16GiB sampled owned-session RSS and12GiB available-memory floor on validation phases; hooks360s/live120s/related600s deadlines. Guards did not trigger; the final inspection observed no owned processes. No GPU allocation, neural calls, autonomous repair or upstream CI-success claim.

## Retained setup and validation failures

The first upload targeted a missing output directory; no experiment started. The first two pre-commit attempts failed while fetching the external yamlfmt hook repository: HTTP/2 interruption, then HTTP/1.1 empty reply. Neither reached applicable checks. The existing task cache on GPU3 was copied read-only to an absent path on GPU5 after verifying archive SHA and unchanged tracked hook code. Its HEAD matches the GitHub API's official0.2.1 tag commit `752eb7b8990459b8134765a395eeee06f87d0f17`; generated untracked build/egg-info directories are declared. Hooks then ran normally. Original caches were not overwritten; no hook/security bypass or mutable-tag update.

The first actual source hook invocation reformatted the new error string; other applicable hooks passed. The formatted source was synchronized and the entire file hook set rerun successfully. An expanded-suite command referenced an old tool-name test filename and exited4 during collection; the current `tests/cross/test_default_tool_names.py` was selected from the actual tree. The corrected203-case group passed with unchanged production code and assertions. Failures are preserved, not regraded.

## Reproduction

Use a dedicated authorized Linux server checkout and the base/candidate revision shown in report.json. Run `UV_FROZEN=1 make build` with a writable private pre-commit cache. No dependency or lockfile changes are needed.

```sh
uv run pre-commit run --files openhands-tools/openhands/tools/apply_patch/definition.py
uv run pre-commit run --files tests/tools/apply_patch/test_apply_patch_executor.py
uv run pytest tests/tools/apply_patch -v
uv run pytest tests/tools/apply_patch tests/tools/file_editor tests/cross/test_default_tool_names.py -v
# Execute this repository's four-case reproduction with the SDK checkout environment:
/path/to/openhands/.venv/bin/python benchmarks/openhands_apply_move.py result.json
```

The public-entrypoint reproduction uses only temporary workspaces. To repeat the regression counterfactual, keep the candidate test file while restoring only the executor to the fixed base revision; select `-k same_resolved_path` and expect three failures. Restore the candidate executor afterwards.

Primary files: report.json, baseline-live.json, candidate-live.json, baseline-regression.log, candidate-focused.log, candidate-related-corrected.log, the protocol files and runtime.json. Original/public artifact hashes identify metadata-path normalization; source snapshots use `.py.txt` to avoid accidental test discovery. PR status is tracked separately when a draft is submitted; validation is not human review or a merged contribution.

Upstream [draftPR#7050](https://github.com/OpenHands/software-agent-sdk/pull/7050) is open and unmerged. Server validation above is separate from upstream CI: test workflows currently require maintainer authorization (`action_required`). The description validator is skipped while draft; the human-only placeholder remains unchanged. Current four-PR status snapshot is upstream-snapshot.json.
