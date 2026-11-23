# Report retrieval: real-artifact CPU diagnostic

2026-11-23. The existing real 9B report-audit failure motivated an optional lexical catalog policy. This is application engineering and retrieval diagnostics; **there are no new neural task scores**. [Implementation and limitations](../../docs/report-retrieval.md).

The corpus contains **24 actual project reports**, copied byte-for-byte from commit `301220730b5c740ee847f0c119c02caf612b9f86`. [Catalog and original artifact hashes](corpus/catalog.json). The **19 frozen queries** comprise two previously seen development questions and seventeen operator-authored, unblinded diagnostic queries. They are not a held-out or independent user evaluation. Metadata descriptions and queries were authored with knowledge of the reports.

| Policy | Queries with every required report | Mean serialized result bytes | Maximum bytes |
| --- | ---: | ---: | ---: |
| Full catalog,24 entries | 19/19 | 5272 | 5272 |
| Unique-term overlap,up to4 entries | 19/19 | 1495.42 | 1790 |
| BM25,up to4 entries | 19/19 | 1512.47 | 1808 |

BM25 k1=1.2/b=0.75, fixed identifier splitting and English stop words, each unique query term once. Ranked replies include their explanations and fit4096 UTF-8 bytes. The full-catalog baseline retains complete recall while exceeding that smaller response budget; it is not presented as an equal-budget low-recall baseline. **BM25 did not improve coverage over simple term overlap here**. No post-result parameter, query or label tuning. [All query results](results/cases.json) and [aggregate](results/summary.json).

Only report ID, description and advertised JSON-pointer names enter ranking. No answer values, judgments, hidden file reads, embeddings or model are used by the retriever. Lexical filtering can miss relevant reports; query="*" requests the original full catalog. Selection is not evidence: normal read receipts and remote verification are still required. The MCP listing still transfers full metadata to the adapter and validates reports server-side; filtering changes the model-visible reply, not that MCP transfer or file-validation work.

## Actual server checks

Seven [module controls](logs/retrieval-unit-controls.log) pass. Three real MCP2/FunctionAgent/TCP scenarios pass: ranked listing, explicit full-catalog fallback, zero-match followed by full fallback. Each completes receipt-checked facts and closes the same audit; replies from the model endpoint are explicitly scripted, using3/3/4 POSTs. [Scenario results](controls/ranked.json).

Four original acceptance/rejection controls ran with the old adapter and the new default mode, each using9 scripted POSTs. All nine corresponding serialized model-request bodies have identical SHA256. [Baseline](controls/baseline.json), [default candidate](controls/default-candidate.json). This equivalence applies to those exact scripted requests, not arbitrary conversations. Counts overlap older control scenarios and must not be added to the historical130 core snapshot.

Node-local Linux CPU, existing locked Python3.11/MCP2.3.0/LlamaIndex Core0.14.26 runtime;4 CPUs/nice19,32GiB virtual-memory cap,3GiB owned-RSS guard,900s job wall. Actual job128.737s, no installation, GPU or neural calls. Lint passes. [Phase report](run-report.json), [process/port/lock audit](cleanup.json), [pre-execution protocol](operator/protocol.json). The old 3B generation ledger, unknown-attempt budgets, training and 9B failures remain unchanged.

The six exact tested Python files are under [tested-source](tested-source/agent_lab/report_retrieval.py); formatting ASTs matched local inputs before synchronization. Operator text is path-normalized and labeled `.py.txt`; its public hash differs from the original bytes bound in the protocol. [Export manifest](export-manifest.json) preserves both hashes; [public payload manifest](artifacts.json) covers this evidence directory excluding itself. Model wire bodies, audit handles, environments and weights are excluded.

## Reproduce on a CPU server

```sh
python -m unittest discover -s tests -p test_report_retrieval.py -v
python -m benchmarks.report_retrieval \
  --root evidence/report-retrieval/corpus \
  --manifest evidence/report-retrieval/corpus/catalog.json \
  --cases benchmarks/report_retrieval_cases.json --output /tmp/fresh-retrieval-diagnostic
```

Use Python3.11+. Real SDK controls additionally require the locked `extras/mcp-agent` runtime and a local MCP evidence service; see the [method page](../../docs/report-retrieval.md). The optional BM25 mode also adds a concise planning prompt. Retrieval and prompt changes must be separated in a future real-model ablation before attributing any application benefit. Directory reply bytes are not full-request input tokens, total network bytes, latency or cost. The current dataset is small and curated; a broader independently judged corpus and real-model task completion remain unverified.
