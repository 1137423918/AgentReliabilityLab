# Native CPU maintenance pilot — both cases timed out

A pinned Qwen3-4B-Instruct-2507 snapshot was converted to FP16 GGUF and Q4_K_M,
then served by unmodified official llama.cpp b12576 on an authorized CPU node.
The full public Deep Agents task ran in normal and checkpoint-resume modes.
**Both hit the predeclared 600-second deadline: no exported or verified patch,
and no official acceptance was reached.** These are two operational trials of
one problem, not independent benchmark tasks or a general model success rate.

- [Report, cases and 37 original/public file hashes](report.json)
- [Protocol declared before model loading](protocol.json)
- [Model, template, native binaries and runtime library identities](native-manifest.json)
- [Exact official download artifacts](runtime-artifacts.json)
- [Full protocol and reproduction commands](../../docs/native-cpu-pilot.md)
- [Original snapshot reverified after conversion](preparation/llama-original-snapshot-reverified-20261120.json)
- [Public model inspector reproduction](preparation/llama-public-inspector-reproduction-20261120.log)
- [Three native launcher ownership/cleanup checks](preparation/llama-launcher-tests-20261120.log)

The final checkpoints retained 8/12 model replies and 9/13 tool results. The
interruption occurred after two non-mutating `ls` queries; navigation state
continued, but edited-file recovery and maintenance recovery success remain
unvalidated. The server recorded 22 model task launches and two cancellations;
the 20 persisted reply usage records omit canceled generations.

The normal case's [unexported virtual text](audit/normal/libs/deepagents/deepagents/backends/utils.py.txt)
contains literal backslash-n sequences and fails static Python parsing. It is
not a patch to apply. [Normal audit](audit/normal.json) records the 1,250-line
baseline versus one-line virtual result, hashes and syntax failure; symbol
removal is not inferred from an unparseable AST. [Recovery audit](audit/checkpoint-resume.json)
retains no virtual content changes and includes one tool error. Full dialogs,
checkpoint databases and worktrees remain private.

The owned service was identity-checked and stopped. Launcher exit 143 records
operator SIGTERM; the native child exited 0 without forced cleanup. Pending
model nodes and `running` status files are stale retained state after worker
deadline termination, not evidence of live processes.

Private workspace paths and terminal progress formatting are replaced in public
copies; original and public hashes are distinct. Weights, native binaries and
libraries are external artifacts, not included here. Prior 33 core checks and
14 parser checks were unchanged and not rerun. The three new launcher checks
use explicit non-model process fixtures, never neural-inference scores.
