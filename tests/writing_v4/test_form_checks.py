from __future__ import annotations

from pathlib import Path

import pytest

from lunograph.writing_v4.form_checks import check_form, check_script, check_social


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_social_clean_passes(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "post.md",
        "# 一个具体标题\n\n"
        "先说结果：这样做能少走一步。具体做法是把材料按顺序放好，再开始操作。\n\n"
        "顺序错了，后面每一步都要返工；顺序对了，后面只需要检查一个点。\n\n"
        "---\n\n素材来源：B 站视频（BVtest）。\n",
    )
    report = check_social(path, repo_root=tmp_path)
    assert report["ok"], report["issues"]


def test_social_leak_word_fails(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "post.md",
        "# 标题\n\n视频里说了一个方法，具体做法是把材料按顺序放好。\n\n"
        "---\n\n素材来源：B 站视频（BVtest）。\n",
    )
    report = check_social(path, repo_root=tmp_path)
    assert not report["ok"]
    assert any("视频里" in issue for issue in report["issues"])


def test_social_timecode_fails(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "post.md",
        "# 标题\n\n在 0:15 的时候，先把材料放好，再开始操作。\n\n"
        "---\n\n素材来源：B 站视频（BVtest）。\n",
    )
    report = check_social(path, repo_root=tmp_path)
    assert not report["ok"]
    assert any("timecode" in issue for issue in report["issues"])


def test_social_missing_source_fails(tmp_path: Path) -> None:
    path = _write(tmp_path / "post.md", "# 标题\n\n正文。\n")
    report = check_social(path, repo_root=tmp_path)
    assert not report["ok"]
    assert any("source" in issue for issue in report["issues"])


def test_source_line_is_not_a_leak(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "post.md",
        "# 标题\n\n正文里没有工作痕迹。\n\n---\n\n素材来源：B 站视频（BVtest）。\n",
    )
    report = check_social(path, repo_root=tmp_path)
    assert report["ok"], report["issues"]


def test_script_clean_passes(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "script.md",
        "# 标题\n\n## 镜头表\n\n| 时间 | 画面 | 旁白 | 素材 |\n|---|---|---|---|\n"
        "| 0–3s | 成品特写 | 为什么别人做出来是脆的？ | 图示 1（figures/fig-01.jpg） |\n"
        "| 3–10s | 操作特写 | 差别在第一次的温度。 | 图示 2（figures/fig-02.jpg） |\n\n"
        "## 旁白全文\n\n同样的材料，为什么别人做出来是脆的？差别在第一次的温度。\n\n"
        "## 素材说明\n\n- 真实帧：图示 1、图示 2。\n- 示意/生成：无。\n\n"
        "---\n\n素材来源：B 站视频（BVtest）；画面仅作分镜参考。\n",
    )
    (tmp_path / "figures").mkdir()
    (tmp_path / "figures" / "fig-01.jpg").write_bytes(b"x")
    (tmp_path / "figures" / "fig-02.jpg").write_bytes(b"x")
    report = check_script(path, repo_root=tmp_path)
    assert report["ok"], report["issues"]


def test_script_missing_narration_fails(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "script.md",
        "# 标题\n\n## 镜头表\n\n| 时间 | 画面 | 旁白 | 素材 |\n|---|---|---|---|\n"
        "| 0–3s | 特写 | 问题 | 示意/生成 |\n\n"
        "---\n\n素材来源：B 站视频（BVtest）。\n",
    )
    report = check_script(path, repo_root=tmp_path)
    assert not report["ok"]
    assert any("旁白" in issue for issue in report["issues"])


def test_script_missing_shot_section_fails(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "script.md",
        "# 标题\n\n## 旁白全文\n\n一句话。\n\n---\n\n素材来源：B 站视频（BVtest）。\n",
    )
    report = check_script(path, repo_root=tmp_path)
    assert not report["ok"]
    assert any("镜头" in issue or "分镜" in issue for issue in report["issues"])


def test_script_missing_image_fails(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "script.md",
        "# 标题\n\n## 镜头表\n\n| 时间 | 画面 | 旁白 | 素材 |\n|---|---|---|---|\n"
        "| 0–3s | 特写 | 问题 | 图示 1（figures/missing.jpg） |\n\n"
        "## 旁白全文\n\n一句话。\n\n---\n\n素材来源：B 站视频（BVtest）。\n",
    )
    report = check_script(path, repo_root=tmp_path)
    assert not report["ok"]
    assert any("missing image" in issue for issue in report["issues"])


def test_check_form_unknown_profile_raises(tmp_path: Path) -> None:
    path = _write(tmp_path / "x.md", "# 标题\n")
    with pytest.raises(ValueError):
        check_form(path, profile="nope", repo_root=tmp_path)
