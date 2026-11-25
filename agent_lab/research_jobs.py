"""Durable, bounded batch retrieval on one immutable research generation.

State is owner-controlled local SQLite, not an untrusted job queue. A retrieval
attempt is reserved before querying. A crash before its result commits leaves
that attempt charged; explicit resume can use only the remaining fixed budget.
"""
from pathlib import Path
import argparse
import fcntl
import hashlib
import importlib.metadata
import json
import os
import platform
import sqlite3
import stat
import tempfile
from urllib.parse import quote

from .storage import admit_state_directory
from .research_library import ResearchSnapshot, digest, load_batch_requests, open_generation, packed, sha


def _paths(directory):
    directory = Path(directory).absolute()
    if directory.is_symlink(): raise ValueError('State directory cannot be a symlink')
    admit_state_directory(directory)
    for name in ['batch.lock', 'batch.sqlite', 'batch.sqlite-wal', 'batch.sqlite-shm']:
        p = directory/name
        if p.is_symlink() or (p.exists() and not stat.S_ISREG(p.stat().st_mode)):
            raise ValueError('Batch control paths must be regular files')
    return directory


def _code_identity():
    here = Path(__file__).parent
    return {'modules': {n: sha(here/n) for n in ['research_jobs.py', 'research_library.py', 'research_embeddings.py']},
            'python': platform.python_version(),
            'versions': {n: importlib.metadata.version(n) for n in ['llama-index-core', 'numpy', 'torch', 'transformers']}}


def _summary(db):
    job = db.execute('SELECT binding, status, output_sha256 FROM job WHERE id=1').fetchone()
    if job is None: raise ValueError('Batch state was not initialized; use a new state directory')
    binding, status, output_sha = json.loads(job[0]), job[1], job[2]
    attempts = dict(db.execute('SELECT status, COUNT(*) FROM attempts GROUP BY status'))
    completed = db.execute('SELECT COUNT(*) FROM results').fetchone()[0]
    return {'job_id': digest(binding), 'generation': binding['generation'], 'status': status,
            'queries': binding['queries'], 'completed_queries': completed,
            'attempt_limit': binding['attempt_limit'], 'attempts': attempts,
            'attempts_remaining': binding['attempt_limit']-sum(attempts.values()),
            'output_sha256': output_sha, 'generated_answers': False}


def batch_status(state_dir):
    """Inspect committed state without importing a model or changing the journal."""
    directory = _paths(state_dir); path = directory/'batch.sqlite'
    if not path.is_file(): raise FileNotFoundError('No batch database')
    db = sqlite3.connect('file:'+quote(str(path.resolve()), safe='/')+'?mode=ro', uri=True)
    try: return _summary(db)
    finally: db.close()


