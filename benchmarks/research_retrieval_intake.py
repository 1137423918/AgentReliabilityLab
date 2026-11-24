"""Offline first-party SciFact intake and tokenizer planning; no neural forwards.

Assets are verified against supplied frozen metadata. The model directory is
read-only and must contain the project's existing pinned E5 assets. The output
must be a new directory. PyArrow is unpacked privately from its verified wheel.
"""
from pathlib import Path
import argparse,collections,csv,hashlib,io,json,os,sys,tarfile,zipfile


def run(INPUT, ROOT, MODEL):
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assetmeta=json.loads((INPUT/'HF-official-assets.json').read_text());
    for x in assetmeta['files']:
     p=INPUT/x['repo'].replace('/','--')/x['file'];assert p.stat().st_size==x['bytes'] and sha(p)==x['sha256']
    wheelmeta=json.loads((INPUT/'pyarrow-intake.json').read_text())['wheel'];wheel=INPUT/wheelmeta['filename'];assert wheel.stat().st_size==wheelmeta['size'] and sha(wheel)==wheelmeta['digests']['sha256']
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=False)
    arrow=ROOT/'arrow';arrow.mkdir();total=0
    with zipfile.ZipFile(wheel) as z:
     for m in z.infolist():
      n=Path(m.filename);assert not n.is_absolute() and '..' not in n.parts;total+=m.file_size;assert total<256*1024**2;q=arrow/n
      if m.is_dir():q.mkdir(parents=True,exist_ok=True)
      else:q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(z.read(m));q.chmod((m.external_attr>>16)&0o777 or 0o644)
    sys.path.insert(0,str(arrow))
    import pyarrow.parquet as pq
    assert __import__('pyarrow').__version__=='22.0.0'
    corpus=pq.read_table(INPUT/'BeIR--scifact/corpus/corpus-00000-of-00001.parquet').to_pylist();allqueries=pq.read_table(INPUT/'BeIR--scifact/queries/queries-00000-of-00001.parquet').to_pylist()
    assert len(corpus)==5183 and len({x['_id'] for x in corpus})==5183
    rels=collections.defaultdict(dict)
    with (INPUT/'BeIR--scifact-qrels/test.tsv').open() as s:
     for x in csv.DictReader(s,delimiter='\t'):
      q,d,v=x['query-id'],x['corpus-id'],int(x['score']);assert v==1 and d not in rels[q];rels[q][d]=v
    assert len(rels)==300 and sum(map(len,rels.values()))==339
    queries={x['_id']:x['text'] for x in allqueries};assert len(queries)==len(allqueries) and set(rels)<=queries.keys()
    ids={x['_id'] for x in corpus};assert all(d in ids for ds in rels.values() for d in ds)
    a=json.loads((INPUT/'author-data-intake.json').read_text());assert sha(INPUT/'author-scifact-data.tar.gz')==a['sha256']
    author={}
    with tarfile.open(INPUT/'author-scifact-data.tar.gz') as t:
     for name in ['data/claims_dev.jsonl','data/corpus.jsonl']:
      m=t.getmember(name);assert m.isfile() and m.size<16*1024**2;author[name]=[json.loads(l) for l in t.extractfile(m).read().splitlines()]
    claims={str(x['id']):x for x in author['data/claims_dev.jsonl']};assert set(claims)==set(rels)
    source_corpus={str(x['doc_id']):x for x in author['data/corpus.jsonl']};assert set(source_corpus)==ids
    assert all(source_corpus[x['_id']]['title']==x['title'] for x in corpus)
    assert all(claims[q]['claim']==queries[q] for q in rels)
    label_check={q: sorted(rels[q])==sorted(set(map(str,claims[q]['cited_doc_ids']))) for q in rels}
    assert all(label_check.values()),'Inspect primary label semantics before any ranking'
    corpus_dir=ROOT/'corpus';(corpus_dir/'sources').mkdir(parents=True);ranking=ROOT/'ranking-input';ranking.mkdir();gold=ROOT/'judgments';gold.mkdir();sources=[];idmap={}
    url=next(x['url'] for x in assetmeta['files'] if x['file'].startswith('corpus/'))
    for x in corpus:
     key='scifact_'+x['_id'];raw=(x['title']+'\n'+x['text']).encode();(corpus_dir/'sources'/(key+'.txt')).write_bytes(raw);idmap[key]=x['_id'];sources.append({'id':key,'path':'sources/'+key+'.txt','title':x['title'],'url':url+'#document='+x['_id'],'kind':'beir_scifact_abstract','sha256':hashlib.sha256(raw).hexdigest()})
    (corpus_dir/'collection.json').write_text(json.dumps({'version':1,'sources':sources},ensure_ascii=False)+'\n')
    (ranking/'queries.jsonl').write_text(''.join(json.dumps({'id':q,'query':queries[q]},ensure_ascii=False)+'\n' for q in sorted(rels,key=int)))
    (ranking/'source-id-map.json').write_text(json.dumps(idmap,sort_keys=True)+'\n');(gold/'qrels.json').write_text(json.dumps(rels,sort_keys=True)+'\n');(gold/'query-strata.json').write_text(json.dumps({q:{'has_author_evidence_annotation':bool(claims[q]['evidence'])} for q in rels},sort_keys=True)+'\n')
    from agent_lab.research_intake import check_model
    from agent_lab.research_library import load_sources,parser_for
    from transformers import AutoTokenizer
    from llama_index.core import Document
    from llama_index.core.schema import MetadataMode
    assert (MODEL/'model-manifest.json').is_file();checked=check_model(MODEL);assert not checked['manifest_created']
    tokenizer=AutoTokenizer.from_pretrained(str(MODEL),local_files_only=True,trust_remote_code=False)
    class TokenOnly:
     def tokens(self,text):return tokenizer.encode(text,add_special_tokens=False)
    rows=load_sources(corpus_dir/'collection.json');docs=[Document(id_=k,text=rows[k]['text'],metadata=rows[k]['metadata'],excluded_embed_metadata_keys=list(rows[k]['metadata']),excluded_llm_metadata_keys=list(rows[k]['metadata'])) for k in sorted(rows)]
    nodes=parser_for(TokenOnly()).get_nodes_from_documents(docs);assert len({n.node_id for n in nodes})==len(nodes)
    node_manifest=[{'id':n.node_id,'source_id':n.ref_doc_id,'text_sha256':hashlib.sha256(n.get_content(metadata_mode=MetadataMode.EMBED).encode()).hexdigest(),'tokens':len(tokenizer.encode('passage: '+n.get_content(metadata_mode=MetadataMode.EMBED)))} for n in nodes]
    query_manifest=[{'id':q,'text_sha256':hashlib.sha256(queries[q].encode()).hexdigest(),'tokens':len(tokenizer.encode('query: '+queries[q]))} for q in sorted(rels,key=int)]
    assert max(x['tokens'] for x in node_manifest+query_manifest)<=512
    (ROOT/'planned-nodes.json').write_text(json.dumps(node_manifest,sort_keys=True)+'\n');(ROOT/'planned-queries.json').write_text(json.dumps(query_manifest,sort_keys=True)+'\n')
    result={'ready':True,'dataset':'Official BeIR/scifact and BeIR/scifact-qrels fixed HF revisions','corpus_documents':len(corpus),'test_queries':len(rels),'test_qrel_pairs':sum(map(len,rels.values())),'all_query_rows_in_official_file':len(allqueries),'title_plus_abstract_in_full':True,'node_count':len(nodes),'chunk_tokens':256,'chunk_overlap':32,'embedding_batch_size_planned':16,'planned_text_forward_upper_bound':(len(nodes)+15)//16,'planned_query_forward_upper_bound':300,'maximum_passage_tokens':max(x['tokens'] for x in node_manifest),'maximum_query_tokens':max(x['tokens'] for x in query_manifest),'cited_document_qrels_match_author_dev_all_300':True,'queries_with_evidence_annotations':sum(bool(claims[q]['evidence']) for q in rels),'queries_without_evidence_annotations':sum(not claims[q]['evidence'] for q in rels),'label_semantics':'BEIR relevant documents match author cited_doc_ids. Some claims have no author evidence annotations; retrieval relevance does not prove support, refutation or answer truth.','top_k_planned':[1,3,5,10],'candidate_node_window_planned':40,'BM25_k1':1.2,'BM25_b':.75,'RRF_constant':60,'methods':['lexical','semantic','hybrid'],'no_test_tuning':True,'model_generation_calls':0,'neural_forwards':0,'GPU_used':False,'model_manifest_sha256':sha(MODEL/'model-manifest.json'),'frozen_input_files':{str(p.relative_to(ROOT)):sha(p) for folder in [corpus_dir,ranking,gold] for p in sorted(folder.rglob('*')) if p.is_file()},'planned_nodes_sha256':sha(ROOT/'planned-nodes.json'),'planned_queries_sha256':sha(ROOT/'planned-queries.json')}
    (ROOT/'intake-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='frozen_input_files'}))


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--model-dir',type=Path,required=True)
    a=p.parse_args(argv);run(a.assets,a.output,a.model_dir)


if __name__=='__main__':main()
