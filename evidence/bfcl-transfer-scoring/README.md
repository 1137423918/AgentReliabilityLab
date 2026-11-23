# Guarded BFCL-derived scoring controls — 2026-11-24

No model predictions, optimizer updates or actual tool execution. All 250 reference-derived witnesses are checker controls, **not model accuracy**. Admission IDs and inputs were frozen and independently verified before reading reference values.

- [v1 intent](v1/scoring-intent.json), frozen before reference fetch: `f952e4d155713fa9f1c7bae00ab125c81a19bc46c662a267187b3db1bb17a80a`.
- [v1 report](v1/results/report.json): 12 unit controls passed,246/250 reference witnesses matched. Four nested-dictionary witness representations were constructed incorrectly; no guard or scorer infrastructure errors.
- [v2 intent](v2/scoring-intent.json) and [protocol](v2/operator/protocol.json): witness-only preflight correction, parent intent retained, no new model outcomes observed.
- [v2 report](v2/results/report.json): 14 unit controls and250/250 witnesses pass; zero guard rejections/scorer errors/eval attempts. Counts overlap with v1 and must not be added.
- [v1](v1/results/binding-metadata.jsonl) and [v2 binding metadata](v2/results/binding-metadata.jsonl): public IDs, input/reference/witness hashes and control flags only. Reference and witness values remain private.
- [Unchanged upstream definitions](v2/results/checker-source-identity.json): pinned source SHA-256 and definition AST hashes. Python matching and guard function ASTs are unchanged across the witness correction.
- [Final tested implementation](v2/tested-source/benchmarks/bfcl_transfer_scoring.py), [binder](v2/tested-source/benchmarks/bind_bfcl_transfer_gold.py), [14 tests](v2/tested-source/extras/lora-training/test_bfcl_scoring.py), and original v1 tested sources are included. Pinned upstream definitions are accompanied by the [Apache-2.0 license](v2/tested-source/upstream/LICENSE).
- [v1 controller](v1/operator/run-report.json), [v2 controller](v2/operator/run-report.json), [final control log](v2/operator/CPU-controls.log), [binding log](v2/operator/gold-binding.log), [cleanup](cleanup.json) and [45-payload hash manifest](export-manifest.json).

The metric is a guarded BFCL-derived Python-track diagnostic, not the full official harness. BinOp/Lambda or text/AST resource-limit rejections earn no credit and have unknown unrestricted official outcomes. Original irrelevance parse-failure credit is retained and decoder/empty-list flags are reported separately. Unsupported scorer/schema errors remain undefined rather than invented prediction failures.

Source copies are unchanged bytes; operator paths are normalized where required, with original/public hashes distinguished. No private question or prompt bodies, reference values, witness bodies, predictions, token vectors, weights, environment secrets or server connection data are exported. See [interpretation](../../docs/bfcl-transfer-scoring.md).
