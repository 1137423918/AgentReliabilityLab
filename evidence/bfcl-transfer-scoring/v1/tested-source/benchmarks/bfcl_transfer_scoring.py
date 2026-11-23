"""Guarded Python-track BFCL-derived case scoring, without generated execution.

Pinned upstream functions are loaded unchanged from trusted local source. An
outer AST/resource guard rejects eval-bearing expressions before the official
decoder. Rejected cases receive no credit; this is not the full BFCL harness.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import re
from types import SimpleNamespace


class GuardRejected(ValueError):
    pass


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(packed(value)).hexdigest()


def guard_python_response(raw, max_chars=65536, max_nodes=2048, max_depth=64):
    if not isinstance(raw, str) or len(raw) > max_chars:
        raise GuardRejected('response_size_or_type')
    # Match default_decode_ast_prompting's exact wrapping, including its legacy
    # lack of special handling for a ```python language identifier.
    text = raw.strip('`\n ')
    if not text.startswith('['):
        text = '[' + text
    if not text.endswith(']'):
        text += ']'
    try:
        tree = ast.parse(text.strip().strip("'"), mode='eval')
    except SyntaxError:
        return {'syntax_error': True, 'nodes': 0, 'depth': 0}
    except (RecursionError, MemoryError):
        raise GuardRejected('parser_resource_limit')
    stack = [(tree, 0)]
    nodes = depth = 0
    while stack:
        node, level = stack.pop()
        nodes += 1
        depth = max(depth, level)
        if nodes > max_nodes or depth > max_depth:
            raise GuardRejected('AST_resource_limit')
        if isinstance(node, (ast.BinOp, ast.Lambda)):
            raise GuardRejected('eval_bearing_expression')
        stack.extend((child, level+1) for child in ast.iter_child_nodes(node))
    return {'syntax_error': False, 'nodes': nodes, 'depth': depth}


def load_python_scorer(source):
    """Load only pinned trusted definitions, not broad upstream import graphs.

    Caller must verify source file SHA/protocol first. No generated AST is
    compiled or evaluated; only the trusted source module definitions are.
    """
    source = Path(source)
    env = {'ast': ast, 're': re, 'json': json, 'Enum': __import__('enum').Enum,
           'MODEL_CONFIG_MAPPING': {'agentlab/local': SimpleNamespace(underscore_to_dot=False)}}
    identity = {}
    blocked_eval_attempts = []

    def deny_eval(*args, **kwargs):
        blocked_eval_attempts.append(True)
        raise GuardRejected('eval_is_disabled')

    def unsupported(*args, **kwargs):
        raise NotImplementedError('Only the Python track is enabled')

    env.update(eval=deny_eval, java_type_converter=unsupported, js_type_converter=unsupported,
               JAVA_TYPE_CONVERSION={}, JS_TYPE_CONVERSION={})

    def definitions(filename, names=None, assignments=False, classes=False):
        path = source/filename
        raw = path.read_bytes()
        parsed = ast.parse(raw)
        body = []
        found = set()
        for node in parsed.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                if isinstance(node, ast.ClassDef) and not classes:
                    continue
                if names is None or node.name in names:
                    body.append(node)
                    found.add(node.name)
            elif assignments and isinstance(node, (ast.Assign, ast.AnnAssign)):
                body.append(node)
        if names is not None:
            assert found == set(names), (filename, found)
        # Future annotations do not modify any upstream function body.
        future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
        module = ast.fix_missing_locations(ast.Module(body=[future]+body, type_ignores=[]))
        exec(compile(module, str(path), 'exec'), env)
        identity[filename] = {'source_sha256': hashlib.sha256(raw).hexdigest(),
                              'definitions': {node.name: hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
                                              for node in body if isinstance(node, (ast.FunctionDef, ast.ClassDef))}}

    definitions('bfcl_enums.py', names={'Language', 'ReturnFormat', 'ModelStyle'}, classes=True)
    definitions('bfcl_ast_checker.py', assignments=True)
    definitions('bfcl_model_utils.py', names={'default_decode_ast_prompting', 'ast_parse', 'resolve_ast_call', 'resolve_ast_by_type'})
    definitions('bfcl_utils.py', names={'is_empty_output', 'is_function_calling_format_output'})
    definitions('bfcl_eval_runner.py', names={'_evaluate_single_relevance_entry', '_evaluate_single_ast_entry'})

    class Handler:
        def __init__(self):
            self.trace = {'decode_success': False, 'decode_error_type': None,
                          'decoded_call_count': None, 'explicit_empty_call_list': False}

        def decode_ast(self, raw, language, has_tool_call_tag):
            assert language == env['ReturnFormat'].PYTHON and not has_tool_call_tag
            guard_python_response(raw)
            try:
                result = env['default_decode_ast_prompting'](raw, language, has_tool_call_tag)
            except Exception as error:
                self.trace['decode_error_type'] = type(error).__name__
                raise
            valid_format = env['is_function_calling_format_output'](result)
            self.trace.update(decode_success=True, decoded_call_count=len(result) if valid_format else None,
                              explicit_empty_call_list=valid_format and result == [])
            return result

    def score(raw, row, gold, category):
        assert category in {'live_simple', 'live_multiple', 'parallel', 'parallel_multiple', 'irrelevance'}
        initial_eval_attempts = len(blocked_eval_attempts)
        try:
            guard = guard_python_response(raw)
        except GuardRejected as error:
            return {'guarded_valid': False, 'upstream_python_case_valid': None,
                    'guard_rejected': True, 'guard_reason': str(error),
                    'decode_success': False, 'decode_error_type': None,
                    'decoded_call_count': None, 'explicit_empty_call_list': False,
                    'error_type': 'outer_guard_rejection', 'eval_attempts': 0}
        handler = Handler()
        try:
            if category == 'irrelevance':
                result = env['_evaluate_single_relevance_entry'](
                    handler, row['id'], raw, copy.deepcopy(row), 'agentlab/local', category)
            else:
                result = env['_evaluate_single_ast_entry'](
                    handler, row['id'], raw, copy.deepcopy(gold), copy.deepcopy(row),
                    'agentlab/local', category, env['Language'].PYTHON, env['ReturnFormat'].PYTHON, False)
        except Exception as error:
            # Infrastructure/schema errors are not fabricated prediction errors.
            return {'guarded_valid': None, 'upstream_python_case_valid': None,
                    'guard_rejected': False, 'scorer_error_type': type(error).__name__,
                    **handler.trace, 'eval_attempts': len(blocked_eval_attempts)-initial_eval_attempts}
        attempts = len(blocked_eval_attempts)-initial_eval_attempts
        assert attempts == 0, 'A rejected evaluation branch escaped the outer guard'
        assert type(result['valid']) is bool
        return {'guarded_valid': result['valid'], 'upstream_python_case_valid': result['valid'],
                'guard_rejected': False, 'guard_syntax_error': guard['syntax_error'],
                **handler.trace, 'error_type': result.get('error_type'), 'eval_attempts': attempts}

    return score, identity


def canonical_witness(gold):
    """A reference-derived checker control, never a model prediction.

    Keep all cases if a witness fails; do not alter gold, selection or prompts.
    """
    assert isinstance(gold, list) and gold
    calls = []
    for item in gold:
        assert isinstance(item, dict) and len(item) == 1
        name, params = next(iter(item.items()))
        assert isinstance(params, dict)
        arguments = []
        for key, choices in params.items():
            assert isinstance(choices, list) and choices
            if '' in choices:
                continue
            arguments.append(key+'='+repr(choices[0]))
        calls.append(name+'('+', '.join(arguments)+')')
    return '['+', '.join(calls)+']'
