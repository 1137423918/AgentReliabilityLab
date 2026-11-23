# Fixed-scaffold supervision audit — 2026-11-24

CPU-only analysis of the frozen training data and all 597 committed generation outcomes. No model training, inference, response re-parsing or official re-scoring. This is exploratory analysis after the old clean outcomes were observed; the proposed mask is prepared, not trained.

- [Report](results/report.json): complete supervision counts, fixed32 per-step label counts, stored outcomes and paired transitions.
- [Receipt](results/receipt.json): unchanged inputs/ledger, preparation timing and private mask-file hashes. Token vectors are not included.
- [Supervision metadata](results/supervision-metadata.jsonl): 7,676 rows containing ordinals, shape/counts and source/input/label hashes.
- [Stored-output metadata](results/stored-output-metadata.jsonl): 597 rows containing existing scores, objective marker flags and hashes; no response bodies.
- [Frozen CPU protocol](operator/protocol.json), [supervision record](operator/run-report.json), [10 controls](operator/CPU-controls.log), [audit log](operator/alignment-audit.log) and [cleanup](cleanup.json).
- [Tested source](tested-source/benchmarks/audit_toolrl_alignment.py) and [tests](tested-source/extras/lora-training/test_alignment_audit.py) match the published implementation byte for byte. The empty `benchmarks/__init__.py` is an isolated import shim used by the server test environment.
- The pinned [upstream converter](tested-source/upstream/convert_to_toolrl_parquet.py) is source evidence, with its [Apache-2.0 license](tested-source/upstream/LICENSE); its two fixed prose constants were read through AST, without importing/executing it.

Protocol SHA-256: `1106f9a35601aeb3f006308292e1674c85afbfc328bd0e27ba858e38dc902bf9`. The original generation ledger remains `188a45f27b0fcc0448c2b8366c4eaa0d72327882de59547b0e6d45ad7226a6e0`; 599 reservations / 597 committed results / 2 historical unknown attempts still charged.

[export-manifest.json](export-manifest.json) records the byte count and original/public SHA-256 of all 18 payloads. Operator paths were normalized where necessary; tested source bytes were not rewritten. The accompanying operator scripts describe the bounded server deployment and are not a portable scheduler or GPU training harness. No private inputs, gold answers, predictions, masked token vectors, model weights, environment credentials or connection details were exported.

See [interpretation and limits](../../docs/training-alignment.md). Marker associations do not establish causality or semantic refusal; the original negative generation results and earlier training failure remain unchanged.
