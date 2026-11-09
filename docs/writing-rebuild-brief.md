# Writing layer brief（2026-11-04）

> **2026-11-06 产品层重定义**：产品 v1 是**聊天式内容工作台**（用户给视频 + 写作要求，Agent 按需写一种形态，聊天内预览/修改/验收），见 [product-v1-chat-studio.md](product-v1-chat-studio.md)；目标架构见 [architecture.md](../architecture.md)；JD/评测口径见 [jd-mapping-2026-11.md](jd-mapping-2026-11.md)。**§2（什么是好 writing）和 §3（开发纪律）仍然是保留的方法/纪律，不要改。** 本文件其余章节是历史规划/旧 pipeline（§1/§4–§8），不是当前实现。bundle 是内部/调试产物，不是产品默认输出。

> **2026-11-05 session 2**：**§2（什么是好 writing）和 §3（开发纪律）是保留的方法/纪律，不要改。** 本文件其余章节是历史规划/旧 pipeline（§1/§4–§8），不是当前实现。当前写作引擎见 [writing-v5-architecture.md](writing-v5-architecture.md)。旧 supervisor/demo/词表/P1 两段式已删除；`wechat-article` 旧稿被否。

> 读者：接手写作层的新 session。
> 开发纪律见 §3；两份读者标准是内部评测材料，不随公开仓库发布。
> 旧写作层（brief/verifier/repair/polish/source line/claim status + skill v1/v2）已归档；不要按旧链做，不要读旧 memo/runs/skill/judge。

## 1. 我们在做什么

把一条视频的连续证据，写成一篇没看过视频的读者也能获得≈同等理解与体验的独立文章。

当前阶段：**一个写作 skill 已经做到质量稳定、能拿出手**；3 篇可发布文章已经形成 articles-only 作品集。下一步不是预设的“继续加 stage”，也不是预设的“先 JD”或“先多 skill”；先认知，再判断。

> 2026-11-05：上一轮 P1 社媒/编排实验（social-core、social-note、wechat-article、orchestrator 等）**不是基线**，可能整体重做。当前实现见 [writing-v5-architecture.md](writing-v5-architecture.md)。

## 2. 什么是好 writing

完整标准是内部评测材料，不随公开仓库发布。最低共识：

- 五层：Readable → Comprehensible → Value → Engagement → Shareable。
- 12 维；知识准确性是红线。P5 是质量红线概念（重大事实错误/严重误导/未证实关键能力写成已证实），不是要求你组织 30 份 subagent 评审。
- 一个控制性 idea、一条机制/论证链、具体例子/演示/画面/数字、诚实边界、自然入口/下一步。
- 不是章节笔记、coverage dump、术语表、论文、百科、正确废话。
- 默认读者是 smart general reader with some technical baseline；`reader_profile` 注入时服从。
- judge 是模型评审，不是真人；不能写成 reader pass。用户 manual acceptance 是发布门。

## 3. 开发纪律

- **证据优先**：视频事实/数字/引语/说话人只来自 substrate evidence；模型知识只解释/类比/组织。
- **写作层只保证“视频有就写，没有就不写”**：这是对视频内容的忠实，不是核实世界。视频说假设/单次演示，保留 scope；视频说 X，不要升级成“官方/已证实”。
- **核实与正文绝对分离**：“未证实”不是写作层的事。正文不写“视频称/未核实/待核”，不写成体检报告/论文/百科。验证/审计只能放在正文之外，或作为独立质量门。
- **主语是内容，不是视频**：默认直接陈述；不要写“作者说/视频里/据内容介绍”，除非需要区分个人经验、主观判断或具体演示。出处只做正文外一行。
- **Writer 是产品，检查是地板**：先写得好；不要用 validator、词表、规则怪谈、多 stage 去“保证”质量。
- **只对写作逻辑负责**：写作层负责组织、表达、结构、范围、文风；不核实世界、不给素材挑毛病、不把源材料冲突写成纠错清单。允许围绕原文语义/结构做补充、重写、修饰、精简；不新增事实/机制/因果。
- **Skill 优先**：角色/读者/方法/例子/self-review；规则少、例子多。
- **严禁单例**：skill/文档/代码里不能出现某个视频/产品/人物的具体内容、标题、台词、claim；每条规则必须由 ≥2 视频/文体或通用写作原则支持。例子匿名。
- ≥2 视频/文体才进通用层；不按单篇调参；不手改单篇文章。
- 先测后调；同 request + 盲评；不用“测试通过”代替读者质量。
- 失败/partial/unknown 显式；不静默截断；不自动发布；不伪造 reader test/A-B。
- trace/成本/状态可查；旧 artifact 冻结；可 replay。
- 有界：一次修复；不做无限“再修一轮看看”。

## 4. 架构一屏

```text
substrate v1（冻结）
  视频 → units / sentences / passages → content.md + figures/ + source metadata
        │
        ▼
写作层 v4
  SKILL + 一次 writer → 文章草稿
        → 有界 consistency review/edit
        → SVG pass（占位符 → JSON 规格 → 本地确定性渲染）
        → 地板检查
        │
        ▼
交付层
  历史 articles-only 作品集（不随公开仓库发布）
```

