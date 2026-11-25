"""Source review on real fixture checkpoints/citations; no neural inference."""
import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import stat
import unittest
from unittest.mock import patch

from agent_lab.request_budget import digest
from agent_lab.research_library import ingest
from agent_lab.research_report import ReportError
from agent_lab.research_review import (
    build_review, initial_decisions, main, validate_decisions, write_review,
)
from agent_lab.research_review_view import review_html
import test_research_report as report_fixture
from test_research_view import Page


def rebound(bundle):
    """Bind intentionally hostile presentation fixtures, never recorded results."""
    for position, entry in enumerate(bundle['entries']):
        for passage in entry['passages']:
            passage['excerpt_sha256'] = hashlib.sha256(passage['excerpt'].encode()).hexdigest()
        entry['answer_sha256'] = digest(entry['run'].get('answer'))
        entry['entry_id'] = digest({'position': position, 'run': entry['run'],
                                    'passages': entry['passages'], 'evidence_error': entry['evidence_error']})
    bundle['bundle_sha256'] = digest({k: v for k, v in bundle.items() if k != 'bundle_sha256'})
    return bundle


class SourceReview(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.fixture = report_fixture.ReportWorkflows('runTest')
        await self.fixture.asyncSetUp()

    async def asyncTearDown(self):
        await self.fixture.asyncTearDown()

    async def bundle(self, name='run'):
        directory = await self.fixture.make_run(name)
        return build_review([directory], self.fixture.store)

    async def test_exact_passage_from_real_checkpoint_without_network_or_new_encoding(self):
        f = self.fixture
        directory = await f.make_run()
        before = report_fixture.hashes(directory), report_fixture.hashes(f.store), f.model.calls
        with patch('socket.socket.connect', side_effect=AssertionError('No network allowed')):
            bundle = build_review([directory], f.store)
        entry = bundle['entries'][0]
        self.assertTrue(entry['reviewable'])
        ref = entry['run']['references'][0]
        self.assertTrue(entry['passages'][0]['excerpt'])
        self.assertEqual(entry['passages'][0]['excerpt'], f.raw.decode()[ref['char_start']:ref['char_end']])
        self.assertEqual(entry['passages'][0]['excerpt_sha256'], hashlib.sha256(entry['passages'][0]['excerpt'].encode()).hexdigest())
        self.assertEqual(entry['passages'][0]['citation_id'], entry['run']['references'][0]['citation_id'])
        self.assertFalse(bundle['semantic_entailment_checked'])
        self.assertEqual(initial_decisions(bundle)['entries'][0]['decision'], 'pending')
        self.assertEqual(before, (report_fixture.hashes(directory), report_fixture.hashes(f.store), f.model.calls))

    async def test_historical_passage_survives_a_new_active_source_generation(self):
        f = self.fixture
        directory = await f.make_run()
        old = build_review([directory], f.store)
        raw = b'New unrelated content.\n'
        (f.root / 'paper.txt').write_bytes(raw)
        spec = json.loads(f.manifest.read_text()); spec['sources'][0]['sha256'] = hashlib.sha256(raw).hexdigest()
        f.manifest.write_text(json.dumps(spec)); ingest(f.manifest, f.store, f.model)
        new = build_review([directory], f.store)
        self.assertEqual(old['entries'][0]['passages'], new['entries'][0]['passages'])
        self.assertFalse(new['entries'][0]['run']['references'][0]['is_current_generation'])
        self.assertIn('归档资料版本', review_html(new))

    async def test_unfinished_and_missing_runs_cannot_be_marked_checked(self):
        f = self.fixture
        good = await f.make_run('good'); unfinished = await f.make_run('unfinished', failed=True)
        bundle = build_review([good, unfinished, f.root / 'missing'], f.store)
        self.assertEqual([e['reviewable'] for e in bundle['entries']], [True, False, False])
        self.assertEqual([e['run']['recorded_status'] for e in bundle['entries']], ['submitted', 'turn_limit', None])
        notes = initial_decisions(bundle)
        self.assertEqual([e['decision'] for e in notes['entries']], ['pending', 'unavailable', 'unavailable'])
        for index in [1, 2]:
            bad = copy.deepcopy(notes); bad['entries'][index]['decision'] = 'checked'
            with self.assertRaises(ReportError): validate_decisions(bundle, bad)

    async def test_reordered_unicode_notes_roundtrip_without_changing_original_results(self):
        f = self.fixture
        one = await f.make_run('one'); two = await f.make_run('two', question='Another question')
        bundle = build_review([one, two], f.store); original = copy.deepcopy(bundle)
        notes = initial_decisions(bundle); notes['reviewer'] = '👩' * 120
        notes['entries'][0].update(decision='needs_changes', notes='证据\n🧪' * 200)
        notes['entries'][1].update(decision='checked', notes='Synthetic test annotation')
        expected = copy.deepcopy(notes); notes['entries'].reverse()
        self.assertEqual(validate_decisions(bundle, notes), expected)
        self.assertEqual(bundle, original)
        self.assertEqual(notes['entries'][0]['decision'], 'checked')

    async def test_stale_bundle_answer_and_entry_mixups_are_rejected(self):
        bundle = await self.bundle()
        notes = initial_decisions(bundle)
        variants = []
        bad = copy.deepcopy(notes); bad['bundle_sha256'] = '0' * 64; variants.append(bad)
        bad = copy.deepcopy(notes); bad['entries'][0]['answer_sha256'] = '0' * 64; variants.append(bad)
        bad = copy.deepcopy(notes); bad['entries'][0]['entry_id'] = '0' * 64; variants.append(bad)
        bad = copy.deepcopy(notes); bad['entries'].append(copy.deepcopy(bad['entries'][0])); variants.append(bad)
        bad = copy.deepcopy(notes); bad['entries'] = []; variants.append(bad)
        for bad in variants:
            with self.subTest(bad=bad):
                before = copy.deepcopy(bad)
                with self.assertRaises(ReportError): validate_decisions(bundle, bad)
                self.assertEqual(bad, before)
        changed = copy.deepcopy(bundle); changed['entries'][0]['run']['answer'] = 'A revised answer'
        with self.assertRaises(ReportError): validate_decisions(rebound(changed), notes)

    async def test_notes_schema_and_unicode_limits_are_enforced(self):
        bundle = await self.bundle(); notes = initial_decisions(bundle); variants = []
        for field, value in [('version', True), ('reviewer', 'x' * 121), ('reviewer', None), ('extra', True)]:
            bad = copy.deepcopy(notes); bad[field] = value; variants.append(bad)
        for field, value in [('notes', '😀' * 1001), ('notes', 4), ('decision', 'supported'), ('extra', 'field')]:
            bad = copy.deepcopy(notes); bad['entries'][0][field] = value; variants.append(bad)
        for bad in variants:
            with self.assertRaises(ReportError): validate_decisions(bundle, bad)
        notes['entries'][0]['notes'] = '😀' * 1000
        self.assertEqual(validate_decisions(bundle, notes), notes)

    async def test_repeatable_private_outputs_and_manifest_cover_notes_and_view(self):
        bundle = await self.bundle(); f = self.fixture
        one, two = f.root / 'one', f.root / 'two'; write_review(bundle, one); write_review(bundle, two)
        self.assertEqual(report_fixture.hashes(one), report_fixture.hashes(two))
        manifest = json.loads((one / 'review-manifest.json').read_text())
        self.assertEqual(set(manifest['files']), {'source-review.html', 'source-review.json', 'review-notes.json'})
        for name, record in manifest['files'].items():
            raw = (one / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record['sha256'])
            self.assertEqual(stat.S_IMODE((one / name).stat().st_mode), 0o600)
        with self.assertRaises(FileExistsError): write_review(bundle, one)

    async def test_tampered_archived_source_is_unavailable_without_a_fabricated_passage(self):
        f = self.fixture; directory = await f.make_run()
        from agent_lab.research_library import open_generation
        root, _ = open_generation(f.store); (root / 'sources/paper.txt').write_text('tampered')
        bundle = build_review([directory], f.store); entry = bundle['entries'][0]
        self.assertFalse(entry['reviewable']); self.assertEqual(entry['passages'], [])
        self.assertEqual(entry['run']['export_status'], 'error')
        self.assertIsNone(entry['run']['answer'])

    async def test_hostile_content_is_text_and_scripts_are_CSP_hash_bound(self):
        import base64
        bundle = await self.bundle()
        attack = '</pre><script>window.attacked=1</script><img src=x onerror="window.attacked=2">'
        entry = bundle['entries'][0]; entry['run']['question'] = attack
        entry['passages'][0]['excerpt'] = attack
        rebound(bundle)
        page = Page(review_html(bundle))
        self.assertEqual(json.loads(page.blocks['pre']), bundle)
        self.assertEqual(len([1 for tag, _ in page.tags if tag == 'script']), 1)
        self.assertFalse(any(tag in ['img', 'iframe', 'object', 'base'] for tag, _ in page.tags))
        self.assertFalse(any(key.startswith('on') for _, attrs in page.tags for key in attrs))
        policy = next(attrs['content'] for tag, attrs in page.tags if tag == 'meta' and attrs.get('http-equiv') == 'Content-Security-Policy')
        for name in ['style', 'script']:
            expected = base64.b64encode(hashlib.sha256(page.blocks[name].encode()).digest()).decode()
            self.assertIn("'sha256-" + expected + "'", policy)
        self.assertIn("connect-src 'none'", policy)

    async def test_cli_prepares_then_validates_notes_without_model_or_source_mutation(self):
        f = self.fixture; directory = await f.make_run(); output = f.root / 'private-review'
        before = report_fixture.hashes(directory), report_fixture.hashes(f.store), f.model.calls
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(['prepare', '--run-dir', str(directory), '--store', str(f.store), '--output', str(output)]), 0)
            self.assertEqual(main(['check-notes', '--bundle', str(output / 'source-review.json'), '--notes', str(output / 'review-notes.json')]), 0)
        self.assertEqual(before, (report_fixture.hashes(directory), report_fixture.hashes(f.store), f.model.calls))


if __name__ == '__main__':
    unittest.main()
