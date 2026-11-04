# Writing Operating Model（2026-11-03）

> **2026-11-04 历史状态：写作层进入干净重做。本文件是旧 v1 operating model，不是当前基线；不要按它改。当前方法/认知见 [writing-rebuild-brief.md](writing-rebuild-brief.md) + [NEXT_SESSION_PROMPT.md](../handoffs/2026-11-03/NEXT_SESSION_PROMPT.md)。**
>
> 状态：当前 writing 层的**工作模型 + 开发方法 + 评测方法**。不是已验收基线，不是 substrate 合同。
> 上位：`AGENTS.md`（护栏）、`architecture.md`（高层设计事实源）、`docs/substrate-v1-freeze.md`（substrate v1）。
> 冲突裁决：本文件 + 当前代码 + 最新 runs > 旧 `docs/writing-*.md` 设计笔记 > 旧 handoff/旧 run。旧文档是历史假设，不是指令。
> 读者：接手 writing 层的新 session/agent。先读本文件，再读代码和实际 artifact；不要先相信任何“接手点”。
>
> **2026-11-03 late 更新**：当前代码的 semantic verifier 改为“交付稿 final-only + 一次 bounded repair”；initial verifier 已删除；`--verify-after-repair` 是 opt-in 的只读 post-audit（默认关）。下面 §2.2/§2.3/§3.5/§5.2 仍描述旧的 initial+final 设计；冲突时以代码/artifacts 为准。

---

## 0. 一句话

把一条视频的**连续证据文本**，写成一篇没看过视频的读者也能获得≈同等理解与体验的独立文章：来源可回查、机制讲得通、边界诚实、有具体例子/画面/数字；模型知识可以解释、类比、补充背景，但不能伪造视频事实、数字、引语或说话人。

**技术通过 ≠ 读者通过。** 当前质量由四层共同判断：确定性校验 → semantic verifier → LLM-as-Judge → 人工验收。没有真人 reader test，就不要说“读者已验证”。

---

## 1. 什么是好的 AI Writing（本项目的判断）

完整标准见两份只读文档：

- `runs/_reader_test_2026-11-03/reader_pack/5个persona.md`
- `runs/_reader_test_2026-11-03/reader_pack/评价方法.md`

本项目对“好”的最低共识：

### 1.1 五个层次

1. **Readable**：愿意读、读得顺；不是语法正确但机器味/翻译腔。
2. **Comprehensible**：读完真正理解，不是“好像懂了”；机制/术语/关系能复述。
3. **Value**：有知识、认知增量、判断或情绪价值；不是正确废话。
4. **Engagement**：标题/开头/节奏/例子让人愿意继续；不是标题党。
5. **Shareable**：有可独立传播的判断/对比/金句/行动出口；不是流量感。

### 1.2 写作层的硬事实

- **来源可追溯**：标题/频道/日期/链接/官方文档/时间戳；拿不到就明确 `未提供/未核实`，不要编 URL，也不要把“视频说”升级成“官方/已证实”。
- **三种句子分开**：`事实（有来源）` / `视频作者或说话人的说法（待核）` / `本文的判断`。不要把本文建议塞回视频人物嘴里。
- **机制**：解释“为什么/怎么发生”，不要把术语当解释；视频只给假设/示意时，标明“视频的假设/本文的读法”，不要写成实测因果。
- **术语**：默认读者是 **smart general reader with some technical baseline**，不是 AI 初学者，也不是全知专家。保留标准术语；只在承重/真陌生时给一句定义或一个类比；不要写百科全书/论文。`reader_profile` 由 request 注入时，服从 request。
- **数字**：带 metric/task/baseline/status；不要把假设示例、单次演示、视频转述写成实测/基准。
- **绝对化**：任何/唯一/真正/就是/证明/永远/第一次/从未/每次/实际作用，都要有证据范围；正文和边界同一 scope。
- **标题/目录**：标题有具体主体 + 冲突/问题；标题 + H2 能当目录；第一段兑现标题；标题引语必须在正文逐字出现。
- **结尾/CTA**：给自然来源入口/下一步；不要编链接；不要用“关注点赞”代替出口。
- **视觉**：图/表/帧是证据或结构，不是装饰；caption 只写图里实际能看到的东西；不把“整体压低”这类数值结论写在一张 2D 聚类图上；假设数字的图注不能写“视频数据/实测”。
- **voice**：文章是独立文章，不是视频笔记；不要把“视频里/这一段/作者说”当每段锚点；不要 uniform scene → table → aphorism；不要重复“不是 X 而是 Y”。

