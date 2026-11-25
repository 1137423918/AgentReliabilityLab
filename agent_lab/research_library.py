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

MAX_SOURCES = 8192


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
    if spec.get('version') != 1 or not 1 <= len(spec['sources']) <= MAX_SOURCES: raise ValueError('Expected1–8192explicit sources')
    total = 0; pdfs = {}
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
        pdf_raw = None
        if 'pdf' in item:
            pdf = item['pdf']; pdf_sha = pdf['sha256']
            if not re.fullmatch('[a-f0-9]{64}', pdf_sha) or pdf['path'] != 'originals/'+pdf_sha+'.pdf':
                raise ValueError('Invalid original PDF path or hash')
            if type(pdf['page_number']) is not int or type(pdf['page_count']) is not int or not 1 <= pdf['page_number'] <= pdf['page_count'] <= 256:
                raise ValueError('Invalid PDF page number')
            if item['kind'] != 'pdf_page_text' or url.fragment != 'page='+str(pdf['page_number']):
                raise ValueError('PDF source kind/URL disagrees with page')
            if not isinstance(pdf['page_label'], str) or pdf['extractor'].get('name') != 'pypdf' or pdf['extractor'].get('mode') != 'plain':
                raise ValueError('Invalid PDF extraction provenance')
            if pdf_sha not in pdfs:
                original = manifest.parent/pdf['path']
                if original.is_symlink(): raise ValueError('Original PDF cannot be a symlink')
                with original.open('rb') as stream: pdfs[pdf_sha] = stream.read(32*1024**2+1)
                if len(pdfs[pdf_sha]) > 32*1024**2 or sum(map(len, pdfs.values())) > 64*1024**2:
                    raise ValueError('Original PDF byte limit exceeded')
                if hashlib.sha256(pdfs[pdf_sha]).hexdigest() != pdf_sha: raise ValueError('Original PDF bytes differ')
            pdf_raw = pdfs[pdf_sha]
            if len(pdf_raw) != pdf['bytes']: raise ValueError('Original PDF size differs')
            metadata['pdf'] = {k: v for k, v in pdf.items() if k != 'path'}
        rows[key] = {'metadata': metadata, 'raw': raw, 'text': text, 'fingerprint': digest(metadata), 'pdf_raw': pdf_raw}
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
            documents = []
            for key in changed:
                item = sources[key]; metadata = item['metadata']
                doc = Document(id_=key, text=item['text'], metadata=metadata,
                               excluded_embed_metadata_keys=list(metadata), excluded_llm_metadata_keys=list(metadata))
                documents.append(doc)
            if documents:
                # Split multiple documents together so the embedding adapter can
                # fill batches across document boundaries. Preserve source links
                # and document hashes through LlamaIndex's public interfaces.
                parsed = parser_for(embedder).get_nodes_from_documents(documents)
                for node in parsed:
                    start, end = node.start_char_idx, node.end_char_idx
                    if start is None or end is None or sources[node.ref_doc_id]['text'][start:end] != node.text:
                        raise ValueError('Chunk offsets do not match original source')
                index.insert_nodes(parsed)
                for doc in documents: index.docstore.set_document_hash(doc.id_, doc.hash)
            active = dict(index.ref_doc_info)
            if set(active) != set(sources): raise ValueError('Active index documents disagree with collection')
            index.storage_context.persist(persist_dir=str(staging/'index'))
            (staging/'sources').mkdir()
            for key, item in sources.items():
                (staging/'sources'/(key+'.txt')).write_bytes(item['raw'])
                if item['pdf_raw'] is not None:
                    (staging/'originals').mkdir(exist_ok=True)
                    original = staging/'originals'/(item['metadata']['pdf']['sha256']+'.pdf')
                    if not original.exists(): original.write_bytes(item['pdf_raw'])
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
    return _citation_payload(store, root, meta, nodes, node_id)


