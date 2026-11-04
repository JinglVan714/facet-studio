"""Tests for the final polish pass."""

from __future__ import annotations

import json
from pathlib import Path

from lunograph.writing.polish import run_polish

ARTICLE = "# 标题\n\n正文第一段。\n\n正文第二段。"
SOURCE = "视频里说，正文。"
BRIEF = {
    "source_block": {"video": "BVtest", "missing": ["link"]},
    "number_ledger": [{"value": "0.756", "metric": "cosine"}],
    "concept_ledger": [],
    "mechanism_chain": [],
}


class _Usage:
    def as_dict(self):
        return {"total_tokens": 42}


class _Response:
    text = "# 更好的标题\n\n润色后的第一段。\n\n润色后的第二段。"
    usage = _Usage()
    latency_ms = 9
    cached = False
    finish_reason = "stop"


class _Provider:
    model = "fake"

    def __init__(self) -> None:
        self.user: dict = {}

    def complete(self, **kwargs):
        self.user = json.loads(kwargs["user"])
        return _Response()


def test_run_polish_returns_markdown_and_report(tmp_path: Path) -> None:
    provider = _Provider()
    report = run_polish(
        ARTICLE,
        SOURCE,
        BRIEF,
        {"central_question": "它是什么？"},
        tmp_path,
        run=True,
        provider=provider,
    )
    assert report["status"] == "complete"
    assert report["article"] == _Response.text
    assert len(report["article_hash"]) == 64
    assert report["usage"] == {"total_tokens": 42}
    assert provider.user["article"] == ARTICLE
    assert provider.user["source_text"] == SOURCE
    assert "smart general reader" in provider.user["request"]["reader_profile"]
    assert (tmp_path / "polished.md").exists()
    assert (tmp_path / "polish_report.json").exists()


def test_run_polish_dry_run_does_not_call_provider(tmp_path: Path) -> None:
    report = run_polish(ARTICLE, SOURCE, BRIEF, {}, tmp_path, run=False)
    assert report["status"] == "dry_run"
    assert report["article"] == ""
