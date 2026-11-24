"""Frozen CPU-only research retrieval + actual MCP/TCP lifecycle demonstration."""
from pathlib import Path
import asyncio, hashlib, importlib.metadata, json, os, socket, sys, threading, time, traceback
from agent_lab.research_library import ingest, search, citation, open_generation, load_sources, parser_for
from agent_lab.research_embeddings import LocalE5Embedding

MODEL, INPUT, OUT = map(Path, sys.argv[1:]); OUT.mkdir(mode=0o700, exist_ok=False)
STORE=OUT/'store'; ledger=OUT/'cpu-embedding-events.jsonl'
counts={'reserved_forwards':0,'completed_forwards':0,'text_inputs':0,'query_inputs':0}
CAPS={'reserved_forwards':768,'text_inputs':2048,'query_inputs':96}
started=time.monotonic()
def save(name,data): (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def observer(phase,event):
    if phase=='reserved':
        key=event['kind']+'_inputs'
        assert counts['reserved_forwards']+1<=CAPS['reserved_forwards'] and counts[key]+event['inputs']<=CAPS[key]
        counts['reserved_forwards']+=1;counts[key]+=event['inputs']
    else: counts['completed_forwards']+=1
    record={'sequence':counts['reserved_forwards'],'phase':phase,**event,'counts':dict(counts)}
    with ledger.open('a') as f: f.write(json.dumps(record,sort_keys=True)+'\n');f.flush();os.fsync(f.fileno())
report={'ready':False,'GPU_used':False,'generation_model_calls':0,'caps':CAPS,'scope':'24frozenoperator-authoredknown-source diagnostics,notheldoutQAoransweraccuracy'}
try:
    import torch
    model=LocalE5Embedding(MODEL,observer=observer,batch_size=4)
    assert not torch.cuda.is_initialized() and all(p.device.type=='cpu' for p in model._model.parameters())
    report['runtime']={k:importlib.metadata.version(k) for k in ['torch','transformers','numpy','llama-index-core','mcp']}
    report['model']=model.fingerprint
    from llama_index.core import Document
    plans={}
    for label in ['a','b']:
        sources=load_sources(INPUT/('collection-'+label+'.json'))
        docs=[Document(id_=k,text=v['text'],metadata=v['metadata'],excluded_embed_metadata_keys=list(v['metadata']),excluded_llm_metadata_keys=list(v['metadata'])) for k,v in sources.items()]
        nodes=parser_for(model).get_nodes_from_documents(docs)
        plans[label]={'sources':len(sources),'nodes':len(nodes),'max_passage_tokens':max(len(model.tokens('passage: '+n.text))+2 for n in nodes),'by_source':{k:sum(n.ref_doc_id==k for n in nodes) for k in sources}}
        assert plans[label]['max_passage_tokens']<=512
    report['plan']=plans;save('plan.json',report)
    report['initial']=ingest(INPUT/'collection-a.json',STORE,model)
    before=dict(counts);report['no_op']=ingest(INPUT/'collection-a.json',STORE,model)
    assert counts==before and not report['no_op']['published'];report['no_op_zero_embedding']=True
    old=search(STORE,'Agent Reliability Lab',model,source_id='lab_readme',mode='lexical',top_k=1)['results'][0]
    before=dict(counts);report['update']=ingest(INPUT/'collection-b.json',STORE,model)
    report['update_embedding_delta']={k:counts[k]-before[k] for k in counts}
    assert report['update']['updated']==['lab_readme'] and report['update']['added']==['dependency_workbench'] and report['update']['removed']==['tool_use_baseline']
    expected=plans['b']['by_source']['lab_readme']+plans['b']['by_source']['dependency_workbench']
    assert report['update_embedding_delta']['text_inputs']==expected
    replay=citation(STORE,old['citation_id']);assert replay['excerpt']==old['excerpt'] and not replay['is_current_generation']
    save('old-citation.json',replay);report['old_citation_exact']=True
    before=dict(counts);absent=search(STORE,'tool calling',model,source_id='tool_use_baseline')
    assert not absent['results'] and counts==before;report['deleted_source_zero_embedding']=True
    cases=json.loads((INPUT/'retrieval-cases.json').read_text());rows=[]
    for case in cases['cases']:
        row={'id':case['id'],'query':case['query'],'relevant_sources':case['relevant_sources'],'modes':{}}
        for mode in ['lexical','semantic','hybrid']:
            found=search(STORE,case['query'],model,mode=mode,top_k=3)
            for result in found['results']:
                raw=(open_generation(STORE)[0]/'sources'/(result['source_id']+'.txt')).read_bytes().decode()
                assert raw[result['char_start']:result['char_end']]==result['excerpt']
            ids=[r['source_id'] for r in found['results']]; rank=next((i+1 for i,k in enumerate(ids) if k in case['relevant_sources']),None)
            row['modes'][mode]={'source_ids':ids,'hit_at_3':bool(rank),'reciprocal_rank_at_3':1/rank if rank else 0,'citation_ids':[r['citation_id'] for r in found['results']]}
        rows.append(row);save('retrieval-rows.json',rows)
    report['retrieval']={mode:{'n':len(rows),'hits_at_3':sum(r['modes'][mode]['hit_at_3'] for r in rows),'MRR_at_3':sum(r['modes'][mode]['reciprocal_rank_at_3'] for r in rows)/len(rows)} for mode in ['lexical','semantic','hybrid']}
    from agent_lab.research_mcp import create_app
    import uvicorn
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    import httpx2
    with socket.socket() as sock: sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(create_app(STORE,model),host='127.0.0.1',port=port,log_level='error',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        deadline=time.monotonic()+20
        while not server.started:
            assert thread.is_alive() and time.monotonic()<deadline;time.sleep(.05)
        async def client_checks():
            async with httpx2.AsyncClient(trust_env=False,timeout=30,follow_redirects=False) as http:
                async with Client(streamable_http_client('http://127.0.0.1:'+str(port)+'/mcp',http_client=http),cache=None) as client:
                    listing=await client.list_tools();names=sorted(t.name for t in listing.tools);assert names==['list_sources','read_citation','search_sources']
                    async def call(name,params):
                        result=await client.call_tool(name,params);assert not result.is_error;return result.structured_content
                    sources=await call('list_sources',{});assert len(sources['sources'])==20
                    found=await call('search_sources',{'query':'LGABlock lightweight hybrid encoder','source_id':'ls_detr_readme','top_k':1})
                    assert found['results'][0]['source_id']=='ls_detr_readme' and not found['generated_answer']
                    read=await call('read_citation',{'citation_id':found['results'][0]['citation_id']});assert read['excerpt']==found['results'][0]['excerpt']
                    historic=await call('read_citation',{'citation_id':old['citation_id']});assert not historic['is_current_generation']
                    bad=await client.call_tool('read_citation',{'citation_id':'../invalid'});assert bad.is_error
                    before=dict(counts);missing=await call('search_sources',{'query':'anything','source_id':'tool_use_baseline'});assert not missing['results'] and before==counts
                    return {'transport':'real TCP streamable HTTP loopback','tools':names,'active_sources':20,'source_filter':True,'citation_exact':True,'historic_citation':True,'invalid_citation_tool_error':True,'deleted_source_zero_embedding':True}
        report['MCP']=asyncio.run(client_checks())
    finally:
        server.should_exit=True;thread.join(timeout=15);assert not thread.is_alive()
    assert counts['reserved_forwards']==counts['completed_forwards'] and counts==model.counts
    assert not torch.cuda.is_initialized();report['CUDA_initialized']=False;report['ready']=True
except BaseException as error:
    report['error']={'type':type(error).__name__,'message':str(error)[:1000]};traceback.print_exc()
finally:
    report['CPU_embedding_counts']=counts;report['wall_seconds']=round(time.monotonic()-started,3)
    if ledger.exists():report['embedding_ledger_sha256']=hashlib.sha256(ledger.read_bytes()).hexdigest()
    save('experiment-report.json',report);print(json.dumps({k:report.get(k) for k in ['ready','error','CPU_embedding_counts','retrieval','wall_seconds']}),flush=True)
raise SystemExit(0 if report['ready'] else 2)
