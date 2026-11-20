# Bounded repair and feedback recovery

Protocol and limits: [docs/repair-loop.md](../../docs/repair-loop.md).
`report.json` binds fixed tasks, implementation hashes, tests and public files.
`experiment.json` preserves the experiment report with private paths replaced;
nested `raw_log_sha256` fields still identify original log bytes.

The reference operates on OpenHands SDK commit
`722e5d403cf75d4e032b79296cfaf178f8678a93`, editing only two production files.
Its first scripted plan adds a history reader without fixing undo ordering.
That candidate passes all 184 existing tests but fails the real directory
permission check. One additional scripted round completes the repair; it passes
the 184 tests and permission check.

Normal execution and a real parent-only SIGKILL after feedback is persisted both
finish on attempt 1, with the same 1,795-byte patch. The interrupted run records
the failed verification log hashes before the kill and checks that they remain
unchanged after resume. The old failed candidate is retained in `attempts/000`,
and the accepted candidate in `attempts/001`.

The complete project suite passes 33 tests (8 evidence, 15 worker, 10 HTTP/repair)
in 209.493 seconds. HTTP tests use an explicit fake service, including real
feedback requests, budget exhaustion, exclusive ownership and SIGKILL recovery.
They do not perform neural-model inference. Real-repository edits are also
scripted; no model success-rate improvement is claimed.

Manifests containing full candidate inputs, checkpoints, worktrees and secrets
are excluded. Public logs replace private paths and strip ANSI styling. The
top-level manifest records raw and public SHA-256 separately. Original OpenHands
code/patch context uses its [MIT license](../openhands-undo/UPSTREAM_LICENSE).

Limits: graph steps are budgeted per attempt, with a separate total attempt cap;
there is no token/cost cap. This is not an adversarial-code sandbox or a
prompt-injection evaluation. Host power loss, verifier-supervisor death and
escaping process groups are not covered. Verification may repeat if a process
dies after the command ends but before its result is recorded.
