"""Export stopped, trusted research-assistant runs without invoking their graph.

Reads completed SQLite snapshots and immutable paper citations. This is a local
reading report, not a model retry, new evaluation or proof of semantic truth.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import html
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote, urlsplit

from .request_budget import digest


class ReportError(ValueError):
    pass


def read_json(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024**2:
        raise ReportError('Run JSON is missing or too large')
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ReportError('Expected a run object')
    return value


def checkpoint_values(database, owner):
    """Read a closed snapshot in one transaction, with no migrations or sidecars."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    if database.is_symlink() or not database.is_file() or database.stat().st_size > 64 * 1024**2:
        raise ReportError('Checkpoint is missing or too large')
    for suffix in ['-wal', '-shm', '-journal']:
        sidecar = Path(str(database) + suffix)
        if sidecar.exists() and sidecar.stat().st_size:
            raise ReportError('Stop the writer and close its SQLite connections before export')
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro&immutable=1', uri=True)) as connection:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        saver = SqliteSaver(connection)
        saver.is_setup = True  # setup() migrates tables; this reader must never do that.
        saved = saver.get_tuple({'configurable': {'thread_id': owner}})
        if saved is None:
            raise ReportError('No checkpoint for this run identity')
        values = saved.checkpoint['channel_values']
        if saved.pending_writes or values.get('pending') or values.get('status') == 'running':
            raise ReportError('Checkpoint is not a closed terminal result')
        return values


def request_counts(directory, owner, result):
    journal = read_json(directory / 'requests/model-requests.json')
    payload = {k: v for k, v in journal.items() if k != 'checksum'}
    summary = result['model_requests']
    if digest(payload) != journal['checksum'] or journal['identity'] != {
        k: summary[k] for k in ['journal_id', 'owner_sha256', 'limits']
    } or summary['owner_sha256'] != owner:
        raise ReportError('Request journal identity or checksum differs')
    reservations = journal['reservations']
    known = {r['request_body_sha256'] for r in reservations}
    complete = 0
    for path in sorted((directory / 'responses').glob('*.json')):
        record = read_json(path)
        payload = {k: v for k, v in record.items() if k != 'checksum'}
        body = json.dumps(payload['request'], ensure_ascii=False, sort_keys=True,
                          allow_nan=False, separators=(',', ':')).encode()
        body_sha = hashlib.sha256(body).hexdigest()
        if digest(payload) != record['checksum'] or body_sha != path.stem or body_sha not in known or payload['request_body_sha256'] != body_sha:
            raise ReportError('Saved model reply differs from its recorded request')
        complete += 1
    unknown = len(reservations) - complete
    if unknown < 0 or len(reservations) != summary['reserved_requests'] or complete != result['saved_complete_response_files'] or unknown != result['reservations_without_complete_saved_response']:
        raise ReportError('Saved result and request counts disagree')
    return {'reserved': len(reservations), 'saved_complete': complete,
            'without_saved_complete_response': unknown, 'limit': summary['limits']['max_requests']}


def final_diagnostics(state):
    """Describe the last recorded submission attempt; never repair it or grade anew."""
    messages = state['messages']
    diagnostics = []
    for index in range(len(messages) - 1, -1, -1):
        for call in messages[index].get('tool_calls') or []:
            if call.get('function', {}).get('name') != 'submit_answer':
                continue
            try:
                args = json.loads(call['function']['arguments'])
                if not isinstance(args.get('answer'), str) or not args['answer'].strip():
                    diagnostics.append('empty_answer')
                if args.get('status') == 'insufficient_evidence' and args.get('citations'):
                    diagnostics.append('insufficient_evidence_with_citations')
                if any(ref not in state['read_refs'] for ref in args.get('citations', [])):
                    diagnostics.append('unread_reference')
            except (ValueError, TypeError, KeyError, AttributeError):
                diagnostics.append('invalid_submission_arguments')
            for message in messages[index + 1:]:
                if message.get('role') == 'tool' and message.get('tool_call_id') == call['id']:
                    try:
                        feedback = json.loads(message['content'])
                        if feedback.get('error'):
                            diagnostics.append('submission_rejected')
                    except (ValueError, TypeError, AttributeError):
                        pass
            return sorted(set(diagnostics))
    return ['no_final_submission']


