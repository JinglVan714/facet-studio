from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lunograph.writing_v4.skill_runner import (
    _source_line,
    build_system,
    build_user,
    load_manifest,
)


def _manifest(tmp_path: Path, **overrides) -> Path:
    (tmp_path / "SKILL.md").write_text("# skill\n", encoding="utf-8")
    (tmp_path / "examples.md").write_text("# examples\n", encoding="utf-8")
    (tmp_path / "user.md").write_text(
        "请写一条笔记。\n请求：{request}\n内容：{content}\n", encoding="utf-8"
    )
    payload = {
        "id": "test-skill",
        "version": "0.1.0",
        "skill": "SKILL.md",
        "examples": "examples.md",
        "prompt": "user.md",
        "source_line": "social",
        "check_profile": "social",
        "forms": ["social_note"],
        "quality_rubric": "test-v1",
    }
    payload.update(overrides)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_manifest_resolves_paths(tmp_path: Path) -> None:
    manifest = load_manifest(_manifest(tmp_path))
    assert Path(manifest["skill"]) == (tmp_path / "SKILL.md").resolve()
    assert Path(manifest["examples"]) == (tmp_path / "examples.md").resolve()
    assert Path(manifest["prompt"]) == (tmp_path / "user.md").resolve()
    assert manifest["source_line"] == "social"
    assert manifest["max_tokens"] == 8192


def test_load_manifest_missing_required_key_raises(tmp_path: Path) -> None:
    path = _manifest(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["id"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_manifest(path)


def test_build_system_includes_examples(tmp_path: Path) -> None:
    manifest = load_manifest(_manifest(tmp_path))
    system = build_system(manifest)
    assert "# skill" in system
    assert "# 例子参考" in system
    assert "# examples" in system


def test_build_user_replaces_placeholders(tmp_path: Path) -> None:
    manifest = load_manifest(_manifest(tmp_path))
    user = build_user(manifest, request="小红书", content="内容正文")
    assert "小红书" in user
    assert "内容正文" in user
    assert "{content}" not in user


def test_inline_user_template(tmp_path: Path) -> None:
    manifest = load_manifest(
        _manifest(tmp_path, prompt="", user_template="请求：{request}\n内容：{content}")
    )
    user = build_user(manifest, request="R", content="C")
    assert user == "请求：R\n内容：C"


def test_source_line_social_with_source_json(tmp_path: Path) -> None:
    video = tmp_path / "BVtest"
    video.mkdir()
    (video / "source.json").write_text(
        json.dumps({"title": "标题", "uploader": "作者"}), encoding="utf-8"
    )
    line = _source_line(
        "social",
        settings=SimpleNamespace(data_root=tmp_path),
        video_id="BVtest",
    )
    assert line == "素材来源：B 站视频《标题》（UP 主：作者）。"


def test_source_line_without_source_json_uses_video_id(tmp_path: Path) -> None:
    line = _source_line(
        "social",
        settings=SimpleNamespace(data_root=tmp_path),
        video_id="BVtest",
    )
    assert line == "素材来源：B 站视频（BVtest）。"


def test_source_line_none(tmp_path: Path) -> None:
    line = _source_line(
        "none",
        settings=SimpleNamespace(data_root=tmp_path),
        video_id="BVtest",
    )
    assert line == ""
