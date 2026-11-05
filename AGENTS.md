# AGENTS.md — 全局规则 / 护栏

本文件是任何 agent 的防跑偏入口。**先读 [handoffs/2026-11-03/NEXT_SESSION_PROMPT.md](handoffs/2026-11-03/NEXT_SESSION_PROMPT.md)（先认知，再决定下一步），再读 [docs/writing-rebuild-brief.md](docs/writing-rebuild-brief.md)（开发方法/认知）。** 旧写作层（brief/verifier/repair/polish/source line/claim status）已归档，不是基线。

## 1. 事实源与边界

- `architecture.md` 是 v3 高层设计事实源；只读为主。先看 §0.1 阅读地图：§1/§6.5/§11/§13.1/§14 是产品/多文体/JD/复用机会地图，仍有效；§4.2–4.3、§6.3.1、§7–§10 的 Brief/Verifier/repair/30 judge 是历史实现，不要当当前代码。写作层当前认知以 [docs/writing-rebuild-brief.md](docs/writing-rebuild-brief.md) + NEXT_SESSION_PROMPT + 当前代码为准。
- `HANDOFF.md`/`STATE.md` 是当前快照；`handoffs/` 是历史，只追加。
- 旧写作层的 memo/runs/skill/judge、`docs/writing-operating-model.md`、`docs/writing-layer-*.md`、`docs/writing-skill-study.md`、`docs/writing-planner-position.md` 都是历史；不要读、不要当基线。
- 旧架构/旧结果：`_archive/_blocked/`、v2 冻结链路不读、不恢复。旧分支/旧 run 不从里面恢复对象或链路。

## 2. 写作硬规则

- **证据优先**：视频事实/数字/引语/说话人只来自 substrate evidence；模型知识只解释/类比/组织；不伪造。
- **读者体验等价 / 标题 TOC / 视觉优先**：未看视频的读者获得≈同等认知与体验；标题/H2 能当目录；能用图/表/帧说明的结构不堆长文。
- **写作层只保证“视频有就写，没有就不写”**：这是对视频内容的忠实，不是核实世界。视频说假设/单次演示，保留 scope；视频说 X，不要升级成“官方/已证实”。**“未证实”不是写作层的事**；不要每句“视频称/未核实”，不要写成论文/百科/体检报告。judge 的 P5 管红线；写作层不管。
- **主语是内容，不是视频**：模型采用并组织 substrate 内容来表述；不需要“知道自己在总结视频”，也不要显式说“视频里/作者说”，除非真的需要区分观点/事实或指演示。source line 只做一行出处。
- **Writer 是产品，检查是地板**：先写得好；不要用 validator/规则怪谈/多 stage 去“保证”质量。
- **Skill 优先**：角色/读者/方法/示例/self-review；不用词表/规则怪谈。
- **多文体 = 多 Skill/View**：不为每个文体加 body/validator/gate。
- **容量 advisory**：不做固定 length/focus 硬门；只作预算/截断/审计。
- **证据带上下文**：不拍平成 claim 列表，不拆成失去上下文的句子碎片。
- **ASR 为主**：关键帧在 ASR 关键节点附近挑；`real_frame`/`text_experiment`/`no_demo`；生成图不当视频证据。
- **Reader/Audit 分离**：reader 无内部 ID/citation/时间码/审计语言；来源归属按读者影响判断，不按词表。**核实/审计与正文绝对分离**；“未证实”不是正文该管的事，不要每句“视频称/未核实”。
- **失败一等**：partial/unknown/insufficient evidence 明确记录；不静默降级；不自动发布；人工 `publish_approved` 是唯一发布门。
- **不单例适配**：≥2 视频/知识形态/文体结构复现才进通用层；不按单条 finding/单篇调参；不手改单篇文章；skill 里不能出现某个视频/产品/人物的具体内容。
- **复用优先**：本地 skill/知识文档 → 开源项目 → 自己写；借逻辑不抄文本，查 license，不造轮子。
- **评审成本**：不要再跑 5 persona × N 篇的 30 份 subagent 评审；太贵，收益递减。需要外部视角时做小规模、针对性的单 persona 抽查。

## 3. 输入与安全

- `data/`：有效只读输入；不改写；`data/cookies/` 不读、不入库、不外传。
- `参考素材/skills/`、`参考素材/skills_downloaded/`：只读；复用前查 license；不运行仓库内脚本；不把其中示例当本项目事实；不照搬与证据优先冲突的 pipeline。
- `REFERENCES.md`：本地参考/证据的 git 可见索引。
- 不自动 commit/push/publish；不伪造 reader test/A-B；不编造画面/生成图当证据。
- 复用开源/第三方 skill 前审 license、安全、维护状态；借逻辑，不抄文本。

