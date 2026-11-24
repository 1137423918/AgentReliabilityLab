# Frozen SciFact retrieval inputs

This directory contains download metadata, not dataset text or model weights.
The full run uses the official BeIR/scifact corpus revision
`b3b5335604bf5ee3c4447671af975ea25143d4f5` and scifact-qrels revision
`2938d17dc3b09882fdb8c12bbbe2e2dc0e75a029`: 5,183 title/abstract documents,
300 test queries and 339 positive document pairs. The original TU-hosted ZIP
could not be downloaded in this run; its checksum was not verified.

Download each entry in `HF-official-assets.json` to
`ASSETS/<repo with / replaced by -->/<file>`. Also download the PyArrow wheel
in `pyarrow-intake.json` and the original authors' archive in
`author-data-intake.json` to `ASSETS/<wheel filename>` and
`ASSETS/author-scifact-data.tar.gz`. Copy these three JSON files into `ASSETS`.
The intake verifies sizes/hashes before reading them. The authors' `latest`
URL is mutable: a different hash must fail, rather than silently use new data.
PyArrow is privately unpacked for intake, not added to the application runtime.

Use the frozen Linux x86_64/Python 3.11 CPU environment and verified E5 model
described in [the package guide](../../packages/research-library/README.md).
Run from the repository root, on the experiment server:

```sh
extras/research-library/.venv/bin/python -m benchmarks.research_retrieval_intake \
  --assets /path/to/assets --output /tmp/new-scifact-input \
  --model-dir /path/to/verified-e5

extras/research-library/.venv/bin/agentlab-research ingest \
  --manifest /tmp/new-scifact-input/corpus/collection.json \
  --store /tmp/new-scifact-store --model-dir /path/to/verified-e5 \
  --embed-batch-size 16

extras/research-library/.venv/bin/agentlab-research search-batch \
  --queries /tmp/new-scifact-input/ranking-input/queries.jsonl \
  --output /tmp/scifact-rankings.jsonl --store /tmp/new-scifact-store \
  --model-dir /path/to/verified-e5 --top-k 10

extras/research-library/.venv/bin/python -m benchmarks.research_retrieval_eval score \
  --batch /tmp/scifact-rankings.jsonl \
  --id-map /tmp/new-scifact-input/ranking-input/source-id-map.json \
  --queries /tmp/new-scifact-input/ranking-input/queries.jsonl \
  --qrels /tmp/new-scifact-input/judgments/qrels.json --output /tmp/new-scores

extras/research-library/.venv/bin/python -m benchmarks.research_retrieval_eval verify \
  --scores /tmp/new-scores --trec-eval /path/to/trec_eval
```

The intake and scorer are checkout benchmark modules; the installed wheel
provides the production ingest/search-batch commands. Intake plans tokenizer
inputs without neural forwards. Ingest and search-batch perform real CPU E5
encoding. The published experiment additionally uses a private reserve-before-
forward observer and resource supervisor; these limits are not built-in CLI
quotas. Do not run the above repeatedly to select a favorable result.

Build the unmodified [NIST trec_eval](https://github.com/usnistgov/trec_eval)
commit `615ecba29b1651ae130f953f2d753bc437160d84` on the server using `make`,
then `make quicktest`. Archive SHA-256:
`6799d78280dc41d6a582029f134362b19cfe4a3a6210bdd135c86d7acccc5fda`.
The scorer exports ordinal TREC runs to preserve the application's actual
ordering, including ties. Verification compares each query and macro mean
against the C executable; the 0.000051 tolerance reflects its four decimal
output, not a quality target.

BEIR test relevance matches the original authors' development-set
`cited_doc_ids` as sets for all 300 claims. These are cited-document retrieval
labels. Of those claims, 112 have no original evidence annotation; retrieval
does not establish support, refutation, or generated-answer correctness.
The authors' [license](https://github.com/allenai/scifact/blob/68b98a56d93e0f9da0d2aab4e6c3294699a0f72e/LICENSE.md)
distinguishes claims/evidence (CC BY 4.0) and abstracts (S2ORC/ODC-By 1.0),
whereas the [HF dataset card](https://huggingface.co/datasets/BeIR/scifact)
labels CC BY-SA 4.0. Preserve source attribution and review the upstream terms
when obtaining or redistributing data. This repository redistributes metadata
and document IDs only.
