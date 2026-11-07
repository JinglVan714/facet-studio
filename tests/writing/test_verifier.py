"""Tests for the independent semantic verifier."""

from __future__ import annotations

import json
from pathlib import Path

from facet_studio.writing.verifier import run_verifier

ARTICLE = "# 标题\n\n正文提到 Google 昨晚开源了某个模型。"
SOURCE = "视频里说，Google 昨晚开源了某个模型。"
BRIEF = {
    "source_block": {"video": "BVtest", "missing": ["link"]},
    "number_ledger": [{"value": "0.756", "metric": "cosine", "status": "video_claim"}],
    "concept_ledger": [],
    "mechanism_chain": [],
}


class _Usage:
    def as_dict(self):
        return {"total_tokens": 42}


class _Response:
    text = json.dumps(
        {
            "status": "complete",
            "red_line": False,
            "findings": [
                {
                    "axis": "source",
                    "severity": "critical",
                    "quote": "Google 昨晚开源了某个模型",
                    "observation": "视频说法被写成事实。",
                    "impact": "读者会把它当作官方确认。",
                    "action": "改成“视频称”，并说明未核实。",
                }
            ],
        },
        ensure_ascii=False,
    )
    usage = _Usage()
    latency_ms = 7
    cached = False
    finish_reason = "stop"


class _Provider:
    model = "fake"

    def __init__(self) -> None:
        self.user: dict = {}
        self.images: list = []

    def complete(self, **kwargs):
        self.user = json.loads(kwargs["user"])
        self.images = list(kwargs.get("images") or [])
        return _Response()


def test_run_verifier_returns_quote_located_findings(tmp_path: Path) -> None:
    provider = _Provider()
    report = run_verifier(
        ARTICLE,
        SOURCE,
        BRIEF,
        {"provenance": {"video_id": "BVtest"}},
        {"central_question": "它是什么？", "reader_profile": "AI beginner"},
        tmp_path,
        run=True,
        provider=provider,
    )
    assert report["status"] == "complete"
    assert report["red_line"] is True  # critical finding escalates the red line
    assert report["findings"][0]["axis"] == "source"
    assert report["findings"][0]["severity"] == "critical"
    assert len(report["article_hash"]) == 64
    assert provider.user["article"] == ARTICLE
    assert provider.user["source_text"] == SOURCE
    assert provider.user["request"]["reader_profile"] == "AI beginner"
    assert (tmp_path / "verifier_report.json").exists()


def test_run_verifier_dry_run_does_not_call_provider(tmp_path: Path) -> None:
    report = run_verifier(
        ARTICLE,
        SOURCE,
        BRIEF,
        {},
        {},
        tmp_path,
        run=False,
    )
    assert report["status"] == "dry_run"
    assert report["findings"] == []


def test_run_verifier_passes_visual_manifest_for_rendered_visuals(
    tmp_path: Path,
) -> None:
    provider = _Provider()
    report = run_verifier(
        ARTICLE,
        SOURCE,
        BRIEF,
        {},
        {},
        tmp_path,
        run=True,
        provider=provider,
        visual_plan={
            "visuals": [
                {
                    "kind": "diagram",
                    "status": "illustration",
                    "caption": "正文",
                    "diagram": {
                        "nodes": [{"id": "n1", "label": "正文"}],
                        "edges": [],
                    },
                }
            ]
        },
    )
    assert report["status"] == "complete"
    assert provider.user["visual_manifest"][0]["kind"] == "diagram"
    assert provider.user["visual_manifest"][0]["status"] == "illustration"
    assert report["visual_manifest"] == 1


def test_run_verifier_passes_images_and_records_hashes(tmp_path: Path) -> None:
    provider = _Provider()
    report = run_verifier(
        ARTICLE,
        SOURCE,
        BRIEF,
        {"provenance": {"video_id": "BVtest"}},
        {"central_question": "它是什么？"},
        tmp_path,
        run=True,
        provider=provider,
        images=[
            {
                "data": b"fake-jpeg-bytes",
                "media_type": "image/jpeg",
                "name": "frame_00010.jpg",
                "frame_id": "00010",
                "caption": "看分数和前排动物",
            }
        ],
    )
    assert report["status"] == "complete"
    assert report["visual_status"] == "checked"
    assert len(provider.images) == 1
    assert provider.user["image_manifest"][0]["frame_id"] == "00010"
    assert len(report["images"][0]["sha256"]) == 64
    assert report["images"][0]["bytes"] == len(b"fake-jpeg-bytes")
