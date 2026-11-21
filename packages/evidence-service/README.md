# Installable MCP report evidence service

Build a standalone `agentlab-evidence` wheel from the canonical `agent_lab` evidence modules. The builder copies the three module bytes unchanged into the independent `agentlab_evidence` namespace. It does not ship or install the maintenance worker, Deep Agents, LlamaIndex, model weights, private state or report corpus. The optional runtime remains separately pinned to MCP2.3.0 and HTTPX2 2.16.2.

On an authorized build server with Python3.11 and setuptools>=75:

```sh
python packages/evidence-service/build.py --output /tmp/new-evidence-wheel
```

Use a fresh output directory. The build receipt records wheel/source hashes and entry-point metadata; it describes the build step, not subsequent installation validation.

The CLI accepts `--root`, `--manifest`, `--port` and `--max-operations`. `--check` validates every pinned report and exits without starting a listener. Normal startup performs the same preflight before binding loopback. Changed bytes, missing reports and symlinks are rejected. Existing `python -m benchmarks.mcp_evidence_server` remains a compatibility entry in a source checkout.

The six MCP tools and their bounds are unchanged: begin/list/read/verify/status/close, 32 live audit contexts, 600-second TTL, default16 operations and8 reads per audit. Receipts prove possession of a report response, not human/model understanding; verdict truth and free prose are unchecked. Capabilities are not user authentication. This is a single-process loopback service, not a public hosted API or persistent multiuser backend.

See [service usage](../../docs/mcp-evidence.md) for the starter download, commands, measured installed-artifact validation and limitations. The package is distributed as a repository artifact; no PyPI upload is implied.
