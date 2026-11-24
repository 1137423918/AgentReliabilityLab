"""Real localhost MCP compatibility for the enlarged offline batch library."""
import asyncio
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
import uvicorn
from mcp import Client
import httpx2
from mcp.client.streamable_http import streamable_http_client
from agent_lab.research_mcp import create_app
from agent_lab.research_library import ingest
from test_research_library import FixtureEmbedding
import hashlib


class MCPBatchCompatibility(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.store=self.root/'store';self.model=FixtureEmbedding()
        self.path=self.root/'source.txt';self.manifest=self.root/'collection.json';self.publish('Original sonar recovery source')
        self.sock=socket.socket();self.sock.bind(('127.0.0.1',0));self.port=self.sock.getsockname()[1]
        self.server=uvicorn.Server(uvicorn.Config(create_app(self.store,self.model),host='127.0.0.1',port=self.port,log_level='error',access_log=False))
        self.thread=threading.Thread(target=lambda:self.server.run(sockets=[self.sock]),daemon=True);self.thread.start()
        for _ in range(200):
            if self.server.started:break
            if not self.thread.is_alive():self.fail('MCP server exited before readiness')
            await asyncio.sleep(.05)
        self.assertTrue(self.server.started)
    def publish(self,text):
        self.path.write_text(text);self.manifest.write_text(json.dumps({'version':1,'sources':[{'id':'alpha','path':'source.txt','title':'Owned fixture','kind':'test_fixture','url':'https://example.com/source','sha256':hashlib.sha256(text.encode()).hexdigest()}]}));ingest(self.manifest,self.store,self.model)
    async def asyncTearDown(self):
        self.server.should_exit=True;self.thread.join(timeout=10);self.sock.close();self.temp.cleanup();self.assertFalse(self.thread.is_alive())
    def unwrap(self,result):
        self.assertFalse(result.is_error)
        if result.structured_content is not None:return result.structured_content
        raise AssertionError('Expected structured MCP content')
    async def test_mcp_remains_bounded_and_reads_old_citation_after_new_publication(self):
        async with httpx2.AsyncClient(trust_env=False,timeout=15) as http:
            async with Client(streamable_http_client(f'http://127.0.0.1:{self.port}/mcp',http_client=http),cache=None) as session:
                old=self.unwrap(await session.call_tool('list_sources',{}))
                hit=self.unwrap(await session.call_tool('search_sources',{'query':'sonar','top_k':8}))['results'][0]
                before=self.model.calls;bad=await session.call_tool('search_sources',{'query':'sonar','top_k':9})
                self.assertTrue(bad.is_error);self.assertEqual(self.model.calls,before)
                self.publish('Updated sonar recovery edition')
                current=self.unwrap(await session.call_tool('list_sources',{}));self.assertNotEqual(old['generation'],current['generation'])
                retained=self.unwrap(await session.call_tool('read_citation',{'citation_id':hit['citation_id']}))
                self.assertEqual(retained['excerpt'],hit['excerpt']);self.assertFalse(retained['is_current_generation'])


if __name__=='__main__':unittest.main()
