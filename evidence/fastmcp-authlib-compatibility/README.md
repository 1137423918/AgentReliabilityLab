# Paired historical FastMCP Authlib compatibility

The same279 upstream auth-related test IDs pass in both frozen environments,
with no failures/errors/skips. Baseline Authlib1.6.1; candidate Authlib1.9.10
plus joserfc1.8.0. These are overlapping paired cases, not558 independent tests.

See [summary](results/summary.json), [full paired report](results/report.json),
[source-file manifests](results/source-file-manifests.json), both JUnit XML
files, frozen locks and [30-payload export manifest](export-manifest.json).
The operator directory retains both the pre-checkout v1 preparation failure and
the completed v2 protocol, lifecycle report, harness and logs.

Only uv.lock differs between the614 tracked source files; no upstream test or
snapshot was edited. All test IDs match. The server supervisor is terminal,
owned processes zero, source hashes preserved. Source/license identifies the
pinned upstream checkout; environments and caches remain private.

This measures the historical auth subset on Linux/Python3.11.4 with mocked
providers and loopback flows, not full native CI, real cloud identity services,
deployment approval or vulnerability freedom. Authlib deprecation warnings and
the prior16 affected registry resolutions remain visible. No neural calls.
Paths in operator metadata are normalized; original/public hashes are separate.

[Method and reproduction](../../docs/dependency-upgrade-compatibility.md).
