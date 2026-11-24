"""Versioned LlamaIndex research retrieval, incremental updates and exact citations.

Returns candidate source passages, not generated answers or confidence claims.
All model assets are local; source ingestion is explicit and read-only.
"""
from __future__ import annotations
import argparse
from collections import Counter
import fcntl
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlsplit
from .storage import admit_state_directory


def packed(x): return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
def digest(x): return hashlib.sha256(packed(x)).hexdigest()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(path, value):
    temporary = path.with_name(path.name+'.tmp')
    with temporary.open('wb') as stream: stream.write(packed(value)+b'\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)


def checked_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', value): raise ValueError('Invalid source ID')
    return value


def load_sources(manifest):
    manifest = Path(manifest); spec = json.loads(manifest.read_text()); rows = {}
    if spec.get('version') != 1 or not 1 <= len(spec['sources']) <= 256: raise ValueError('Expected1–256explicit sources')
    total = 0
    for item in spec['sources']:
        key = checked_id(item['id'])
        if key in rows: raise ValueError('Repeated source ID')
        url = urlsplit(item['url'])
        if url.scheme != 'https' or not url.netloc: raise ValueError('Source URL must be HTTPS')
        path = manifest.parent/item['path']
        if path.is_symlink(): raise ValueError('Source symlinks are not accepted')
        with path.open('rb') as stream: raw = stream.read(524289)
        if len(raw) > 524288 or hashlib.sha256(raw).hexdigest() != item['sha256']: raise ValueError('Source bytes differ from manifest')
        text = raw.decode('utf-8'); total += len(raw)
        if not text.strip() or total > 16*1024**2: raise ValueError('Empty source or collection too large')
        metadata = {k: item[k] for k in ['id', 'title', 'url', 'kind', 'sha256']}
        rows[key] = {'metadata': metadata, 'raw': raw, 'text': text, 'fingerprint': digest(metadata)}
    return rows


def open_generation(store, generation=None):
    store = Path(store)
    if generation is None: generation = json.loads((store/'CURRENT.json').read_text())['generation']
    if not re.fullmatch('[a-f0-9]{64}', generation): raise ValueError('Invalid generation ID')
    root = store/'generations'/generation
    if root.is_symlink(): raise ValueError('Generation cannot be a symlink')
    meta = json.loads((root/'generation.json').read_text())
    if digest(meta['identity']) != generation: raise ValueError('Generation identity changed')
    for name, expected in meta['files'].items():
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or (root/p).is_symlink() or sha(root/p) != expected: raise ValueError('Stored index/source fingerprint changed')
    for key, source in meta['identity']['sources'].items():
        if sha(root/'sources'/(key+'.txt')) != source['sha256']: raise ValueError('Archived source differs from its identity')
    return root, meta


def parser_for(embedder):
    from llama_index.core.node_parser import TokenTextSplitter
    def node_id(position, document): return digest([document.doc_id, document.metadata['sha256'], position, 256, 32])
    return TokenTextSplitter(chunk_size=256, chunk_overlap=32, tokenizer=embedder.tokens, id_func=node_id)


def open_index(root, embedder):
    from llama_index.core import StorageContext, load_index_from_storage
    return load_index_from_storage(StorageContext.from_defaults(persist_dir=str(root/'index')),
                                   embed_model=embedder, transformations=[parser_for(embedder)])


def ingest(manifest, store, embedder, *, _before_publish=None):
    from llama_index.core import VectorStoreIndex, Document
    sources = load_sources(manifest); store = Path(store); admit_state_directory(store)
    store.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in ['CURRENT.json', 'writer.lock', 'generations']:
        if (store/name).is_symlink(): raise ValueError('Store control paths cannot be symlinks')
    with (store/'writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        identity = {'schema': 1, 'sources': {k: v['metadata'] for k, v in sorted(sources.items())},
                    'embedding': embedder.fingerprint, 'splitter': {'tokens': 256, 'overlap': 32},
                    'framework_version': importlib.metadata.version('llama-index-core')}
        generation = digest(identity); previous = {}; prior_root = None
        if (store/'CURRENT.json').exists():
            prior_root, prior = open_generation(store); previous = prior['identity']['sources']
            if prior['identity'] == identity:
                return {'generation': generation, 'unchanged': len(sources), 'added': [], 'updated': [], 'removed': [], 'published': False}
            if prior['identity']['embedding'] != identity['embedding']: raise ValueError('Embedding model/configuration changed;use a new store')
            if prior['identity']['framework_version'] != identity['framework_version']: raise ValueError('Framework changed;use a new store')
        changed = sorted(k for k in sources if k not in previous or sources[k]['metadata'] != previous[k])
        removed = sorted(set(previous)-set(sources)); added = sorted(set(sources)-set(previous)); updated = sorted(set(changed)-set(added))
        generations = store/'generations'; generations.mkdir(mode=0o700, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix='.building-', dir=generations))
        try:
            index = open_index(prior_root, embedder) if prior_root else VectorStoreIndex([], embed_model=embedder, transformations=[parser_for(embedder)])
            for key in removed+updated: index.delete_ref_doc(key, delete_from_docstore=True)
            for key in changed:
                item = sources[key]; metadata = item['metadata']
                doc = Document(id_=key, text=item['text'], metadata=metadata,
                               excluded_embed_metadata_keys=list(metadata), excluded_llm_metadata_keys=list(metadata))
                index.insert(doc)
            active = dict(index.ref_doc_info)
            if set(active) != set(sources): raise ValueError('Active index documents disagree with collection')
            index.storage_context.persist(persist_dir=str(staging/'index'))
            (staging/'sources').mkdir()
            for key, item in sources.items(): (staging/'sources'/(key+'.txt')).write_bytes(item['raw'])
            nodes = {}
            for key, reference in active.items():
                for node in index.docstore.get_nodes(reference.node_ids):
                    start, end = node.start_char_idx, node.end_char_idx
                    if start is None or end is None or sources[key]['text'][start:end] != node.text: raise ValueError('Chunk offsets do not match original source')
                    nodes[node.node_id] = {'source_id': key, 'start': start, 'end': end, 'text_sha256': hashlib.sha256(node.text.encode()).hexdigest()}
            write(staging/'nodes.json', nodes)
            fingerprints = {str(p.relative_to(staging)): sha(p) for p in staging.rglob('*') if p.is_file()}
            meta = {'identity': identity, 'files': fingerprints, 'node_count': len(nodes)}
            write(staging/'generation.json', meta)
            for p in staging.rglob('*'):
                if p.is_file():
                    with p.open('rb') as stream: os.fsync(stream.fileno())
            if _before_publish: _before_publish(staging)
            destination = generations/generation
            if destination.exists():
                existing_root, existing = open_generation(store, generation)
                if existing['identity'] != identity: raise ValueError('Generation collision')
                shutil.rmtree(staging)
            else: os.rename(staging, destination)
            write(store/'CURRENT.json', {'generation': generation})
            return {'generation': generation, 'added': added, 'updated': updated, 'removed': removed,
                    'unchanged': len(sources)-len(changed), 'nodes': len(nodes), 'published': True}
        finally:
            if staging.exists(): shutil.rmtree(staging)


