from pathlib import Path

from lunograph.writing_v4.article_checks import check_article


SOURCE_LINE = "本文根据 B 站视频《示例》整理；画面截取自原视频。"


def write_article(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "article.md"
    path.write_text(body, encoding="utf-8")
    return path


def test_clean_article_passes(tmp_path: Path) -> None:
    path = write_article(
        tmp_path,
        f"# 标题\n\n正文。\n\n---\n\n{SOURCE_LINE}\n",
    )
    report = check_article(path, repo_root=tmp_path)
    assert report["ok"], report["issues"]


def test_leak_word_fails(tmp_path: Path) -> None:
    path = write_article(
        tmp_path,
        f"# 标题\n\n这里的素材说了一件事。\n\n---\n\n{SOURCE_LINE}\n",
    )
    report = check_article(path, repo_root=tmp_path)
    assert not report["ok"]
    assert any("leak word" in issue for issue in report["issues"])


def test_video_framing_fails(tmp_path: Path) -> None:
    path = write_article(
        tmp_path,
        f"# 标题\n\n视频里演示了这件事。\n\n---\n\n{SOURCE_LINE}\n",
    )
    report = check_article(path, repo_root=tmp_path)
    assert not report["ok"]
    assert any("leak word" in issue for issue in report["issues"])


def test_timecode_fails(tmp_path: Path) -> None:
    path = write_article(
        tmp_path,
        f"# 标题\n\n在 00:12 时发生了这件事。\n\n---\n\n{SOURCE_LINE}\n",
    )
    report = check_article(path, repo_root=tmp_path)
    assert not report["ok"]
    assert any("timecode" in issue for issue in report["issues"])


def test_missing_image_fails(tmp_path: Path) -> None:
    path = write_article(
        tmp_path,
        f"# 标题\n\n![说明](assets/missing.jpg)\n\n---\n\n{SOURCE_LINE}\n",
    )
    report = check_article(path, repo_root=tmp_path)
    assert not report["ok"]
    assert any("missing image" in issue for issue in report["issues"])


def test_existing_image_passes(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "ok.jpg").write_bytes(b"not-a-real-jpeg")
    path = write_article(
        tmp_path,
        f"# 标题\n\n![说明](assets/ok.jpg)\n\n---\n\n{SOURCE_LINE}\n",
    )
    report = check_article(path, repo_root=tmp_path)
    assert report["ok"], report["issues"]


def test_missing_source_line_fails(tmp_path: Path) -> None:
    path = write_article(tmp_path, "# 标题\n\n正文。\n")
    report = check_article(path, repo_root=tmp_path)
    assert not report["ok"]
    assert any("source line" in issue for issue in report["issues"])
