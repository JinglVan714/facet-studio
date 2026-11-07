from pathlib import Path

from facet_studio.writing_v4.skills import form_catalog, load_skill

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills" / "writing"


def test_wechat_extends_video_article_core() -> None:
    skill = load_skill(SKILLS / "wechat-article")
    assert skill.form == "wechat_article"
    assert skill.id == "wechat-article"
    assert skill.role == "wechat_writer"
    assert skill.source_line == "article"
    assert skill.output_name == "article.md"
    assert skill.temperature == 0.5
    # core method and platform layer are both present
    assert "内容文章写作" in skill.system
    assert "公众号文章" in skill.system
    assert "事实边界" in skill.system


def test_examples_include_core_and_platform() -> None:
    skill = load_skill(SKILLS / "wechat-article")
    assert len(skill.example_parts) == 2
    assert "匿名例子" in skill.system
    assert "caption 要写" in skill.system


def test_render_user_fills_request_and_content() -> None:
    skill = load_skill(SKILLS / "wechat-article")
    user = skill.render_user(request="写给新手看", content="这是这件事的完整内容。")
    assert "写给新手看" in user
    assert "这是这件事的完整内容。" in user
    assert "{content}" not in user
    assert "{request}" not in user


def test_form_catalog_has_active_forms_only() -> None:
    catalog = form_catalog(SKILLS)
    forms = {item["form"] for item in catalog}
    assert "long_article" in forms
    assert "wechat_article" in forms
    # old placeholder/method skills are not active forms
    assert "reader_first_explainer" not in forms


def test_video_article_form_id_is_long_article() -> None:
    skill = load_skill(SKILLS / "video-article")
    assert skill.form == "long_article"
    assert "内容文章写作" in skill.system
