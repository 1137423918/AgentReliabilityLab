"""Build a dated bilingual project PDF and its static portfolio page."""

import argparse
import hashlib
import html
import json
import os
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[1]
INK = "#172c25"
GREEN = "#276b46"
MUTED = "#53665d"
RULE = "#dce5df"
PDF_NAME = "junzhe-wang-project-brief.pdf"


def esc(value):
    return html.escape(value, quote=True)


def linked(label, url):
    return f'<a href="{esc(url)}" color="{GREEN}">{esc(label)}</a>'


def contribution_prs(contribution):
    return [contribution, *contribution.get("extra_prs", [])]


def pr_status_label(pr, evidence, language):
    row = next(p for p in evidence["pull_requests"] if p["url"] == pr["url"])
    status = "merged" if row["merged"] else "closed" if row["state"] == "closed" else "draft" if row["draft"] else "open"
    labels = {"zh": {"merged": "已合并", "closed": "已关闭", "draft": "草稿", "open": "开放"},
              "en": {"merged": "Merged", "closed": "Closed", "draft": "Draft", "open": "Open"}}
    return f'{labels[language][status]} #{pr["number"]}'


def register_fonts(args):
    specs = [
        ("CJKBody", args.font_regular, args.font_index),
        ("CJKHead", args.font_bold, args.font_index),
        ("LatinBody", args.latin_regular, 0),
        ("LatinHead", args.latin_bold, 0),
    ]
    receipts = []
    for name, path, index in specs:
        face = TTFont(name, str(path), subfontIndex=index)
        pdfmetrics.registerFont(face)
        receipts.append({"role": name, "face": face.face.name.decode(), "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "index": index})
    for family, head in [("CJKBody", "CJKHead"), ("LatinBody", "LatinHead")]:
        pdfmetrics.registerFontFamily(family, normal=family, bold=head, italic=family, boldItalic=head)
    return receipts


def build_pdf(data, evidence, output):
    page_width, page_height = A4
    margin = 47
    width = page_width - margin * 2
    old_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = str(int(datetime.fromisoformat(evidence["checked_at"]).timestamp()))
    try:
        document = canvas.Canvas(str(output), pagesize=A4, pageCompression=1, invariant=1)
    finally:
        if old_epoch is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = old_epoch
    document.setTitle("Junzhe Wang - Projects and contributions")
    document.setAuthor(data["name"])
    document.setCreator("Agent Reliability Lab portfolio builder")
    layouts = []
    for page_number, language in enumerate(["zh", "en"], 1):
        content = data["languages"][language]
        body = "CJKBody" if language == "zh" else "LatinBody"
        head = "CJKHead" if language == "zh" else "LatinHead"
        all_text = json.dumps(content, ensure_ascii=False) + data["paper"]["title"] + data["stack"]
        missing = sorted({c for c in all_text if ord(c) > 32 and ord(c) not in pdfmetrics.getFont(body).face.charToGlyph})
        if missing:
            raise ValueError(f"Font does not cover {language}: {missing}")
        y = page_height - margin
        boxes = []

        def paragraph(text, size=10.1, leading=14.6, gap=7, color=INK, bold=False, indent=0):
            nonlocal y
            style = ParagraphStyle("brief", fontName=head if bold else body, fontSize=size, leading=leading, textColor=colors.HexColor(color), alignment=TA_LEFT, wordWrap="CJK" if language == "zh" else "LTR")
            p = Paragraph(text, style)
            _, height = p.wrap(width - indent, page_height)
            if y - height < 67:
                raise ValueError(f"Content overflows page {page_number}: {text[:70]}")
            p.drawOn(document, margin + indent, y - height)
            boxes.append({"top": round(y, 2), "bottom": round(y - height, 2), "height": round(height, 2)})
            y -= height + gap

        def section(label):
            nonlocal y
            y -= 4
            document.setStrokeColor(colors.HexColor(RULE))
            document.line(margin, y, page_width - margin, y)
            y -= 9
            paragraph(esc(label), 9, 12, 6, GREEN, True)

        paragraph(esc(data["name"]), 25, 28, 5, INK, True)
        paragraph(esc(content["title"]), 14, 18, 3, INK, True)
        paragraph(esc(content["subtitle"]), 10, 14, 5, MUTED)
        paragraph(linked("1137423918.github.io", data["website"]) + " / " + linked("GitHub: A_Zhe", data["github"]), 9, 12, 6)
        section(content["project_label"])
        paragraph(esc(content["project_title"]), 13.2, 17, 3, INK, True)
        paragraph(esc(data["stack"]), 8.6, 11.5, 6, MUTED)
        paragraph(esc(content["project_intro"]), gap=6)
        for bullet in content["bullets"]:
            paragraph("- " + esc(bullet), gap=5)
        paragraph(esc(content["project_scope"]), 8.9, 12.8, 6, MUTED)
        paragraph(linked(content["links_label"], "https://github.com/1137423918/AgentReliabilityLab") + " / " + linked(content["sources_label"], "https://1137423918.github.io/project-brief.html#evidence") + " / " + linked(content["starter_label"], data["starter_url"]), 9, 12, 5)
        section(content["contributions_label"])
        for contribution in content["contributions"]:
            pr_links = " / ".join(linked(pr_status_label(p, evidence, language), p["url"]) for p in contribution_prs(contribution))
            paragraph(f'<b>{esc(contribution["name"])}</b> / ' + pr_links, 10.3, 13.5, 3)
            paragraph(esc(contribution["text"]), 9.5, 13.5, 7)
        section(content["paper_label"])
        paragraph(esc(data["paper"]["title"]), 10.3, 13.8, 4, INK, True)
        paragraph(esc(content["paper_text"]), 9.5, 13, 4)
        paragraph(linked("DOI: " + data["paper"]["doi"], data["paper"]["url"]) + " / " + linked("LS-DETR code", data["paper"]["code"]), 8.9, 12, 6)
        paragraph(esc(content["scope"]), 8.6, 12, 0, MUTED)
        document.setStrokeColor(colors.HexColor(RULE))
        document.line(margin, 48, page_width - margin, 48)
        document.setFont(body, 8.5)
        document.setFillColor(colors.HexColor(MUTED))
        document.drawString(margin, 32, data["date"] + " / " + ("工程与研究项目介绍" if language == "zh" else "Engineering and research brief"))
        document.drawRightString(page_width - margin, 32, f"{page_number} / 2")
        layouts.append({"language": language, "content_bottom": round(y, 2), "paragraphs": boxes})
        document.showPage()
    document.save()
    return layouts


def build_html(data, evidence, output):
    sections = []
    for language in ["zh", "en"]:
        c = data["languages"][language]
        bullets = "".join(f"<li>{esc(x)}</li>" for x in c["bullets"])
        contribution_items = []
        for x in c["contributions"]:
            prs = contribution_prs(x)
            pr_links = " · ".join(f'<a href="{esc(p["url"])}">{esc(pr_status_label(p, evidence, language))}</a>' for p in prs)
            sources = " · ".join(f'<a class="source-link" href="{esc(next(r["url"] for r in evidence["files"] if r["id"] == p["source"]))}">{esc(c["sources_label"])} #{p["number"]}</a>' for p in prs)
            contribution_items.append(f'<article class="contribution"><div><h3>{esc(x["name"])}</h3><span>{pr_links}</span></div><p>{esc(x["text"])}</p>{sources}</article>')
        contributions = "".join(contribution_items)
        sections.append(f'''<section class="brief-language" data-language="{language}" lang="{'zh-CN' if language == 'zh' else 'en'}" {'hidden' if language == 'en' else ''}>
<p class="eyebrow">SELECTED ENGINEERING WORK / {esc(data['date'])}</p><h1>{esc(c['title'])}</h1><p class="brief-intro">{esc(c['subtitle'])}</p>
<div class="brief-actions"><a class="button" href="downloads/{PDF_NAME}" download>{esc(c['download_label'])}</a><button class="copy-brief" type="button" data-copy="{language}" disabled>{esc(c['copy_label'])}</button><span class="copy-result" role="status" aria-live="polite"></span></div>
<article class="brief-project"><p class="eyebrow">{esc(c['project_label'])}</p><h2>{esc(c['project_title'])}</h2><p class="brief-stack">{esc(data['stack'])}</p><p class="brief-intro">{esc(c['project_intro'])}</p><ul class="brief-points">{bullets}</ul>
<div class="workflow" role="img" aria-label="{'固定任务、持久化执行、隔离验收、补丁审阅' if language == 'zh' else 'Pinned task, durable execution, isolated verification, patch review'}"><span>{'固定任务' if language == 'zh' else 'Pinned task'}</span><span>{'持久化执行' if language == 'zh' else 'Durable execution'}</span><span>{'隔离验收' if language == 'zh' else 'Isolated checks'}</span><span>{'补丁审阅' if language == 'zh' else 'Patch review'}</span></div>
<p class="scope-note">{esc(c['project_scope'])}</p><p><a href="https://github.com/1137423918/AgentReliabilityLab">{esc(c['links_label'])}</a> · <a href="{esc(data['starter_url'])}" download>{esc(c['starter_label'])}</a> · <a href="notes/mcp-evidence.html#installable">{'安装与实测' if language == 'zh' else 'Installation and evidence'}</a> · <a href="notes/recovery.html#verification-tree">{'验证进程生命周期' if language == 'zh' else 'Verifier lifecycle'}</a> · <a href="notes/local-state.html">{'本机状态与恢复' if language == 'zh' else 'Local state and recovery'}</a> · <a href="notes/model-request-budget.html">{'请求预算案例' if language == 'zh' else 'Request budget case'}</a> · <a href="notes/protected-grading.html">{'验收保护案例' if language == 'zh' else 'Acceptance protection'}</a></p></article>
<section class="brief-contributions"><h2>{esc(c['contributions_label'])}</h2><div class="contribution-grid">{contributions}</div></section>
<section class="brief-paper"><p class="eyebrow">{esc(c['paper_label'])}</p><h2>{esc(data['paper']['title'])}</h2><p>{esc(c['paper_text'])}</p><p><a href="{esc(data['paper']['url'])}">DOI: {esc(data['paper']['doi'])}</a> · <a href="{esc(data['paper']['code'])}">LS-DETR code</a></p></section>
<p class="scope-note">{esc(c['scope'])}</p></section>''')
    sources = "".join(f'<li><a href="{esc(r["url"])}">{esc(r["label"])}</a><code>{esc(r["sha256"][:16])}</code></li>' for r in evidence["files"])
    page = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Projects and contributions · Junzhe Wang</title><meta name="description" content="Junzhe Wang 的 Agent 工程项目、实际开源草稿和研究论文：中英介绍、可下载 PDF 与证据入口。"><link rel="stylesheet" href="style.css"><link rel="stylesheet" href="brief.css"><script src="brief.js" defer></script></head><body><header class="header wrap"><a class="brand" href="index.html"><span class="monogram">JW</span><span>JUNZHE WANG<span class="brand-sub">ENGINEERING &amp; RESEARCH</span></span></a><a class="text-link" href="index.html#work">个人主页</a></header><main class="wrap brief-main"><nav class="language-controls" aria-label="Language"><button type="button" data-select-language="zh" aria-pressed="true">中文</button><button type="button" data-select-language="en" aria-pressed="false">English</button></nav>{''.join(sections)}<section id="evidence" class="brief-evidence"><h2>证据与状态 / Evidence and status</h2><p>状态快照：{esc(evidence['checked_at'])}。以下为公开原始报告；测试、PR 与神经试验的状态分别记录。</p><ul>{sources}</ul><p><a href="portfolio-evidence.json">完整文件哈希与 PR 快照</a> · <a href="portfolio-content.json">中英文本 JSON</a> · <a href="index.html#lab">全部实验记录</a></p></section><textarea class="copy-fallback" aria-label="Project text for manual copying" hidden></textarea></main><footer class="wrap footer"><span>© 2026 Junzhe Wang</span><a href="index.html">个人主页</a></footer></body></html>'''
    (output / "project-brief.html").write_text(page)
    (output / "portfolio-content.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    (output / "portfolio-evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    for name in ["brief.css", "brief.js"]:
        (output / name).write_bytes((ROOT / "portfolio" / name).read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--font-regular", type=Path, required=True)
    parser.add_argument("--font-bold", type=Path, required=True)
    parser.add_argument("--font-index", type=int, default=0)
    parser.add_argument("--latin-regular", type=Path, required=True)
    parser.add_argument("--latin-bold", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads((ROOT / "portfolio/brief.json").read_text())
    evidence = json.loads((ROOT / "portfolio/evidence-map.json").read_text())
    if datetime.fromisoformat(evidence["checked_at"]).date().isoformat() != data["date"]:
        raise ValueError("Brief and evidence dates differ")
    for record in evidence["files"]:
        if hashlib.sha256((ROOT / record["path"]).read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("Evidence changed: " + record["id"])
    citation = ROOT / "portfolio/citation.bib"
    if hashlib.sha256(citation.read_bytes()).hexdigest() != evidence["paper_bibtex_sha256"]:
        raise ValueError("Paper citation changed")
    if data["paper"]["doi"] != evidence["paper_doi"]:
        raise ValueError("Paper DOI differs from evidence")
    prs = evidence["pull_requests"]
    if any(p["state"] not in {"open", "closed"} or type(p["draft"]) is not bool or type(p["merged"]) is not bool or (p["merged"] and p["state"] != "closed") for p in prs):
        raise ValueError("Invalid PR status snapshot")
    if len({p["url"] for p in prs}) != len(prs):
        raise ValueError("Duplicate PR status URL")
    counts = {"open": sum(p["state"] == "open" for p in prs),
              "draft": sum(p["state"] == "open" and p["draft"] for p in prs),
              "closed": sum(p["state"] == "closed" for p in prs),
              "merged": sum(p["merged"] for p in prs)}
    if data["pr_status_summary"] != counts:
        raise ValueError("Brief status summary differs from the PR snapshot")
    for content in data["languages"].values():
        linked_prs = {p["url"] for c in content["contributions"] for p in contribution_prs(c)}
        if linked_prs != {p["url"] for p in evidence["pull_requests"]}:
            raise ValueError("Contribution links differ from the PR snapshot")
    fonts = register_fonts(args)
    args.output.mkdir(parents=True, exist_ok=True)
    layouts = build_pdf(data, evidence, args.output / PDF_NAME)
    build_html(data, evidence, args.output)
    receipt = {"pdf": PDF_NAME, "pdf_sha256": hashlib.sha256((args.output / PDF_NAME).read_bytes()).hexdigest(), "content_sha256": hashlib.sha256((ROOT / "portfolio/brief.json").read_bytes()).hexdigest(), "evidence_map_sha256": hashlib.sha256((ROOT / "portfolio/evidence-map.json").read_bytes()).hexdigest(), "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "asset_sha256": {n: hashlib.sha256((ROOT / "portfolio" / n).read_bytes()).hexdigest() for n in ["brief.css", "brief.js"]}, "reportlab_version": version("reportlab"), "metadata_date_source": evidence["checked_at"], "fonts": fonts, "pages": layouts}
    (args.output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"pages": len(layouts), "pdf_sha256": receipt["pdf_sha256"], "content_bottoms": [p["content_bottom"] for p in layouts]}))


if __name__ == "__main__":
    main()
