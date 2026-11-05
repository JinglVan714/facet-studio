"""Run the video-article skill once against a material packet.

This is deliberately a single writer call, not a pipeline.  The skill is the
product; quote hygiene / fact binding are floor checks that can run afterwards.

Usage:
    PYTHONPATH=src python -m lunograph.writing_v4.run \
        --video-id <video-id> \
        --packet runs/<run>/<video-id>/material.md \
        --out-dir runs/<run>/<video-id>
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from ..core.config import get_settings
from ..providers.llm import DeepSeekLLM


DEFAULT_SKILL = Path("skills/writing/video-article/SKILL.md")
DEFAULT_EXAMPLES = Path("skills/writing/video-article/references/examples.md")

USER_TEMPLATE = """请按上面的 skill 写一篇文章。

要求：
- 只输出文章正文，不要输出分析、自审、JSON、出处。
- 内容稿，以及写作请求中明确提供的真实补充，是事实源；没有的事实、数字、引语、图示细节不要写。
- 模型记忆/常识只能组织语言和改写，不能补事实、机制或因果。
- 正文里不要出现“内容稿/素材/原文/转写/视频/UP 主”。
- 写完后先做一次一致性回读：数字/步骤/标题/表格/例子/结论是否对得上；内容有冲突时选一个口径或省略。
- 术语可以用一句最小解释帮助理解，但不要展开成百科。
- 如果使用图示，使用内容稿里给出的图示路径。

写作请求：
{request}

内容稿：

{packet}
"""


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _ensure_source_line(
    article: str,
    *,
    data_root: Path,
    video_id: str,
    source_path: Path | None = None,
) -> str:
    """Append the one-line source if the writer omitted it."""
    tail = [line.strip() for line in article.splitlines() if line.strip()][-3:]
    if any("本文根据" in line for line in tail):
        return article
    source_file = source_path or data_root / video_id / "source.json"
    if not source_file.exists():
        return article
    source = json.loads(source_file.read_text(encoding="utf-8-sig"))
    title = str(source.get("title") or video_id)
    uploader = str(source.get("uploader") or "")
    if title == video_id or (not uploader and title.startswith("BV")):
        line = f"本文根据 B 站视频（{title}）整理；画面截取自原视频。"
    else:
        line = (
            f"本文根据 B 站视频《{title}》（UP 主：{uploader}）"
            "整理；画面截取自原视频。"
        )
    return article.rstrip() + "\n\n---\n\n" + line + "\n"


def _rewrite_images(article: str, run_dir: Path, repo_root: Path) -> str:
    """Copy referenced data/ images into the run's assets/ and rewrite paths."""
    assets = run_dir / "assets"
    pattern = re.compile(r"(!\[[^\]]*\]\()([^)]+)(\))")

    def replace(match: re.Match[str]) -> str:
        prefix, target, suffix = match.groups()
        target = target.strip()
        if not target.startswith("data/"):
            return match.group(0)
        source = repo_root / target
        if not source.exists():
            return match.group(0)
        assets.mkdir(parents=True, exist_ok=True)
        name = source.name
        destination = assets / name
        if not destination.exists():
            shutil.copy2(source, destination)
        return f"{prefix}assets/{name}{suffix}"

    return pattern.sub(replace, article)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the video-article skill once.")
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--skill", type=Path, default=DEFAULT_SKILL)
    parser.add_argument("--examples", type=Path, default=DEFAULT_EXAMPLES)
    parser.add_argument("--request", default="")
    parser.add_argument("--request-file", type=Path, default=None)
    parser.add_argument("--source-json", type=Path, default=None)
    parser.add_argument("--temperature", type=float, default=0.4)
    parser.add_argument("--max-tokens", type=int, default=65536)
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.provider_configured:
        raise SystemExit("provider not configured (DEEPSEEK_API_KEY / DEEPSEEK_MODEL)")

    request = args.request
    if args.request_file is not None:
        request = args.request_file.read_text(encoding="utf-8").strip()

    skill = _read(args.skill)
    examples = _read(args.examples) if args.examples.exists() else ""
    system = f"{skill}\n\n---\n\n# 例子参考\n\n{examples}"
    user = USER_TEMPLATE.format(
        request=request or "（未指定；按 skill 默认读者）",
        packet=_read(args.packet),
    )

    client = DeepSeekLLM(settings)
    response = client.complete(
        stage="writing_v4",
        key=args.video_id,
        system=system,
        user=user,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
    )
    if not response.text.strip():
        raise SystemExit(f"empty response ({response.finish_reason})")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    article = _ensure_source_line(
        response.text.strip() + "\n",
        data_root=settings.data_root,
        video_id=args.video_id,
        source_path=args.source_json,
    )
    article = _rewrite_images(article, args.out_dir, settings.project_root)
    (args.out_dir / "article.md").write_text(article, encoding="utf-8")
    meta = {
        "video_id": args.video_id,
        "model": response.model,
        "provider": response.provider,
        "finish_reason": response.finish_reason,
        "latency_ms": response.latency_ms,
        "usage": response.usage.as_dict(),
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "packet": str(args.packet),
        "skill": str(args.skill),
        "article_chars": len(article),
    }
    (args.out_dir / "response_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
