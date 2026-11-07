# 新 session 启动：先认知，再决定（2026-11-04）

你接手的是 Facet Studio 的写作层。当前不是“从零重做”，也不是“继续修旧链”：一个写作 skill 已经做到质量稳定、能拿出手；下一步做什么，需要你先认知，再自己判断。

**先不要改代码，也不要预设“先 JD”或“先多 skill”。** 读完之后，给出你看到的 2–3 个方向、依据和最小下一步，再让用户裁决。

## 只读这些（按顺序，不要多读）

1. 本文件。
2. `docs/writing-rebuild-brief.md` 的 §2（什么是好 writing）和 §3（开发纪律）。其余章节按需查。
3. `AGENTS.md` 的全局护栏。
4. `architecture.md`：先看 §0.1 阅读地图。判断下一步必须看机会地图：§1（产品定义）、§6.5（多文体矩阵）、§11（多文体产出）、§13.1（JD 映射）、§14（复用）；架构分层看 §4.1，substrate 看 §5/§12。§4.2–4.3、§6.3.1、§7–§10 是旧实现，不要当当前代码；当前写作层看 brief §4。不要通读 1000 行，但也不要跳过 §11/§13。
5. `STATE.md` + `HANDOFF.md` 的当前快照；最后再打开 `deliverables/writing-skill/site/index.html` 看一眼现在做成了什么样，不要逐行读。
6. 需要评测时，再看两份只读标准：`runs/_reader_test_2026-11-03/reader_pack/评价方法.md`、`5个persona.md`。不要一开始就读。

**不要读**：旧写作层的 `DIAGNOSTIC_MEMO.md`、`PIPELINE_IO_AUDIT.md`、`DISCIPLINE_AUDIT.md`、旧 `runs/_diag/*`、旧 `skills/writing/reader_first_explainer/`、旧 judge `problems.md`/`summary.md`、`docs/writing-operating-model.md`、`docs/writing-layer-*.md`、`docs/writing-skill-study.md`、`docs/writing-planner-position.md`。这些会把你带回“brief/claim/verifier/repair/polish”的旧框架。

## 1. 什么是好 writing（先建立判断）

完整标准在 brief §2；最低共识：

- 五层：Readable → Comprehensible → Value → Engagement → Shareable。
- 一篇文章要有一个控制性 idea、一条机制/论证链、具体例子/演示/画面/数字、诚实的边界、自然的入口和下一步。
- 读者是聪明、好奇、有一点生活或技术常识的普通读者；不是 AI 初学者，也不是全知专家。
- 不是章节笔记、coverage dump、术语表、论文、百科、正确废话。
- 好文章让没看过视频的读者获得≈同等的理解与体验；不是把视频每段搬一遍。
- 质量判断以少量针对性评审 + 人工 acceptance 为主；确定性测试只是地板，不是质量评判。

## 2. 开发纪律（必须遵守）

- **证据优先**：视频事实/数字/引语/说话人只来自 substrate evidence；模型知识只用于解释、类比、组织语言，不补事实、机制、因果。
- **写作层只保证“视频有就写，没有就不写”**：这是对视频内容的忠实，不是替视频核实世界。视频说假设/单次演示，保留 scope；视频说 X，不要升级成“官方/已证实”。
- **核实与正文绝对分离**：“未证实”不是写作层该管的事。正文里不要每句“视频称/未核实”，不要写成体检报告、论文、百科；这样会没完没了。验证/审计要做，也只能放在正文之外，或作为独立的质量门。
- **主语是内容，不是视频**：默认直接陈述；不要写“作者说/视频里/据内容介绍”，除非真的需要区分个人经验、主观判断或具体演示。出处只做正文外的一行。
- **Writer 是产品，检查是地板**：先写得好；不要用 validator、词表、规则怪谈、多 stage 去“保证”质量。旧架构把 brief/claim/verifier/repair 塞进写作，正是要重做而不是小修的原因之一；别人的写作 skill 没有这套东西。
- **Skill 优先**：角色/读者/方法/例子/self-review；规则少、例子多。
- **严禁单例**：skill、文档、代码里不能出现某个视频/产品/人物的具体内容、标题、台词、claim；每条规则必须由 ≥2 视频/文体或通用写作原则支持。例子用匿名模式。不要把某一篇的修法写进通用层。
- **有界**：一次修复；不做无限“再修一轮看看”；不按单篇调参，不手改单篇文章。
- **不伪造/不自动发布/不改 substrate/不读 `data/cookies/`**；不 commit/push 到用户没让你动的分支。

## 3. 项目与 agent skill：本质区别与重叠

