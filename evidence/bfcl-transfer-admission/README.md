# BFCL-derived transfer admission — 2026-11-24

Question-only CPU preparation, with **zero new gold-file reads, model calls, optimizer updates or scores**. This is not the full BFCL evaluation harness or proof of semantic/pretraining isolation.

- [Selection intent](selection-intent.json), frozen before fetching question bytes: SHA-256 `080e8df193fd50e8a19bbaaa26748560057b7da94eaae8cd8e1c0603dcc958f0`.
- [Admission](results/admission.json): 250 fixed IDs in 250 distinct components, 50 per category; prompt/row/token hashes and grouping metadata. SHA-256 `d96f2f3d19f057e3a37c896d0d09fdd242add1a62e4b66c23e77afeeb9bf2bf9`.
- [Preparation report](results/report.json) and [all 1,951 candidate metadata rows](results/candidate-metadata.jsonl). No question bodies, reference answers or token vectors are included.
- [Successful v2 protocol](v2/operator/protocol.json), [controller report](v2/operator/run-report.json), [10 controls](v2/operator/CPU-controls.log), [runtime identity](v2/operator/runtime-identity.log), [admission log](v2/operator/question-admission.log).
- [Initial v1 failure](v1/operator/run-report.json): wrong location for the old benchmark, stopped before staging question inputs or running admission. The correct file was subsequently checked against the already frozen SHA. The v2 deployment changes the location, not the selection intent, quotas or source algorithm.
- [Tested implementation](tested-source/benchmarks/prepare_bfcl_transfer.py) and [tests](tested-source/extras/lora-training/test_bfcl_transfer.py) match the published code byte for byte. The empty package file is an isolated server import shim. Pinned BFCL [prompt constants](tested-source/upstream/default_prompts.py) are read as literal AST assignments; accompanying [Apache-2.0 license](tested-source/upstream/LICENSE).
- [Cleanup](cleanup.json): both CPU profiles terminal, no matching live processes; protected data unchanged. [Export manifest](export-manifest.json) binds all 23 payload byte counts and original/public hashes. Operator paths were normalized; tested source was not rewritten.

Both deployments contain metadata/source only in this export. Private question archives, rendered prompts, gold data, model weights, credentials and server connection details are excluded. No reference-answer file has been staged for this admission. See [method and unresolved scoring limits](../../docs/bfcl-transfer-admission.md) before attempting a subsequent model experiment.
