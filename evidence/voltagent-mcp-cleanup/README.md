# VoltAgent MCP session-registration cleanup

Follow-up to [PR #1562](https://github.com/VoltAgent/voltagent/pull/1562), tested
commit `afa92332ed938c750f452cda8b5a68cbc7b6067e`. The
[first patch](../voltagent-mcp-notifications/README.md) prevented notification
calls from rejecting because of disconnected targets. A
[review](https://github.com/VoltAgent/voltagent/pull/1562#discussion_r4666416427)
identified that the bridge Sets still retained closed/request server objects.
The [dated PR snapshot](pr-status.json) records that review thread as resolved
by the reviewer after the follow-up. Native Actions run45190965225 remains
`completed/action_required`, awaiting upstream approval; this is not CI success.

The follow-up unregisters session servers on close, including HTTP/SSE cleanup,
request-handling errors and base shutdown. Stateless servers remain registered
while their response is active and are released on response finish/close. Base
transport reconnection registers the server again without duplicating handlers.
This targets retained notification-server references, not every possible source
of memory growth or per-client subscription ownership.

## Final same-fixture comparison

Linux CPU / Node22.23.5 / pnpm8.10.5 / Vitest3.2.4 / MCP SDK1.30.0, reusing the
first patch's frozen dependency environment. Original lockfile SHA
`fa866ef0b4476afa12b798892884ef1d3ade2c07c01cf9abe2ab2f95c0c66c75` stayed unchanged.
No dependency installation or dependency-package rebuild occurred in this stage;
the MCP-server package itself was rebuilt. No model or GPU was used.

| Final validation | Result |
| --- | --- |
| Reviewed first PR head `fffed261` plus final lifecycle fixture | 8 fail |
| Cleanup candidate plus that identical fixture | 8 pass |
| Complete MCP-server package suite | 23 pass |
| Package source typecheck | Pass |
| Strict check of both new regression files | Pass |
| MCP-server build; changed-TypeScript lint; Markdown format | Pass |

The23 include the4 notification and8 lifecycle cases; counts are not added.
Lifecycle controls use real HTTP and MCP SDK connections, external SSE lifecycle
callbacks, linked in-memory base reconnection, injected request failure, and a
gate-controlled real tool function. They cover repeated completed stateless
JSON/SSE requests, HTTP session termination, SSE close, unconnected shutdown,
request errors, reconnect, and preserving an unfinished streaming response.
This is package validation, not whole-monorepo or upstream CI success.

The final lifecycle fixture was identical before/after the production change:
SHA `a29142c25f419b2b0f8a7a096a91cf4774a67fd64a836bb18eb9e5fc49e7c8b4`.
[Baseline hashes](baseline-source.json) match the reviewed first PR source.
Final validation took57.877s excluding source copying/setup, with CPU4, nice19
and a2GiB Node heap setting. A post-run [process audit](cleanup.json) found no
matching live job process across six runtime roots.

## Preserved failed attempts and correction

- **V1:** the first lifecycle fixture failed all8 cases on `fffed261`; the
  production cleanup candidate passed5 and failed3. Its test expected only the
  base registration while a client was connected.
- **Diagnostic:** actual HTTP logs show completed POST responses and a GET200
  stream that closed only after client shutdown. The initial flat diagnostic
  directory could not find the CLI and executed no tests; the corrected
  diagnostic selected1 old-expectation failure, with7 skipped.
- **V2:** tests were corrected to independently track unfinished HTTP responses:
  stateless registrations must equal base + active responses, then return to
  only base after client close. Lifecycle8 and complete23 passed, but strict
  checking rejected the fixture factory's overly narrow `Tool` generic type.
- **V3:** the factory uses the existing `MCPServerConfig["tools"]` type. All
  final checks passed. The other seven checked files were byte-identical across
  the three candidates; production behavior was not changed to chase the tests.

The failed controller outcomes remain failed. Neither HTTP diagnostics nor type
checks are additional neural scores. The final matched baseline still fails8
cases, so the revised lifetime model does not hide the original retention bug.

## Evidence and reproduction

[Final baseline](v3/baseline-lifecycle.log) ·
[Final lifecycle cases](v3/candidate-lifecycle.log) ·
[Complete23 tests](v3/package-suite.log) ·
[Source typecheck](v3/package-typecheck.log) ·
[New-test typecheck](v3/new-regressions-typecheck.log) ·
[Build](v3/package-build.log) · [Final report](v3/run-report.json).

[First failed report](v1/run-report.json) ·
[Second failed report](v2/run-report.json) ·
[Actual HTTP lifetime observations](debug/stream-lifetime-debug-v2.log) ·
[Exact final test source](v3/tested-source/packages/mcp-server/src/server-lifecycle.spec.ts) ·
[Summary](analysis.json) · [Export manifest](export-manifest.json) ·
[Artifact hashes](artifacts.json).

In an authorized server checkout of the tested commit with the unchanged
workspace lock, the relevant commands are:

```sh
pnpm --filter @voltagent/mcp-server exec vitest run --maxWorkers 2 --minWorkers 1
pnpm --filter @voltagent/mcp-server typecheck
pnpm --filter @voltagent/mcp-server build
```

The strict new-test check used the package tsconfig extended to include the two
new `.spec.ts` files explicitly; normal package typecheck excludes test files.
Only logs, hashes and source snapshots were exported; dependencies, models,
credentials and runtime directories stayed on the server. Public log paths/ANSI
are normalized; source snapshots are exact tested bytes. Approval/merge is not
claimed, and the personal homepage remains frozen.