### 1.3 不要做成什么

- 不是 chapter-by-chapter 笔记 / coverage dump。
- 不是百科全书 / 论文 / 术语表。
- 不是把视频时间线复述一遍。
- 不是“信息正确但没有观点、没有入口、没有可分享单元”的稿子。
- 不是用模型/模拟盲读冒充真人 reader test。

---

## 2. 当前架构（从证据到读者）

### 2.1 底座：substrate v1（冻结/可信）

`units → sentences/passages → claims（可选）→ evidence → frames → edited text / source map / consume index`

- 详细接口/证据/限制：`docs/substrate-v1-freeze.md`。
- substrate 只读；writing 层通过既有接口消费，不重写。
- 默认 light path：writer 读连续 edited text + frames；claims 是可选 audit/reuse。

### 2.2 writing 层的当前数据流

```text
WritingRequest（含可选 reader_profile/audience/primary_objective）
  + consume index + edited text + source map + light pack
        │
        ▼
Editorial Brief（可选/条件；full 时两层）
  - 短编辑 brief：core/throughline/spine/title/stance/cut/challenge
  - 知识 brief：concept_ledger / mechanism_chain / number_ledger /
                source_block / texture_policy / next_step
        │
        ▼
Writer（1 次；Markdown；skill = reader_first_explainer）
        │
        ▼
确定性校验 + contract audit
  - structure / reader hygiene / quote hygiene / fact+quote binding
  - source line 从 binding 中剥离；模型知识术语 → editorial_terms（advisory）
  - contract：source line / title quote / title numbers / image captions /
              source gaps / absolute words（advisory）
        │
        ├─ 通过 → 进入语义审计
        └─ 失败 → 1 次 bounded repair（带具体 findings；同一 skill）
        │
        ▼
Semantic Verifier（initial；只读）
  - article + source_text + source/number/concept/mechanism ledger
  - axes: source / claim_scope / number / consistency / term /
          mechanism / title_cta / reader
  - critical/high 或 medium 在材料轴 → blocking
        │
        ├─ blocking → 1 次 bounded repair（binding + contract + verifier findings）
        └─ 不 blocking → 继续
        │
        ▼
Polish（1 次；style/voice/rhythm/title/terms）
  - 可重写 ASR/拗口表达/术语表述；保留 facts/numbers/exact quotes/
    source/claim status/source line/next step
        │
        ▼
Visual planner + renderer（caption-aware；max_assets/genre）
        │
        ▼
Final validation + contract
        │
        ▼
Final Verifier（只读审计最终交付稿；不触发第二次 repair loop）
        │
        ▼
reader.md + assets + binding/citations/audit/validation/manifest
```

### 2.3 调用预算 / 状态

- Writer、repair、polish、verifier 都**不设 per-call `max_tokens`**；由模型概率决定，provider headroom 64k，单次预算 400k tokens，client timeout 300s。
- 一条普通稿的调用：brief（可选）+ writer + initial verifier + repair（条件）+ polish + visual + final verifier。**没有无限 loop**；final verifier 只审计，不再 repair。
- 任何 stage 失败/截断/partial/unknown 必须显式记录；不静默降级。
- 最新 artifact：`runs/_diag/<video>_workflow_v*/`；直接看 `manifest.json`、`reader.md`、`assets/`、`verifier_final_report.json`。

### 2.4 质量层

| 层 | 做什么 | 不做什么 |
|---|---|---|
| L1 确定性 | structure/reader hygiene/quote hygiene/binding/contract | 不判读者质量；不把 complete 当 pass |
| L2 semantic verifier | 来源/范围/数字/一致性/术语/机制/标题/读者；initial 驱动 1 次 repair；final 审计交付稿 | 不重写；不做第二次 repair；不是评分 |
| L3 LLM-as-Judge | 5 persona × 6 articles；两份标准；匿名 A/B；团队权重；P5 红线；manual acceptance | 不冒充真人；不读 hidden mapping 提前；不把团队分当发布许可 |
| L4 真人 reader test | 未来/可选；真实读者、盲读、原始回答、attestation | 未做就写 not_run；不得伪造 |

---

## 3. 每个 stage 的输入/输出/失败/思考点

### 3.1 WritingRequest

