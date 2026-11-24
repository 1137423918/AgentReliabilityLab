"""Local document intake contracts; no model or network calls."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from agent_lab.research_intake import prepare
from agent_lab.research_library import load_sources


class IntakeControls(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.docs=self.root/'docs';self.docs.mkdir();self.output=self.root/'bundle'
    def tearDown(self):self.temp.cleanup()
    def test_snapshot_preserves_CRLF_unicode_and_hash_and_is_loadable(self):
        raw='资料\r\nExact source.\r\n'.encode();(self.docs/'研究 note.md').write_bytes(raw)
        report=prepare(self.docs,self.output,'https://example.com/commit/docs');rows=load_sources(self.output/'collection.json')
        self.assertEqual(report['documents'],1);self.assertEqual(next(iter(rows.values()))['raw'],raw)
        metadata=next(iter(rows.values()))['metadata'];self.assertEqual(metadata['sha256'],hashlib.sha256(raw).hexdigest());self.assertIn('%E7%A0%94%E7%A9%B6%20note.md',metadata['url'])
    def test_ids_stable_for_content_updates_and_nested_paths_distinct(self):
        (self.docs/'a').mkdir();(self.docs/'a/x.md').write_text('first');(self.docs/'x.md').write_text('other')
        prepare(self.docs,self.output,'https://example.com/');before=json.loads((self.output/'collection.json').read_text())['sources']
        (self.docs/'a/x.md').write_text('changed');other=self.root/'second';prepare(self.docs,other,'https://example.com/');after=json.loads((other/'collection.json').read_text())['sources']
        self.assertEqual([r['id'] for r in before],[r['id'] for r in after]);self.assertNotEqual(before[0]['id'],before[1]['id']);self.assertNotEqual(before[0]['sha256'],after[0]['sha256'])
    def test_hidden_and_unsupported_files_are_not_ingested(self):
        (self.docs/'keep.bib').write_text('@article{key}');(self.docs/'.secret.txt').write_text('private');(self.docs/'binary.pdf').write_bytes(b'PDF')
        prepare(self.docs,self.output,'https://example.com/');self.assertEqual(len(load_sources(self.output/'collection.json')),1)
    def test_symlink_sources_rejected_without_partial_output(self):
        (self.docs/'a.md').symlink_to('/etc/hosts')
        with self.assertRaisesRegex(ValueError,'symlink'):prepare(self.docs,self.output,'https://example.com/')
        self.assertFalse(self.output.exists())
    def test_output_inside_source_or_existing_is_rejected(self):
        (self.docs/'a.md').write_text('source')
        with self.assertRaisesRegex(ValueError,'outside'):prepare(self.docs,self.docs/'output','https://example.com/')
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError,'new output'):prepare(self.docs,self.output,'https://example.com/')
    def test_empty_invalid_UTF8_oversized_and_nonHTTPS_rejected(self):
        p=self.docs/'a.txt'
        for raw in [b'',b'\xff',b'x'*524289]:
            p.write_bytes(raw)
            with self.assertRaises((ValueError,UnicodeError)):prepare(self.docs,self.output,'https://example.com/')
            self.assertFalse(self.output.exists())
        p.write_text('valid')
        with self.assertRaisesRegex(ValueError,'HTTPS'):prepare(self.docs,self.output,'file:///docs')

if __name__=='__main__':unittest.main()
