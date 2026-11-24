"""Loopback MCP access to an immutable, versioned local research collection."""
import argparse
from pathlib import Path
import threading
from typing import Any
import anyio
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
import uvicorn
from .research_library import search, citation, open_generation


def create_app(store, embedder):
    server = MCPServer('AgentLab Research Library', version='0.1.0')
    lock = threading.Lock()
    def serialized(function, *args, **kwargs):
        with lock:
            return function(*args, **kwargs)
    async def call(function, *args, **kwargs):
        try:
            return await anyio.to_thread.run_sync(lambda: serialized(function, *args, **kwargs))
        except (ValueError, OSError, KeyError) as error:
            raise ToolError(str(error)) from error

    @server.tool()
    async def list_sources() -> dict[str, Any]:
        """List the active indexed sources and their exact version fingerprints."""
        def read():
            root, meta = open_generation(store)
            return {'generation': root.name, 'sources': list(meta['identity']['sources'].values()), 'nodes': meta['node_count']}
        return await call(read)

    @server.tool()
    async def search_sources(query: str, top_k: int = 5, source_id: str | None = None) -> dict[str, Any]:
        """Retrieve candidate passages with citations; no generated answer or confidence promise."""
        return await call(search, store, query, embedder, top_k=top_k, source_id=source_id)

    @server.tool()
    async def read_citation(citation_id: str) -> dict[str, Any]:
        """Read the exact stored source span, including citations from older generations."""
        return await call(citation, store, citation_id)

    return server.streamable_http_app(stateless_http=True, json_response=True,
        max_request_body_size=8192, host='127.0.0.1')


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--store', type=Path, required=True)
    p.add_argument('--model-dir', type=Path, required=True); p.add_argument('--port', type=int, default=18863)
    a = p.parse_args()
    if not 1024 <= a.port <= 65535: p.error('Use an unprivileged local port')
    from .research_embeddings import LocalE5Embedding
    model = LocalE5Embedding(a.model_dir)
    uvicorn.run(create_app(a.store, model), host='127.0.0.1', port=a.port, workers=1,
                log_level='warning', access_log=False)


if __name__ == '__main__': main()
