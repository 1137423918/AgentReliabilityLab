# Current-source Python navigation

The Qwen3.5 CPU maintenance trace read lines 1–400 of a 1,250-line production file without reaching `to_posix_path` (line 822) or `validate_path` (line 846). The request budget was mostly consumed by prompt processing. This is motivation to improve source localization; it does not establish that navigation alone caused failure or that this tool improves model repair success.

`python_source_v1` is an explicit task capability. It adds one read-only `inspect_python` tool over **the current checkpointed virtual file state**, restricted to the task's declared file set. Existing tasks retain their tool list and system prompt. There is no host file access, subprocess, import of subject code, reference patch, external embedding service or GPU operation.

## Interface

1. Call `inspect_python(file_path="/path/module.py")` for an outline. It lists classes, synchronous/asynchronous functions and nested definitions with unique line/column IDs, qualified display names and exact line ranges including decorators. Repeated definition names retain distinct IDs. Display names longer than 160 characters are marked as truncated; IDs remain usable.
2. Select a returned `id`, then call with `symbol_id` and `expected_sha256` copied from `source_sha256`. The response contains exact source lines for that definition, numbered in the original file. Class ranges include the full class body; methods can be selected individually.
3. `offset` is zero-based within the outline or selected symbol. `limit` defaults to 40, accepts 1–120 items. Follow `next_offset` until null. All continuation pages require a matching source hash; after any edit, refresh the outline.

Every JSON response is bounded to 8,192 UTF-8 bytes. A long single line that cannot fit returns an explicit error rather than silently cutting executable text; use ordinary bounded `read_file`/`grep` for further investigation. Paging by bytes may return fewer items than `limit`. Wrong scope, stale hash, invalid page, missing symbol and unsupported Python syntax are explicit errors. The tool does not automatically unescape, repair or execute inspected text.

Hashes bind to current virtual UTF-8 text, not a moving checkout or an in-memory index cache. The tool reparses on each call; no index needs invalidation across edits or process restarts. The worker's Python AST grammar is identified in each response (Python 3.11 in these server checks). Non-Python files and parse failures remain accessible through existing file tools. Comments, top-level assignments and dynamically generated definitions are not indexed; Python AST output is not a complete semantic or cross-file dependency index. Maximum source size is 2 MiB, matching the worker's overall virtual-text bound.

## Observed validation

The server suite completed 63 checks: 49 passed, 14 skipped for missing jsonschema (154.217 seconds). The new six source checks are included in 49. Both real reference cases passed the fixed acceptance and produced the same 1,573-byte patch. The checkpoint-resume case was killed immediately after the production edit; source-tool replies after resume matched the edited files.

The real-source retrieval control returned one outline and two source pages (11,127 UTF-8 bytes total; maximum 4,766 per response). The two target names were explicitly selected by the operator. The additional OpenAI tool schema serializes to 988 bytes, before full system-prompt and conversation overhead. No net token, cost, speed or neural success improvement is measured.

## Enable and reproduce

Add `python_source_v1` to a task's `required_features`, or use [the prepared model preset](../tasks/deepagents-path-model-source-navigation.json). That preset keeps the Qwen3.5 task's prompt, model, acceptance and budgets and only enables this capability; **it has not run neural inference**. Historical task files and failure reports are unchanged.

On the authorized Linux server, use the existing worker environment and put the prepared upstream test environment on PATH:

```sh
python -m unittest discover -s tests -v
python benchmarks/source_navigation.py --repo /path/to/deepagents \
  --output /path/to/fresh-source-navigation-control
```

The control pins Deep Agents `744a797e3b9495539ca35571eeffd112a205f5c8`. It retrieves two operator-selected symbols through bounded pages, separately from model inference. A fixed reference edit plan then runs normally and after an actual SIGKILL immediately after the production edit. Source-tool replies must hash to the edited worktree contents, not the original blobs. Both cases must pass import checks, 113 fixed original tests, 119 candidate tests and 28 independent path contracts, with identical patches. These test groups overlap; counts are not added. The reference patch and selection targets are operator supplied; this is infrastructure validation, not autonomous localization or repair.

[Evidence and results](../evidence/source-navigation/README.md). Output-byte counts, where reported, include source/outline JSON only; they omit prompts, tool schemas, conversation history and future model choices. They are not token savings, cost savings, latency improvements or model success measurements.

The integration follows the official [LangChain ToolRuntime state API](https://docs.langchain.com/oss/python/langchain/tools) and [Deep Agents custom-tool interface](https://docs.langchain.com/oss/python/deepagents/tools). Tests exercise the actual pinned installed packages; current documentation alone is not treated as proof of compatibility.


## Later full-prefix accounting

The original source-navigation control above measured response bytes only. A separate [full-request budget control](context-budget.md) now includes schemas, worker prompts and all history with reference tokenization. For the same operator-known function objective, AST uses fewer logical input tokens than sequential pages but more than literal grep plus a supplied span. It does not establish real-model net cost, latency or repair improvement; the neural preset remains unrun.