## 4. 上下文维护

- 核心入口只保留三份：`NEXT_SESSION_PROMPT.md`（认知顺序/边界）、`docs/writing-rebuild-brief.md`（方法/纪律）、`AGENTS.md`（护栏）；不要把历史结论塞进入口。
- 断点/换 session：更新 `HANDOFF.md`（当前任务/接手点）和 `STATE.md`（分支/代码/测试事实）；方法/评测变化还要更新 `docs/writing-rebuild-brief.md`。
- 历史交接放 `handoffs/<date>/`，只追加，不改旧快照。
- `architecture.md` 只写设计；发现架构问题先报告，确认后再改。
- 文档冲突：先报告，不静默改架构。

## 5. 开发纪律

- 先想每个步骤的输入/输出：是否最有效、最清晰、最符合该阶段和整体 workflow；输出是否结构化、低摩擦、能被下一 stage 低成本消费。模型调用尤其如此。
- 证据 vs 编辑：视频事实/数字/引语只来自 evidence；模型知识只解释/类比/组织；不伪造。
- 读者优先，不是 coverage：一个控制性 idea、一条机制、具体例子/画面、边界；不是把视频每段都搬。
- Skill 优先，不堆规则：用角色/读者模型/方法/示例/self-review；不要为单条 finding 加 validator/词表/硬编码 gate。
- ≥2 视频/文体复现才进通用层；不按单篇调参；不手改单篇文章；不硬编码个例。
- trace/成本/状态：prompt/system/user/raw/usage/latency/finish_reason/validation/decision 可查；partial/unknown 显式；不静默截断。
- 有界 loop：一次修复；不做无限“再修一轮看看”。
- 不要过度离散：关系/连续性/上下文是写作的一部分；不要为了“结构清晰”把内容切成孤立 claim/表格/小节。
- 先测后调：改模型/参数/prompt 前先有 before/after；同一 request + 盲评；不用“测试通过”代替读者质量。
- 不伪造：不伪造 reader test/A/B；不编来源/数字/画面；不把模型/模拟盲读写成真人；不自动发布。
- 改文档：architecture 只写设计；HANDOFF 写当前快照/接手点；STATE 写事实；历史只追加。
- 遇到冲突：先判断是设计/实现/证据/评测问题；不要用加字段/加 stage/加 validator 掩盖。发现真实阻塞先报告，不静默改 substrate/架构。

## 6. 阶段门（2026-11-05 修正：多文体进行中）

- 当前阶段：**一个写作 skill 已做到质量稳定、能拿出手**；多文体进行中：**社媒（小红书 + 公众号）优先，视频脚本第二步；md 内容先过关；HTML 后续；PDF 暂不做；demo shell 完全体后置**。方向/阶段/验收见 [docs/multiform-roadmap.md](docs/multiform-roadmap.md)。
- 下一步按 roadmap 执行：先调研（本地 + GitHub 的小红书/公众号 reuse map），再社媒，再视频脚本，再 JD 落点/HTML/demo。JD 10 行全部映射到核心，不写“未覆盖”、不硬塞；**多 Agent 编排 = Lead/Editor + specialists + LeadPlan + 共享 RunState + bounded agents-as-tools + trace**，不是多角色 fixed pipeline。
- substrate v1 已冻结；非必要不改；发现真实阻塞先报告。
- 旧写作层（brief/verifier/repair/polish/source line/claim status）已归档，不是基线；不要修旧 pipeline 来适配新 skill。
- 质量门/评测：L1 确定性是地板；L2 semantic editor 可选；L3 小规模针对性评审 + manual acceptance（历史 30 份 5 persona 结果只作参考，**不要再跑 30 份 subagent 评审**）；L4 真人 reader test 未做，不能用模型冒充。
- 先测后调；同 request + 盲评；不按单条 finding/单篇调参。

## 7. 素材消费（2026-11-04）

- 默认路径：素材层产出 `content.md` + `figures/`；Writer 只读内容稿，不知道视频/素材包/管线。
- **不硬截断**：`max_chars` 只 advisory；`over_budget` 记录；caption cap 报告 `caption_truncated`/`caption_full_chars`；不静默删内容。
- **写作层不核实世界**：视频有就写，没有就不写；不每句“未核实”；source line 只做出处；P5 只是质量红线概念，不等于要跑 30 份评审。
- **不按单篇修**：任何 view/排序/覆盖/格式修复都必须跨 ≥2 视频复现；不手改单篇文章来“证明”方法有效。
- **substrate v1 只读**：writing 层通过 [docs/substrate-v1-freeze.md](docs/substrate-v1-freeze.md) 的接口使用它；非必要不改。
