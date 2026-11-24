"""Private, identity-bound model/optimizer/RNG snapshots for planned boundaries.

This does not authorize retrying an interrupted training update. The caller must
admit continuation from a clean, committed segment and keep compute accounting.
Only tensors and typed JSON are loaded; pickle and executable objects are unused.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import tempfile


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value, tensors, prefix='state'):
    import torch
    if torch.is_tensor(value):
        key = prefix+'.%06d'%len(tensors)
        tensors[key] = value.detach().cpu().clone().contiguous()
        return {'type': 'tensor', 'key': key}
    if isinstance(value, dict):
        return {'type': 'dict', 'items': [[encoded(k, tensors, prefix), encoded(v, tensors, prefix)] for k, v in value.items()]}
    if isinstance(value, (list, tuple)):
        return {'type': 'tuple' if isinstance(value, tuple) else 'list',
                'items': [encoded(v, tensors, prefix) for v in value]}
    assert value is None or type(value) in [str, int, float, bool], type(value)
    assert type(value) is not float or math.isfinite(value)
    return {'type': 'scalar', 'value': value}


def decoded(value, tensors, used):
    kind = value['type']
    if kind == 'tensor':
        key = value['key']; assert key in tensors and key not in used
        used.add(key)
        return tensors[key]
    if kind == 'dict':
        pairs = [(decoded(k, tensors, used), decoded(v, tensors, used)) for k, v in value['items']]
        result = dict(pairs); assert len(result) == len(pairs)
        return result
    if kind in ['list', 'tuple']:
        items = [decoded(v, tensors, used) for v in value['items']]
        return tuple(items) if kind == 'tuple' else items
    assert kind == 'scalar'
    result = value['value']
    assert result is None or type(result) in [str, int, float, bool]
    assert type(result) is not float or math.isfinite(result)
    return result


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_json(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def parameter_order(named):
    assert named and len({name for name, _ in named}) == len(named)
    return [{'name': name, 'shape': list(p.shape), 'dtype': str(p.dtype)} for name, p in named]


def commit_checkpoint(destination, named, optimizer, scaler, identity, counters, cuda_devices=()):
    """Commit a new snapshot atomically; an existing destination is never replaced."""
    import numpy as np
    import torch
    from safetensors.torch import save_file
    destination = Path(destination)
    assert not destination.exists() and not destination.is_symlink()
    assert identity and counters['completed_optimizer_updates'] >= 0
    assert list(cuda_devices) == list(range(len(cuda_devices))), 'Explicit local CUDA device order required'
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.'+destination.name+'-', dir=destination.parent))
    try:
        order = parameter_order(named)
        weights = {row['name']: p.detach().cpu().clone().contiguous() for row, (_, p) in zip(order, named)}
        save_file(weights, str(temporary/'parameters.safetensors'))
        numpy_state = np.random.get_state()
        state = {'optimizer': optimizer.state_dict(), 'scaler': scaler.state_dict(),
                 'torch_cpu_rng': torch.get_rng_state(),
                 'torch_cuda_rng': [torch.cuda.get_rng_state(device) for device in cuda_devices],
                 'python_rng': random.getstate(),
                 'numpy_rng': [numpy_state[0], torch.from_numpy(numpy_state[1].astype(np.int64)),
                               numpy_state[2], numpy_state[3], numpy_state[4]]}
        tensors = {}; tree = encoded(state, tensors)
        save_file(tensors, str(temporary/'state.safetensors'))
        metadata = {'schema': 1, 'identity': identity, 'counters': counters,
                    'parameter_order': order, 'cuda_devices': list(cuda_devices), 'state': tree}
        write_json(temporary/'state.json', metadata)
        files = {name: sha(temporary/name) for name in ['parameters.safetensors', 'state.safetensors', 'state.json']}
        for name in files:
            with (temporary/name).open('rb') as stream:
                os.fsync(stream.fileno())
        write_json(temporary/'manifest.json', {'schema': 1, 'files': files})
        fsync_dir(temporary)
        # The caller holds its run lock; refuse accidental overwrite under that contract.
        assert not destination.exists() and not destination.is_symlink()
        os.rename(temporary, destination); fsync_dir(destination.parent)
        return {'directory': destination.name, 'manifest_sha256': sha(destination/'manifest.json'),
                'completed_optimizer_updates': counters['completed_optimizer_updates']}
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def inspect_checkpoint(directory, expected_manifest_sha256, identity):
    directory = Path(directory)
    assert not directory.is_symlink() and directory.is_dir()
    assert not (directory/'manifest.json').is_symlink()
    assert sha(directory/'manifest.json') == expected_manifest_sha256
    manifest = json.loads((directory/'manifest.json').read_text())
    assert manifest['schema'] == 1
    assert set(manifest['files']) == {'parameters.safetensors', 'state.safetensors', 'state.json'}
    assert {p.name for p in directory.iterdir()} == set(manifest['files']) | {'manifest.json'}
    for name, expected in manifest['files'].items():
        assert not (directory/name).is_symlink() and sha(directory/name) == expected, name
    metadata = json.loads((directory/'state.json').read_text())
    assert metadata['schema'] == 1 and metadata['identity'] == identity, 'Checkpoint identity mismatch'
    return metadata


def restore_checkpoint(directory, expected_manifest_sha256, named, optimizer, scaler, identity, cuda_devices=()):
    """Validate before applying state, then restore all saved seeded RNG streams."""
    import numpy as np
    import torch
    from safetensors.torch import load_file
    directory = Path(directory)
    metadata = inspect_checkpoint(directory, expected_manifest_sha256, identity)
    assert metadata['parameter_order'] == parameter_order(named), 'Parameter name/order/shape/dtype changed'
    assert metadata['cuda_devices'] == list(cuda_devices)
    parameters = load_file(str(directory/'parameters.safetensors'), device='cpu')
    assert set(parameters) == {name for name, _ in named}
    for name, p in named:
        assert parameters[name].shape == p.shape and parameters[name].dtype == p.dtype
    tensors = load_file(str(directory/'state.safetensors'), device='cpu'); used = set()
    state = decoded(metadata['state'], tensors, used); assert used == set(tensors)
    assert set(state) == {'optimizer', 'scaler', 'torch_cpu_rng', 'torch_cuda_rng', 'python_rng', 'numpy_rng'}
    assert len(state['torch_cuda_rng']) == len(cuda_devices)
    assert state['torch_cpu_rng'].dtype == torch.uint8
    with torch.no_grad():
        for name, p in named:
            p.copy_(parameters[name])
    optimizer.load_state_dict(state['optimizer']); scaler.load_state_dict(state['scaler'])
    optimizer.zero_grad(set_to_none=True)
    numpy_state = state['numpy_rng']
    np.random.set_state((numpy_state[0], numpy_state[1].numpy().astype(np.uint32), *numpy_state[2:]))
    random.setstate(state['python_rng']); torch.set_rng_state(state['torch_cpu_rng'])
    for device, rng in zip(cuda_devices, state['torch_cuda_rng']):
        torch.cuda.set_rng_state(rng, device)
    return metadata['counters']
