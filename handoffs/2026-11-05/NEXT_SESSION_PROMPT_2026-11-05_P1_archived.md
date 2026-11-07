# 新 session 启动：先认知，再独立判断（2026-11-05）

> **2026-11-05 晚更新**：用户决定清场。supervisor / demo / 词表 / P1 社媒与脚本 skill 已删除；当前只做公众号 one-call。先看 `STATE.md` / `HANDOFF.md`。本文下面的 P1/supervisor 方向作废，只作历史。

你接手的是 Facet Studio。上一轮做了大量工作，也做了一次 P1 多文体实验；**这些都不是基线，也不代表方向正确**。你的任务不是接着做，而是先认知项目结构、我们的思考方式和开发习惯，再独立判断“现在该做什么、JD 覆盖是否成立”。不要被上一轮的 roadmap、强决策或已有代码锚定；它们只是候选证据。

## 0. 先看 git，分清基线

```bash
git log --oneline -8
git status --short
```

- **可信基线**：`2f8faea`（上一轮开始前的 commit）。
- `2f8faea` 之后的所有代码/文档——`src/facet_studio/writing_v4/orchestrator.py`、`package.py`、`view_retriever.py`、`skills/writing/social-core/`、`social-note/`、`wechat-article/`、相关测试、roadmap——都是**实验**。可能有未发现的问题，甚至需要整体重做。
- 不要因为“已经写了/测试过了/commit 过”就默认它对。先独立读、独立判断；如果方向不成立，可以整体推翻。
- `runs/` 是本地运行产物，不是基线。

## 1. 只读顺序（不要多读）

1. 本文件。
2. `architecture.md`：先看 §0.1 阅读地图；机会地图 §1/§6.5/§11/§13.1/§14；分层 §4.1；substrate §5/§12。§4.2–4.3、§6.3.1、§7–§10 是旧实现，不要当当前代码。
3. `docs/writing-rebuild-brief.md` §2（什么是好 writing）+ §3（开发纪律）；其余按需。
4. `AGENTS.md` 全局护栏。
5. 当前成熟 skill：`skills/writing/video-article/SKILL.md` + `references/examples.md` + `references/material_prep.md`。这是目前唯一“调了很久、能拿出手”的 skill；只看最新版，不看旧版本。它的架构来自 `bilibili-render-pdf` 教学 flow；新文体可以抄这个架构改内容。
6. `STATE.md` / `HANDOFF.md` 的当前快照；注意里面的 P1 实验标记。
7. 需要时再看上一轮的提案/调研/诊断（**都不是基线，批判阅读**）：
   - `docs/multiform-roadmap.md`（上一轮方向提案 + JD 表）
   - `docs/social-writing-reuse-map.md`（调研记录）
   - `handoffs/2026-11-04/DIAGNOSTIC_JD_MULTIFORM_PRESENTATION.md`（上一轮诊断）
8. 只有需要评测时，才读 `runs/_reader_test_2026-11-03/reader_pack/评价方法.md`、`5个persona.md`。

**不要读**：旧写作层的 memo/runs/skill/judge、`docs/writing-operating-model.md`、`docs/writing-layer-*.md`、旧 `reader_first_explainer`。这些会把你带回旧框架。

## 2. 先学我们的思考方式

- **好 writing**：五层 Readable → Comprehensible → Value → Engagement → Shareable；一个控制性 idea、一条机制/论证链、具体例子/画面/数字、诚实边界、自然入口/下一步。没看过视频的读者获得≈同等理解与体验。不是章节笔记、coverage dump、术语表、论文、百科、正确废话。
- **证据优先**：视频事实/数字/引语/说话人只来自 substrate evidence；模型知识只解释、类比、组织语言。
- **写作层只保证“视频有就写，没有就不写”**：这是对视频内容的忠实，不是替视频核实世界。视频说假设/单次演示，保留 scope；视频说 X，不要升级成“官方/已证实”。
- **核实与正文绝对分离**：“未证实”不是写作层的事；正文不写“视频称/未核实/待核”，不写成体检报告/论文/百科。
- **主语是内容，不是视频**：默认直接陈述；不要写“作者说/视频里/据内容介绍”，除非真的需要区分个人经验、主观判断或具体演示。
- **Writer 是产品，检查是地板**：先写得好；不要用 validator、词表、规则怪谈、多 stage 去“保证”质量。
- **Skill 优先**：角色/读者/方法/例子/self-review；规则少、例子多。新文体先抄成熟 skill 的架构，改内容，快速迭代；不用像成熟 skill 那么严谨。
- **只对写作逻辑负责**：负责组织、表达、结构、范围、文风；不核实世界、**不给素材挑毛病**、不把源材料冲突写成纠错清单。允许围绕原文语义/结构做补充、重写、修饰、精简；不新增事实/机制/因果。
- **严禁单例**：≥2 视频/文体/结构复现才进通用层；不按单篇/单个例子调参；例子匿名；不要把某个视频/产品/人物的具体内容写进 skill。
- **有界**：一次修复；不做无限“再修一轮看看”；不按单篇调参，不手改单篇文章。

