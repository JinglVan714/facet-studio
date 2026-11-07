import json
from pathlib import Path
from types import SimpleNamespace

from facet_studio.providers.llm import LLMResponse, LLMUsage
from facet_studio.writing_v4.orchestrator import run_bundle

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills" / "writing"


def _plan_text() -> str:
    return json.dumps(
        {
            "central_idea": "先理解反常识，再按三步做对。",
            "reader_goal": "读完能说出为什么旧做法不对，并知道按什么顺序做。",
            "forms": [
                {
                    "form": "wechat_article",
                    "reason": "有完整机制",
                    "angle": "从反常识切入",
                    "brief": "先给反常识，再讲机制和边界。",
                    "must_use_figures": ["fig-01.jpg"],
                },
                {
                    "form": "xiaohongshu_note",
                    "reason": "有一个能上手的动作",
                    "angle": "只保留最反直觉的动作",
                    "brief": "一条主线覆盖整体。",
                    "must_use_figures": [],
                },
            ],
            "shared_constraints": ["同一组数字和范围", "角度不同"],
        },
        ensure_ascii=False,
    )


ARTICLES = {
    "write_wechat_article": (
        "# 公众号标题\n\n正文。\n\n![图](figures/fig-01.jpg)\n\n"
        '<!-- reader_contract: {"must_ground": ["概念"], '
        '"title_promise": "公众号标题"} -->\n'
        "<!-- title_candidates: 候选一；候选二 -->\n"
    ),
    "write_xiaohongshu_note": (
        '<!-- reader_contract: {"must_ground": ["动作"], '
        '"title_promise": "笔记标题"} -->\n'
        "# 笔记标题\n\n> 封面：一句话\n\n正文。\n\n"
        "## 配图\n- figures/fig-01.jpg：看这里\n\n"
        "## 标签\n#标签1 #标签2\n"
    ),
}


class FakeLLM:
    provider = "fake"
    model = "fake-model"

    def __init__(self, *, fail_stage: str | None = None):
        self.fail_stage = fail_stage
        self.call_sink = None
        self._count = 0

    def complete(self, *, stage, key, system, user, max_tokens=None, temperature=0.0, images=None):
        self._count += 1
        if self.call_sink is not None:
            self.call_sink(
                {
                    "call_id": f"call_{self._count}",
                    "stage": stage,
                    "key": key,
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 20,
                        "total_tokens": 30,
                    },
                    "latency_ms": 1,
                }
            )
        if self.fail_stage == stage:
            raise RuntimeError("fake writer failure")
        text = _plan_text() if stage == "bundle_plan" else ARTICLES.get(
            stage, "# 标题\n\n正文。\n"
        )
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.provider,
            usage=LLMUsage(prompt_tokens=10, completion_tokens=20, total_tokens=30),
            latency_ms=1,
            finish_reason="stop",
        )


def _fixtures(tmp_path: Path):
    content_dir = tmp_path / "content"
    figures = content_dir / "figures"
    figures.mkdir(parents=True)
    (content_dir / "content.md").write_text(
        "这件事的完整内容。\n\n（图示 1：一张表；图：figures/fig-01.jpg）\n",
        encoding="utf-8",
    )
    (figures / "fig-01.jpg").write_bytes(b"fake-jpeg")
    source_dir = tmp_path / "data" / "BV1"
    source_dir.mkdir(parents=True)
    source = source_dir / "source.json"
    source.write_text(
        json.dumps({"title": "示例视频", "uploader": "示例 UP"}, ensure_ascii=False),
        encoding="utf-8",
    )
    settings = SimpleNamespace(
        data_root=tmp_path / "data",
        skills_root=ROOT / "skills",
        provider_configured=True,
    )
    return content_dir, source, settings


def test_run_bundle_complete(tmp_path: Path) -> None:
    content_dir, source, settings = _fixtures(tmp_path)
    client = FakeLLM()
    result = run_bundle(
        video_id="BV1",
        content_path=content_dir / "content.md",
        out_root=tmp_path / "runs",
        request="生成公众号和小红书",
        required_forms=["wechat_article", "xiaohongshu_note"],
        source_json=source,
        client=client,
        settings=settings,
        concurrency=2,
        run_id="bundle_test",
    )

    assert result.status == "complete"
    run = result.run_dir
    for name in (
        "bundle.md",
        "bundle_manifest.json",
        "lead_plan.json",
        "task_plan.json",
        "semantic_memory.json",
        "working_memory.json",
        "artifact_board.json",
        "llm_calls.jsonl",
        "tool_calls.jsonl",
        "decision_records.jsonl",
    ):
        assert (run / name).exists(), name

    assert (run / "wechat_article" / "article.md").exists()
    assert (run / "xiaohongshu_note" / "note.md").exists()
    assert (run / "wechat_article" / "reader_contract.json").exists()
    assert (run / "xiaohongshu_note" / "reader_contract.json").exists()
    assert (run / "wechat_article" / "inspect.json").exists()
    assert (run / "xiaohongshu_note" / "inspect.json").exists()

    manifest = json.loads((run / "bundle_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete"
    assert {item["form"] for item in manifest["forms"]} == {
        "wechat_article",
        "xiaohongshu_note",
    }

    llm_rows = [
        json.loads(line)
        for line in (run / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stages = {row["stage"] for row in llm_rows}
    assert {"bundle_plan", "write_wechat_article", "write_xiaohongshu_note"} <= stages

    tool_rows = [
        json.loads(line)
        for line in (run / "tool_calls.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(tool_rows) >= 4

    decision_rows = [
        json.loads(line)
        for line in (run / "decision_records.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(decision_rows) >= 3

    task_plan = json.loads((run / "task_plan.json").read_text(encoding="utf-8"))
    node_ids = {node["task_id"] for node in task_plan["nodes"]}
    assert {
        "compile_content",
        "lead_plan",
        "write_wechat_article",
        "inspect_wechat_article",
        "write_xiaohongshu_note",
        "inspect_xiaohongshu_note",
        "assemble_bundle",
    } <= node_ids

    bundle = (run / "bundle.md").read_text(encoding="utf-8")
    assert "wechat_article/article.md" in bundle
    assert "xiaohongshu_note/note.md" in bundle


def test_run_bundle_partial_when_one_writer_fails(tmp_path: Path) -> None:
    content_dir, source, settings = _fixtures(tmp_path)
    client = FakeLLM(fail_stage="write_xiaohongshu_note")
    result = run_bundle(
        video_id="BV1",
        content_path=content_dir / "content.md",
        out_root=tmp_path / "runs",
        request="生成公众号和小红书",
        required_forms=["wechat_article", "xiaohongshu_note"],
        source_json=source,
        client=client,
        settings=settings,
        concurrency=2,
        run_id="bundle_partial",
    )

    assert result.status == "partial"
    by_form = {item.form: item for item in result.forms}
    assert by_form["wechat_article"].status == "complete"
    assert by_form["xiaohongshu_note"].status == "failed"
    assert by_form["xiaohongshu_note"].error
    manifest = json.loads(
        (result.run_dir / "bundle_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "partial"
    assert (result.run_dir / "wechat_article" / "article.md").exists()
    assert (result.run_dir / "xiaohongshu_note" / "inspect.json").exists()
