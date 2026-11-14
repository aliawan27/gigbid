"""Builds the R&D report PDF: docs/report/report.md (+ tables from evals/results/tables.md) -> HTML -> PDF (Chromium).
Usage: python scripts/build_report.py"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "report" / "report.md"
HTML = ROOT / "docs" / "report" / "report.html"
PDF = ROOT / "docs" / "report" / "GigBid_RnD_Report.pdf"

CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
body { font-family: 'Segoe UI', Roboto, Arial, sans-serif; font-size: 9.6pt; line-height: 1.38; color: #1d2433; }
h1 { font-size: 18pt; margin: 0 0 4px; } h2 { font-size: 12.5pt; margin: 14px 0 5px; border-bottom: 1px solid #d0d5dd; padding-bottom: 2px; }
h3 { font-size: 10.5pt; margin: 10px 0 4px; } p { margin: 4px 0 6px; } ul, ol { margin: 3px 0 6px 18px; padding: 0; } li { margin: 1px 0; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 8px; font-size: 8.2pt; page-break-inside: avoid; }
th, td { border: 1px solid #d0d5dd; padding: 3px 5px; text-align: left; vertical-align: top; } th { background: #f2f4f7; }
code { font-family: Consolas, monospace; font-size: 8.4pt; background: #f2f4f7; padding: 0 3px; border-radius: 3px; }
img { max-width: 100%; } .fig { text-align: center; margin: 6px 0; } .fig img { max-height: 330px; }
.sub { color: #667085; } .pb { page-break-before: always; } a { color: #2457d6; text-decoration: none; }
"""


def md_to_html(md: str) -> str:
    lines, out, i = md.split("\n"), [], 0
    def inline(s):
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", s)
        s = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<div class="fig"><img src="\2" alt="\1"></div>', s)
        return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[1:] if not set("".join(r)) <= set("-: ")]
            out.append("<table><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr>" +
                       "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body) + "</table>")
            continue
        if ln.startswith("<!--pb-->"):
            out.append('<div class="pb"></div>')
        elif m := re.match(r"(#{1,3}) (.*)", ln):
            out.append(f"<h{len(m.group(1))}>{inline(m.group(2))}</h{len(m.group(1))}>")
        elif re.match(r"\s*[-*] ", ln):
            items = []
            while i < len(lines) and re.match(r"\s*[-*] ", lines[i]):
                items.append(inline(re.sub(r"^\s*[-*] ", "", lines[i])))
                i += 1
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>")
            continue
        elif re.match(r"\d+\. ", ln):
            items = []
            while i < len(lines) and re.match(r"\d+\. ", lines[i]):
                items.append(inline(re.sub(r"^\d+\. ", "", lines[i])))
                i += 1
            out.append("<ol>" + "".join(f"<li>{x}</li>" for x in items) + "</ol>")
            continue
        elif ln.strip():
            para = [ln.strip()]
            while (i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"(#{1,3} |\s*[-*] |\d+\. |\||<!--pb-->|!\[)", lines[i + 1])):
                i += 1
                para.append(lines[i].strip())
            out.append(f"<p>{inline(' '.join(para))}</p>")
        i += 1
    return "\n".join(out)


def main():
    md = SRC.read_text(encoding="utf-8")
    tables = (ROOT / "evals" / "results" / "tables.md").read_text(encoding="utf-8")
    md = md.replace("{{TABLES}}", tables)
    for sec in re.findall(r"\{\{TABLE:([^}]+)\}\}", md):
        part = tables.split(f"### {sec}")[1].split("\n### ")[0] if f"### {sec}" in tables else ""
        md = md.replace(f"{{{{TABLE:{sec}}}}}", part.strip())
    HTML.write_text(f"<!doctype html><html><head><meta charset='utf-8'><title>GigBid R&D report</title><style>{CSS}</style>"
                    f"</head><body>{md_to_html(md)}</body></html>", encoding="utf-8")
    js = (f"const {{chromium}}=require('@playwright/test');(async()=>{{const b=await chromium.launch();const p=await b.newPage();"
          f"await p.goto('file:///{HTML.as_posix()}');await p.pdf({{path:'{PDF.as_posix()}',format:'A4',printBackground:true,"
          f"displayHeaderFooter:true,headerTemplate:'<span></span>',footerTemplate:'<div style=\"font-size:7pt;width:100%;text-align:center;color:#888\">GigBid R&amp;D report · <span class=pageNumber></span>/<span class=totalPages></span></div>',"
          f"margin:{{top:'14mm',bottom:'16mm',left:'14mm',right:'14mm'}}}});await b.close();}})();")
    subprocess.run(["node", "-e", js], cwd=ROOT / "apps" / "web", check=True)
    print("wrote", PDF)


if __name__ == "__main__":
    main()
