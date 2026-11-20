# Checking reference prompts against the native server converter

The 14 fixed requests from the [context budget audit](context-budget.md) were replayed on the authorized CPU server through **the actual `oaicompat_chat_params_parse` symbol in the pinned `libllama-server-impl.so`**, then compared with the historical reference prompts. All **14 prompt byte strings and 14 complete token-ID arrays match**. An independent call through the common-chat renderer also produces the same text for each request. These are the same 14 inputs, not 28 independent cases.

This closes the reference-renderer uncertainty for these exact requests and settings. It does not establish universal template equivalence, actual HTTP delivery, inference usage, cache behavior, generation, or maintenance success. No HTTP listener, inference context, tensor inference or GPU was used. Historical model timeouts remain failures.

## Fixed identity and comparison

- Backend: llama.cpp b12576, commit `4783b1145c7073bb809f4c282ff4853cbfe42954`; the existing official shared libraries are used without rebuilding or editing them. All 40 previously recorded runtime library hashes are verified.
- Model: the existing Qwen3.5-9B Q4_K_M GGUF, SHA-256 `cd76ec205963b3b33350093e6904d9de16c4e666fd104e1f632d25c7f15f2a13`. Streaming hash verification precedes vocabulary-only loading. The template is taken from the GGUF and its exact SHA is checked against the historical reference template.
- Converter settings mirror the earlier CPU service: Jinja enabled, thinking disabled, reasoning format none, assistant prefill enabled by the pinned default, no image/audio/video projector. The original request bodies are passed to the actual converter. A restricted manual input mapping is a separate comparison branch, not a replacement for that converter.
- Historical HTTP JSON bodies reconstruct their recorded SHA and byte length. Each original prefix and all original token arrays remain byte-identical. No retrieval plan or tool response was regenerated.
- Both old and new token arrays use the same vocabulary and flattened-text settings: `add_special=false`, `parse_special=true`. This is an exact comparison of those tokenization settings, not an observation of a live inference slot's accounting. Native prompt parts and their `is_input` markers are also retained.

The logical input sums therefore remain **43,990 / 11,341 / 19,054** for sequential pages / known-name grep and span / Python outline and symbols. They include repeated prefixes; no latency, billed-token, cost, cache-saving or autonomous-localization conclusion follows. This is one operator-supplied source objective and one model/backend configuration.

## Reproduction

Use the pinned source headers, existing model and existing native runtime. Compile only the small audit program; a normal C++17 compiler can use:

```sh
g++ -std=c++17 -O2 -Wall -Wextra -Werror \
  -isystem /path/to/pinned-source/common \
  -isystem /path/to/pinned-source/include \
  -isystem /path/to/pinned-source/ggml/include \
  -isystem /path/to/pinned-source/tools/server \
  -isystem /path/to/pinned-source/tools/mtmd \
  -isystem /path/to/pinned-source/vendor \
  benchmarks/native_template.cpp -o /path/to/native-template \
  -L/path/to/native -L/path/to/runtime-libs \
  -Wl,-rpath,/path/to/native -Wl,-rpath,/path/to/runtime-libs \
  -Wl,-rpath-link,/path/to/native -Wl,-rpath-link,/path/to/runtime-libs \
  -l:libllama-common.so.1 -l:libllama.so.1 \
  -l:libllama-server-impl.so
python benchmarks/native_template_audit.py \
  --input evidence/context-budget --model /path/to/pinned-model.gguf \
  --native /path/to/native-template --library-dir /path/to/native \
  --runtime-dir /path/to/runtime-libs --output /path/to/fresh-output
```

The recorded server had a C compiler but no C++ frontend or headers. Two official Rocky Linux RPMs were downloaded by HTTPS and **extracted into a task-owned directory**, without installing packages or changing existing environments. The installed AlmaLinux GCC driver invoked that extracted GCC 11.5 C++ frontend and headers; the original native bundle's runtime libraries remained pinned. [compile.json](../evidence/native-template/compile.json) records the actual command and package identities; the generic command above is a reproduction recipe, not the literal recorded command. Package hashes identify the downloaded bytes; no claim of independently verified RPM signatures is made.

Native replay is limited to 4 GiB address space, 90 CPU seconds, 120 wall seconds and nice 19; GPU visibility is empty and the model's device list is empty. Compilation has separate bounded limits. Inputs are fixed before execution by the transferred driver and prior evidence; no new task-success metric was introduced. This adds an audit utility, not a worker-core change, so the previous 74-test core suite was not rerun or enlarged.

The initial compile used an unsupported stream overload of the pinned `common_json::parse`. That failure is retained in `preflight/`; the final source reads a string first, compiles successfully, and is the source bound by the final receipt. The preliminary common-only successful replay remains private and is not an additional score.

## Evidence and source references

[Complete evidence](../evidence/native-template/README.md) includes native prompt/token output, per-request comparison, exact compile receipt, the initial failure and file hashes. Six relevant source files were independently fetched from the official pinned commit and compared with the header/source archive. The [server route](https://github.com/ggml-org/llama.cpp/blob/4783b1145c7073bb809f4c282ff4853cbfe42954/tools/server/server-context.cpp) calls the same converter for chat completions and apply-template; the [converter implementation](https://github.com/ggml-org/llama.cpp/blob/4783b1145c7073bb809f4c282ff4853cbfe42954/tools/server/server-common.cpp) and [common-chat interface](https://github.com/ggml-org/llama.cpp/blob/4783b1145c7073bb809f4c282ff4853cbfe42954/common/chat.h) define the exercised path. Calling those library functions directly does not exercise HTTP middleware, slot scheduling or generation.
