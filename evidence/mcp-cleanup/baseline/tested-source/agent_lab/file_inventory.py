"""Task-local directory-listing policy for complete, bounded file inventories."""

import json

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

FEATURE = "file_inventory_v1"
MAX_INVENTORY_BYTES = 8192


def inventory_prompt(files):
    """Render the complete canonical task paths, never a silently partial list."""
    catalog = json.dumps(["/" + name for name in files], ensure_ascii=False)
    if len(catalog.encode("utf-8")) > MAX_INVENTORY_BYTES:
        raise ValueError("Complete file inventory exceeds 8192 UTF-8 bytes.")
    return (
        " Complete editable file inventory (JSON):\n"
        + catalog
        + "\nThese are all editable files. Use these paths directly. "
        "Directory listing with ls is unavailable for this task."
    )


class FileInventoryMiddleware(AgentMiddleware):
    """Hide ls for this graph and reject stale or unsolicited ls calls explicitly.

    This is a navigation policy, not a filesystem sandbox. File scope and patch
    acceptance remain the worker's separate materialization invariants.
    """

    @staticmethod
    def _filtered(request):
        return request.override(
            tools=[
                tool for tool in request.tools if getattr(tool, "name", None) != "ls"
            ]
        )

    @staticmethod
    def _rejection(request):
        if request.tool_call["name"] == "ls":
            return ToolMessage(
                content="Directory listing is unavailable for this complete file inventory task. Use the listed file paths directly.",
                name="ls",
                tool_call_id=request.tool_call["id"],
                status="error",
            )
        return None

    def wrap_model_call(self, request, handler):
        return handler(self._filtered(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._filtered(request))

    def wrap_tool_call(self, request, handler):
        rejection = self._rejection(request)
        return rejection if rejection is not None else handler(request)

    async def awrap_tool_call(self, request, handler):
        rejection = self._rejection(request)
        return rejection if rejection is not None else await handler(request)
