# New session startup prompt — writing layer takeover（2026-11-03）

> **历史，已废弃，不要读。** 当前入口是 [NEXT_SESSION_PROMPT.md](NEXT_SESSION_PROMPT.md)；本文件属于旧的 brief/claim/verifier/repair 框架，只作历史留存。

你接手的是一个已经把 substrate v1 冻结、正在迭代 writing 层的项目。你的任务不是继承上一轮结论，也不是马上改代码；你的任务是**先用项目当前的方法判断现状，再决定下一步**。

## 0. 第一个交付物：诊断 memo（先不要改代码）

在读完本 Prompt 指定的材料、代码和最新 runs 后，先写一份诊断 memo，回答：

1. 这个系统现在实际是什么（不是文档说它是什么）？
2. 最新交付的文章实际做到了什么、没做到什么？给出具体文件/段/句/行号。
3. 你认为当前 top 3–5 个问题是什么？按“影响读者/影响成本/影响可迭代性”排序。
4. 每个问题是**设计问题、实现问题、证据/数据问题，还是评测问题**？
5. 你会保留什么、改什么、删什么？为什么？
6. 下一步最小、最有杠杆的实验是什么？验收标准是什么？需要几个 case 才能说明不是单例？
7. 你需要用户裁决什么？

**在 memo 完成、用户确认之前，不要改代码、不要加字段、不要加 agent/validator、不要 commit。**

## 1. 阅读顺序（不要跳）

项目根目录：`D:\秋招\个人作品\1023视频写作`

1. `AGENTS.md` — 全局护栏/纪律（最高优先）。
2. `docs/writing-operating-model.md` — **当前 writing 方法、stage 边界、评测、开发习惯、最新 residual**（最重要）。
3. `architecture.md` — 高层设计；注意 §7–§10/§15 的旧 writing 设计已标注为历史；与 operating model + 代码冲突时，以 operating model + 代码为准。
4. `docs/substrate-v1-freeze.md` — substrate v1 接口/证据/限制（只读）。
5. `HANDOFF.md`、`STATE.md` — 项目快照和接手点；**不保真**，必须用代码/artifacts 验证。
6. `evals/writing/README.md` — 当前评测栈和 judge 协议。
7. 两份只读标准（不要修改）：
   - `runs/_reader_test_2026-11-03/reader_pack/5个persona.md`
   - `runs/_reader_test_2026-11-03/reader_pack/评价方法.md`
8. `skills/writing/reader_first_explainer/SKILL.md` + `references/` + `examples.md`。
9. 当前代码：`src/facet_studio/writing/`（request/context/skill/source_map/brief/prompt/writer/validate/contract/verifier/polish/pipeline/cli）、`src/facet_studio/media/`、`src/facet_studio/evidence_access/`。
10. 最新 runs：`runs/_diag/BV17_workflow_v5/`、`runs/_diag/BV1AC_workflow_v10/`、`runs/_diag/BV1yb_workflow_v1/`；直接读 `reader.md`、`assets/`、`manifest.json`、`verifier_final_report.json`，不要只读 summary。
11. 历史评测（只作证据，不作当前分数）：`runs/_reader_test_2026-11-03/llm_judge/summary.md`、`problems.md`、`method_conflicts.md`、`manual_acceptance.md`。
12. 新的 judge v5 pack：`runs/_reader_test_2026-11-03/judge_v5/`；`STARTUP_PROMPT.md` 是给评测 session 的。**不要提前读 `_hidden_mapping.json`**；v5 的 30 份报告尚未跑，不要编造分数。

不要读：`_archive/_blocked/`、v2 冻结链路、旧分支/旧 run（除非用户明确要求）。`data/`、`参考素材/skills/` 只读；`data/cookies/` 不读。

## 2. 这个项目在做什么

把一条 B 站视频的**连续证据文本**（ASR/画面/claims/evidence）写成一篇独立文章：没看过视频的读者读完，能获得≈同等的理解与体验——知道视频讲了什么、怎么讲、展示了什么、边界在哪。

不是视频笔记，不是 coverage 摘要，不是百科全书/论文。文章要有：一个控制性 idea、一条机制/论证链、具体例子/演示/画面/数字、诚实的边界、自然的来源入口/下一步。

**证据优先**：视频事实/数字/引语只能来自 substrate evidence；模型知识可以解释/类比/补充背景，但不能伪造视频事实、数字、引语、说话人。**技术 complete ≠ 读者 pass。**

## 3. 什么是好的 AI Writing（本项目当前判断）

完整标准在两份只读文档里；先读全文，不要只记结论。最低共识：

