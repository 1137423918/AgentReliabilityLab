# Optional real Agent/MCP consumer runtime

Pins the actual LlamaIndex FunctionAgent and MCP2 Client together in an isolated uv environment. Run uv sync --project extras/mcp-agent --frozen --no-install-project --no-default-groups from the checkout root, then use its Python for benchmarks.llamaindex_mcp_audit and benchmarks.mcp_agent_controls.

See ../../docs/mcp-agent.md for commands and measured boundaries. Model replies in controls are explicitly scripted; MCP tools and transport are real. This environment does not modify the original maintenance worker dependencies. On a slow shared filesystem, place the locked environment on authorized server-local storage; keep protocol and dependency identity records rather than extending model budgets.
