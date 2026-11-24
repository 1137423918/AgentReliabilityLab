"""Add one versioned paper to a copied full-PDF index, with fresh CPU accounting.

Old generation/embeddings are reused read-only; no model generation or query.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys
import time
import traceback
import urllib.request
from urllib.parse import urlsplit

from agentlab_research.research_embeddings import LocalE5Embedding
from agentlab_research.research_library import ingest, load_sources, open_generation, parser_for
from agentlab_research.research_pdf import prepare_pdfs


def run(prior_store, model_dir, intake, output):
    output.mkdir(mode=0o700, exist_ok=False)
    caps = {'reserved_forwards': 100, 'text_inputs': 400, 'query_inputs': 0}
    counts = {'reserved_forwards': 0, 'completed_forwards': 0, 'text_inputs': 0, 'query_inputs': 0}
    ledger = output / 'cpu-embedding-events.jsonl'
    ledger.touch(exist_ok=False)
    started = time.monotonic()
    result = {'ready': False, 'scope': 'One new full-paper intake/incremental CPU index; no new QA score or RECEIPT benchmark reproduction.',
              'caps': caps, 'generation_requests': 0, 'GPU_used': False}

    def save():
        (output / 'ingest-result.json').write_text(json.dumps(result, indent=2) + '\n')

    def observe(phase, event):
        if phase == 'reserved':
            field = event['kind'] + '_inputs'
            assert counts['reserved_forwards'] + 1 <= caps['reserved_forwards']
            assert counts[field] + event['inputs'] <= caps[field]
            counts['reserved_forwards'] += 1
            counts[field] += event['inputs']
        else:
            counts['completed_forwards'] += 1
        with ledger.open('a') as stream:
            stream.write(json.dumps({'phase': phase, **event, 'counts': dict(counts)}, sort_keys=True) + '\n')
            stream.flush(); os.fsync(stream.fileno())

    try:
        import torch
        from llama_index.core import Document
        assert torch.__version__ == '2.6.0+cpu' and not torch.cuda.is_initialized()
        previous = '80bdd57f5e68d682a5b04c7e799c55f6b8979e75445a2ce744e39c88acce88ca'
        old_root, old = open_generation(prior_store, previous)
        before = {name: hashlib.sha256((old_root / name).read_bytes()).hexdigest() for name in old['files']}
        incoming = output / 'input'; incoming.mkdir()
        spec = json.loads(intake.read_text())
        assert [p['path'] for p in spec['pdfs']] == ['lightrag.pdf', 'minirag.pdf', 'receipt.pdf']
        for row, sha in zip(spec['pdfs'][:2], [
            'bd72eebf611df1366b251c16ce4eac7aac699e519783c586feb2c5c43899347a',
            '6a7e36747f1bf7345045c40287e5f584ee73fdcc3a30bcaff66990a8c5d1f561',
        ]):
            original = old_root / 'originals' / (sha + '.pdf')
            assert hashlib.sha256(original.read_bytes()).hexdigest() == sha
            shutil.copyfile(original, incoming / row['path'])
        url = spec['pdfs'][2]['url']
        assert url == 'https://arxiv.org/pdf/2611.01930v1'
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(urllib.request.Request(url, headers={'User-Agent': 'AgentReliabilityLab/ResearchReading'}), timeout=60) as response:
            assert response.status == 200 and urlsplit(response.geturl()).hostname in ['arxiv.org', 'export.arxiv.org']
            raw = response.read(32 * 1024**2 + 1)
            result['fetch'] = {'declared_url': url, 'final_url': response.geturl(), 'status': response.status,
                               'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        assert raw.startswith(b'%PDF') and len(raw) <= 32 * 1024**2
        (incoming / 'receipt.pdf').write_bytes(raw)
        (incoming / 'intake.json').write_text(json.dumps(spec, indent=2) + '\n')
        result['prepare'] = prepare_pdfs(incoming / 'intake.json', output / 'bundle')
        extraction = json.loads((output / 'bundle/pdf-extraction.json').read_text())
        result['papers'] = [{'title': d['title'], 'url': d['url'], 'sha256': d['sha256'],
                             'bytes': d['bytes'], 'physical_pages': len(d['pages'])} for d in extraction['documents']]
        assert len(result['papers']) == 3
        manifest = output / 'bundle/collection.json'
        sources = load_sources(manifest)
        assert set(old['identity']['sources']) <= set(sources)
        assert all(sources[key]['metadata'] == metadata for key, metadata in old['identity']['sources'].items())
        added = set(sources) - set(old['identity']['sources'])
        assert added and all(sources[key]['metadata']['pdf']['sha256'] == result['fetch']['sha256'] for key in added)
        first = next(sources[k]['text'] for k in added if sources[k]['metadata']['pdf']['page_number'] == 1)
        letters = ''.join(c for c in first.upper() if c.isalpha())
        assert 'RECEIPT' in letters and 'RETURNASSUMPTION' in letters
        store = output / 'store'
        (store / 'generations').mkdir(parents=True)
        shutil.copytree(old_root, store / 'generations' / previous)
        (store / 'CURRENT.json').write_text(json.dumps({'generation': previous}) + '\n')
        model = LocalE5Embedding(model_dir, observer=observe, batch_size=4)
        docs = [Document(id_=key, text=sources[key]['text'], metadata=sources[key]['metadata'],
                         excluded_embed_metadata_keys=list(sources[key]['metadata']),
                         excluded_llm_metadata_keys=list(sources[key]['metadata'])) for key in sorted(added)]
        nodes = parser_for(model).get_nodes_from_documents(docs)
        result.update(added_page_sources=len(added), unchanged_page_sources=len(old['identity']['sources']),
                      planned_added_nodes=len(nodes), max_added_passage_tokens=max(len(model.tokens('passage: ' + n.text)) + 2 for n in nodes))
        assert len(nodes) <= caps['text_inputs'] and result['max_added_passage_tokens'] <= 512
        save()
        result['ingest'] = ingest(manifest, store, model)
        assert sorted(result['ingest']['added']) == sorted(added)
        assert not result['ingest']['updated'] and not result['ingest']['removed']
        assert 0 < counts['text_inputs'] <= len(nodes)
        before_noop = dict(counts)
        result['noop'] = ingest(manifest, store, model)
        assert counts == before_noop and not result['noop']['published']
        _, current = open_generation(store)
        result.update(current_generation=json.loads((store / 'CURRENT.json').read_text())['generation'],
                      total_page_sources=len(current['identity']['sources']), total_nodes=current['node_count'],
                      old_generation_and_sources_unchanged=all(hashlib.sha256((old_root / name).read_bytes()).hexdigest() == expected for name, expected in before.items()),
                      unchanged_old_source_vectors_reused=True, noop_zero_embeddings=True)
        assert result['old_generation_and_sources_unchanged'] and counts == model.counts
        assert counts['completed_forwards'] == counts['reserved_forwards'] and not torch.cuda.is_initialized()
        result['ready'] = True
    except BaseException as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error)[:1000]}
        traceback.print_exc()
    finally:
        result.update(counts=counts, unknown_forwards=counts['reserved_forwards'] - counts['completed_forwards'],
                      ledger_sha256=hashlib.sha256(ledger.read_bytes()).hexdigest(), budget_status='CLOSED',
                      wall_seconds=round(time.monotonic() - started, 3))
        save(); print(json.dumps(result))
    return 0 if result['ready'] else 2


if __name__ == '__main__':
    raise SystemExit(run(*map(Path, sys.argv[1:])))