- 五层：Readable（愿意读、读得顺）→ Comprehensible（真正理解、能复述机制）→ Value（知识/认知/判断/情绪价值）→ Engagement（标题/开头/节奏/例子）→ Shareable（可独立传播的判断/对比/入口）。
- 12 维：流畅、逻辑、信息密度、易理解、知识准确、认知增量、Hook、受众适配、叙事、可信、传播、行动引导；知识准确性是红线。
- 5 persona：Human Reader / Knowledge Translator / Content Strategist / Growth Expert / Critical Reviewer；P5 发现重大事实错误/严重误导/未证实关键产品能力写成已证实 → risk hold。
- 写作层硬事实：
  - 来源行/来源块：标题、频道、日期、链接、官方文档；拿不到就写“未提供/未核实”，不编 URL，不把“视频说”升级成“官方/已证实”。
  - `事实（有来源）` / `视频作者或说话人的说法（待核）` / `本文的判断` 三种句子分开；不要把本文建议塞回视频人物嘴里。
  - 机制不是术语；视频只给假设/示意/单次演示时，标“视频的假设/本文的读法”，不要写成实测因果。
  - 默认读者是 **smart general reader with technical baseline**，不是 AI 初学者，也不是全知专家；保留标准术语，承重/真陌生时给一句定义或类比；不要百科全书/论文。`reader_profile` 由 request 注入时服从 request。
  - 数字带 metric/task/baseline/status；不把示例/单次演示/视频转述写成实测/基准。
  - 绝对化（任何/唯一/真正/就是/证明/永远/第一次/从未/每次/实际作用）必须有证据范围；正文和边界同 scope。
  - 标题有具体主体 + 冲突/问题；标题 + H2 能当目录；第一段兑现；标题引语正文逐字出现；结尾有自然出口。
  - 图/表/帧是证据或结构；caption 只写图里实际能看到的；假设数字的图注不能写“视频数据/实测”。
  - 文章是独立文章，不是视频转写；不要每段“视频里/这一段/作者说”；不要 uniform scene → table → aphorism。
- 不要做成：chapter notes、coverage dump、术语表、论文、无观点/无入口/无可分享单元的正确废话。

## 4. 当前架构（一屏）

```text
substrate v1（冻结）: units → sentences/passages → claims（可选）→ evidence → frames
        │  edited text + source map + consume index + light pack
        ▼
WritingRequest（可选 reader_profile）
  → Editorial Brief（条件；full = 短编辑 brief + knowledge ledger）
  → Writer（1 次；Markdown；skill）
  → 确定性校验 + contract audit
      ├─ binding/quote/结构/contract 失败 → 1 次 bounded repair
      └─ 通过 → initial semantic verifier
  → blocking → 至多 1 次 bounded repair
  → Polish（风格/voice/术语；保 facts/numbers/quotes/source/claim status）
  → Visual planner + renderer（caption-aware；max_assets/genre）
  → Final validation + contract + Final Verifier（只读审计交付稿，不 repair）
  → reader.md + assets + audit/citations/validation/manifest
```

关键点：

- brief 是编辑合同/护栏，不是 section schema；Writer 拥有 H2/段落/句子/视觉意图自由。
- binding 硬门只对 numbers/quotes/outside-input；模型知识的拉丁术语（如 `Programmatic Tool Calling`）进入 `editorial_terms`，交给 verifier，不误杀。
- source line/heading 在 binding 前剥离（metadata，不是视频事实）。
- initial verifier 驱动至多 1 次 repair；final verifier 只审计，不再 repair；residual findings 保留为 partial/known risk。
- 不设 per-call `max_tokens`；provider headroom 64k，单次预算 400k，timeout 300s。
- 调用/usage/latency/finish_reason/validation/decision 必须可查；失败/partial/unknown 不静默。

## 5. 开发/优化时怎么想（比具体代码更重要）

