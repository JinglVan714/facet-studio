import json
from pathlib import Path

from PIL import Image

from facet_studio.evals.product import _check_run, evaluate


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _xhs_run(tmp_path: Path) -> Path:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "product_v1" / "run_xhs"
    form_dir = run_dir / "xiaohongshu_note"
    export = form_dir / "xhs_export"
    figures = form_dir / "figures"
    export.mkdir(parents=True)
    figures.mkdir()
    (figures / "fig-01.jpg").write_bytes(b"fake")
    Image.new("RGB", (1080, 1440), "white").save(export / "01_cover.png")
    (form_dir / "note.md").write_text(
        "# 测试标题\n\n> 封面：一句话\n\n测试正文。\n\n## 标签\n#测试\n",
        encoding="utf-8",
    )
    (form_dir / "reader.html").write_text(
        '<button id="copy-note-btn">复制</button>'
        '<button class="copy-image-btn">复制图片</button>',
        encoding="utf-8",
    )
    _write_json(
        run_dir / "run_meta.json",
        {
            "run_id": "run_xhs",
            "form": "xiaohongshu_note",
            "status": "approved",
            "form_dir": str(form_dir),
            "output": "note.md",
            "planner_usage": {"total_tokens": 50},
            "planner_latency_ms": 100,
            "write": {
                "output_chars": 500,
                "figures_referenced": ["figures/fig-01.jpg"],
                "missing_figures": [],
                "usage": {"total_tokens": 100},
                "latency_ms": 1000,
            },
            "artifacts": {
                "reader_html": str(form_dir / "reader.html"),
                "xhs_export_dir": str(export),
            },
        },
    )
    _write_json(run_dir / "publish_review.json", {"decision": "approved"})
    return runs_root


def test_eval_passes_well_formed_xhs_case(tmp_path: Path) -> None:
    runs_root = _xhs_run(tmp_path)
    result = _check_run(
        {
            "case_id": "case_xhs",
            "kind": "capability",
            "form": "xiaohongshu_note",
            "run_id": "run_xhs",
            "require_approval": True,
            "min_body_chars": 100,
            "min_figures": 1,
            "min_cards": 1,
            "must_include": ["测试"],
        },
        runs_root=runs_root,
    )
    assert result["passed"] is True
    assert all(check["passed"] for check in result["checks"])


def test_eval_marks_missing_case_without_faking_scores(tmp_path: Path) -> None:
    report = evaluate(
        [
            {
                "case_id": "missing",
                "kind": "capability",
                "run_id": None,
            }
        ],
        runs_root=tmp_path,
    )
    assert report["summary"]["cases_run"] == 0
    assert report["summary"]["cases_missing"] == 1
    assert report["summary"]["deterministic_pass_rate"] is None
    assert report["summary"]["pass_at_1"] is None
    assert report["cases"][0]["status"] == "not_run"


def test_eval_fails_wechat_h1_in_copy_body(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "product_v1" / "run_wechat"
    form_dir = run_dir / "wechat_article"
    form_dir.mkdir(parents=True)
    (form_dir / "article.md").write_text("# 标题\n\n正文。\n", encoding="utf-8")
    (form_dir / "wechat.html").write_text(
        '<main id="wechat-article"><h1>标题</h1><p>正文。</p></main>',
        encoding="utf-8",
    )
    _write_json(
        run_dir / "run_meta.json",
        {
            "run_id": "run_wechat",
            "form": "wechat_article",
            "status": "approved",
            "form_dir": str(form_dir),
            "output": "article.md",
            "planner_usage": {"total_tokens": 50},
            "planner_latency_ms": 100,
            "write": {
                "output_chars": 100,
                "figures_referenced": [],
                "missing_figures": [],
                "usage": {"total_tokens": 100},
                "latency_ms": 1000,
            },
            "artifacts": {
                "reader_html": str(form_dir / "wechat.html"),
                "wechat_html": str(form_dir / "wechat.html"),
            },
        },
    )
    _write_json(run_dir / "publish_review.json", {"decision": "approved"})
    result = _check_run(
        {
            "case_id": "case_wechat",
            "kind": "regression",
            "form": "wechat_article",
            "run_id": "run_wechat",
            "require_approval": True,
            "min_body_chars": 10,
            "min_figures": 0,
            "min_images": 0,
        },
        runs_root=runs_root,
    )
    assert result["passed"] is False
    assert any(
        check["check_id"] == "wechat_artifact" and not check["passed"]
        for check in result["checks"]
    )
