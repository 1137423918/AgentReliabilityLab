"""Prepare explicit local UTF-8 documents and verify the pinned E5 asset set."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from urllib.parse import quote, urlsplit


def prepare(directory, output, base_url):
    directory = Path(directory).resolve(); output = Path(output).absolute()
    url = urlsplit(base_url)
    if url.scheme != 'https' or not url.netloc or url.query or url.fragment:
        raise ValueError('Use an HTTPS source base URL without query or fragment')
    if not directory.is_dir() or directory == output or directory in output.parents:
        raise ValueError('Output must be outside the source directory')
    if output.exists() or output.is_symlink(): raise ValueError('Use a new output directory')
    rows = []; payloads = {}; total = 0
    for path in sorted(directory.rglob('*')):
        rel = path.relative_to(directory)
        if any(p.startswith('.') for p in rel.parts): continue
        if path.is_symlink(): raise ValueError('Source symlinks are not accepted')
        if not path.is_file() or path.suffix.lower() not in {'.md', '.txt', '.rst', '.bib'}: continue
        with path.open('rb') as stream: raw = stream.read(524289)
        total += len(raw)
        if len(raw) > 524288 or total > 16*1024**2: raise ValueError('Source collection exceeds byte limit')
        text = raw.decode('utf-8')
        if not text.strip(): raise ValueError('Empty document: '+str(rel))
        source_id = 'src_'+hashlib.sha256(rel.as_posix().encode()).hexdigest()[:20]
        rows.append({'id': source_id, 'path': 'sources/'+source_id+'.txt', 'title': rel.as_posix(),
                     'url': base_url.rstrip('/')+'/'+quote(rel.as_posix(), safe='/'),
                     'kind': 'local_document_snapshot', 'sha256': hashlib.sha256(raw).hexdigest()})
        payloads[source_id] = raw
        if len(rows) > 256: raise ValueError('At most256documents are supported')
    if not rows: raise ValueError('No supported nonempty documents found')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.research-intake-', dir=output.parent))
    try:
        (temporary/'sources').mkdir()
        for source_id, raw in payloads.items(): (temporary/'sources'/(source_id+'.txt')).write_bytes(raw)
        (temporary/'collection.json').write_text(json.dumps({'version': 1, 'sources': rows}, ensure_ascii=False, indent=2)+'\n')
        # An existing nonempty directory is never replaced. Inputs are trusted local
        # files; this operation is not an adversarial snapshot of a mutating tree.
        if output.exists() or output.is_symlink(): raise ValueError('Output appeared during preparation')
        temporary.rename(output)
    finally:
        if temporary.exists(): shutil.rmtree(temporary)
    return {'manifest': str(output/'collection.json'), 'documents': len(rows), 'bytes': total,
            'source_ids': [r['id'] for r in rows], 'model_calls': 0, 'source_urls_claim_verified': False}


def check_model(directory):
    directory = Path(directory)
    expected = json.loads(Path(__file__).with_name('research_model_assets.json').read_text())
    for row in expected['files']:
        path = directory/row['path']
        if path.is_symlink() or path.stat().st_size != row['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Model asset differs from pinned manifest: '+row['path'])
    manifest = directory/'model-manifest.json'
    if manifest.is_symlink(): raise ValueError('Model manifest cannot be a symlink')
    created = not manifest.exists()
    if created:
        with manifest.open('x') as stream: stream.write(json.dumps(expected, indent=2)+'\n')
    actual = json.loads(manifest.read_text())
    for key in ['model_id', 'revision', 'files']:
        if actual[key] != expected[key]: raise ValueError('Existing model manifest differs from pinned assets')
    return {'model': actual['model_id'], 'revision': actual['revision'], 'files': len(actual['files']),
            'manifest_created': created, 'model_calls': 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--directory', type=Path, required=True); p.add_argument('--output', type=Path, required=True); p.add_argument('--base-url', required=True)
    p = sub.add_parser('check-model'); p.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args(argv)
    result = prepare(args.directory, args.output, args.base_url) if args.command == 'prepare' else check_model(args.directory)
    print(json.dumps(result, ensure_ascii=False, indent=2))
