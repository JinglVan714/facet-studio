import json
from pathlib import Path

import pytest

import facet_studio.mcp_server as mcp_server
from facet_studio.mcp_server import (
    _export_pdf,
    _normalize_form,
    _parse_xhs_note,
    _pdf_title,
    _render_wechat,
    _render_xhs,
    get_run,
    list_sources,
    review_artifact,
    typeset_article,
)


def _write_run(
    tmp_path: Path,
    monkeypatch,
    run_id: str,
    *,
    status: str = "written",
) -> tuple[Path, Path]:
    monkeypatch.setenv("FACET_STUDIO_RUNS_ROOT", str(tmp_path))
    run_dir = tmp_path / "product_v1" / run_id
    form_dir = run_dir / "long_article"
    form_dir.mkdir(parents=True)
    (form_dir / "article.md").write_text("# 标题\n\n正文。\n", encoding="utf-8")
    meta = {
        "schema_version": "product-v1-run",
        "run_id": run_id,
        "video_id": "BVtest",
        "form": "long_article",
        "form_label": "深度总结",
        "status": status,
        "source": {"title": "示例视频"},
        "form_dir": str(form_dir),
        "output": "article.md",
        "artifacts": {},
    }
    (run_dir / "run_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8"
    )
    return run_dir, form_dir


def test_normalize_form_aliases() -> None:
    assert _normalize_form("公众号") == "wechat_article"
    assert _normalize_form("deep_summary") == "long_article"
    assert _normalize_form("xiaohongshu") == "xiaohongshu_note"
    assert _normalize_form("wechat_article") == "wechat_article"


def test_list_sources_contains_cached_bv17() -> None:
    payload = list_sources()
    assert payload["count"] >= 1
    ids = {item["video_id"] for item in payload["sources"]}
    assert "BV17DHC6CELr" in ids


def test_render_xhs_uses_gallery_not_sidecar_paths(tmp_path: Path) -> None:
    markdown = """# 标题

> 封面：一句话

正文第一段。

## 配图
- figures/fig-01.jpg：看封面
- figures/fig-02.jpg：看动作

## 标签
#测试 #示例
"""
    html = _render_xhs(markdown, tmp_path, "标题")
    assert "figures/fig-01.jpg" in html
    assert "<img" in html
    assert 'class="card-list"' in html
    assert "card fallback" in html
    assert "card-box" in html
    assert "看动作" in html
    assert "## 配图" not in html
    assert "#测试" in html


def test_render_xhs_text_only_cover_when_no_figures(tmp_path: Path) -> None:
    html = _render_xhs("# 标题\n\n> 封面：一句话\n\n正文。\n", tmp_path, "标题")
    assert "card fallback text-only" in html
    assert "一句话" in html


def test_render_xhs_prefers_rendered_cards(tmp_path: Path) -> None:
    export = tmp_path / "xhs_export"
    export.mkdir()
    (export / "01_cover.png").write_bytes(b"fake-png")
    html = _render_xhs(
        "# 标题\n\n> 封面：一句话\n\n正文。\n\n## 配图\n- figures/fig-01.jpg：看封面\n",
        tmp_path,
        "标题",
        card_images=["xhs_export/01_cover.png"],
    )
    assert "xhs_export/01_cover.png" in html
    assert "配图 · 1 张" in html
    assert "figures/fig-01.jpg" not in html


def test_parse_xhs_note_separates_sidecars() -> None:
    markdown = """# 标题

> 封面：一句话

正文第一段。

## 配图
- figures/fig-01.jpg：看封面

## 标签
#测试 #示例

---

内容参考 B 站视频《示例》。
"""
    parsed = _parse_xhs_note(markdown)
    assert parsed["title"] == "标题"
    assert parsed["cover_text"] == "一句话"
    assert parsed["body"] == "正文第一段。"
    assert parsed["gallery"] == [("figures/fig-01.jpg", "看封面")]
    assert parsed["tags"] == ["#测试", "#示例"]
    assert parsed["source"] == "内容参考 B 站视频《示例》。"


def test_render_wechat_inlines_styles_and_copy_button(tmp_path: Path) -> None:
    html = _render_wechat("## 小节\n\n正文。", tmp_path, "标题")
    assert 'style="font-size:21px' in html
    assert 'style="font-size:16px' in html
    assert "copyWechat()" in html
    assert "复制正文" in html


def test_export_pdf_reports_missing_binary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FACET_STUDIO_PANDOC", str(tmp_path / "missing-pandoc"))
    result = _export_pdf(
        form_dir=tmp_path,
        markdown="# 标题\n\n正文。",
        title="标题",
        source="来源",
    )
    assert "pandoc not found" in result["error"]


def test_pdf_title_breaks_long_title_at_punctuation() -> None:
    value = _pdf_title("300 张没有标签的照片，输入一句话就能搜到蝙蝠")
    assert r" \\ " in value
    assert _pdf_title("短标题") == "短标题"


def test_render_wechat_copy_body_excludes_title(tmp_path: Path) -> None:
    html = _render_wechat("# 标题\n\n正文。", tmp_path, "标题")
    main = html.split('<main id="wechat-article"', 1)[1].split("</main>", 1)[0]
    assert "正文。" in main
    assert "<h1" not in main
    assert "<h1" in html


def test_typeset_marks_partial_and_get_run_reports_draft(
    tmp_path: Path, monkeypatch
) -> None:
    run_dir, _ = _write_run(tmp_path, monkeypatch, "run_partial")
    monkeypatch.setattr(
        mcp_server,
        "_export_pdf",
        lambda **kwargs: {"error": "tectonic not found"},
    )
    result = typeset_article("run_partial")
    assert result["pdf"]["error"] == "tectonic not found"

    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "partial"
    assert any("tectonic not found" in item for item in meta["typeset_errors"])

    run = get_run("run_partial")
    assert run["review_status"] == "draft"
    assert "草稿" in run["summary"]
    assert run["typeset_errors"]

    reviewed = review_artifact("run_partial", "approved")
    assert reviewed["status"] == "approved"
    assert reviewed["review_status"] == "approved"
    assert get_run("run_partial")["review_status"] == "approved"
    assert "草稿" not in get_run("run_partial")["summary"]

    # A new render invalidates the old approval instead of silently inheriting it.
    typeset_article("run_partial")
    stale = get_run("run_partial")
    assert stale["review_status"] == "stale"
    assert "待重新验收" in stale["summary"]
    assert review_artifact("run_partial", "approved")["review_status"] == "approved"


def test_review_artifact_rejects_untypeset_run(
    tmp_path: Path, monkeypatch
) -> None:
    _write_run(tmp_path, monkeypatch, "run_written", status="written")
    with pytest.raises(ValueError, match="typeset_article"):
        review_artifact("run_written", "approved")
