import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from agent_lab.evidence_audit import EvidenceCatalog
from agent_lab.review_workbench import run_workbench

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT/'evidence/dependency-upgrade/corpus'
MANIFEST = ROOT/'catalog.json'
COMPAT = PROJECT/'examples/dependency-workbench/compatibility.json'


class WorkbenchControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.run = self.root/'run'; self.spec = json.loads(COMPAT.read_text())
        for item in self.spec['reports']['fastmcp_2_12_4'].values():
            if isinstance(item, dict) and 'path' in item:
                item['path'] = str((COMPAT.parent/item['path']).resolve())
        self.compat = self.root/'compatibility.json'; self.write_spec()

    def tearDown(self): self.temp.cleanup()

    def write_spec(self): self.compat.write_text(json.dumps(self.spec))

    def invoke(self, **kwargs):
        return run_workbench(ROOT, MANIFEST, self.run, compatibility_manifest=self.compat, **kwargs)

    def replace_artifact(self, key, raw):
        path = self.root/key; path.write_bytes(raw)
        self.spec['reports']['fastmcp_2_12_4'][key] = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
        self.write_spec()

    def test_real_two_projects_produce_correct_distinct_maintenance_actions(self):
        result = self.invoke(); self.assertTrue(result['completed']); self.assertEqual(result['reports'], 2)
        reviews = {r['report_id']: r for r in result['reviews']}
        self.assertEqual(reviews['browser_use_1_0_8']['status'], 'blocked')
        self.assertEqual(reviews['fastmcp_2_12_4']['status'], 'scoped_tests_passed')
        self.assertEqual(reviews['fastmcp_2_12_4']['remaining_affected_registry_resolutions'], 16)
        full = json.loads((self.run/'reviews/fastmcp_2_12_4.json').read_text())
        self.assertEqual(full['compatibility']['baseline']['tests'], 279)
        self.assertEqual(full['compatibility']['candidate']['tests'], 279)
        self.assertFalse(full['deployment_approved']); self.assertEqual(full['model_calls'], 0)

    def test_completed_replay_uses_framework_state_and_preserves_review_bytes(self):
        self.invoke(); before = {p.name: p.read_bytes() for p in (self.run/'reviews').iterdir()}
        with patch.object(EvidenceCatalog, 'read_report', side_effect=AssertionError('completed node ran again')):
            result = self.invoke()
        self.assertEqual(result['reused_completed'], 2)
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.run/'reviews').iterdir()})

    def test_checkpointed_read_resumes_without_rereading_report(self):
        first = self.invoke(_interrupt_after=['collect']); self.assertEqual(len(first['pending']), 2)
        with patch.object(EvidenceCatalog, 'read_report', side_effect=AssertionError('read reran after committed boundary')):
            result = self.invoke()
        self.assertTrue(result['completed'])

    def test_wrong_project_commit_compatibility_rejected(self):
        self.spec['reports']['fastmcp_2_12_4']['commit'] = '0'*40; self.write_spec()
        with self.assertRaisesRegex(ValueError, 'different project snapshot'): self.invoke()

    def test_corrupt_compatibility_artifact_rejected_before_graph(self):
        item = self.spec['reports']['fastmcp_2_12_4']['candidate_junit']; raw = Path(item['path']).read_bytes()
        path = self.root/'changed.xml'; path.write_bytes(raw+b'corrupt'); item['path'] = str(path); self.write_spec()
        with self.assertRaisesRegex(ValueError, 'hash mismatch'): self.invoke()

    def test_different_test_identity_even_with_new_valid_hash_rejected(self):
        item = self.spec['reports']['fastmcp_2_12_4']['candidate_junit']
        xml = ET.fromstring(Path(item['path']).read_bytes()); next(xml.iter('testcase')).set('name', 'different_test')
        self.replace_artifact('candidate_junit', ET.tostring(xml))
        with self.assertRaisesRegex(ValueError, 'different test identities'): self.invoke()

    def test_changed_test_source_manifest_cannot_be_accepted_as_lock_only_change(self):
        item = self.spec['reports']['fastmcp_2_12_4']['source_file_manifests']; data = json.loads(Path(item['path']).read_text())
        key = next(k for k in data['candidate'] if k.startswith('tests/'))
        data['candidate'][key] = '0'*64
        self.replace_artifact('source_file_manifests', json.dumps(data).encode())
        with self.assertRaisesRegex(ValueError, 'beyond the lock file'): self.invoke()

    def test_human_edited_output_is_preserved_and_conflict_reported(self):
        self.invoke(); path = self.run/'reviews/fastmcp_2_12_4.md'; path.write_text('human edit')
        with self.assertRaisesRegex(ValueError, 'output changed'): self.invoke()
        self.assertEqual(path.read_text(), 'human edit')

    def test_changed_inputs_cannot_resume_same_job(self):
        self.invoke(_interrupt_after=['collect']); self.spec['reports']['fastmcp_2_12_4']['scope'] += ' changed'; self.write_spec()
        with self.assertRaisesRegex(ValueError, 'inputs or implementation changed'): self.invoke()

    def test_unbound_previous_sqlite_state_is_not_overwritten(self):
        self.run.mkdir(); p = self.run/'workbench.sqlite'; p.write_text('unbound state')
        with self.assertRaisesRegex(ValueError, 'Unbound prior state'): self.invoke()
        self.assertEqual(p.read_text(), 'unbound state')

    def test_skipped_test_is_not_promoted_to_compatibility_pass(self):
        item = self.spec['reports']['fastmcp_2_12_4']['candidate_junit']; xml = ET.fromstring(Path(item['path']).read_bytes())
        ET.SubElement(next(xml.iter('testcase')), 'skipped')
        self.replace_artifact('candidate_junit', ET.tostring(xml)); result = self.invoke()
        row = next(r for r in result['reviews'] if r['report_id'] == 'fastmcp_2_12_4')
        self.assertEqual(row['status'], 'compatibility_failed_or_incomplete')

    def test_missing_compatibility_remains_explicitly_unverified(self):
        result = run_workbench(ROOT, MANIFEST, self.run, ['fastmcp_2_12_4'])
        self.assertEqual(result['reviews'][0]['status'], 'ready_for_scoped_tests')


if __name__ == '__main__': unittest.main()
