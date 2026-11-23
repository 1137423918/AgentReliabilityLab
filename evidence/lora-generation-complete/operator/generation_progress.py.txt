"""Durable case results and charged local-generation attempts, not HTTP billing.

Unknown attempts remain charged. Only a stopped segment's resource-guard
evidence may authorize a bounded retry; completed cases cannot be rerun.
The operator is trusted: checksums detect accidents, not malicious rewrites.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
from uuid import uuid4


class ProgressError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def atomic_save(path, value):
    temp = path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    try:
        with temp.open('x', encoding='utf-8') as stream:
            os.chmod(temp, 0o600)
            json.dump(value, stream, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temp.unlink(missing_ok=True)


class GenerationProgress:
    """One experiment journal; create once, reopen by its immutable definition."""

    RESOURCE_GUARDS = {'foreign_compute_client', 'GPU_telemetry_stale', 'host_memory_floor'}

    def __init__(self, root, definition, *, create=False):
        self.root = Path(root)
        self.path = self.root/'generation-progress.json'
        self.definition = json.loads(json.dumps(definition))
        variants = self.definition['variants']; cases = self.definition['cases']
        limits = self.definition['limits']
        if (not isinstance(variants, list) or not variants
                or len(variants) != len(set(variants))
                or any(not isinstance(v, str) or not re.fullmatch(r'[a-z0-9_-]{1,64}', v) for v in variants)
                or not isinstance(cases, list) or not 1 <= len(cases) <= 1000
                or set(limits) != {'total_attempts', 'variant_attempts', 'case_attempts'}
                or any(type(v) is not int or not 1 <= v <= 10000 for v in limits.values())):
            raise ProgressError('Invalid fixed generation definition')
        for case in cases:
            if any(not isinstance(case.get(k), str) or not re.fullmatch(r'[a-f0-9]{64}', case[k])
                   for k in ['id_sha256', 'sample_sha256', 'request_sha256']):
                raise ProgressError('Invalid case fingerprint')
        self.owner = digest(self.definition)
        if create:
            self.root.mkdir(mode=0o700, exist_ok=False)
        if not self.root.is_dir() or self.root.is_symlink():
            raise ProgressError('Private progress directory is missing or is a symlink')
        with self.lock():
            if create:
                if self.path.exists():
                    raise ProgressError('Progress already exists')
                self._write({'version': 1, 'owner_sha256': self.owner,
                             'attempts': [], 'results': {}, 'imports': []})
            self._read()

    @contextlib.contextmanager
    def lock(self):
        fd = os.open(self.root/'generation-progress.lock',
                     os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    @contextlib.contextmanager
    def worker(self, variant):
        self._case(variant, 1)
        fd = os.open(self.root/(variant+'-worker.lock'),
                     os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'a') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ProgressError('This variant already has a worker') from exc
            yield

    def _case(self, variant, index):
        if variant not in self.definition['variants'] or type(index) is not int:
            raise ProgressError('Unknown variant or case index')
        if not 1 <= index <= len(self.definition['cases']):
            raise ProgressError('Case index outside the fixed definition')
        return self.definition['cases'][index-1]

    def _read(self):
        try:
            if self.path.is_symlink() or self.path.stat().st_size > 32*1024**2:
                raise ValueError('Invalid journal file')
            state = json.loads(self.path.read_text())
            checksum = state.pop('checksum')
            if (checksum != digest(state) or type(state['version']) is not int or state['version'] != 1
                    or state['owner_sha256'] != self.owner
                    or set(state) != {'version', 'owner_sha256', 'attempts', 'results', 'imports'}):
                raise ValueError('Journal identity or checksum changed')
            attempts = state['attempts']; limits = self.definition['limits']
            if not isinstance(attempts, list) or len(attempts) > limits['total_attempts']:
                raise ValueError('Invalid attempt list')
            for seq, attempt in enumerate(attempts, 1):
                case = self._case(attempt['variant'], attempt['case_index'])
                if (type(attempt['sequence']) is not int or attempt['sequence'] != seq
                        or attempt['request_sha256'] != case['request_sha256']
                        or attempt['state'] not in {'reserved', 'completed'}):
                    raise ValueError('Invalid attempt identity')
                permission = attempt.get('retry_permission')
                if permission is not None and (permission['guard'] not in self.RESOURCE_GUARDS
                                              or len(permission['controller_sha256']) != 64):
                    raise ValueError('Invalid retry permission')
            for variant in self.definition['variants']:
                scoped = [x for x in attempts if x['variant'] == variant]
                if len(scoped) > limits['variant_attempts']:
                    raise ValueError('Variant limit exceeded')
                for index in range(1, len(self.definition['cases'])+1):
                    same = [x for x in scoped if x['case_index'] == index]
                    if len(same) > limits['case_attempts']:
                        raise ValueError('Case limit exceeded')
                    if any(x['state'] == 'completed' or not x.get('retry_permission') for x in same[:-1]):
                        raise ValueError('Attempt repeated without resource authorization')
            for key, result in state['results'].items():
                attempt = attempts[result['attempt_sequence']-1]
                expected = attempt['variant']+':'+str(attempt['case_index'])
                if (key != expected or attempt['state'] != 'completed'
                        or digest(result['row']) != result['row_sha256']):
                    raise ValueError('Completed result changed')
            completed = [x for x in attempts if x['state'] == 'completed']
            if len(completed) != len(state['results']):
                raise ValueError('Completed attempt has no result')
            return state
        except (OSError, KeyError, TypeError, ValueError, IndexError) as exc:
            raise ProgressError('Missing or inconsistent generation progress; cannot reset') from exc

    def _write(self, state):
        value = {**state, 'checksum': digest(state)}
        if len(json.dumps(value, ensure_ascii=False).encode()) > 32*1024**2:
            raise ProgressError('Generation progress exceeds the fixed size bound')
        atomic_save(self.path, value)

    def snapshot(self):
        with self.lock():
            return self._read()

    def cached(self, variant, index):
        self._case(variant, index)
        with self.lock():
            result = self._read()['results'].get(variant+':'+str(index))
            return result['row'] if result else None

    def reserve(self, variant, index, request_sha256):
        expected = self._case(variant, index)
        if request_sha256 != expected['request_sha256']:
            raise ProgressError('Generation request changed')
        with self.lock():
            state = self._read(); attempts = state['attempts']; limits = self.definition['limits']
            if variant+':'+str(index) in state['results']:
                raise ProgressError('Completed cases cannot be regenerated')
            scoped = [x for x in attempts if x['variant'] == variant]
            same = [x for x in scoped if x['case_index'] == index]
            if (len(attempts) >= limits['total_attempts'] or len(scoped) >= limits['variant_attempts']
                    or len(same) >= limits['case_attempts']):
                raise ProgressError('Generation attempt budget exhausted')
            if same and not same[-1].get('retry_permission'):
                raise ProgressError('Unknown attempt stays charged and is not authorized for retry')
            entry = {'sequence': len(attempts)+1, 'variant': variant, 'case_index': index,
                     'request_sha256': request_sha256, 'state': 'reserved'}
            attempts.append(entry); self._write(state); return entry['sequence']

    def complete(self, sequence, row):
        with self.lock():
            state = self._read()
            if type(sequence) is not int or not 1 <= sequence <= len(state['attempts']):
                raise ProgressError('Unknown attempt sequence')
            attempt = state['attempts'][sequence-1]
            if attempt['state'] != 'reserved':
                raise ProgressError('Attempt already completed')
            case = self._case(attempt['variant'], attempt['case_index'])
            if (hashlib.sha256(row['id'].encode()).hexdigest() != case['id_sha256']
                    or row['sample_sha256'] != case['sample_sha256']):
                raise ProgressError('Result does not match the admitted case')
            key = attempt['variant']+':'+str(attempt['case_index'])
            if key in state['results']:
                raise ProgressError('A completed result cannot be replaced')
            attempt['state'] = 'completed'
            state['results'][key] = {'attempt_sequence': sequence, 'row': row,
                                     'row_sha256': digest(row)}
            self._write(state)

    def authorize_resource_retry(self, sequence, controller):
        if (not controller.get('terminal') or controller.get('status') != 'failed'
                or not controller.get('own_GPU_context_absent')
                or controller['shutdown']['remaining_owned_processes']):
            raise ProgressError('Prior supervisor is not stopped and cleaned')
        phases = controller.get('phases', [])
        last = phases[-1] if phases else {}
        guard = last.get('guard_reason')
        if guard not in self.RESOURCE_GUARDS or last.get('phase') != controller['variant']:
            raise ProgressError('Only a resource-guard interruption may authorize retry')
        with self.lock():
            state = self._read()
            if type(sequence) is not int or not 1 <= sequence <= len(state['attempts']):
                raise ProgressError('Unknown attempt sequence')
            attempt = state['attempts'][sequence-1]
            if controller['variant'] != attempt['variant'] or attempt['state'] != 'reserved':
                raise ProgressError('Supervisor does not match the unknown attempt')
            if attempt.get('retry_permission'):
                raise ProgressError('Retry authorization already recorded')
            attempt['retry_permission'] = {'guard': guard,
                                           'controller_sha256': digest(controller)}
            self._write(state)

    def record_import(self, evidence):
        with self.lock():
            state = self._read()
            if evidence in state['imports']:
                raise ProgressError('Import already recorded')
            state['imports'].append(evidence); self._write(state)
