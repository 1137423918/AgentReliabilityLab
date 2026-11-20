# OpenHands as a maintenance target

The worker still runs Deep Agents / LangGraph; the target repository and public
tool acceptance are OpenHands SDK. This is not an OpenHands Agent runtime adapter.

Task definitions and reproduction instructions are in
[docs/openhands-maintenance.md](../../docs/openhands-maintenance.md).
`selfcheck/` compares unchanged source with an operator reference patch.
`recovery/` records the scripted worker's normal execution and interruption runs.
`report.json` binds both experiments to fixed tasks, source files, and hashes.

The maintenance task edits only two production files. The old upstream suite
contains 184 tests, whereas the upstream PR's 185-test evidence additionally
includes its new permanent regression. The task's fixed operator-owned permission
check distinguishes the buggy base despite all 184 old tests passing.

These are controlled unprivileged Linux filesystem faults and process-boundary
SIGKILL tests, without neural-model inference. Repeated executions of the same
184-test scope are not independent new tests or a model success rate. Checkpoint
SQLite, complete source worktrees, credentials and connection details are excluded.

Public copies replace private server/environment paths and strip ANSI styling.
The manifest lists SHA-256 of both raw files and public copies. Nested
`raw_log_sha256` fields refer to the original log bytes, not sanitized copies.
Unmodified task and patch hashes keep their original meaning.

Limits: no host power loss, supervisor death, descendants escaping process groups,
crash-atomic file/history transaction, production incident, or hostile-code sandbox
claim. OpenHands code and patch context use its MIT license, retained in
[UPSTREAM_LICENSE](../openhands-undo/UPSTREAM_LICENSE).
