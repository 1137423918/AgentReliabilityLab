"""Real LlamaIndex batch/snapshot lifecycle controls; fixture embeddings only."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from llama_index.core.bridge.pydantic import PrivateAttr
from agent_lab.research_library import ResearchSnapshot, citation, ingest, open_generation, search, search_batch
from test_research_library import FixtureEmbedding


class BatchEmbedding(FixtureEmbedding):
    _batches = PrivateAttr(default_factory=list)
    @property
    def batches(self): return list(self._batches)
    def _get_text_embeddings(self, texts):
        self._batches.append(len(texts))
        return [self._get_text_embedding(text) for text in texts]


class SnapshotControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name); self.store = self.root/'store'
        self.model = BatchEmbedding(embed_batch_size=4); self.rows = {}
        self.put('alpha', 'Alpha sonar recovery evidence.\r\nExact source line.\r\n')
        self.put('beta', 'Beta checkpoint storage and interrupted process evidence.\n')
    def tearDown(self): self.temp.cleanup()
    def put(self, key, text):
        raw = text.encode(); (self.root/(key+'.txt')).write_bytes(raw)
        self.rows[key] = {'id': key, 'path': key+'.txt', 'title': key, 'kind': 'test_fixture',
                          'url': 'https://example.com/'+key, 'sha256': hashlib.sha256(raw).hexdigest()}
    def manifest(self):
        p=self.root/'sources.json'; p.write_text(json.dumps({'version':1,'sources':list(self.rows.values())})); return p
    def queries(self, rows):
        p=self.root/'queries.jsonl'; p.write_text(''.join(json.dumps(x)+'\n' for x in rows)); return p
    def test_invalid_parser_offsets_fail_before_embedding(self):
        from unittest.mock import patch
        from llama_index.core.node_parser import TokenTextSplitter
        class Misaligned(TokenTextSplitter):
            def get_nodes_from_documents(self,*args,**kwargs):
                nodes=super().get_nodes_from_documents(*args,**kwargs)
                nodes[0].start_char_idx+=1
                return nodes
        parser=Misaligned(chunk_size=256,chunk_overlap=32,tokenizer=self.model.tokens)
        with patch('agent_lab.research_library.parser_for',return_value=parser):
            with self.assertRaisesRegex(ValueError,'Chunk offsets'):ingest(self.manifest(),self.store,self.model)
        self.assertEqual(self.model.calls,0)
        self.assertFalse((self.store/'CURRENT.json').exists())
    def test_bulk_ingestion_fills_batches_across_documents_and_reuses_unchanged(self):
        for i in range(6): self.put('extra'+str(i), 'Distinct batch document '+str(i))
        ingest(self.manifest(),self.store,self.model)
        self.assertEqual(self.model.batches,[4,4]); self.assertEqual(self.model.calls,8)
        old=ResearchSnapshot(self.store,self.model).search('checkpoint',mode='lexical')['results'][0]
        self.put('alpha','Updated sonar document')
        ingest(self.manifest(),self.store,self.model)
        self.assertEqual(self.model.batches,[4,4,1]); self.assertEqual(self.model.calls,9)
        self.assertEqual(citation(self.store,old['citation_id'])['excerpt'],old['excerpt'])
    def test_multi_mode_reuses_one_query_embedding_and_matches_single_requests(self):
        ingest(self.manifest(),self.store,self.model); snapshot=ResearchSnapshot(self.store,self.model); before=self.model.calls
        grouped=snapshot.search_modes('sonar evidence',top_k=10)
        self.assertEqual(self.model.calls-before,1)
        for mode in ['lexical','semantic','hybrid']:
            self.assertEqual(grouped[mode],search(self.store,'sonar evidence',self.model,mode=mode,top_k=10))
        before=self.model.calls
        self.assertFalse(snapshot.search('x',source_id='absent')['results'])
        snapshot.search('checkpoint',mode='lexical',source_id='beta')
        self.assertEqual(self.model.calls,before)
    def test_captured_snapshot_keeps_old_sources_after_new_generation_publication(self):
        ingest(self.manifest(),self.store,self.model); old=ResearchSnapshot(self.store,self.model)
        first=old.search('sonar',mode='lexical')['results'][0]
        self.put('alpha','Changed alpha edition with sonar evidence')
        ingest(self.manifest(),self.store,self.model)
        retained=old.search('sonar',mode='lexical')['results'][0]
        self.assertEqual(retained['excerpt'],first['excerpt']); self.assertEqual(retained['generation'],old.generation)
        self.assertFalse(retained['is_current_generation'])
        new=ResearchSnapshot(self.store,self.model)
        self.assertNotEqual(new.generation,old.generation)
        self.assertNotEqual(new.search('sonar',mode='lexical')['results'][0]['excerpt'],first['excerpt'])
    def test_collection_above_previous_256_limit_uses_actual_framework(self):
        for i in range(255): self.put('source'+str(i),'Distinct scientific abstract number '+str(i))
        result=ingest(self.manifest(),self.store,self.model)
        self.assertEqual(len(result['added']),257); self.assertEqual(open_generation(self.store)[1]['node_count'],257)
        self.assertEqual(sum(self.model.batches),257)
        self.assertEqual(len(ResearchSnapshot(self.store,self.model).search('scientific',mode='lexical',top_k=10)['results']),10)
    def test_batch_prevalidates_ids_and_never_overwrites_complete_output(self):
        ingest(self.manifest(),self.store,self.model); before=self.model.calls; output=self.root/'batch.jsonl'
        duplicate=self.queries([{'id':'one','query':'sonar'},{'id':'one','query':'checkpoint'}])
        with self.assertRaisesRegex(ValueError,'Repeated query'):search_batch(self.store,duplicate,output,self.model)
        self.assertEqual(self.model.calls,before); self.assertFalse(output.exists())
        queries=self.queries([{'id':'one','query':'sonar'},{'id':'two','query':'checkpoint'}])
        result=search_batch(self.store,queries,output,self.model); self.assertEqual(result['queries'],2)
        self.assertEqual(self.model.calls-before,2)
        rows=[json.loads(l) for l in output.read_text().splitlines()];self.assertEqual([r['id'] for r in rows],['one','two'])
        for row in rows:
            for response in row['modes'].values():
                self.assertEqual(len({x['source_id'] for x in response['results']}),len(response['results']))
                for item in response['results']: self.assertEqual(citation(self.store,item['citation_id'])['excerpt'],item['excerpt'])
        before=self.model.calls
        with self.assertRaises(FileExistsError):search_batch(self.store,queries,output,self.model)
        self.assertEqual(self.model.calls,before)
    def test_failed_batch_retains_partial_records_without_publishing_final(self):
        ingest(self.manifest(),self.store,self.model)
        class Failing(FixtureEmbedding):
            _queries=PrivateAttr(default=0)
            def _get_query_embedding(self,text):
                self._queries+=1
                if self._queries==2:raise RuntimeError('fixture query failure')
                return super()._get_query_embedding(text)
        model=Failing(); output=self.root/'batch.jsonl'
        queries=self.queries([{'id':'one','query':'sonar'},{'id':'two','query':'checkpoint'}])
        with self.assertRaisesRegex(RuntimeError,'fixture query failure'):search_batch(self.store,queries,output,model)
        self.assertFalse(output.exists()); partial=output.with_name(output.name+'.partial')
        self.assertEqual([json.loads(l)['id'] for l in partial.read_text().splitlines()],['one'])
        with self.assertRaises(FileExistsError):search_batch(self.store,queries,output,model)


if __name__=='__main__':unittest.main()