## 3. 先学我们的开发习惯

- 先想每个步骤的输入/输出：是否最有效、最清晰、最符合该阶段和整体 workflow；输出是否结构化、低摩擦、能被下一 stage 低成本消费。
- **能复用就复用**：先看本地 `参考素材/skills/`、`skills/`、`bilibili-render-pdf`，再调研 GitHub 开源项目；借逻辑不抄文本，复用前查 license，不把仓库示例当本项目事实，不运行不可信脚本。
- **架构可以抄**：成熟 `video-article` skill 的 SKILL.md/例子/references 结构可以直接拿来改；其他调研到的 skill 能抄 prompt 结构/例子组织就抄；快速迭代，不造轮子。
- **多文体不是复制管线**：文体差异放 Skill/平台层；不为每个文体加 body/validator/gate/pipeline。
- 先测后调；同 request + 盲评；不用“测试通过”代替读者质量。
- 失败/partial/unknown 显式；不静默截断；不自动发布；不伪造 reader test/A-B。
- 不 commit/push 到用户没让你动的分支；不改 substrate；不读 `data/cookies/`。

## 4. 你的任务（先回答，不要直接执行）

1. 用 **≤10 行**写下你的理解：什么是好 writing、开发纪律、项目结构、当前状态。
2. **独立列 JD 表**：`architecture.md` §13.1 的 10 行，每行写“核心业务问题 / 真实落点 / consumer / 验收 / 现状”。不能写“未覆盖”，也不能硬塞；如果某行没有真实 consumer，就说明为什么、最小怎么补。
3. **独立判断上一轮 P1 方向**：多文体/社媒优先、LeadPlan 多 Agent 编排、social-core + platform editor、ViewRetriever、md first / HTML later / PDF no / demo later——哪些成立？哪些是伪需求、过度设计、单例、或越界做了核实/挑素材毛病？给出 **2–3 个方向**，每个写：为什么、最小下一步、验收标准、需要几个 case 才能说明不是单例。
4. 不要直接开做；先让用户裁决。用户可能选一个，也可能让你先做诊断。

## 5. 当前已知事实（只作事实，不作方向）

- 成熟 skill：`skills/writing/video-article/`；3 篇可发布文章 + articles-only HTML/PDF 作品集；官方 30 历史结果为 3 CLEAR + 3 HOLD，只作参考，**不要再跑 30 份 subagent 评审**。
- 上一轮 P1 实验：`skills/writing/social-core/`、`social-note/`、`wechat-article/`、`src/facet_studio/writing_v4/orchestrator.py`、`package.py`、`view_retriever.py`；4 个草稿在 `runs/.../multiform/v2*`。**这些是实验，不是基线，可能整体重做。**
- 当前测试：全 suite 581 passed（其中 v4 55）；测试通过只是地板，不是方向正确或质量通过。
- 产出格式：md 先过关；HTML 还没具体调整；PDF 暂不做；完全体之后可做简易前后端 demo。不要现在做 PDF/展示层。

## 6. 不要做（红线）

- 不要因为上一轮 roadmap/代码/结论就默认方向正确；不要被“强决策”锚定。
- 不要读旧写作层 memo/runs/skill/judge；不要照着旧 30 judge 问题改。
- 不要再组织 5 persona × N 篇的 30 份 subagent 评审；需要外部视角时做小规模、针对性单 persona 抽查。
- 不要加 validator/agent/stage/词表来“保证”质量；不要用测试通过代替读者质量。
- 不要把“未证实/待核/来源缺失”写进正文；不要写成论文/百科/体检报告；不要给素材挑毛病。
- 不要把某个视频/产品/人物写进 skill；不要按单篇/单个例子调参；不要手改单篇文章来“证明”方法有效。
- 不要静默改 substrate/架构；发现真实阻塞先报告。
- 不自动发布；不 commit/push 到用户没让你动的分支；不读 `data/cookies/`。
