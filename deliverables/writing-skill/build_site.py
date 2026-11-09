"""Build a reader-facing portfolio: three articles, figures, HTML and PDF.

No architecture, scores, evidence tables, or hand-written SVG.  The article
Markdown is the source; figures are copied as-is (including SVGs produced by
the writing pipeline).

    python deliverables/writing-skill/build_site.py
    python deliverables/writing-skill/build_site.py --pdf
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
ARTICLES_DIR = ROOT / "articles"

ARTICLES = [
    {
        "video": "BV1ixpd6GENc",
        "kicker": "教程",
        "blurb": "鳞片靠“抛”，不靠“按”；脆靠两次油温，嫩靠腌料把水带进肉里。",
    },
    {
        "video": "BV17DHC6CELr",
        "kicker": "技术解释",
        "blurb": "文字和图片在同一个空间，但分数不能直接当门槛；看排名，切短后要归一化。",
    },
    {
        "video": "BV1B5411A7ax",
        "kicker": "知识 / 文化",
        "blurb": "毛色叫法、地方类群、CFA 登记不是同一回事；古人按“颜色长在哪儿”起名。",
    },
]

EDGE = Path(
    os.environ.get("FACET_STUDIO_EDGE")
    or shutil.which("msedge")
    or r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
)


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def inline(text: str) -> str:
    text = esc(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def md_to_html(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("# "):
            out.append(f"<h1>{inline(stripped[2:])}</h1>")
            i += 1
            continue
        if stripped.startswith("## "):
            out.append(f"<h2>{inline(stripped[3:])}</h2>")
            i += 1
            continue
        if stripped.startswith("### "):
            out.append(f"<h3>{inline(stripped[4:])}</h3>")
            i += 1
            continue
        if stripped == "---":
            out.append("<hr>")
            i += 1
            continue
        image = re.match(r"!\[(.*?)\]\((.*?)\)", stripped)
        if image:
            alt, src = image.group(1), image.group(2)
            out.append(
                f'<figure><img src="{esc(src)}" alt="{esc(alt)}">'
                f"<figcaption>{inline(alt)}</figcaption></figure>"
            )
            i += 1
            continue
        if stripped.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            parsed = [
                [cell.strip() for cell in row.strip("|").split("|")]
                for row in rows
            ]
            if len(parsed) >= 2:
                header = parsed[0]
                body = parsed[2:] if re.match(r"^:?-{2,}", parsed[1][0]) else parsed[1:]
                out.append("<table><thead><tr>")
                out.extend(f"<th>{inline(cell)}</th>" for cell in header)
                out.append("</tr></thead><tbody>")
                for row in body:
                    out.append("<tr>")
                    out.extend(f"<td>{inline(cell)}</td>" for cell in row)
                    out.append("</tr>")
                out.append("</tbody></table>")
            continue
        if stripped.startswith("- "):
            out.append("<ul>")
            while i < len(lines) and lines[i].strip().startswith("- "):
                out.append(f"<li>{inline(lines[i].strip()[2:])}</li>")
                i += 1
            out.append("</ul>")
            continue
        if re.match(r"^\d+\.\s", stripped):
            out.append("<ol>")
            while i < len(lines) and re.match(r"^\d+\.\s", lines[i].strip()):
                item = re.sub(r"^\d+\.\s", "", lines[i].strip())
                out.append(f"<li>{inline(item)}</li>")
                i += 1
            out.append("</ol>")
            continue
        if stripped.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(f"<blockquote>{inline(' '.join(quote))}</blockquote>")
            continue
        para = [stripped]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt or nxt.startswith(("#", "|", "- ", ">", "![", "---")):
                break
            if re.match(r"^\d+\.\s", nxt):
                break
            para.append(nxt)
            i += 1
        text = " ".join(para)
        cls = ' class="source"' if "本文根据" in text else ""
        out.append(f"<p{cls}>{inline(text)}</p>")
    return "\n".join(out)


def read_article(meta: dict) -> tuple[str, str]:
    path = ARTICLES_DIR / meta["video"] / "article.md"
    md = path.read_text(encoding="utf-8")
    # The portfolio shows the article, not the pipeline's source footer.
    md = re.sub(r"\n*---\s*\n+\s*本文根据[^\n]*整理[^\n]*\s*$", "", md).rstrip() + "\n"
    match = re.search(r"^# (.+)$", md, re.M)
    return md, (match.group(1).strip() if match else meta["video"])


def copy_figures(video: str, md: str) -> None:
    """Copy only the images the article actually references."""
    for target in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", md):
        target = target.strip()
        source = ARTICLES_DIR / video / target
        if not source.is_file():
            raise SystemExit(f"missing image: {source}")
        destination = SITE / video / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def build_article(meta: dict, md: str, title: str) -> str:
    body = md_to_html(md)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="stylesheet" href="../assets/style.css">
</head>
<body>
<nav class="topnav"><a href="../index.html">← 文章</a><span>{esc(meta["kicker"])}</span></nav>
<main class="article">
{body}
</main>
</body>
</html>
"""


