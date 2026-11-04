# Writing rebuild brief（2026-11-04）

> 当前写作层是**干净重做**，不是修旧链。旧写作层（brief/verifier/repair/polish/source line/claim status + skill v1/v2）已归档在 commit/tag `archive/writing-v1-2026-11-04`；不要按旧链做，不要读旧 memo/runs/skill/judge。
> 上位：`AGENTS.md` 全局护栏；两份只读标准；开源参考原始仓库。
> 读者：接手写作层重做的新 session。

## 1. 我们在做什么

把一条视频的连续证据，写成一篇没看过视频的读者也能获得≈同等理解与体验的独立文章。**先把一个 skill 做好**：质量稳定、优质、可发布。质量门是 **LLM-as-Judge 高分通过**（5 persona × 两份标准）；确定性测试只是地板，不是质量评判。用户会自己重新跑 30 份 judge；**不要照着旧 judge 问题改**。

## 2. 什么是好 writing

读两份标准全文：

- `runs/_reader_test_2026-11-03/reader_pack/评价方法.md`
- `runs/_reader_test_2026-11-03/reader_pack/5个persona.md`

最低共识：

- 五层：Readable → Comprehensible → Value → Engagement → Shareable。
- 12 维；知识准确性是红线；P5 发现重大事实错误/严重误导/未证实关键产品能力写成已证实 → risk hold。
- 好文章：一个控制性 idea、一条机制/论证链、具体例子/演示/画面/数字、诚实边界、自然来源入口/下一步；不是章节笔记、coverage dump、百科/论文、正确废话。
- 默认读者是 smart general reader with some technical baseline；`reader_profile` 注入时服从。
- judge 是模型评审，不是真人，不能写成 reader pass；用户 manual acceptance 是发布门。

## 3. 开发纪律

- **证据优先**：视频事实/数字/引语/说话人只来自 substrate evidence；模型知识只解释/类比/组织。
- **写作层只保证“视频有就写，没有就不写”**：这是对视频内容的忠实，不是核实世界。视频说假设/单次演示，保留 scope；视频说 X，不要升级成“官方/已证实”。**“未证实”不是写作层的事**；不要每句“视频称/未核实”，不要写成体检报告/论文/百科。judge 的 P5 管红线；写作层不管。
- **主语是内容**：模型采用并组织 substrate 内容来表述；它不需要“知道自己在总结视频”，也不要显式说“视频里/作者说”，除非真的需要区分观点/事实或指演示。source line 只做一行出处。
- **Writer 是产品，检查是地板**：先写得好；不要用 validator/规则怪谈/多 stage 去“保证”质量。
- **Skill 优先**：角色/读者/方法/例子/self-review；规则少、例子多。
- **严禁单例**：skill 里不能出现某个视频/产品/人物的具体内容、标题、台词、claim；每条规则必须由 ≥2 视频/文体或通用写作原则支持。例子匿名。
- ≥2 视频/文体才进通用层；不按单篇调参；不手改 reader/claim。
- 先测后调；同 request + 盲评；不用“测试通过”代替读者质量。
- 失败/partial/unknown 显式；不静默截断；不自动发布；不伪造 reader test/A-B。
- trace/成本/状态可查；旧 artifact 冻结；可 replay。

## 4. 项目架构（一屏）

- **substrate v1（冻结）**：视频 → units/sentences/passages → edited text + frames + source metadata。writing 层通过既有接口消费，不改 substrate。
- **写作层（重做中）**：skill + writer → 独立文章；visual 可选；judge 是质量门。
- **旧写作层**（brief/verifier/repair/polish/source line/claim status）已归档，不是基线；不要修它。

## 5. 开源参考（直接读原始仓库）

- `参考素材/skills/imraywang__wewrite/.../article-brief.md`、`editorial-quality.md` + claims：一页 brief、claim type/status/boundary、五项编辑标准。
- `参考素材/skills/VincentOld__stop-slop-zh/.../SKILL.md` + `references/`：8 条中文 AI 味规则、五维“直/实/变/散/真”；借判断，不借词表/硬分数。
- `参考素材/skills/conorbronsdon__avoid-ai-writing/.../SKILL.md`：detect/edit 分离、source fidelity、protected content、two-pass ceiling；不借英文 detector 目录。
- `参考素材/skills_downloaded/anthropics__skills/skills/doc-coauthoring/SKILL.md`：context → structure → reader testing；只借方法。
- `参考素材/skills_downloaded/mattpocock__skills/.../writing-beats|writing-shape|writing-for-agents`：grounding、beats、format arguments（prose/list/table/quote）。
- `参考素材/skills/d-wwei__great-writer/`：reader stance、core tension、结构先行；不抄 6-phase。
- 本地 `bilibili-render-pdf`：教学 flow（动机→idea→机制→例子→takeaway）；不抄 LaTeX/图越多越好。
- 其余 curated：只作方法/结构参考；复用前查 license；不运行仓库脚本；不把示例当本项目事实。
- **项目 vs agent skill 的本质**：agent skill 是程序性知识包（角色/方法/示例/渐进披露）；我们的项目多一层“视频证据 → 连续文本”的 substrate。skill 不复制 substrate/验证层；它只负责“怎么写好”。重叠部分直接借逻辑，不造轮子。

## 6. 交付

- 一个新 skill 包：通用、无单例、规则少例子多、writer-first。
- 在 2–3 个视频上跑出文章（建议 BV13/BV1ix + 一个旧 dev 做回归），证明不是单例。
- 一个简短说明：核心方法、借了哪些开源逻辑、刻意没做什么（验证官僚/多 stage/单例）。
- 用户自己跑 30 份 judge；不用先跑，也不要照着旧 judge 问题改。

## 7. 不要做

- 不读旧写作层的 `DIAGNOSTIC_MEMO`/`PIPELINE_IO_AUDIT`/`DISCIPLINE_AUDIT`/旧 runs/旧 skill/旧 judge problems/旧 operating model。
- 不修旧 pipeline；不基于旧错误做诊断 memo；不按旧 30-judge 问题改。
- 不加 validator/agent/stage/词表来“保证”质量；不把文章写成论文/百科/体检报告；不每句“未核实”。
- 不把某个视频/产品/人物写进 skill；不按单篇调参。
- 不伪造事实/数字/引语/说话人；不自动发布；不 commit/push 到用户没让你动的分支；不读 `data/cookies/`。
