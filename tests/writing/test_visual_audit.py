"""Tests for loading the article's real frames for a VLM verifier."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from lunograph.media.audit import load_article_frame_images


def test_load_article_frame_images_downscales_and_keeps_caption(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    Image.new("RGB", (2000, 1000), "white").save(assets / "frame_00010.jpg")
    article = (
        "# 标题\n\n"
        "![frame](assets/frame_00010.jpg)\n\n"
        "*看哪里：前排仍是水中动物。*\n\n"
        "![chart](assets/chart_01.svg)\n\n"
        "*看两根柱子。*\n"
    )
    images, skipped = load_article_frame_images(article, assets)
    assert not skipped
    assert len(images) == 1
    assert images[0]["frame_id"] == "00010"
    assert images[0]["caption"] == "看哪里：前排仍是水中动物。"
    assert images[0]["sent_width"] <= 1024
    assert images[0]["sent_height"] <= 1024
    assert images[0]["downscaled"] is True


def test_load_article_frame_images_reports_missing_asset(tmp_path: Path) -> None:
    article = "![frame](assets/frame_missing.jpg)\n\n*看画面。*\n"
    images, skipped = load_article_frame_images(article, tmp_path / "assets")
    assert images == []
    assert skipped[0]["reason"] == "missing_asset"