def build_index(entries: list[tuple[dict, str]]) -> str:
    cards = []
    for index, (meta, title) in enumerate(entries, start=1):
        cards.append(f"""
<a class="card" href="{meta['video']}/index.html">
  <div class="card-meta"><span>文章 {index:02d}</span><span>{esc(meta['kicker'])}</span></div>
  <h3>{esc(title)}</h3>
  <p>{esc(meta['blurb'])}</p>
  <div class="card-foot"><span>读全文</span><span>→</span></div>
</a>""")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>写作作品</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<header class="hero">
  <div class="eyebrow">写作作品 · 2026</div>
  <h1>三篇文章</h1>
  <p class="lede">一篇教程，一篇技术解释，一篇关于猫的名字的文化随笔。每一篇都从具体问题开始，把机制、例子和边界讲清楚。</p>
</header>
<main>
  <div class="cards">{''.join(cards)}</div>
</main>
<footer>写作作品 · 2026</footer>
</body>
</html>
"""


def build_print(entries: list[tuple[dict, str, str]]) -> str:
    parts = []
    cover_items = []
    for meta, title, md in entries:
        body = md_to_html(md).replace('src="figures/', f'src="{meta["video"]}/figures/')
        parts.append(f'<section class="print-article">{body}</section>')
        cover_items.append(f"<li>{esc(title)}</li>")
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>写作作品</title>
<link rel="stylesheet" href="assets/style.css">
<style>
@page {{ size: A4; margin: 18mm 16mm; }}
@media print {{
  .cover {{ page-break-after: always; }}
  .print-article {{ page-break-before: always; }}
  figure, table {{ page-break-inside: avoid; }}
  a {{ color: inherit; text-decoration: none; }}
}}
</style>
</head>
<body class="print">
<section class="cover">
  <div class="eyebrow">写作作品 · 2026</div>
  <h1>三篇文章</h1>
  <p class="lede">一篇教程，一篇技术解释，一篇关于猫的名字的文化随笔。</p>
  <ul class="cover-list">{''.join(cover_items)}</ul>
</section>
{''.join(parts)}
</body>
</html>
"""


def build_pdf() -> Path:
    pdf = SITE / "writing-articles.pdf"
    if not EDGE.exists():
        raise SystemExit(f"Edge not found: {EDGE}")
    subprocess.run(
        [
            str(EDGE),
            "--headless",
            "--disable-gpu",
            "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw",
            "--virtual-time-budget=8000",
            f"--print-to-pdf={pdf}",
            (SITE / "print.html").resolve().as_uri(),
        ],
        check=True,
    )
    return pdf


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the article portfolio.")
    parser.add_argument("--pdf", action="store_true", help="Also print site/print.html to PDF.")
    args = parser.parse_args(argv)

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "assets").mkdir(parents=True)
    shutil.copy2(ROOT / "site_style.css", SITE / "assets/style.css")

    entries: list[tuple[dict, str, str]] = []
    for meta in ARTICLES:
        md, title = read_article(meta)
        copy_figures(meta["video"], md)
        (SITE / meta["video"]).mkdir(parents=True, exist_ok=True)
        (SITE / meta["video"] / "index.html").write_text(
            build_article(meta, md, title), encoding="utf-8"
        )
        entries.append((meta, title, md))

    (SITE / "index.html").write_text(
        build_index([(meta, title) for meta, title, _ in entries]), encoding="utf-8"
    )
    (SITE / "print.html").write_text(build_print(entries), encoding="utf-8")
    print(f"built {SITE}")
    if args.pdf:
        print(f"built {build_pdf()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
