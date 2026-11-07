"""Blind advisory A/B comparison for two articles of the same video.

This is not the project's quality gate.  It is a quick internal signal: the
two articles are shown anonymously, with a compact rubric derived from the
reader-pack standards.  The user runs the real 30-judge evaluation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..core.config import get_settings
from ..providers.llm import DeepSeekLLM


SYSTEM = """你是 AI Writing 的盲评审稿人。你会看到同一视频的两篇文章 A 和 B。
不要猜它们分别由什么输入/流程产生，只评文章本身。

按 1-5 分评以下维度：
1. 可读性：自然、流畅、不费劲。
2. 可理解性：概念讲清楚，读者能真正理解。
3. 认知增量：读完学到东西，不只是信息搬运。
4. 吸引力：开头和全文让人愿意读下去。
5. 叙事与表达：有主线、有具体例子/画面、有记忆点。
6. 可信度：事实/边界/口吻可信，不夸大。
7. 传播性：有值得收藏/转发的核心。
8. 行动引导：读者知道下一步能做什么。
9. 反 AI 味：不模板化、不空话、不八股。

只输出 JSON：
{
  "A": {"可读性": n, "可理解性": n, "认知增量": n, "吸引力": n, "叙事与表达": n, "可信度": n, "传播性": n, "行动引导": n, "反AI味": n},
  "B": {...},
  "winner": "A" | "B" | "tie",
  "reason": "一句话说明关键差异",
  "A_weakness": "一句话",
  "B_weakness": "一句话"
}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Blind advisory A/B judge.")
    parser.add_argument("--article-a", type=Path, required=True)
    parser.add_argument("--article-b", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.provider_configured:
        raise SystemExit("provider not configured")

    a = args.article_a.read_text(encoding="utf-8")
    b = args.article_b.read_text(encoding="utf-8")
    user = (
        "文章 A：\n\n"
        + a
        + "\n\n---\n\n文章 B：\n\n"
        + b
        + "\n\n请按 rubric 输出 JSON，不要输出别的。"
    )

    client = DeepSeekLLM(settings)
    response = client.complete(
        stage="writing_v4_ab_judge",
        key=str(args.out),
        system=SYSTEM,
        user=user,
        max_tokens=4096,
        temperature=0.0,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(response.text.strip() + "\n", encoding="utf-8")
    print(response.text.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
