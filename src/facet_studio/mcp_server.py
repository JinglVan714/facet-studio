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

from mcp.server.fastmcp import FastMCP
from markdown_it import MarkdownIt

from .core.config import get_settings
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


def _clip_error(value: object, limit: int = 1200) -> str:
    """Keep tool stderr useful without dumping pages of TeX logs into run data."""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n…（已截断）"


def _source_dir(video_id: str) -> Path:
    return _settings().data_root / video_id


def _content_path(video_id: str) -> Path:
    """Cached content manuscript for a BV id."""
    root = _project() / "runs" / "writing_rebuild_2026-11-04"
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
    return {
        "video_id": video_id,
        "title": str(meta.get("title") or video_id),
        "uploader": str(meta.get("uploader") or ""),
        "content_path": str(content),
        "content_chars": len(content.read_text(encoding="utf-8")),
        "figures": figures,
        "figure_count": len(figures),
    }


def _list_cached_sources() -> list[dict[str, Any]]:
    root = _project() / "runs" / "writing_rebuild_2026-11-04"
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
        parts.append("优先使用图示：" + "、".join(item.must_use_figures))
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


def _render_reader(
    markdown: str, form_dir: Path, title: str, *, inline_images: bool = False
) -> str:
    md = MarkdownIt("commonmark", {"html": False})
    md.enable("table")
    body = md.render(_inline_images(markdown, form_dir) if inline_images else markdown)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html_escape(title)}</title>
