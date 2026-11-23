# Saved tool-call schema diagnostics · 2026-11-23

Offline CPU analysis of the existing Stage52 generation snapshot. No generation,
raw-text parsing, official rescoring or tool execution. The original ledger
remained byte-identical (`c485cf3ad69116dc6d24b0051e36c57820a1f3ffb7e7de0cb7b817e36be93275`).

The [analysis](../../docs/tool-schema-diagnostics.md) explains the raw and
upstream-FC-projection interpretations and the interrupted83-case comparison.
Schema validity is not task accuracy; invalid source schemas are unassessable.

- [Frozen protocol](operator/protocol.json): fixed before this diagnostic
  inspected prediction values; binds data, source, pure upstream functions,
  ledger and dependency versions. SHA `690be4731ab4754e42423ae0bf4b0e27327c56b1df4e1784e53ba2470bddb173`.
- [Summary](results/summary.json): both views, all-known and matched-prefix
  denominators, benchmark groups and stored-score cross-tabs.
- [282 case diagnostics](results/case-diagnostics.jsonl): hashes, ordinals,
  stored official numbers, call statuses and violation keyword counts only.
- [199 input-schema inventories](results/schema-inventory.jsonl): all879 tool
  occurrences, independently of what the model selected.
- [Analysis receipt](results/analysis-receipt.json), [admission](operator/admission.json),
  [run report](operator/run-report.json) and [13 CPU controls](operator/controls.log).
- [Separate source checks](operator/post-analysis-source-checks.json): server
  Ruff passed, actual SDK lock identity matched, and five related distributions
  were recorded. These checks did not rerun the diagnostic or model.
- [Tested entry point](tested-source/benchmarks/diagnose_saved_tool_calls.py) and
  [contract implementation](tested-source/agent_lab/tool_schema.py).
- [Export manifest](export-manifest.json) and [artifact hashes](artifacts.json).

Both phases exited0;5.753s combined phase wall time, excluding admission/source
copy; no owned child left running. Controls are
boundary tests, not neural scores or additions to the historical130-core count.
Base correct118/199 is unchanged; Full has83 known results, Mixed0. The matched
prefix is nonrandom and covers only BFCL/API-Bank, so no complete three-arm
comparison or training benefit is established.

Only metadata returned from the server (59,950-byte archive,
SHA `0590e6195fd109cd77e0625e1ebe345385972dc2e01c8191dacc1bb317244200`).
Predictions, arguments, prompts, reference answers and weights are not included.
Public metadata supports reaggregation and source verification, not independent
validation of the undisclosed model arguments.

Operator `.py.txt` files have private paths normalized and are documentary
snapshots, not executable launchers. Original/public hashes are separate in
artifacts; protocol controller identity refers to original bytes. Public
contract, analysis and control sources are exact tested bytes. The existing MCP
SDK environment was reused with the three validator dependencies checked;
this was not a fresh install or a complete environment rebuild. Homepage frozen.
