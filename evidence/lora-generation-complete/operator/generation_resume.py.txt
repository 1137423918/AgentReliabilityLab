"""Import immutable generation evidence and reuse first committed case results."""
from pathlib import Path
import hashlib
import json
import math

try:
    from .generation_progress import GenerationProgress, ProgressError, digest
except ImportError:
    from generation_progress import GenerationProgress, ProgressError, digest


def packed(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def request_fingerprint(case, settings):
    return digest({'messages_sha256': case['messages_sha256'],
                   'prompt_token_ids_sha256': case['prompt_token_ids_sha256'],
                   'settings': settings})


def result_for_case(progress, variant, index, expected, evaluate):
    """Cached failures are final too; evaluate/scorer callbacks are never replayed."""
    if progress is not None:
        cached = progress.cached(variant, index)
        if cached is not None:
            if (cached['id'] != expected['id'] or cached['sample_sha256'] != expected['sample_sha256']):
                raise ProgressError('Cached row is not the admitted case')
            return cached, True
    row = evaluate()
    if progress is not None:
        progress.complete(row['progress_metadata']['attempt_sequence'], row)
    return row, False


def validate_legacy_source(source, admission, definition):
    """Validate stored scores against their original wire evidence, without rescoring."""
    for name, expected in source['sha256'].items():
        if sha_file(source['paths'][name]) != expected:
            raise ProgressError('Legacy evidence changed: '+name)
    controller = json.loads(Path(source['paths']['controller']).read_text())
    model = json.loads(Path(source['paths']['report.json']).read_text())
    rows = [json.loads(s) for s in Path(source['paths']['predictions.jsonl']).read_text().splitlines()]
    events = [json.loads(s) for s in Path(source['paths']['calls.jsonl']).read_text().splitlines()]
    reserved = {x['sequence']: x for x in events if x['event'] == 'reserved'}
    completed = {x['sequence']: x for x in events if x['event'] == 'completed'}
    if (not controller['terminal'] or controller['variant'] != source['variant']
            or not controller['own_GPU_context_absent'] or controller['shutdown']['remaining_owned_processes']
            or len(reserved)+len(completed) != len(events)
            or list(reserved) != list(range(1, len(reserved)+1))
            or list(completed) != list(range(1, len(completed)+1))
            or len(rows) != len(completed) or len(reserved)-len(completed) not in [0, 1]):
        raise ProgressError('Legacy segment is not stopped with a valid complete prefix')
    ledger = controller['local_generation_ledger']
    if ledger != {'reserved': len(reserved), 'completed': len(completed),
                  'unknown_still_charged': len(reserved)-len(completed)}:
        raise ProgressError('Legacy controller/journal counts disagree')
    if (model['data_sha256'] != admission['data_sha256']
            or model['model_repository'] != definition['model_repository']
            or model['model_revision'] != definition['model_revision']
            or model['completed_cases'] != len(rows)
            or model['driver_sha256'] != definition['legacy_driver_sha256']
            or controller['protocol_sha256'] != definition['legacy_protocol_sha256']
            or not controller['source_and_inputs_unchanged']
            or model['runner_sha256'] != admission['runner_sha256']
            or model['scorer_sha256'] != admission['scorer_sha256']):
        raise ProgressError('Legacy model/data identity mismatch')
    settings = definition['settings']
    for key in ['max_context', 'max_new_tokens', 'temperature', 'seed', 'batch_size', 'dtype']:
        if model[key] != settings[key]:
            raise ProgressError('Legacy inference setting changed: '+key)
    adapter = definition['models'][source['variant']]['adapter_artifact_sha256']
    if model['adapter_used'] != bool(adapter) or model.get('adapter_artifact_sha256', {}) != adapter:
        raise ProgressError('Legacy checkpoint identity changed')
    augmented = {}; input_tokens = generated_tokens = 0
    for i, row in enumerate(rows, 1):
        expected = admission['cases'][i-1]; r = reserved[i]; c = completed[i]
        m = row['generation_metadata']
        if (row['id'] != expected['id'] or row['id'] != r['case'] or row['id'] != c['case']
                or row['sample_sha256'] != expected['sample_sha256']
                or row['prediction']['error'] is not None
                or row['prediction']['raw_output'] != c['raw_output']
                or hashlib.sha256(packed(r['messages'])).hexdigest() != expected['messages_sha256']
                or hashlib.sha256(packed(r['prompt_token_ids'])).hexdigest() != expected['prompt_token_ids_sha256']
                or len(r['prompt_token_ids']) != expected['input_tokens']
                or m['sequence'] != i or any(m[k] != c[k] for k in m)):
            raise ProgressError('Legacy row/wire/admission mismatch')
        if any(k in row for k in ['progress_metadata']):
            raise ProgressError('Legacy row unexpectedly has recovery fields')
        if type(row['official_score']['correct']) is not bool or not math.isfinite(row['official_score']['score']):
            raise ProgressError('Invalid stored official score')
        count = len(c['generated_token_ids']); input_tokens += m['input_tokens']; generated_tokens += count
        augmented[i] = {**row, 'progress_metadata': {
            'variant': source['variant'], 'case_index': i, 'generated_token_count': count,
            'legacy_row_sha256': digest(row), 'wire_reserved_sha256': digest(r),
            'wire_completed_sha256': digest(c)}}
    if model['input_tokens'] != input_tokens or model['generated_token_ids'] != generated_tokens:
        raise ProgressError('Legacy token totals do not match durable completed rows')
    if len(reserved) > len(rows):
        i = len(reserved); r = reserved[i]; expected = admission['cases'][i-1]
        if (r['case'] != expected['id']
                or hashlib.sha256(packed(r['messages'])).hexdigest() != expected['messages_sha256']
                or hashlib.sha256(packed(r['prompt_token_ids'])).hexdigest() != expected['prompt_token_ids_sha256']):
            raise ProgressError('Unknown attempt is not the admitted next case')
    return controller, reserved, augmented


def import_legacy_profile(root, definition, admission, sources):
    """Resume an interrupted CPU import without resetting already charged attempts."""
    if (len(admission['cases']) != len(definition['cases'])
            or admission['data_sha256'] != definition['data_sha256']):
        raise ProgressError('Admission definition changed')
    for actual, expected in zip(admission['cases'], definition['cases']):
        if (hashlib.sha256(actual['id'].encode()).hexdigest() != expected['id_sha256']
                or actual['sample_sha256'] != expected['sample_sha256']
                or request_fingerprint(actual, definition['settings']) != expected['request_sha256']):
            raise ProgressError('Admission case fingerprint changed')
    validated = [validate_legacy_source(s, admission, definition) for s in sources]
    progress = GenerationProgress(root, definition, create=not Path(root).exists())
    seq = 0; unknown = []
    for source, (controller, reserved, rows) in zip(sources, validated):
        variant = source['variant']
        for index in reserved:
            seq += 1; request = definition['cases'][index-1]['request_sha256']
            state = progress.snapshot()
            if len(state['attempts']) < seq:
                if len(state['attempts']) != seq-1 or progress.reserve(variant, index, request) != seq:
                    raise ProgressError('Legacy import order changed')
            attempt = progress.snapshot()['attempts'][seq-1]
            if (attempt['variant'] != variant or attempt['case_index'] != index
                    or attempt['request_sha256'] != request):
                raise ProgressError('Existing import attempt differs from source')
            if index in rows:
                row = rows[index]; row['progress_metadata']['attempt_sequence'] = seq
                if attempt['state'] == 'reserved':
                    progress.complete(seq, row)
                elif progress.cached(variant, index) != row:
                    raise ProgressError('Existing imported result differs')
            else:
                if attempt['state'] != 'reserved':
                    raise ProgressError('Unknown legacy attempt was replaced')
                unknown.append((seq, controller))
        evidence = {'variant': variant, 'source_sha256': source['sha256']}
        if evidence not in progress.snapshot()['imports']:
            progress.record_import(evidence)
    if len(progress.snapshot()['attempts']) != seq:
        raise ProgressError('Journal already contains work beyond this legacy import')
    for sequence, controller in unknown:
        permission = progress.snapshot()['attempts'][sequence-1].get('retry_permission')
        if permission is None:
            progress.authorize_resource_retry(sequence, controller)
        elif permission['controller_sha256'] != digest(controller):
            raise ProgressError('Retry permission bound to a different stopped segment')
    return progress
