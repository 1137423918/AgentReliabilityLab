"""Linux CPU controls for persistent inference progress; no model calls."""
from pathlib import Path
import copy
import hashlib
import json
import os
import select
import signal
import subprocess
import sys
import tempfile
import unittest

MODULES = Path(__file__).resolve().parents[2]/'benchmarks'
sys.path.insert(0, str(MODULES))
from generation_progress import GenerationProgress, ProgressError, digest


def definition(total=12, variant=6, case=2):
    return {'variants': ['base', 'full32', 'mixed32'],
            'cases': [{'id_sha256': hashlib.sha256(('case%d'%i).encode()).hexdigest(),
                       'sample_sha256': digest(['sample', i]),
                       'request_sha256': digest(['request', i])} for i in range(1, 5)],
            'model_identity': {'base_revision': 'fixed', 'full_adapter': 'fixed32'},
            'limits': {'total_attempts': total, 'variant_attempts': variant, 'case_attempts': case}}


def row(index=1, correct=False):
    return {'id': 'case%d'%index, 'sample_sha256': digest(['sample', index]),
            'official_score': {'correct': correct, 'score': float(correct)},
            'prediction': {'raw_output': 'recorded output', 'tool_calls': []}}


def stopped(variant='full32', guard='foreign_compute_client'):
    return {'terminal': True, 'status': 'failed', 'variant': variant,
            'own_GPU_context_absent': True, 'shutdown': {'remaining_owned_processes': []},
            'phases': [{'phase': variant, 'guard_reason': guard}]}


class ProgressControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='agentlab-progress-control-')
        self.base = Path(self.temp.name); self.root = self.base/'state'
        self.d = definition(); self.children = []

    def tearDown(self):
        for p in self.children:
            if p.poll() is None: p.kill()
            p.wait(timeout=5)
            if p.stdout: p.stdout.close()
        self.temp.cleanup()

    def create(self, d=None):
        self.d = d or self.d
        return GenerationProgress(self.root, self.d, create=True)

    def spawn(self, body):
        path = self.base/'definition.json'; path.write_text(json.dumps(self.d))
        code = ('import json,sys,time\nfrom pathlib import Path\n'
                +'sys.path.insert(0,'+repr(str(MODULES))+')\n'
                +'from generation_progress import GenerationProgress,ProgressError\n'
                +'d=json.loads(Path('+repr(str(path))+').read_text())\n'
                +'p=GenerationProgress('+repr(str(self.root))+',d)\n'+body)
        p = subprocess.Popen([sys.executable, '-u', '-c', code], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True)
        self.children.append(p); return p

    def line(self, p):
        self.assertTrue(select.select([p.stdout], [], [], 10)[0], 'child did not signal readiness')
        return p.stdout.readline().strip()

    def test_completed_failure_is_cached_and_never_regenerated(self):
        p = self.create(); seq = p.reserve('full32', 1, self.d['cases'][0]['request_sha256'])
        p.complete(seq, row(correct=False))
        reopened = GenerationProgress(self.root, self.d)
        self.assertEqual(reopened.cached('full32', 1), row(correct=False))
        with self.assertRaises(ProgressError):
            reopened.reserve('full32', 1, self.d['cases'][0]['request_sha256'])
        self.assertEqual(len(reopened.snapshot()['attempts']), 1)

    def test_real_SIGKILL_keeps_unknown_charged_before_authorized_retry(self):
        p = self.create()
        child = self.spawn("with p.worker('full32'):\n seq=p.reserve('full32',1,d['cases'][0]['request_sha256'])\n print(seq,flush=True)\n time.sleep(60)\n")
        self.assertEqual(self.line(child), '1'); os.kill(child.pid, signal.SIGKILL)
        self.assertEqual(child.wait(timeout=5), -signal.SIGKILL)
        reopened = GenerationProgress(self.root, self.d)
        self.assertEqual(reopened.snapshot()['attempts'][0]['state'], 'reserved')
        with self.assertRaises(ProgressError):
            reopened.reserve('full32', 1, self.d['cases'][0]['request_sha256'])
        reopened.authorize_resource_retry(1, stopped())
        seq = reopened.reserve('full32', 1, self.d['cases'][0]['request_sha256'])
        self.assertEqual(seq, 2); reopened.complete(seq, row())
        state = reopened.snapshot()
        self.assertEqual([x['state'] for x in state['attempts']], ['reserved', 'completed'])
        self.assertEqual(state['attempts'][0]['retry_permission']['guard'], 'foreign_compute_client')

    def test_live_worker_lock_and_release_after_kill(self):
        p = self.create()
        child = self.spawn("with p.worker('full32'):\n print('locked',flush=True)\n time.sleep(60)\n")
        self.assertEqual(self.line(child), 'locked')
        with self.assertRaises(ProgressError):
            with p.worker('full32'): self.fail('second worker acquired live lease')
        child.kill(); child.wait(timeout=5)
        with p.worker('full32'): self.assertIsNotNone(p.snapshot())

    def test_concurrent_processes_cannot_overspend_global_budget(self):
        p = self.create(definition(total=2, variant=2))
        children = [self.spawn("try:\n print(p.reserve('full32',%d,d['cases'][%d]['request_sha256']),flush=True)\nexcept ProgressError:\n print('denied',flush=True)\n"%(i, i-1)) for i in range(1, 5)]
        values = [self.line(child) for child in children]
        for child in children: self.assertEqual(child.wait(timeout=5), 0)
        self.assertEqual(sum(x != 'denied' for x in values), 2)
        self.assertEqual(len(p.snapshot()['attempts']), 2)

    def test_identity_change_and_missing_or_corrupt_state_fail_closed(self):
        p = self.create(); p.reserve('base', 1, self.d['cases'][0]['request_sha256'])
        altered = copy.deepcopy(self.d); altered['model_identity']['base_revision'] = 'changed'
        with self.assertRaises(ProgressError): GenerationProgress(self.root, altered)
        data = p.path.read_bytes(); p.path.write_bytes(data.replace(b'reserved', b'brokenxx'))
        with self.assertRaises(ProgressError): GenerationProgress(self.root, self.d)
        self.assertIn(b'brokenxx', p.path.read_bytes())
        p.path.unlink()
        with self.assertRaises(ProgressError): GenerationProgress(self.root, self.d)
        self.assertFalse(p.path.exists())

    def test_quality_errors_or_live_supervisor_never_authorize_retry(self):
        p = self.create(); p.reserve('full32', 1, self.d['cases'][0]['request_sha256'])
        for guard in ['single_call_watchdog', 'model_load_watchdog', None]:
            with self.subTest(guard=guard), self.assertRaises(ProgressError):
                p.authorize_resource_retry(1, stopped(guard=guard))
        running = stopped(); running['terminal'] = False
        with self.assertRaises(ProgressError): p.authorize_resource_retry(1, running)
        self.assertNotIn('retry_permission', p.snapshot()['attempts'][0])

    def test_per_case_and_variant_limits_do_not_refund_unknowns(self):
        p = self.create(definition(total=6, variant=2, case=2))
        request = self.d['cases'][0]['request_sha256']
        one = p.reserve('full32', 1, request); p.authorize_resource_retry(one, stopped())
        two = p.reserve('full32', 1, request); p.authorize_resource_retry(two, stopped())
        with self.assertRaises(ProgressError): p.reserve('full32', 1, request)
        with self.assertRaises(ProgressError): p.reserve('full32', 2, self.d['cases'][1]['request_sha256'])
        self.assertEqual(len(p.snapshot()['attempts']), 2)

    def test_wrong_request_or_result_and_duplicate_completion_rejected(self):
        p = self.create()
        with self.assertRaises(ProgressError): p.reserve('full32', 1, '0'*64)
        self.assertEqual(len(p.snapshot()['attempts']), 0)
        seq = p.reserve('full32', 1, self.d['cases'][0]['request_sha256'])
        with self.assertRaises(ProgressError): p.complete(seq, row(index=2))
        p.complete(seq, row())
        with self.assertRaises(ProgressError): p.complete(seq, row(correct=True))
        self.assertEqual(p.cached('full32', 1), row(correct=False))


if __name__ == '__main__':
    unittest.main(verbosity=2)
