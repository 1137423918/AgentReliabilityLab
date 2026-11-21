"""Protect report comparisons against misleading results and dataset changes."""
import copy
import unittest

from audit import run_case
from compare import compare


def report(passed):
    return {'scope': 'unit', 'cases_sha256': 'same-hash', 'results': [
        {'id': 'canonical', 'input': 'a', 'expected': {'value': '/a'}, 'passed': passed}]}


class EvidenceTests(unittest.TestCase):
    def test_detects_fixed_behavior(self):
        result = compare(report(False), report(True))
        self.assertEqual(result['fixed'], ['canonical'])
        self.assertEqual(result['regressed'], [])

    def test_detects_regression(self):
        result = compare(report(True), report(False))
        self.assertEqual(result['regressed'], ['canonical'])
        self.assertEqual(result['remaining_failures'], ['canonical'])

    def test_rejects_different_case_sets(self):
        candidate = report(True)
        candidate['cases_sha256'] = 'different'
        with self.assertRaisesRegex(ValueError, 'Case sets differ'):
            compare(report(False), candidate)

    def test_rejects_different_cases_under_same_hash(self):
        candidate = report(True)
        candidate['results'][0]['input'] = 'b'
        with self.assertRaisesRegex(ValueError, 'Case content differs'):
            compare(report(False), candidate)

    def test_rejects_missing_result(self):
        candidate = report(True)
        candidate['results'] = []
        with self.assertRaisesRegex(ValueError, 'Result IDs differ'):
            compare(report(False), candidate)

    def test_rejects_duplicate_result(self):
        candidate = report(True)
        candidate['results'].append(copy.deepcopy(candidate['results'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate result IDs'):
            compare(report(False), candidate)

    def test_does_not_hide_unexpected_exceptions_as_expected_value_error(self):
        def broken(path):
            raise RuntimeError('tool crashed')
        case = {'id': 'bad', 'input': '../', 'expected': {'error': 'ValueError'}}
        result = run_case(broken, case)
        self.assertFalse(result['passed'])
        self.assertEqual(result['observed']['unexpected_error'], 'RuntimeError')

    def test_accepts_explicit_expected_value_error(self):
        def rejects(path):
            raise ValueError('invalid path')
        result = run_case(rejects, {'id': 'bad', 'input': '../', 'expected': {'error': 'ValueError'}})
        self.assertTrue(result['passed'])


if __name__ == '__main__':
    unittest.main()
