"""Controls for complete-cohort gating and paired diagnostic accounting."""
import unittest
from benchmarks.score_bfcl_generation import paired, require_complete, summarize, ROLES


def row(index, valid, category='live_simple', **flags):
    return {'id': str(index), 'category': category,
        'score': {'guarded_valid': valid, 'guard_rejected': False, 'decode_success': True,
                  'explicit_empty_call_list': False, 'eval_attempts': 0, **flags}}


class ScoringControls(unittest.TestCase):
    def test_partial_cohort_cannot_be_scored(self):
        definition = {'variants': ROLES, 'cases': [None]*250}
        state = {'results': {role+':'+str(i): {} for role in ROLES for i in range(1, 251)}}
        require_complete(state, definition)
        state['results'].pop('masked32:250')
        with self.assertRaises(AssertionError):
            require_complete(state, definition)

    def test_undefined_infrastructure_error_keeps_full_denominator(self):
        result = summarize([row(1, True), row(2, None, scorer_error_type='KeyError')])
        self.assertEqual(result['cases'], 2)
        self.assertEqual(result['observed_successes'], 1)
        self.assertEqual(result['undefined_cases'], 1)
        self.assertIsNone(result['accuracy'])

    def test_irrelevance_parse_failure_credit_is_visible(self):
        result = summarize([row(1, True, 'irrelevance', decode_success=False)])
        self.assertEqual(result['accuracy'], 1)
        self.assertEqual(result['irrelevance_credit_with_decode_failure'], 1)
        self.assertEqual(result['decoder_failure_after_guard'], 1)
        self.assertEqual(result['explicit_empty_call_list'], 0)

    def test_guard_rejection_is_separate_from_decoder_failure(self):
        result = summarize([row(1, False, guard_rejected=True, decode_success=False)])
        self.assertEqual(result['accuracy'], 0)
        self.assertEqual(result['guard_rejected'], 1)
        self.assertEqual(result['decoder_failure_after_guard'], 0)

    def test_paired_changes_and_exact_test(self):
        left = [row(i, False) for i in range(4)]
        right = [row(i, True) for i in range(4)]
        result = paired(left, right)
        self.assertEqual(result['right_only'], 4)
        self.assertEqual(result['accuracy_difference_right_minus_left'], 1)
        self.assertEqual(result['exact_two_sided_McNemar_p'], .125)

    def test_paired_undefined_is_not_dropped_or_scored_false(self):
        result = paired([row(1, None)], [row(1, True)])
        self.assertEqual(result['undefined_pairs'], 1)
        self.assertEqual(result['cases'], 1)
        self.assertIsNone(result['accuracy_difference_right_minus_left'])
        self.assertIsNone(result['exact_two_sided_McNemar_p'])
        with self.assertRaises(AssertionError):
            paired([row(1, False)], [row(2, True)])


if __name__ == '__main__':
    unittest.main()
