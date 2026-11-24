import math
from pathlib import Path
import tempfile
import unittest
import torch
import torch.nn.functional as F
from benchmarks.causal_loss_parts import PARTS, causal_selection, summarize_token_losses, target_parts
from benchmarks.evaluate_loss_parts import evaluate_case
from benchmarks.generation_progress import GenerationProgress, ProgressError


class LossPartControls(unittest.TestCase):
    def test_exact_fixed_prose_payload_structure_and_special_offsets(self):
        answer = '<think> constant </think>\n<tool_call>{"x":1}</tool_call>'
        offsets = [(i, i+1) for i in range(len(answer))]+[(0, 0)]
        parts, shape = target_parts(answer, 0, [1]*len(offsets), offsets, {'constant', 'other'})
        self.assertEqual(shape, 'tool_call')
        self.assertEqual(parts[answer.index('constant'):answer.index('constant')+8], [0]*8)
        a, b = answer.index('{'), answer.index('}')+1
        self.assertEqual(parts[a:b], [1]*(b-a))
        self.assertEqual(parts[-1], 3)
        self.assertEqual(sum(part == 0 for part in parts), 8)

    def test_variable_reason_is_not_assumed_fixed_and_direct_response_kept(self):
        answer = '<think> novel reasoning </think><response>hello</response>'
        parts, shape = target_parts(answer, 0, [1]*len(answer), [(i, i+1) for i in range(len(answer))], {'constant'})
        self.assertEqual(shape, 'response')
        self.assertNotIn(0, parts)
        self.assertEqual(parts.count(1), 5)
        self.assertGreater(parts.count(2), 0)

    def test_cross_boundary_tokens_and_ignored_prompt_are_not_reassigned(self):
        answer = '<think> constant </think><response>yes</response>'
        i = answer.index('constant')
        parts, _ = target_parts(answer, 7, [-100, 1, 1], [(0, 3), (7+i-1, 7+i+2), (7+i, 7+i+2)], {'constant'})
        self.assertEqual(parts, [-1, 3, 0])
        # The first active token straddles the fixed-prose boundary and must
        # remain in the structural/boundary residual.

    def test_unexpected_answer_envelope_is_rejected_not_dropped(self):
        with self.assertRaises(AssertionError):
            target_parts('<think>constant</think>plain', 0, [1], [(0, 1)], {'constant'})

    def test_causal_shift_and_target_tampering(self):
        row = {'input_ids': [1, 2, 3, 4], 'labels': [-100, -100, 3, 4], 'parts': [-1, -1, 0, 1], 'target_tokens': 2}
        self.assertEqual(causal_selection(row), ([1, 2], [3, 4], [0, 1]))
        row['labels'][2] = 7
        with self.assertRaises(AssertionError):
            causal_selection(row)

    def test_unreduced_component_sums_reconstruct_standard_causal_CE(self):
        torch.manual_seed(42)
        logits = torch.randn(7, 13, dtype=torch.float64)
        labels = torch.tensor([-100, -100, 3, 4, 5, 6, 7])
        parts = [0, 1, 1, 2, 3]
        losses = F.cross_entropy(logits[1:6], labels[2:], reduction='none').tolist()
        full = F.cross_entropy(logits[:-1], labels[1:], reduction='sum')
        result = summarize_token_losses(losses, parts)
        self.assertAlmostEqual(sum(v['loss_sum'] for v in result.values()), float(full), places=12)
        self.assertAlmostEqual(sum(v['loss_sum'] for v in result.values())/5, float(full)/5, places=12)

    def test_zero_token_parts_undefined_and_token_weighted_not_case_average(self):
        values = summarize_token_losses([1., 3., 10.], [1, 1, 3])
        self.assertIsNone(values[PARTS[0]]['token_weighted_NLL'])
        self.assertAlmostEqual(sum(v['loss_sum'] for v in values.values())/3, 14/3)
        self.assertFalse(math.isclose(14/3, (2+10)/2))

    def test_forward_reserved_before_callback_and_unknown_never_refunded(self):
        case = {'id': 'case', 'sample_sha256': 'a'*64, 'request_sha256': 'b'*64,
                'kind': 'parts', 'split': 'test', 'id_sha256': 'c'*64,
                'component_sha256': 'd'*64, 'target_tokens': 2}
        definition = {'variants': ['base'], 'cases': [{'id_sha256': __import__('hashlib').sha256(b'case').hexdigest(),
            'sample_sha256': 'a'*64, 'request_sha256': 'b'*64}],
            'limits': {'total_attempts': 1, 'variant_attempts': 1, 'case_attempts': 1}}
        with tempfile.TemporaryDirectory() as root:
            progress = GenerationProgress(Path(root)/'progress', definition, create=True)
            def fail(value, sequence):
                self.assertEqual(progress.snapshot()['attempts'][0]['state'], 'reserved')
                raise RuntimeError('Interrupted forward')
            with self.assertRaises(RuntimeError):
                evaluate_case(progress, 'base', 1, case, fail)
            self.assertEqual(len(progress.snapshot()['attempts']), 1)
            with self.assertRaises(ProgressError):
                evaluate_case(progress, 'base', 1, case, lambda *a: self.fail('Retry callback invoked'))

    def test_completed_forward_cannot_be_replayed(self):
        case = {'id': 'case', 'sample_sha256': 'a'*64, 'request_sha256': 'b'*64,
                'kind': 'parts', 'split': 'test', 'id_sha256': 'c'*64,
                'component_sha256': 'd'*64, 'target_tokens': 2}
        definition = {'variants': ['base'], 'cases': [{'id_sha256': __import__('hashlib').sha256(b'case').hexdigest(),
            'sample_sha256': 'a'*64, 'request_sha256': 'b'*64}],
            'limits': {'total_attempts': 1, 'variant_attempts': 1, 'case_attempts': 1}}
        with tempfile.TemporaryDirectory() as root:
            progress = GenerationProgress(Path(root)/'progress', definition, create=True)
            evaluate_case(progress, 'base', 1, case, lambda *a: {'loss_sum': 2., 'parts': None})
            before = progress.snapshot()
            with self.assertRaises(AssertionError):
                evaluate_case(progress, 'base', 1, case, lambda *a: self.fail('Completed callback invoked'))
            self.assertEqual(before, progress.snapshot())


if __name__ == '__main__':
    assert not torch.cuda.is_initialized()
    unittest.main()
