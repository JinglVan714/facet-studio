"""Tests for the deterministic reader-facing contract audit."""

from __future__ import annotations

from facet_studio.writing.contract import audit_contract

ARTICLE = (
    "# 最高分只有 0.756：为什么 0.8 会筛空\n\n"
    "正文里有 0.756 和 0.8 这两个数。\n\n"
    "![chart](assets/chart_01.svg)\n\n"
    "*看 0.8 这条线在 0.756 之上。*\n\n"
    "来源：视频；标题、发布日期与链接未提供，可在 B 站按频道名检索。"
)

BRIEF = {
    "source_block": {
        "video": "BVtest",
        "channel": "unknown",
        "date": "unknown",
        "link": "unknown",
        "official": [],
        "missing": ["title", "link"],
    }
}


def test_contract_complete_when_source_title_and_caption_exist() -> None:
    report = audit_contract(ARTICLE, brief=BRIEF)
    assert report["status"] == "complete"
    assert report["blocking"] == []
    assert report["findings"] == []


def test_contract_blocks_missing_source_line() -> None:
    report = audit_contract("# 标题\n\n正文。", brief=BRIEF)
    assert report["status"] == "partial"
    assert any(item["axis"] == "source" for item in report["blocking"])


def test_contract_blocks_title_quote_not_in_body() -> None:
    article = (
        "# 「你们永远不用毕业」：一个虚拟主播\n\n"
        "正文只有第三人称转述。\n\n"
        "来源：视频；链接未提供。"
    )
    report = audit_contract(article, brief=BRIEF)
    assert report["status"] == "partial"
    assert any(item["axis"] == "title_cta" for item in report["blocking"])


def test_contract_blocks_image_without_caption() -> None:
    article = (
        "# 标题\n\n正文 0.756。\n\n"
        "![chart](assets/chart_01.svg)\n\n"
        "图片后面的正文。\n\n"
        "来源：视频；链接未提供。"
    )
    report = audit_contract(article, brief=BRIEF)
    assert report["status"] == "partial"
    assert any(item["axis"] == "image_caption" for item in report["blocking"])


def test_contract_marks_absolutes_advisory_not_blocking() -> None:
    article = ARTICLE.replace("正文里有", "任何固定门槛都会筛空；正文里有")
    report = audit_contract(article, brief=BRIEF)
    assert report["status"] == "complete"
    assert any(item["axis"] == "consistency" for item in report["findings"])
    assert not any(item["axis"] == "consistency" for item in report["blocking"])


def test_contract_blocks_undisclosed_source_gap() -> None:
    article = (
        "# 标题 0.756\n\n正文 0.756。\n\n"
        "来源：视频。"
    )
    report = audit_contract(article, brief=BRIEF)
    assert report["status"] == "partial"
    assert any(
        item["axis"] == "source" and "gaps" in item["observation"].lower()
        for item in report["blocking"]
    )


def test_contract_does_not_treat_search_hint_as_gap_disclosure() -> None:
    article = (
        "# 标题 0.756\n\n正文 0.756。\n\n"
        "来源：视频；可在 B 站搜索 BVtest。"
    )
    report = audit_contract(article, brief=BRIEF)
    assert report["status"] == "partial"
    assert any(item["axis"] == "source" for item in report["blocking"])


def test_contract_accepts_field_specific_gap_disclosure() -> None:
    article = (
        "# 标题 0.756\n\n正文 0.756。\n\n"
        "来源：视频；标题与链接未提供。"
    )
    report = audit_contract(article, brief=BRIEF)
    assert report["status"] == "complete"
    assert report["blocking"] == []


