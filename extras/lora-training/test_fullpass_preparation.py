import copy
from collections import Counter
import unittest
from benchmarks.fullpass_schedule import make_fullpass, validate_fullpass
from benchmarks.admit_fresh_bfcl import fresh_selection


def examples(lengths):
    original, masked = [], []
    for i, n in enumerate(lengths):
        row = {'id_sha256': str(i), 'component_sha256': 'group'+str(i),
               'input_ids': list(range(n+2)), 'labels': [-100, -100]+list(range(2, n+2)),
               'prompt_tokens': 2, 'target_tokens': n}
        original.append(row)
        labels = list(row['labels']); labels[2] = -100
        masked.append({**copy.deepcopy(row), 'labels': labels,
            'effective_target_tokens': n-1, 'masked_fixed_reason_tokens': 1})
    return original, masked


def candidate(category, name, component, eligible=True):
    return {'category': category, 'id': name, 'component_sha256': component,
            'eligible': eligible, 'exclusions': [] if eligible else ['protected_text_component']}


class FullpassControls(unittest.TestCase):
    def test_whole_examples_exact_once_with_partial_actual_denominators(self):
        left, right = examples([2, 3, 5, 7, 11, 4])
        plan = make_fullpass(left, right, 42, target_labels=8)
        self.assertEqual(plan['updates'], 4)
        self.assertEqual(plan['sequence_forwards'], 6)
        self.assertEqual(plan['training_active_labels'], {'reference': 32, 'masked': 26})
        self.assertEqual(Counter(s['id_sha256'] for p in plan['steps'] for s in p['segments']), Counter(str(i) for i in range(6)))
        self.assertEqual(plan['input_token_exposures'], 44)
        self.assertTrue(any(step['active_labels']['reference'] != 8 for step in plan['steps']))

    def test_seed_repeatability_pair_identity_and_different_orders(self):
        left, right = examples([i % 11+2 for i in range(80)])
        plans = [make_fullpass(left, right, seed, 32) for seed in [42, 43, 44]]
        self.assertEqual(plans[0], make_fullpass(left, right, 42, 32))
        self.assertEqual(len({p['order_sha256'] for p in plans}), 3)
        self.assertEqual(len({p['updates'] for p in plans}), 1)
        self.assertEqual(len({p['input_token_exposures'] for p in plans}), 1)

    def test_oversized_example_never_truncated_or_cut_into_empty_mask_fragment(self):
        left, right = examples([30, 2, 3])
        plan = make_fullpass(left, right, 44, 4)
        self.assertEqual(plan['updates'], 3)
        self.assertEqual(plan['training_active_labels']['reference'], 35)
        for step in plan['steps']:
            for segment in step['segments']:
                row = next(row for row in left if row['id_sha256'] == segment['id_sha256'])
                self.assertEqual((segment['label_start'], segment['label_end']), (2, len(row['input_ids'])))

    def test_missing_repeated_or_changed_schedule_label_range_rejected(self):
        left, right = examples([3, 4, 7, 8])
        plan = make_fullpass(left, right, 42, 10)
        for change in ['missing', 'duplicate', 'range']:
            broken = copy.deepcopy(plan)
            if change == 'missing':
                broken['steps'][0]['segments'].pop()
            elif change == 'duplicate':
                broken['steps'][0]['segments'].append(broken['steps'][0]['segments'][0])
            else:
                broken['steps'][0]['segments'][0]['label_start'] += 1
            with self.assertRaises(AssertionError):
                validate_fullpass(broken, left, right)

    def test_changed_input_and_empty_mask_row_rejected_without_dropping(self):
        left, right = examples([3, 4, 5])
        right[0]['input_ids'][2] += 1
        with self.assertRaises(AssertionError):
            make_fullpass(left, right, 42)
        left, right = examples([3, 4, 5])
        right[0]['labels'] = [-100]*5; right[0]['effective_target_tokens'] = 0
        with self.assertRaises(AssertionError):
            make_fullpass(left, right, 42)


class FreshAdmissionControls(unittest.TestCase):
    def test_previous_component_excludes_other_ID_and_does_not_mutate_parent(self):
        rows = [candidate('a', 'seen', 'x'), candidate('a', 'different-id', 'x'),
                candidate('a', 'new', 'y'), candidate('b', 'other', 'z')]
        before = copy.deepcopy(rows)
        selected, filtered = fresh_selection(rows, [rows[0]], {'a': 1, 'b': 1}, 'fixed-seed')
        self.assertEqual({r['id'] for r in selected}, {'new', 'other'})
        self.assertEqual(rows, before)
        self.assertFalse(filtered[1]['eligible'])

    def test_old_ID_excluded_even_if_component_metadata_disagrees(self):
        row = candidate('a', 'same-id', 'new-component')
        with self.assertRaises(AssertionError):
            fresh_selection([row], [candidate('a', 'same-id', 'old-component')], {'a': 1}, 'seed')

    def test_protected_and_duplicate_components_never_fill_quota(self):
        rows = [candidate('a', 'protected', 'p', False), candidate('a', 'x', 'z'), candidate('b', 'y', 'z')]
        with self.assertRaises(AssertionError):
            fresh_selection(rows, [], {'a': 1, 'b': 1}, 'seed')

    def test_selection_cannot_accept_score_fields(self):
        row = candidate('a', 'x', 'z'); row['correct'] = True
        with self.assertRaises(AssertionError):
            fresh_selection([row], [], {'a': 1}, 'seed')

    def test_seeded_selection_is_stable_without_changing_quota(self):
        rows = [candidate(cat, cat+str(i), cat+'component'+str(i)) for cat in ['a', 'b'] for i in range(12)]
        first, _ = fresh_selection(rows, [], {'a': 3, 'b': 3}, 'fixed-seed')
        second, _ = fresh_selection(list(reversed(rows)), [], {'a': 3, 'b': 3}, 'fixed-seed')
        self.assertEqual(first, second)
        self.assertEqual(Counter(r['category'] for r in first), {'a': 3, 'b': 3})


if __name__ == '__main__':
    unittest.main()
