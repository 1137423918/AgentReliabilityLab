# AutoGen cancellation callbacks outside the token lock

A user cancellation callback commonly checks whether cancellation has happened, registers another cleanup action, or waits for a cleanup thread that reads the token. AutoGen's original `CancellationToken.cancel()` invokes callbacks while holding a non-reentrant lock. These operations then block on that same lock. `add_callback()` also invokes callbacks under the lock when cancellation already happened.

This contribution fixes that lock scope in AutoGen's existing API; it does not add a model or another Agent runtime adapter to this project. The upstream repository is now archived and read-only; new PR creation returned HTTP 403. Its README directs new framework development toward Microsoft Agent Framework. This work is a focused bug fix to an existing high-star SDK, not a claim that AutoGen is Microsoft's latest framework.

## Fixed subject and change

- Upstream: `microsoft/autogen`, base `8390985108cb1e3881f5f7297765758d8ad2540c`, core version 0.7.5.
- Production file: `python/packages/autogen-core/src/autogen_core/_cancellation_token.py`.
- Test file: `python/packages/autogen-core/tests/test_cancellation.py`.

`cancel()` atomically sets the cancelled flag and snapshots existing callbacks under the lock, then executes callbacks after releasing it. `add_callback()` atomically registers a callback or observes the cancelled flag, then invokes an already-due callback outside the lock. `link_future()` uses this same registration path. State mutation remains protected and repeated cancellation remains idempotent. Replacing the lock with `RLock` alone would still block a cleanup thread reading the token; the regression covers this case too.

This preserves callback exception propagation: a callback that raises can still stop the remaining callbacks in that cancellation call. It does not make arbitrary callback code nonblocking, impose a callback timeout, stop Python threads, or establish that asyncio futures may be cancelled safely from arbitrary threads. Callback completion order across concurrent registration is not promised. These are limits, not newly solved behaviors.

## Observed outcome and publication

The original source fails six new deadlock checks; its three prior cancellation tests and the added late-future compatibility check pass (6 failed / 4 passed). The candidate passes the complete autogen-core test directory: 233 passed, three existing trusted-code warnings, using two workers on Python 3.11.4. The seven added checks are included in 233. Changed-file Ruff, Mypy and Pyright checks pass. This is not the full multi-package CI matrix.

The same runtime-probe driver and final interpreter reproduce the original callback hang and complete on the candidate, with cleanup called once and both request and agent cancelled. No throughput or speedup is inferred from a timeout-truncated original. An earlier missing-test-dependency run and an initial Pyright libatomic setup failure are retained in the evidence.

The tested candidate is pushed to [the personal fork](https://github.com/1137423918/autogen/tree/fix/cancellation-callback-deadlock). Upstream PR creation was rejected because the repository is archived; **no AutoGen PR exists for this change**. This is a fork candidate, with no upstream acceptance or merge claim.

## Reproduction and checks

All execution uses the authorized Linux server's CPU, with a task-owned checkout and environment. Core runtime dependencies are installed with `uv sync --frozen --package autogen-core --no-dev`; test tools and optional provider packages are added through uv with direct versions taken from the upstream lock. Optional test packages subsequently re-resolve compatible transitive dependencies (including typing-extensions); the final environment is not an exact frozen workspace. Its installed package receipt is published with evidence. The baseline is repeated in that same final environment using an isolated original source tree, so it is not compared only with the earlier preparation environment.

```sh
cd /path/to/autogen/python
uv sync --frozen --package autogen-core --no-dev
# Prepare the test tools and optional packages recorded in the evidence runtime.
cd packages/autogen-core
../../.venv/bin/python -m pytest tests/test_cancellation.py -q
# From Agent Reliability Lab, use that same interpreter for the public API probe:
/path/to/autogen/python/.venv/bin/python benchmarks/autogen_cancel.py \
  --repo /path/to/autogen --output /path/to/fresh-cancellation-probe
```

The public probe imports the actual checked-out package, starts a real `SingleThreadedAgentRuntime` and waits until a controlled request enters its handler. A cancellation callback queries the token before cancellation is delivered to the pending work. It records stage markers and a delayed stack dump. The parent uses a 20-second limit and reaps its owned child. A timeout is called the observed callback hang only if the request entered and cleanup began but did not return; generic setup timeouts remain distinguishable.

There is no neural model, paid provider call, remote Agent service or GPU. The pending work and cleanup are controlled, so this is a real SDK cancellation reproduction rather than a production incident or a throughput benchmark. Full source-level regressions and the bounded runtime probe serve different purposes and are not counted as independent model tasks.

[Evidence and results](../evidence/autogen-cancellation/README.md). Upstream review, CLA checks and merge state are tracked separately from local validation; none is inferred from passing server tests.

Sources: [upstream contribution guide](https://github.com/microsoft/autogen/blob/8390985108cb1e3881f5f7297765758d8ad2540c/CONTRIBUTING.md), [AutoGen status and migration direction](https://github.com/microsoft/autogen), [threading locks](https://docs.python.org/3/library/threading.html#lock-objects).
