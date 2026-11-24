"""Offline report presentation and data-boundary controls, without inference."""
import copy
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest

from agent_lab.research_report import ReportError, write_report
from agent_lab.research_view import reading_html


def fixture():
    return {'version': 1, 'semantic_entailment_checked': False,
            'summary': {'runs': 3, 'recorded_submissions': 1, 'recorded_uncompleted': 1, 'export_errors': 1},
            'runs': [
                {'question': '已保存的论文问题', 'export_status': 'ready', 'recorded_status': 'submitted',
                 'answer': '这是原模型回答，并非正确性认证。', 'model_submission_status': 'supported',
                 'source_generation': 'a' * 64, 'model': 'recorded-model', 'diagnostics': [],
                 'requests': {'reserved': 2, 'limit': 6, 'saved_complete': 2, 'without_saved_complete_response': 0},
                 'references': [{'ref': 'r1', 'title': '归档论文', 'source_url': 'https://example.com/paper.pdf#page=3',
                                 'is_current_generation': False, 'citation_id': 'a' * 64 + ':citation',
                                 'source_sha256': 'b' * 64, 'pdf': {'page_number': 3, 'page_label': 'iii', 'sha256': 'c' * 64}}]},
                {'question': '未完成的问题', 'export_status': 'ready', 'recorded_status': 'turn_limit', 'answer': None,
                 'references': [], 'diagnostics': ['empty_answer', 'submission_rejected']},
                {'export_status': 'error', 'recorded_status': None, 'answer': None,
                 'references': [], 'diagnostics': ['artifact_or_source_unavailable']}]}


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags = []; self.current = None; self.blocks = {'style': '', 'script': '', 'pre': ''}
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag in self.blocks: self.current = tag

    def handle_endtag(self, tag):
        if tag == self.current: self.current = None

    def handle_data(self, data):
        if self.current: self.blocks[self.current] += data


class ReadingView(unittest.TestCase):
    def test_preserves_three_record_states_and_archived_page_identity(self):
        report = fixture(); before = copy.deepcopy(report); text = reading_html(report); page = Page(text)
        self.assertEqual(report, before)
        self.assertEqual([a['data-status'] for t, a in page.tags if t == 'article'], ['submitted', 'unfinished', 'error'])
        self.assertIn('PDF物理第3页', text); self.assertIn('归档资料版本', text)
        self.assertIn('未自动验证陈述正确性', text); self.assertIn('回答为空', text)
        self.assertIn('turn_limit', page.blocks['pre'])

    def test_markup_in_question_answer_and_title_is_text_and_payload_roundtrips(self):
        report = fixture(); attack = '</pre><script>window.attacked=1</script><img src=x onerror="window.attacked=2">\u2028'
        report['runs'][0].update(question=attack, answer=attack)
        report['runs'][0]['references'][0]['title'] = attack
        page = Page(reading_html(report))
        self.assertEqual(json.loads(page.blocks['pre']), report)
        self.assertEqual(len([1 for t, _ in page.tags if t == 'script']), 1)
        self.assertFalse(any(t in ['img', 'iframe', 'object', 'base'] for t, _ in page.tags))
        self.assertFalse(any(k.startswith('on') for _, a in page.tags for k in a))

    def test_inline_code_is_hash_bound_and_has_no_external_asset_endpoints(self):
        import base64
        page = Page(reading_html(fixture()))
        meta = next(a['content'] for t, a in page.tags if t == 'meta' and a.get('http-equiv') == 'Content-Security-Policy')
        for name in ['script', 'style']:
            digest = base64.b64encode(hashlib.sha256(page.blocks[name].encode()).digest()).decode()
            self.assertIn("'sha256-" + digest + "'", meta)
        self.assertIn("connect-src 'none'", meta)
        self.assertFalse(any('src' in a or t == 'link' for t, a in page.tags))

    def test_unusable_source_url_rejects_before_creating_output(self):
        for url in ['javascript:alert(1)', 'http://example.com', 'https://user:secret@example.com/paper']:
            report = fixture(); report['runs'][0]['references'][0]['source_url'] = url
            with tempfile.TemporaryDirectory() as root:
                out = Path(root) / 'report'
                with self.assertRaises(ReportError): write_report(report, out)
                self.assertFalse(out.exists())

    def test_manifest_binds_the_complete_standalone_view_and_exact_json(self):
        report = fixture()
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / 'report'; write_report(report, out)
            manifest = json.loads((out / 'report-manifest.json').read_text())
            self.assertEqual(set(manifest['files']), {'reading-report.md', 'reading-report.json', 'reading-report.html'})
            for name, record in manifest['files'].items():
                raw = (out / name).read_bytes(); self.assertEqual(hashlib.sha256(raw).hexdigest(), record['sha256'])
            page = Page((out / 'reading-report.html').read_text())
            self.assertEqual(page.blocks['pre'].encode(), (out / 'reading-report.json').read_bytes())


if __name__ == '__main__': unittest.main()