def read_run(directory, store):
    from agentlab_research.research_library import citation

    directory = Path(directory).resolve()
    metadata = read_json(directory / 'run.json')
    owner = metadata['owner_sha256']
    identity = metadata['identity']
    if digest(identity) != owner:
        raise ReportError('Run identity differs')
    result = read_json(directory / 'result.json')
    state = checkpoint_values(directory / 'graph.sqlite', owner)
    first_question = next((m.get('content') for m in state['messages'] if m.get('role') == 'user'), None)
    if first_question != identity['question']:
        raise ReportError('Question differs from the committed conversation')
    for key in ['status', 'final', 'model_turns', 'successful_tools', 'read_refs']:
        if state[key] != result[key]:
            raise ReportError('Result differs from the committed checkpoint')
    if identity['source_generation'] != result['source_generation']:
        raise ReportError('Source generation differs')
    final = result['final']
    references = []
    if result['status'] == 'submitted':
        if not final or not final['citation_lineage_checked'] or final['semantic_entailment_checked']:
            raise ReportError('Unsupported final-result contract')
        for saved in final['citations']:
            if saved['ref'] not in state['read_refs'] or saved['generation'] != identity['source_generation']:
                raise ReportError('Final reference differs from the recorded reads')
            actual = citation(store, saved['citation_id'])
            for key in ['generation', 'source_id', 'source_sha256', 'char_start', 'char_end', 'pdf', 'source_url', 'title']:
                if actual.get(key) != saved.get(key):
                    raise ReportError('Archived citation differs from the saved answer')
            references.append({k: actual[k] for k in actual if k not in ['excerpt', 'note']})
            references[-1]['ref'] = saved['ref']
    elif final is not None:
        raise ReportError('Unsubmitted run contains an accepted answer')
    return {
        'run_id': owner, 'question': identity['question'], 'export_status': 'ready',
        'recorded_status': result['status'], 'model': identity['model'],
        'source_generation': identity['source_generation'],
        'answer': final['answer'] if final else None,
        'model_submission_status': final['status'] if final else None,
        'references': references,
        'diagnostics': [] if final else final_diagnostics(state),
        'requests': request_counts(directory, owner, result),
        'semantic_entailment_checked': False,
    }


def build_report(directories, store):
    if not 1 <= len(directories) <= 16:
        raise ReportError('Choose 1 to 16 stopped local runs')
    if len({Path(p).resolve() for p in directories}) != len(directories):
        raise ReportError('Repeated run directory')
    rows = []
    for directory in directories:
        try:
            row = read_run(directory, store)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
            row = {'export_status': 'error', 'recorded_status': None, 'answer': None,
                   'references': [], 'diagnostics': ['artifact_or_source_unavailable']}
        rows.append(row)
    return {'version': 1, 'scope': 'Recorded answers and read-only source checks; no model/tool execution or new evaluation.',
            'semantic_entailment_checked': False, 'runs': rows,
            'summary': {'runs': len(rows),
                        'recorded_submissions': sum(r['recorded_status'] == 'submitted' for r in rows),
                        'recorded_uncompleted': sum(r['export_status'] == 'ready' and r['recorded_status'] != 'submitted' for r in rows),
                        'export_errors': sum(r['export_status'] == 'error' for r in rows)}}


def plain(value):
    text = html.escape(str(value), quote=False)
    return re.sub(r'([\\`*_{}\[\]()#!|>])', r'\\\1', text)


def source_link(reference):
    url = reference['source_url']
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ReportError('Unsupported source URL')
    return quote(url, safe=':/?#=&%+@,;~.-_')


