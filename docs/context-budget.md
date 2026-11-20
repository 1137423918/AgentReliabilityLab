# Full-request context budgets for source retrieval

> 2026-11-21 follow-up: the [native server-converter replay](native-template.md) now matches all 14 captured prompt byte strings and full token arrays. The original reports below are unchanged; this proves equivalence only for those exact requests/settings, not observed inference usage.

Three operator-planned controls run through the actual `agent_phase`, Deep Agents 0.7.41, StateBackend and ChatOpenAI 1.8.5 transport. An explicitly fake loopback HTTP service returns tool calls; no neural model is queried. All controls retain the original Qwen3.5 maintenance task prompt, source commit and file inventory. Their retrieval goal is supplied separately by the operator: the complete original `to_posix_path` and `validate_path` definitions in Deep Agents commit `744a797e3b9495539ca35571eeffd112a205f5c8`.

The benchmark checks all **86 target lines verbatim** in actual tool messages and confirms the exact virtual file set and every file's text remain unchanged. It does not edit a candidate, run maintenance acceptance, establish autonomous localization, or add a model-success result.

## Observed reference accounting

| Operator policy | Tool calls | First prefix | Final context | Sum of logical input prefixes |
| --- | ---: | ---: | ---: | ---: |
| Sequential 200-line reads | 5 | 2,446 | 12,330 | 43,990 |
| Two literal greps, then enclosing span | 3 | 2,446 | 3,658 | 11,341 |
| Python outline, then two symbols | 3 | 2,732 | 6,683 | 19,054 |

Units are **reference-rendered prefix tokens**, not observed inference usage. Each full prefix includes system prompt, all available tool schemas, original human prompt, assistant tool calls and returned tool history. The final post-tool request is included, so there are 6 / 4 / 4 captured HTTP requests (14 total). The plain policies' first HTTP JSON bodies are byte identical; the AST case adds only the existing `python_source_v1` capability and its worker instruction. Its first-request overhead is 286 reference tokens. All final prefixes fit the declared 32,768 context plus 1,536 generation reserve.

The AST control returns 11,127 UTF-8 response bytes, versus 3,997 for grep + span and 37,531 for sequential reads. Counting source bytes alone misses schema, outline metadata and repeated-history overhead. For this known-name objective, grep is a strong baseline and AST does not win on input size. AST's structure, exact boundaries and current-content hashes serve a separate need. This is a scoped engineering inference from the controlled result, not a recommendation proven across models or tasks.

## What the counts mean

The original model's exact pinned chat-template bytes are rendered with Jinja2 3.1.6, parsed assistant tool arguments and thinking disabled. A small C utility uses the pinned llama.cpp b12576 shared library and the fixed GGUF vocabulary with `vocab_only=true`, no inference context and no GPU devices. The 5.6 GB GGUF SHA is checked by streaming; tensor weights are not loaded for inference. Source, template, native library and binary hashes are recorded.

This **reference Jinja renderer is not validated as native minja/server-equivalent**. Token IDs are exact for the published rendered bytes and GGUF vocabulary; they are not a receipt of an actual model request's usage. No generation token count, latency, money cost or end-to-end success is measured.

Logical input sum counts each request's full input, including repeated prefixes. It is not net prefill work: prompt caching can reuse a prefix, and actual model-generated history/cache behavior is absent here. A prompt-only longest-common-prefix diagnostic is published, but does not model generated-token caching, reasoning stripping, slot contention or cache eviction. Component byte counts are standalone diagnostics, not additive token attribution. Captured request byte counts cover JSON bodies, excluding HTTP/TLS headers.

The grep control receives operator-supplied function names and AST-derived enclosing boundaries; it is not a model-discovered boundary. AST selects names from the actual returned outline and uses returned IDs/hashes. The sequential control reads fixed 200-line pages from zero through the page containing the last goal. Every policy retrieves the same required lines; none is graded on a smaller goal.

## Reproduce on a CPU server

Use the existing project worker environment plus Jinja2 3.1.6 in a task-owned environment. This run used a new virtual environment with a read-only `.pth` reference to the original worker's site-packages, adding Jinja2/MarkupSafe only to the new environment. Ordinary `--system-site-packages` inherited the base Python, not the original worker virtual environment; its initial missing-dependency failure is retained. The original worker environment was unchanged.

For a normal isolated project checkout, `uv run --extra local-model --with jinja2==3.1.6 python benchmarks/context_budget.py ...` supplies the transport extra and reference renderer using the project's dependency environment. Replace `...` with the explicit arguments below. The read-only `.pth` setup above describes the recorded server environment, not a required shared-path layout.

Compile against the fixed backend headers and **versioned** shared library (the release's unversioned link was not usable):

```sh
cc -std=c11 -Wall -Wextra -Werror -O2 \
  -I /path/to/pinned-llama/include -I /path/to/pinned-llama/ggml/include \
  benchmarks/tokenize_vocab.c /path/to/native/libllama.so.1 \
  -Wl,-rpath,/path/to/native -Wl,-rpath-link,/path/to/native \
  -o /path/to/tokenize_vocab
# Provide task-local native runtime libraries through this process's LD_LIBRARY_PATH.
/path/to/worker-with-jinja/bin/python benchmarks/context_budget.py \
  --repo /path/to/deepagents --model /path/to/pinned-qwen35.gguf \
  --template /path/to/source--chat_template.jinja \
  --tokenizer /path/to/tokenize_vocab --output /tmp/fresh-context-budget
```

The fixed protocol is [context_budget_protocol.json](../benchmarks/context_budget_protocol.json). It was hashed before execution; preparation corrections did not alter the retrieval objective or metrics. Initial harness mistakes comparing timestamped FileData records and assuming numbered rather than compact read output were corrected, preserving rejected attempts. The final audit validates compact header/body line counts, trailing empty lines and every target line. It never bypasses coverage to publish smaller replies.

[Raw prefixes, JSON bodies, token IDs and checksums](../evidence/context-budget/README.md) support reconstruction. Databases and credentials are excluded. This is one public source objective with operator plans, not a held-out multi-task benchmark. New retrieval policies still need real-model evaluation under the same maintenance acceptance and budgets.

## Design references

Anthropic's [advanced tool-use discussion](https://www.anthropic.com/research/advanced-tool-use) distinguishes schema loading and accumulated intermediate results, and describes trade-offs when adding discovery steps. Its reported model results are not results of this local project. The [Deep Agents profile interface](https://docs.langchain.com/oss/python/deepagents/profiles) provides tool and prompt configuration; this control uses the existing pinned worker profile rather than assuming documentation proves runtime compatibility.
