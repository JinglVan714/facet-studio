# Clean rebuild startup prompt — writing skill（2026-11-04）

你接手的是写作层的**干净重做**，不是修复旧链。旧写作层（brief/verifier/repair/polish/source line/claim status + skill v1/v2）已归档在 commit/tag `archive/writing-v1-2026-11-04`。**不要基于它改，不要读它的诊断 memo/旧 runs/旧 skill/旧 judge 结果。** 你的任务：在副本/新分支里，从零做一个写作 skill，先把一个 skill 做到产出优质、拿得出手的文章。

## 现在做什么

- 写作层只有一个目标：把一条视频的连续证据，写成一篇没看过视频的读者也能获得≈同等理解与体验的独立文章。
- **先把一个 skill 做好**：质量稳定、优质、可发布。
- 质量门是 **LLM-as-Judge 高分通过**（5 persona / 两份标准）；确定性测试（结构/数字/引号/ID）只是地板，不是质量评判。用户后续会自己重新跑 30 份 judge；**你不需要读/照着旧 30-judge 问题改**。
- 不做“先诊断旧系统”的 memo；不修旧 pipeline；不从旧错误出发。直接从“什么是好 writing + 开源参考 + 项目约束”重写。

## 只读这些（不要多读）

1. `runs/_reader_test_2026-11-03/reader_pack/评价方法.md` 全文。
2. `runs/_reader_test_2026-11-03/reader_pack/5个persona.md` 全文。
3. `docs/writing-rebuild-brief.md`（本 prompt 的详细版：好 writing、开发纪律、架构、参考、边界）。
4. 开源参考：`参考素材/skills/` + `参考素材/skills_downloaded/` 里的原始 SKILL.md/references。**直接读原始仓库，不读项目旧总结。**
5. `AGENTS.md` 的全局护栏（证据优先、不伪造、不自动发布、不单例、可观测）。
6. 需要 substrate 接口时，只读 `docs/substrate-v1-freeze.md` 的相关接口。

**不要读**：旧 `DIAGNOSTIC_MEMO.md`、`PIPELINE_IO_AUDIT.md`、`DISCIPLINE_AUDIT.md`、旧 `runs/_diag/*`、旧 `skills/writing/reader_first_explainer/`、旧 judge `problems.md`/`summary.md`、`docs/writing-operating-model.md`（已标历史）、`docs/writing-layer-*.md`、`docs/writing-skill-study.md`、`docs/writing-planner-position.md`。这些是旧上下文，读了会把你带回旧框架。

## 必须知道的认知

- **写作层只保证“视频有就写，没有就不写”。** 这是对视频内容的忠实，不是替视频核实世界。视频说假设/单次演示，保留 scope；视频说 X，不要升级成“官方/已证实”。**“未证实”不是写作层的事**；不要每句“视频称/未核实”，不要把文章写成体检报告/论文/百科。judge 的 P5 会管红线；写作层不管。
- **主语是内容，不是视频。** 模型采用并组织 substrate 里的内容来表述；它不需要“知道自己在总结视频”，也不要显式说“视频里/作者说”，除非真的需要区分观点/事实或指演示。source line 只做一行出处。
- **Writer 是产品，检查是地板。** 先写得好；不要用 validator/规则怪谈/多 stage 去“保证”质量。skill 用角色/读者/方法/例子/self-review；规则少、例子多。
- **严禁单例。** skill 里不能出现某个视频/产品/人物的具体内容、标题、台词、claim；每条规则必须由 ≥2 个视频/文体或通用写作原则支持。例子用匿名模式。
- **能复用就复用。** 开源高赞 skill 的架构/方法直接借逻辑（stop-slop 的 8 条中文 AI 味、avoid-ai-writing 的 detect/edit 与 source fidelity、wewrite 的一页 brief/claim/五项标准、mattpocock 的 grounding/beats/format arguments、doc-coauthoring 的 reader testing、bilibili-render-pdf 的教学 flow）；借逻辑不抄文本，复用前查 license。不要造轮子。
- **区分项目与 agent skill 的本质。** Agent skill 是“程序性知识包”（角色/方法/示例/渐进披露）；我们的项目多一层“视频证据 → 连续文本”的 substrate。skill 不应该复制 substrate/验证层；它只负责“怎么写好”。
- **全量重做。** 在副本/新分支里从零写 skill；旧 skill 只作为“不要这样做”的反面（最好不读）。不要改旧 pipeline 来适配新 skill；先让 skill 独立成立，再决定最小管线。

## 项目架构（一屏）

substrate v1（冻结）：视频 → units/sentences/passages → edited text + frames + source metadata。
写作层（重做中）：skill + writer → 独立文章；visual 可选；judge 是质量门。
旧写作层（brief/verifier/repair/polish/source line/claim status）已归档，不是基线。

## 交付

- 一个新的 skill 包（通用、无单例、规则少例子多、writer-first）。
- 在 2–3 个视频上跑出文章（建议 BV13/BV1ix + 一个旧 dev 做回归），证明不是单例。
- 一个简短说明：skill 的核心方法、借了哪些开源逻辑、哪些地方刻意没做（验证官僚/多 stage/单例）。
- 用户会自己跑 30 份 judge；你不用先跑，也不要照着旧 judge 问题改。

## 纪律

- 不伪造事实/数字/引语/说话人；不自动发布；不 commit/push 到用户没让你动的分支。
- 不读 `data/cookies/`；`data/`、`参考素材/` 只读。
- 先测后调；同 request 盲评；不用“测试通过”代替读者质量。
- 遇到架构冲突先报告，不静默改 substrate。
