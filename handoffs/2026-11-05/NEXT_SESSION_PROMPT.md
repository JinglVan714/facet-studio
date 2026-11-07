# 2026-11-05 交接：Facet Studio 项目快照（不是方向指令）

> 接手前先读这份快照，再自己看代码、产出和用户反馈，自己判断问题与 architecture 下一步。**不要照抄上一轮/本 session 的方向；不要因为已有代码、文档、测试、runs 就默认它对。本 session 的代码和文档也可能是错的、脏的。**

## 0. 项目是什么

- 视频 → 冻结 substrate（units/passages/claims/evidence/frames）→ 连续内容 + figures → 写作 skill → 文章/社媒/脚本。
- 目标不是“总结视频”，是让没看视频的读者获得≈同等理解与体验：一个控制性 idea、一条机制/论证链、具体例子/数字/画面、诚实边界。
- substrate v1 在 `src/facet_studio/writing_v3/`，已冻结；写作层在 `src/facet_studio/writing_v4/`。
- 分支 `writing-rebuild`；正式基线 commit `2f8faea`；**用户明确说“当前基线不是好基线”**；当前工作树有大量未提交改动；未 commit/push。

## 1. 当前快照（事实，不是质量结论）

- **相对成熟资产**：`skills/writing/video-article/` + 3 篇 `content_final_v4`（教程/技术/知识）。用户不认为当前基线是好基线；自己判断。
- **本 session 新增**：`skills/writing/wechat-article/`（one-call 公众号 skill；和已删除的 P1 同名 platform editor 不是同一个东西）+ `src/facet_studio/writing_v4/run_form.py`。
- **本 session 跑过**：BV1ix 公众号，输出 `runs/writing_rebuild_2026-11-04/wechat_step1/BV1ixpd6GENc/article.md`；**用户否决**：标题/正文槽点多、表达差、没有帧、配料/流程全塞文字、应该用 SVG 图辅助。不是通过。
- **本 session 删除（用户指令）**：supervisor/orchestrator、content_index/plan/skills/tools/replay/package/form_checks/skill_runner/article_checks、demo、P1 `social-core`/`social-note`/`wechat-article`/`video-script`、P1/v3 multiform runs、supervisor eval。
- **仍存在但可能是历史/脏的**：`reader_first_explainer`、`writing-operating-model`、`writing-layer-*`、`writing-planner-position`、`writing-skill-study`、`writing-reuse-map`、`multiform-roadmap`、`social-writing-reuse-map`、`handoffs/2026-11-04/*`、旧 runs `official_30`/`review_v2`、`deliverables/portfolio`、旧 `evals/requests`。
- **文档可能互相矛盾**：`CLAUDE`/`AGENTS`/`NEXT_SESSION`/`writing-rebuild-brief` 里旧 P1/证据核实/30 judge/checks 与新 one-writer 说法并存；`STATE`/`HANDOFF` 也可能被本 session 污染。先核对代码、产出、用户反馈，不要照单全收。

## 2. 用户明确的写作边界（本 session 听到的；仍以用户后续裁决为准）

- writer 只拿到“这件事的完整内容”，不知道这是视频/素材包/内容稿。
- 一个产物一次 writer；没有草稿阶段、editor、checker。
- 不加 skill 内词表、skill 外词表、离散规则怪谈、validator/floor gate。
- 不核实；只忠于内容想表达的意思和范围；模型知识可以优化结构/表达/概括/类比，但不加内容没有的具体事实/数字/引语/画面。
- 质量和架构由用户判断；跑通/测试绿/模型说好都不算通过。
- 一步一个环节：每步先说输入/输出/下游影响，再动手；不按单篇调参；不手改单篇文章。

## 3. 要继承的开发思路/方法

- 好 writing 五层：Readable → Comprehensible → Value → Engagement → Shareable；一个控制性 idea、一条机制/论证链、具体例子/数字/画面、诚实边界、自然入口/下一步；不是章节笔记/coverage dump/百科/正确废话。位于：D:\秋招\个人作品\1023视频写作\runs\_reader_test_2026-11-03\reader_pack\评价方法.md
- Skill 优先：角色/读者/方法/例子/self-review；规则少、例子多；不用词表/规则怪谈。
- 能复用就复用：本地 skills/参考素材/成熟 `video-article` 的架构（角色/读者/方法/形状/例子/自审）；借逻辑不抄文本；查 license；不运行不可信脚本。
- 每步先想输入/输出/下游消费；有界；失败/partial/unknown 显式；不静默截断；不自动发布。
- ≥2 视频/文体复现才进通用层；不按单篇/单例调参；例子匿名；skill 里不出现具体视频/产品/人物。
- 不读旧写作层 memo/runs/skill/judge/operating model；不跑 30 judge；不伪造 reader test/A-B；不改 substrate；不读 `data/cookies`；不 commit/push。

## 4. 不要做

- 不要照抄本 session 的 `wechat-article`/`run_form` 方向；它只是一个未通过的尝试。
- 不要恢复 supervisor/demo/词表/P1 两段式，除非你自己独立判断后用户同意。
- 不要根据本文件给“下一步做 X”的计划；下一手自己看代码、产出、用户反馈，自己列问题/方向，让用户裁决。
- 不要把 `STATE`/`HANDOFF`/`README`/本文件当干净真相；先看代码、runs、用户反馈，自己核对。

## 5. 读什么

- 先看：本文件、`STATE.md`、`HANDOFF.md`（注意可能被本 session 污染）。
- 代码：`src/facet_studio/writing_v3/`（substrate v1）、`src/facet_studio/writing_v4/`（当前写作层）、`skills/writing/video-article`、`skills/writing/wechat-article`。
- 产出：`runs/writing_rebuild_2026-11-04/wechat_step1/BV1ixpd6GENc/article.md`（被否的第一篇）；`content_final_v4`（相对成熟文章）。
- `architecture.md`：先看 §0.1；机会地图 §1/§6.5/§11/§13.1/§14；旧实现章节不要当当前代码。
- 历史：`handoffs/2026-11-04/`、`docs/multiform-roadmap.md`、`docs/social-writing-reuse-map.md`；标了非基线，仍可能带偏，批判阅读。