def citation(store, citation_id):
    parts = citation_id.split(':')
    if len(parts) != 2 or not all(re.fullmatch('[a-f0-9]{64}', x) for x in parts): raise ValueError('Invalid citation ID')
    generation, node_id = parts; root, meta = open_generation(store, generation)
    nodes = json.loads((root/'nodes.json').read_text())
    if node_id not in nodes: raise ValueError('Citation is not in that generation')
    row = nodes[node_id]; source_id = row['source_id']; source = meta['identity']['sources'][source_id]
    text = (root/'sources'/(source_id+'.txt')).read_bytes().decode('utf-8'); excerpt = text[row['start']:row['end']]
    if hashlib.sha256(excerpt.encode()).hexdigest() != row['text_sha256']: raise ValueError('Citation text fingerprint changed')
    start = text[:row['start']].count('\n')+1; end = text[:max(row['start'], row['end']-1)].count('\n')+1
    current = json.loads((Path(store)/'CURRENT.json').read_text())['generation']
    return {'citation_id': citation_id, 'generation': generation, 'is_current_generation': generation == current,
            'source_id': source_id, 'title': source['title'], 'source_kind': source['kind'], 'source_url': source['url'],
            'source_sha256': source['sha256'], 'line_start': start, 'line_end': end,
            'char_start': row['start'], 'char_end': row['end'], 'excerpt': excerpt}


