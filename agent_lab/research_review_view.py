"""Single-file source comparison and portable notes; no services or persistence."""
from __future__ import annotations

import json

from .research_view import CSS, card, escaped, policy_hash


REVIEW_CSS = CSS + '''
header,main,footer{max-width:1320px}.review-item{background:#fff;border:1px solid var(--line);border-radius:16px;padding:24px;margin-bottom:24px;min-width:0}
.review-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:28px}.review-grid .card{border:0;padding:0;border-radius:0}.source-column{border-left:1px solid var(--line);padding-left:24px;min-width:0}.source-column h3{font-size:15px;margin:0 0 12px}.passage{padding:16px;background:#f5f8f3;border:1px solid #e0e7dc;border-radius:10px;margin-bottom:14px}.passage h4{margin:0 0 6px;font-size:14px}.passage blockquote{margin:12px 0;white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.7 system-ui,sans-serif}.passage code{display:block;color:var(--muted);font-size:11px}.review-controls{border-top:1px solid var(--line);margin-top:20px;padding-top:18px;gap:14px;align-items:start;flex-wrap:wrap}.note-field{flex:1;min-width:220px}.review-controls textarea{width:100%;min-height:86px;font:inherit;font-size:14px;line-height:1.5;padding:10px;border:1px solid #bdcbc5;border-radius:8px;resize:vertical}textarea:focus-visible{outline:3px solid #7aaba2;outline-offset:3px}.review-controls select{min-width:145px}.review-summary{font-size:14px;color:var(--muted)}.review-item[data-decision="needs_changes"]{border-color:#c3954f}.review-item[data-decision="checked"]{border-color:#659c86}input[type=file]{max-width:300px;font-size:13px}#feedback{min-height:26px;font-size:14px;color:#215b47}#feedback[data-error="true"]{color:#93433b}.print-annotation{display:none;white-space:pre-wrap;overflow-wrap:anywhere}
@media(max-width:760px){.review-grid{grid-template-columns:1fr;gap:20px}.source-column{border-left:0;border-top:1px solid var(--line);padding:20px 0 0}.review-item{padding:18px}.note-field{flex-basis:100%;min-width:0}.toolbar>*{max-width:100%}}
@media print{.review-controls{display:none!important}.print-annotation{display:block}.review-grid{display:block}.review-item{break-inside:auto;border-radius:0}.source-column{border:0;padding:12px 0}.passage{break-inside:avoid}#feedback{display:none}}
'''


