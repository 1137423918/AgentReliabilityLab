import copy
import json
from pathlib import Path
import tempfile
import unittest
from benchmarks.training_journal import TrainingJournal


DEFINITION = {'identity': {'seed': 42, 'profile': 'reference', 'source': 'frozen'},
              'segments': [{'start': 0, 'end': 1, 'forwards': 1}, {'start': 1, 'end': 2, 'forwards': 1}],
              'forward_cap': 2, 'optimizer_cap': 2}


def step(journal, number):
    journal.event('update_begin', {'update': number})
    state = journal.event('forward_reserved', {'phase': 'training', 'update': number, 'id_sha256': 'row', 'position': 0})
    sequence = state['forward_reserved']
    journal.event('forward_completed', {'sequence': sequence})
    journal.event('backward_reserved', {'forward_sequence': sequence})
    journal.event('backward_completed', {'forward_sequence': sequence})
    journal.event('optimizer_reserved', {'update': number})
    journal.event('optimizer_completed', {'update': number})
    journal.event('checkpoint_committed', {'directory': 'step-%03d'%number, 'manifest_sha256': 'a'*64, 'completed_optimizer_updates': number})
    journal.event('segment_clean')


class JournalControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.path = Path(self.temp.name)/'trajectory'
        self.journal = TrainingJournal(self.path, DEFINITION)

    def tearDown(self):
        self.journal.close(); self.temp.cleanup()

    def reopen(self):
        self.journal.close(); self.journal = TrainingJournal(self.path, DEFINITION)

    def test_clean_segment_survives_process_state_reopen_and_finishes_without_refund(self):
        self.journal.event('segment_begin', {'index': 0}); step(self.journal, 1); before = self.journal.snapshot()
        self.reopen(); self.assertEqual(self.journal.snapshot(), before)
        self.journal.event('segment_begin', {'index': 1}); step(self.journal, 2)
        state = self.journal.snapshot()
        self.assertEqual(state['forward_reserved'], 2); self.assertEqual(state['optimizer_reserved'], 2)
        self.assertEqual(state['next_segment'], 2)

    def test_running_segment_and_unknown_dispatch_cannot_resume(self):
        self.journal.event('segment_begin', {'index': 0})
        self.journal.event('update_begin', {'update': 1})
        self.journal.event('forward_reserved', {'phase': 'training', 'update': 1})
        self.reopen()
        self.assertEqual(self.journal.snapshot()['forward_reserved'], 1)
        self.assertEqual(self.journal.snapshot()['forward_completed'], 0)
        with self.assertRaises(AssertionError): self.journal.event('segment_begin', {'index': 0})

    def test_failed_segment_even_with_committed_checkpoint_cannot_resume(self):
        self.journal.event('segment_begin', {'index': 0}); step(self.journal, 1)
        self.journal.event('segment_begin', {'index': 1}); self.journal.event('failed', {'error': 'resource guard'})
        self.reopen()
        with self.assertRaises(AssertionError): self.journal.event('segment_begin', {'index': 1})

    def test_forward_limit_no_extra_kernel_dispatch_and_double_completion_rejected(self):
        self.journal.event('segment_begin', {'index': 0}); step(self.journal, 1)
        self.journal.event('segment_begin', {'index': 1}); step(self.journal, 2)
        with self.assertRaises(AssertionError): self.journal.event('forward_completed', {'sequence': 2})
        with self.assertRaises(AssertionError): self.journal.event('forward_reserved', {'phase': 'canary_sparse'})

    def test_partial_update_without_durable_checkpoint_cannot_close_clean(self):
        self.journal.event('segment_begin', {'index': 0})
        with self.assertRaises(AssertionError): self.journal.event('segment_clean')
        with self.assertRaises(AssertionError): self.journal.event('optimizer_reserved', {'update': 1})

    def test_changed_identity_or_budget_rejected(self):
        self.journal.close()
        for field in ['identity', 'forward_cap']:
            definition = copy.deepcopy(DEFINITION)
            if field == 'identity': definition['identity']['seed'] = 43
            else: definition['forward_cap'] = 3
            with self.assertRaises(AssertionError): TrainingJournal(self.path, definition)

    def test_tampered_hash_or_partial_tail_rejected(self):
        self.journal.close(); path = self.path/'events.jsonl'; raw = path.read_bytes()
        event = json.loads(raw); event['data']['identity']['seed'] = 43
        path.write_text(json.dumps(event)+'\n')
        with self.assertRaises(AssertionError): TrainingJournal(self.path, DEFINITION)
        path.write_bytes(raw+b'{"partial":')
        with self.assertRaises(AssertionError): TrainingJournal(self.path, DEFINITION)

    def test_exclusive_run_lock_rejects_concurrent_driver(self):
        with self.assertRaises(BlockingIOError): TrainingJournal(self.path, DEFINITION)


if __name__ == '__main__':
    unittest.main()
