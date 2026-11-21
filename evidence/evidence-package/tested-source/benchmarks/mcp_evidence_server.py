"""Compatibility module for the canonical installable evidence MCP service."""

from agent_lab.evidence_mcp import create_app, main

__all__ = ["create_app", "main"]


if __name__ == "__main__":
    main()