def _publish(output, payload):
    """Create a final file without overwriting; recover a matching prior publish."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink(): raise ValueError('Output cannot be a symlink')
    if output.exists():
        if not output.is_file() or output.read_bytes() != payload:
            raise FileExistsError('Output differs from this batch; it was not overwritten')
        return
    fd, name = tempfile.mkstemp(prefix='.'+output.name+'.', suffix='.publishing', dir=output.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        try: os.link(temporary, output)
        except FileExistsError:
            if output.is_symlink() or not output.is_file() or output.read_bytes() != payload:
                raise FileExistsError('Output appeared during publication; it was not overwritten')
        directory_fd = os.open(output.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
    finally: temporary.unlink(missing_ok=True)


def run_batch_job(store, requests, output, embedder, *, state_dir, resume=False,
                  attempt_limit=None, top_k=10, modes=('lexical', 'semantic', 'hybrid'),
                  _after_commit=None):
    raw, rows = load_batch_requests(requests, top_k=top_k, modes=modes)
    limit = len(rows) if attempt_limit is None else attempt_limit
    if type(limit) is not int or not len(rows) <= limit <= 1024:
        raise ValueError('Attempt limit must cover all queries and be at most1024')
    directory = _paths(state_dir); directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    output = Path(output).absolute(); store = Path(store).resolve()
    if output == directory or directory in output.parents:
        raise ValueError('Final output must be outside the state directory')
    partial = output.with_name(output.name+'.partial')
    if partial.exists() or partial.is_symlink():
        raise FileExistsError('Legacy partial output is not a resumable job')
    lock = (directory/'batch.lock').open('a'); db = None
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        exists = (directory/'batch.sqlite').exists()
        if exists != bool(resume):
            raise FileExistsError('Use --resume for an existing job, or a new state directory')
        if not exists and (output.exists() or output.is_symlink()):
            raise FileExistsError('Use a new final output path')
        db = sqlite3.connect(directory/'batch.sqlite', timeout=0)
        db.execute('PRAGMA journal_mode=WAL'); db.execute('PRAGMA synchronous=FULL')
        if exists:
            old = db.execute('SELECT binding FROM job WHERE id=1').fetchone()
            if old is None: raise ValueError('Batch state was not initialized; use a new state directory')
            previous = json.loads(old[0]); generation = previous['generation']
        else:
            generation = open_generation(store)[0].name
        root, _ = open_generation(store, generation)
        binding = {'schema': 1, 'query_input_sha256': hashlib.sha256(raw).hexdigest(),
                   'queries': len(rows), 'store': str(store), 'generation': generation,
                   'generation_manifest_sha256': sha(root/'generation.json'),
                   'embedding': embedder.fingerprint, 'code_runtime': _code_identity(),
                   'modes': list(modes), 'top_k': top_k, 'attempt_limit': limit,
                   'output': str(output)}
        if exists:
            if binding != previous: raise ValueError('Batch identity changed; resume requires the exact original inputs/configuration')
        else:
            db.executescript('''
                CREATE TABLE job(id INTEGER PRIMARY KEY CHECK(id=1), binding TEXT NOT NULL, status TEXT NOT NULL, output_sha256 TEXT);
                CREATE TABLE attempts(id INTEGER PRIMARY KEY, position INTEGER NOT NULL, status TEXT NOT NULL, error_type TEXT);
                CREATE TABLE results(position INTEGER PRIMARY KEY, payload BLOB NOT NULL, sha256 TEXT NOT NULL);
            ''')
            with db: db.execute('INSERT INTO job VALUES(1, ?, ?, NULL)', (packed(binding).decode(), 'retrieving'))
        saved = {}
        for position, payload, expected in db.execute('SELECT position, payload, sha256 FROM results ORDER BY position'):
            if not 0 <= position < len(rows) or hashlib.sha256(payload).hexdigest() != expected:
                raise ValueError('Stored batch result fingerprint changed')
            value = json.loads(payload); row = rows[position]
            if (value['id'] != row['id'] or value['query_sha256'] != hashlib.sha256(row['query'].encode()).hexdigest()
                    or value['generation'] != generation or set(value['modes']) != set(modes)):
                raise ValueError('Stored batch result belongs to different inputs')
            saved[position] = payload
        # The exclusive OS lock proves no prior writer remains. Its unresolved
        # reservations are unknown, never refunded or labeled completed.
        with db: db.execute("UPDATE attempts SET status='unknown' WHERE status='reserved'")
        snapshot = None
        for position, row in enumerate(rows):
            if position in saved: continue
            if db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0] >= limit:
                raise RuntimeError('Batch query-attempt budget exhausted; unknown/failed attempts remain charged')
            if snapshot is None: snapshot = ResearchSnapshot(store, embedder, generation=generation)
            with db:
                attempt = db.execute("INSERT INTO attempts(position,status) VALUES(?, 'reserved')", (position,)).lastrowid
            try:
                result = {'id': row['id'], 'query_sha256': hashlib.sha256(row['query'].encode()).hexdigest(),
                          'generation': generation, 'modes': snapshot.search_modes(row['query'], modes=modes, top_k=top_k)}
                payload = packed(result)
            except BaseException as error:
                with db: db.execute("UPDATE attempts SET status='failed',error_type=? WHERE id=?", (type(error).__name__, attempt))
                raise
            with db:
                db.execute('INSERT INTO results VALUES(?,?,?)', (position, payload, hashlib.sha256(payload).hexdigest()))
                db.execute("UPDATE attempts SET status='completed' WHERE id=?", (attempt,))
            saved[position] = payload
            if _after_commit: _after_commit(position)
        payload = b''.join(saved[i]+b'\n' for i in range(len(rows)))
        with db: db.execute("UPDATE job SET status='ready',output_sha256=? WHERE id=1", (hashlib.sha256(payload).hexdigest(),))
        _publish(output, payload)
        with db: db.execute("UPDATE job SET status='published' WHERE id=1")
        return _summary(db)
    finally:
        if db is not None: db.close()
        lock.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Inspect durable retrieval progress; no model is loaded.')
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(batch_status(args.state_dir), ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