SCRIPT = '''
"use strict";
const bundle = JSON.parse(document.getElementById("bundle-data").textContent);
const items = Array.from(document.querySelectorAll(".review-item"));
const reviewer = document.getElementById("reviewer");
const query = document.getElementById("query");
const status = document.getElementById("status");
const feedback = document.getElementById("feedback");
function message(text, error = false) { feedback.textContent = text; feedback.dataset.error = String(error); }
function length(text) { return Array.from(text).length; }
function keys(value, names) {
  return value !== null && typeof value === "object" && !Array.isArray(value) &&
    Object.keys(value).length === names.length && names.every(key => Object.hasOwn(value, key));
}
function validate(value) {
  if (!keys(value, ["version", "bundle_sha256", "reviewer", "entries"]) || value.version !== 1 || value.bundle_sha256 !== bundle.bundle_sha256)
    throw new Error("备注不属于这份回答与资料版本，请打开对应核查页。");
  if (typeof value.reviewer !== "string" || length(value.reviewer) > 120 || !Array.isArray(value.entries) || value.entries.length !== bundle.entries.length)
    throw new Error("核查人名称或记录数量无效。");
  const expected = new Map(bundle.entries.map(entry => [entry.entry_id, entry]));
  const seen = new Map();
  for (const row of value.entries) {
    if (!keys(row, ["entry_id", "answer_sha256", "decision", "notes"]) || !expected.has(row.entry_id) || seen.has(row.entry_id))
      throw new Error("备注含未知、重复或缺少的记录。");
    const entry = expected.get(row.entry_id);
    const choices = entry.reviewable ? ["pending", "checked", "needs_changes"] : ["unavailable"];
    if (row.answer_sha256 !== entry.answer_sha256 || !choices.includes(row.decision) || typeof row.notes !== "string" || length(row.notes) > 1000)
      throw new Error("回答标识、核查状态或备注长度无效。");
    seen.set(row.entry_id, row);
  }
  return bundle.entries.map(entry => seen.get(entry.entry_id));
}
function snapshot() {
  const value = {version: 1, bundle_sha256: bundle.bundle_sha256, reviewer: reviewer.value,
    entries: items.map((item, index) => ({entry_id: bundle.entries[index].entry_id,
      answer_sha256: bundle.entries[index].answer_sha256,
      decision: item.querySelector(".decision").value, notes: item.querySelector("textarea").value}))};
  validate(value);
  return value;
}
function refresh() {
  const needle = query.value.normalize("NFKC").trim().toLocaleLowerCase();
  let visible = 0, checked = 0, changes = 0, pending = 0;
  for (const item of items) {
    const decision = item.querySelector(".decision").value;
    item.dataset.decision = decision;
    item.querySelector(".print-annotation").textContent = "核查标记：" + item.querySelector(".decision").selectedOptions[0].textContent + "\\n核查备注：" + item.querySelector("textarea").value;
    checked += Number(decision === "checked"); changes += Number(decision === "needs_changes"); pending += Number(decision === "pending");
    const text = (item.querySelector(".review-grid").textContent + " " + item.querySelector("textarea").value).normalize("NFKC").toLocaleLowerCase();
    item.hidden = !(status.value === "all" || decision === status.value) || !text.includes(needle);
    visible += Number(!item.hidden);
  }
  document.getElementById("result-count").textContent = `显示 ${visible} / ${items.length} 项 · 待核对 ${pending} · 标记已核对 ${checked} · 需修改 ${changes}`;
  document.getElementById("empty").hidden = visible !== 0;
}
for (const item of items) {
  item.querySelector(".decision").addEventListener("change", refresh);
  item.querySelector("textarea").addEventListener("input", refresh);
}
query.addEventListener("input", refresh); status.addEventListener("change", refresh);
document.getElementById("reset").addEventListener("click", () => {query.value = ""; status.value = "all"; refresh();});
document.getElementById("print").addEventListener("click", () => window.print());
document.getElementById("save-notes").addEventListener("click", () => {
  try {
    const text = JSON.stringify(snapshot(), null, 2) + "\\n";
    const url = URL.createObjectURL(new Blob([text], {type: "application/json;charset=utf-8"}));
    const link = document.createElement("a"); link.href = url; link.download = "review-notes.json";
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    message("已下载全部记录的核查备注。重新打开页面后，可导入该文件继续。");
  } catch (error) { message(error.message, true); }
});
document.getElementById("load-notes").addEventListener("change", async event => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    if (file.size > 1048576) throw new Error("备注文件不能超过 1MiB。");
    const value = JSON.parse(await file.text());
    const rows = validate(value); // Validate the whole file before changing any control.
    rows.forEach((row, index) => {
      items[index].querySelector(".decision").value = row.decision;
      items[index].querySelector("textarea").value = row.notes;
    });
    reviewer.value = value.reviewer; refresh(); message("已导入核查备注，原模型回答保持不变。");
  } catch (error) { message(error.message, true); }
  finally { event.target.value = ""; }
});
refresh(); document.documentElement.classList.add("enhanced");
'''


