### Motivation and Context

Cancelling the task awaiting `InProcessRuntime.send_message()` cancels its response future. If the agent handler or asynchronous agent factory subsequently raises an ordinary exception, `_process_send()` calls `set_exception()` on that cancelled future. The resulting `InvalidStateError` prevents `task_done()` from running, so `stop_when_idle()` can wait indefinitely.

The regression uses the public runtime API and events to establish this ordering. It covers both an agent handler and an asynchronous factory, with a still-waiting caller as a control for each path. No model or external service is needed.

### Description

Check `future.cancelled()` before setting the exception, following the existing `CancelledError` and response paths. Queue completion and exception logging continue for the cancelled caller. A still-waiting caller receives the original agent error.

One production guard changes; the four parameterized tests use the same test-file bytes before and after the fix. The branch is based on main `aa46eddff989c13fba70c15e0ae8715b75f3fe8d` and does not depend on the separate cancellation-callback PR #14845. The earlier merged intervention-accounting fix #14656 addresses a different path.

Server validation: Linux, Python 3.11.4, the same dedicated test environment for both checkouts.

| Scope | Result |
| --- | --- |
| Four new cases against original production code | 2 cancelled-caller failures, 2 normal-error controls pass |
| Four cases with this guard | 4 pass |
| Runtime and group-chat directories | 97 pass, zero skips; includes the four cases |
| Original broader runtime/group-chat/orchestration scope, excluding the four new cases | 172 pass, 12 fail, 1 skip |
| Candidate broader scope, including the four new cases | 176 pass, 12 fail, 1 skip; identical failure IDs |
| Original pre-commit configuration, both changed files | All applicable hooks pass; source bytes unchanged |
| Mypy, both changed files | Pass |
| Wheel build | Pass; wheel runtime bytes match the tested checkout |

The scopes overlap and are not additive. The 12 broader orchestration failures remain on the unchanged base; this does not claim that the full SDK suite or upstream CI is green. The initial build invocation found no build frontend in the test environment. Packaging then passed in a separate locked build environment (`build==1.3.0`, `flit-core==3.12.0`, within the declared backend range). The original test environment and tested source bytes remained unchanged; successful tests were not rerun for that tooling correction.

Focused reproduction after applying only the new test file to the base checkout:

```sh
python -m pytest tests/unit/agents/runtime/test_runtime.py::test_late_send_failure_after_sender_cancellation
```

AI assistance: Codex produced the implementation, tests and server validation. Human author review and upstream review remain pending; this PR is a draft.

### Contribution Checklist

- [ ] The code builds clean without any errors or warnings
- [ ] The PR follows the [SK Contribution Guidelines](https://github.com/microsoft/semantic-kernel/blob/main/CONTRIBUTING.md) and the [pre-submission formatting script](https://github.com/microsoft/semantic-kernel/blob/main/CONTRIBUTING.md#development-scripts) raises no violations
- [ ] All unit tests pass, and I have added new tests where possible
- [ ] I didn't break anyone :smile:
