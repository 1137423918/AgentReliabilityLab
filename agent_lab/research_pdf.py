"""Prepare explicit digital-text PDFs as page sources with original-file provenance."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urlsplit, urlunsplit


def prepare_pdfs(manifest, output):
    from importlib.metadata import version
    from pypdf import PdfReader
    manifest = Path(manifest)
    output = Path(output).absolute()
    spec = json.loads(manifest.read_text())
    if spec.get('version') != 1 or not 1 <= len(spec['pdfs']) <= 32:
        raise ValueError('Expected1–32explicit PDFs')
    if output.exists() or output.is_symlink():
        raise ValueError('Use a new output directory')
    rows = []; payloads = {}; originals = {}; documents = []; seen = set(); total = 0; total_pages = 0
    for item in spec['pdfs']:
        rel = Path(item['path'])
        if rel.is_absolute() or '..' in rel.parts or rel.as_posix() in seen:
            raise ValueError('Use unique relative PDF paths inside the manifest directory')
        seen.add(rel.as_posix())
        path = manifest.parent/rel
        if any(p.is_symlink() for p in [path, *path.parents]) or path.suffix.lower() != '.pdf':
            raise ValueError('Use nonsymlink PDF files')
        if path.resolve() == output or path.resolve() in output.parents:
            raise ValueError('Output cannot replace a PDF')
        url = urlsplit(item['url'])
        if url.scheme != 'https' or not url.netloc or url.fragment or url.username or url.password:
            raise ValueError('Use an HTTPS PDF URL without credentials or fragment')
        if not isinstance(item['title'], str) or not item['title'].strip():
            raise ValueError('PDF title is required')
        with path.open('rb') as stream: raw = stream.read(32*1024**2+1)
        total += len(raw)
        if len(raw) > 32*1024**2 or total > 64*1024**2:
            raise ValueError('PDF byte limit exceeded')
        pdf_sha = hashlib.sha256(raw).hexdigest()
        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted:
            raise ValueError('Encrypted PDFs are not supported')
        pages = len(reader.pages)
        total_pages += pages
        if not 1 <= pages <= 256 or total_pages > 256:
            raise ValueError('Collection supports at most256PDF pages')
        labels = reader.page_labels
        page_records = []
        for offset, page in enumerate(reader.pages):
            text = page.extract_text(extraction_mode='plain') or ''
            content = text.encode('utf-8')
            if len(content) > 524288:
                raise ValueError('Extracted page exceeds text limit')
            page_number = offset+1
            record = {'page_number': page_number, 'page_label': labels[offset],
                      'text_sha256': hashlib.sha256(content).hexdigest(), 'text_bytes': len(content)}
            page_records.append(record)
            if not text.strip():
                record['status'] = 'no_extractable_text'
                continue
            source_id = 'pdf_'+hashlib.sha256(rel.as_posix().encode()).hexdigest()[:20]+'_p'+str(page_number)
            pdf = {'path': 'originals/'+pdf_sha+'.pdf', 'sha256': pdf_sha, 'bytes': len(raw),
                   'page_number': page_number, 'page_label': labels[offset], 'page_count': pages,
                   'extractor': {'name': 'pypdf', 'version': version('pypdf'), 'mode': 'plain'}}
            rows.append({'id': source_id, 'path': 'sources/'+source_id+'.txt', 'title': item['title']+' — PDF page '+str(page_number),
                         'url': urlunsplit(url._replace(fragment='page='+str(page_number))),
                         'kind': 'pdf_page_text', 'sha256': record['text_sha256'], 'pdf': pdf})
            payloads[source_id] = content
            record.update(status='indexed_text_source', source_id=source_id)
        if not any(r['status'] == 'indexed_text_source' for r in page_records):
            raise ValueError('No extractable PDF text; OCR is not provided')
        originals[pdf_sha] = raw
        documents.append({'title': item['title'], 'url': item['url'], 'sha256': pdf_sha,
                          'bytes': len(raw), 'pages': page_records})
    if sum(len(raw) for raw in payloads.values()) > 16*1024**2:
        raise ValueError('Extracted text collection exceeds16MiB')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.research-pdf-', dir=output.parent))
    try:
        (temporary/'sources').mkdir(); (temporary/'originals').mkdir()
        for key, raw in payloads.items(): (temporary/'sources'/(key+'.txt')).write_bytes(raw)
        for key, raw in originals.items(): (temporary/'originals'/(key+'.pdf')).write_bytes(raw)
        (temporary/'collection.json').write_text(json.dumps({'version': 1, 'sources': rows}, ensure_ascii=False, indent=2)+'\n')
        (temporary/'pdf-extraction.json').write_text(json.dumps({'version': 1, 'documents': documents,
            'scope': 'Digital text extraction, not OCR, table reconstruction or layout-equivalence verification.',
            'source_urls_claim_verified': False}, ensure_ascii=False, indent=2)+'\n')
        if output.exists() or output.is_symlink(): raise ValueError('Output appeared during preparation')
        temporary.rename(output)
    finally:
        if temporary.exists(): shutil.rmtree(temporary)
    return {'manifest': str(output/'collection.json'), 'pdfs': len(documents), 'page_sources': len(rows),
            'pages_without_text': sum(r['status']=='no_extractable_text' for d in documents for r in d['pages']),
            'model_calls': 0, 'source_urls_claim_verified': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(prepare_pdfs(args.manifest, args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
