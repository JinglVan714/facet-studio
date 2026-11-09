"""Facet Studio MCP server (P1).

Exposes the writing engine as MCP tools for LibreChat / external agents:

- list_sources / resolve_source
- compile_content
- plan_article
- write_form
- typeset_article
- get_run / review_artifact

P1 is deliberately small: one form per run, cached content only, no video
transcription, no eval.  The writer still runs once; the server only adapts
the existing writing_v4 engine to MCP.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from markdown_it import MarkdownIt

from .core.config import CONTENT_CACHE_DIRNAME, get_settings
from .observability import trace_summary, write_trace
from .providers.llm import DeepSeekLLM
from .writing_v4.planner import LeadPlan, PlannedForm, plan_bundle
from .writing_v4.skills import form_catalog, load_skill
from .writing_v4.tools import compile_content as _compile_content
from .writing_v4.writer import write_form as _write_form

mcp = FastMCP("Facet Studio")

FORM_SKILLS = {
    "long_article": "video-article",
    "wechat_article": "wechat-article",
    "xiaohongshu_note": "xiaohongshu-note",
}
FORM_LABELS = {
    "long_article": "深度总结",
    "wechat_article": "公众号",
    "xiaohongshu_note": "小红书",
}
STATUS_LABELS = {
    "compiled": "内容已编译",
    "planned": "已规划",
    "written": "已写作",
    "typeset": "已排版",
    "partial": "部分完成",
    "approved": "已通过",
    "changes_requested": "待修改",
    "rejected": "已拒绝",
}
FORM_ALIASES = {
    "深度总结": "long_article",
    "长文": "long_article",
    "文章": "long_article",
    "long": "long_article",
    "longform": "long_article",
    "article": "long_article",
    "deep_summary": "long_article",
    "公众号": "wechat_article",
    "公众号文章": "wechat_article",
    "wechat": "wechat_article",
    "wechat_article": "wechat_article",
    "小红书": "xiaohongshu_note",
    "笔记": "xiaohongshu_note",
    "小红书笔记": "xiaohongshu_note",
    "xiaohongshu": "xiaohongshu_note",
    "xhs": "xiaohongshu_note",
    "xiaohongshu_note": "xiaohongshu_note",
}


def _normalize_form(form: str) -> str:
    key = (form or "").strip()
    return FORM_ALIASES.get(key) or FORM_ALIASES.get(key.lower()) or key

IMAGE_RE = re.compile(r"!\[([^\]]*)\]\((figures/[^)\s]+)\)")

COPY_IMAGE_SCRIPT = """
<script>
async function copyImage(src) {
  try {
    if (!navigator.clipboard || !window.ClipboardItem) {
      throw new Error('当前浏览器不支持复制图片');
    }
    const resp = await fetch(src, {cache: 'no-store'});
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    let blob = await resp.blob();
    if (blob.type !== 'image/png') {
      const bitmap = await createImageBitmap(blob);
      const canvas = document.createElement('canvas');
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      canvas.getContext('2d').drawImage(bitmap, 0, 0);
      blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
    }
    await navigator.clipboard.write([new ClipboardItem({'image/png': blob})]);
    alert('图片已复制，可粘贴到手机传输助手或编辑器');
  } catch (err) {
    alert('复制失败：' + err);
  }
}
function bindCopyButtons() {
  document.querySelectorAll('.copy-image-btn').forEach((btn) => {
    if (btn.dataset.bound) return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', () => copyImage(btn.dataset.src));
  });
}
bindCopyButtons();
</script>
"""

COPY_NOTE_SCRIPT = """
<script>
document.getElementById('copy-note-btn').addEventListener('click', async () => {
  const text = document.getElementById('note-text').innerText.trim();
  try {
    await navigator.clipboard.writeText(text);
    alert('已复制标题、正文和标签');
  } catch (err) {
    alert('复制失败：' + err);
  }
});
</script>
"""


def _settings():
    return get_settings()


def _project() -> Path:
    return _settings().project_root


def _runs_root() -> Path:
    root = _settings().runs_root / "product_v1"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Append call records without rewriting the existing trace."""
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _clip_error(value: object, limit: int = 1200) -> str:
    """Keep tool stderr useful without dumping pages of TeX logs into run data."""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n…（已截断）"


def _progress_callback(ctx: Context | None):
    """Bridge workflow stage events to MCP progress notifications."""
    if ctx is None:
        return None

    def report(event: dict[str, Any], step: int, total: int) -> None:
        label = str(event.get("node") or event.get("type") or "workflow")
        try:
            ctx.report_progress(step, total, label)
        except Exception:  # noqa: BLE001 - progress is advisory
            pass

    return report


def _source_dir(video_id: str) -> Path:
    return _settings().data_root / video_id


def _content_path(video_id: str) -> Path:
    """Cached content manuscript for a BV id."""
    root = _settings().runs_root / CONTENT_CACHE_DIRNAME
    candidates = [
        root / video_id / "content_final_v3" / "content.md",
        root / video_id / "content_final_v2" / "content.md",
        root / video_id / "content_final" / "content.md",
    ]
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"没有找到 {video_id} 的缓存内容稿；P1 只读缓存，不重跑视频。"
    )


def _source_meta(video_id: str, content: Path) -> dict[str, Any]:
    source_path = _source_dir(video_id) / "source.json"
    meta: dict[str, Any] = {}
    if source_path.is_file():
        meta = _read_json(source_path)
    figures = []
    fig_dir = content.parent / "figures"
    if fig_dir.is_dir():
        figures = sorted(
            f"figures/{item.name}" for item in fig_dir.iterdir() if item.is_file()
        )
    cover = _source_dir(video_id) / "cover.jpg"
    if meta.get("cover_path"):
        cover = Path(str(meta["cover_path"]))
        if not cover.is_absolute():
            cover = _project() / cover
    return {
        "video_id": video_id,
        "title": str(meta.get("title") or video_id),
        "uploader": str(meta.get("uploader") or ""),
        "content_path": str(content),
        "content_chars": len(content.read_text(encoding="utf-8")),
        "figures": figures,
        "figure_count": len(figures),
        "cover": str(cover) if cover.is_file() else "",
    }


def _list_cached_sources() -> list[dict[str, Any]]:
    root = _settings().runs_root / CONTENT_CACHE_DIRNAME
    result: list[dict[str, Any]] = []
    if not root.is_dir():
        return result
    for path in sorted(root.glob("*/content_final_v3/content.md")):
        video_id = path.parent.parent.name
        try:
            result.append(_source_meta(video_id, path))
        except Exception:
            continue
    return result


