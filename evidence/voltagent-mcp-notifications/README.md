# VoltAgent MCP notification fix · 2026-11-23

[VoltAgent #1562](https://github.com/VoltAgent/voltagent/pull/1562) is open as a
regular PR. Commit `fffed2614bc4354f31f3a1dff50afec65b2412eb`, based on upstream
`e9fc599f6059afcd88b34f2bfc50d0d1d6a0877c`. No approval or merge is claimed.
This is the first-patch snapshot. The subsequent
[registration-cleanup review fix](../voltagent-mcp-cleanup/README.md) retains this
record and adds final23-test validation at a newer PR head.
The [dated status snapshot](pr-status.json) records native Actions run45182715145
as `completed/action_required`; an upstream maintainer must approve its execution.

The capability bridges register the base server and per-session servers. An
HTTP-only base server has no transport, and closed sessions lose theirs.
Broadcasting notifications to these entries rejects with `Not connected`.
The patch skips entries without an attached transport, preserving cache
invalidation and connected-send error propagation. It does not redesign
subscription ownership, remove retained registrations or guarantee success
when a connection closes during a send.

## Actual server validation

Linux CPU / Node22.23.5 / pnpm8.10.5 / Vitest3.2.4 / MCP SDK1.30.0. Unchanged
upstream lock SHA `fa866ef0b4476afa12b798892884ef1d3ade2c07c01cf9abe2ab2f95c0c66c75`.

| Check | Observed result |
| --- | --- |
| Original source plus new regression file | 3 `Not connected` failures; 1 passing connected-send-error control |
| Candidate regression file | 4 pass |
| Complete MCP-server package suite | 15 pass, including those same 4 |
| Package source typecheck | Pass |
| Separate strict new-regression typecheck | Pass |
| Builds: internal, logger, core, MCP-server | Pass |
| Changed TypeScript Biome; Markdown format | Pass |

Regressions use real MCP SDK Server/Client instances and linked in-memory
transports. They cover an unconnected registration, a closed client/server
pair, active-client delivery, all clients subsequently closed, and propagation
of an active send failure. The full package suite includes existing HTTP and
tool-adapter tests. Counts overlap; dependency packages were built, not tested.
This is not a whole-monorepo or upstream-CI pass.

Install239.202s; candidate validation72.721s. CPU affinity4, nice19, Node heap
cap2GiB are settings, not a total descendant RSS guarantee. Install scripts
were disabled in a new server-local workspace. No model or GPU was used.

## Evidence

- [Original failure](bootstrap/baseline-notifications.log),
  [candidate regressions](validation/candidate-notifications.log),
  [complete package suite](validation/package-suite.log).
- [Source typecheck](validation/package-typecheck.log),
  [strict regression typecheck](validation/regression-typecheck.log),
  [package build](validation/package-build.log), [lint](validation/lint-changed.log).
- [Bootstrap report](bootstrap/run-report.json),
  [candidate report](validation/run-report.json),
  [Node](bootstrap/node-version.log) / [pnpm](bootstrap/pnpm-version.log) versions.
- [Exact tested regression](tested-source/packages/mcp-server/src/capabilities/notifications.spec.ts),
  [upstream attribution](tested-source/UPSTREAM.json),
  [selection and duplicate search](selection.json).
- [Export manifest](export-manifest.json) and [artifact hashes](artifacts.json).
- [Post-run process check](cleanup-verification.json): no same-UID process with
  argv or working directory under this job's unique runtime root remained.

Only logs, metadata and six exact source files returned in the10,739-byte archive
(SHA `fc800ce840ad57f27ce41fe1dd4733a96cc69abe9d714bea8013b50f73d2815f`).
ANSI and private runtime paths were normalized in logs, with original/public
hashes separate. Tested sources are exact bytes. No environment, credentials,
weights or user data are included. Homepage remains frozen.
