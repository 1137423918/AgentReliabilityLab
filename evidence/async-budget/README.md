# Async request budgets: cancellation, restart and SDK retries

The existing maintenance worker deliberately remains synchronous. This opt-in asyncio/HTTPX2 transport reuses its unchanged RequestBudget journal and storage admission code. A separate budget-only wheel imports no Deep Agents/LangChain worker stack; its three module files are byte-identical to the canonical sources, verified again after installation in the isolated Pydantic AI environment.

## Observed server results

- Complete core suite: **116 passed / zero skipped**; eight new async checks are included. Focused checks are not added again. Unittest251.556s / supervised phase254.435s; no speedup comparison.
- Pydantic AI2.71.0 / OpenAI SDK3.57.0 / HTTPX2=2.16.2: four actual SDK/tool cases against an explicitly fake HTTP service. **Eight POSTs /3250 serialized-body bytes**, not eight neural requests or a model repair score.
- Normal tool roundtrip:2 HTTP200; an async tool reads the real public lifecycle report and returns its SHA/count. Reopening the spent journal rejects another run.
- In-flight cancellation:1 POST, response status unknown; its reservation remains charged after reopening. No refund or extra POST.
- Four concurrent Agent.run calls: one shared three-request cap; actual3 HTTP200/tool reads. The contract allows scheduling to complete0or1 runs; it does not require round-robin fairness.
- SDK max_retries=2 with controlled503 replies:2 HTTP503; the next SDK attempt is denied before sending. SDK retries cannot bypass the shared cap.

All four journals are exported byte-identically. Server body hashes/lengths were matched to reservations at runtime; full conversational wire bodies were not persisted, so the public files do not provide an independent full-payload trace. Scripted replies and synthetic token usage are test controls, not neural inference, token-cost or reasoning evidence.

## Cancellation and initialization contracts

Reservations are committed before transport send. Blocking journal operations run in a thread; cancellation waits for an outstanding journal write to finish before returning. Network waits stay cancellable. A cancellation can therefore consume a reservation without sending; unknown in-flight work is never refunded. Responses are closed if status persistence is interrupted. Held filesystem locks can delay cancellation; no hard cancellation-latency guarantee is made.

Create a budget only in a **fresh directory**. Reopen with create=False and keep the expected journal_id in job metadata. An extra no-network fault probe found that the first standalone API could recreate a lost journal and replace its expected ID, clearing used attempts. The final wrapper refuses existing-directory initialization and expected-ID creation; missing journals fail closed. The existing wire503/reopen check now deletes its charged journal and verifies that every mistaken initialization form is rejected. The legacy worker's manifest-based resume and canonical synchronous journal code were not changed.

The first focused run had6pass/2readiness failures: cold dependency imports and fresh-process initialization had not reached the intended fault boundary. Final fixtures use a health GET before fault injection and a fresh-child READY handshake, separately bounded at30s. The actual3s boundary waits,5s journal gates, quotas and600s phase limits were retained; first failures are not regraded. Health GETs are setup traffic, not inference POSTs. A proposed eager-import-only preparation was never executed and is not another experiment.

The intermediate116-test green profile and its old wheel were not released: the later journal-loss probe revealed the missing initialization assertion. Its sources/report remain in ready-before-init-guard/, distinct from normal/. Final code and installed-wheel guard checks pass; no test count was added for extending that existing check.

## Reproduction and boundaries

Run all process/HTTP experiments on the authorized Linux server. Mutable journals/fixtures used private ext4; four CPU cores/nice19,48GiB address-space limit,16GiB sampled tree RSS,12GiB memory floor and bounded phases. Guards did not trigger. The worker's68 dependency name/version pairs remain unchanged; Python import caches are not claimed byte-identical. Framework dependencies are hash-locked separately in bootstrap/framework-lock.txt.

Download the [budget-only wheel](https://1137423918.github.io/downloads/agentlab_durable_budget-0.1.0-py3-none-any.whl), SHA256 `a27d27b935b9646a0bed30cac5cc300f783311860471a2df92c053ac9657005a` (8441bytes). Build and usage: [package guide](https://github.com/1137423918/AgentReliabilityLab/tree/main/packages/durable-budget); [controlled SDK case](https://github.com/1137423918/AgentReliabilityLab/blob/main/benchmarks/pydantic_budget_case.py).

Asyncio only; no Trio, cloud-host, Responses or WebSocket support claim. Only loopback chat-completions POSTs are admitted; connection retries, environment proxies and redirect following are disabled. Set SDK retries explicitly; the shared cap counts them either way. Counters are attempts and body bytes, not tokens, fees, completed responses or exactly-once tool effects. Directory admission/checksums do not defend against a privileged owner replacing whole state directories, remounting filesystems or rewriting both state and checksums. No power-loss or general cross-host migration guarantee.

Primary API references: [Pydantic AI OpenAI-compatible provider](https://github.com/pydantic/pydantic-ai/blob/dee24dfb337f2e5ae937cd45d8564084bac55967/pydantic_ai_slim/pydantic_ai/providers/openai_compatible.py), [Pydantic AI dependency declaration](https://github.com/pydantic/pydantic-ai/blob/dee24dfb337f2e5ae937cd45d8564084bac55967/pydantic_ai_slim/pyproject.toml), [HTTPX2 custom transports](https://pydantic.dev/docs/httpx2/advanced/transports/), [asyncio cancellation shielding](https://docs.python.org/3.11/library/asyncio-task.html#asyncio.shield). Pinned package artifact hashes and actual installed versions identify the executed environment; the documentation commit is not claimed as the package wheel's build revision.
