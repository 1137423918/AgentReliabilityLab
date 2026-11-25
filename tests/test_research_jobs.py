"""Durable retrieval invariants using actual LlamaIndex and fixture embeddings."""
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from test_research_library import FixtureEmbedding
from agent_lab.research_library import ingest, citation
from agent_lab.research_jobs import batch_status, run_batch_job


class JobControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.store = self.root/'store'; self.state = self.root/'job'; self.output = self.root/'results.jsonl'
        text = b'Sonar detection and persistent checkpoint recovery source.'
        (self.root/'paper.txt').write_bytes(text)
        self.manifest = self.root/'sources.json'
        self.manifest.write_text(json.dumps({'version':1,'sources':[{'id':'paper','path':'paper.txt','title':'paper',
            'kind':'fixture','url':'https://example.com/paper','sha256':hashlib.sha256(text).hexdigest()}]}))
        self.model = FixtureEmbedding(); ingest(self.manifest,self.store,self.model)
        self.queries = self.root/'queries.jsonl'
        self.queries.write_text(''.join(json.dumps({'id':str(i),'query':q})+'\n' for i,q in enumerate(['sonar detection','checkpoint recovery','source provenance'])))
    def tearDown(self): self.temp.cleanup()
    def run_job(self, **kwargs):
        return run_batch_job(self.store,self.queries,self.output,self.model,state_dir=self.state,**kwargs)
    def interrupt(self, **kwargs):
        def stop(_): raise RuntimeError('after durable result')
        with self.assertRaisesRegex(RuntimeError,'after durable result'): self.run_job(_after_commit=stop,**kwargs)
        self.assertFalse(self.output.exists()); self.assertEqual(batch_status(self.state)['completed_queries'],1)

    def test_resume_skips_durable_rows_and_completed_job_is_zero_query_replay(self):
        before=self.model.calls; self.interrupt(); self.assertEqual(self.model.calls-before,1)
        result=self.run_job(resume=True); self.assertEqual(self.model.calls-before,3)
        self.assertEqual(result['status'],'published'); self.assertEqual(result['attempts'],{'completed':3})
        before=self.model.calls; raw=self.output.read_bytes(); self.run_job(resume=True)
        self.assertEqual(self.model.calls,before); self.assertEqual(self.output.read_bytes(),raw)
        for row in map(json.loads,raw.splitlines()):
            for response in row['modes'].values():
                for item in response['results']: self.assertEqual(citation(self.store,item['citation_id'])['excerpt'],item['excerpt'])

    def test_resume_requires_opt_in_and_exact_identity_before_queries(self):
        self.interrupt(); before=self.model.calls
        with self.assertRaises(FileExistsError): self.run_job()
        for options in [{'top_k':2},{'modes':['semantic']},{'attempt_limit':4}]:
            with self.subTest(options=options),self.assertRaisesRegex(ValueError,'identity changed'): self.run_job(resume=True,**options)
        original=self.queries.read_bytes(); self.queries.write_bytes(original+b'\n')
        with self.assertRaisesRegex(ValueError,'identity changed'): self.run_job(resume=True)
        self.queries.write_bytes(original)
        with patch('agent_lab.research_jobs._code_identity',return_value={'changed':True}):
            with self.assertRaisesRegex(ValueError,'identity changed'): self.run_job(resume=True)
        self.assertEqual(self.model.calls,before)

    def test_resume_uses_captured_generation_after_active_collection_changes(self):
        self.interrupt(); original=batch_status(self.state)['generation']
        spec=json.loads(self.manifest.read_text()); raw=b'New unrelated edition of the document.'
        (self.root/'paper.txt').write_bytes(raw); spec['sources'][0]['sha256']=hashlib.sha256(raw).hexdigest(); self.manifest.write_text(json.dumps(spec))
        self.assertNotEqual(ingest(self.manifest,self.store,self.model)['generation'],original)
        self.run_job(resume=True)
        rows=[json.loads(x) for x in self.output.read_bytes().splitlines()]
        self.assertTrue(all(r['generation']==original for r in rows))
        self.assertTrue(all('Sonar' in r['modes']['semantic']['results'][0]['excerpt'] for r in rows))

    def test_unknown_attempt_stays_charged_and_fixed_budget_cannot_be_increased(self):
        self.interrupt(); db=sqlite3.connect(self.state/'batch.sqlite')
        with db: db.execute("INSERT INTO attempts(position,status) VALUES(1,'reserved')")
        db.close(); before=self.model.calls
        with self.assertRaisesRegex(RuntimeError,'budget exhausted'): self.run_job(resume=True)
        status=batch_status(self.state); self.assertEqual(status['attempts'],{'completed':2,'unknown':1})
        self.assertEqual(status['attempts_remaining'],0); self.assertEqual(self.model.calls-before,1)
        with self.assertRaisesRegex(ValueError,'identity changed'): self.run_job(resume=True,attempt_limit=4)
        self.assertFalse(self.output.exists())

    def test_failed_query_charged_but_reserved_extra_capacity_can_finish(self):
        self.interrupt(attempt_limit=4)
        with patch('agent_lab.research_jobs.ResearchSnapshot.search_modes',side_effect=RuntimeError('query failed')):
            with self.assertRaisesRegex(RuntimeError,'query failed'): self.run_job(resume=True,attempt_limit=4)
        status=self.run_job(resume=True,attempt_limit=4)
        self.assertEqual(status['attempts'],{'completed':3,'failed':1}); self.assertEqual(status['attempts_remaining'],0)

    def test_changed_saved_result_is_rejected_without_more_queries(self):
        self.interrupt(); before=self.model.calls; db=sqlite3.connect(self.state/'batch.sqlite')
        with db: db.execute("UPDATE results SET payload=?",(b'{}',))
        db.close()
        with self.assertRaisesRegex(ValueError,'fingerprint changed'): self.run_job(resume=True)
        self.assertEqual(self.model.calls,before)

    def test_publication_failure_recovers_without_retrieval_and_never_clobbers(self):
        with patch('agent_lab.research_jobs._publish',side_effect=OSError('publish unavailable')):
            with self.assertRaisesRegex(OSError,'publish unavailable'): self.run_job()
        self.assertEqual(batch_status(self.state)['status'],'ready'); before=self.model.calls
        self.output.write_bytes(b'caller file')
        with self.assertRaises(FileExistsError): self.run_job(resume=True)
        self.assertEqual(self.output.read_bytes(),b'caller file'); self.assertEqual(self.model.calls,before)
        self.output.unlink(); self.run_job(resume=True); self.assertEqual(self.model.calls,before)

    def test_matching_published_file_recovers_after_post_link_commit_failure(self):
        import agent_lab.research_jobs as jobs
        publish=jobs._publish
        def stop(output,payload): publish(output,payload); raise OSError('after final link')
        with patch('agent_lab.research_jobs._publish',side_effect=stop):
            with self.assertRaisesRegex(OSError,'after final link'): self.run_job()
        raw=self.output.read_bytes(); before=self.model.calls; self.run_job(resume=True)
        self.assertEqual(self.model.calls,before); self.assertEqual(self.output.read_bytes(),raw)

    def test_legacy_partial_and_symlink_controls_are_not_adopted(self):
        partial=self.output.with_name(self.output.name+'.partial'); partial.write_text('legacy')
        with self.assertRaisesRegex(FileExistsError,'Legacy partial'): self.run_job()
        partial.unlink(); (self.state/'batch.sqlite').symlink_to(self.root/'elsewhere')
        with self.assertRaisesRegex(ValueError,'regular files'): self.run_job()

    def test_sigkill_releases_writer_lock_and_new_process_resumes(self):
        marker=self.root/'committed'; source=Path(__file__).resolve().parents[1]
        code='''from pathlib import Path
import json,sys,time
from test_research_library import FixtureEmbedding
from agent_lab.research_jobs import run_batch_job
root=Path(sys.argv[1]);resume=sys.argv[2]=='resume';model=FixtureEmbedding()
def pause(position):
 (root/'committed').write_text(str(position));time.sleep(30)
r=run_batch_job(root/'store',root/'queries.jsonl',root/'results.jsonl',model,state_dir=root/'job',resume=resume,_after_commit=None if resume else pause)
(root/'recovered.json').write_text(json.dumps({'result':r,'query_calls':model.calls}))
'''
        env=dict(os.environ,PYTHONPATH=str(source)+':'+str(source/'tests'))
        child=subprocess.Popen([sys.executable,'-c',code,str(self.root),'start'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+20
            while not marker.exists() and child.poll() is None and time.monotonic()<deadline: time.sleep(.05)
            self.assertTrue(marker.exists(),child.stderr.read().decode() if child.poll() is not None else 'no commit')
            before=self.model.calls
            with self.assertRaises(BlockingIOError): self.run_job(resume=True)
            self.assertEqual(self.model.calls,before)
        finally:
            if child.poll() is None: child.kill()
            child.wait(timeout=5); child.stderr.close()
        subprocess.run([sys.executable,'-c',code,str(self.root),'resume'],env=env,check=True,capture_output=True,timeout=30)
        recovered=json.loads((self.root/'recovered.json').read_text())
        self.assertEqual(recovered['query_calls'],2); self.assertEqual(recovered['result']['completed_queries'],3)


if __name__ == '__main__': unittest.main()
