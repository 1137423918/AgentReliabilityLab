"""Self-contained reading view for the existing, verified report representation.

Static content remains readable without JavaScript. Enhancements only filter the
display, print it, or download the full recorded report; they never call a model.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json


CSS = '''
:root{color-scheme:light;--ink:#203b3b;--muted:#5a6c6b;--line:#dbe3df;--paper:#fff;--accent:#155e57}
*{box-sizing:border-box}body{margin:0;background:#f4f6f2;color:var(--ink);font:16px/1.7 system-ui,-apple-system,"Noto Sans CJK SC",sans-serif}
main,header,footer{max-width:1080px;margin:auto;padding:28px}header{padding-top:50px;padding-bottom:14px}
.eyebrow{color:var(--accent);font-size:12px;font-weight:750;letter-spacing:.15em;margin:0 0 12px}h1{font-size:clamp(28px,5vw,42px);line-height:1.25;letter-spacing:-.03em;margin:0 0 14px}
.lead{max-width:760px;color:var(--muted);margin:0}.overview{display:flex;flex-wrap:wrap;gap:10px;margin:24px 0 14px}.metric{padding:10px 16px;border:1px solid var(--line);border-radius:12px;background:#fff;font-size:14px}.metric strong{font-size:21px;margin-right:7px}
.notice{border-left:3px solid #c6a76a;padding:9px 15px;background:#faf5e9;color:#67532e;font-size:14px}.toolbar{display:flex;align-items:end;flex-wrap:wrap;gap:12px;padding:20px 0}.field{display:flex;flex-direction:column;gap:5px;font-size:13px;font-weight:650}.search{flex:1;min-width:220px}
input,select,button{font:inherit;color:var(--ink);border:1px solid #bdcbc5;border-radius:8px;background:#fff;padding:10px 12px;min-height:44px}input{width:100%}button{cursor:pointer;font-size:14px;font-weight:650}button:hover{background:#edf3ef}input:focus-visible,select:focus-visible,button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #7aaba2;outline-offset:3px}
.result-count{font-size:14px;color:var(--muted);margin:0 0 14px}.cards{display:grid;gap:20px}.card{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:24px;min-width:0}.card-top{display:flex;align-items:center;justify-content:space-between;gap:12px}.number{font-size:12px;font-weight:750;color:var(--muted);letter-spacing:.08em}.badge{font-size:12px;font-weight:700;border-radius:20px;padding:3px 10px;white-space:nowrap;background:#e4f1eb;color:#215b47}.unfinished .badge{background:#fff0db;color:#825719}.error .badge{background:#f9e7e5;color:#93433b}
h2{font-size:20px;line-height:1.55;margin:14px 0 16px;overflow-wrap:anywhere}.answer{white-space:pre-wrap;margin:0 0 18px;overflow-wrap:anywhere}.answer-label{font-size:12px;color:var(--muted);margin-bottom:7px}.diagnostics{padding-left:22px;color:#825719;font-size:14px}.refs{border-top:1px solid var(--line);padding-top:16px}.refs h3{font-size:13px;margin:0 0 10px;color:var(--muted)}.refs ul{list-style:none;padding:0;margin:0;display:grid;gap:12px}.refs li{padding:12px 14px;background:#f6f8f5;border-radius:9px;overflow-wrap:anywhere}.ref-label{font-weight:750;font-size:12px;margin-right:8px}a{color:#155e57;text-underline-offset:3px}.location{color:var(--muted);font-size:13px;margin-top:4px}details{font-size:13px;margin-top:16px;color:var(--muted)}summary{cursor:pointer}dl{display:grid;grid-template-columns:90px 1fr;gap:8px 12px;margin-bottom:0}dt{font-weight:650}dd{margin:0;min-width:0;overflow-wrap:anywhere}code{font-family:ui-monospace,monospace;font-size:12px;overflow-wrap:anywhere}
#empty{border:1px dashed #bdcbc5;border-radius:12px;padding:35px;text-align:center;color:var(--muted)}[hidden]{display:none!important}.enhanced-only{display:none}html.enhanced .enhanced-only{display:flex}footer{font-size:12px;color:var(--muted);padding-top:8px;padding-bottom:40px}
@media(max-width:600px){main,header,footer{padding-left:18px;padding-right:18px}header{padding-top:30px}.toolbar{align-items:stretch}.field{flex:1;min-width:140px}.search{flex-basis:100%}.card{padding:18px}.metric{padding:8px 12px}.overview{gap:7px}h2{font-size:18px}dl{grid-template-columns:74px 1fr}}
@media print{body{background:#fff;font-size:11pt}main,header,footer{max-width:none;padding:10px 0}header{padding-top:0}.toolbar,.download-note{display:none!important}.card{break-inside:avoid;border-radius:0;margin-bottom:12px}.overview{margin:12px 0}.metric{padding:3px 8px}.refs li{background:#fff;padding:4px 0}details{display:block}details>*{display:block}summary{display:none}h1{font-size:24pt}}
'''

SCRIPT = '''
"use strict";
const cards = Array.from(document.querySelectorAll(".card"));
const query = document.getElementById("query");
const status = document.getElementById("status");
const count = document.getElementById("result-count");
function filter() {
  const needle = query.value.normalize("NFKC").trim().toLocaleLowerCase();
  let visible = 0;
  for (const card of cards) {
    const text = card.querySelector(".searchable").textContent.normalize("NFKC").toLocaleLowerCase();
    card.hidden = !(status.value === "all" || card.dataset.status === status.value) || !text.includes(needle);
    if (!card.hidden) visible += 1;
  }
  count.textContent = `显示 ${visible} / ${cards.length} 项`;
  document.getElementById("empty").hidden = visible !== 0;
}
query.addEventListener("input", filter);
status.addEventListener("change", filter);
document.getElementById("reset").addEventListener("click", () => { query.value = ""; status.value = "all"; filter(); query.focus(); });
document.getElementById("print").addEventListener("click", () => window.print());
document.getElementById("download").addEventListener("click", () => {
  const data = document.getElementById("report-data").textContent;
  const url = URL.createObjectURL(new Blob([data], {type: "application/json;charset=utf-8"}));
  const link = document.createElement("a"); link.href = url; link.download = "reading-report.json";
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
filter();
document.documentElement.classList.add("enhanced");
'''


def escaped(value):
    return html.escape(str(value), quote=True)


def policy_hash(text):
    return base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()


def card(run, number):
    from .research_report import DIAGNOSTICS, source_link

    state = ('error' if run['export_status'] == 'error' else
             'submitted' if run['recorded_status'] == 'submitted' else 'unfinished')
    label = {'error': '导出异常', 'submitted': '已提交', 'unfinished': '未完成'}[state]
    parts = [f'<article class="card {state}" data-status="{state}" aria-labelledby="question-{number}">',
             f'<div class="card-top"><span class="number">READING {number:02d}</span><span class="badge">{label}</span></div>',
             '<div class="searchable">',
             f'<h2 id="question-{number}">{escaped(run.get("question", "运行记录不可用"))}</h2>']
    if state == 'submitted':
        heading = '已保存的模型回答' if run['model_submission_status'] == 'supported' else '模型报告资料不足'
        parts += [f'<div class="answer-label">{heading} · 未自动验证陈述正确性</div>',
                  f'<p class="answer">{escaped(run["answer"])}</p>']
    elif state == 'unfinished':
        parts += ['<p class="answer">未形成已接受的最终回答。原运行状态及原因保留如下。</p>']
    else:
        parts += ['<p class="answer">运行记录或来源无法核对，未导出该项回答。</p>']
    if run['diagnostics']:
        parts += ['<ul class="diagnostics">']
        parts += [f'<li>{escaped(DIAGNOSTICS[code])}</li>' for code in run['diagnostics']]
        parts += ['</ul>']
    if run['references']:
        parts += ['<section class="refs" aria-label="论文与原文引用"><h3>实际读取的来源</h3><ul>']
        for ref in run['references']:
            pdf = ref.get('pdf')
            location = (f'PDF物理第{pdf["page_number"]}页 · 页标签{pdf["page_label"]}' if pdf else
                        f'原文第{ref["line_start"]}–{ref["line_end"]}行')
            version = '当前资料版本' if ref['is_current_generation'] else '归档资料版本'
            parts += [f'<li><span class="ref-label">{escaped(ref["ref"])}</span>'
                      f'<a href="{escaped(source_link(ref))}" target="_blank" rel="noopener noreferrer">{escaped(ref["title"])}</a>'
                      f'<div class="location">{escaped(location)} · {version} · 打开来源需联网</div>'
                      '<details><summary>查看引用标识与文件哈希</summary><dl>'
                      f'<dt>引用标识</dt><dd><code>{escaped(ref["citation_id"])}</code></dd>'
                      f'<dt>原文SHA256</dt><dd><code>{escaped(ref["source_sha256"])}</code></dd>'
                      + (f'<dt>PDF SHA256</dt><dd><code>{escaped(pdf["sha256"])}</code></dd>' if pdf else '')
                      + '</dl></details></li>']
        parts += ['</ul></section>']
    parts += ['</div>']
    if run.get('source_generation'):
        budget = run['requests']
        parts += ['<details class="usage"><summary>查看原运行状态与用量</summary><dl>',
                  f'<dt>原状态</dt><dd><code>{escaped(run["recorded_status"])}</code></dd>',
                  f'<dt>生成请求</dt><dd>{budget["reserved"]} / {budget["limit"]}；完整回复{budget["saved_complete"]}；未保存完整回复{budget["without_saved_complete_response"]}（仍占用原额度）</dd>',
                  f'<dt>资料版本</dt><dd><code>{escaped(run["source_generation"])}</code></dd>',
                  f'<dt>模型</dt><dd>{escaped(run["model"])}</dd></dl></details>']
    parts += ['</article>']
    return '\n'.join(parts)


def reading_html(report):
    """Render an already verified report. No graph, model, store or network access."""
    summary = report['summary']
    payload = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    policy = ("default-src 'none'; base-uri 'none'; form-action 'none'; "
              f"style-src 'sha256-{policy_hash(CSS)}'; script-src 'sha256-{policy_hash(SCRIPT)}'; "
              "connect-src 'none'; object-src 'none'")
    metrics = ''.join(f'<div class="metric"><strong>{summary[key]}</strong>{label}</div>' for key, label in [
        ('runs', '项记录'), ('recorded_submissions', '项已提交'),
        ('recorded_uncompleted', '项未完成'), ('export_errors', '项导出异常')])
    cards = '\n'.join(card(run, number) for number, run in enumerate(report['runs'], 1))
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{escaped(policy)}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer"><title>论文阅读记录 · Agent Lab</title>
<style>{CSS}</style></head><body>
<header><p class="eyebrow">AGENT LAB / READING NOTES</p><h1>让阅读结果，回到来源。</h1>
<p class="lead">集中查看已有回答、实际读取的论文页和未完成原因。这是一份可离线打开的阅读记录。</p>
<div class="overview" aria-label="记录概览">{metrics}</div>
<p class="notice">“已提交”表示原运行接受了回答；引用来源已核对，陈述正确性仍需复核。此页面不会重新生成或补写答案。</p></header>
<main><div class="toolbar enhanced-only" aria-label="筛选阅读记录">
<label class="field search" for="query">搜索问题、回答或来源<input id="query" type="search" placeholder="例如：检索、RECEIPT、资料不足" autocomplete="off"></label>
<label class="field" for="status">运行状态<select id="status"><option value="all">全部记录</option><option value="submitted">已提交</option><option value="unfinished">未完成</option><option value="error">导出异常</option></select></label>
<button type="button" id="reset">清除筛选</button><button type="button" id="print">打印当前结果</button><button type="button" id="download">下载全部JSON</button></div>
<noscript><p>当前未启用JavaScript，所有记录仍完整显示；搜索、筛选和下载按钮不可用。</p></noscript>
<p id="result-count" class="result-count" role="status" aria-live="polite">显示 {summary['runs']} / {summary['runs']} 项</p>
<div class="cards">{cards}</div><p id="empty" hidden>没有匹配的记录。可修改关键词或清除筛选。</p></main>
<footer><p>单文件阅读页 · 无外部字体、脚本或自动联网请求。点击论文链接时才打开在线来源。</p>
<p class="download-note">筛选仅改变显示与打印内容；HTML本身和“下载全部JSON”始终包含全部记录，分享前请检查问题与回答。</p></footer>
<pre id="report-data" hidden>{escaped(payload)}</pre><script>{SCRIPT}</script></body></html>
'''
