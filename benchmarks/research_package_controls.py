"""Installed-artifact CPU application flow on two real maintainer documents."""
from pathlib import Path
import asyncio,hashlib,importlib.metadata,json,os,socket,subprocess,sys,time,traceback
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
import httpx2

PYTHON,ENTRY,CLI,DOCS,MODEL,OUT=map(Path,sys.argv[1:]);OUT.mkdir(mode=0o700,exist_ok=False)
ROOT=OUT/'neutral';ROOT.mkdir();bundle=OUT/'bundle';store=OUT/'store';budget=OUT/'budget';budget.mkdir()
identity={'purpose':'freshCPUwheelinstalledCLIcallableandactualMCP,notretrievalgainbenchmark','caps':{'forwards':32,'text_inputs':128,'query_inputs':8},'model_manifest_sha256':hashlib.sha256((MODEL/'model-manifest.json').read_bytes()).hexdigest(),'app_version':importlib.metadata.version('agentlab-research'),'documents':{str(p.relative_to(DOCS)):hashlib.sha256(p.read_bytes()).hexdigest() for p in DOCS.rglob('*') if p.is_file()}}
(budget/'identity.json').write_text(json.dumps(identity,sort_keys=True)+'\n');(budget/'events.jsonl').write_bytes(b'')
started=time.monotonic();report={'ready':False,'GPU_used':False,'generation_model_calls':0,'scope':'installedCLIcallableusesactualmodelwithobserver;rawconsoleprepare/check/read/help;actualMCP/TCP'}
def save(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def counts():
    rows=[json.loads(line) for line in (budget/'events.jsonl').read_text().splitlines()];reserved=[r for r in rows if r['phase']=='reserved'];completed=[r for r in rows if r['phase']=='completed']
    return {'reserved_forwards':len(reserved),'completed_forwards':len(completed),'text_inputs':sum(r['inputs'] for r in reserved if r['kind']=='text'),'query_inputs':sum(r['inputs'] for r in reserved if r['kind']=='query')}
def run(name,command):
    p=subprocess.run([str(x) for x in command],cwd=ROOT,capture_output=True,text=True,timeout=90)
    (OUT/(name+'.stdout')).write_text(p.stdout);(OUT/(name+'.stderr')).write_text(p.stderr)
    assert p.returncode==0,(name,p.stderr[-1200:]);return json.loads(p.stdout)
try:
    import importlib.util
    assert importlib.util.find_spec('agent_lab') is None and importlib.util.find_spec('deepagents') is None
    import agentlab_research.research_cli as installed
    assert '/site-packages/' in installed.__file__
    report['installed_origin']=installed.__file__;report['source_checkout_importable']=False
    report['prepare']=run('console-prepare',[CLI,'prepare','--directory',DOCS,'--output',bundle,'--base-url','https://github.com/1137423918/AgentReliabilityLab/blob/d05cdbb557e7226f0090290397bb44ec89e6db03/docs/'])
    assert report['prepare']['documents']==2
    before=hashlib.sha256((MODEL/'model-manifest.json').read_bytes()).hexdigest();report['model_check']=run('console-check-model',[CLI,'check-model','--directory',MODEL]);assert before==hashlib.sha256((MODEL/'model-manifest.json').read_bytes()).hexdigest()
    common=[PYTHON,'-I',ENTRY,budget]
    args=['ingest','--manifest',bundle/'collection.json','--store',store,'--model-dir',MODEL]
    report['ingest']=run('installed-ingest',[*common,*args]);c=counts();assert c['text_inputs']>0 and c['query_inputs']==0
    report['no_op']=run('installed-noop',[*common,*args]);assert counts()==c and report['no_op']['CPU_embedding_calls']['reserved_forwards']==0
    rows=json.loads((bundle/'collection.json').read_text())['sources'];target=next(r for r in rows if r['title']=='dependency-upgrade-compatibility.md')['id']
    query=run('installed-search',[*common,'search','--query','Authlib same authentication test identities before and after upgrade','--source',target,'--top-k','1','--store',store,'--model-dir',MODEL])
    citation=query['results'][0];assert citation['source_id']==target and not query['generated_answer']
    read=run('console-read',[CLI,'read','--store',store,'--citation-id',citation['citation_id']]);assert read['excerpt']==citation['excerpt']
    raw=(DOCS/'dependency-upgrade-compatibility.md').read_bytes().decode();assert raw[read['char_start']:read['char_end']]==read['excerpt']
    assert citation['source_sha256']==hashlib.sha256(raw.encode()).hexdigest()
    save('query-example.json',query);report['exact_cli_citation']=True
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    log=(OUT/'mcp-server.log').open('w')
    server=subprocess.Popen([str(x) for x in [*common,'serve','--store',store,'--model-dir',MODEL,'--port',str(port)]],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    try:
        deadline=time.monotonic()+60
        while True:
            assert server.poll() is None and time.monotonic()<deadline,'MCP startup failed'
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.1)
        async def checks():
            async with httpx2.AsyncClient(trust_env=False,timeout=30) as http:
                async with Client(streamable_http_client('http://127.0.0.1:'+str(port)+'/mcp',http_client=http),cache=None) as client:
                    listing=await client.list_tools();assert sorted(t.name for t in listing.tools)==['list_sources','read_citation','search_sources'] and all(t.output_schema for t in listing.tools)
                    async def call(name,params):
                        r=await client.call_tool(name,params);assert not r.is_error and isinstance(r.structured_content,dict);return r.structured_content
                    sources=await call('list_sources',{});assert len(sources['sources'])==2
                    found=await call('search_sources',{'query':'Authlib compatibility tests','source_id':target,'top_k':1});assert found['results'][0]['source_id']==target
                    replay=await call('read_citation',{'citation_id':found['results'][0]['citation_id']});assert replay['excerpt']==found['results'][0]['excerpt']
                    bad=await client.call_tool('read_citation',{'citation_id':'../invalid'});assert bad.is_error
                    return {'actual_TCP':True,'three_structured_tools':True,'two_real_documents':True,'source_filter':True,'exact_citation':True,'invalid_citation_error':True}
        report['MCP']=asyncio.run(checks())
    finally:
        server.terminate()
        try:server.wait(timeout=15)
        except subprocess.TimeoutExpired:server.kill();server.wait(timeout=5)
        log.close();assert server.poll() is not None
    final=counts();assert final['reserved_forwards']==final['completed_forwards'] and final['query_inputs']==2
    import torch
    assert torch.__version__=='2.6.0+cpu' and torch.version.cuda is None and not torch.cuda.is_initialized()
    report['CPU_only_build']=True;report['CUDA_initialized']=False;report['ready']=True
except BaseException as error:report['error']={'type':type(error).__name__,'message':str(error)[:1200]};traceback.print_exc()
finally:
    report['counts']=counts();report['ledger_sha256']=hashlib.sha256((budget/'events.jsonl').read_bytes()).hexdigest();report['wall_seconds']=round(time.monotonic()-started,3)
    save('report.json',report);print(json.dumps({k:report.get(k) for k in ['ready','error','counts','wall_seconds']}),flush=True)
raise SystemExit(0 if report['ready'] else 2)
