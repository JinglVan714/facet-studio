"""Tests for the M1 generate wiring (no provider call)."""

from __future__ import annotations

import json
from pathlib import Path

from lunograph.writing_v3 import generate

PACK = {
    "pack_id": "p1",
    "sentences": [
        {
            "sentence_id": "s1",
            "text": "产品有 1805 年历史。",
            "t_start_ms": 0,
            "t_end_ms": 1000,
        }
    ],
    "claims": [
        {
            "claim_id": "c1",
            "text": "产品有 1805 年历史。",
            "evidence_ids": ["e1"],
        }
    ],
    "evidence": [
        {
            "evidence_id": "e1",
            "claim_ids": ["c1"],
            "quote": "产品有 1805 年历史。",
            "sentence_ids": ["s1"],
            "t_start_ms": 0,
            "t_end_ms": 1000,
        }
    ],
    "frames": [],
}
ARTICLE = """# 标题

产品有 1805 年历史。“产品有 1805 年历史。”是原文，“这套产品绝对可靠”是转述。
"""
EDITED = "产品有 1805 年历史。\n"


def _write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, str):
        path.write_text(value, encoding="utf-8")
    else:
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8"
        )


def test_generate_with_existing_article_cleans_and_binds(tmp_path) -> None:
    request = tmp_path / "request.json"
    _write(request, {"central_question": "为什么？"})
    edited = tmp_path / "edited.txt"
    _write(edited, EDITED)
    article = tmp_path / "article.md"
    _write(article, ARTICLE)
    pack = tmp_path / "pack.json"
    _write(pack, PACK)
    sentences = tmp_path / "sentences.json"
    _write(sentences, {"sentences": PACK["sentences"]})
    out_dir = tmp_path / "out"
    code = generate.main(
        [
            "--case-id",
            "case",
            "--request",
            str(request),
            "--edited-text",
            str(edited),
            "--article",
            str(article),
            "--pack",
            str(pack),
            "--sentences",
            str(sentences),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert code == 0
    cleaned = (out_dir / "article.md").read_text(encoding="utf-8")
    assert "“产品有 1805 年历史。”" in cleaned
    assert "“这套产品绝对可靠”" not in cleaned
    assert "这套产品绝对可靠" in cleaned
    hygiene = json.loads(
        (out_dir / "quote_hygiene.json").read_text(encoding="utf-8")
    )
    assert hygiene["removed"] == 1
    binding = json.loads(
        (out_dir / "binding.json").read_text(encoding="utf-8")
    )
    assert binding["status"] == "complete"
    assert binding["counts"]["facts"]["bound"] == 1
    assert (out_dir / "reader.md").exists()
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "complete"


def test_generate_dry_run_writes_prompts_without_article(tmp_path) -> None:
    request = tmp_path / "request.json"
    _write(request, {"central_question": "为什么？"})
    edited = tmp_path / "edited.txt"
    _write(edited, EDITED)
    out_dir = tmp_path / "out"
    code = generate.main(
        [
            "--case-id",
            "case",
            "--request",
            str(request),
            "--edited-text",
            str(edited),
            "--out-dir",
            str(out_dir),
        ]
    )
    assert code == 0
    assert (out_dir / "writer" / "prompts" / "prose_writer.system.txt").exists()
    assert (out_dir / "writer" / "prompts" / "prose_writer.user.txt").exists()
    assert not (out_dir / "article.md").exists()
    manifest = json.loads(
        (out_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "dry_run"