def _run_dir(run_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", run_id)
    return _runs_root() / safe


def _new_run_id(video_id: str, form: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{video_id}_{form}"


def _load_run(run_id: str) -> tuple[Path, dict[str, Any]]:
    run_dir = _run_dir(run_id)
    meta_path = run_dir / "run_meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"run 不存在：{run_id}")
    return run_dir, _read_json(meta_path)


def _save_run(run_dir: Path, meta: dict[str, Any]) -> None:
    meta["updated_at"] = _now()
    _write_json(run_dir / "run_meta.json", meta)


def _ensure_compiled(
    *, video_id: str, content: Path, run_dir: Path
) -> dict[str, Any]:
    content_dir = run_dir / "content"
    if not (content_dir / "content.md").is_file():
        _compile_content(
            {
                "content_path": str(content),
                "out_dir": str(content_dir),
            }
        )
    return _source_meta(video_id, content_dir / "content.md")


def _form_request(plan: LeadPlan, form: str) -> str:
    item = next((entry for entry in plan.forms if entry.form == form), None)
    if item is None:
        raise ValueError(f"计划里没有 form：{form}")
    parts = [
        f"只写这个产物：{form}（{FORM_LABELS.get(form, form)}）。",
        "不要写其他形态；不要输出其他产物的标题或段落。",
    ]
    if item.brief:
        parts.append("编辑方向：" + item.brief)
    if item.angle:
        parts.append("角度：" + item.angle)
    if plan.shared_constraints:
        parts.append("共享约束：" + "；".join(plan.shared_constraints))
    if item.must_use_figures:
        parts.append(
            "可选关键帧建议（默认不用；只有通过极紧门槛才用，最多 1 张）："
            + "、".join(item.must_use_figures)
        )
    return "\n\n".join(part for part in parts if part)


def _client(sink=None):
    settings = _settings()
    if not settings.provider_configured:
        raise RuntimeError(
            "provider 未配置（DEEPSEEK_API_KEY / DEEPSEEK_MODEL）；"
            "P1 需要真实 writer 调用。"
        )
    return DeepSeekLLM(settings, call_sink=sink)


def _inline_images(markdown: str, form_dir: Path) -> str:
    def repl(match: re.Match[str]) -> str:
        alt, rel = match.group(1), match.group(2)
        path = (form_dir / rel).resolve()
        if not path.is_file():
            return match.group(0)
        media = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"![{alt}](data:{media};base64,{data})"

    return IMAGE_RE.sub(repl, markdown)


def _reading_stats(markdown: str) -> tuple[int, int]:
    """Rough reader-facing size: CJK chars + Latin words, ~400 per minute."""
    text = re.sub(r"<!--.*?-->", " ", markdown, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    cjk = len(re.findall(r"[㐀-鿿]", text))
    latin = len(re.findall(r"[A-Za-z0-9]+", text))
    total = cjk + latin
    minutes = max(1, round(total / 400)) if total else 1
    return total, minutes


def _add_heading_ids(html: str) -> tuple[str, list[tuple[str, str]]]:
    """Give H2s stable anchors and return a TOC list."""
    toc: list[tuple[str, str]] = []
    counter = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal counter
        counter += 1
        inner = match.group(1)
        plain = re.sub(r"<[^>]+>", "", inner)
        plain = re.sub(r"[*_`#>\[\]]", "", plain).strip()
        anchor = f"section-{counter}"
        toc.append((anchor, plain))
        return f'<h2 id="{anchor}">{inner}</h2>'

    return re.sub(r"<h2>(.*?)</h2>", repl, html, flags=re.DOTALL), toc


def _toc_html(items: list[tuple[str, str]]) -> str:
    if len(items) < 2:
        return ""
    links = "".join(
        f'<a href="#{anchor}">{_html_escape(label)}</a>'
        for anchor, label in items
    )
    return (
        '<nav class="toc" aria-label="目录">'
        '<div class="toc-title">本文目录</div>'
        f'<div class="toc-links">{links}</div>'
        "</nav>"
    )


def _render_reader(
    markdown: str,
    form_dir: Path,
    title: str,
    *,
    inline_images: bool = False,
    trace_url: str | None = None,
    form_label: str = "深度总结",
) -> str:
    md = MarkdownIt("commonmark", {"html": False})
    md.enable("table")
    source = _inline_images(markdown, form_dir) if inline_images else markdown
    body = md.render(_strip_first_heading(source))
    body = body.replace(
        "<table>",
        '<div class="table-hint">表格可左右滑动</div><div class="table-wrap"><table>',
    ).replace("</table>", "</table></div>")
    body, toc_items = _add_heading_ids(body)
    total, minutes = _reading_stats(markdown)
    toc = _toc_html(toc_items)
    meta = f"{total:,} 字 · 约 {minutes} 分钟"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html_escape(title)}</title>
<style>
:root{{--bg:#f2efe8;--paper:#fffdf9;--ink:#1b1916;--muted:#6b645b;--line:#ddd6c9;--accent:#b5502f;--accent-soft:#f3e4dc}}
*{{box-sizing:border-box}}
body{{margin:0;background:radial-gradient(1200px 600px at 50% -10%,#fffdf9 0%,var(--bg) 55%);
color:var(--ink);font-family:system-ui,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;
line-height:1.8;-webkit-font-smoothing:antialiased}}
.page{{max-width:780px;margin:0 auto;padding:44px 22px 88px}}
.hero{{background:linear-gradient(180deg,#fffdf9 0%,#faf6ee 100%);border:1px solid var(--line);
border-radius:20px;padding:34px 42px 28px;margin:0 0 18px;box-shadow:0 16px 44px rgba(66,50,32,.08)}}
.kicker{{font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);font-weight:700}}
h1{{font-family:"Noto Serif SC","Source Han Serif SC","Songti SC",SimSun,Georgia,serif;
font-size:clamp(30px,4.6vw,42px);line-height:1.22;letter-spacing:-.015em;margin:10px 0 14px;text-wrap:balance}}
.meta{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;font-size:13px;color:var(--muted)}}
.meta span{{display:inline-flex;align-items:center;gap:6px}}
.meta a{{color:var(--accent);text-decoration:none}}
.dot{{width:3px;height:3px;border-radius:50%;background:var(--line)}}
.toc{{background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:18px 22px;margin:0 0 18px}}
.toc-title{{font-size:12px;letter-spacing:.12em;color:var(--muted);margin:0 0 10px}}
.toc-links{{display:grid;gap:7px}}
.toc a{{color:var(--ink);text-decoration:none;font-size:14.5px;line-height:1.45;
padding-left:14px;border-left:2px solid var(--line)}}
.toc a:hover{{border-color:var(--accent);color:var(--accent)}}
.article{{background:var(--paper);border:1px solid var(--line);border-radius:20px;
padding:38px 42px 46px;box-shadow:0 16px 44px rgba(66,50,32,.07)}}
h2{{font-family:"Noto Serif SC","Source Han Serif SC","Songti SC",SimSun,Georgia,serif;
font-size:26px;line-height:1.35;margin:44px 0 14px;padding-top:20px;
border-top:1px solid var(--line);scroll-margin-top:24px}}
.article > h2:first-child{{margin-top:0;padding-top:0;border-top:0}}
p{{font-size:17.5px;line-height:1.9;margin:0 0 18px}}
figure{{margin:28px 0}}img{{max-width:100%;height:auto;border-radius:10px;display:block}}
img[src$=".svg"]{{width:100%;height:auto}}
figcaption{{font-size:13px;color:var(--muted);margin-top:8px}}
.table-hint{{display:none}}
@media(max-width:640px){{.table-hint{{display:block;font-size:12px;color:var(--muted);margin:18px 0 4px}}}}
.table-wrap{{overflow-x:auto;margin:24px 0;border:1px solid var(--line);border-radius:12px;background:#fff;-webkit-overflow-scrolling:touch}}
table{{width:100%;border-collapse:collapse;margin:0;font-size:14.5px;background:#fff}}
.table-wrap table{{min-width:680px}}
th,td{{border-bottom:1px solid var(--line);padding:11px 13px;text-align:left;vertical-align:top}}
th{{background:#f1ede4;font-weight:650;color:#3c372f;white-space:nowrap}}
tbody tr:nth-child(even){{background:#faf8f3}}
tbody tr:last-child td{{border-bottom:0}}
td{{font-variant-numeric:tabular-nums}}
blockquote{{margin:24px 0;padding:16px 20px;border-left:4px solid var(--accent);
border-radius:0 12px 12px 0;background:#fbf4ef;color:#4a433c}}
hr{{border:0;border-top:1px solid var(--line);margin:40px 0}}
a{{color:var(--accent)}}
code{{background:#f1ede4;padding:2px 6px;border-radius:5px;font-size:.92em}}
pre{{background:#211d19;color:#f4f1e8;padding:18px 20px;border-radius:12px;
overflow-x:auto;font-size:13.5px;line-height:1.65;margin:24px 0}}
pre code{{background:none;padding:0;color:inherit;font-size:inherit}}
.footer{{max-width:780px;margin:0 auto;padding:0 22px 48px;text-align:center;
font-size:12px;color:var(--muted)}}
@media(max-width:640px){{
.page{{padding:24px 12px 56px}}
.hero,.article{{padding:26px 20px;border-radius:16px}}
p{{font-size:17px;line-height:1.85}}
h2{{font-size:23px;margin-top:36px}}
.toc{{padding:16px 18px}}
}}
</style>
</head>
<body>
<div class="page">
<header class="hero">
<div class="kicker">{_html_escape(form_label)}</div>
<h1>{_html_escape(title)}</h1>
<div class="meta"><span>{meta}</span><span class="dot"></span><span>Facet Studio</span>{f'<span class="dot"></span><a href="{_html_escape(trace_url)}">运行数据</a>' if trace_url else ''}</div>
</header>
{toc}
<main class="article">{body}</main>
</div>
<div class="footer">由 Facet Studio 根据视频内容整理{f' · <a href="{_html_escape(trace_url)}">运行数据</a>' if trace_url else ''}</div>
</body></html>"""


def _parse_xhs_note(markdown: str) -> dict[str, Any]:
    """Parse a note.md into title/cover/body/gallery/tags/source."""
    title = _first_heading(markdown)
    cover_text = ""
    body_lines: list[str] = []
    gallery: list[tuple[str, str]] = []
    tags: list[str] = []
    source = ""
    section = "body"
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            continue
        if stripped.startswith("> 封面："):
            cover_text = stripped[len("> 封面：") :].strip()
            continue
        if stripped == "## 配图":
            section = "gallery"
            continue
        if stripped == "## 标签":
            section = "tags"
            continue
        if stripped.startswith(("内容参考", "本文根据", "本脚本根据")):
            source = stripped
            continue
        if section == "gallery" and stripped.startswith("- "):
            match = re.match(r"-\s*(figures/[^\s：:]+)\s*[：:]\s*(.*)", stripped)
            if match:
                gallery.append((match.group(1), match.group(2).strip()))
            continue
        if section == "tags":
            if stripped:
                tags.extend(re.findall(r"#[^\s#]+", stripped))
            continue
        if stripped == "---":
            continue
        body_lines.append(line)
    body_markdown = "\n".join(body_lines).strip()
    body = body_markdown
    body = re.sub(r"\*\*(.+?)\*\*", r"\1", body)
    body = re.sub(r"\*(.+?)\*", r"\1", body)
    body = re.sub(r"`(.+?)`", r"\1", body)
    body = re.sub(r"^#{2,6}\s*", "", body, flags=re.MULTILINE)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return {
        "title": title,
        "cover_text": cover_text,
        "body": body,
        "body_markdown": body_markdown,
        "gallery": gallery,
        "tags": list(dict.fromkeys(tags)),
        "source": source,
    }


def _xhs_export(
    *, form_dir: Path, markdown: str, request: str = ""
) -> dict[str, Any]:
    """Build an App-import-friendly Xiaohongshu export folder and PNG cards."""
    parsed = _parse_xhs_note(markdown)
    export_dir = form_dir / "xhs_export"
    export_dir.mkdir(parents=True, exist_ok=True)
    for stale in export_dir.glob("*.png"):
        stale.unlink()
    (export_dir / "title.txt").write_text(parsed["title"] + "\n", encoding="utf-8")
    (export_dir / "body.txt").write_text(parsed["body"] + "\n", encoding="utf-8")
    (export_dir / "tags.txt").write_text(" ".join(parsed["tags"]) + "\n", encoding="utf-8")
    source_path = export_dir / "source.txt"
    if parsed["source"]:
        source_path.write_text(parsed["source"] + "\n", encoding="utf-8")
    elif source_path.exists():
        source_path.unlink()
    gallery = [
        {
            "path": str((form_dir / rel).resolve()),
            "rel": rel,
            "caption": caption,
        }
        for rel, caption in parsed["gallery"]
        if (form_dir / rel).is_file()
    ]
    total_cards = 1 + max(len(gallery) - 1, 0)
    cards: list[dict[str, Any]] = [
        {
            "kind": "cover",
            "title": parsed["cover_text"] or parsed["title"],
            "subtitle": parsed["title"] if parsed["cover_text"] else "",
            "image": gallery[0]["path"] if gallery else "",
            "caption": "",
            "footer": "",
            "index": "" if total_cards == 1 else f"01 / {total_cards:02d}",
        }
    ]
    for index, item in enumerate(gallery[1:], start=2):
        cards.append(
            {
                "kind": "image",
                "image": item["path"],
                "caption": item["caption"],
                "index": f"{index:02d} / {total_cards:02d}",
            }
        )
    manifest = {
        "title": parsed["title"],
        "cover_text": parsed["cover_text"],
        "tags": parsed["tags"],
        "source": parsed["source"],
        "images": [
            {
                "file": f"{index:02d}_{'cover' if index == 1 else 'card'}.png",
                "rel": (gallery[index - 1]["rel"] if index <= len(gallery) else ""),
                "caption": (gallery[index - 1]["caption"] if index <= len(gallery) else ""),
            }
            for index in range(1, len(cards) + 1)
        ],
    }
    (export_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (export_dir / "README.txt").write_text(
        "小红书导入步骤：\n"
        "1. 打开小红书 App → 发布 → 图文。\n"
        "2. 按 01_cover.png、02_card.png… 的顺序上传图片。\n"
        "3. 粘贴 title.txt 的标题、body.txt 的正文；tags.txt 的标签按需加在正文末尾。\n"
        "4. 封面图已是 3:4；正文图可替换成你更满意的关键帧。\n"
        "5. source.txt 只作素材出处，可不发布。\n",
        encoding="utf-8",
    )
    # Kicker is request-driven, not inferred from the video's topic/type.
    kicker = "教程" if "教程" in request else "笔记"
    spec = {
        "out_dir": str(export_dir),
        "brand": "FACET STUDIO",
        "kicker": kicker,
        "cover_text": parsed["cover_text"],
        "title": parsed["title"],
        "cards": cards,
    }
    spec_path = export_dir / "cards_spec.json"
    spec_path.write_text(
        json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    renderer = _project() / "integrations" / "xhs" / "render_cards.mjs"
    node = shutil.which("node") or "node"
    # Playwright is resolved by the renderer itself: local node_modules,
    # then FACET_STUDIO_PLAYWRIGHT.  Never hard-code a machine-specific path.
    env = dict(os.environ)
    error = ""
    if renderer.is_file():
        try:
            proc = subprocess.run(
                [node, str(renderer), str(spec_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
                timeout=180,
            )
            if proc.returncode != 0:
                error = _clip_error(
                    proc.stderr or proc.stdout or "card renderer failed"
                )
        except Exception as exc:  # noqa: BLE001 - export is partial, keep text files
            error = _clip_error(f"{type(exc).__name__}: {exc}")
    else:
        error = _clip_error(f"card renderer not found: {renderer}")
    images = sorted(
        f"xhs_export/{item.name}"
        for item in export_dir.glob("*.png")
    )
    return {
        "export_dir": str(export_dir),
        "images": images,
        "manifest": str(export_dir / "manifest.json"),
        "error": error,
    }


def _strip_first_heading(markdown: str) -> str:
    """Remove the document H1 so the copied WeChat body excludes the title."""
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            del lines[index]
            break
    return "\n".join(lines).strip() + "\n"


def _render_wechat(
    markdown: str,
    form_dir: Path,
    title: str,
    *,
    trace_url: str | None = None,
) -> str:
    """Render a WeChat-friendly HTML page with inline styles for copy/paste."""
    md = MarkdownIt("commonmark", {"html": False})
    md.enable("table")
    body = md.render(_strip_first_heading(markdown))
    styles = {
        "h1": "font-family:'Noto Serif SC','Songti SC',SimSun,Georgia,serif;font-size:27px;line-height:1.4;margin:0 0 22px;color:#191817;text-wrap:balance;",
        "h2": "font-size:22px;font-family:'Noto Serif SC','Songti SC',SimSun,Georgia,serif;line-height:1.5;margin:34px 0 14px;padding-top:16px;border-top:1px solid #e5ded3;color:#191817;",
        "h3": "font-size:18px;line-height:1.5;margin:26px 0 10px;color:#191817;",
        "p": "font-size:17px;line-height:1.85;margin:0 0 18px;color:#2f2a25;",
        "img": "max-width:100%;max-height:520px;width:auto;height:auto;display:block;margin:18px auto;border-radius:6px;",
        "figure": "margin:24px 0;",
        "figcaption": "font-size:13px;color:#8a847a;text-align:center;margin-top:6px;",
        "table": "width:100%;border-collapse:collapse;margin:20px 0;font-size:15px;",
        "th": "border:1px solid #d8d3c8;background:#f1ede4;padding:10px 12px;text-align:left;font-weight:650;",
        "td": "border:1px solid #d8d3c8;padding:10px 12px;text-align:left;font-variant-numeric:tabular-nums;",
        "blockquote": "margin:20px 0;padding:14px 18px;border-left:4px solid #c96442;background:#fbf4ef;color:#4a433c;border-radius:0 10px 10px 0;",
        "li": "font-size:17px;line-height:1.85;color:#2f2a25;",
        "pre": "background:#211d19;color:#f4f1e8;padding:16px 18px;border-radius:10px;overflow-x:auto;font-size:13.5px;line-height:1.65;margin:20px 0;",
        "code": "background:#f1ede4;padding:2px 6px;border-radius:5px;font-size:.92em;",
    }
    def _add_style(match: re.Match[str], tag: str, style: str) -> str:
        attrs = (match.group(1) or "").rstrip()
        if attrs.endswith("/"):
            attrs = attrs[:-1].rstrip()
        return f"<{tag}{attrs} style=\"{style}\">"

    for tag, style in styles.items():
        body = re.sub(
            rf"<{tag}(\s[^>]*)?>",
            lambda m, t=tag, s=style: _add_style(m, t, s),
            body,
        )
    # An SVG with only a viewBox has a 300x150 intrinsic size in an <img>;
    # without an explicit width the diagram renders tiny and its labels are
    # unreadable.  Fill the column, keep the aspect ratio.
    body = re.sub(
        r'<img[^>]+src="[^"]+\.svg"[^>]*>',
        lambda m: m.group(0).replace(
            "max-height:520px;width:auto;", "max-height:none;width:100%;"
        ),
        body,
    )
    # The <code> chip inside a dark <pre> would be a light block; drop its
    # inline style so it inherits the code block colors.
    body = re.sub(
        r'(<pre[^>]*>.*?)<code[^>]*? style="[^"]*"',
        r"\1<code",
        body,
        flags=re.DOTALL,
    )
    # Wide tables should scroll on a phone instead of forcing the column wider.
    # Two-column tables fit the 520px preview; only 3+ columns need a min-width.
    def _wrap_wechat_table(match: re.Match[str]) -> str:
        table = match.group(0)
        columns = len(re.findall(r"<th(?:\s|>)", table))
        min_width = 560 if columns >= 4 else 480 if columns == 3 else 0
        if min_width:
            table = table.replace(' style="', f' style="min-width:{min_width}px;', 1)
            hint = (
                '<div class="table-hint copy-ui" style="font-size:12px;color:#8a847a;'
                'margin:16px 0 6px;">表格可左右滑动</div>'
            )
        else:
            hint = ""
        return (
            hint
            + '<div style="overflow-x:auto;border:1px solid #e5ded3;border-radius:10px;'
            'margin:20px 0;">'
            + table
            + "</div>"
        )

    body = re.sub(r"<table[^>]*>.*?</table>", _wrap_wechat_table, body, flags=re.DOTALL)
    total, minutes = _reading_stats(markdown)
    meta = f"{total:,} 字 · 约 {minutes} 分钟"
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html_escape(title)}</title>
<style>
#wechat-article table{{table-layout:auto}}
#wechat-article pre code{{background:none;padding:0;color:inherit}}
</style></head>
<body style="margin:0;background:radial-gradient(900px 500px at 50% -10%,#fffdf9 0%,#f2efe8 60%);font-family:system-ui,'Segoe UI','Microsoft YaHei','PingFang SC',sans-serif;">
<div style="max-width:520px;margin:0 auto;padding:28px 12px 76px;">
<div style="background:#fffdf9;border:1px solid #e5ded3;border-radius:20px;box-shadow:0 16px 44px rgba(66,50,32,.08);overflow:hidden;">
<div style="padding:20px 26px 0;display:flex;align-items:center;justify-content:space-between;gap:12px;font-size:12px;letter-spacing:.1em;color:#8a847a;">
<span style="color:#c96442;font-weight:700;">公众号预览</span>
<span>{meta}{f' · <a href="{_html_escape(trace_url)}" style="color:#8a847a;">运行数据</a>' if trace_url else ''}</span>
</div>
<header style="padding:14px 26px 0;"><h1 style="{styles['h1']}">{_html_escape(title)}</h1></header>
<main id="wechat-article" style="padding:0 26px 42px;">
{body}
</main>
</div>
</div>
{COPY_IMAGE_SCRIPT}
<script>
function copyWechat() {{
  const el = document.getElementById('wechat-article');
  const clone = el.cloneNode(true);
  clone.querySelectorAll('.copy-ui').forEach((node) => node.remove());
  const html = clone.innerHTML;
  if (navigator.clipboard && window.ClipboardItem) {{
    navigator.clipboard.write([new ClipboardItem({{'text/html': new Blob([html], {{type:'text/html'}})}})]).then(()=>alert('已复制，去公众号编辑器粘贴'));
  }} else {{
    const range = document.createRange(); range.selectNodeContents(el);
    const sel = window.getSelection(); sel.removeAllRanges(); sel.addRange(range);
    document.execCommand('copy'); alert('已选中，按 Ctrl+C 复制');
  }}
}}
function enhanceWechatImages() {{
  const el = document.getElementById('wechat-article');
  el.querySelectorAll('img').forEach((img, index) => {{
    const src = img.currentSrc || img.src;
    // SVG diagrams are vector assets, not copyable photos; skip the photo bar.
    if (src.toLowerCase().endsWith('.svg')) return;
    const bar = document.createElement('div');
    bar.className = 'copy-ui';
    bar.style.cssText = 'display:flex;gap:8px;justify-content:flex-end;margin:-8px 0 18px;';
    const copy = document.createElement('button');
    copy.type = 'button';
    copy.className = 'copy-image-btn';
    copy.dataset.src = img.currentSrc || img.src;
    copy.textContent = '复制图片';
    copy.style.cssText = 'font:inherit;font-size:12px;color:#5a554e;background:#eeede6;border:1px solid #d8d3c8;border-radius:999px;padding:4px 10px;cursor:pointer;';
    const dl = document.createElement('a');
    dl.href = img.currentSrc || img.src;
    dl.download = 'image-' + (index + 1) + '.jpg';
    dl.textContent = '下载';
    dl.style.cssText = 'font-size:12px;color:#5a554e;background:#eeede6;border:1px solid #d8d3c8;border-radius:999px;padding:4px 10px;text-decoration:none;';
    bar.append(copy, dl);
    img.insertAdjacentElement('afterend', bar);
  }});
  bindCopyButtons();
}}
enhanceWechatImages();
</script>
<button onclick="copyWechat()" style="position:fixed;right:24px;bottom:24px;padding:10px 16px;border-radius:999px;border:1px solid #d8d3c8;background:#191817;color:#fff;cursor:pointer;">复制正文</button>
</body></html>"""


def _pdf_title(title: str) -> str:
    """Escape a title and break long Chinese titles at punctuation.

    A single CJK title can leave one or two characters alone on the second
    line; splitting at the punctuation nearest the middle keeps the cover
    balanced without hard-coding a particular title.
    """
    title = str(title or "").strip()
    if len(title) <= 20:
        return _latex_escape(title)
    candidates = [i for i, char in enumerate(title) if char in "，。；：、"]
    if not candidates:
        return _latex_escape(title)
    midpoint = len(title) / 2
    cut = min(candidates, key=lambda i: abs(i + 1 - midpoint)) + 1
    first, second = title[:cut].strip(), title[cut:].strip()
    if not first or not second:
        return _latex_escape(title)
    return _latex_escape(first) + r" \\ " + _latex_escape(second)


def _latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in str(text))


def _pdf_ready_markdown(form_dir: Path, markdown: str) -> tuple[str, list[str]]:
    """Rewrite ``figures/*.svg`` to PNG so XeLaTeX can measure them.

    LaTeX cannot include SVG directly (no BoundingBox).  The writing layer
    emits SVG by default, so the PDF path renders each referenced SVG once and
    swaps the image path in a PDF-only copy of the Markdown.  The HTML/reader
    artifacts keep the SVG.
    """
    refs = sorted(set(re.findall(r"\((figures/[^)\s]+\.svg)\)", markdown)))
    if not refs:
        return markdown, []
    node = os.environ.get("FACET_STUDIO_NODE") or shutil.which("node")
    renderer = _project() / "integrations" / "pdf" / "render_svg_png.mjs"
    if not node or not renderer.is_file():
        return markdown, ["SVG 转 PNG 失败：找不到 node 或 render_svg_png.mjs"]
    items = []
    for ref in refs:
        svg = form_dir / ref
        png = svg.with_suffix(".png")
        if not svg.is_file():
            return markdown, [f"SVG 转 PNG 失败：缺少 {ref}"]
        if not png.is_file() or png.stat().st_mtime < svg.stat().st_mtime:
            items.append({"svg": str(svg), "png": str(png)})
    if items:
        spec_path = form_dir / "_pdf_svg.json"
        spec_path.write_text(
            json.dumps({"items": items}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [node, str(renderer), str(spec_path)],
            cwd=form_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(os.environ),
            timeout=180,
        )
        if proc.returncode != 0:
            return markdown, [
                "SVG 转 PNG 失败：" + _clip_error(proc.stderr or proc.stdout, 300)
            ]
    missing = [ref for ref in refs if not (form_dir / ref).with_suffix(".png").is_file()]
    if missing:
        return markdown, ["SVG 转 PNG 失败：未生成 " + ", ".join(missing)]
    for ref in refs:
        markdown = markdown.replace(f"({ref})", f"({ref[:-4]}.png)")
    return markdown, []


def _pdf_cover(form_dir: Path, markdown: str, video_cover: str = "") -> str:
    """Prefer the platform video cover; fall back to the first real photo.

    Diagrams (SVG or converted SVG PNGs) must never become the title-page
    cover.  The video cover is copied into the form directory so LaTeX can use
    a stable relative path.
    """
    if video_cover:
        source = Path(video_cover)
        if source.is_file():
            suffix = source.suffix.lower() or ".jpg"
            destination = form_dir / "figures" / f"video-cover{suffix}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            return f"figures/video-cover{suffix}"
    images = re.findall(r"!\[[^\]]*\]\((figures/[^)\s]+)\)", markdown)
    photos = [
        item
        for item in images
        if not item.lower().endswith(".svg")
        and not Path(item).name.startswith("svg-")
    ]
    return photos[0] if photos else ""


def _export_pdf(
    *, form_dir: Path, markdown: str, title: str, source: str, video_cover: str = ""
) -> dict[str, Any]:
    """Markdown → Pandoc LaTeX body → Tectonic PDF (long_article)."""
    pandoc = os.environ.get("FACET_STUDIO_PANDOC") or shutil.which("pandoc")
    tectonic = os.environ.get("FACET_STUDIO_TECTONIC") or shutil.which("tectonic")
    template_path = _project() / "integrations" / "pdf" / "facet-template.tex"
    if not pandoc or not Path(pandoc).is_file():
        return {
            "error": (
                "pandoc not found; install pandoc or set FACET_STUDIO_PANDOC"
            )
        }
    if not tectonic or not Path(tectonic).is_file():
        return {
            "error": (
                "tectonic not found; install tectonic or set FACET_STUDIO_TECTONIC"
            )
        }
    if not template_path.is_file():
        return {"error": f"template not found: {template_path}"}

    pdf_markdown, svg_errors = _pdf_ready_markdown(form_dir, markdown)
    if svg_errors:
        return {"error": "; ".join(svg_errors)}
    body_md = re.sub(r"^# .*\n", "", pdf_markdown, count=1, flags=re.MULTILINE)
    # The source line is already on the cover; keeping it at the end creates
    # an orphan page in the PDF.  Strip it (and its trailing rule) from body.
    source_re = re.compile(
        r"\n\s*(?:本文根据|内容参考|本脚本根据)[^\n]*\s*$"
    )
    body_md, removed = source_re.subn("\n", body_md)
    if removed:
        body_md = re.sub(r"\n---\s*$", "\n", body_md.rstrip()) + "\n"
    body_md_path = form_dir / "_pdf_body.md"
    body_tex_path = form_dir / "_pdf_body.tex"
    body_md_path.write_text(body_md, encoding="utf-8")
    proc = subprocess.run(
        [
            pandoc,
            "-f",
            "markdown",
            "-t",
            "latex",
            "--wrap=none",
            "--listings",
            "--top-level-division=section",
            "--shift-heading-level-by=-1",
            "--resource-path=.",
            "-o",
            str(body_tex_path),
            str(body_md_path),
        ],
        cwd=form_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    if proc.returncode != 0:
        return {
            "error": _clip_error(proc.stderr or proc.stdout or "pandoc failed"),
            "tex_path": "",
        }
    body_tex = body_tex_path.read_text(encoding="utf-8")
    cover = _pdf_cover(form_dir, pdf_markdown, video_cover)
    template = template_path.read_text(encoding="utf-8")
    tex = (
        template.replace("@@TITLE@@", _pdf_title(title))
        .replace("@@DATE@@", _latex_escape(datetime.now().strftime("%Y-%m-%d")))
        .replace("@@SOURCE@@", _latex_escape(source))
        .replace("@@COVER@@", cover)
        .replace("@@BODY@@", body_tex)
    )
    tex_path = form_dir / "article.tex"
    tex_path.write_text(tex, encoding="utf-8")
    proc = subprocess.run(
        [tectonic, "article.tex"],
        cwd=form_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    pdf_path = form_dir / "article.pdf"
    if proc.returncode != 0 or not pdf_path.is_file():
        return {
            "error": _clip_error(proc.stderr or proc.stdout or "tectonic failed"),
            "tex_path": str(tex_path),
        }
    pages = 0
    try:
        from pypdf import PdfReader  # BSD-3-Clause

        pages = len(PdfReader(str(pdf_path)).pages)
    except Exception:  # noqa: BLE001 - verification is advisory
        pass
    return {
        "pdf_path": str(pdf_path),
        "tex_path": str(tex_path),
        "pages": pages,
        "error": "",
    }


def _render_xhs(
    markdown: str,
    form_dir: Path,
    title: str,
    card_images: list[str] | None = None,
    trace_url: str | None = None,
) -> str:
    """Render a copy-friendly Xiaohongshu page: cards first, then note text.

    ``card_images`` are the already-rendered 3:4 PNGs (relative to ``form_dir``).
    When they are unavailable, fall back to the source figures inside a 3:4
    frame with ``object-fit: contain`` so nothing is cropped.
    """
    parsed = _parse_xhs_note(markdown)
    md = MarkdownIt("commonmark", {"html": False})
    md.enable("table")
    body = md.render(parsed["body_markdown"])

    def image_actions(src: str) -> str:
        src_attr = _html_escape(src)
        return (
            '<div class="card-actions">'
            f'<button type="button" class="copy-image-btn" '
            f'data-src="{src_attr}">复制图片</button>'
            f'<a class="download-link" href="{src_attr}" download>下载</a>'
            "</div>"
        )

    cards: list[str] = []
    for item in card_images or []:
        if (form_dir / item).is_file():
            cards.append(
                f'<figure class="card"><img src="{_html_escape(item)}" alt="">'
                f"{image_actions(item)}</figure>"
            )
    if not cards:
        for index, (src, caption) in enumerate(parsed["gallery"]):
            overlay = (
                parsed["cover_text"]
                if index == 0 and parsed["cover_text"]
                else caption
            )
            cards.append(
                '<figure class="card fallback">'
                f'<div class="card-box"><img src="{_html_escape(src)}" '
                f'alt="{_html_escape(caption)}"></div>'
                f'<figcaption>{_html_escape(overlay)}</figcaption>'
                f"{image_actions(src)}</figure>"
            )
    text_only_cover = False
    if not cards and parsed["cover_text"]:
        text_only_cover = True
        cards.append(
            '<figure class="card fallback text-only">'
            '<div class="card-box">'
            '<div class="cover-kicker">FACET STUDIO · 笔记</div>'
            f'<div class="cover-text">{_html_escape(parsed["cover_text"])}</div>'
            '<div class="cover-rule"></div>'
            "</div></figure>"
        )
    cards_head = (
        "封面 · 文字卡"
        if text_only_cover
        else f"配图 · {len(cards)} 张（按顺序保存或上传）"
    )
    cards_html = (
        '<section class="cards">'
        f'<div class="cards-head">{cards_head}</div>'
        f'<div class="card-list">{"".join(cards)}</div>'
        "</section>"
        if cards
        else ""
    )
    tags_html = "".join(
        f'<span class="tag">{_html_escape(tag)}</span>'
        for tag in dict.fromkeys(parsed["tags"])
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html_escape(title)}</title>
<style>
:root{{--bg:#f4f3ee;--ink:#191817;--muted:#5a554e;--line:#d8d3c8;--accent:#c96442}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);
font-family:system-ui,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;line-height:1.8}}
main{{max-width:680px;margin:0 auto;padding:22px 22px 80px}}
.cards{{margin:0 0 30px}}
.cards-head{{font-size:13px;color:var(--muted);margin:0 0 12px}}
.reader-actions{{display:flex;justify-content:flex-end;gap:8px;margin:0 0 12px}}
.reader-actions button,.reader-actions .trace-link,.card-actions button,.card-actions a{{font:inherit;font-size:12px;color:var(--muted);
background:#eeede6;border:1px solid var(--line);border-radius:999px;padding:4px 10px;cursor:pointer;
text-decoration:none}}
.card-list{{display:flex;flex-direction:column;gap:16px;align-items:center}}
.card{{margin:0;width:min(100%,420px)}}
.card-actions{{display:flex;justify-content:flex-end;gap:8px;margin-top:8px}}
.card img{{width:100%;height:auto;display:block;border-radius:18px;border:1px solid var(--line);background:#fff}}
.card.fallback .card-box{{width:100%;aspect-ratio:3/4;background:#fff;border:1px solid var(--line);
border-radius:18px;display:flex;align-items:center;justify-content:center;overflow:hidden}}
.card.fallback .card-box img{{width:auto;height:auto;max-width:100%;max-height:100%;
object-fit:contain;border:0;border-radius:0}}
.card.fallback figcaption{{font-size:12px;color:var(--muted);margin-top:6px;line-height:1.45}}
.card.fallback.text-only .card-box{{background:linear-gradient(155deg,#221e1a 0%,#3b332a 55%,#2a241f 100%);
color:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:34px 28px}}
.cover-kicker{{font-size:10px;letter-spacing:.2em;color:#d8b9a8;margin:0 0 18px}}
.cover-text{{font-family:"Noto Serif SC","Source Han Serif SC","Songti SC",SimSun,Georgia,serif;
font-size:25px;line-height:1.4;font-weight:600;text-wrap:balance}}
.cover-rule{{width:44px;height:3px;background:#c96442;border-radius:2px;margin:22px auto 0}}
h1{{font-family:"Noto Serif SC","Source Han Serif SC","Songti SC",SimSun,Georgia,serif;
font-size:30px;line-height:1.25;letter-spacing:-.01em;margin:0 0 18px;text-wrap:balance}}
p{{font-size:17px;margin:0 0 14px}}strong{{font-weight:700}}
.tags{{margin-top:18px;display:flex;gap:8px;flex-wrap:wrap}}
.tag{{background:#eeede6;color:var(--muted);border-radius:999px;padding:4px 10px;font-size:12px}}
hr{{border:0;border-top:1px solid var(--line);margin:28px 0}}
a{{color:var(--accent)}}
</style>
</head>
<body>
<main class="content">
<div class="reader-actions">{f'<a class="trace-link" href="{_html_escape(trace_url)}">运行数据</a>' if trace_url else ''}<button id="copy-note-btn" type="button">复制标题+正文+标签</button></div>
{cards_html}
<div id="note-text">
<h1>{_html_escape(title)}</h1>
{body}
{f'<div class="tags">{tags_html}</div>' if tags_html else ''}
</div>
</main>
{COPY_IMAGE_SCRIPT}
{COPY_NOTE_SCRIPT}
</body></html>"""


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


@mcp.tool()
def ingest_source(
    target: str,
    profile: str = "quality",
    force: bool = False,
    include_evidence: bool = False,
) -> dict[str, Any]:
    """接入新视频：B 站 URL 或本地路径 → 证据层 → content.md + figures。

    默认只做写作需要的 content 路径（抽帧/ASR/VLM），不跑 contract/L1 知识底稿；
    ``include_evidence=True`` 时才生成完整证据层。
    """
    from .ingest import ingest_source as _ingest_source

    return _ingest_source(
        target,
        profile=profile,
        force=force,
        include_evidence=include_evidence,
    )


@mcp.tool()
def list_sources() -> dict[str, Any]:
    """列出可用的缓存视频内容稿（P1 不重跑视频）。"""
    items = _list_cached_sources()
    return {"count": len(items), "sources": items}


@mcp.tool()
def resolve_source(video_id: str = "", path: str = "") -> dict[str, Any]:
    """解析一条视频的缓存内容稿。video_id 如 BV1xxxxxxxxx；path 可直接给 content.md。"""
    if path:
        content = Path(path).expanduser().resolve()
        if not content.is_file():
            raise FileNotFoundError(f"内容稿不存在：{content}")
        video_id = video_id or content.parent.parent.name
        return _source_meta(video_id, content)
    if not video_id:
        raise ValueError("需要 video_id 或 path")
    return _source_meta(video_id, _content_path(video_id))


@mcp.tool()
def compile_content(video_id: str, run_id: str = "") -> dict[str, Any]:
    """把缓存内容稿和 figures 复制到 run 目录，返回 hash/字数/图数。"""
    content = _content_path(video_id)
    run_id = run_id or _new_run_id(video_id, "compile")
    run_dir = _run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    info = _ensure_compiled(video_id=video_id, content=content, run_dir=run_dir)
    meta_path = run_dir / "run_meta.json"
    if not meta_path.is_file():
        _save_run(
            run_dir,
            {
                "schema_version": "product-v1-run",
                "run_id": run_id,
                "video_id": video_id,
                "status": "compiled",
                "source": info,
                "created_at": _now(),
            },
        )
    return {"run_id": run_id, "status": "compiled", **info}


@mcp.tool()
def plan_article(
    video_id: str,
    form: str,
    request: str = "",
    run_id: str = "",
    visual_audit: bool = True,
) -> dict[str, Any]:
    """读内容稿，视觉审计候选关键帧，再用 Lead Planner 生成一个 form 的 brief；不写正文。

    ``visual_audit=True`` 时先用 deepseek-flash 的视觉能力审计候选关键帧；
    只有通过的帧会留在运行用的内容稿副本里，planner/writer 不会误用未审计帧。
    """
    form = _normalize_form(form)
    if form not in FORM_SKILLS:
        raise ValueError(f"未知 form：{form}；可用：{', '.join(FORM_SKILLS)}")
    content = _content_path(video_id)
    run_id = run_id or _new_run_id(video_id, form)
    run_dir = _run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    source = _ensure_compiled(video_id=video_id, content=content, run_dir=run_dir)
    settings = _settings()
    content_copy = run_dir / "content" / "content.md"
    approved_figures: list[str] = []
    visual_audit_summary: dict[str, Any] = {}
    visual_audit_usage: dict[str, int] = {}
    visual_audit_calls = 0
    if visual_audit and settings.provider_configured:
        from .writing_v4.visual_audit import audit_content, filter_content_for_approved

        audit_records: list[dict[str, Any]] = []
        try:
            audit = audit_content(
                content,
                client=_client(audit_records.append),
                max_frames=6,
                out_path=run_dir / "visual_audit.json",
            )
            _append_jsonl(run_dir / "llm_calls.jsonl", audit_records)
            approved_figures = [
                Path(item["file"]).name for item in audit.get("approved") or []
            ]
            filtered = filter_content_for_approved(
                content_copy.read_text(encoding="utf-8"),
                audit.get("approved") or [],
            )
            content_copy.write_text(filtered, encoding="utf-8")
            visual_audit_calls = len(audit_records)
            visual_audit_usage = {
                key: sum(
                    int((record.get("usage") or {}).get(key) or 0)
                    for record in audit_records
                )
                for key in (
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "reasoning_tokens",
                    "cached_tokens",
                )
            }
            visual_audit_summary = {
                "candidate_count": audit.get("candidate_count"),
                "approved_count": audit.get("approved_count"),
                "approved": approved_figures,
                "errors": audit.get("errors") or [],
            }
        except Exception as exc:  # noqa: BLE001 - audit failure means 0 keyframes
            # Enforce the safe default: no audited keyframes in the run copy.
            filtered = filter_content_for_approved(
                content_copy.read_text(encoding="utf-8"), []
            )
            content_copy.write_text(filtered, encoding="utf-8")
            visual_audit_summary = {
                "error": f"{type(exc).__name__}: {exc}"[:300],
                "approved": [],
            }
    catalog = form_catalog(settings.skills_root / "writing")
    planner_skill = load_skill(settings.skills_root / "writing" / "bundle-planner")
    planner_records: list[dict[str, Any]] = []
    client = _client(planner_records.append)
    plan, raw = plan_bundle(
        client=client,
        skill=planner_skill,
        content=content_copy.read_text(encoding="utf-8"),
        catalog=catalog,
        request=request,
        required_forms=[form],
        available_figures=approved_figures,
        video_id=video_id,
    )
    _write_json(run_dir / "lead_plan.json", plan.as_dict())
    if raw:
        (run_dir / "lead_plan_raw.txt").write_text(raw, encoding="utf-8")
    _append_jsonl(run_dir / "llm_calls.jsonl", planner_records)
    item = next((entry for entry in plan.forms if entry.form == form), None)
    if item is None:
        raise ValueError("planner 没有返回请求的 form")
    meta = {
        "schema_version": "product-v1-run",
        "run_id": run_id,
        "video_id": video_id,
        "form": form,
        "form_label": FORM_LABELS.get(form, form),
        "request": request,
        "status": "planned",
        "source": source,
        "plan": plan.as_dict(),
        "visual_audit": visual_audit_summary,
        "visual_audit_usage": visual_audit_usage,
        "visual_audit_calls": visual_audit_calls,
        "planner_calls": len(planner_records),
        "planner_usage": planner_records[-1].get("usage") if planner_records else {},
        "planner_latency_ms": planner_records[-1].get("latency_ms") if planner_records else 0,
        "created_at": _now(),
    }
    _save_run(run_dir, meta)
    return {
        "run_id": run_id,
        "status": "planned",
        "video_id": video_id,
        "form": form,
        "form_label": FORM_LABELS.get(form, form),
        "central_idea": plan.central_idea,
        "reader_goal": plan.reader_goal,
        "angle": item.angle,
        "brief": item.brief,
        "must_use_figures": item.must_use_figures,
        "shared_constraints": plan.shared_constraints,
        "plan_source": plan.source,
        "content_chars": source["content_chars"],
        "figure_count": source["figure_count"],
        "visual_audit": visual_audit_summary,
        "planner_usage": meta["planner_usage"],
        "planner_latency_ms": meta["planner_latency_ms"],
    }


@mcp.tool()
def write_form(run_id: str, form: str = "") -> dict[str, Any]:
    """按计划写一个 form；一次 writer，写完即停。"""
    run_dir, meta = _load_run(run_id)
    form = _normalize_form(form or str(meta.get("form") or ""))
    if form not in FORM_SKILLS:
        raise ValueError(f"未知 form：{form}")
    plan = LeadPlan(
        central_idea=str(meta["plan"].get("central_idea") or ""),
        reader_goal=str(meta["plan"].get("reader_goal") or ""),
        forms=[
            PlannedForm(
                form=item["form"],
                reason=item.get("reason", ""),
                angle=item.get("angle", ""),
                brief=item.get("brief", ""),
                must_use_figures=item.get("must_use_figures", []),
            )
            for item in meta["plan"].get("forms", [])
        ],
        shared_constraints=list(meta["plan"].get("shared_constraints") or []),
        notes=str(meta["plan"].get("notes") or ""),
        source=str(meta["plan"].get("source") or "planner"),
        error=meta["plan"].get("error"),
    )
    request = _form_request(plan, form)
    skill_dir = _settings().skills_root / "writing" / FORM_SKILLS[form]
    out_dir = run_dir / form
    write_records: list[dict[str, Any]] = []
    result = _write_form(
        video_id=meta["video_id"],
        content_path=run_dir / "content" / "content.md",
        out_dir=out_dir,
        skill_dir=skill_dir,
        request=request,
        source_json=_source_dir(meta["video_id"]) / "source.json",
        client=_client(write_records.append),
        settings=_settings(),
        store=None,
    )
    _append_jsonl(run_dir / "llm_calls.jsonl", write_records)
    markdown = (out_dir / result.output).read_text(encoding="utf-8")
    meta["status"] = "written" if result.status == "complete" else result.status
    meta["write"] = result.as_dict()
    meta["write_calls"] = len(write_records)
    meta["form_dir"] = str(out_dir)
    meta["output"] = result.output
    meta["markdown_path"] = str(out_dir / result.output)
    _save_run(run_dir, meta)
    return {
        "run_id": run_id,
        "status": meta["status"],
        "form": form,
        "form_label": FORM_LABELS.get(form, form),
        "output": result.output,
        "output_chars": result.output_chars,
        "figures_referenced": result.figures_referenced,
        "missing_figures": result.missing_figures,
        "latency_ms": result.latency_ms,
        "usage": result.usage,
        "reader_contract": result.reader_contract,
        "title_candidates": result.title_candidates,
        "markdown": markdown,
    }


@mcp.tool()
def typeset_article(run_id: str) -> dict[str, Any]:
    """把 run 的 Markdown 渲染成读者 HTML（相对图片路径），返回本地预览 URL。"""
    run_dir, meta = _load_run(run_id)
    form = str(meta.get("form") or "")
    form_dir = Path(str(meta.get("form_dir") or run_dir / form))
    output = str(meta.get("output") or ("note.md" if form == "xiaohongshu_note" else "article.md"))
    path = form_dir / output
    if not path.is_file():
        raise FileNotFoundError(f"产物不存在，请先 write_form：{path}")
    markdown = path.read_text(encoding="utf-8")
    title = _first_heading(markdown) or f"{meta.get('video_id', '')} · {FORM_LABELS.get(form, form)}"
    errors: list[str] = []
    xhs: dict[str, Any] | None = None
    # The run-detail page is served at /runs/<run_id>; from the form page
    # (/runs/<run_id>/<form>/reader.html) it is ../../<run_id>.
    trace_href = f"../../{run_id}"
    if form == "xiaohongshu_note":
        # Render the 3:4 cards first, then reuse those exact files in the
        # reader page so the preview and the export cannot diverge.
        xhs = _xhs_export(
            form_dir=form_dir,
            markdown=markdown,
            request=str(meta.get("request") or ""),
        )
        card_images = [f"xhs_export/{Path(item).name}" for item in xhs["images"]]
        html = _render_xhs(
            markdown,
            form_dir,
            title,
            card_images=card_images,
            trace_url=trace_href,
        )
    else:
        html = _render_reader(
            markdown,
            form_dir,
            title,
            trace_url=trace_href,
            form_label=FORM_LABELS.get(form, form),
        )
    html_path = form_dir / "reader.html"
    html_path.write_text(html, encoding="utf-8")
    base = str(
        os.environ.get("FACET_STUDIO_PREVIEW_BASE", "http://127.0.0.1:8765/runs")
    ).rstrip("/")
    preview_url = f"{base}/{run_id}/{form}/reader.html"
    trace_url = f"{base}/{run_id}"
    artifacts = meta.setdefault("artifacts", {})
    artifacts["reader_html"] = str(html_path)
    artifacts["preview_url"] = preview_url
    result: dict[str, Any] = {
        "run_id": run_id,
        "form": form,
        "html_path": str(html_path),
        "preview_url": preview_url,
        "html_chars": len(html),
        "hint": (
            "把 preview_url 给用户打开（需要 preview server 在跑）；"
            "同时可以展示 Markdown 正文。"
        ),
    }
    if form == "wechat_article":
        wechat_html = _render_wechat(markdown, form_dir, title, trace_url=trace_href)
        wechat_path = form_dir / "wechat.html"
        wechat_path.write_text(wechat_html, encoding="utf-8")
        wechat_url = f"{base}/{run_id}/{form}/wechat.html"
        artifacts["wechat_html"] = str(wechat_path)
        artifacts["wechat_url"] = wechat_url
        result["wechat_html_path"] = str(wechat_path)
        result["wechat_url"] = wechat_url
    if form == "xiaohongshu_note":
        assert xhs is not None
        card_urls = [f"{base}/{run_id}/{form}/{item}" for item in xhs["images"]]
        artifacts["xhs_export_dir"] = xhs["export_dir"]
        artifacts["xhs_manifest"] = xhs["manifest"]
        artifacts["xhs_cards"] = card_urls
        result["xhs_export"] = {**xhs, "card_urls": card_urls}
        if xhs.get("error"):
            errors.append(f"小红书卡片渲染失败：{xhs['error']}")
    if form == "long_article":
        source_meta = meta.get("source") or {}
        source_line = f"B 站视频《{source_meta.get('title') or meta.get('video_id', '')}》"
        if source_meta.get("uploader"):
            source_line += f"（UP 主：{source_meta['uploader']}）"
        video_cover = str(source_meta.get("cover") or "")
        if not video_cover:
            candidate = _source_dir(str(meta.get("video_id") or "")) / "cover.jpg"
            if candidate.is_file():
                video_cover = str(candidate)
        pdf = _export_pdf(
            form_dir=form_dir,
            markdown=markdown,
            title=title,
            source=source_line,
            video_cover=video_cover,
        )
        if pdf.get("pdf_path"):
            pdf_url = f"{base}/{run_id}/{form}/article.pdf"
            artifacts["pdf"] = pdf["pdf_path"]
            artifacts["pdf_url"] = pdf_url
            artifacts["tex"] = pdf["tex_path"]
            result["pdf"] = {**pdf, "pdf_url": pdf_url}
        else:
            result["pdf"] = pdf
            errors.append(f"PDF 导出失败：{pdf.get('error') or '未知错误'}")
    meta["typeset"] = result
    meta["typeset_errors"] = errors
    meta["status"] = "partial" if errors else "typeset"
    # A new render is a new artifact version.  Do not let an older approval
    # silently cover it; keep the review record and mark it stale.
    meta["review_stale"] = (run_dir / "publish_review.json").is_file()
    _save_run(run_dir, meta)
    result["status"] = meta["status"]
    result["typeset_errors"] = errors

    # A standalone re-typeset must also update the workflow trace.  Otherwise
    # a fixed PDF still leaves the old "partial" stage and error in
    # workflow.json, and get_workflow/eval keep reporting a failure that no
    # longer exists.
    workflow_path = run_dir / "workflow.json"
    if workflow_path.is_file():
        workflow = _read_json(workflow_path)
        changed = False
        for stage in workflow.get("stages") or []:
            if str(stage.get("name") or "") == "typeset":
                stage["status"] = meta["status"]
                stage["error"] = "; ".join(errors) or None
                stage["at"] = _now()
                changed = True
        stale_prefixes = ("PDF 导出失败", "排版失败", "小红书卡片渲染失败")
        other_errors = [
            item
            for item in (workflow.get("errors") or [])
            if not str(item).startswith(stale_prefixes)
        ]
        current_errors = other_errors + list(errors)
        if current_errors != (workflow.get("errors") or []):
            workflow["errors"] = current_errors
            changed = True
        if meta["status"] == "partial":
            if workflow.get("status") != "partial":
                workflow["status"] = "partial"
                changed = True
        elif workflow.get("status") == "partial" and meta["status"] == "typeset":
            workflow["status"] = "typeset"
            changed = True
        if changed:
            workflow["updated_at"] = _now()
            _write_json(workflow_path, workflow)

    # Trace/observability page: stages, calls, checks and grounding candidates
    # in one read-only artifact.  It is a dev/interview surface, not a score.
    trace_path = write_trace(run_id, run_dir, meta)
    artifacts["trace_html"] = str(trace_path)
    artifacts["trace_url"] = trace_url
    result["trace_url"] = trace_url
    _save_run(run_dir, meta)
    return result


@mcp.tool()
def get_run(run_id: str) -> dict[str, Any]:
    """查看 run 状态、计划、usage、产物和验收状态。"""
    run_dir, meta = _load_run(run_id)
    review = None
    review_path = run_dir / "publish_review.json"
    if review_path.is_file():
        review = _read_json(review_path)
    workflow = None
    workflow_path = run_dir / "workflow.json"
    if workflow_path.is_file():
        workflow = _read_json(workflow_path)
    cost_estimate = (workflow or {}).get("cost_estimate")
    write = meta.get("write") or {}
    planner_usage = meta.get("planner_usage") or {}
    write_usage = write.get("usage") or {}
    audit_usage = meta.get("visual_audit_usage") or {}
    usage_total = {
        key: int(planner_usage.get(key, 0) or 0)
        + int(write_usage.get(key, 0) or 0)
        + int(audit_usage.get(key, 0) or 0)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens", "cached_tokens")
    }
    calls_total = (
        (1 if planner_usage else 0)
        + (1 if write_usage else 0)
        + int(meta.get("visual_audit_calls") or 0)
    )
    # The per-call JSONL is the source of truth when present: it includes
    # SVG-spec calls and any other calls not folded into the summary fields.
    calls_path = run_dir / "llm_calls.jsonl"
    if calls_path.is_file():
        records: list[dict[str, Any]] = []
        for line in calls_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if records:
            calls_total = len(records)
            usage_total = {
                key: sum(
                    int((record.get("usage") or {}).get(key) or 0)
                    for record in records
                )
                for key in (
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "reasoning_tokens",
                    "cached_tokens",
                )
            }
    latency_total = int(meta.get("planner_latency_ms") or 0) + int(write.get("latency_ms") or 0)
    status = str(meta.get("status") or "")
    review_status = str((review or meta.get("review") or {}).get("decision") or "draft")
    if review and meta.get("review_stale"):
        review_status = "stale"
    status_label = STATUS_LABELS.get(status, status)
    if review_status == "stale":
        status_label = f"待重新验收 · {status_label}"
    elif review_status == "draft" and status in {"typeset", "partial"}:
        status_label = f"草稿 · {status_label}"
    cost_note = (
        f" · ${cost_estimate:.4f}"
        if isinstance(cost_estimate, (int, float))
        else ""
    )
    artifacts = meta.get("artifacts") or {}
    base = str(
        os.environ.get("FACET_STUDIO_PREVIEW_BASE", "http://127.0.0.1:8765/runs")
    ).rstrip("/")
    trace_url = str(artifacts.get("trace_url") or "")
    if not trace_url and (run_dir / "trace.html").is_file():
        trace_url = f"{base}/{run_id}"
    trace = trace_summary(run_id, run_dir, meta)
    trace["trace_url"] = trace_url
    return {
        "run_id": run_id,
        "status": meta.get("status"),
        "review_status": review_status,
        "video_id": meta.get("video_id"),
        "form": meta.get("form"),
        "form_label": meta.get("form_label"),
        "source": meta.get("source"),
        "plan": {
            "central_idea": (meta.get("plan") or {}).get("central_idea"),
            "reader_goal": (meta.get("plan") or {}).get("reader_goal"),
            "forms": (meta.get("plan") or {}).get("forms"),
            "shared_constraints": (meta.get("plan") or {}).get("shared_constraints"),
            "source": (meta.get("plan") or {}).get("source"),
        },
        "planner_usage": planner_usage,
        "planner_latency_ms": meta.get("planner_latency_ms"),
        "write": write,
        "usage_total": usage_total,
        "calls_total": calls_total,
        "latency_total_ms": latency_total,
        "summary": (
            f"调用 {calls_total} 次 · {usage_total['total_tokens']} tokens · "
            f"{latency_total}ms{cost_note} · {status_label}"
        ),
        "artifacts": artifacts,
        "trace": trace,
        "trace_url": trace_url,
        "typeset_errors": list(meta.get("typeset_errors") or []),
        "cost_estimate": cost_estimate,
        "markdown_path": meta.get("markdown_path"),
        "review": review,
        "workflow": workflow,
    }


@mcp.tool()
def review_artifact(run_id: str, decision: str, notes: str = "") -> dict[str, Any]:
    """人工验收门：approved / changes_requested / rejected。不自动发布。"""
    allowed = {"approved", "changes_requested", "rejected"}
    if decision not in allowed:
        raise ValueError(f"decision 必须是 {sorted(allowed)}")
    run_dir, meta = _load_run(run_id)
    if decision == "approved":
        status = str(meta.get("status") or "")
        if status not in {"typeset", "partial"} or not meta.get("artifacts"):
            raise ValueError(
                f"run 还没有可验收的产物（status={status}）；先调用 typeset_article"
            )
    review = {
        "run_id": run_id,
        "decision": decision,
        "notes": notes,
        "reviewed_at": _now(),
        "reviewer": "user",
    }
    _write_json(run_dir / "publish_review.json", review)
    meta["status"] = (
        "approved"
        if decision == "approved"
        else "rejected" if decision == "rejected" else "changes_requested"
    )
    meta["review"] = review
    meta["review_stale"] = False
    _save_run(run_dir, meta)
    return {
        "run_id": run_id,
        "status": meta["status"],
        "review_status": decision,
        "review": review,
    }


@mcp.tool()
def start_workflow(
    video_id: str,
    form: str,
    request: str = "",
    auto_approve: bool = False,
    ctx: Context | None = None,
) -> dict[str, Any]:
    """启动 LangGraph 工作流；默认停在计划卡，等 resume_workflow 确认。"""
    from .workflow import start_workflow as _start_workflow

    return _start_workflow(
        video_id=video_id,
        form=form,
        request=request,
        auto_approve=auto_approve,
        on_event=_progress_callback(ctx),
    )


@mcp.tool()
def resume_workflow(
    run_id: str,
    decision: str,
    notes: str = "",
    ctx: Context | None = None,
) -> dict[str, Any]:
    """恢复暂停的工作流：计划卡或最终验收。decision=approved/changes_requested/rejected。"""
    from .workflow import resume_workflow as _resume_workflow

    return _resume_workflow(
        run_id=run_id,
        decision=decision,
        notes=notes,
        on_event=_progress_callback(ctx),
    )


@mcp.tool()
def get_workflow(run_id: str) -> dict[str, Any]:
    """查看工作流阶段、暂停点、usage、trace 事件。"""
    from .workflow import get_workflow as _get_workflow

    return _get_workflow(run_id=run_id)


def _first_heading(markdown: str) -> str:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


if __name__ == "__main__":
    mcp.run()
