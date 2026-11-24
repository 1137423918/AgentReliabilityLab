# Standalone CPU research retrieval

`agentlab-research` packages the canonical retrieval, embedding, MCP, local-document intake and storage modules in its own `agentlab_research` namespace. It does not install the maintenance worker or Deep Agents. Model weights, private indexes and server connection details are not shipped.

The supported frozen runtime is Linux x86_64 / Python3.11, in `extras/research-library`. It selects the official PyTorch CPU index explicitly; `torch==2.6.0+cpu` has no CUDA runtime. The generic wheel metadata specifies the application dependencies; use the supplied runtime lock for the tested CPU dependency selection.

From the repository root, or a starter archive with the same relative layout:

```sh
uv sync --project extras/research-library --frozen --no-install-project --no-default-groups
uv pip install --python extras/research-library/.venv/bin/python --no-deps \
  artifacts/agentlab_research-0.3.0-py3-none-any.whl
uv pip check --python extras/research-library/.venv/bin/python
extras/research-library/.venv/bin/agentlab-research --help
```

Obtain the six pinned E5 assets listed in the package's `research_model_assets.json`, or copy an existing verified model directory. The fixed revision is `614241f622f53c4eeff9890bdc4f31cfecc418b3` in `intfloat/multilingual-e5-small`. The model checker verifies the asset hashes without importing a model; it writes a manifest only if one is absent, and preserves a valid existing manifest.

```sh
extras/research-library/.venv/bin/agentlab-research check-model --directory /path/to/e5
extras/research-library/.venv/bin/agentlab-research prepare \
  --directory /path/to/docs --output /tmp/research-input \
  --base-url 'https://github.com/OWNER/REPO/blob/COMMIT/docs/'
extras/research-library/.venv/bin/agentlab-research ingest \
  --manifest /tmp/research-input/collection.json --store /tmp/research-store \
  --model-dir /path/to/e5
extras/research-library/.venv/bin/agentlab-research search \
  --store /tmp/research-store --model-dir /path/to/e5 \
  --query 'Which authentication tests were run before and after the upgrade?' --top-k 3
extras/research-library/.venv/bin/agentlab-research read \
  --store /tmp/research-store --citation-id '<generation>:<node_id>'
extras/research-library/.venv/bin/agentlab-research serve \
  --store /tmp/research-store --model-dir /path/to/e5 --port 18863
```

`prepare` snapshots explicit UTF-8 `.md`, `.txt`, `.rst` and `.bib` files, preserves original bytes, creates stable path-derived IDs and records SHA-256. It ignores hidden paths and unsupported formats, rejects symlinks and empty/invalid documents, and supports up to8,192 files /512KiB each /16MiB total. The output must be new and outside the input tree. The text command does not parse PDFs or verify source URLs, and does not provide an atomic snapshot of a concurrently edited source tree. Use the separate PDF command below for digital-text papers. Supply a matching immutable source URL base when publishing citations.

`ingest/search/read` dispatch to the canonical engine; `serve` exposes its three read tools over loopback MCP. Unknown sources and citations are handled by the same retrieval contracts as the source checkout. Console execution reports process-local embedding counts. The installation benchmark uses an explicit observer and a durable, capped test journal; this instrumentation is not a built-in persistent service quota.

To build a wheel from source on a build server with setuptools>=75:

```sh
python packages/research-library/build.py --output /tmp/new-research-wheel
```

The build receipt records canonical module/data hashes. Artifact installation, real CPU embeddings and MCP verification are documented separately in [the project guide](../../docs/research-library.md).

## Batch retrieval in 0.3.0

`search-batch` accepts JSONL rows containing exactly `id` and `query`, at most
512 unique requests /1MiB. It captures one verified index generation and reuses
its index, lexical statistics and source bytes. Semantic and hybrid rankings
share one query embedding. The final JSONL is published after every row has
been saved; a failed run retains `.partial` and is not resumable. Neither an
existing final file nor a partial file is overwritten.

```sh
extras/research-library/.venv/bin/agentlab-research search-batch \
  --queries /path/to/questions.jsonl --output /tmp/new-results.jsonl \
  --store /tmp/research-store --model-dir /path/to/e5 --top-k 10
```

Each output row binds the caller's ID, query hash and generation to all three
retrieval responses and citations. Results include source text. This is
retrieval output, not generated answers or calibrated relevance probabilities.
Offline top-k is 1–32, with candidate-node window `max(24,4*top_k)`; MCP retains
its 1–8 result cap. Ingest fills embedding batches across changed documents;
`--embed-batch-size` accepts 1/2/4/8/16 (default 4). Source limits and PDF limits
are separate.

The smaller retrieval dependency lock is unchanged from the 0.2.0 runtime.
The 0.3.0 application wheel was built and installed into a new namespace using
a read-only view of the larger frozen reading-assistant CPU environment, with
copied distribution metadata. Its 90 shared third-party dependency versions
match the retrieval lock; the lockfiles themselves differ. This is not another
clean dependency reinstall. Source controls and actual
model evidence are scoped separately in [the batch guide](../../docs/research-batch.md).

## Full PDF papers with page citations

Create an explicit local JSON intake manifest. Paths are relative to that file; URLs should identify the matching PDF version. The tool reads local files and never downloads URLs itself.

```json
{"version":1,"pdfs":[{"path":"paper.pdf","url":"https://example.org/paper-v3.pdf","title":"Paper title"}]}
```

```sh
extras/research-library/.venv/bin/agentlab-research prepare-pdf \
  --manifest /path/to/papers/intake.json --output /tmp/paper-input
extras/research-library/.venv/bin/agentlab-research ingest \
  --manifest /tmp/paper-input/collection.json --store /tmp/paper-store \
  --model-dir /path/to/e5
```

Each nonempty PDF page becomes a stable path/page source. Citations return a 1-based physical page number, a separate PDF page label, the original file hash and pypdf extraction version. Character offsets and line numbers refer to extracted page text. Each immutable index version retains the original PDF, so old citations can be checked after intake files or active sources are removed. Large collections grow storage because old generations are retained.

This is digital-text extraction with pypdf7.1.1, not OCR or reconstruction of tables, figures, formulas and multi-column reading order. Pages without extractable text are recorded explicitly; all-empty and encrypted PDFs fail without publishing a bundle. Limits: up to32 PDFs,256 physical pages total,32MiB per PDF,64MiB original bytes total,512KiB per extracted page and16MiB extracted text. Local inputs and manifest provenance are trusted; hashes do not independently authenticate a caller's claimed URL or extraction process.

[Whole-paper workflow evidence](../../docs/paper-library.md) covers two versioned public papers, real CPU E5 and MCP. These are known-topic workflow checks, not a QA benchmark or answer-generation score.