def review_item(entry, number):
    run = entry['run']
    sources = ['<aside class="source-column" aria-label="引用原文"><h3>引用原文对照</h3>']
    by_id = {ref['citation_id']: ref for ref in run['references']}
    for passage in entry['passages']:
        reference = by_id[passage['citation_id']]
        pdf = reference.get('pdf')
        location = f'PDF物理第{pdf["page_number"]}页 · 页标签{pdf["page_label"]}' if pdf else f'原文第{reference["line_start"]}–{reference["line_end"]}行'
        sources += [f'<section class="passage"><h4>{escaped(passage["ref"])} · {escaped(reference["title"])}</h4>',
                    f'<div class="location">{escaped(location)} · 字符 {reference["char_start"]}–{reference["char_end"]}</div>',
                    f'<blockquote>{escaped(passage["excerpt"])}</blockquote>',
                    f'<code>片段 SHA256 {escaped(passage["excerpt_sha256"])}</code></section>']
    if not entry['passages']:
        sources.append('<p>本项没有可展示的已接受引用原文。保留原运行状态，不补写答案或证明资料覆盖。</p>')
    if entry['evidence_error']:
        sources.append('<p class="notice">原引用当前无法回读核对，本项不可标为已核对。</p>')
    sources.append('</aside>')
    options = '<option value="pending">待核对</option><option value="checked">标记已核对</option><option value="needs_changes">需修改</option>' if entry['reviewable'] else '<option value="unavailable">无可核对的提交</option>'
    disabled = '' if entry['reviewable'] else ' disabled'
    return (f'<section class="review-item" data-entry-id="{entry["entry_id"]}"><div class="review-grid">'
            f'<div>{card(run, number)}</div>' + '\n'.join(sources) + '</div>'
            '<div class="review-controls enhanced-only">'
            f'<label class="field" for="decision-{number}">你的核查标记<select class="decision" id="decision-{number}"{disabled}>{options}</select></label>'
            f'<label class="field note-field" for="notes-{number}">核查备注<textarea id="notes-{number}" aria-label="第{number}项核查备注" placeholder="例如：哪句解释还需补充、哪个引用不能支持该陈述。"></textarea></label></div><p class="print-annotation"></p></section>')


def review_html(bundle):
    from .research_review import check_bundle

    check_bundle(bundle)
    payload = json.dumps(bundle, ensure_ascii=False, indent=2) + '\n'
    policy = ("default-src 'none'; base-uri 'none'; form-action 'none'; "
              f"style-src 'sha256-{policy_hash(REVIEW_CSS)}'; script-src 'sha256-{policy_hash(SCRIPT)}'; "
              "connect-src 'none'; object-src 'none'")
    cards = '\n'.join(review_item(entry, number) for number, entry in enumerate(bundle['entries'], 1))
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{escaped(policy)}"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="referrer" content="no-referrer">
<title>论文引用核查 · Agent Lab</title><style>{REVIEW_CSS}</style></head><body>
<header><p class="eyebrow">AGENT LAB / SOURCE REVIEW</p><h1>让回答，与原文并排。</h1>
<p class="lead">核对已保存的回答与实际读取的原文片段，记录需要修改的地方。原文按当时资料版本回读；核查页不调用模型，也不修改原答案。</p>
<p class="notice">此文件包含问题、回答和论文原文片段，分享前请检查全部内容。“标记已核对”是操作者声明，不是自动语义判断或身份认证。</p></header>
<main><div class="toolbar enhanced-only"><label class="field search" for="query">搜索问题、回答、原文或备注<input id="query" type="search" autocomplete="off" placeholder="例如：实体、索引、需要补充"></label>
<label class="field" for="status">核查状态<select id="status"><option value="all">全部记录</option><option value="pending">待核对</option><option value="checked">标记已核对</option><option value="needs_changes">需修改</option><option value="unavailable">无可核对的提交</option></select></label><button id="reset" type="button">清除筛选</button></div>
<div class="toolbar enhanced-only"><label class="field" for="reviewer">核查人（选填）<input id="reviewer" type="text" autocomplete="off" placeholder="自行填写显示名称"></label><button id="save-notes" type="button">下载全部核查备注</button><label class="field" for="load-notes">导入核查备注<input id="load-notes" type="file" accept=".json,application/json"></label><button id="print" type="button">打印当前结果</button></div>
<p id="feedback" role="status" aria-live="polite"></p><p id="result-count" class="review-summary" role="status" aria-live="polite">共 {len(bundle['entries'])} 项记录</p>
<noscript><p>未启用JavaScript，原回答和引用原文仍可阅读；编辑、保存和导入标注不可用。</p></noscript>
{cards}<p id="empty" hidden>没有匹配的记录。可清除筛选。</p></main>
<footer><p>备注只保留在当前页面内存中。下载后可在同一核查页导入；不同回答或来源版本的文件不会混入。筛选仅改变显示，导出备注始终覆盖全部记录。</p><p>离线原文对照无需联网；点击论文标题才打开在线来源。没有保存浏览器存储或上传内容。</p></footer>
<pre id="bundle-data" hidden>{escaped(payload)}</pre><script>{SCRIPT}</script></body></html>
'''
