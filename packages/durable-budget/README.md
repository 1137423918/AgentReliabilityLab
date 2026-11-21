# Durable request budgets for asyncio agents

This small wheel packages the canonical Agent Lab request journal, storage admission and asyncio/HTTPX2 client, without installing the maintenance-worker dependency stack. The worker itself stays synchronous. Validated with Python3.11, HTTPX2=2.16.2, PydanticAI2.71.0 and OpenAI SDK3.57.0 on Linux/ext4; see [evidence](../../evidence/async-budget/README.md).

## Build on the server

Use a dedicated build/framework environment with pip25.3/setuptools80.9.0/wheel0.45.1 installed. Dependency hashes are recorded in the evidence lockfile.

```sh
python packages/durable-budget/build.py --output /path/to/wheel-output
python -m pip install --no-deps /path/to/wheel-output/agentlab_durable_budget-0.1.0-py3-none-any.whl
```

Install HTTPX2 and framework dependencies from the recorded lockfile first. The builder copies three canonical modules unchanged into `durable_agent_budget`, builds without dependency resolution, checks wheel source bytes and writes a SHA256 receipt. No PyPI publication is performed.

## Create once, then reopen

```python
import asyncio
from hashlib import sha256
from durable_agent_budget import open_budget, make_async_http_client

limits = {"max_requests": 4, "max_request_bytes": 65536,
          "max_total_request_bytes": 262144}
owner = sha256(b"my-fixed-task-and-policy").hexdigest()
# Once only: this directory must not already exist.
budget = open_budget("/path/to/local/private-journals/job-001", owner, limits,
                     create=True)
# Persist budget.journal_id in the job's metadata. On subsequent startups use:
# budget = open_budget(state_path, owner, limits, journal_id=saved_id)

async def main():
    async with make_async_http_client(budget) as client:
        response = await client.post(
            "http://127.0.0.1:8000/v1/chat/completions",
            json={"model": "your-local-model", "messages": [
                {"role": "user", "content": "Your task"}]})
        response.raise_for_status()
        print(response.json())

asyncio.run(main())
```

Initialize budgets and clients during startup. Journal reads/writes run off the event loop; library imports, filesystem admission and client construction are not a hard low-latency API. Cancelled durable I/O is drained before cancellation returns. A reservation can be charged without a packet; unknown in-flight attempts remain charged. Never delete or recreate a spent journal to retry a run.

## Pydantic AI integration

Pass the guarded client to `AsyncOpenAI(base_url=loopback_url, api_key=local_key, max_retries=0, http_client=client)`, then use `OpenAICompatibleProvider("your-local-service", openai_client=sdk)` and `OpenAIChatModel`. Use a local-service key explicitly; this example needs no cloud key. The [four controlled SDK cases](../../benchmarks/pydantic_budget_case.py) include an actual report-reading tool, cancellation/reopen, concurrent Agent.run calls and explicitly enabled SDK retries under the same durable cap. They use fake replies, not a real model or autonomous repair.

The client is limited to asyncio and loopback chat-completions POSTs. Redirects/proxies/connection retries are disabled. Request counts/JSON bytes are not tokens or money. Low-level RequestBudget is a trusted building block; the recommended open_budget wrapper enforces fresh-directory creation and missing-journal refusal. This is conservative accounting, not a hostile-owner sandbox, response-memory limiter, tool idempotency layer or migration protocol.
