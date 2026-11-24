# Local research assistant runtime

This optional runtime connects the existing page-citation research service to a local model through LangGraph and an async SQLite checkpointer. The retrieval wheel remains a separate read-only MCP service; the assistant generates prose and checks that cited references came from actual tool reads. This check does not establish the factual correctness of the prose.

On a Linux x86_64 / Python3.11 compute server, from the repository root:

```sh
uv sync --project extras/research-assistant --frozen --no-install-project --no-default-groups
uv pip install --python extras/research-assistant/.venv/bin/python --no-deps \
  artifacts/agentlab_research-0.2.0-py3-none-any.whl
uv pip check --python extras/research-assistant/.venv/bin/python
```

Prepare a library with the [PDF workflow](../../docs/paper-library.md) or the existing text intake, then start its MCP service:

```sh
extras/research-assistant/.venv/bin/agentlab-research serve \
  --store /path/to/paper-store --model-dir /path/to/verified-e5 --port 18863
```

Start a compatible local model server separately. The tested native backend is llama.cpp b12576 and the fixed model is the existing Qwen3-4B-Instruct-2507 Q4_K_M conversion; [its provenance](../../evidence/native-cpu/native-manifest.json) identifies the source revision and conversion. Model/runtime artifacts are not shipped. A bounded CPU-only invocation is:

```sh
/path/to/llama-server --model /path/to/model.gguf \
  --alias agentlab-research-qwen3-4b-cpu --host 127.0.0.1 --port 18864 \
  --api-key-file /path/to/owner-only-service-key \
  --device none --n-gpu-layers 0 --fit off --threads 2 --threads-batch 2 \
  --threads-http 1 --parallel 1 --ctx-size 4096 --n-predict 256 \
  --timeout 180 --temp 0 --seed 42 \
  --jinja --reasoning-format none --chat-template-kwargs '{"enable_thinking":false}' \
  --cache-prompt --no-warmup --no-context-shift --no-webui --no-slots
```

Run one model process per assigned resource scope. The assistant never starts or downloads a model implicitly. Native prefix caching is enabled by default; `--no-prompt-cache` on the assistant disables its request flag. Reproducing the original failed profiles also requires their recorded source/configuration, not just this flag.

Set `AGENT_LAB_RESEARCH_KEY` in the assistant process environment to that local service key. Do not pass the key on the command line or save it in project files. Then run:

```sh
extras/research-assistant/.venv/bin/python -m agent_lab.research_assistant \
  --question 'Explain the two levels of retrieval in the indexed LightRAG paper.' \
  --run-dir /tmp/research-question-001 \
  --mcp-url http://127.0.0.1:18863/mcp \
  --model-url http://127.0.0.1:18864/v1 \
  --model agentlab-research-qwen3-4b-cpu \
  --model-fingerprint '<verified-model-file-SHA256>' \
  --max-turns 6 --max-output-tokens 256 --request-seconds 180
```

Use an actual file SHA256 for the model you serve; this is the operator's declaration, not remote server attestation. The model alias must match the native server. Model and MCP endpoints are loopback only; there is no cloud-provider fallback or implicit API purchase. A model with different chat/tool support may behave differently.

Repeat the exact command to resume a committed node or reuse a completed result. The run identity binds the question, endpoints, declared model fingerprint, active library generation, source code, framework and limits. Changes require a new run directory. Store mutable SQLite and request journals on an admitted local filesystem. Do not move live state onto NFS, delete a journal to reset its limit, or reuse a closed experiment budget.

After the writer has stopped and closed SQLite connections, export a reading report without starting either service:

```sh
extras/research-assistant/.venv/bin/python -m agent_lab.research_report \
  --run-dir /tmp/research-question-001 \
  --store /path/to/paper-store --output /path/to/new-reading-report
```

Repeat `--run-dir` to combine up to16 runs. The new output directory contains Markdown, JSON reference metadata and a completion manifest. Uncompleted model tasks stay uncompleted with recorded diagnostics; the command returns2 for export errors, rather than for an original uncompleted model task. Archived source versions must remain available. [Report usage and validation](../../docs/research-reading-report.md) explain the stopped-input contract and the actual historical-page example.

Model requests are reserved durably before HTTP transmission, with no transport retry, redirect or environment proxy. Failed/unknown attempts stay charged. An asyncio deadline covers the whole request in addition to HTTP idle timeouts. Complete responses are cached before node checkpointing so the same request body can reuse its saved reply after restart. A tool query interrupted before its node commits can be repeated on resume; this is not exactly-once tool execution. The separate retrieval service's embedding budget is not controlled by the assistant's generation-request journal; operators must also bound that resource.

`submitted` means final arguments passed the structural/reference contract. Search/read choices are model-selected; at most one final-format request uses the exact `submit_answer` argument schema through `response_format=json_schema` with `tool_choice=none`, within the same turn budget, after an unsubmitted draft or on the last available turn. The model still supplies all content and citation refs. The application constrains termination format; this is not fully unforced terminal tool selection. Unstructured text is never accepted or automatically assigned citations. `supported` is the model's own status; `semantic_entailment_checked` remains false. `insufficient_evidence` reports a lack of usable material after a coverage/evidence check. Truncation, source changes, invalid finalization and turn exhaustion remain explicit outcomes. Review generated answers against the cited pages.

Named tool selection alone did not guarantee structured output on the pinned backend. Its [documented response schema support](https://github.com/ggml-org/llama.cpp/blob/4783b1145c7073bb809f4c282ff4853cbfe42954/tools/server/README.md#post-v1chatcompletions-openai-compatible-chat-completions-api) constrains final arguments instead. The adapter handles only a complete, unambiguous object with exactly `status`, `answer`, and `citations`, on that final schema request with normal completion. It sends the object through the same final-tool validator and reports `final_transport=schema_arguments_content`; it never infers citations from plain prose. Duplicate keys, extra fields, truncation and unforced content are rejected. The private cache retains the original service response; normalized arguments are not presented as a native tool call.

[Three-case workflow input](../../examples/research-assistant/tasks.json) is an operator-authored known-collection diagnostic, not a held-out benchmark. The final CPU profile submitted two cases; the absent-paper case produced invalid final arguments and was rejected. This does not establish reliable abstention or general QA accuracy. Complete model wire responses and paper text are kept private; [published evidence](../../evidence/research-assistant/README.md) contains scoped results, short reviewed answer samples and provenance.
