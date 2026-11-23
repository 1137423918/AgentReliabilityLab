"""Data-integrity and nonsemantic-scaffold masking controls; CPU only."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from benchmarks.audit_toolrl_alignment import constant_reason_span, digest, mask_constant_offsets, validate_progress


class AlignmentControls(unittest.TestCase):
    def test_only_exact_leading_reason_is_selected(self):
        answer = '<think>  fixed reasoning  </think><response>fixed reasoning</response>'
        span = constant_reason_span(answer, {'fixed reasoning'})
        self.assertEqual(answer[slice(*span)], 'fixed reasoning')
        self.assertLess(span[1], answer.index('</think>'))

    def test_variable_reasoning_is_retained(self):
        self.assertIsNone(constant_reason_span('<think>specific reasoning</think>', {'fixed reasoning'}))

    def test_later_constant_text_is_not_selected(self):
        self.assertIsNone(constant_reason_span('<response>fixed reasoning</response>', {'fixed reasoning'}))

    def test_unterminated_reason_is_not_selected(self):
        self.assertIsNone(constant_reason_span('<think>fixed reasoning', {'fixed reasoning'}))

    def test_tokens_crossing_span_boundaries_are_retained(self):
        original = [-100, 11, 12, 13, 14]
        offsets = [(0, 1), (1, 4), (4, 6), (6, 8), (8, 11)]
        self.assertEqual(mask_constant_offsets(original, offsets, (3, 9)), [-100, 11, -100, -100, 14])
        self.assertEqual(original, [-100, 11, 12, 13, 14])

    def test_missing_span_leaves_all_labels_unchanged(self):
        self.assertEqual(mask_constant_offsets([-100, 12], [(0, 1), (1, 2)], None), [-100, 12])

    def state(self):
        row = {'prediction': {'tool_calls': []}, 'official_score': {'correct': False}}
        value = {'version': 1, 'owner_sha256': 'owner', 'imports': [],
                 'attempts': [{'sequence': 1, 'variant': 'base', 'case_index': 1, 'state': 'reserved',
                               'retry_permission': {'guard': 'foreign_compute_client', 'controller_sha256': 'a'*64}},
                              {'sequence': 2, 'variant': 'base', 'case_index': 1, 'state': 'completed'}],
                 'results': {'base:1': {'attempt_sequence': 2, 'row': row, 'row_sha256': digest(row)}}}
        expected = {'owner_sha256': 'owner', 'attempts': 2, 'known_by_variant': {'base': 1}, 'unknown_still_charged': 1}
        return value, expected

    def raw(self, value):
        return json.dumps({**value, 'checksum': digest(value)}).encode()

    def test_unknown_attempt_stays_charged(self):
        value, expected = self.state()
        result = validate_progress(self.raw(value), expected)
        self.assertEqual(len(result['attempts']), 2)
        self.assertEqual(result['attempts'][0]['state'], 'reserved')

    def test_tampered_saved_score_is_rejected_even_with_new_outer_checksum(self):
        value, expected = self.state()
        value['results']['base:1']['row']['official_score']['correct'] = True
        with self.assertRaises(AssertionError):
            validate_progress(self.raw(value), expected)

    def test_missing_variant_is_not_silently_ignored(self):
        value, expected = self.state()
        expected['known_by_variant']['full32'] = 1
        with self.assertRaises(AssertionError):
            validate_progress(self.raw(value), expected)

    def test_wrong_attempt_identity_is_rejected(self):
        value, expected = self.state()
        value['attempts'][1]['case_index'] = 2
        with self.assertRaises(AssertionError):
            validate_progress(self.raw(value), expected)


if __name__ == '__main__':
    unittest.main()