- 输入：central_question、job_to_be_done、reader_before/after、success criteria、required/forbidden、platform、media policy；可选 reader_profile。
- 输出：冻结 request + hash；后续看到文章不得改 request。
- 失败：缺核心字段/非法 field；不要用标题猜 request。
- 思考点：request 是读者问题/任务，不是大纲；不要列节序；required_information 是覆盖约束，不是顺序。

### 3.2 Source map / brief

- 输入：consume index + edited text + skill planning lens + request。
- 输出：source map（sections/anchors/numbers/frames/provenance/gaps）；brief（短编辑 + 知识 ledger）。
- 失败：brief 缺 core/spine/title → 不可用；source metadata 缺失 → source_block missing；不编。
- 思考点：brief 是编辑合同/护栏，不是 section schema；Writer 拥有 H2/段落/句子/视觉意图自由；素材与 brief 冲突时以素材为准并记录。
- 已知坑：过度离散的 cut/spine 会破坏关系纹理；知识 brief 缺 concept/mechanism 会让文章变成“好读但没讲清”。

### 3.3 Writer

- 输入：request + skill + edited text + source map/pack + 可选 brief；reader_profile。
- 输出：Markdown（单 H1 + H2 + 段落 + 可选图片），`writer_output.json` 含 article/title/self_review/usage。
- 失败：provider empty/length/structured output；validation 失败 → 1 次 repair。
- 思考点：文章是内容主语，不是视频汇报；一个控制性 idea；TOC；具体例子/演示/画面；机制；边界；术语按 `how_much`；模型知识 explanatory。
- 禁止：内部 ID/timecode/citation/audit language；伪造视频事实/数字/引语；把假设写实测；长段描述本可图/表。

### 3.4 确定性校验 + contract

- 输入：article + edited text + pack + sentences + source_map + brief。
- 输出：validation（structure/reader hygiene/quote hygiene/binding）、contract（source line/title quote/title numbers/image captions/source gaps/absolutes）。
- 失败：binding partial（unsupported number/quote/outside input）→ repair；contract blocking → repair；advisory 不 block。
- 思考点：binding 硬门只对 numbers/quotes/outside-input；拉丁术语（模型知识/术语展开）降为 `editorial_terms`，交给 verifier，避免把“Programmatic Tool Calling”误杀；source line 是 metadata，binding 前剥离。

### 3.5 Semantic verifier

- 输入：article + source_text + source_block/number_ledger/concept_ledger/mechanism_chain + reader_profile；不看 writer plan/self-review。
- 输出：quote-located findings（axis/severity/observation/impact/action）；red_line。
- 失败：provider error/invalid output → unverified；不伪造 findings。
- 思考点：独立视角；不 rewrite；不 judge 现实真伪；`unverified ≠ false`；critical/high 或 material medium → blocking；只做 1 次 repair；final verifier 只 audit。

### 3.6 Repair

- 输入：原 article + findings（binding/contract/verifier）+ skill + brief。
- 输出：repaired Markdown；必须重新 validation/contract；只有 validation complete 才采用。
- 失败：repair 仍 partial → 保留原稿（不静默用坏稿）；记录原因。
- 思考点：repair 不是重写全文；只修 findings；不要引入新 claim/number/quote；不要在修一个 finding 时制造新的内部矛盾。

### 3.7 Polish

- 输入：文章 + source + brief + request；参考 `参考素材/skills` 的风格原则。
- 输出：polished Markdown；preserve facts/numbers/exact quotes/source/claim status/source line/next step；重新 validation/contract；失败则丢弃。
- 思考点：可以重写 ASR/拗口/术语表述；不要新增事实；变化句长/段落形状；避免模板化；polish 不是第二次 repair（不处理 semantic findings）。

### 3.8 Visual planner/renderer

- 输入：article + index frames/claims/evidence + request media policy + max_assets + genre。
- 输出：visual plan + assets + article with images/captions。
- 失败：frame ID/数字/节点不 grounded → skip；图太暗/不可读 → partial/override；不伪造。
- 思考点：图是证据/结构，不是装饰；caption 只写图里能看到的；假设/示意数字不能写成“视频数据/实测”；narrative/mixed 最多 2 个，analytical 可多；section-summary diagram 不要。
- 已知限制：图片/图注的语义一致性最终靠 LLM judge/VLM/人工；contract 只查 caption 存在。

### 3.9 Final verifier / render

- final verifier 是交付稿的只读审计；不触发第二次 repair；findings 保留为 partial/known risk。
- render：reader.md（无内部 ID/timecode）、assets、binding/citations/audit/validation/manifest；同输入同 hash；失败/partial 不静默。

---