def terms(text):
    text = text.casefold(); latin = re.findall('[a-z0-9_]+', text); words = list(latin)
    for run in re.findall('[\u3400-\u9fff]+', text): words.extend(run[i:i+2] for i in range(max(1, len(run)-1)))
    return words


def lexical(nodes, query):
    query_terms = set(terms(query)); counts = {n.node_id: Counter(terms(n.text)) for n in nodes}
    lengths = {k: sum(c.values()) for k, c in counts.items()}; avg = sum(lengths.values())/max(1, len(nodes)); scores = {}
    for term in query_terms:
        df = sum(term in c for c in counts.values()); idf = math.log(1+(len(nodes)-df+.5)/(df+.5))
        for key, counter in counts.items():
            frequency = counter[term]
            if frequency: scores[key] = scores.get(key, 0)+idf*frequency*2.2/(frequency+1.2*(.25+.75*lengths[key]/max(avg, 1)))
    return sorted(scores, key=lambda key: (-scores[key], key))


def search(store, query, embedder, *, top_k=5, mode='hybrid', source_id=None):
    if not isinstance(query, str) or not query.strip() or len(query)>2000: raise ValueError('Use a nonempty query up to2000characters')
    if not 1 <= top_k <= 8 or mode not in ['semantic', 'lexical', 'hybrid']: raise ValueError('Invalid retrieval options')
    root, meta = open_generation(store); generation = root.name
    if meta['identity']['embedding'] != embedder.fingerprint: raise ValueError('Query embedding differs from stored model')
    if source_id and source_id not in meta['identity']['sources']: return {'generation': generation, 'results': [], 'status': 'source_not_in_active_collection'}
    index = open_index(root, embedder); lookup = json.loads((root/'nodes.json').read_text())
    nodes = index.docstore.get_nodes(list(lookup)); nodes = [n for n in nodes if source_id is None or n.metadata['id'] == source_id]
    sparse = lexical(nodes, query) if mode != 'semantic' else []
    dense = []
    if mode != 'lexical':
        from llama_index.core.vector_stores import MetadataFilters, MetadataFilter
        options = {'filters': MetadataFilters(filters=[MetadataFilter(key='id', value=source_id)])} if source_id else {}
        dense = [r.node.node_id for r in index.as_retriever(similarity_top_k=min(24, len(nodes)), **options).retrieve(query)]
    rankings = [dense] if mode == 'semantic' else [sparse[:24]] if mode == 'lexical' else [dense, sparse[:24]]
    scores = {}
    for ranking in rankings:
        for rank, node_id in enumerate(ranking): scores[node_id] = scores.get(node_id, 0)+1/(60+rank+1)
    ordered = sorted(scores, key=lambda key: (-scores[key], key)); results = []; seen = set()
    for node_id in ordered:
        key = lookup[node_id]['source_id']
        if key in seen: continue
        seen.add(key); result = citation(store, generation+':'+node_id); result['ranking_score'] = scores[node_id]; results.append(result)
        if len(results) == top_k: break
    return {'generation': generation, 'mode': mode, 'results': results, 'generated_answer': False,
            'note': 'Candidate source passages,not an answer or calibrated relevance probability.'}


def main(argv=None, *, embedding_observer=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    ingest_parser = sub.add_parser('ingest'); ingest_parser.add_argument('--manifest', type=Path, required=True)
    query_parser = sub.add_parser('search'); query_parser.add_argument('--query', required=True); query_parser.add_argument('--mode', choices=['semantic', 'lexical', 'hybrid'], default='hybrid'); query_parser.add_argument('--source'); query_parser.add_argument('--top-k', type=int, default=5)
    read_parser = sub.add_parser('read'); read_parser.add_argument('--citation-id', required=True)
    for item in [ingest_parser, query_parser, read_parser]: item.add_argument('--store', type=Path, required=True)
    for item in [ingest_parser, query_parser]: item.add_argument('--model-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'read': result = citation(args.store, args.citation_id)
    else:
        from .research_embeddings import LocalE5Embedding
        model = LocalE5Embedding(args.model_dir, observer=embedding_observer)
        result = ingest(args.manifest, args.store, model) if args.command == 'ingest' else search(args.store, args.query, model, top_k=args.top_k, mode=args.mode, source_id=args.source)
        result['CPU_embedding_calls'] = model.counts
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
