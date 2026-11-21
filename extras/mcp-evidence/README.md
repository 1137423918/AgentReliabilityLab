# Optional MCP runtime

This isolated uv project pins MCP2.3.0 and HTTPX2 2.16.2. Use the committed uv.lock with uv sync --frozen --no-install-project --no-default-groups; it does not add MCP to the maintenance worker environment. Run from the AgentReliabilityLab source checkout so benchmarks modules are available. See ../../docs/mcp-evidence.md for server/client commands, capability/receipt semantics and measured limits. No cloud model key is required or loaded by this service.
