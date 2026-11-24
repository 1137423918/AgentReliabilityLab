"""Append-only charging and clean-boundary admission for segmented training.

A running/failed segment is never resumed. Unknown forward/backward/update
dispatches remain charged; only a clean completed segment permits continuation.
"""
from __future__ import annotations
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
from benchmarks.training_checkpoint import fsync_dir


def packed(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(packed(value)).hexdigest()


def transition(state, event, definition):
    kind = event['kind']; data = event['data']
    if kind == 'initialized':
        assert not state and data == definition
        return {'status': 'idle', 'next_segment': 0, 'updates': 0, 'checkpoint': None,
                'forward_reserved': 0, 'forward_completed': 0, 'backward_reserved': 0,
                'backward_completed': 0, 'optimizer_reserved': 0, 'optimizer_completed': 0,
                'pending': None, 'active_update': None, 'last_forward': None, 'backward_forwards': []}
    assert state
    if kind == 'segment_begin':
        assert state['status'] in ['idle', 'clean'] and data['index'] == state['next_segment']
        segment = definition['segments'][data['index']]
        assert state['updates'] == segment['start'] and state['pending'] is None and state['active_update'] is None
        state.update(status='running', segment_start_forwards=state['forward_reserved'])
    elif kind == 'forward_reserved':
        assert state['status'] == 'running' and state['pending'] is None
        assert state['forward_reserved'] < definition['forward_cap']
        assert data['phase'] in ['canary_standard', 'canary_sparse', 'training']
        if data['phase'] == 'training': assert state['active_update'] == data['update']
        else: assert state['active_update'] is None
        state['forward_reserved'] += 1; state['pending'] = {'kind': 'forward', **data, 'sequence': state['forward_reserved']}
    elif kind == 'forward_completed':
        pending = state['pending']; assert pending and pending['kind'] == 'forward' and data['sequence'] == pending['sequence']
        state['forward_completed'] += 1; state['last_forward'] = pending; state['pending'] = None
    elif kind == 'update_begin':
        assert state['status'] == 'running' and state['pending'] is None and state['active_update'] is None
        assert data['update'] == state['updates']+1 <= definition['segments'][state['next_segment']]['end']
        state['active_update'] = data['update']
    elif kind == 'backward_reserved':
        previous = state['last_forward']
        assert state['status'] == 'running' and state['pending'] is None and previous
        assert previous['phase'] == 'training' and previous['update'] == state['active_update']
        assert data['forward_sequence'] == previous['sequence'] and previous['sequence'] not in state['backward_forwards']
        state['backward_forwards'].append(previous['sequence']); state['backward_reserved'] += 1
        state['pending'] = {'kind': 'backward', **data}
    elif kind == 'backward_completed':
        pending = state['pending']; assert pending and pending['kind'] == 'backward' and data == {k: v for k, v in pending.items() if k != 'kind'}
        state['backward_completed'] += 1; state['pending'] = None
    elif kind == 'optimizer_reserved':
        assert state['status'] == 'running' and state['pending'] is None
        assert data['update'] == state['active_update'] == state['updates']+1
        assert state['optimizer_reserved'] < definition['optimizer_cap']
        state['optimizer_reserved'] += 1; state['pending'] = {'kind': 'optimizer', **data}
    elif kind == 'optimizer_completed':
        pending = state['pending']; assert pending and pending['kind'] == 'optimizer' and data['update'] == pending['update']
        state['updates'] = data['update']; state['optimizer_completed'] += 1; state['pending'] = None; state['active_update'] = None
    elif kind == 'checkpoint_committed':
        assert state['status'] == 'running' and state['pending'] is None and state['active_update'] is None
        assert data['completed_optimizer_updates'] == state['updates']
        assert set(data) == {'directory', 'manifest_sha256', 'completed_optimizer_updates'}
        assert Path(data['directory']).name == data['directory'] and len(data['manifest_sha256']) == 64
        state['checkpoint'] = data
    elif kind == 'segment_clean':
        segment = definition['segments'][state['next_segment']]
        assert state['status'] == 'running' and state['pending'] is None and state['active_update'] is None
        assert state['checkpoint'] and state['checkpoint']['completed_optimizer_updates'] == state['updates'] == segment['end']
        assert state['forward_reserved']-state['segment_start_forwards'] == segment['forwards']
        assert state['forward_reserved'] == state['forward_completed']
        assert state['backward_reserved'] == state['backward_completed']
        assert state['optimizer_reserved'] == state['optimizer_completed'] == state['updates']
        state.update(status='clean', next_segment=state['next_segment']+1)
    elif kind == 'failed':
        assert state['status'] == 'running'; state['status'] = 'failed'
    else:
        raise AssertionError('Unknown event: '+kind)
    return state


class TrainingJournal:
    def __init__(self, directory, definition):
        self.directory = Path(directory); self.directory.mkdir(parents=True, exist_ok=True)
        fsync_dir(self.directory.parent)
        self.lock = (self.directory/'run.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.path = self.directory/'events.jsonl'; self.definition = definition
            self.owner = digest(definition); self.state = {}; self.length = 0; self.tail = '0'*64
            assert definition['segments'] and definition['segments'][0]['start'] == 0
            for previous, current in zip(definition['segments'], definition['segments'][1:]): assert previous['end'] == current['start']
            assert all(s['end'] > s['start'] and s['forwards'] > 0 for s in definition['segments'])
            assert sum(s['forwards'] for s in definition['segments']) == definition['forward_cap']
            assert definition['segments'][-1]['end'] == definition['optimizer_cap']
            if self.path.exists():
                raw = self.path.read_bytes(); assert raw and raw.endswith(b'\n'), 'Partial journal is unknown, never replay'
                for line in raw.splitlines():
                    event = json.loads(line); hashed = event.pop('sha256')
                    assert event['owner'] == self.owner and event['previous'] == self.tail and event['sequence'] == self.length
                    assert digest(event) == hashed
                    self.state = transition(self.state, event, definition); self.tail = hashed; self.length += 1
            else:
                self.event('initialized', definition)
        except BaseException:
            self.lock.close(); raise

    def snapshot(self):
        return copy.deepcopy(self.state)

    def event(self, kind, data=None):
        assert not self.lock.closed
        record = {'owner': self.owner, 'sequence': self.length, 'previous': self.tail, 'kind': kind, 'data': data or {}}
        candidate = transition(copy.deepcopy(self.state), record, self.definition)
        hashed = digest(record); record['sha256'] = hashed
        with self.path.open('ab') as stream:
            stream.write(packed(record)+b'\n'); stream.flush(); os.fsync(stream.fileno())
        if self.length == 0:
            fsync_dir(self.directory)
        self.state = candidate; self.tail = hashed; self.length += 1
        return self.snapshot()

    def close(self):
        self.lock.close()
