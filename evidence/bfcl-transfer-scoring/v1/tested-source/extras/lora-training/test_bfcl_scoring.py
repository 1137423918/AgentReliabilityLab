import copy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest

from benchmarks.bfcl_transfer_scoring import (GuardRejected, canonical_witness,
                                               guard_python_response, load_python_scorer)


class GuardedScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(os.environ['BFCL_SCORER_SOURCE'])
        cls.score, cls.identity = load_python_scorer(cls.source)

    @staticmethod
    def row():
        return {'id': 'fixture_1', 'function': [
            {'name': 'fn', 'parameters': {'type': 'dict', 'properties': {
                'x': {'type': 'integer'}}, 'required': ['x']}}]}

    def evaluate(self, raw, row=None, gold=None, category='live_simple'):
        return type(self).score(raw, row or self.row(), gold or [{'fn': {'x': [3]}}], category)

    def test_literal_correct_and_input_unchanged(self):
        row = self.row()
        gold = [{'fn': {'x': [3]}}]
        before = copy.deepcopy([row, gold])
        result = self.evaluate('[fn(x=3)]', row, gold)
        self.assertTrue(result['guarded_valid'])
        self.assertEqual(result['eval_attempts'], 0)
        self.assertEqual([row, gold], before)

    def test_wrong_name_required_extra_and_type_are_rejected(self):
        for raw in ['[other(x=3)]', '[fn()]', '[fn(x=3,y=4)]',
                    '[fn(x="3")]', '[fn(x=True)]', '[fn(3)]']:
            with self.subTest(raw=raw):
                result = self.evaluate(raw)
                self.assertFalse(result['guarded_valid'])
                self.assertNotIn('scorer_error_type', result)

    def test_parallel_order_is_ignored(self):
        row = self.row()
        row['function'].append({'name': 'gn', 'parameters': {'type': 'dict',
            'properties': {'n': {'type': 'integer'}}, 'required': ['n']}})
        gold = [{'fn': {'x': [3]}}, {'gn': {'n': [8]}}]
        self.assertTrue(self.evaluate('[gn(n=8),fn(x=3)]', row, gold, 'parallel')['guarded_valid'])
        self.assertFalse(self.evaluate('[fn(x=3),fn(x=3)]', row, gold, 'parallel')['guarded_valid'])
        self.assertFalse(self.evaluate('[fn(x=3)]', row, gold, 'parallel')['guarded_valid'])

    def test_multiple_selects_correct_function(self):
        row = self.row()
        row['function'].append({'name': 'gn', 'parameters': {'type': 'dict',
            'properties': {'n': {'type': 'integer'}}, 'required': ['n']}})
        gold = [{'gn': {'n': [8]}}]
        self.assertTrue(self.evaluate('[gn(n=8)]', row, gold, 'live_multiple')['guarded_valid'])
        self.assertFalse(self.evaluate('[fn(x=3)]', row, gold, 'live_multiple')['guarded_valid'])

    def test_dotted_function_names_are_preserved(self):
        row = self.row()
        row['function'][0]['name'] = 'api.fn'
        gold = [{'api.fn': {'x': [3]}}]
        self.assertTrue(self.evaluate('[api.fn(x=3)]', row, gold)['guarded_valid'])
        self.assertFalse(self.evaluate('[api_fn(x=3)]', row, gold)['guarded_valid'])

    def test_irrelevance_keeps_parse_failure_boundary_visible(self):
        empty = self.evaluate('[]', category='irrelevance')
        prose = self.evaluate('No suitable tool.', category='irrelevance')
        call = self.evaluate('[fn(x=3)]', category='irrelevance')
        self.assertTrue(empty['guarded_valid'] and empty['explicit_empty_call_list'])
        self.assertTrue(prose['guarded_valid'])
        self.assertFalse(prose['decode_success'])
        self.assertIsNotNone(prose['decode_error_type'])
        self.assertFalse(call['guarded_valid'])

    def test_eval_bearing_expressions_never_gain_credit(self):
        for category in ['live_simple', 'irrelevance']:
            for raw in ['[fn(x=1+2)]', '[fn(x=lambda y: y)]']:
                result = self.evaluate(raw, category=category)
                self.assertFalse(result['guarded_valid'])
                self.assertTrue(result['guard_rejected'])
                self.assertIsNone(result['upstream_python_case_valid'])
                self.assertEqual(result['eval_attempts'], 0)

    def test_generated_calls_are_never_executed(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d)/'must-not-exist'
            raw = '[fn(x=__import__("pathlib").Path('+repr(str(marker))+').write_text("bad"))]'
            result = self.evaluate(raw)
            self.assertFalse(result['guarded_valid'])
            self.assertFalse(marker.exists())
            self.assertEqual(result['eval_attempts'], 0)

    def test_resource_guards_fail_closed(self):
        for raw, kwargs in [('x'*65537, {}), ('[fn(x=3)]', {'max_nodes': 3}),
                            ('[fn(x=[[3]])]', {'max_depth': 2})]:
            with self.assertRaises(GuardRejected):
                guard_python_response(raw, **kwargs)

    def test_legacy_decoder_wrapping_is_preserved(self):
        self.assertTrue(self.evaluate('fn(x=3)')['guarded_valid'])
        self.assertTrue(self.evaluate('```\n[fn(x=3)]\n```')['guarded_valid'])
        self.assertFalse(self.evaluate('```python\n[fn(x=3)]\n```')['guarded_valid'])

    def test_reference_witness_is_only_a_checker_control(self):
        gold = [{'fn': {'x': [3], 'unused': ['']}}]
        raw = canonical_witness(gold)
        self.assertEqual(raw, '[fn(x=3)]')
        self.assertTrue(self.evaluate(raw, gold=gold)['guarded_valid'])

    def test_source_and_definition_identity_recorded(self):
        self.assertEqual(len(self.identity), 5)
        for name, record in self.identity.items():
            self.assertEqual(record['source_sha256'], hashlib.sha256((self.source/name).read_bytes()).hexdigest())
            self.assertTrue(record['definitions'])


if __name__ == '__main__':
    unittest.main()