<style>
:root{{--bg:#f4f3ee;--ink:#191817;--muted:#5a554e;--line:#d8d3c8;--accent:#c96442}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);
font-family:system-ui,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;line-height:1.75}}
main{{max-width:760px;margin:0 auto;padding:56px 24px 96px}}
h1{{font-family:"Noto Serif SC","Source Han Serif SC","Songti SC",SimSun,Georgia,serif;
font-size:clamp(32px,5vw,48px);line-height:1.2;letter-spacing:-.01em;margin:0 0 28px;text-wrap:balance}}
h2{{font-family:inherit;font-size:24px;line-height:1.35;margin:44px 0 14px;
padding-top:18px;border-top:1px solid var(--line)}}
p{{font-size:18px;margin:0 0 18px}}figure{{margin:28px 0}}img{{max-width:100%;height:auto;
border-radius:8px;display:block}}figcaption{{font-size:13px;color:var(--muted);margin-top:8px}}
table{{width:100%;border-collapse:collapse;margin:24px 0;font-size:14px;background:#fff}}
th,td{{border:1px solid var(--line);padding:10px 12px;text-align:left;vertical-align:top}}
th{{background:#eeede6}}blockquote{{margin:24px 0;padding:12px 18px;border-left:3px solid var(--accent);
color:var(--muted)}}hr{{border:0;border-top:1px solid var(--line);margin:40px 0}}
a{{color:var(--accent)}}code{{background:#eeede6;padding:2px 5px;border-radius:4px}}
@media(max-width:640px){{main{{padding:32px 18px 72px}}p{{font-size:17px}}}}
</style>
</head>
<body><main>{body}</main></body></html>"""


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
            "index": f"01 / {total_cards:02d}",
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
    env = dict(os.environ)
    env.setdefault(
        "FACET_STUDIO_PLAYWRIGHT",
        "D:/luno_external/librechat/node_modules/playwright",
    )
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


def _render_wechat(markdown: str, form_dir: Path, title: str) -> str:
    """Render a WeChat-friendly HTML page with inline styles for copy/paste."""
    md = MarkdownIt("commonmark", {"html": False})
    md.enable("table")
    body = md.render(_strip_first_heading(markdown))
    styles = {
        "h1": "font-family:Georgia,'Songti SC',SimSun,serif;font-size:26px;line-height:1.4;margin:0 0 22px;color:#191817;text-wrap:balance;",
        "h2": "font-size:21px;line-height:1.5;margin:34px 0 14px;padding-top:16px;border-top:1px solid #e5ded3;color:#191817;",
        "h3": "font-size:18px;line-height:1.5;margin:26px 0 10px;color:#191817;",
        "p": "font-size:16px;line-height:1.9;margin:0 0 18px;color:#2f2a25;",
        "img": "max-width:100%;max-height:520px;width:auto;height:auto;display:block;margin:18px auto;border-radius:6px;",
        "figure": "margin:24px 0;",
        "figcaption": "font-size:13px;color:#8a847a;text-align:center;margin-top:6px;",
        "table": "width:100%;border-collapse:collapse;margin:20px 0;font-size:14px;",
        "th": "border:1px solid #d8d3c8;background:#eeede6;padding:8px 10px;text-align:left;",
        "td": "border:1px solid #d8d3c8;padding:8px 10px;text-align:left;",
        "blockquote": "margin:20px 0;padding:10px 16px;border-left:3px solid #c96442;color:#5a554e;",
        "li": "font-size:16px;line-height:1.9;color:#2f2a25;",
    }
    for tag, style in styles.items():
        body = re.sub(
            rf"<{tag}(\s[^>]*)?>",
            lambda m, t=tag, s=style: f"<{t}{m.group(1) or ''} style=\"{s}\">",
            body,
        )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_html_escape(title)}</title></head>
<body style="margin:0;background:#f4f3ee;">
<div style="max-width:680px;margin:0 auto;background:#fff;">
<header style="padding:32px 22px 0;"><h1 style="{styles['h1']}">{_html_escape(title)}</h1></header>
<main id="wechat-article" style="padding:0 22px 64px;">
{body}
</main>
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


def _export_pdf(
    *, form_dir: Path, markdown: str, title: str, source: str
) -> dict[str, Any]:
    """Markdown → Pandoc LaTeX body → Tectonic PDF (long_article)."""
    pandoc = (
        os.environ.get("FACET_STUDIO_PANDOC")
        or shutil.which("pandoc")
        or "C:/Users/30279/AppData/Local/Pandoc/pandoc.exe"
    )
    tectonic = (
        os.environ.get("FACET_STUDIO_TECTONIC")
        or shutil.which("tectonic")
        or "D:/luno_external/tectonic/tectonic.exe"
    )
    template_path = _project() / "integrations" / "pdf" / "facet-template.tex"
    if not Path(pandoc).is_file():
        return {"error": f"pandoc not found: {pandoc}"}
    if not Path(tectonic).is_file():
        return {"error": f"tectonic not found: {tectonic}"}
    if not template_path.is_file():
        return {"error": f"template not found: {template_path}"}

    body_md = re.sub(r"^# .*\n", "", markdown, count=1, flags=re.MULTILINE)
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
    images = re.findall(r"!\[[^\]]*\]\((figures/[^)\s]+)\)", markdown)
    cover = images[0] if images else ""
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
    if not cards and parsed["cover_text"]:
        cards.append(
            '<figure class="card fallback text-only">'
            f'<div class="card-box"><div class="cover-text">'
            f'{_html_escape(parsed["cover_text"])}</div></div></figure>'
        )
    cards_html = (
        '<section class="cards">'
        f'<div class="cards-head">配图 · {len(cards)} 张（按顺序保存或上传）</div>'
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
.reader-actions{{display:flex;justify-content:flex-end;margin:0 0 12px}}
.reader-actions button,.card-actions button,.card-actions a{{font:inherit;font-size:12px;color:var(--muted);
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
.card.fallback.text-only .card-box{{background:linear-gradient(160deg,#211d19,#3a332b);
color:#fff;align-items:flex-end;padding:26px 22px}}
.cover-text{{font-family:"Noto Serif SC","Source Han Serif SC","Songti SC",SimSun,Georgia,serif;
font-size:22px;line-height:1.35;font-weight:600}}
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
<div class="reader-actions"><button id="copy-note-btn" type="button">复制标题+正文+标签</button></div>
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
) -> dict[str, Any]:
    """读内容稿，用 Lead Planner 生成一个 form 的 brief；不写正文。"""
    form = _normalize_form(form)
    if form not in FORM_SKILLS:
        raise ValueError(f"未知 form：{form}；可用：{', '.join(FORM_SKILLS)}")
    content = _content_path(video_id)
    run_id = run_id or _new_run_id(video_id, form)
    run_dir = _run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    source = _ensure_compiled(video_id=video_id, content=content, run_dir=run_dir)
    settings = _settings()
    catalog = form_catalog(settings.skills_root / "writing")
    planner_skill = load_skill(settings.skills_root / "writing" / "bundle-planner")
    planner_records: list[dict[str, Any]] = []
    client = _client(planner_records.append)
    plan, raw = plan_bundle(
        client=client,
        skill=planner_skill,
        content=(run_dir / "content" / "content.md").read_text(encoding="utf-8"),
        catalog=catalog,
        request=request,
        required_forms=[form],
        available_figures=[Path(item).name for item in source["figures"]],
        video_id=video_id,
    )
    _write_json(run_dir / "lead_plan.json", plan.as_dict())
    if raw:
        (run_dir / "lead_plan_raw.txt").write_text(raw, encoding="utf-8")
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
    result = _write_form(
        video_id=meta["video_id"],
        content_path=run_dir / "content" / "content.md",
        out_dir=out_dir,
        skill_dir=skill_dir,
        request=request,
        source_json=_source_dir(meta["video_id"]) / "source.json",
        client=_client(),
        settings=_settings(),
        store=None,
    )
    markdown = (out_dir / result.output).read_text(encoding="utf-8")
    meta["status"] = "written" if result.status == "complete" else result.status
    meta["write"] = result.as_dict()
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
    if form == "xiaohongshu_note":
        # Render the 3:4 cards first, then reuse those exact files in the
        # reader page so the preview and the export cannot diverge.
        xhs = _xhs_export(
            form_dir=form_dir,
            markdown=markdown,
            request=str(meta.get("request") or ""),
        )
        card_images = [f"xhs_export/{Path(item).name}" for item in xhs["images"]]
        html = _render_xhs(markdown, form_dir, title, card_images=card_images)
    else:
        html = _render_reader(markdown, form_dir, title)
    html_path = form_dir / "reader.html"
    html_path.write_text(html, encoding="utf-8")
    base = str(
        os.environ.get("FACET_STUDIO_PREVIEW_BASE", "http://127.0.0.1:8765/runs")
    ).rstrip("/")
    preview_url = f"{base}/{run_id}/{form}/reader.html"
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
        wechat_html = _render_wechat(markdown, form_dir, title)
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
        pdf = _export_pdf(
            form_dir=form_dir,
            markdown=markdown,
            title=title,
            source=source_line,
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
    usage_total = {
        key: int(planner_usage.get(key, 0) or 0) + int(write_usage.get(key, 0) or 0)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens", "cached_tokens")
    }
    calls_total = (1 if planner_usage else 0) + (1 if write_usage else 0)
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
        "artifacts": meta.get("artifacts", {}),
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
) -> dict[str, Any]:
    """启动 LangGraph 工作流；默认停在计划卡，等 resume_workflow 确认。"""
    from .workflow import start_workflow as _start_workflow

    return _start_workflow(
        video_id=video_id,
        form=form,
        request=request,
        auto_approve=auto_approve,
    )


@mcp.tool()
def resume_workflow(run_id: str, decision: str, notes: str = "") -> dict[str, Any]:
    """恢复暂停的工作流：计划卡或最终验收。decision=approved/changes_requested/rejected。"""
    from .workflow import resume_workflow as _resume_workflow

    return _resume_workflow(run_id=run_id, decision=decision, notes=notes)


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
