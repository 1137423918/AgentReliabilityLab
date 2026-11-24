# Standalone CPU research retrieval

`agentlab-research` packages the canonical retrieval, embedding, MCP, local-document intake and storage modules in its own `agentlab_research` namespace. It does not install the maintenance worker or Deep Agents. Model weights, private indexes and server connection details are not shipped.

The supported frozen runtime is Linux x86_64 / Python3.11, in `extras/research-library`. It selects the official PyTorch CPU index explicitly; `torch==2.6.0+cpu` has no CUDA runtime. The generic wheel metadata specifies the application dependencies; use the supplied runtime lock for the tested CPU dependency selection.

From the repository root, or a starter archive with the same relative layout:

```sh
uv sync --project extras/research-library --frozen --no-install-project --no-default-groups
uv pip install --python extras/research-library/.venv/bin/python --no-deps \
  artifacts/agentlab_research-0.1.0-py3-none-any.whl
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

`prepare` snapshots explicit UTF-8 `.md`, `.txt`, `.rst` and `.bib` files, preserves original bytes, creates stable path-derived IDs and records SHA-256. It ignores hidden paths and unsupported formats, rejects symlinks and empty/invalid documents, and supports up to256 files /512KiB each /16MiB total. The output must be new and outside the input tree. It does not parse PDFs, verify the supplied source URLs, or provide an atomic snapshot of a concurrently edited source tree. Supply a matching immutable source URL base when publishing citations.

`ingest/search/read` dispatch to the canonical engine; `serve` exposes its three read tools over loopback MCP. Unknown sources and citations are handled by the same retrieval contracts as the source checkout. Console execution reports process-local embedding counts. The installation benchmark uses an explicit observer and a durable, capped test journal; this instrumentation is not a built-in persistent service quota.

To build a wheel from source on a build server with setuptools>=75:

```sh
python packages/research-library/build.py --output /tmp/new-research-wheel
```

The build receipt records canonical module/data hashes. Artifact installation, real CPU embeddings and MCP verification are documented separately in [the project guide](../../docs/research-library.md).