- substrate v1 在 `src/facet_studio/writing_v3/` 的 substrate 链路；只读 substrate 相关文件，不要读同目录的旧写作实验。writing 层通过既有接口消费，不改 substrate。需要接口时只读 `docs/substrate-v1-freeze.md` 的相关部分。
- 写作层代码在 `src/facet_studio/writing_v4/`；skill 在 `skills/writing/video-article/`。
- 当前通路：`pipeline.py` = writer → consistency → SVG → checks。
- 质量门独立于正文；不要把评审语言写进文章。
- 判断下一步看 `architecture.md` 的机会地图：§6.5 多文体矩阵、§11 多文体产出、§13.1 JD 映射、§14 复用；§4.2–4.3、§6.3.1、§7–§10 是旧实现，不要当当前代码。

## 5. 项目与 agent skill：本质区别与重叠

- Agent skill 是程序性知识包：角色、读者模型、方法、示例、渐进披露、self-review。
- 本项目多一层 substrate：视频 → 连续内容稿 + figures + metadata。写作 skill 消费它，但不复制 substrate、证据校验、渲染、发布。
- 重叠部分直接借：写作方法、读者模型、例子组织、自审问题、格式判断。
- 区别部分不要混：skill 只负责“怎么写好”，不负责“怎么证明视频是真的”。
- **能复用就复用**：先看本地 `参考素材/skills/`、`skills/`、`bilibili-render-pdf`；需要时再调研 GitHub 开源项目或知识文档。借逻辑不抄文本，复用前查 license，不把仓库示例当本项目事实，不运行不可信脚本。
- 本地参考多是 skill；不要把“再写一个写作方法论”当默认答案。

## 6. 当前方法（已经跑通的部分）

- **素材/写作分离**：素材层出 `content.md` + `figures/`，去掉标题/UP 主/时长/链接/时间码/ID/帧号/出处；Writer 只读内容稿，不知道视频/素材包/管线。
- **直接陈述**：默认写“清洁是……”，不写“作者说清洁是……”。个人经验用“一个案例/一次观察/这个演示”，不用“作者”作过渡。
- **证据范围**：一个案例/一次演示/一个预测保持一个；不升级成“所有人/一定/从来”。标题/小标题/开头与正文同 scope。
- **一致性 pass**：先 review 列 Must fix（数字/步骤/条件/结论、标题/表格/正文/例子、标题承诺/核心价值位置、动作字面矛盾、默认/可选反转、术语、分类层数、工作痕迹、视觉缺口），再按 fix list 做最小 edit；不做外部核查、不加安全/百科内容、不改观点/结构。
- **SVG 通路**：writer/editor 只留 `<!-- svg: ... -->`；模型返回图表 JSON 规格（只支持 flow/tree/timeline），本地确定性渲染；模型不写 SVG；每篇 0–2 张，按结构需要；统计/对比/关系用 Markdown 表格或正文，未知 kind 直接跳过；有真实图就不画。
- **地板**：`article_checks.py` 检查泄漏词/时间码/图片路径/标题/来源行；不是质量门。
- **来源行**：review 前剥离、edit 后原样接回；正文不把它当工作痕迹删掉。

## 7. 现在做到哪 / 已知边界

- 一个 skill `skills/writing/video-article/` 已做到质量稳定；3 篇可发布文章：教程 / 技术解释 / 知识 / 文化。
- 历史 articles-only 作品集（不随公开仓库发布）没有架构、评分、HOLD、官方 30 证据。
- 全 suite 542 passed；3 篇地板检查全过；正文“作者”0 次。
- **还不是 demo-ready**：排版、字体、图片大小、PDF 文本层、移动端阅读等展示层还需要后续调整。
- 帧 caption 主要是 OCR，纯文本 writer 不描述没看到的画面；没有 VLM；没有真人 reader test。
- 历史 30 份结果是模型评审，不是真人通过；3 篇 HOLD 不发布。

## 8. 不要做

- **不要再跑 5 persona × N 篇的 30 份 subagent 评审**：太贵，收益递减。需要外部视角时，做小规模、针对性的单 persona 抽查，或先跑确定性地板检查。
- 不读旧写作层 memo/runs/skill/judge；不读 `docs/writing-operating-model.md`、`docs/writing-layer-*.md` 等旧设计笔记；不照着旧 30-judge 问题改。
- 不加 validator/agent/stage/词表来“保证”质量；不把文章写成论文/百科/体检报告。
- 不把某个视频/产品/人物写进 skill；不按单篇调参；不手改单篇来“证明”方法有效。
- 不为了“结构清晰”把内容切成孤立 claim/表格/小节；关系、连续性、上下文是写作的一部分。
- 不伪造事实/数字/引语/说话人；不自动发布；不 commit/push 到用户没让你动的分支；不读 `data/cookies/`。
- 不静默改 substrate/架构；发现真实阻塞先报告。

## 9. 下一步怎么判断（2026-11-06 已定产品方向）

**产品方向已由用户裁决**：聊天式内容工作台（LibreChat + MCP + LangGraph + 排版/导出），按需一种形态；见 [product-v1-chat-studio.md](product-v1-chat-studio.md) 和 [architecture.md](../architecture.md)。本文件 §9 不再作为方向来源。

判断任何下一步时：

- 先看它是否服务“用户在聊天里舒服地生成/预览/修改/验收”；
- 再看它是否有真实 consumer（不是为 JD 关键词造 demo）；
- 再看它是否破坏“一个产物一次 writer / 不按单篇调参”；
- 评测先预留，产品原型稳定后再做；不要用“跑通”代替质量。

每个方向写：为什么、最小下一步、验收标准、需要几个 case 才能说明不是单例。不要直接开做；先让用户裁决。
