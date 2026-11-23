# VoltAgent MCP connection ownership follow-up

2026-11-23 · [PR #1562](https://github.com/VoltAgent/voltagent/pull/1562) · tested source `44cbec5791030c9aef2e47bd30df0b240e145b33`.

A rejected second connection could close the transport already owned by another connection attempt. Reject it before changing handlers or notification registrations, and only clean up a failed startup when the shared server has no transport or still owns that attempt's transport.

The three added real-MCP-SDK cases cover an established connection, a gated pending startup, and an owned startup failure. The surviving client must still list tools; the established connection must still receive notifications. No model response is mocked or requested.

With the **identical final 11-case lifecycle fixture**, reviewed head `afa92332ed938c750f452cda8b5a68cbc7b6067e` fails 2 cases and passes 9; candidate passes all 11. The [complete MCP package suite](logs/package-suite.log) passes **26**, including those 11 and the original 4 notification cases. These counts overlap and must not be added. Strict source and both new-test typechecks, package build, changed-TypeScript Biome and changed-Markdown checks pass. [Phase results and source hashes](run-report.json).

Linux CPU, Node22.23.5 / pnpm8.10.5 / MCP SDK1.30.0; unchanged frozen upstream lockfile. Reused dependency environment; 4 CPUs, nice19, 2GiB Node heap. No GPU or neural calls. [Terminal process audit](cleanup.json).

[Exact tested source](tested-source/packages/mcp-server/src/server.ts) · [Lifecycle tests](tested-source/packages/mcp-server/src/server-lifecycle.spec.ts) · [Baseline source hashes](baseline-source.json) · [Original failure](logs/baseline-lifecycle.log) · [Candidate](logs/candidate-lifecycle.log) · [PR status snapshot](pr-status.json).

[Earlier cleanup results, retained failed attempts and HTTP lifetime diagnostics](../voltagent-mcp-cleanup/README.md) remain historical evidence; their 23-test scope predates this ownership follow-up. Current package checks do not establish whole-monorepo or upstream-CI success, and the PR is not merged. Author: Junzhe Wang; upstream VoltAgent, package MIT attribution retained in source context.

Only log paths and ANSI colors are normalized. [Export manifest](export-manifest.json) retains original and public hashes; [public payload manifest](artifacts.json) covers this evidence folder excluding itself.
