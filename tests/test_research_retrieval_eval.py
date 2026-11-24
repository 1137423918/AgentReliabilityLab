"""Analytically known binary retrieval cases; no neural runtime imported."""
import importlib.util
import math
import json
from pathlib import Path
import tempfile
import unittest

_spec=importlib.util.spec_from_file_location('retrieval_eval',Path(__file__).resolve().parents[1]/'benchmarks/research_retrieval_eval.py')
evaluation=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(evaluation)


class RetrievalMetricControls(unittest.TestCase):
    def test_multiple_relevant_documents_missing_slots_and_rank_cutoffs(self):
        x=evaluation.query_metrics({'a','b'},['irrelevant','a','b'])
        self.assertEqual(x['recall@1'],0);self.assertEqual(x['hit@1'],0)
        self.assertEqual(x['recall@3'],1);self.assertAlmostEqual(x['precision@3'],2/3)
        self.assertAlmostEqual(x['ndcg@3'],0.6934264036172708);self.assertEqual(x['mrr@3'],.5)
        self.assertEqual(x['precision@10'],.2);self.assertEqual(x['mrr@10'],.5)
    def test_all_queries_are_required_and_missing_results_still_score_zero(self):
        qrels={'q1':{'a':1},'q2':{'b':1}}
        result=evaluation.evaluate(qrels,{'method':{'q1':['a'],'q2':[]}})
        self.assertEqual(result['aggregate']['method']['recall@10'],.5)
        with self.assertRaisesRegex(ValueError,'coverage'):evaluation.evaluate(qrels,{'method':{'q1':['a']}})
        with self.assertRaisesRegex(ValueError,'Repeated'):evaluation.query_metrics({'a'},['a','a'])
        with self.assertRaisesRegex(ValueError,'binary'):evaluation.evaluate({'q':{'a':2}},{'m':{'q':['a']}})
    def test_query_id_cannot_be_scored_with_a_different_question(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'batch.jsonl';generation='a'*64
            response={'generated_answer':False,'generation':generation,'results':[]}
            row={'id':'q','query_sha256':'wrong','generation':generation,'modes':{m:response for m in evaluation.METHODS}}
            path.write_text(json.dumps(row)+'\n')
            with self.assertRaisesRegex(ValueError,'fingerprint'):
                evaluation.read_batch(path,{'source':'doc'},{'q':{'doc':1}},{'q':'expected'})
    def test_trec_export_preserves_the_supplied_rank_order_without_score_ties(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'trec';evaluation.write_trec(root,{'q':{'a':1}},{'m':{'q':['z','a','b']}})
            rows=[line.split() for line in (root/'m.top3.run').read_text().splitlines()]
            self.assertEqual([r[2] for r in rows],['z','a','b']);self.assertEqual([r[4] for r in rows],['3','2','1'])
            self.assertEqual((root/'qrels.txt').read_text(),'q 0 a 1\n')


if __name__=='__main__':unittest.main()
