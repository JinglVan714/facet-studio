import json
from pathlib import Path
from types import SimpleNamespace

from facet_studio.providers.llm import LLMResponse, LLMUsage
from facet_studio.writing_v4.writer import (
    ensure_source_line,
    extract_reader_contract,
    extract_title_candidates,
    figure_refs,
    write_form,
)

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills" / "writing"
WECHAT = SKILLS / "wechat-article"


class FakeLLM:
    provider = "fake"
    model = "fake-model"

    def __init__(self, *, article: str, svg_spec: str = "") -> None:
        self.article = article
        self.svg_spec = svg_spec
        self.calls: list[dict] = []

    def complete(self, *, stage, key, system, user, max_tokens=None, temperature=0.0, images=None):
        self.calls.append(
            {
                "stage": stage,
                "key": key,
                "system": system,
                "user": user,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        text = self.svg_spec if stage.endswith("_svg_spec") and self.svg_spec else self.article
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.provider,
            usage=LLMUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            latency_ms=1,
            finish_reason="stop",
        )


def _content_dir(tmp_path: Path) -> Path:
    content_dir = tmp_path / "content"
    figures = content_dir / "figures"
    figures.mkdir(parents=True)
    (content_dir / "content.md").write_text(
        "这件事的完整内容。图示 1：一张表；图：figures/fig-01.jpg\n",
        encoding="utf-8",
    )
    (figures / "fig-01.jpg").write_bytes(b"fake-jpeg")
    return content_dir


def _source_json(tmp_path: Path) -> Path:
    path = tmp_path / "source.json"
    path.write_text(
        json.dumps(
            {"title": "示例视频", "uploader": "示例 UP"} ,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_extract_title_candidates_removes_comment() -> None:
    text = "# 标题\n\n正文。\n\n<!-- title_candidates: 候选一；候选二；候选三 -->\n"
    cleaned, candidates = extract_title_candidates(text)
    assert candidates == ["候选一", "候选二", "候选三"]
    assert "title_candidates" not in cleaned
    assert "# 标题" in cleaned


def test_title_candidates_preserve_decimal_prefix() -> None:
    text = "<!-- title_candidates: 0.8 的门槛；1. 第二个候选 -->"
    _, candidates = extract_title_candidates(text)
    assert candidates == ["0.8 的门槛", "第二个候选"]


def test_title_candidates_accept_slash_separator() -> None:
    text = "<!-- title_candidates: 候选一 / 候选二 / 候选三 -->"
    _, candidates = extract_title_candidates(text)
    assert candidates == ["候选一", "候选二", "候选三"]


def test_figure_refs_include_sidecar_paths() -> None:
    article = (
        "![图](figures/fig-01.jpg)\n\n## 配图\n"
        "- figures/fig-02.jpg：看这里\n- figures/fig-01.jpg：重复\n"
    )
    assert figure_refs(article) == ["figures/fig-01.jpg", "figures/fig-02.jpg"]


def test_extract_reader_contract_removes_comment() -> None:
    text = (
        "# 标题\n\n正文。\n\n"
        '<!-- reader_contract: {"must_ground": ["embedding"], '
        '"title_promise": "为什么分数低"} -->\n'
    )
    cleaned, contract, raw = extract_reader_contract(text)
    assert "reader_contract" not in cleaned
    assert contract == {
        "must_ground": ["embedding"],
        "title_promise": "为什么分数低",
    }
    assert raw


def test_extract_reader_contract_keeps_invalid_raw() -> None:
    text = "# 标题\n\n正文。\n\n<!-- reader_contract: not json -->\n"
    cleaned, contract, raw = extract_reader_contract(text)
    assert "reader_contract" not in cleaned
    assert contract is None
    assert raw == "not json"


def test_ensure_source_line_is_not_duplicated() -> None:
    article = "# 标题\n\n正文。\n\n---\n\n本文根据 B 站视频《示例》整理；画面截取自原视频。\n"
    same = ensure_source_line(
        article,
        data_root=Path("data"),
        video_id="BV1",
        source_path=None,
    )
    assert same == article


def test_write_form_copies_figures_and_writes_meta(tmp_path: Path) -> None:
    content_dir = _content_dir(tmp_path)
    source = _source_json(tmp_path)
    out_dir = tmp_path / "out"
    article = (
        "# 标题\n\n正文。\n\n![看这张表](figures/fig-01.jpg)\n\n"
        '<!-- reader_contract: {"must_ground": ["embedding"], '
        '"title_promise": "标题"} -->\n'
        "<!-- title_candidates: 候选一；候选二 -->\n"
    )
    client = FakeLLM(article=article)

    result = write_form(
        video_id="BV1",
        content_path=content_dir / "content.md",
        out_dir=out_dir,
        skill_dir=WECHAT,
        request="写给新手看",
        source_json=source,
        client=client,
        settings=SimpleNamespace(data_root=tmp_path / "data"),
    )

    assert result.form == "wechat_article"
    assert result.status == "complete"
    assert result.title_candidates == ["候选一", "候选二"]
    assert result.reader_contract == {
        "must_ground": ["embedding"],
        "title_promise": "标题",
    }
    assert (out_dir / "figures" / "fig-01.jpg").exists()
    assert (out_dir / "reader_contract.json").exists()
    text = (out_dir / "article.md").read_text(encoding="utf-8")
    assert "title_candidates" not in text
    assert "reader_contract" not in text
    assert "本文根据 B 站视频《示例视频》（UP 主：示例 UP）整理" in text
    assert result.missing_figures == []
    meta = json.loads((out_dir / "response_meta.json").read_text(encoding="utf-8"))
    assert meta["form"] == "wechat_article"
    assert meta["content"]["sha256"]
    assert meta["title_candidates"] == ["候选一", "候选二"]
    assert meta["reader_contract"] == {
        "must_ground": ["embedding"],
        "title_promise": "标题",
    }
    # one writer call; no editor/checker
    assert [call["stage"] for call in client.calls] == ["write_wechat_article"]


def test_write_form_renders_svg_placeholder(tmp_path: Path) -> None:
    content_dir = _content_dir(tmp_path)
    source = _source_json(tmp_path)
    out_dir = tmp_path / "out"
    article = (
        "# 标题\n\n正文。\n\n<!-- svg: 三步依赖：A → B → C -->\n\n结尾。\n"
    )
    spec = json.dumps(
        {
            "kind": "flow",
            "title": "三步依赖",
            "items": [
                {"label": "A", "detail": ""},
                {"label": "B", "detail": ""},
                {"label": "C", "detail": ""},
            ],
            "caption": "三步依赖",
        },
        ensure_ascii=False,
    )
    client = FakeLLM(article=article, svg_spec=spec)

    result = write_form(
        video_id="BV1",
        content_path=content_dir / "content.md",
        out_dir=out_dir,
        skill_dir=WECHAT,
        source_json=source,
        client=client,
        settings=SimpleNamespace(data_root=tmp_path / "data"),
    )

    assert result.svg_assets == ["svg-01.svg"]
    assert (out_dir / "figures" / "svg-01.svg").exists()
    text = (out_dir / "article.md").read_text(encoding="utf-8")
    assert "figures/svg-01.svg" in text
    assert "<!-- svg:" not in text
    assert (out_dir / "svg_report.md").exists()
    assert [call["stage"] for call in client.calls] == [
        "write_wechat_article",
        "BV1:wechat_article_svg_spec",
    ]


def test_write_form_reports_missing_figure(tmp_path: Path) -> None:
    content_dir = _content_dir(tmp_path)
    source = _source_json(tmp_path)
    out_dir = tmp_path / "out"
    article = "# 标题\n\n正文。\n\n![不存在](figures/nope.jpg)\n"
    client = FakeLLM(article=article)

    result = write_form(
        video_id="BV1",
        content_path=content_dir / "content.md",
        out_dir=out_dir,
        skill_dir=WECHAT,
        source_json=source,
        client=client,
        settings=SimpleNamespace(data_root=tmp_path / "data"),
    )

    assert result.missing_figures == ["figures/nope.jpg"]
    assert (out_dir / "article.md").exists()