DIAGNOSTICS = {
    'empty_answer': '最后一次提交的回答为空。',
    'insufficient_evidence_with_citations': '声明证据不足时仍附带了引用，未满足提交要求。',
    'unread_reference': '提交中含有未读取的引用。',
    'invalid_submission_arguments': '最后一次提交参数无效。',
    'submission_rejected': '应用拒收了最后一次提交。',
    'no_final_submission': '没有最终提交记录。',
    'artifact_or_source_unavailable': '运行记录或归档来源缺失、不一致，或尚未关闭，无法导出该项。',
}


def markdown(report):
    summary = report['summary']
    lines = ['# 论文阅读记录', '',
             f"共{summary['runs']}项：已提交{summary['recorded_submissions']}项，未完成{summary['recorded_uncompleted']}项，导出异常{summary['export_errors']}项。", '',
             '本报告整理已有运行，不重新调用模型。引用已回读归档原文核对；这不证明回答解释完整或事实正确。', '']
    for number, run in enumerate(report['runs'], 1):
        lines += [f"## {number}. {plain(run.get('question', '运行记录不可用'))}", '']
        if run['export_status'] == 'error':
            lines += ['导出异常。', '']
        elif run['recorded_status'] == 'submitted':
            label = '已提交回答' if run['model_submission_status'] == 'supported' else '模型报告资料不足'
            lines += [f"**{label}**", '', plain(run['answer']), '']
        else:
            reason = {'turn_limit': '达到调用上限', 'unsubmitted': '未提交有效回答',
                      'truncated': '输出被截断', 'source_changed': '资料版本发生变化',
                      'finalization_failed': '最终提交未通过要求'}.get(run['recorded_status'], '没有可用的已接受回答')
            lines += [f'**未完成：{reason}。**', '']
        for code in run['diagnostics']:
            lines += ['- ' + DIAGNOSTICS[code]]
        if run['diagnostics']:
            lines.append('')
        for ref in run['references']:
            pdf = ref.get('pdf')
            location = f"，PDF物理第{pdf['page_number']}页（页标签{plain(pdf['page_label'])}）" if pdf else f"，原文第{ref['line_start']}–{ref['line_end']}行"
            version = '归档版本' if not ref['is_current_generation'] else '当前版本'
            lines += [f"- [{plain(ref['ref'])}] [{plain(ref['title'])}](<{source_link(ref)}>)" + location + f"，{version}。"]
        if run.get('source_generation'):
            budget = run['requests']
            lines += ['', '<details>', '<summary>来源版本与运行用量</summary>', '',
                      f"资料版本：`{run['source_generation']}`。完整引用标识及原PDF哈希见同目录JSON。", '',
                      f"原运行状态：`{plain(run['recorded_status'])}`；生成请求{budget['reserved']}/{budget['limit']}，完整回复{budget['saved_complete']}，未保存完整回复{budget['without_saved_complete_response']}（继续计入原额度）。", '', '</details>', '']
    return '\n'.join(lines).rstrip() + '\n'


def write_report(report, output):
    output = Path(output)
    artifacts = {
        'reading-report.json': (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode(),
        'reading-report.md': markdown(report).encode(),
    }
    if any(len(data) > 1024**2 for data in artifacts.values()):
        raise ReportError('Report exceeds output limit')
    manifest = {'files': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
                          for name, data in artifacts.items()}}
    artifacts['report-manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    output.mkdir(mode=0o700, exist_ok=False)
    for name, data in artifacts.items():
        path = output / name
        with path.open('xb') as stream:
            path.chmod(0o600)
            stream.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', action='append', type=Path, required=True)
    parser.add_argument('--store', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if any(root.resolve() == output or root.resolve() in output.parents for root in [*args.run_dir, args.store]):
        parser.error('Write reports outside input run/store directories')
    report = build_report(args.run_dir, args.store)
    write_report(report, output)
    print(json.dumps(report['summary']))
    return 2 if report['summary']['export_errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
