# Current virtual-source navigation

Read-only Python AST navigation, followed by real-repository **scripted reference controls**. No GPU, neural inference, autonomous localization or model repair score.

- Full server suite: 63 checks, **49 passed / 14 skipped**, 154.217 seconds; missing jsonschema explains the skips. The six new checks are included in 49, not added again. Targeted six-check run also passed.
- Fixed real Deep Agents source: `744a797e3b9495539ca35571eeffd112a205f5c8`. Complete outline plus exact source for two operator-selected functions returned three JSON pages, 11,127 UTF-8 bytes total, 4,766 maximum per response (8,192-byte bound). Functions start at lines 822 and 846; the earlier actual model trace had read only lines 1–400.
- The 988-byte serialized OpenAI tool schema is additional input overhead, not a token count or full request size. Navigation payload bytes alone cannot prove net context, token, latency or cost savings. No model decided which symbols to select in this control.
- Reference edits run normally and after an actual SIGKILL at the first checkpoint, immediately after the production edit. Both export the same 1,573-byte patch and pass import checks, **113 fixed original / 119 candidate tests / 28 independent contracts**. Counts overlap. Source replies must hash to edited worktree contents, confirming current-state navigation after recovery, rather than indexing stale baseline code.

## Evidence

- [report.json](report.json): original control report; [summary.json](summary.json): current project checks and source identities.
- [navigation.json](navigation.json): exact bounded source/outline output and selection objectives.
- [runtime.json](runtime.json): Python/package/source identities and actual tool schema. Python 3.11.4, deepagents 0.7.41, langgraph 1.2.24.
- [task.json](task.json): explicit fixed reference edit plan, not the neural preset.
- [cases/normal/audit.json](cases/normal/audit.json), [cases/checkpoint-resume/audit.json](cases/checkpoint-resume/audit.json): current source hashes and actual tool replies, hydrated read-only from checkpoints without inference.
- [logs/full-tests.log](logs/full-tests.log), [logs/targeted.log](logs/targeted.log), [logs/controls.log](logs/controls.log): server checks; per-case verification logs and patches remain under cases/.
- [artifacts.json](artifacts.json): explicit original/private and public file hashes. Private server paths and terminal formatting normalized; full conversations, SQLite databases, model weights and worktrees excluded.

[Usage and boundaries](../../docs/source-navigation.md). The new model preset is prepared but has **not run neural inference**. Historical model failures and their fixed source identities remain unchanged. Source previews and patch context retain [upstream MIT](UPSTREAM_LICENSE). AST parsing uses the worker grammar, does not execute subject code and is not a semantic dependency index or hostile-code OS sandbox. Existing grep/read_file remain available for non-Python and invalid syntax.