def _citation_payload(store, root, meta, nodes, node_id, text=None):
    generation = root.name
    citation_id = generation+':'+node_id
    if node_id not in nodes: raise ValueError('Citation is not in that generation')
    row = nodes[node_id]; source_id = row['source_id']; source = meta['identity']['sources'][source_id]
    if text is None: text = (root/'sources'/(source_id+'.txt')).read_bytes().decode('utf-8')
    excerpt = text[row['start']:row['end']]
    if hashlib.sha256(excerpt.encode()).hexdigest() != row['text_sha256']: raise ValueError('Citation text fingerprint changed')
    start = text[:row['start']].count('\n')+1; end = text[:max(row['start'], row['end']-1)].count('\n')+1
    current = json.loads((Path(store)/'CURRENT.json').read_text())['generation']
    result = {'citation_id': citation_id, 'generation': generation, 'is_current_generation': generation == current,
            'source_id': source_id, 'title': source['title'], 'source_kind': source['kind'], 'source_url': source['url'],
            'source_sha256': source['sha256'], 'line_start': start, 'line_end': end,
            'char_start': row['start'], 'char_end': row['end'], 'excerpt': excerpt}
    if 'pdf' in source:
        original = root/'originals'/(source['pdf']['sha256']+'.pdf')
        if sha(original) != source['pdf']['sha256']: raise ValueError('Archived PDF differs from citation')
        result['pdf'] = dict(source['pdf'])
        result['note'] = 'Offsets refer to extracted page text; PDF page is1-based, label is separate. No layout/OCR guarantee.'
    return result


def terms(text):
    text = text.casefold(); latin = re.findall('[a-z0-9_]+', text); words = list(latin)
    for run in re.findall('[\u3400-\u9fff]+', text): words.extend(run[i:i+2] for i in range(max(1, len(run)-1)))
    return words


class LexicalIndex:
    """BM25 statistics for a fixed node set, reusable across queries."""
    def __init__(self, nodes):
        self.size = len(nodes); self.lengths = {}; self.postings = {}
        for node in nodes:
            counts = Counter(terms(node.text)); self.lengths[node.node_id] = sum(counts.values())
            for term, frequency in counts.items():
                self.postings.setdefault(term, []).append((node.node_id, frequency))
        self.average = sum(self.lengths.values())/max(1, self.size)

    def rank(self, query):
        scores = {}
        for term in sorted(set(terms(query))):
            postings = self.postings.get(term, ())
            idf = math.log(1+(self.size-len(postings)+.5)/(len(postings)+.5))
            for key, frequency in postings:
                scores[key] = scores.get(key, 0)+idf*frequency*2.2/(frequency+1.2*(.25+.75*self.lengths[key]/max(self.average, 1)))
        return sorted(scores, key=lambda key: (-scores[key], key))


def lexical(nodes, query):
    return LexicalIndex(nodes).rank(query)


