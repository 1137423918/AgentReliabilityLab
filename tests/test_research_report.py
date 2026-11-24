"""Report workflows with actual LlamaIndex/SQLite and scripted, non-neural replies."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from agent_lab.request_budget import RequestBudget, atomic_save, digest
from agent_lab.research_assistant import EvidenceTools, LocalModel, graph_for
from agent_lab.research_library import ingest, open_generation, search, citation
from agent_lab.research_report import build_report, markdown, write_report, ReportError
from test_research_assistant import reply, initial
from test_research_library import FixtureEmbedding


def hashes(directory):
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob('*') if p.is_file()}


class ReportWorkflows(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = self.root / 'store'
        self.model = FixtureEmbedding()
        self.raw = b'Restore the committed checkpoint after interruption.\n'
        (self.root / 'paper.txt').write_bytes(self.raw)
        self.manifest = self.root / 'sources.json'
        self.manifest.write_text(json.dumps({'version': 1, 'sources': [{
            'id': 'paper', 'path': 'paper.txt', 'title': 'Owned report fixture',
            'kind': 'fixture', 'url': 'https://example.com/paper-v1',
            'sha256': hashlib.sha256(self.raw).hexdigest()}]}))
        ingest(self.manifest, self.store, self.model)

    async def asyncTearDown(self):
        self.temp.cleanup()

    async def make_run(self, name='run', *, failed=False, question='How does recovery work?'):
        directory = self.root / name
        directory.mkdir()
        _, generation = open_generation(self.store)
        gen = digest(generation['identity'])
        identity = {'question': question, 'source_generation': gen, 'model': 'scripted-fixture'}
        owner = digest(identity)
        atomic_save(directory / 'run.json', {'identity': identity, 'owner_sha256': owner})
        limits = {'max_requests': 3, 'max_request_bytes': 32768, 'max_total_request_bytes': 98304}
        (directory / 'requests').mkdir()
        budget = RequestBudget(directory / 'requests', owner, limits, create=True)
        final = {'status': 'insufficient_evidence' if failed else 'supported',
                 'answer': '' if failed else 'Restore the committed checkpoint.', 'citations': ['r1']}
        answers = iter([reply('find_passages', {'query': 'checkpoint'}),
                        reply('read_passage', {'ref': 'r1'}), reply(text=json.dumps(final))])

        class HTTP:
            async def post(inner, url, **kwargs):
                sequence = budget.reserve(kwargs['content'], '/v1/chat/completions')
                budget.observe(sequence, 200)
                value = next(answers)
                class Response:
                    def raise_for_status(self): pass
                    def json(self): return copy.deepcopy(value)
                return Response()

        async def call(tool, args):
            if tool == 'search_sources':
                return search(self.store, args['query'], self.model, mode='lexical', top_k=args['top_k'])
            if tool == 'read_citation':
                return citation(self.store, args['citation_id'])
            raise AssertionError(tool)

        evidence = EvidenceTools(call, {'generation': gen, 'sources': []})
        provider = LocalModel(HTTP(), 'http://127.0.0.1/v1', 'fixture', None, 256, 2, directory / 'responses')
        async with AsyncSqliteSaver.from_conn_string(str(directory / 'graph.sqlite')) as saver:
            graph = graph_for(provider, evidence, saver, 3)
            start = initial()
            start['messages'] = [{'role': 'user', 'content': question}]
            state = await graph.ainvoke(start, {'configurable': {'thread_id': owner}, 'recursion_limit': 14})
        result = {key: state[key] for key in ['status', 'final', 'model_turns', 'successful_tools', 'read_refs']}
        result.update(source_generation=gen, model_requests=budget.summary(), saved_complete_response_files=3,
                      reservations_without_complete_saved_response=0, semantic_entailment_checked=False)
        atomic_save(directory / 'result.json', result)
        return directory

    async def test_actual_checkpoint_to_reading_report_without_input_changes_or_network(self):
        directory = await self.make_run()
        before = hashes(directory), hashes(self.store), self.model.calls
        with patch('socket.socket.connect', side_effect=AssertionError('No network allowed')):
            report = build_report([directory], self.store)
        self.assertEqual(report['summary'], {'runs': 1, 'recorded_submissions': 1, 'recorded_uncompleted': 0, 'export_errors': 0})
        text = markdown(report)
        self.assertIn('Restore the committed checkpoint.', text)
        self.assertIn('https://example.com/paper-v1', text)
        self.assertNotIn(str(directory), text)
        self.assertNotIn('excerpt', json.dumps(report))
        self.assertFalse(report['semantic_entailment_checked'])
        self.assertEqual(before, (hashes(directory), hashes(self.store), self.model.calls))

    async def test_failed_submission_exports_diagnostics_and_never_an_answer(self):
        directory = await self.make_run(failed=True)
        report = build_report([directory], self.store)
        row = report['runs'][0]
        self.assertEqual(row['recorded_status'], 'turn_limit')
        self.assertIsNone(row['answer'])
        self.assertEqual(row['diagnostics'], ['empty_answer', 'insufficient_evidence_with_citations', 'submission_rejected'])
        self.assertEqual(report['summary']['recorded_uncompleted'], 1)
        self.assertNotIn('模型报告资料不足', markdown(report))

    async def test_batch_keeps_good_failed_and_unavailable_runs_distinct(self):
        good = await self.make_run('good')
        failed = await self.make_run('failed', failed=True)
        report = build_report([good, failed, self.root / 'missing'], self.store)
        self.assertEqual(report['summary'], {'runs': 3, 'recorded_submissions': 1, 'recorded_uncompleted': 1, 'export_errors': 1})
        self.assertEqual(report['runs'][2]['export_status'], 'error')
        self.assertIsNone(report['runs'][2]['answer'])

    async def test_old_source_generation_remains_explicit_after_new_publication(self):
        directory = await self.make_run()
        raw = b'New version, different material.\n'
        (self.root / 'paper.txt').write_bytes(raw)
        spec = json.loads(self.manifest.read_text())
        spec['sources'][0]['sha256'] = hashlib.sha256(raw).hexdigest()
        self.manifest.write_text(json.dumps(spec))
        ingest(self.manifest, self.store, self.model)
        report = build_report([directory], self.store)
        self.assertEqual(report['summary']['recorded_submissions'], 1)
        self.assertFalse(report['runs'][0]['references'][0]['is_current_generation'])
        self.assertIn('归档版本', markdown(report))

    async def test_result_or_response_tampering_is_not_exported_as_an_answer(self):
        for name in ['result', 'response']:
            directory = await self.make_run(name)
            path = directory / 'result.json' if name == 'result' else next((directory / 'responses').glob('*.json'))
            value = json.loads(path.read_text())
            if name == 'result': value['final']['answer'] = 'Not the recorded answer'
            else: value['response']['choices'][0]['message']['content'] = 'changed'
            path.write_text(json.dumps(value))
            report = build_report([directory], self.store)
            self.assertEqual(report['summary']['export_errors'], 1)
            self.assertIsNone(report['runs'][0]['answer'])

    async def test_changed_archived_source_is_not_exported_as_verified(self):
        directory = await self.make_run()
        root, _ = open_generation(self.store)
        (root / 'sources/paper.txt').write_text('tampered')
        self.assertEqual(build_report([directory], self.store)['summary']['export_errors'], 1)

    async def test_live_sidecar_and_owner_mismatch_refused(self):
        directory = await self.make_run('sidecar')
        Path(str(directory / 'graph.sqlite') + '-wal').write_bytes(b'active')
        self.assertEqual(build_report([directory], self.store)['summary']['export_errors'], 1)
        directory = await self.make_run('owner')
        path = directory / 'run.json'
        meta = json.loads(path.read_text()); meta['identity']['question'] = 'Changed question'; path.write_text(json.dumps(meta))
        self.assertEqual(build_report([directory], self.store)['summary']['export_errors'], 1)

    async def test_report_outputs_are_repeatable_and_do_not_overwrite(self):
        directory = await self.make_run()
        report = build_report([directory], self.store)
        one, two = self.root / 'one', self.root / 'two'
        write_report(report, one); write_report(report, two)
        self.assertEqual(hashes(one), hashes(two))
        with self.assertRaises(FileExistsError): write_report(report, one)
        with self.assertRaises(ReportError): build_report([directory, directory], self.store)

    async def test_question_html_and_markdown_are_displayed_as_text(self):
        directory = await self.make_run(question='<script>alert(1)</script> [click](javascript:bad)')
        text = markdown(build_report([directory], self.store))
        self.assertNotIn('<script>', text)
        self.assertIn('&lt;script&gt;', text)
        self.assertIn('\\[click\\]\\(javascript:bad\\)', text)


if __name__ == '__main__':
    unittest.main()
