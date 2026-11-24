"""Real loopback MCP controls reusing a completed index; never re-embed documents."""
from pathlib import Path
import asyncio,hashlib,json,os,socket,sys,threading,time,traceback
from agent_lab.research_embeddings import LocalE5Embedding
from agent_lab.research_library import open_generation
from agent_lab.research_mcp import create_app
import uvicorn
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
import httpx2
MODEL,STORE,OLD_CITATION,OUT=map(Path,sys.argv[1:]);OUT.mkdir(mode=0o700,exist_ok=False)
counts={'reserved_forwards':0,'completed_forwards':0,'text_inputs':0,'query_inputs':0};journal=OUT/'cpu-embedding-events.jsonl';began=time.monotonic()
def fingerprints():return {str(p.relative_to(STORE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in STORE.rglob('*') if p.is_file()}
def observer(phase,event):
    assert event['kind']=='query'
    if phase=='reserved':
        assert counts['reserved_forwards']<4 and counts['query_inputs']+event['inputs']<=4
        counts['reserved_forwards']+=1;counts['query_inputs']+=event['inputs']
    else:counts['completed_forwards']+=1
    with journal.open('a') as f:f.write(json.dumps({'phase':phase,**event,'counts':dict(counts)})+'\n');f.flush();os.fsync(f.fileno())
report={'ready':False,'GPU_used':False,'generation_model_calls':0,'caps':{'forwards':4,'query_inputs':4,'text_inputs':0}}
try:
    import torch
    before=fingerprints();root,meta=open_generation(STORE);assert len(meta['identity']['sources'])==20
    model=LocalE5Embedding(MODEL,observer=observer);old=json.loads(OLD_CITATION.read_text());assert not torch.cuda.is_initialized()
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(create_app(STORE,model),host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        deadline=time.monotonic()+20
        while not server.started:assert thread.is_alive() and time.monotonic()<deadline;time.sleep(.05)
        async def checks():
            async with httpx2.AsyncClient(trust_env=False,timeout=30,follow_redirects=False) as http:
                async with Client(streamable_http_client('http://127.0.0.1:'+str(port)+'/mcp',http_client=http),cache=None) as client:
                    listing=await client.list_tools();names=sorted(t.name for t in listing.tools);assert names==['list_sources','read_citation','search_sources']
                    assert all(t.output_schema is not None for t in listing.tools)
                    async def call(name,params):
                        r=await client.call_tool(name,params);assert not r.is_error and isinstance(r.structured_content,dict);return r.structured_content
                    sources=await call('list_sources',{});assert len(sources['sources'])==20
                    found=await call('search_sources',{'query':'LGABlock lightweight hybrid encoder','source_id':'ls_detr_readme','top_k':1})
                    assert found['results'][0]['source_id']=='ls_detr_readme' and not found['generated_answer']
                    read=await call('read_citation',{'citation_id':found['results'][0]['citation_id']});assert read['excerpt']==found['results'][0]['excerpt']
                    historic=await call('read_citation',{'citation_id':old['citation_id']});assert not historic['is_current_generation'] and historic['excerpt']==old['excerpt']
                    bad=await client.call_tool('read_citation',{'citation_id':'../invalid'});assert bad.is_error
                    c=dict(counts);missing=await call('search_sources',{'query':'anything','source_id':'tool_use_baseline'});assert not missing['results'] and c==counts
                    return {'transport':'actual TCP streamable HTTP loopback','tools':names,'declared_output_schemas':3,'five_successful_tool_calls':True,'invalid_citation_tool_error':True,'active_sources':20,'source_filter':True,'exact_citation':True,'old_citation_exact':True,'deleted_source_zero_embedding':True,'generated_answer':False}
        report['MCP']=asyncio.run(checks())
    finally:server.should_exit=True;thread.join(timeout=15);assert not thread.is_alive()
    assert fingerprints()==before and counts==model.counts and counts['reserved_forwards']==counts['completed_forwards']==1 and counts['text_inputs']==0
    assert not torch.cuda.is_initialized();report['unchanged_existing_store']=True;report['CUDA_initialized']=False;report['ready']=True
except BaseException as error:
    report['error']={'type':type(error).__name__,'message':str(error)[:1000]};traceback.print_exc()
finally:
    report['CPU_embedding_counts']=counts;report['wall_seconds']=round(time.monotonic()-began,3)
    if journal.exists():report['ledger_sha256']=hashlib.sha256(journal.read_bytes()).hexdigest()
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report),flush=True)
raise SystemExit(0 if report['ready'] else 2)
