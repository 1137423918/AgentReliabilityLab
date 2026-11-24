"""CPU numerical controls; run on the authorized server, never local training."""
import copy
import random
from pathlib import Path
import tempfile
import unittest
import numpy as np
import torch
from benchmarks.training_checkpoint import commit_checkpoint, inspect_checkpoint, restore_checkpoint

NUMERIC = {'tiny_CPU_forward_calls': 0, 'tiny_CPU_optimizer_updates': 0}


def seed(value):
    torch.manual_seed(value); random.seed(value); np.random.seed(value)


def network():
    model = torch.nn.Sequential(torch.nn.Linear(4, 7), torch.nn.Dropout(.35), torch.nn.Tanh(), torch.nn.Linear(7, 2))
    optimizer = torch.optim.AdamW(model.parameters(), lr=.003, foreach=False)
    scaler = torch.amp.GradScaler('cpu', init_scale=128.0)
    return model, optimizer, scaler


def update(model, optimizer, scaler):
    model.train(); optimizer.zero_grad(set_to_none=True)
    # Exercise all three seeded RNG streams, plus stochastic model execution.
    x = torch.randn(5, 4)*(1+random.random())+float(np.random.random())
    y = torch.randn(5, 2)
    NUMERIC['tiny_CPU_forward_calls'] += 1
    loss = (model(x)-y).square().mean(); scaler.scale(loss).backward()
    scaler.step(optimizer); scaler.update()
    NUMERIC['tiny_CPU_optimizer_updates'] += 1
    return float(loss.detach())


def equal(left, right):
    if torch.is_tensor(left):
        assert torch.equal(left, right), (left, right)
    elif isinstance(left, dict):
        assert left.keys() == right.keys()
        for key in left: equal(left[key], right[key])
    elif isinstance(left, (list, tuple)):
        assert type(left) is type(right) and len(left) == len(right)
        for a, b in zip(left, right): equal(a, b)
    else:
        assert left == right


class CheckpointControls(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.path = Path(self.directory.name)/'step-002'
        self.identity = {'study': 'checkpoint-control', 'seed': 42, 'profile': 'reference', 'schedule_sha256': 'frozen'}

    def tearDown(self):
        self.directory.cleanup()

    def make_checkpoint(self):
        seed(42); model, optimizer, scaler = network()
        for _ in range(2): update(model, optimizer, scaler)
        receipt = commit_checkpoint(self.path, list(model.named_parameters()), optimizer, scaler,
                                    self.identity, {'completed_optimizer_updates': 2, 'charged_forwards': 2})
        return model, optimizer, scaler, receipt

    def test_planned_resume_matches_uninterrupted_weights_optimizer_scaler_and_rng_bitwise(self):
        model, optimizer, scaler, receipt = self.make_checkpoint()
        expected_losses = [update(model, optimizer, scaler) for _ in range(3)]
        expected_model = copy.deepcopy(model.state_dict()); expected_optimizer = copy.deepcopy(optimizer.state_dict())
        expected_scaler = scaler.state_dict(); expected_next = (random.random(), float(np.random.random()), torch.rand(9))
        seed(123); resumed, ropt, rscale = network()
        counters = restore_checkpoint(self.path, receipt['manifest_sha256'], list(resumed.named_parameters()), ropt, rscale, self.identity)
        self.assertEqual(counters, {'completed_optimizer_updates': 2, 'charged_forwards': 2})
        self.assertEqual([update(resumed, ropt, rscale) for _ in range(3)], expected_losses)
        equal(resumed.state_dict(), expected_model); equal(ropt.state_dict(), expected_optimizer); equal(rscale.state_dict(), expected_scaler)
        equal((random.random(), float(np.random.random()), torch.rand(9)), expected_next)

    def test_wrong_study_seed_role_or_schedule_is_rejected_before_mutation(self):
        model, optimizer, scaler, receipt = self.make_checkpoint(); before = copy.deepcopy(model.state_dict())
        for key in self.identity:
            broken = dict(self.identity); broken[key] = 'wrong'
            with self.assertRaises(AssertionError):
                restore_checkpoint(self.path, receipt['manifest_sha256'], list(model.named_parameters()), optimizer, scaler, broken)
            equal(model.state_dict(), before)

    def test_corruption_and_wrong_manifest_are_rejected(self):
        _, _, _, receipt = self.make_checkpoint()
        with self.assertRaises(AssertionError): inspect_checkpoint(self.path, '0'*64, self.identity)
        with (self.path/'state.safetensors').open('ab') as stream: stream.write(b'corrupt')
        with self.assertRaises(AssertionError): inspect_checkpoint(self.path, receipt['manifest_sha256'], self.identity)

    def test_parameter_order_mismatch_is_rejected_before_mutation(self):
        model, optimizer, scaler, receipt = self.make_checkpoint(); before = copy.deepcopy(model.state_dict())
        with self.assertRaises(AssertionError):
            restore_checkpoint(self.path, receipt['manifest_sha256'], list(reversed(list(model.named_parameters()))), optimizer, scaler, self.identity)
        equal(model.state_dict(), before)

    def test_existing_checkpoint_is_never_overwritten_and_no_partial_snapshot_visible(self):
        model, optimizer, scaler, receipt = self.make_checkpoint()
        with self.assertRaises(AssertionError):
            commit_checkpoint(self.path, list(model.named_parameters()), optimizer, scaler, self.identity, {'completed_optimizer_updates': 2})
        self.assertEqual(set(p.name for p in self.path.parent.iterdir()), {self.path.name})
        self.assertEqual(inspect_checkpoint(self.path, receipt['manifest_sha256'], self.identity)['counters']['completed_optimizer_updates'], 2)


if __name__ == '__main__':
    import json
    torch.set_num_threads(2)
    result = unittest.main(exit=False)
    print(json.dumps({**NUMERIC, 'pretrained_model_forwards': 0, 'CUDA_initialized': torch.cuda.is_initialized()}), flush=True)
    raise SystemExit(0 if result.result.wasSuccessful() else 1)
