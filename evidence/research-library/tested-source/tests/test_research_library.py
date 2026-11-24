"""Real LlamaIndex lifecycle tests with non-neural fixture embeddings."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.bridge.pydantic import PrivateAttr
from agent_lab.research_library import ingest, search, citation, open_generation, terms


class FixtureEmbedding(BaseEmbedding):
    _calls = PrivateAttr(default=0)
    @property
    def fingerprint(self): return {'model': 'fixture-hash-not-neural', 'dimensions': 32}
    @property
    def calls(self): return self._calls
    def tokens(self, text): return text.split()
    def _vector(self, text):
        result = [0.0]*32
        for word in terms(text): result[int(hashlib.sha256(word.encode()).hexdigest()[:8], 16)%32] += 1
        norm = sum(x*x for x in result)**.5 or 1
        return [x/norm for x in result]
    def _get_query_embedding(self, text): self._calls += 1; return self._vector(text)
    async def _aget_query_embedding(self, text): return self._get_query_embedding(text)
    def _get_text_embedding(self, text): self._calls += 1; return self._vector(text)


class LibraryControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name); self.store = self.root/'store'
        self.model = FixtureEmbedding(); self.rows = {}
        self.put('alpha', 'Alpha sonar detection\r\n轻量化论文 source evidence.\r\nExact final line.\r\n')
        self.put('beta', 'Beta repository recovery checkpoint and interrupted process evidence.\n')

    def tearDown(self): self.temp.cleanup()

    def put(self, key, text):
        raw = text.encode(); (self.root/(key+'.txt')).write_bytes(raw)
        self.rows[key] = {'id': key, 'path': key+'.txt', 'title': key, 'kind': 'test_fixture',
                          'url': 'https://example.com/'+key, 'sha256': hashlib.sha256(raw).hexdigest()}

    def manifest(self):
        p = self.root/'sources.json'; p.write_text(json.dumps({'version': 1, 'sources': list(self.rows.values())})); return p

    def test_actual_framework_index_and_exact_CRLF_unicode_citation(self):
        ingest(self.manifest(), self.store, self.model)
        found = search(self.store, 'sonar detection', self.model, mode='semantic', source_id='alpha')
        row = found['results'][0]; original = (self.root/'alpha.txt').read_bytes().decode()
        self.assertEqual(original[row['char_start']:row['char_end']], row['excerpt'])
        self.assertIn('\r\n', row['excerpt']); self.assertEqual(row['line_start'], 1)
        self.assertEqual(citation(self.store, row['citation_id'])['excerpt'], row['excerpt'])

    def test_identical_ingestion_embeds_nothing_and_keeps_current_generation(self):
        first = ingest(self.manifest(), self.store, self.model); before = self.model.calls
        second = ingest(self.manifest(), self.store, self.model)
        self.assertEqual(first['generation'], second['generation']); self.assertFalse(second['published'])
        self.assertEqual(self.model.calls, before)

    def test_incremental_update_add_remove_and_old_citation_version(self):
        ingest(self.manifest(), self.store, self.model)
        old = search(self.store, 'sonar', self.model, source_id='alpha')['results'][0]
        self.put('alpha', 'Changed alpha sonar source,second edition.\n'); self.put('gamma', 'Gamma new material.\n'); del self.rows['beta']
        changed = ingest(self.manifest(), self.store, self.model)
        self.assertEqual(changed['updated'], ['alpha']); self.assertEqual(changed['added'], ['gamma']); self.assertEqual(changed['removed'], ['beta'])
        self.assertFalse(citation(self.store, old['citation_id'])['is_current_generation'])
        before = self.model.calls; removed = search(self.store, 'recovery', self.model, source_id='beta')
        self.assertFalse(removed['results']); self.assertEqual(self.model.calls, before)

    def test_failure_before_publication_preserves_previous_complete_generation(self):
        initial = ingest(self.manifest(), self.store, self.model); self.put('alpha', 'New alpha.\n')
        def fail(_): raise OSError('injected publish interruption')
        with self.assertRaises(OSError): ingest(self.manifest(), self.store, self.model, _before_publish=fail)
        root, _ = open_generation(self.store); self.assertEqual(root.name, initial['generation'])
        self.assertFalse(any(p.name.startswith('.building-') for p in (self.store/'generations').iterdir()))

    def test_changed_source_without_manifest_hash_update_is_rejected(self):
        manifest = self.manifest(); (self.root/'alpha.txt').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'bytes differ'): ingest(manifest, self.store, self.model)

    def test_corrupt_stored_source_or_index_detected(self):
        ingest(self.manifest(), self.store, self.model); root, _ = open_generation(self.store)
        (root/'sources/alpha.txt').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'fingerprint changed'): open_generation(self.store)

    def test_embedded_model_identity_cannot_silently_change(self):
        ingest(self.manifest(), self.store, self.model)
        class Other(FixtureEmbedding):
            @property
            def fingerprint(self): return {'model': 'different-fixture', 'dimensions': 32}
        with self.assertRaisesRegex(ValueError, 'Embedding model'): ingest(self.manifest(), self.store, Other())

    def test_lexical_retrieval_and_source_filter_do_not_call_embedding(self):
        ingest(self.manifest(), self.store, self.model); before = self.model.calls
        row = search(self.store, 'checkpoint', self.model, mode='lexical', source_id='beta')
        self.assertEqual(row['results'][0]['source_id'], 'beta'); self.assertEqual(self.model.calls, before)

    def test_invalid_citation_and_unknown_nodes_do_not_escape_store(self):
        ingest(self.manifest(), self.store, self.model); root, _ = open_generation(self.store)
        for value in ['../file:node', '0'*64+':'+ '1'*64, root.name+':'+ '1'*64]:
            with self.assertRaises((ValueError, FileNotFoundError)): citation(self.store, value)

    def test_changed_source_url_republishes_metadata_without_losing_other_docs(self):
        ingest(self.manifest(), self.store, self.model); self.rows['alpha']['url'] = 'https://example.com/alpha-v2'
        updated = ingest(self.manifest(), self.store, self.model)
        self.assertEqual(updated['updated'], ['alpha']); self.assertEqual(updated['unchanged'], 1)
        self.assertEqual(len(open_generation(self.store)[1]['identity']['sources']), 2)


if __name__ == '__main__': unittest.main()