- Agent skill 是**程序性知识包**：角色、读者模型、方法、示例、渐进披露、self-review。
- 本项目多一层 **substrate**：视频 → units/sentences/passages → `content.md` + `figures/` + metadata。写作层消费它，但不把 substrate、证据校验、渲染、发布塞进 skill。
- 重叠部分直接借：写作方法、读者模型、例子组织、自审问题、格式判断。区别部分不要混：skill 只负责“怎么写好”，不负责“怎么证明视频是真的”。
- **能复用就复用，不造轮子**：先看本地 `参考素材/skills/`、`skills/`、`bilibili-render-pdf`；需要时再调研 GitHub 开源项目或知识文档。借逻辑不抄文本，复用前查 license，不把仓库示例当本项目事实，不运行不可信脚本。
- 多文体不是复制管线：文体差异放 Skill；`architecture.md` §6.5/§11 是机会地图，不是现成实现。
- 本地参考多是 skill；不要把“再写一个写作方法论”当成默认答案。

## 4. 架构一屏

```text
substrate v1（冻结）
  视频 → units / sentences / passages → content.md + figures/ + source metadata
        │
        ▼
写作层 v4（当前）
  SKILL + 一次 writer → 文章草稿
        → 有界 consistency review/edit（只修内部矛盾/范围/标题承诺/工作痕迹/视觉缺口）
        → SVG pass（占位符 → JSON 规格 → 本地确定性渲染；模型不写 SVG）
        → 地板检查（泄漏词/时间码/图片路径/标题/来源行）
        → 文章 + 配图
        │
        ▼
交付层
  deliverables/writing-skill/site/：只呈现文章的 HTML / PDF 作品集
```

关键边界：

- substrate v1 已冻结；非必要不改。需要接口时只读 `docs/substrate-v1-freeze.md` 的相关部分。
- 写作层代码在 `src/facet_studio/writing_v4/`；skill 在 `skills/writing/video-article/`。
- 多文体机会：`architecture.md` §6.5/§11（教程、社媒、企业知识、脚本、二创等）；是机会地图，不是现成实现。
- JD 能力：`architecture.md` §13.1（多 Agent、工具、记忆、评测、作品等）；是能力地图，不是现成实现。
- 质量门是独立于正文的评审/人工 acceptance；不要把评审语言写进文章。
- 现有 30 份评审结果是历史证据，不是要重跑的任务。

## 5. 现在做到哪（最后再看）

- 一个写作 skill 已经做到质量稳定、能拿出手：3 篇可发布文章（教程 / 技术解释 / 知识 / 文化），正文无“作者说/视频里”，地板检查全过。
- 交付包 `deliverables/writing-skill/` 已改成 articles-only 作品集：`site/index.html`、`site/writing-articles.pdf`；没有架构、评分、HOLD、官方 30 证据。
- 写作通路已打通：`pipeline.py` = writer → consistency → SVG → checks；`svg_pass.py` 的占位符/规格/渲染有单测；全 suite 542 passed。
- **还不算 demo-ready**：排版、字体、图片大小、PDF 文本层、移动端阅读等还需要后续调整；这是展示层问题，不是写作方法问题。
- 已知边界：帧 caption 主要是 OCR，纯文本 writer 不描述没看到的画面；没有 VLM；没有真人 reader test；历史 30 份结果是模型评审，不是真人通过。
- 3 篇 HOLD 不发布；不要为了凑数把 HOLD 硬发。

## 6. 不要做（红线）

- **不要再组织 5 persona × N 篇的 30 份 subagent 评审**：太贵，收益递减。需要外部视角时，做小规模、针对性的单 persona 抽查，或先跑确定性地板检查；不要用“多跑几份 judge”代替判断。
- 不要读旧写作层的 memo/runs/skill/judge，不要照着旧 30-judge 问题改。
- 不要把“未证实/待核/来源缺失”写进正文；不要把文章写成论文/百科/体检报告。
- 不要把某个视频/产品/人物写进 skill；不要按单篇调参；不要手改单篇文章来“证明”方法有效。
- 不要为了“结构清晰”把内容切成孤立 claim/表格/小节；关系、连续性、上下文是写作的一部分。
- 不要加 validator/agent/stage/词表来“保证”质量；不要用测试通过代替读者质量。
- 不要静默改 substrate/架构；发现真实阻塞先报告。

## 7. 你的第一个任务

1. 按上面的顺序读，不要先读旧结论。
2. 用 10 行以内写下你的理解：什么是好 writing、开发纪律、项目架构、当前状态。
3. 给出你看到的 2–3 个下一步方向（例如：对照 JD/岗位要求补作品集；先扩 skill 适配更多文体；先修已有展示/质量问题），每个方向写：为什么、最小下一步、验收标准、需要几个 case 才能说明不是单例。
4. 不要直接执行某个预设方向；先让用户裁决。用户可能选一个，也可能让你先做诊断。

如果要评估 JD 方向，可看 `architecture.md` §13.1 的 JD 映射；用现有作品集 + 目标岗位要求判断即可，不需要为此重跑 30 份 judge。它只是参考，不是默认路线。
