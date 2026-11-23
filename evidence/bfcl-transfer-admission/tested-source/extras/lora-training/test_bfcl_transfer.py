import copy
from pathlib import Path
import tempfile
import unittest

from benchmarks.prepare_bfcl_transfer import (choose, make_prompt, normal,
                                             prompt_constants, question_messages,
                                             sequence, text_components)


class TransferAdmissionTests(unittest.TestCase):
    def test_nfkc_case_and_whitespace(self):
        self.assertEqual(normal('  ＡＢＣ\nDEF '), 'abc def')

    def test_exact_short_text_and_shared_id_groups(self):
        components, _ = text_components([('protected', ('book it',)),
                                         ('new', ('book it',)),
                                         ('shared-id', ('old text',)),
                                         ('shared-id', ('very different text',))], 100)
        self.assertEqual(components['protected'], components['new'])
        self.assertNotEqual(components['new'], components['shared-id'])

    def test_near_groups_are_transitive(self):
        a = 'one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'
        b = a + ' extra'
        c = b + ' final'
        components, stats = text_components([('a', (a,)), ('b', (b,)), ('c', (c,))], 100)
        self.assertEqual(len(set(components.values())), 1)
        self.assertGreater(stats['near_edges'], 0)

    def test_lexical_pair_budget_fails_closed(self):
        with self.assertRaisesRegex(AssertionError, 'pair cap'):
            text_components([('a', ('one two three four five six seven eight',)),
                             ('b', ('one two three four five six seven nine',))], 0)

    def test_gold_is_rejected(self):
        row = self.row()
        row['possible_answer'] = {'fn': {'x': [1]}}
        with self.assertRaises(AssertionError):
            question_messages(row)

    def test_multiturn_is_rejected(self):
        row = self.row()
        row['question'].append([{'role': 'user', 'content': 'next'}])
        with self.assertRaisesRegex(AssertionError, 'single-turn'):
            question_messages(row)

    def test_selection_is_order_independent_with_unique_components(self):
        rows = [{'id': str(i), 'category': c, 'eligible': i != 4,
                 'component_sha256': str(i // 2)} for c in ['a', 'b'] for i in range(8)]
        first = choose(rows, {'a': 2, 'b': 2}, 'frozen')
        second = choose(list(reversed(rows)), {'a': 2, 'b': 2}, 'frozen')
        self.assertEqual(first, second)
        self.assertEqual(len({r['component_sha256'] for r in first}), 4)
        self.assertTrue(all(r['eligible'] for r in first))

    def test_quota_does_not_fall_back(self):
        with self.assertRaisesRegex(AssertionError, 'Insufficient'):
            choose([{'id': 'one', 'category': 'a', 'eligible': True,
                     'component_sha256': 'only'}], {'a': 2}, 'seed')

    def test_prompt_composition_keeps_input_unchanged(self):
        row = self.row()
        row['question'][0].insert(0, {'role': 'system', 'content': 'Original system'})
        original = copy.deepcopy(row)
        values = {'OUTPUT_FORMAT_MAPPING': {'python': '[fn(x=1)]'},
                  'PARAM_TYPE_MAPPING': {'python': ''},
                  'PROMPT_STYLE_TEMPLATES': {'classic': {'persona': 'P', 'task': 'T',
                      'tool_call_no_tag': '{output_format}{param_types}',
                      'multiturn_behavior': 'M', 'available_tools': '{format}:{functions}'}},
                  '_PLAINTEXT_SYSTEM_PROMPT_TEMPLATE': '{persona}{task}|{tool_call_format}|{multiturn_behavior}|{available_tools}'}
        messages = make_prompt(row, values)
        self.assertEqual(row, original)
        self.assertEqual(len(messages), 2)
        self.assertTrue(messages[0]['content'].startswith('PT|[fn(x=1)]|M|json:'))
        self.assertTrue(messages[0]['content'].endswith('\n\nOriginal system'))

    def test_literal_constants_do_not_execute_source(self):
        source = "raise RuntimeError('must not run')\n"
        source += "OUTPUT_FORMAT_MAPPING = {}\nPARAM_TYPE_MAPPING = {}\nPROMPT_STYLE_TEMPLATES = {}\n_PLAINTEXT_SYSTEM_PROMPT_TEMPLATE = 'x'\n"
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'prompts.py'
            path.write_text(source)
            self.assertEqual(prompt_constants(path)['_PLAINTEXT_SYSTEM_PROMPT_TEMPLATE'], 'x')

    @staticmethod
    def row():
        return {'id': 'test_1', 'question': [[{'role': 'user', 'content': 'Use fn with x one'}]],
                'function': [{'name': 'fn', 'parameters': {'type': 'dict', 'properties': {'x': {'type': 'integer'}}}}]}


if __name__ == '__main__':
    unittest.main()