class ResearchSnapshot:
    """Verified, captured generation for repeated retrieval on a trusted store.

    Open again to observe a new generation or revalidate disk contents. Published
    generations are immutable in normal use; this is not a filesystem watcher.
    Source text is captured at open, while PDF reads retain their hash check.
    """
    def __init__(self, store, embedder, generation=None):
        self.store = Path(store); self.root, self.meta = open_generation(store, generation)
        self.generation = self.root.name; self.embedder = embedder
        if self.meta['identity']['embedding'] != embedder.fingerprint:
            raise ValueError('Query embedding differs from stored model')
        self.index = open_index(self.root, embedder)
        self.lookup = json.loads((self.root/'nodes.json').read_text())
        self.nodes = self.index.docstore.get_nodes(list(self.lookup))
        self.sparse = LexicalIndex(self.nodes); self.texts = {}
        for key, source in self.meta['identity']['sources'].items():
            raw = (self.root/'sources'/(key+'.txt')).read_bytes()
            if hashlib.sha256(raw).hexdigest() != source['sha256']:
                raise ValueError('Archived source differs from its identity')
            self.texts[key] = raw.decode('utf-8')

    def search_modes(self, query, *, modes=('lexical', 'semantic', 'hybrid'), top_k=5, source_id=None):
        if not isinstance(query, str) or not query.strip() or len(query)>2000:
            raise ValueError('Use a nonempty query up to2000characters')
        if (not modes or len(set(modes)) != len(modes) or
                any(mode not in ['semantic', 'lexical', 'hybrid'] for mode in modes) or not 1 <= top_k <= 32):
            raise ValueError('Invalid retrieval options')
        if source_id and source_id not in self.meta['identity']['sources']:
            return {mode: {'generation': self.generation, 'results': [], 'status': 'source_not_in_active_collection'} for mode in modes}
        nodes = [n for n in self.nodes if source_id is None or n.metadata['id'] == source_id]
        sparse = []
        if any(mode != 'semantic' for mode in modes):
            sparse = (LexicalIndex(nodes) if source_id else self.sparse).rank(query)[:max(24, 4*top_k)]
        dense = []
        if any(mode != 'lexical' for mode in modes):
            from llama_index.core.vector_stores import MetadataFilters, MetadataFilter
            options = {'filters': MetadataFilters(filters=[MetadataFilter(key='id', value=source_id)])} if source_id else {}
            dense = [r.node.node_id for r in self.index.as_retriever(similarity_top_k=min(max(24, 4*top_k), len(nodes)), **options).retrieve(query)]
        output = {}
        for mode in modes:
            rankings = [dense] if mode == 'semantic' else [sparse] if mode == 'lexical' else [dense, sparse]
            scores = {}
            for ranking in rankings:
                for rank, node_id in enumerate(ranking): scores[node_id] = scores.get(node_id, 0)+1/(60+rank+1)
            results = []; seen = set()
            for node_id in sorted(scores, key=lambda key: (-scores[key], key)):
                key = self.lookup[node_id]['source_id']
                if key in seen: continue
                seen.add(key)
                result = _citation_payload(self.store, self.root, self.meta, self.lookup, node_id, self.texts[key])
                result['ranking_score'] = scores[node_id]; results.append(result)
                if len(results) == top_k: break
            output[mode] = {'generation': self.generation, 'mode': mode, 'results': results, 'generated_answer': False,
                            'note': 'Candidate source passages,not an answer or calibrated relevance probability.'}
        return output

    def search(self, query, *, top_k=5, mode='hybrid', source_id=None):
        return self.search_modes(query, modes=(mode,), top_k=top_k, source_id=source_id)[mode]


def search(store, query, embedder, *, top_k=5, mode='hybrid', source_id=None):
    if not isinstance(query, str) or not query.strip() or len(query)>2000:
        raise ValueError('Use a nonempty query up to2000characters')
    if not 1 <= top_k <= 32 or mode not in ['semantic', 'lexical', 'hybrid']:
        raise ValueError('Invalid retrieval options')
    return ResearchSnapshot(store, embedder).search(query, top_k=top_k, mode=mode, source_id=source_id)


def load_batch_requests(requests, *, top_k=10, modes=('lexical', 'semantic', 'hybrid')):
    requests = Path(requests)
    if requests.is_symlink(): raise ValueError('Query input cannot be a symlink')
    with requests.open('rb') as stream: raw = stream.read(1024**2+1)
    if len(raw)>1024**2: raise ValueError('Query input exceeds1MiB')
    rows = [json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
    if not 1 <= len(rows) <= 512: raise ValueError('Expected1–512queries')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'id', 'query'}: raise ValueError('Query rows require only id and query')
        key = checked_id(row['id']); query = row['query']
        if key in seen: raise ValueError('Repeated query ID')
        seen.add(key)
        if not isinstance(query, str) or not query.strip() or len(query)>2000:
            raise ValueError('Use a nonempty query up to2000characters')
    if not modes or len(set(modes)) != len(modes) or any(m not in ['lexical', 'semantic', 'hybrid'] for m in modes) or not 1 <= top_k <= 32:
        raise ValueError('Invalid retrieval options')
    return raw, rows