1. **先想每个 stage 的输入输出**：输入是否最有效、最清晰、最符合该阶段和整体 workflow？输出是否结构化、低摩擦、能被下一 stage 低成本消费？模型调用尤其如此。
2. **证据 vs 编辑**：视频事实/数字/引语只来自 evidence；模型知识只解释/类比/组织；不伪造。
3. **读者优先，不是 coverage**：一个控制性 idea、一条机制、具体例子/画面、边界；不是把视频每段都搬。
4. **Skill 优先，不堆规则**：用角色/读者模型/方法/示例/self-review；不要为单条 finding 加 validator/词表/硬编码 gate。
5. **≥2 视频/文体复现才进通用层**：不按单篇调参；不手改 reader/claim；不硬编码个例。
6. **trace/成本/状态**：prompt/system/user/raw/usage/latency/finish_reason/validation/decision 可查；partial/unknown 显式；不静默截断。
7. **有界 loop**：一次 repair；final verifier 只审计；不做无限“再修一轮看看”。
8. **不要过度离散**：关系/连续性/上下文是写作的一部分；不要为了“结构清晰”把内容切成孤立 claim/表格/小节。
9. **先测后调**：改模型/参数/prompt 前先有 before/after；同一 request + 盲评；不用“测试通过”代替读者质量。
10. **不伪造**：不伪造 reader test/A-B；不编来源/数字/画面；不把模型/模拟盲读写成真人；不自动发布。
11. **改文档**：architecture 只写设计；HANDOFF 写当前快照/接手点；STATE 写事实；历史只追加。旧设计笔记不是基线；冲突先报告。

## 6. 评测工具与当前事实（快照，不保真）

- L1：deterministic validation + contract。
- L2：semantic verifier；initial + final；final 只审计。
- L3：LLM-as-Judge；5 persona × 6 篇 = 30 独立报告；两份只读标准；匿名 A/B；团队权重 0.20/0.25/0.20/0.15/0.20；P5 红线；用户 manual acceptance。**不是真人 reader test。**
- L4：真人 reader test 未做；未来可选；不能伪造。

当前事实（2026-11-03，需自行验证）：

- 508 tests passed。
- 最新 runs：`BV17_workflow_v5`（partial；final verifier 5）、`BV1AC_workflow_v10`（partial；final verifier 3）、`BV1yb_workflow_v1`（final article；32k final verifier invalid；64k probe 6）。
- 第一轮 LLM-as-Judge（旧 pack，30 报告）：current 赢 2/3；candidate P2 −8.0；3/6 红线。详细在 `runs/_reader_test_2026-11-03/llm_judge/`。
- judge v5 pack 已建好：`runs/_reader_test_2026-11-03/judge_v5/`；**尚未跑 30 个 subagent**。
- 已知修复（代码已完成；旧 runs 可能早于修复）：binding `editorial_terms`；final verifier；64k headroom/300s timeout；source_map 从帧 OCR 提 channel；chart 图注“视频内容”不是“视频数据”；caption 只描述图里能看到的。
- 已知 residual（不要手改单篇；作为判断输入）：来源行归属/频道、机制写成事实、内部一致性、2D 图注承诺数值结论、“几乎无损”像实测、第一人称引语视角、历史“第一次”断言、单次统计写成结论。

**这份快照是上一轮的判断，不是你的结论。** 如果代码/最新 `reader.md`/`manifest.json` 与它冲突，以代码/artifacts 为准，并在 memo 里报告冲突。

## 7. 上一位 agent 的接手点（不保真，供你挑战）

上一轮的判断大意：

- 当前问题不是“句子像 AI”，而是证据链、机制、内部一致性、来源归属、图注语义、标题/CTA/可分享单元；这些问题在 30 份 judge 和 final verifier 里反复出现。
- 已经加了 reader_profile、两层 brief、contract、semantic verifier、polish、final verifier、64k headroom；但 final verifier 仍抓 residual，v5 judge 还没跑。
- 下一步不是继续加 stage，而是先用 judge v5 验证“新 workflow 是否真的比旧 current 好”，再按 top problems 做通用修复；不要按单篇手修。

你可以接受、修正或推翻它。请用代码、最新 runs 和两份标准自己判断。

## 8. 你的第一个任务

1. 按 §1 阅读；不要先读旧结论就下判断。
2. 写 §0 的诊断 memo；必须引用具体文件/段/句/行号。
3. 在 memo 中明确：
   - 当前实际交付的质量瓶颈是什么（不要只说“AI 味”）；
   - 哪些是设计/实现/证据/评测问题；
   - 当前 pipeline 是否有过度工程/缺失环节/边界错误；
   - 如果你只能做一件事，做什么？验收标准是什么？需要几个 case？
4. 把 memo 给用户；等确认后再动手。

## 9. 纪律

- 不擅自 commit/revert/publish；不自动发布。
- `data/`、`参考素材/skills/` 只读；`data/cookies/` 不读。
- 不伪造 reader test/A-B；不把模型/模拟盲读写成真人；不编来源/数字/画面。
- 不按单条 finding/单篇调参；不为单个文体/视频加 hardcode validator/gate/词表。
- 不必要不改 substrate；发现 substrate 问题先报告。
- 不设 per-call `max_tokens`；不静默截断；失败/partial/unknown 记录。
- 旧 `_archive/_blocked`、v2 冻结链路、旧 branch/run 不读，除非用户明确要求。
