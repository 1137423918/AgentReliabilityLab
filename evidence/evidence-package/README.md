# Installed MCP evidence wheel

A standalone wheel packages the three canonical modules byte-for-byte under agentlab_evidence, with agentlab-evidence as the installed console entry. The main project and installed wheel share the app/service implementation; the old benchmark module remains a compatibility entry. --check and normal startup both validate pinned report bytes before listening.

- [Measured summary and limits](report.json) · [Independent saved-data checks](verification.json) · [Artifact hashes](artifacts.json) · [Starter payload receipt](starter-receipt.json)
- [Actual installed wheel controls](installed/report.json) · [Actual MCP wire bytes](installed/wire.json) · [Fresh130 core tests](operator/full-core.log) · [Controller phases/cleanup](operator/run-report.json)
- [Build-time wheel receipt](wheel/build-receipt.json) · [Frozen protocol](operator/protocol.json) · [Installed dependency check](operator/installed-dependency-check.log)
- [Canonical MCP entry](tested-source/agent_lab/evidence_mcp.py) · [Build script](tested-source/packages/evidence-service/build.py) · [Outside-checkout test driver](tested-source/benchmarks/evidence_package_controls.py)

Eight installed artifact controls pass using the exact wheel in a new frozen minimal environment, with isolated Python outside the source checkout. agent_lab/benchmarks/deepagents/llama_index do not resolve. Actual SDK/TCP verifies fixed reports and read receipts; borrowed receipts/wrong JSON types, modified report preflight/start/live reads, and previous-process capabilities are rejected. Exhausted contexts can close. Two planned server lifetimes terminate without forced kill, ports close and no owned process remains.

The independent original130 core tests pass again with no skips after the shared import/module change, with zero new core test functions. They are not added to the eight controls or earlier10/6network cases. Core and builder environments keep all distribution versions, and the new runtime only adds the own wheel after frozen dependency sync. All181 server-frozen sources are unchanged.

The starter is a static bundle of the actual tested wheel, unchanged frozen runtime files, ten catalog/report files (nine reports) and usage instructions. Every payload byte is checked; the whole starter quickstart is not executed a second time. Its catalog is historical cb67290, not a live PR feed. The package is a repository artifact, not a PyPI upload. No model inference, GPU, public hosted service or changed historical model outcome.
