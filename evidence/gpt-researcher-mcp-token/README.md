# GPT Researcher: authenticated HTTP MCP discovery and tool calls

The documented `connection_token` configuration was forwarded as a top-level `token` option. The real LangChain adapter rejects that keyword; `get_all_tools()` catches the error and returns an empty list. A private research source consequently appears to have no tools. The fix sends an HTTP Bearer header, preserves other headers and respects an explicit Authorization header regardless of casing. Unsupported WebSocket/stdio token settings fail clearly; stdio credentials belong in `env`.

Source: [upstream `9d39a2f86d55`](https://github.com/assafelovic/gpt-researcher/tree/9d39a2f86d55e264f69dfeff2365f27fad3c1144) → [candidate `973514b3737a`](https://github.com/1137423918/gpt-researcher/tree/973514b3737a0befd4b27f54685db485793ffa74). Four upstream files change: converter, regression tests and two documentation pages. [Patch](patch.diff), [source binding](source-binding.json), [runtime constraints](runtime-constraints.txt), [export identities](export-manifest.json). The original upstream license is retained in each profile. [Formal PR #2367](https://github.com/assafelovic/gpt-researcher/pull/2367) is open and not merged. [Same-head workflow/review observation](PR-state.json): no unresolved review threads; Tests and LLM Cost Analysis both report `action_required` with zero jobs, pending maintainer approval. Server validation does not establish upstream CI or maintainer approval.

| Server validation scope | Observed result |
| --- | --- |
| Same 11 regression cases on unchanged upstream | 11 failed, including real adapter rejection of `token` |
| Same cases on the fix | 11 passed; 3 actual authenticated MCP/TCP discovery + invocation scenarios |
| MCP-related selection | 44 passed, 2 skipped, 1085 deselected |
| Full standalone collection | 1131 tests collected; 2 collection skips |
| Repository offline selection | 1112 passed, 17 skipped, 4 deselected |
| Library and ASGI app imports | Passed |

Scopes overlap and are not added. The 17 skips include the two collection skips. The full selection uses the repository CI command, excluding its three live-test modules (four collected cases), with the optional adapter explicitly installed. It is Linux/Python 3.12.16 evidence, not a claim about every supported interpreter or production deployment. Exact tool versions and all output are under [v1](v1/).

The three real loopback scenarios cover token-only configuration, an explicit `Authorization` override and a lowercase `authorization` override. Each rejects an unauthenticated HTTP request with 401, discovers the actual MCP tool and invokes it once through `MultiServerMCPClient`. Tools and service data are fixtures; no LLM decides the call. The optional-adapter scenarios skip in a bare environment without the adapter, but all three executed in this server proof. No production credential, paid service, external MCP endpoint or neural model was used. This does not validate a complete research report or LLM tool selection.

Both frozen server profiles terminated ready with unchanged source and zero owned processes. The initial full suite used the same Python ASTs as the final commit; only original document EOF conventions and one test trailing blank line were cleaned up. The [final profile](final/) independently verifies that change, confirms exact committed source hashes and reruns the same 11 red/green cases with identical baseline/candidate test bytes. Those repetitions are not independent new successes. [EOF receipt](EOF-cleanup.json), [cleanup](cleanup.json).

To run the focused regression in an isolated Linux/Python 3.12 environment, check out the candidate commit, install the project test extra and optional adapter, then run:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -c /path/to/runtime-constraints.txt -e '.[test]' langchain-mcp-adapters==0.3.2
GPTR_BLOCK_NETWORK=1 .venv/bin/python -m pytest tests/test_mcp_client_auth.py --timeout=30 -q
```

Constraints record observed package versions rather than wheel hashes; the original editable install path was removed and the source commit is pinned separately. The test network guard allows loopback. Tokenizer cache warming happened before the offline full suite, as in upstream CI. Evidence exports only source/logs/metadata, omitting environments and caches. Private server paths are normalized and original/public hashes distinguished. Personal homepage/Profile/Pages remain frozen.
