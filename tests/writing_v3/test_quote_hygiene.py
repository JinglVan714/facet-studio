"""Tests for deterministic quote hygiene."""

from __future__ import annotations

from facet_studio.writing_v3 import quote_hygiene


def test_exact_quote_is_kept() -> None:
    source = "他说：“产品有 1805 年历史。”"
    result = quote_hygiene.clean_article(
        "“产品有 1805 年历史。”这是结论。", source
    )
    assert "“产品有 1805 年历史。”" in result["article"]
    assert result["report"]["kept"] == 1
    assert result["report"]["removed"] == 0


def test_paraphrase_quote_is_removed() -> None:
    source = "产品有 1805 年历史。"
    result = quote_hygiene.clean_article(
        "“这套产品非常可靠”这是结论。", source
    )
    assert "“" not in result["article"]
    assert "这套产品非常可靠" in result["article"]
    assert result["report"]["removed"] == 1
    assert result["report"]["removed_quotes"] == ["这套产品非常可靠"]


def test_normalized_filler_quote_is_kept() -> None:
    source = "他说：“产品有 1805 年历史，嗯，很久了。”"
    result = quote_hygiene.clean_article(
        "“产品有 1805 年历史，很久了”这是结论。", source
    )
    assert "“产品有 1805 年历史，很久了”" in result["article"]
    assert result["report"]["kept"] == 1


def test_corner_quotes_and_backticks() -> None:
    source = "「一切皆插件」是核心理念。"
    result = quote_hygiene.clean_article(
        "「一切皆插件」和「不存在的说法」以及 `runcode`。", source
    )
    assert "「一切皆插件」" in result["article"]
    assert "「不存在的说法」" not in result["article"]
    assert "不存在的说法" in result["article"]
    assert "`runcode`" not in result["article"]
    assert "runcode" in result["article"]


def test_short_quotes_are_untouched() -> None:
    result = quote_hygiene.clean_article("他说“好”。", "没有这个字。")
    assert result["article"] == "他说“好”。"
    assert result["report"]["checked"] == 0


def test_same_input_same_output() -> None:
    first = quote_hygiene.clean_article("“甲”和“乙”。", "甲。")
    second = quote_hygiene.clean_article("“甲”和“乙”。", "甲。")
    assert first == second
