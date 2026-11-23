import copy
import unittest

import torch
import torch.nn.functional as F

from benchmarks.fixed_reason_objective import active_causal_targets, update_label_count, validate_pair


class ObjectiveTests(unittest.TestCase):
    def test_shift_and_internal_masks(self):
        row = {'input_ids': [1, 2, 3, 4, 5], 'labels': [-100, -100, 3, -100, 5]}
        self.assertEqual(active_causal_targets(row, 2, 5), ([1, 3], [3, 5]))
        self.assertEqual(active_causal_targets(row, 3, 5), ([3], [5]))

    def test_zero_active_or_unshifted_segment_fails(self):
        row = {'input_ids': [1, 2, 3], 'labels': [-100, -100, 3]}
        for a, b in [(0, 3), (1, 2)]:
            with self.assertRaises(AssertionError):
                active_causal_targets(row, a, b)

    def test_changed_target_token_is_rejected(self):
        with self.assertRaises(AssertionError):
            active_causal_targets({'input_ids': [1, 2], 'labels': [-100, 3]}, 1, 2)

    def test_sparse_loss_and_all_logit_gradients_match_standard_causal_loss(self):
        torch.manual_seed(42)
        row = {'input_ids': [1, 2, 3, 4, 5, 6], 'labels': [-100, -100, 3, -100, 5, 6]}
        for a, b in [(2, 6), (3, 5), (4, 6)]:
            logits = torch.randn(6, 11, requires_grad=True)
            labels = torch.full((6,), -100, dtype=torch.long)
            labels[a:b] = torch.tensor(row['labels'][a:b])
            ordinary = F.cross_entropy(logits[:-1], labels[1:], reduction='sum')
            pos, targets = active_causal_targets(row, a, b)
            sparse = F.cross_entropy(logits[pos], torch.tensor(targets), reduction='sum')
            torch.testing.assert_close(ordinary, sparse)
            g1 = torch.autograd.grad(ordinary, logits, retain_graph=True)[0]
            g2 = torch.autograd.grad(sparse, logits)[0]
            torch.testing.assert_close(g1, g2)

    def test_update_normalization_matches_concatenated_active_targets(self):
        torch.manual_seed(42)
        rows = {'a': {'input_ids': [1, 2, 3, 4], 'labels': [-100, -100, 3, 4]},
                'b': {'input_ids': [1, 2, 3, 4], 'labels': [-100, -100, -100, 4]}}
        step = {'segments': [{'id_sha256': k, 'label_start': 2, 'label_end': 4} for k in rows]}
        total = update_label_count(step, rows)
        self.assertEqual(total, 3)
        weight = torch.randn(5, 8, requires_grad=True)
        all_logits, all_targets = [], []
        loss = 0
        for row in rows.values():
            inputs = torch.randn(4, 5)
            logits = inputs @ weight
            pos, targets = active_causal_targets(row, 2, 4)
            chosen = logits[pos]
            target = torch.tensor(targets)
            loss = loss + F.cross_entropy(chosen, target, reduction='sum') / total
            all_logits.append(chosen)
            all_targets.append(target)
        combined = F.cross_entropy(torch.cat(all_logits), torch.cat(all_targets), reduction='mean')
        torch.testing.assert_close(loss, combined)
        g1 = torch.autograd.grad(loss, weight, retain_graph=True)[0]
        g2 = torch.autograd.grad(combined, weight)[0]
        torch.testing.assert_close(g1, g2)
        self.assertNotAlmostEqual(float(loss.detach()), float((combined*3/4).detach()))

    def test_full_pair_validation_preserves_order_and_targets(self):
        left = {'id_sha256': 'id', 'component_sha256': 'component', 'input_ids': [1, 2, 3, 4],
                'labels': [-100, -100, 3, 4], 'prompt_tokens': 2, 'target_tokens': 2}
        right = {**left, 'labels': [-100, -100, -100, 4],
                 'effective_target_tokens': 1, 'masked_fixed_reason_tokens': 1}
        original = [{**copy.deepcopy(left), 'id_sha256': str(i)} for i in range(3700)]
        masked = [{**copy.deepcopy(right), 'id_sha256': str(i)} for i in range(3700)]
        result = validate_pair(original, masked)
        self.assertEqual(result['removed_fixed_reason_labels'], 3700)
        masked[1]['input_ids'][0] = 8
        with self.assertRaises(AssertionError):
            validate_pair(original, masked)


if __name__ == '__main__':
    assert not torch.cuda.is_initialized()
    unittest.main()
