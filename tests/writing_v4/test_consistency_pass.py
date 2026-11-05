from lunograph.writing_v4.consistency_pass import split_source_line


def test_source_line_is_split_from_body() -> None:
    article = "# 标题\n\n正文。\n\n---\n\n本文根据 B 站视频《示例》整理；画面截取自原视频。\n"
    body, source = split_source_line(article)
    assert body == "# 标题\n\n正文。\n"
    assert source == "\n---\n\n本文根据 B 站视频《示例》整理；画面截取自原视频。\n"


def test_no_source_line_leaves_article_alone() -> None:
    article = "# 标题\n\n正文。\n"
    body, source = split_source_line(article)
    assert body == article
    assert source == ""


def test_horizontal_rule_in_body_is_not_source() -> None:
    article = "# 标题\n\n正文。\n\n---\n\n下一节。\n"
    body, source = split_source_line(article)
    assert body == article
    assert source == ""
