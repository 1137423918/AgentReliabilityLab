"""Offline binary-relevance retrieval scoring and independent TREC verification.

Consumes completed batch rankings, never a model or index. Every judged query
must occur exactly once for each method. Relevance is document retrieval, not
claim veracity, entailment, or generated-answer accuracy.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import subprocess

CUTS=(1,3,5,10)
METHODS=('lexical','semantic','hybrid')


def query_metrics(relevant, ranking, cuts=CUTS):
    relevant=set(relevant)
    if not relevant:raise ValueError('Each scored query needs a positive judgment')
    if len(set(ranking))!=len(ranking):raise ValueError('Repeated ranked document')
    result={}
    for k in cuts:
        if type(k) is not int or k<1:raise ValueError('Invalid cutoff')
        hits=[i for i,doc in enumerate(ranking[:k],1) if doc in relevant]
        dcg=sum(1/math.log2(i+1) for i in hits)
        ideal=sum(1/math.log2(i+1) for i in range(1,min(k,len(relevant))+1))
        result.update({f'ndcg@{k}':dcg/ideal,f'recall@{k}':len(hits)/len(relevant),
                       f'precision@{k}':len(hits)/k,f'hit@{k}':float(bool(hits)),
                       f'mrr@{k}':1/hits[0] if hits else 0.0})
    return result


def evaluate(qrels, rankings, cuts=CUTS):
    if not qrels:raise ValueError('No judgments')
    positives={}
    for q,docs in qrels.items():
        if any(type(v) is not int or v not in [0,1] for v in docs.values()):raise ValueError('Only binary judgments supported')
        positives[q]={d for d,v in docs.items() if v==1}
        if not positives[q]:raise ValueError('Each scored query needs a positive judgment')
    per_query={};aggregate={}
    for method,queries in rankings.items():
        if set(queries)!=set(qrels):raise ValueError('Ranking query coverage differs from judgments')
        per_query[method]={q:query_metrics(positives[q],queries[q],cuts) for q in sorted(qrels)}
        names=next(iter(per_query[method].values())).keys()
        aggregate[method]={name:sum(rows[name] for rows in per_query[method].values())/len(qrels) for name in names}
    if not rankings:raise ValueError('No rankings')
    return {'queries':len(qrels),'qrel_positive_pairs':sum(map(len,positives.values())),
            'cuts':list(cuts),'aggregate':aggregate,'per_query':per_query,
            'averaging':'macro over all judged queries; related claims are not assumed independent',
            'scope':'Cited-document retrieval relevance, not evidence entailment or answer correctness.'}


def read_batch(path,id_map,qrels,query_hashes=None):
    rankings={method:{} for method in METHODS};generation=None
    with Path(path).open() as stream:
        for line in stream:
            row=json.loads(line);q=row['id']
            if q not in qrels or q in rankings['lexical']:raise ValueError('Unknown or repeated query ID')
            if query_hashes is not None and row.get('query_sha256')!=query_hashes.get(q):raise ValueError('Query ID and text fingerprint differ')
            if generation is None:generation=row['generation']
            if generation!=row['generation'] or set(row['modes'])!=set(METHODS):raise ValueError('Mixed generations or methods')
            for method,response in row['modes'].items():
                if response.get('generated_answer') is not False or response.get('generation')!=generation:
                    raise ValueError('Expected retrieval-only responses from the same generation')
                docs=[]
                for item in response['results']:
                    if item['source_id'] not in id_map:raise ValueError('Unknown source ID')
                    if item['generation']!=generation or not item['citation_id'].startswith(generation+':'):
                        raise ValueError('Citation differs from retrieval generation')
                    docs.append(id_map[item['source_id']])
                if len(set(docs))!=len(docs):raise ValueError('Repeated ranked document')
                rankings[method][q]=docs
    if any(set(rows)!=set(qrels) for rows in rankings.values()):raise ValueError('Incomplete batch rankings')
    return rankings,generation


def write_trec(directory,qrels,rankings,cuts=CUTS):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    (directory/'qrels.txt').write_text(''.join(f'{q} 0 {d} {v}\n' for q,docs in sorted(qrels.items()) for d,v in sorted(docs.items())))
    for method,queries in rankings.items():
        for k in cuts:
            # Encode the existing ordinal order as unique scores. TREC's tie
            # handling must not reorder equal RRF scores or original node ties.
            (directory/f'{method}.top{k}.run').write_text(''.join(f'{q} Q0 {d} {rank} {k-rank+1} {method}\n' for q,docs in sorted(queries.items()) for rank,d in enumerate(docs[:k],1)))


def score(batch,id_map_path,qrels_path,output,queries_path=None):
    batch=Path(batch);output=Path(output)
    if output.exists():raise FileExistsError('Use a new score directory')
    id_map=json.loads(Path(id_map_path).read_text());qrels=json.loads(Path(qrels_path).read_text())
    query_hashes=None
    if queries_path is not None:
        requests=[json.loads(line) for line in Path(queries_path).read_text().splitlines()]
        query_hashes={row['id']:hashlib.sha256(row['query'].encode()).hexdigest() for row in requests}
        if len(query_hashes)!=len(requests) or set(query_hashes)!=set(qrels):raise ValueError('Query input coverage differs from judgments')
    rankings,generation=read_batch(batch,id_map,qrels,query_hashes);result=evaluate(qrels,rankings)
    result['query_input_sha256']=hashlib.sha256(Path(queries_path).read_bytes()).hexdigest() if queries_path else None
    output.mkdir(parents=True);write_trec(output/'trec',qrels,rankings)
    result.update(generation=generation,batch_sha256=hashlib.sha256(batch.read_bytes()).hexdigest(),
                  id_map_sha256=hashlib.sha256(Path(id_map_path).read_bytes()).hexdigest(),qrels_sha256=hashlib.sha256(Path(qrels_path).read_bytes()).hexdigest(),
                  ranked_documents={m:sum(map(len,x.values())) for m,x in rankings.items()},
                  returned_fewer_than_10={m:sum(len(r)<10 for r in x.values()) for m,x in rankings.items()},
                  new_model_calls=0,GPU_used=False)
    (output/'metrics.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# Full-corpus research retrieval evaluation','',f"Queries: {result['queries']}; positive document pairs: {result['qrel_positive_pairs']}.",'',
           '| Method | nDCG@10 | Recall@10 | MRR@10 | Hit@10 |','| --- | --- | --- | --- | --- |']
    for method,values in result['aggregate'].items():lines.append('| '+method+' | '+' | '.join(f'{values[m]:.6f}' for m in ['ndcg@10','recall@10','mrr@10','hit@10'])+' |')
    lines += ['',result['scope'],result['averaging']+'.','No claim of model-training independence, answer quality, or statistical significance.']
    (output/'metrics.md').write_text('\n'.join(lines)+'\n');return result


def verify_trec(score_directory,binary):
    root=Path(score_directory);result=json.loads((root/'metrics.json').read_text());observed={};checked=0;max_delta=0.0
    expected_keys={'ndcg_cut':'ndcg','recall':'recall','P':'precision','success':'hit'}
    for method,queries in result['per_query'].items():
        for k in result['cuts']:
            command=[str(Path(binary).resolve()),'-q','-c','-m',f'ndcg_cut.{k}','-m',f'recall.{k}','-m',f'P.{k}','-m',f'success.{k}','-m','recip_rank',str(root/'trec/qrels.txt'),str(root/'trec'/f'{method}.top{k}.run')]
            run=subprocess.run(command,capture_output=True,text=True,check=True,timeout=30)
            log=root/f'trec-{method}-top{k}.txt';log.write_text(run.stdout);rows={}
            for line in run.stdout.splitlines():
                parts=line.split()
                if len(parts)!=3:continue
                metric,q,value=parts;rows[(metric,q)]=float(value)
            for q,values in [*queries.items(),('all',result['aggregate'][method])]:
                wanted={f'{name}_{k}':f'{own}@{k}' for name,own in expected_keys.items()};wanted['recip_rank']=f'mrr@{k}'
                for reference,own in wanted.items():
                    if (reference,q) not in rows:raise ValueError('Missing reference metric: '+reference+'/'+q)
                    delta=abs(rows[(reference,q)]-values[own]);max_delta=max(max_delta,delta);checked+=1
                    if delta>0.000051:raise ValueError('TREC result differs: '+reference+'/'+q)
            observed[f'{method}@{k}']={'stdout_sha256':hashlib.sha256(run.stdout.encode()).hexdigest(),'reference_output_rows':len(rows)}
    report={'verified':True,'reference_binary_sha256':hashlib.sha256(Path(binary).read_bytes()).hexdigest(),'values_compared':checked,
            'maximum_absolute_difference':max_delta,'tolerance':0.000051,'reason_for_tolerance':'Unmodified trec_eval prints four decimal places.',
            'runs':observed,'ordinal_run_scores_preserve_application_order':True,'new_model_calls':0,'GPU_used':False}
    (root/'trec-verification.json').write_text(json.dumps(report,indent=2)+'\n');return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('score');a.add_argument('--batch',type=Path,required=True);a.add_argument('--id-map',type=Path,required=True);a.add_argument('--qrels',type=Path,required=True);a.add_argument('--queries',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=s.add_parser('verify');a.add_argument('--scores',type=Path,required=True);a.add_argument('--trec-eval',type=Path,required=True)
    args=p.parse_args(argv)
    if args.command=='score':result=score(args.batch,args.id_map,args.qrels,args.output,args.queries);print(json.dumps({k:v for k,v in result.items() if k!='per_query'}))
    else:print(json.dumps(verify_trec(args.scores,args.trec_eval)))


if __name__=='__main__':main()
