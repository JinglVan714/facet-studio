from pathlib import Path

import pytest

import facet_studio.ingest as ingest


def test_ingest_source_builds_cached_content(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("FACET_STUDIO_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("FACET_STUDIO_DATA_ROOT", str(tmp_path / "data"))
    calls: dict[str, object] = {}

    monkeypatch.setattr(ingest.acquire, "is_url", lambda target: True)
    monkeypatch.setattr(
        ingest.acquire,
        "acquire_url",
        lambda target, max_height=1080: {
            "video_id": "BVnew",
            "title": "新视频",
        },
    )

    def fake_ingest(video_id, *, profile="quality", force=False):
        calls["ingest"] = (video_id, profile, force)
        return {"video_id": video_id, "stages": {}}

    monkeypatch.setattr(ingest, "run_ingest", fake_ingest)

    def fake_content(*, video_id, data_root, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("content for " + video_id + "\n", encoding="utf-8")
        return "content for " + video_id + "\n", 2

    monkeypatch.setattr(ingest, "build_content_manuscript", fake_content)

    result = ingest.ingest_source("https://www.bilibili.com/video/BVnew")
    assert result["video_id"] == "BVnew"
    assert result["status"] == "content_ready"
    assert result["figure_count"] == 2
    assert Path(result["content_path"]).parts[-4:] == (
        "writing_rebuild_2026-11-04",
        "BVnew",
        "content_final_v3",
        "content.md",
    )
    assert Path(result["content_path"]).is_file()
    assert result["content_sha256"]
    assert calls["ingest"] == ("BVnew", "quality", False)


def test_ingest_source_rejects_unknown_profile() -> None:
    with pytest.raises(ValueError):
        ingest.ingest_source("https://example.com/v", profile="slow")
