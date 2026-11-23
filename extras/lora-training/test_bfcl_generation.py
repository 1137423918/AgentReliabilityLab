import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from benchmarks.bfcl_generation import (SETTINGS, canonical_base_name, generate_segment,
                                      request_digest)
from benchmarks.generation_progress import GenerationProgress, ProgressError, digest


def fixture(root, count=3):
    rows = []
    for i in range(count):
        row = {'id': str(i), 'category': 'live_simple', 'sample_sha256': digest(['sample', i]),
               'prompt_sha256': digest(['message', i]), 'input_ids': [1, i+2], 'prompt_tokens': 2}
        row['prompt_token_ids_sha256'] = digest(row['input_ids'])
        row['request_sha256'] = request_digest(row, SETTINGS)
        rows.append(row)
    definition = {'variants': ['base', 'reference32', 'masked32'], 'settings': SETTINGS,
                  'cases': [{'id_sha256': hashlib.sha256(r['id'].encode()).hexdigest(),
                             'sample_sha256': r['sample_sha256'], 'request_sha256': r['request_sha256']}
                            for r in rows],
                  'limits': {'total_attempts': 30, 'variant_attempts': 10, 'case_attempts': 2}}
    return GenerationProgress(root/'progress', definition, create=True), rows


def payload(text='invalid Python stays final'):
    return {'raw_output': text, 'generated_token_ids': [4, 5],
            'metadata': {'ended_with_eos': True}}


class GenerationAdapterTests(unittest.TestCase):
    def test_reservation_precedes_callback_and_bad_outputs_are_cached(self):
        with tempfile.TemporaryDirectory() as d:
            progress, rows = fixture(Path(d))
            calls = []
            def generate(row, seq):
                self.assertEqual(progress.snapshot()['attempts'][seq-1]['state'], 'reserved')
                calls.append(row['id'])
                return payload()
            result = generate_segment(progress, 'base', rows, generate)
            self.assertTrue(result['all_cases_completed'])
            again = generate_segment(progress, 'base', rows,
                                     lambda *x: self.fail('Completed bad outputs cannot regenerate'))
            self.assertEqual(again['new_model_calls'], 0)
            self.assertEqual(calls, ['0', '1', '2'])

    def test_cooperative_chunks_keep_whole_cohort(self):
        with tempfile.TemporaryDirectory() as d:
            progress, rows = fixture(Path(d))
            first = generate_segment(progress, 'base', rows, lambda *x: payload(), max_new_cases=1)
            self.assertFalse(first['all_cases_completed'])
            self.assertEqual(first['variant_committed_cases'], 1)
            second = generate_segment(progress, 'base', rows, lambda *x: payload())
            self.assertTrue(second['all_cases_completed'])
            self.assertEqual(second['new_model_calls'], 2)
            self.assertEqual(len(progress.snapshot()['attempts']), 3)

    def test_deadline_never_reserves_an_unstarted_case(self):
        with tempfile.TemporaryDirectory() as d:
            progress, rows = fixture(Path(d))
            result = generate_segment(progress, 'base', rows, lambda *x: self.fail('Too late'),
                                      deadline=100, clock=lambda: 0)
            self.assertEqual(result['new_model_calls'], 0)
            self.assertFalse(progress.snapshot()['attempts'])

    def test_unknown_stays_charged_and_requires_stopped_resource_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            progress, rows = fixture(Path(d), 1)
            def interrupted(*args):
                raise RuntimeError('synthetic interruption after reservation')
            with self.assertRaises(RuntimeError):
                generate_segment(progress, 'base', rows, interrupted)
            with self.assertRaises(ProgressError):
                generate_segment(progress, 'base', rows, lambda *x: self.fail('Unapproved retry'))
            evidence = {'terminal': True, 'status': 'failed', 'variant': 'base',
                        'own_GPU_context_absent': True, 'shutdown': {'remaining_owned_processes': []},
                        'phases': [{'phase': 'base', 'guard_reason': 'foreign_compute_client'}]}
            progress.authorize_resource_retry(1, evidence)
            result = generate_segment(progress, 'base', rows, lambda *x: payload())
            self.assertEqual(result['total_attempts'], 2)
            self.assertEqual(result['unknown_still_charged'], 1)

    def test_changed_prompt_vector_fails_before_dispatch(self):
        with tempfile.TemporaryDirectory() as d:
            progress, rows = fixture(Path(d))
            changed = copy.deepcopy(rows)
            changed[0]['input_ids'][0] = 6
            with self.assertRaises(AssertionError):
                generate_segment(progress, 'base', changed, lambda *x: self.fail('Changed input'))
            self.assertFalse(progress.snapshot()['attempts'])

    def test_changed_inference_setting_fails_request_identity(self):
        with tempfile.TemporaryDirectory() as d:
            progress, rows = fixture(Path(d))
            progress.definition['settings'] = {**SETTINGS, 'max_new_tokens': 100}
            with self.assertRaises(AssertionError):
                generate_segment(progress, 'base', rows, lambda *x: self.fail('Changed setting'))

    def test_later_role_waits_for_complete_predecessor(self):
        with tempfile.TemporaryDirectory() as d:
            progress, rows = fixture(Path(d))
            with self.assertRaisesRegex(AssertionError, 'Previous role'):
                generate_segment(progress, 'reference32', rows, lambda *x: self.fail('Wrong role order'))

    def test_base_parameter_name_canonicalization(self):
        self.assertEqual(canonical_base_name('base_model.model.model.layers.0.self_attn.q_proj.base_layer.weight'),
                         canonical_base_name('model.layers.0.self_attn.q_proj.weight'))
        self.assertEqual(canonical_base_name('base_model.model.model.embed_tokens.weight'),
                         'model.embed_tokens.weight')


if __name__ == '__main__':
    unittest.main()