## 4. 开发习惯 / 思考方法（比具体代码更重要）

1. **先想 I/O，再写代码**：每个 stage 的输入是否最有效、最清晰、最符合该阶段和整体 workflow？输出是否结构化、低摩擦、能被下一 stage 低成本消费？模型调用尤其如此。
2. **证据 vs 编辑**：视频事实/数字/引语只能来自 evidence；模型知识只能解释/类比/组织；不要把“视频说”升级成“官方/已证实”。
3. **读者优先，不是 coverage**：一个控制性 idea、一条机制、具体例子/画面、边界；不是把视频每段都搬。
4. **Skill 优先，不堆规则**：用角色/读者模型/方法/示例/self-review；不要为单条 finding 加 validator/词表/硬编码 gate。
5. **≥2 视频/文体复现才进通用层**：不按单篇调参；不手改 reader/claim；不“这篇这样修，那篇那样修”。
6. **trace/成本/状态**：prompt/system/user/raw/usage/latency/finish_reason/validation/decision 可查；partial/unknown 显式；不静默截断。
7. **有界 loop**：一次修复；final verifier 只审计；不做“再修一轮看看”的无限 loop。
8. **不要过度离散**：关系/连续性/上下文是写作的一部分；不要为了“结构清晰”把内容切成孤立 claim/表格/小节。
9. **先测后调**：改模型/参数/prompt 前先有 before/after；用同一 request + 盲评；不用“测试通过”代替读者质量。
10. **不伪造成果**：不伪造 reader test/A-B；不编来源/数字/画面；不把模型/模拟盲读写成真人；不自动发布。
11. **改文档时**：architecture 只写设计；HANDOFF 写当前快照/接手点；STATE 写事实；历史 handoff 只追加。旧设计笔记不是基线；与当前代码/runs 冲突时，先报告。
12. **遇到冲突**：先判断是设计问题、实现问题、还是证据/数据问题；不要用加字段/加 stage/加 validator 掩盖。发现真实阻塞先报告，不静默改 substrate/架构。

---

## 5. 评测工具与最新结果

### 5.1 工具

- **L1**：`lunograph.writing.validate` + `contract`；看 `validation.json`/`contract_report.json`。
- **L2**：`lunograph.writing.verifier`；initial `verifier_report.json` + final `verifier_final_report.json`；manifest 的 `verifier`/`verifier_final` 块。
- **L3**：LLM-as-Judge；两份只读标准 + 匿名 A/B pack；5 persona × 6 篇 = 30 独立报告；团队权重 0.20/0.25/0.20/0.15/0.20；P5 红线；manual acceptance。
- **L4**：真人 reader test（未做；未来可选；不能伪造）。

### 5.2 最新结果（事实，不是结论）

- 第一轮 LLM-as-Judge（旧 pack，30 报告）：current 赢 2/3；candidate P2 −8.0；3/6 红线。详细：`runs/_reader_test_2026-11-03/llm_judge/summary.md`、`problems.md`、`method_conflicts.md`、`manual_acceptance.md`。
- 新 workflow 的 judge v5 pack：`runs/_reader_test_2026-11-03/judge_v5/`；`STARTUP_PROMPT.md`；A/B 匿名；**尚未跑 30 个 subagent**。不要提前读 `_hidden_mapping.json`。
- 最新 final verifier residual（事实）：
  - BV17 v5：source line 说 channel 未提供，但帧 OCR 有 `CodingStartup起码课`；演示顺序前后不一致；跨模态解释写成确定机制；2D 聚类 caption 承诺了图里没有的数值结论；“几乎无损”像实测。
  - BV1AC v10：创造模式“就是重排已有插件”与“造了新工具”矛盾；5 vs 3 图注写成“视频数据”；Cordis 事实没有“视频说/未核实”。
  - BV1yb v1：来源行把“验证本文判断”塞给于谦；“没有新事实”应为“没有新的可核验事实”；“实际作用/每次”过强；第一人称引语视角跳；“第一次”历史断言；“治愈系”归属。原 run 的 32k final verifier invalid；64k probe 在 `runs/_diag/BV1yb_workflow_v1/verifier_final_64k/verifier_report.json`（6 findings）。
  - 这些是 residual，不是已修；不要手改单篇；用下一轮通用修复/judge 验证。
- 已知修复（代码已完成；旧 runs 可能早于修复）：binding 的 `editorial_terms`；final verifier；64k headroom/300s timeout；source_map 从帧 OCR 提 channel；chart 图注“视频内容”而非“视频数据”；caption 只描述图里能看到的。

