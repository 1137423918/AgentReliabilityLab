# Full-request context accounting: controlled source retrieval

**No model inference, autonomous search, patch or maintenance acceptance.** Three explicit operator plans run through the real worker/Deep Agents/ChatOpenAI transport against a fake loopback tool-call service. All retrieve the same 86 original source lines and preserve every virtual file's text.

| Policy | Calls / HTTP requests | First / final reference tokens | Logical input sum |
| --- | ---: | ---: | ---: |
| Sequential 200-line pages | 5 / 6 | 2446 / 12330 | 43990 |
| Literal grep + operator enclosing span | 3 / 4 | 2446 / 3658 | 11341 |
| Python outline + symbols | 3 / 4 | 2732 / 6683 | 19054 |

AST adds 286 reference tokens to the first request. Both plain first HTTP JSON bodies are identical; human prompt/source/required lines are held fixed. Grep is cheaper for these known names; this is not evidence that AST is universally cheaper or that a model can find or repair the target. Source response bytes alone do not account for full prompts.

## Audit and scope

- [report.json](report.json), [protocol.json](protocol.json), [runtime.json](runtime.json): pinned inputs, per-request token/byte counts, source/binary/library hashes and environment.
- `sequential_200/`, `literal_grep_then_span/`, `python_outline_then_symbols/`: all rendered UTF-8 prefixes and captured [example request set](literal_grep_then_span/requests.json). These bytes are unmodified from the server measurement. HTTP authorization headers were never captured.
- [native-token-ids.jsonl](native-token-ids.jsonl): 14 token arrays in protocol policy order and request order; lengths and prompt-prefix LCP fields recomputed independently. HTTP JSON bodies reconstruct their exact original SHA/length. Native runtime verifies 40 library hashes from the prior fixed backend manifest.
- [logs/control.log](logs/control.log), [native vocabulary log](logs/native-tokenizer.log), [compile log](logs/compile.log), [artifacts.json](artifacts.json): 28 explicitly transferred artifacts, original/public hashes. Generated summaries/README/license are outside the transfer manifest.
- `preflight/` retains an unversioned-library link error, virtualenv inheritance error, fresh FileData timestamp equality mistake and compact-read parser rejection. The final driver compares exact text/file set, understands actual compact line headers, validates header/body counts and still requires all target lines verbatim. Original rejected directories/databases stay private, not deleted or counted as successes.

Tokenization uses fixed Qwen3.5-9B GGUF vocabulary and pinned llama.cpp **vocab_only** with no inference context or GPU. Rendering uses the exact template bytes with reference Jinja2 3.1.6; **native minja/server equivalence is unverified**. Counts are exact for these rendered bytes, not observed model usage. Logical input sum repeats cached prefixes and is not compute, latency, dollars or billed tokens. Prompt-only LCP is diagnostic and excludes actual generated-token/cache behavior. The JSON-body byte count excludes HTTP/TLS headers; component bytes are not additive token attribution.

The grep span boundaries and all function goals are operator provided, not autonomous discovery. One public objective is not a general benchmark. Both the 32768 context window and 1536 reserve are held fixed; all final contexts fit. No existing neural failure is relabeled as success. Runtime core and the prepared neural source-navigation task are unchanged and unrun.

[Protocol, commands and interpretation](../../docs/context-budget.md). Public tool/source text retains the [Deep Agents MIT license](UPSTREAM_LICENSE).
