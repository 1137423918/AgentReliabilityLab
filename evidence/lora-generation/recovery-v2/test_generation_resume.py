"""CPU integration controls for legacy import and the evaluator's cache dispatch."""
from pathlib import Path
import copy
import hashlib
import json
import sys
import tempfile
import unittest

MODULES = Path(__file__).resolve().parents[2]/'benchmarks'
sys.path.insert(0, str(MODULES))
from generation_progress import GenerationProgress, ProgressError, digest
from generation_resume import import_legacy_profile, packed, request_fingerprint, result_for_case


class ResumeControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='agentlab-resume-control-')
        self.root = Path(self.temp.name); self.calls = []
        settings = {'max_context': 32768, 'max_new_tokens': 1024, 'temperature': 0,
                    'seed': 42, 'batch_size': 1, 'dtype': 'float16'}
        self.admission = {'data_sha256': digest('data'), 'runner_sha256': digest('runner'),
                          'scorer_sha256': digest('scorer'), 'cases': []}
        for i in range(1, 4):
            messages = [{'role': 'user', 'content': 'case%d'%i}]; ids = [10, i, 12]
            self.admission['cases'].append({'id': 'case%d'%i, 'input_tokens': 3,
                'sample_sha256': digest(['sample', i]), 'messages_sha256': digest(messages),
                'prompt_token_ids_sha256': digest(ids)})
        self.definition = {'variants': ['base', 'full32', 'mixed32'], 'settings': settings,
            'model_repository': 'fixed-model', 'model_revision': 'fixed-revision',
            'legacy_driver_sha256': digest('driver'), 'legacy_protocol_sha256': digest('protocol'),
            'data_sha256': self.admission['data_sha256'],
            'models': {v: {'adapter_artifact_sha256': {}} for v in ['base', 'full32', 'mixed32']},
            'cases': [{'id_sha256': hashlib.sha256(c['id'].encode()).hexdigest(),
                       'sample_sha256': c['sample_sha256'],
                       'request_sha256': request_fingerprint(c, settings)} for c in self.admission['cases']],
            'limits': {'total_attempts': 12, 'variant_attempts': 5, 'case_attempts': 3}}
        self.sources = [self.source('base', 3, False), self.source('full32', 1, True)]

    def tearDown(self):
        self.temp.cleanup()

    def source(self, variant, count, unknown):
        folder = self.root/variant; folder.mkdir(); events = []; rows = []
        for i in range(1, count+int(unknown)+1):
            c = self.admission['cases'][i-1]
            events.append({'event': 'reserved', 'sequence': i, 'case': c['id'],
                           'messages': [{'role': 'user', 'content': c['id']}], 'prompt_token_ids': [10, i, 12]})
            if i > count: continue
            meta = {'sequence': i, 'case': c['id'], 'input_tokens': 3, 'ended_with_eos': True}
            events.append({'event': 'completed', **meta, 'raw_output': 'stored%d'%i,
                           'generated_token_ids': [20, i]})
            rows.append({'id': c['id'], 'sample_sha256': c['sample_sha256'],
                         'prediction': {'raw_output': 'stored%d'%i, 'tool_calls': [], 'error': None},
                         'official_score': {'correct': False, 'score': 0.0}, 'generation_metadata': meta})
        controller = {'terminal': True, 'status': 'failed' if unknown else 'completed', 'variant': variant,
            'protocol_sha256': self.definition['legacy_protocol_sha256'], 'source_and_inputs_unchanged': True,
            'own_GPU_context_absent': True, 'shutdown': {'remaining_owned_processes': []},
            'phases': [{'phase': variant, 'guard_reason': 'foreign_compute_client' if unknown else None}],
            'local_generation_ledger': {'reserved': count+int(unknown), 'completed': count,
                                        'unknown_still_charged': int(unknown)}}
        model = {'model_repository': 'fixed-model', 'model_revision': 'fixed-revision',
            'data_sha256': self.admission['data_sha256'], 'runner_sha256': self.admission['runner_sha256'],
            'scorer_sha256': self.admission['scorer_sha256'], 'driver_sha256': self.definition['legacy_driver_sha256'],
            'completed_cases': count, 'input_tokens': count*3, 'generated_token_ids': count*2,
            'adapter_used': False, **self.definition['settings']}
        paths = {'controller': str(folder/'controller.json'), 'report.json': str(folder/'report.json'),
                 'calls.jsonl': str(folder/'calls.jsonl'), 'predictions.jsonl': str(folder/'predictions.jsonl')}
        Path(paths['controller']).write_text(json.dumps(controller)); Path(paths['report.json']).write_text(json.dumps(model))
        for name, data in [('calls.jsonl', events), ('predictions.jsonl', rows)]:
            Path(paths[name]).write_text(''.join(json.dumps(r)+'\n' for r in data))
        return {'variant': variant, 'paths': paths,
                'sha256': {n: hashlib.sha256(Path(p).read_bytes()).hexdigest() for n, p in paths.items()}}

    def test_import_reuses_all_scores_and_preserves_unknown_and_fingerprints(self):
        p = import_legacy_profile(self.root/'state', self.definition, self.admission, self.sources)
        state = p.snapshot(); self.assertEqual(len(state['attempts']), 5); self.assertEqual(len(state['results']), 4)
        self.assertEqual(state['attempts'][-1]['state'], 'reserved')
        self.assertEqual(state['attempts'][-1]['retry_permission']['guard'], 'foreign_compute_client')
        self.assertFalse(p.cached('full32', 1)['official_score']['correct'])
        self.assertEqual(p.cached('full32', 1)['progress_metadata']['generated_token_count'], 2)
        again = import_legacy_profile(self.root/'state', self.definition, self.admission, self.sources)
        self.assertEqual(again.snapshot(), state)

    def test_actual_dispatch_skips_cached_zero_score_and_commits_pending_once(self):
        p = import_legacy_profile(self.root/'state', self.definition, self.admission, self.sources)
        def forbidden(): self.fail('Cached model/scorer callback was replayed')
        result, cached = result_for_case(p, 'full32', 1, self.admission['cases'][0], forbidden)
        self.assertTrue(cached); self.assertFalse(result['official_score']['correct'])
        def evaluate():
            self.calls.append('generate-and-score')
            sequence = p.reserve('full32', 2, self.definition['cases'][1]['request_sha256'])
            c = self.admission['cases'][1]
            return {'id': c['id'], 'sample_sha256': c['sample_sha256'],
                    'official_score': {'correct': True, 'score': 1.0},
                    'progress_metadata': {'attempt_sequence': sequence}}
        result, cached = result_for_case(p, 'full32', 2, self.admission['cases'][1], evaluate)
        self.assertFalse(cached); self.assertEqual(self.calls, ['generate-and-score'])
        self.assertEqual(len(p.snapshot()['attempts']), 6)
        self.assertEqual(result_for_case(p, 'full32', 2, self.admission['cases'][1], forbidden), (result, True))
        self.assertEqual(p.snapshot()['attempts'][4]['state'], 'reserved')

    def test_changed_private_wire_or_definition_is_rejected_before_import(self):
        source = self.sources[1]; path = Path(source['paths']['calls.jsonl']); path.write_text(path.read_text()+'\n')
        with self.assertRaises(ProgressError):
            import_legacy_profile(self.root/'state', self.definition, self.admission, self.sources)
        self.assertFalse((self.root/'state').exists())

    def test_model_setting_or_case_change_cannot_reuse_legacy_results(self):
        for change in ['model_revision', 'settings', 'cases']:
            altered = copy.deepcopy(self.definition)
            if change == 'model_revision': altered[change] = 'different-model'
            elif change == 'settings': altered[change]['max_new_tokens'] = 8
            else: altered['cases'][0]['id_sha256'] = '0'*64
            with self.subTest(change=change), self.assertRaises(ProgressError):
                import_legacy_profile(self.root/('state-'+change), altered, self.admission, self.sources)


if __name__ == '__main__':
    unittest.main(verbosity=2)
