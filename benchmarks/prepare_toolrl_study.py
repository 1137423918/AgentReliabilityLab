"""Build a text-grouped clean development split and exact loss-token schedules.

Run only against verified private paired Parquets and a pinned local tokenizer.
This is deterministic data preparation, not semantic isolation or model training.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import hashlib,json,math,re,time,unicodedata
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
from transformers import AutoTokenizer


def packed(x):
    return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()


def sha(x):
    return hashlib.sha256(x).hexdigest()


def save(path,x):
    path.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')


def lines(path,rows):
    path.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))


def normal(s):
    return ' '.join(unicodedata.normalize('NFKC',s).casefold().split())


def utterances(row):
    result=re.findall(r'<user>\s*(.*?)\s*</user>',row['extra_info']['input'],re.S)
    if not result:
        raise ValueError('Training row lacks user tags; do not invent a grouping key')
    result=tuple(normal(x) for x in result)
    if not any(result):raise ValueError('Empty normalized user sequence')
    return result


class Union:
    def __init__(self):self.parent={}
    def root(self,x):
        self.parent.setdefault(x,x)
        while x!=self.parent[x]:
            self.parent[x]=self.parent[self.parent[x]];x=self.parent[x]
        return x
    def join(self,a,b):
        a,b=self.root(a),self.root(b)
        if a!=b:self.parent[max(a,b)]=min(a,b)


def distribution(values):
    s=sorted(values)
    return {'n':len(s),'total':sum(s),'min':s[0] if s else None,'max':s[-1] if s else None,
            **{'p'+str(p):s[math.ceil(p/100*len(s))-1] if s else None for p in [50,90,95,99]}}


def make_schedule(variant,selected,tokenized,component,steps=32,budget=2048):
    # Shared ID order; differing target lengths can change examples per update.
    order=sorted(selected,key=lambda k:sha(('agentlab-stage50-order-v1|'+k).encode()))
    cursor=offset=cycle=0;plan=[]
    for step in range(steps):
        left=budget;segments=[]
        while left:
            k=order[cursor];r=tokenized[variant,k];n=r['target_tokens'];take=min(left,n-offset)
            assert take>0 and r['prompt_tokens']>0
            segments.append({'id_sha256':sha(k.encode()),'component_sha256':component[k],
                'cycle':cycle,'target_start':offset,'target_end':offset+take,
                'label_start':r['prompt_tokens']+offset,'label_end':r['prompt_tokens']+offset+take,
                'sequence_tokens':len(r['input_ids']),'supervised_tokens':take})
            left-=take;offset+=take
            if offset==n:
                offset=0;cursor+=1
                if cursor==len(order):cursor=0;cycle+=1
        assert sum(s['supervised_tokens'] for s in segments)==budget
        plan.append({'optimizer_step':step,'loss_tokens':budget,'segments':segments})
    return {'variant':variant,'updates':steps,'loss_tokens_per_update':budget,
            'loss_tokens_total':steps*budget,'sequence_forwards':sum(len(s['segments']) for s in plan),
            'input_token_exposures':sum(s['sequence_tokens'] for p in plan for s in p['segments']),
            'unique_IDs_exposed':len({s['id_sha256'] for p in plan for s in p['segments']}),
            'data_cycles_completed':cycle,'steps':plan}


def prepare(args):
    started=time.monotonic();args.output.mkdir(parents=True,exist_ok=False)
    tables={n:pq.ParquetFile(args.source/(n+'-paired.parquet')).read(use_threads=False)
            for n in ['train','mixed_train','test']}
    rows={n:t.to_pylist() for n,t in tables.items()}
    assert [len(rows[n]) for n in rows]==[3905,3905,79]
    keys={n:[r['extra_info']['original_id'] for r in data] for n,data in rows.items()}
    assert keys['train']==keys['mixed_train'] and len(set(keys['train']))==3905
    assert not set(keys['train'])&set(keys['test'])
    union=Union();sequences=defaultdict(list);node_labels=defaultdict(set);public_nodes=[]
    for variant,data in rows.items():
        for i,row in enumerate(data):
            k=row['extra_info']['original_id'];union.root(k);sequences[utterances(row)].append(k)
            node_labels[k].add('released_validation' if variant=='test' else 'candidate')
    benchmark=[json.loads(x) for x in args.benchmark.read_text().splitlines() if x.strip()]
    assert len(benchmark)==199
    for i,r in enumerate(benchmark):
        k='benchmark:'+str(i);assert k not in union.parent;union.root(k);node_labels[k].add('official_benchmark')
        conv=json.loads(r['conversation']) if isinstance(r['conversation'],str) else r['conversation']
        if not isinstance(conv,list) or not all(isinstance(m,dict) and isinstance(m.get('role'),str) for m in conv):raise ValueError('Malformed benchmark conversation')
        seq=tuple(normal(m.get('content') or '') for m in conv if m['role']=='user')
        assert seq;sequences[seq].append(k)
    for members in sequences.values():
        for k in members[1:]:union.join(members[0],k)
    seqs=sorted(sequences);assert len(seqs)<=10000
    grams=[]
    for seq in seqs:
        words=re.findall(r'\w+',' '.join(seq))
        grams.append({tuple(words[j:j+3]) for j in range(len(words)-2)} if len(words)>=8 else set())
    postings=defaultdict(list);near=[];candidate_pairs=0
    for i,g in enumerate(grams):
        overlaps=Counter(j for term in g for j in postings[term])
        candidate_pairs+=len(overlaps)
        if candidate_pairs>10_000_000:raise ValueError('Lexical pair budget exceeded; do not silently skip candidates')
        for j,intersection in overlaps.items():
            # Exact rational threshold 4/5, not rounded floating comparison.
            total=len(g)+len(grams[j])-intersection
            if 5*intersection>=4*total:
                union.join(sequences[seqs[i]][0],sequences[seqs[j]][0])
                near.append({'left_sequence_sha256':sha(packed(seqs[j])),
                             'right_sequence_sha256':sha(packed(seqs[i])),
                             'intersection_ngrams':intersection,'union_ngrams':total})
        for term in g:postings[term].append(i)
    comps=defaultdict(list)
    for k in union.parent:comps[union.root(k)].append(k)
    component={k:sha(packed(sorted(sha(x.encode()) for x in members))) for members in comps.values() for k in members}
    labels=defaultdict(set)
    for k,v in node_labels.items():labels[component[k]].update(v)
    quarantine={c for c,v in labels.items() if v&{'released_validation','official_benchmark'}}
    print(json.dumps({'phase':'grouped','nodes':len(union.parent),'components':len(comps),'sequence_keys':len(seqs),'near_edges':len(near),'candidate_pairs':candidate_pairs}),flush=True)
    tokenizer=AutoTokenizer.from_pretrained(str(args.model),local_files_only=True,trust_remote_code=False)
    tokenized={};metrics=[];counts=Counter()
    for variant,data in rows.items():
        for i,row in enumerate(data):
            k=row['extra_info']['original_id'];prompt=row['prompt'];answer=row['reward_model']['ground_truth']
            prompt_ids=tokenizer.apply_chat_template(prompt,tokenize=True,add_generation_prompt=True)
            full=tokenizer.apply_chat_template(prompt+[{'role':'assistant','content':answer}],tokenize=True,add_generation_prompt=False)
            if full[:len(prompt_ids)]!=prompt_ids:raise ValueError('Chat-template assistant prefix mismatch')
            p=len(prompt_ids);target=len(full)-p
            if p<1 or target<1:raise ValueError('Empty prompt or supervised target')
            tokenized[variant,k]={'id_sha256':sha(k.encode()),'input_ids':full,'labels':[-100]*p+full[p:],
                                  'prompt_tokens':p,'target_tokens':target,'component_sha256':component[k]}
            metrics.append({'variant':variant,'input_position':i,'id_sha256':sha(k.encode()),'full_row_sha256':sha(packed(row)),
                'component_sha256':component[k],'normalized_user_sequence_sha256':sha(packed(utterances(row))),
                'prompt_tokens':p,'target_tokens':target,'sequence_tokens':len(full),
                'perturbation_type':row['extra_info']['perturbation']['type'],
                'prompt_over_2048':p>2048,'sequence_over_4096':len(full)>4096,
                'sequence_over_model_context':len(full)>32768,'prompt_token_ids_sha256':sha(packed(prompt_ids)),
                'full_token_ids_sha256':sha(packed(full)),'label_mask_sha256':sha(packed(tokenized[variant,k]['labels']))})
            counts[variant]+=1
            if sum(counts.values())%250==0:print(json.dumps({'phase':'tokenized','rows':sum(counts.values()),'declared':7889}),flush=True)
    admitted={k for k in keys['train'] if all(len(tokenized[v,k]['input_ids'])<=4096 for v in ['train','mixed_train'])}
    clean_ids={k for k,row in zip(keys['mixed_train'],rows['mixed_train']) if row['extra_info']['perturbation']['type']=='none'}
    eligible_clean_components={component[k] for k in admitted&clean_ids if component[k] not in quarantine}
    ordered=sorted(eligible_clean_components,key=lambda c:sha(('agentlab-stage50-dev-v1|'+c).encode()))
    ndev=max(1,len(ordered)//10) if ordered else 0;dev_components=set(ordered[:ndev])
    train_ids=[k for k in keys['train'] if k in admitted and component[k] not in quarantine|dev_components]
    dev_indices=[];seen=set()
    for i,k in sorted(enumerate(keys['mixed_train']),key=lambda x:sha(x[1].encode())):
        if k in admitted&clean_ids and component[k] in dev_components:
            row=rows['mixed_train'][i];fingerprint=sha(packed([row['prompt'],row['reward_model']['ground_truth']]))
            if fingerprint not in seen:dev_indices.append(i);seen.add(fingerprint)
    if not train_ids or not dev_indices:raise ValueError('No usable grouped training/clean development split')
    assert not {component[k] for k in train_ids}&(quarantine|dev_components)
    assert all(rows['mixed_train'][i]['extra_info']['perturbation']['type']=='none' for i in dev_indices)
    selected={'train':[keys['train'].index(k) for k in train_ids],
              'mixed_train':[keys['mixed_train'].index(k) for k in train_ids],
              'test':list(range(79)),'dev_clean':dev_indices}
    artifacts=[]
    for name,indices in selected.items():
        variant='mixed_train' if name=='dev_clean' else name
        table=tables[variant].take(pa.array(indices,type=pa.int64()));path=args.output/(name+'.parquet')
        pq.write_table(table,path,compression='zstd')
        assert pq.ParquetFile(path).read(use_threads=False).schema==table.schema
        assert packed(pq.ParquetFile(path).read(use_threads=False).to_pylist())==packed([rows[variant][i] for i in indices])
        artifacts.append({'file':path.name,'bytes':path.stat().st_size,'sha256':sha(path.read_bytes()),'rows':len(indices),'row_content_and_schema_roundtrip':True})
        private=[tokenized[variant,keys[variant][i]] for i in indices]
        path=args.output/(name+'-tokenized.jsonl');lines(path,private)
        # Independently reconstruct actual causal labels; no model needed.
        reloaded=[json.loads(x) for x in path.read_text().splitlines()]
        assert reloaded==private
        for r in reloaded:
            assert len(r['input_ids'])==len(r['labels'])
            assert all(x==-100 for x in r['labels'][:r['prompt_tokens']])
            assert r['labels'][r['prompt_tokens']:]==r['input_ids'][r['prompt_tokens']:]
            assert sum(x!=-100 for x in r['labels'][1:])==r['target_tokens']
        artifacts.append({'file':path.name,'bytes':path.stat().st_size,'sha256':sha(path.read_bytes()),'rows':len(indices),'labels_roundtrip_and_causal_shift_checked':True})
    train_set=set(train_ids)
    for r in metrics:
        k=keys[r['variant']][r['input_position']];c=component[k]
        r['split']='released_validation' if r['variant']=='test' else 'quarantine' if c in quarantine else 'clean_dev_family' if c in dev_components else 'overlength_pair' if k not in admitted else 'training'
    lines(args.output/'row-metadata.jsonl',metrics);lines(args.output/'near-edges.jsonl',near)
    schedules={v:make_schedule(v,train_ids,tokenized,component) for v in ['train','mixed_train']}
    # Verify every schedule segment against actual stored tokenized training rows.
    for variant,schedule in schedules.items():
        index={r['id_sha256']:r for r in (json.loads(x) for x in (args.output/(variant+'-tokenized.jsonl')).read_text().splitlines())}
        checked=0
        for step in schedule['steps']:
            actual=0
            for segment in step['segments']:
                r=index[segment['id_sha256']];a,b=segment['label_start'],segment['label_end'];assert a>=r['prompt_tokens'] and b<=len(r['labels'])
                labels=[-100]*a+r['labels'][a:b]+[-100]*(len(r['labels'])-b)
                actual+=sum(x!=-100 for x in labels[1:]);assert actual<=2048
                assert b-a==segment['supervised_tokens'];checked+=1
            assert actual==2048
        schedule['actual_private_label_spans_checked']=checked
        save(args.output/(variant+'-schedule.json'),schedule)
    summary={v:{field:distribution([r[field] for r in metrics if r['variant']==v]) for field in ['prompt_tokens','target_tokens','sequence_tokens']} for v in rows}
    report={'source_sha256':sha(Path(__file__).read_bytes()),'input_sha256':{n:sha((args.source/(n+'-paired.parquet')).read_bytes()) for n in rows},
        'benchmark_sha256':sha(args.benchmark.read_bytes()),'model_inference':False,'training_run':False,'tokenized_rows':len(metrics),
        'text_grouping':{'components':len(comps),'sequence_keys':len(seqs),'word_trigram_Jaccard_threshold':'4/5','candidate_pairs_checked':candidate_pairs,'near_edges':len(near),
            'quarantined_components':len(quarantine),'candidate_IDs_in_quarantine':sum(component[k] in quarantine for k in keys['train']),
            'eligible_clean_components':len(ordered),'dev_components':ndev,'train_components':len({component[k] for k in train_ids}),
            'train_vs_dev_val_benchmark_component_intersection':0,'semantic_isolation_proven':False},
        'selected_training_pairs':len(train_ids),'clean_development_rows':len(dev_indices),'released_validation_rows':79,
        'overlength_pairs':3905-len(admitted),'token_distributions':summary,
        'training_variant_tokens':{v:{'prompt_tokens':sum(tokenized[v,k]['prompt_tokens'] for k in train_ids),'target_tokens':sum(tokenized[v,k]['target_tokens'] for k in train_ids),'sequence_tokens':sum(len(tokenized[v,k]['input_ids']) for k in train_ids)} for v in schedules},
        'planned_exposure':{v:{k:x for k,x in s.items() if k!='steps'} for v,s in schedules.items()},'private_artifacts':artifacts,
        'policy':'Paired IDs and exact normalized user sequences form components; all lexical word-trigram Jaccard>=0.8 links are unioned. Components touching released validation or official clean user inputs quarantined. Lowest seeded SHA 10% eligible clean components held out. Training admits both variants <=4096 with no truncation. Dev deduplicates exact prompt+gold. Original files unchanged.',
        'limits':['Grouping is text-based; paraphrases below threshold, tool-family and pretraining overlap are not ruled out.',
                  'Development comes from released training data, not an independently collected external distribution.',
                  '32x2048 assistant-label schedules are data plans, not executed optimizer updates or a model checkpoint.',
                  'Exact supervised-token/update budgets do not equalize sequence forwards, prompt exposures, FLOPs or data coverage.',
                  'Labels include assistant content and template ending. Segment loss must be summed then divided by2048 with no extra accumulation averaging.',
                  'Original validation79 remains complete even when its sequences exceed4096; future trainer evaluation admission is separate.',
                  'This prepares an SFT research pilot; it is not the original GRPO/ToolRL-DR training recipe.'],
        'wall_seconds':round(time.monotonic()-started,3)}
    save(args.output/'report.json',report);print(json.dumps({'completed':True,'training_pairs':len(train_ids),'dev_rows':len(dev_indices),'quarantined_IDs':report['text_grouping']['candidate_IDs_in_quarantine'],'training_run':False}),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--benchmark',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();prepare(a)
