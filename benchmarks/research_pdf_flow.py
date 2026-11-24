"""Installed PDF→LlamaIndex/E5 CPU→exact page citation→real MCP flow, not a QA benchmark."""
from pathlib import Path
import asyncio,hashlib,importlib.metadata,io,json,os,socket,subprocess,sys,threading,time,traceback
from contextlib import redirect_stdout
from agentlab_research.research_library import ingest,search,citation,open_generation,load_sources,parser_for
from agentlab_research.research_embeddings import LocalE5Embedding
from agentlab_research.research_mcp import create_app
import agentlab_research

INPUT,MODEL,OUT,CLI=map(Path,sys.argv[1:]);OUT.mkdir(mode=0o700,exist_ok=False);STORE=OUT/'store'
CAPS={'reserved_forwards':400,'text_inputs':1400,'query_inputs':8}
counts={'reserved_forwards':0,'completed_forwards':0,'text_inputs':0,'query_inputs':0}
ledger=OUT/'cpu-embedding-events.jsonl';ledger.touch(exist_ok=False)
queries=['LightRAG dual level retrieval local global entity relations','MiniRAG heterogeneous graph indexing lightweight topology enhanced retrieval']
report={'ready':False,'scope':'Two whole versioned PDF papers; known-topic workflow checks, not retrieval accuracy/QA/answer-generation.','caps':CAPS,'GPU_used':False,'generation_calls':0,'queries_declared_before_index':queries}
started=time.monotonic()
def save(name,data):(OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def observe(phase,event):
 if phase=='reserved':
  key=event['kind']+'_inputs';assert counts['reserved_forwards']+1<=CAPS['reserved_forwards'] and counts[key]+event['inputs']<=CAPS[key]
  counts['reserved_forwards']+=1;counts[key]+=event['inputs']
 else:counts['completed_forwards']+=1
 with ledger.open('a') as f:f.write(json.dumps({'phase':phase,**event,'counts':dict(counts)},sort_keys=True)+'\n');f.flush();os.fsync(f.fileno())
try:
 import torch
 from pypdf import PdfReader
 assert str(Path(agentlab_research.__file__).resolve()).startswith(str(Path(sys.prefix).resolve())+'/')
 assert torch.__version__=='2.6.0+cpu' and not torch.cuda.is_initialized()
 report['versions']={n:importlib.metadata.version(n) for n in ['agentlab-research','llama-index-core','pypdf','torch','transformers','mcp']}
 save('declared-queries.json',queries)
 subprocess.run([str(CLI),'prepare-pdf','--manifest',str(INPUT/'intake.json'),'--output',str(OUT/'bundle')],check=True,stdout=(OUT/'prepare-cli.json').open('w'))
 manifest=OUT/'bundle/collection.json';sources=load_sources(manifest);report['page_sources']=len(sources)
 extraction=json.loads((OUT/'bundle/pdf-extraction.json').read_text());report['PDFs']=[{'url':d['url'],'sha256':d['sha256'],'bytes':d['bytes'],'pages':len(d['pages']),'pages_without_text':sum(p['status']=='no_extractable_text' for p in d['pages'])} for d in extraction['documents']]
 # Verify the stored extraction per physical page against the original PDF parser.
 for value in sources.values():
  pdf=value['metadata']['pdf'];original=OUT/'bundle/originals'/(pdf['sha256']+'.pdf')
  assert PdfReader(original).pages[pdf['page_number']-1].extract_text(extraction_mode='plain')==value['text']
 model=LocalE5Embedding(MODEL,observer=observe,batch_size=4)
 from llama_index.core import Document
 docs=[Document(id_=k,text=v['text'],metadata=v['metadata'],excluded_embed_metadata_keys=list(v['metadata']),excluded_llm_metadata_keys=list(v['metadata'])) for k,v in sources.items()]
 nodes=parser_for(model).get_nodes_from_documents(docs)
 report['planned_nodes']=len(nodes);report['max_passage_tokens']=max(len(model.tokens('passage: '+n.text))+2 for n in nodes)
 assert len(nodes)<=CAPS['text_inputs'] and report['max_passage_tokens']<=512
 save('preflight.json',report)
 report['ingest']=ingest(manifest,STORE,model);before=dict(counts);report['noop']=ingest(manifest,STORE,model);assert counts==before and not report['noop']['published']
 results=[]
 for query in queries:
  result=search(STORE,query,model,mode='hybrid',top_k=3);assert result['results'] and not result['generated_answer']
  for hit in result['results']:
   original=sources[hit['source_id']]['text'];assert original[hit['char_start']:hit['char_end']]==hit['excerpt']
   assert hit['pdf']==sources[hit['source_id']]['metadata']['pdf']
  results.append(result)
 save('query-results.json',results)
 first_source=next(k for k,v in sources.items() if v['metadata']['pdf']['sha256']==extraction['documents'][0]['sha256'])
 old=search(STORE,'LightRAG',model,mode='lexical',source_id=first_source,top_k=1)['results'][0]
 subprocess.run([str(CLI),'read','--store',str(STORE),'--citation-id',old['citation_id']],check=True,stdout=(OUT/'read-cli.json').open('w'))
 assert json.loads((OUT/'read-cli.json').read_text())['excerpt']==old['excerpt']
 import uvicorn,httpx2
 from mcp import Client
 from mcp.client.streamable_http import streamable_http_client
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 server=uvicorn.Server(uvicorn.Config(create_app(STORE,model),host='127.0.0.1',port=port,log_level='error',access_log=False));thread=threading.Thread(target=server.run,daemon=True);thread.start()
 try:
  deadline=time.monotonic()+20
  while not server.started:assert thread.is_alive() and time.monotonic()<deadline;time.sleep(.05)
  async def checks():
   async with httpx2.AsyncClient(trust_env=False,timeout=60) as http:
    async with Client(streamable_http_client('http://127.0.0.1:'+str(port)+'/mcp',http_client=http),cache=None) as client:
     names=sorted(t.name for t in (await client.list_tools()).tools);assert names==['list_sources','read_citation','search_sources']
     async def call(name,args):
      result=await client.call_tool(name,args);assert not result.is_error;return result.structured_content
     listed=await call('list_sources',{});assert len(listed['sources'])==len(sources) and all('pdf' in s for s in listed['sources'])
     found=await call('search_sources',{'query':queries[1],'top_k':3});assert found['results']
     hit=found['results'][0];read=await call('read_citation',{'citation_id':hit['citation_id']});assert read==citation(STORE,hit['citation_id']) and read['pdf']['page_number']>=1
     return {'real_loopback_TCP':True,'tool_names':names,'listed_page_sources':len(sources),'search_and_read_page_metadata_exact':True}
  report['MCP']=asyncio.run(checks())
 finally:
  server.should_exit=True;thread.join(timeout=15);assert not thread.is_alive()
 # Removing a whole paper keeps old page citations and copied original accessible.
 first_pdf=extraction['documents'][0]['sha256'];spec=json.loads(manifest.read_text());removed=[r['id'] for r in spec['sources'] if r['pdf']['sha256']==first_pdf];spec['sources']=[r for r in spec['sources'] if r['pdf']['sha256']!=first_pdf]
 reduced=OUT/'bundle/reduced.json';save('removed-source-ids.json',removed);reduced.write_text(json.dumps(spec));before=dict(counts);report['remove_paper']=ingest(reduced,STORE,model);assert counts==before and sorted(report['remove_paper']['removed'])==sorted(removed)
 historical=citation(STORE,old['citation_id']);assert not historical['is_current_generation'] and historical['excerpt']==old['excerpt'] and historical['pdf']==old['pdf'];save('historical-citation.json',historical)
 assert counts==model.counts and counts['reserved_forwards']==counts['completed_forwards'];assert not torch.cuda.is_initialized()
 report.update(ready=True,old_citation_exact_after_paper_removal=True,noop_and_removal_zero_embeddings=True,CUDA_initialized=False)
except BaseException as e:
 report['error']={'type':type(e).__name__,'message':str(e)[:1000]};traceback.print_exc()
finally:
 report.update(counts=counts,unknown_forwards=counts['reserved_forwards']-counts['completed_forwards'],CPU_ledger_sha256=hashlib.sha256(ledger.read_bytes()).hexdigest(),budget_status='CLOSED',wall_seconds=round(time.monotonic()-started,3));save('experiment-report.json',report);print(json.dumps(report),flush=True)
raise SystemExit(0 if report['ready'] else 2)
