# Complete file inventory — task-local tool scope, fake-model transport checks

Opt-in `file_inventory_v1` renders all canonical editable paths as bounded JSON (8192 UTF-8 bytes), omits `ls` from each actual model request and rejects unsolicited/stale `ls` before the backend runs. Other navigation/editing tools remain, including `glob`. This is a graph-local policy through public LangChain middleware, not a new filesystem sandbox or global model-profile override.

**Server full suite:106passed, zero skipped; six new inventory checks are included, not added again.** The fake HTTP model verifies the actual wire schema, explicit error and backend non-execution, successful later edit/acceptance, quote/Unicode complete paths, preserved read-index replies, cached replay, policy-change rejection, same-alias default/opt-in/default isolation, and real checkpoint SIGKILL/resume. These are transport/runner controls, not neural capability or new independent maintenance tasks.

- [Results, source hashes and bounds](report.json).
- [Full log](final/full.log), [six focused checks](final/focused.log), [commands/timing](final/execution.json), [runtime](final/runtime.json), [source hashes](final/source.json).
- [Wheel audit](final/wheel-audit.json): three production modules byte-identical; invoke the actual extracted-wheel worker console entrypoint through a fake HTTP edit and the operator-owned verification command. No global install or new dependency environment.
- [Setup round0 failure](preflight/round0/focused.log): test spy initially referenced old `ls_info`; corrected both actual `ls`/`als` probes.
- [Setup round1 full failure](preflight/round1/full.log): eight historical replay samples were omitted from the candidate archive; restored original2015bytes and checked all hashes, no skipped/removed tests.
- [Original/public artifact hashes](artifacts.json), [contract and usage](../../docs/file-inventory.md).

Task flag participates in the original full task/journal identity; flipping it cannot reset quota or replay cached success under a different policy. Existing state admission, syntax/export allowlist and protected acceptance remain. Default tool visibility is preserved before and after an opt-in graph with the same alias. Current built-in worker graph is pinned to Deep Agents0.7.41/Python3.11 Linux; no broad async or arbitrary-custom-graph guarantee.

No GPU, neural requests, new upstream regression score, model token/cost/latency benefit, or accepted neural patch in these checks. All temporary test state was local ext4. Only selected logs/receipts and source hashes are public; no SQLite, full conversations, weights or credentials. Earlier real-model failures stay unchanged. Real-model effect requires a separately declared trial with the same protected acceptance.