### 5.3 怎么用 judge

- 只把 `judge_v5/reader_pack/` 给 subagent；每个 subagent 只看两份标准 + 自己的 persona + 自己那篇；互不可见；不读旧 `llm_judge` 分数、不读项目 verifier/manifest。
- 30 份报告完成前不读 `_hidden_mapping.json`；完成后解码 A/B，做 comparison/summary/problems/manual_acceptance。
- 标准受众是 AI 初学者/普通互联网用户；本 workflow 可能按 technical baseline 写作。按标准评分，同时单列 `profile_mismatch`，不静默放宽准确性/红线。
- 团队分不是发布许可；P5 红线优先；用户手动验收。

---

## 6. 当前快照与接手点（不保真）

> 这是 2026-11-03 的快照；新 session 必须用代码/artifacts 验证，不要把它当结论。

- 分支 `v3`；未提交；`508 passed`（v3 122 + v2 304 + writing 82）。
- 最新 runs：
  - `runs/_diag/BV17_workflow_v5/`（partial；final verifier 5）
  - `runs/_diag/BV1AC_workflow_v10/`（partial；final verifier 3）
  - `runs/_diag/BV1yb_workflow_v1/`（final article；32k final verifier invalid；64k probe 6）
- 旧 current：`runs/_brief_final3/`；旧链路：`runs/_final/`、`runs/_compare/bilibili_BV1yb/`、`runs/_planner_experiment/`。
- judge v5 pack：`runs/_reader_test_2026-11-03/judge_v5/`；尚未跑。
- 代码入口：`src/lunograph/writing/`（request/context/skill/source_map/brief/prompt/writer/validate/contract/verifier/polish/pipeline/cli）、`src/lunograph/media/`、`src/lunograph/evidence_access/`；skill：`skills/writing/reader_first_explainer/`。
- 未做：真人 reader test、holdout（BV13/BV1ix）、多文体复用、生成图、专家 review。

**接手点不是保真的**：上一位 agent 的判断可能有误；先读代码/最新 `reader.md`/`manifest.json`/`verifier_final_report.json`，再决定保留/重写/删掉什么。

---

## 7. 开放问题 / 决策点

1. **来源可追溯**：标题/频道/日期/链接/官方文档缺失时，source line 如何既诚实又不妨碍阅读？帧 OCR 能补哪些字段？哪些必须等外部来源？
2. **机制 vs 推断**：视频只给假设/示意/单次演示时，文章如何标“视频的假设/本文的读法”，且不在下一段又写成事实？
3. **视觉语义审计**：caption 与图片/表格实际展示是否一致；contract 只查存在；需要 VLM/judge/人工。是否把 visual semantic audit 做成独立 stage？
4. **final verifier residual**：是否允许“final verifier blocking → 第二次 bounded repair”？当前设计是不 loop；如果加，何时停止？成本/质量？
5. **reader profile 冲突**：judge 标准默认 AI 初学者，writer 默认 technical baseline；如何报告/裁决？是否给 judge 两个 audience arm？
6. **holdout/泛化**：BV13/BV1ix 未跑；当前只在 3 个 dev 视频上迭代；何时算通用？
7. **长视频/多文体**：BV1yb 28min 的结构是否可复用？社媒/讲义/教程是否同一 skill 矩阵？
8. **成本/质量**：brief + writer + verifier + repair + polish + visual + final verifier 的调用量是否值得？哪些 stage 可以被 judge 替代/合并？
9. **title/CTA/可分享单元**：当前 judge 的 P4 是弱项；标题/结尾/金句卡如何在不牺牲准确性的前提下改善？
10. **什么算“好 AI writing”**：两份标准是当前最佳共识；如果新证据推翻某条，先记录冲突，不静默改标准。

---

## 8. 阅读顺序

1. `AGENTS.md`（护栏/纪律）
2. 本文件（方法/当前设计/评测）
3. `architecture.md`（高层设计；旧 writing 章节标注为历史，冲突以本文件 + 代码为准）
4. `docs/substrate-v1-freeze.md`（substrate v1）
5. `HANDOFF.md` + `STATE.md`（快照/接手点；不保真）
6. `evals/writing/README.md`（评测协议）
7. 两份只读标准：`runs/_reader_test_2026-11-03/reader_pack/{5个persona.md,评价方法.md}`
8. `skills/writing/reader_first_explainer/SKILL.md` + references/examples
9. 代码 + 最新 runs
