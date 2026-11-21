"""Durable attempt/JSON-byte limits for asyncio and HTTPX2 loopback clients.

This transport is separate from the synchronous maintenance worker. Cancellation
can consume a reservation without sending; an unknown attempt is never refunded.
"""

import asyncio
from pathlib import Path

from .request_budget import RequestBudget, RequestBudgetError
from .storage import admit_state_directory


def open_budget(directory, owner_sha256, limits, journal_id=None, *, create=False):
    """Create in a fresh directory or reopen an existing journal during startup."""
    directory = Path(directory)
    admit_state_directory(directory)
    if create:
        if journal_id is not None:
            raise RequestBudgetError("An expected journal ID is for resume, not creation.")
        try:
            directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        except FileExistsError as error:
            raise RequestBudgetError(
                "A new budget needs a fresh directory; reopen existing state instead."
            ) from error
    return RequestBudget(directory, owner_sha256, limits, journal_id, create=create)


async def _complete_io(operation):
    """Drain journal writes/response closes before propagating cancellation.

    A cancelled to_thread await does not stop its thread. Shielding only these
    I/O operations prevents a journal write from continuing after return.
    Network requests themselves remain cancellable.
    """
    task = asyncio.create_task(operation)
    cancellation = None
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError as error:
            if task.cancelled():
                raise
            cancellation = error
        except BaseException:
            if cancellation is not None:
                raise cancellation
            raise
    if cancellation is not None:
        raise cancellation
    return result


def make_async_http_client(budget):
    """Create an HTTPX2 asyncio client; own and close it with async with.

    Only POST loopback chat completions are admitted. Redirects, environment
    proxies and connection retries are disabled. This counts serialized request
    bytes/attempts, not tokens, money, completed responses or tool effects.
    """
    import httpx2

    admit_state_directory(budget.directory)

    def reserve(body, path):
        admit_state_directory(budget.directory)
        return budget.reserve(body, path)

    class BudgetTransport(httpx2.AsyncBaseTransport):
        def __init__(self):
            self.inner = httpx2.AsyncHTTPTransport(retries=0)

        async def handle_async_request(self, request):
            if (
                request.url.host not in ("127.0.0.1", "localhost", "::1")
                or request.url.scheme not in ("http", "https")
                or request.method != "POST"
                or not request.url.path.endswith("/chat/completions")
            ):
                raise RequestBudgetError(
                    "Budgeted async transport supports only loopback chat completions."
                )
            sequence = await _complete_io(
                asyncio.to_thread(reserve, await request.aread(), request.url.path)
            )
            try:
                response = await self.inner.handle_async_request(request)
            except Exception:
                await _complete_io(asyncio.to_thread(budget.observe, sequence))
                raise
            # CancelledError is a BaseException: an unknown in-flight attempt
            # stays reserved, including across process death and later reopen.
            try:
                await _complete_io(
                    asyncio.to_thread(budget.observe, sequence, response.status_code)
                )
            except BaseException:
                await _complete_io(response.aclose())
                raise
            return response

        async def aclose(self):
            await _complete_io(self.inner.aclose())

    return httpx2.AsyncClient(
        transport=BudgetTransport(), follow_redirects=False, trust_env=False
    )