def search_batch(store, requests, output, embedder, *, top_k=10, modes=('lexical', 'semantic', 'hybrid')):
    """Capture one generation and atomically deliver a bounded JSONL query batch.

    A failed batch retains its .partial file for inspection. It is not resumable;
    existing final or partial outputs are never overwritten. Query IDs are
    caller-provided and do not need to expose query text in the result file.
    """
    raw, rows = load_batch_requests(requests, top_k=top_k, modes=modes)
    output = Path(output); partial = output.with_name(output.name+'.partial')
    if any(p.exists() or p.is_symlink() for p in [output, partial]): raise FileExistsError('Use a new batch output path')
    snapshot = ResearchSnapshot(store, embedder); output.parent.mkdir(parents=True, exist_ok=True)
    with partial.open('xb') as stream:
        for row in rows:
            result = {'id': row['id'], 'query_sha256': hashlib.sha256(row['query'].encode()).hexdigest(),
                      'generation': snapshot.generation,
                      'modes': snapshot.search_modes(row['query'], modes=modes, top_k=top_k)}
            stream.write(packed(result)+b'\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(partial, output)
    fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
    return {'generation': snapshot.generation, 'queries': len(rows), 'modes': list(modes), 'top_k': top_k,
            'candidate_nodes_per_ranker': max(24, 4*top_k), 'output_sha256': sha(output),
            'query_input_sha256': hashlib.sha256(raw).hexdigest(), 'generated_answers': False}


def main(argv=None, *, embedding_observer=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    ingest_parser = sub.add_parser('ingest'); ingest_parser.add_argument('--manifest', type=Path, required=True)
    query_parser = sub.add_parser('search'); query_parser.add_argument('--query', required=True); query_parser.add_argument('--mode', choices=['semantic', 'lexical', 'hybrid'], default='hybrid'); query_parser.add_argument('--source'); query_parser.add_argument('--top-k', type=int, default=5)
    batch_parser = sub.add_parser('search-batch'); batch_parser.add_argument('--queries', type=Path, required=True); batch_parser.add_argument('--output', type=Path, required=True); batch_parser.add_argument('--modes', nargs='+', choices=['lexical', 'semantic', 'hybrid'], default=['lexical', 'semantic', 'hybrid']); batch_parser.add_argument('--top-k', type=int, default=10)
    batch_parser.add_argument('--state-dir', type=Path); batch_parser.add_argument('--resume', action='store_true'); batch_parser.add_argument('--query-attempt-limit', type=int)
    read_parser = sub.add_parser('read'); read_parser.add_argument('--citation-id', required=True)
    for item in [ingest_parser, query_parser, batch_parser, read_parser]: item.add_argument('--store', type=Path, required=True)
    for item in [ingest_parser, query_parser, batch_parser]:
        item.add_argument('--model-dir', type=Path, required=True); item.add_argument('--embed-batch-size', type=int, choices=[1, 2, 4, 8, 16], default=4)
    args = parser.parse_args(argv)
    if args.command == 'search-batch' and not args.state_dir and (args.resume or args.query_attempt_limit is not None):
        parser.error('--resume and --query-attempt-limit require --state-dir')
    if args.command == 'read': result = citation(args.store, args.citation_id)
    else:
        from .research_embeddings import LocalE5Embedding
        model = LocalE5Embedding(args.model_dir, observer=embedding_observer, batch_size=args.embed_batch_size)
        if args.command == 'ingest': result = ingest(args.manifest, args.store, model)
        elif args.command == 'search-batch':
            if args.state_dir:
                from .research_jobs import run_batch_job
                result = run_batch_job(args.store, args.queries, args.output, model, state_dir=args.state_dir,
                                       resume=args.resume, attempt_limit=args.query_attempt_limit,
                                       top_k=args.top_k, modes=args.modes)
            else: result = search_batch(args.store, args.queries, args.output, model, top_k=args.top_k, modes=args.modes)
        else: result = search(args.store, args.query, model, top_k=args.top_k, mode=args.mode, source_id=args.source)
        result['CPU_embedding_calls'] = model.counts
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
