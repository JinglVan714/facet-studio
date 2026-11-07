"""Two-step, bounded consistency edit after the writer draft.

Borrowed logic from avoid-ai-writing (detect/edit separation, one repair entry,
preserve content) and wewrite-review (review then directly revise, bounded
rounds).  This is not a quality judge and not an external fact-checker.

Step 1: consistency review -> a short numbered fix list.
Step 2: targeted edit -> apply only that list, preserve voice/structure.

The content manuscript is the only source.  If the content itself conflicts,
the review recommends one reading or omission; the edit applies it.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from ..core.config import get_settings
from ..providers.llm import DeepSeekLLM


REVIEW_SYSTEM = """你是同一篇文章的一致性编辑。只找文章内部的矛盾，不做外部核查、不评质量、不改风格。

检查：
- 同一个数字、单位、用量、步骤、条件、结论，前后是否不一致。
- 标题/开头承诺、表格/正文、例子/结论是否对不上；标题承诺在正文有没有对应段落；标题/小节标题的范围是否大于正文。
- 分类/清单：标题或开头说“分 N 层/类/步”，正文是否真有 N 个同一维度的项；某一项如果只是另一项的属性、例外或结果，不要算作一层。
- 内容稿本身有冲突时，文章有没有写成两个口径。
- 动作/步骤有没有字面矛盾（接触/不接触、按/抛、先/后、全程/局部），或者缺一拍导致读者照着做会卡住。
- 声称的范围/结论的范围，是否大于例子或演示；例子只支持一部分，就不要写“始终/都/排名是对的”。
- 证据范围：一个案例/一次演示/一个预测，是否被写成“你会发现/所有人/一定/从来”；如果有，保留一个口径或降为可能。
- 出现“唯一/只有……一个/都/所有”时，问一句“在什么范围内”：正文后文若限定为“某个范围里/这个演示里/这套做法里”，标题、小标题和开头也必须带同样的限定词，不能只在后文补。
- 默认/可选项有没有反转：内容说默认 A、可换 B，文章有没有写成默认 B、可换 A。
- 术语是否前后不一致或明显用错。
- 核心价值是否埋在 60% 之后；如果是，建议在开头加一句预告（最小修改）。
- 正文有没有“作者说/据内容介绍/原视频/UP 主”这类工作痕迹。
- 视觉缺口（严格）：只有当一段结构性说明（3 层以上分类、3 步以上流程、分支、两把刻度不同的尺子）用文字讲会跨两段以上或需要来回对照，且没有真实图能承担时，才列为 Must fix：给出一个 `<!-- svg: 一句话描述关系 -->` 占位符，并说明插在哪一段之后；最多 2 个/篇。两项一句能说完的对比不要画图；能用真实图就不用。

只列能由内容稿判断的项；不要列外部事实、安全/医疗/法律条件、百科定义、来源链接、风格偏好、结构建议。

输出：
## Must fix
1. [类型] 原文“……” → 问题 → 修正建议（选一个口径/删除/补一句）
## 可选
...
如果没有，写“无”。
"""

EDIT_SYSTEM = """你是同一篇文章的编辑。只按给定的 Must fix 列表做最小修改。

不要加新事实、机制或结论；不要补安全/医疗/法律条件；不要补百科定义；不要改观点、结构或语气。内容稿是唯一事实源。若某条无法在现有内容内修正，跳过并在 <edits> 里注明。
Must fix 里的 SVG 占位符按原样插到指定段落之后；不要另写 SVG，不要改占位符描述。

只输出：
<edits>
- 改了什么（一句话）
</edits>
<article>
修正后的全文
</article>
"""


SOURCE_TAIL = re.compile(
    r"\n*---\s*\n+\s*(本文根据[^\n]*整理[^\n]*)\s*$"
)


def _extract(text: str, tag: str) -> str:
    match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.S)
    return match.group(1).strip() if match else ""


def split_source_line(article: str) -> tuple[str, str]:
    """Keep the editor's source line out of the body being reviewed.

    Returns (body, source_block).  The source block is appended verbatim after
    editing, so the editor cannot mistake it for a work trace or delete it.
    """
    match = SOURCE_TAIL.search(article)
    if not match:
        return article, ""
    body = article[: match.start()].rstrip() + "\n"
    block = "\n---\n\n" + match.group(1).strip() + "\n"
    return body, block


def run_consistency(
    article: str,
    content: str,
    *,
    client,  # noqa: ANN001 - provider boundary; injected for tests
    key: str,
    out_dir: Path,
    max_tokens: int = 65536,
) -> tuple[str, str, list[dict[str, int]]]:
    """Review + targeted edit, returning (article_with_source, report, usages).

    The caller owns the article file; this function only does the two model
    calls and writes the intermediate review artifacts.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    body, source_block = split_source_line(article)
    usages: list[dict[str, int]] = []

    review_user = f"内容稿：\n\n{content}\n\n---\n\n文章：\n\n{body}\n"
    review = client.complete(
        stage="writing_v4_consistency_review",
        key=key,
        system=REVIEW_SYSTEM,
        user=review_user,
        max_tokens=max_tokens,
        temperature=0.0,
    )
    usages.append(review.usage.as_dict())
    fixes_text = review.text.strip()
    (out_dir / "consistency_fixes.md").write_text(fixes_text + "\n", encoding="utf-8")

    if re.search(r"^\s*无\s*$", fixes_text, re.M) or "## Must fix\n无" in fixes_text:
        return body.rstrip() + "\n" + source_block, "无需修改的一致性项。\n", usages

    edit_user = (
        "Must fix 列表：\n\n"
        + fixes_text
        + "\n\n---\n\n内容稿：\n\n"
        + content
        + "\n\n---\n\n文章：\n\n"
        + body
        + "\n"
    )
    edited = client.complete(
        stage="writing_v4_consistency_edit",
        key=key,
        system=EDIT_SYSTEM,
        user=edit_user,
        max_tokens=max_tokens,
        temperature=0.2,
    )
    usages.append(edited.usage.as_dict())
    (out_dir / "consistency_raw.txt").write_text(edited.text, encoding="utf-8")
    fixed = _extract(edited.text, "article")
    edits = _extract(edited.text, "edits")
    if not fixed:
        raise ValueError(
            f"consistency edit returned no <article> block; raw saved to "
            f"{out_dir / 'consistency_raw.txt'}"
        )

    fixed_body, _ = split_source_line(fixed.strip() + "\n")
    report = f"## Review fixes\n\n{fixes_text}\n\n## Applied edits\n\n{edits or '（未报告）'}\n"
    return fixed_body.rstrip() + "\n" + source_block, report, usages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Two-step consistency edit.")
    parser.add_argument("--article", type=Path, required=True)
    parser.add_argument("--content", type=Path, required=True)
    parser.add_argument("--out-article", type=Path, required=True)
    parser.add_argument("--out-report", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    settings = get_settings()
    if not settings.provider_configured:
        raise SystemExit("provider not configured")

    article = args.article.read_text(encoding="utf-8")
    content = args.content.read_text(encoding="utf-8")
    out_dir = args.out_dir or args.out_article.parent
    client = DeepSeekLLM(settings)
    fixed, report, _usages = run_consistency(
        article,
        content,
        client=client,
        key=str(args.article),
        out_dir=out_dir,
    )
    args.out_article.write_text(fixed, encoding="utf-8")
    args.out_report.write_text(report, encoding="utf-8")
    print(f"wrote {args.out_article} ({len(fixed)} chars)")
    print(f"wrote {args.out_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
