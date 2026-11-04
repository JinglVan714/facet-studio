# Writing Layer Functional Map（完整设计 v1.0 + EditorialBrief 增补）

> **2026-11-03 历史状态**：这是早期 writing 设计笔记，不是当前基线。当前 writing 方法/契约/评测/开发习惯以 [writing-operating-model.md](writing-operating-model.md) + 当前代码 + 最新 runs 为准；本文件只作设计历史/假设，冲突时不采用。
>
> 状态：完整设计；**不是 architecture 事实源，不修改 architecture.md**。
> 日期：2026-11-01（2026-11-02 增补 Planner/brief）
> 依据：substrate v1 freeze、本地 17 个参考仓库、bilibili-render-pdf、substrate 代码/数据审计、Agent Skills 资料、brief 盲审实验。
> 下一步：按 EditorialBrief 契约迁移 Planner/Writer；P0 不调模型。

---

## 已确认决策（2026-11-01）

1. **消费默认**：同意 `full_text` 默认，`claim_lean/index_parts/sectioned` 条件启用。
2. **文体路线**：A 叙事/解释先做；**先学习参考 skill**（见 [writing-skill-study.md](writing-skill-study.md)），再写第一个 skill。
3. **媒体路线**：同意真实帧/表格/示意图/图表 + 图像 prompt；生成图后置。
4. **读者 test**：可招真实读者；按 5+ 人执行。
5. **目录/命名**：同意 `src/lunograph/{writing,evidence_access,media}/`；原占位 skill 已删除。

---

## 0. 结论摘要

一句话：**一个证据底座，四层渐进，三个文体簇，五类媒体家族，四个核心角色（Planner/Writer/Validator/Publisher），一个人工发布门。**

1. **消费不是“一次注入 vs 渐进”二选一**：
   - 模型调用层：默认一次连贯上下文（1 次 Writer），保持文章连续性；
   - 证据层：代码按 L0 index → L1 working text → L2 lookup → L3 audit 分层组装；
   - 细节层：用工具/脚本回查 claim/sentence/frame，不让 Writer 漫游语料；
   - 长文/多文体才升级为 sectioned/multi-source，且必须先测量。
2. **Skill 不是 prompt/pipeline**：它是“元数据常驻 + SKILL.md 按需 + references/scripts/assets 按需”的程序性知识包；写作层用 `method × form × style × output` 组合，先做组合 skill，≥2 文体复现后再拆分。
3. **输出不是“文章 + 插关键帧”**：输出是 reader text + audit/citations + `VisualPlan`；媒体分五类：真实帧、派生图表/示意图、表格、生成图、图像/视频 prompt；生成图只作 editorial，永不当视频证据。
4. **多文体不是 7 条管线**：按“叙事/解释（A）、分发（B）、时间/媒体（C）”三簇组织；A 先做，B/C 后置；同一证据库复用。
5. **功能地图画全，但实现竖切**：先把所有契约/角色/媒体/输出定稳，避免后续回头重做底座；每个竖切必须有真实消费者和验收，不做占位 pipeline。

---

## 1. 设计原则与边界

### 1.1 原则（继承 architecture/AGENTS）

- **证据优先**：substrate 是唯一事实底座；skill/Writer/媒体都不是新事实源。
- **模型写作，代码编译/校验**：Writer 只负责表达；quote/时间码/citation/绑定/结构由代码做。
- **默认 1 次 Writer**：高风险才加 1 次 Verifier；结构/绑定失败最多 1 次 repair；不 loop。
- **多文体 = Skill/View**：不为每个文体加 pipeline/body/validator/gate。
- **容量 advisory**：length/focus 只作预算/截断/审计；不做固定硬门。
- **失败一等**：partial/unknown/insufficient 显式；不静默降级；不自动发布。
- **不单例适配**：≥2 视频/知识形态/文体结构复现才进通用层；不按单篇调参。
- **Reader/Audit 分离**：reader 无内部 ID/citation/时间码/审计语言；来源归属自然。
- **真实评测**：reader test/A-B 必须真人；模型/模拟盲读只作 advisory。

### 1.2 本层边界

- 只承诺 `generate`；`reconstruct/redesign/review` 后置。
- 不做全量 Scheduler/MCP/RAG/LangGraph；不做多租户/平台适配。
- 不判断作者主张的现实真伪；不把生成图/示意图当视频证据。
- 不自动发布；人工 `publish_approved` 是唯一发布门。
- 不把历史 P0/P3/M1 的 token/字数当最终承诺。

### 1.3 “地图画全”与“最小架构”的区别

- **地图画全**：现在就把所有层/角色/契约/媒体/输出/失败状态/JD 证据定义清楚。
- **实现竖切**：按 A–G 阶段实现，每刀有真实消费者、测试、验收；不做占位 pipeline、不写死代码。
- **防返工**：`EvidenceIndex`/`WorkingContext`/`SkillManifest`/`VisualPlan`/`OutputBundle`/`RunRecord` 从第一天就按全量文体设计；后续加 B/C 簇不改底座。
- **不预建**：没有消费者/测试的模块不实现，只保留契约与接口。

---

### 1.4 调研结论：参考仓库/ skill 的共同模式

| 来源 | 关键做法 | 借什么 | 不借什么 |
|---|---|---|---|
| bilibili-render-pdf | >20min/300 字幕切段；subagent 返回 5 项；recall-first 帧候选/view image/full-reveal/时间 provenance；TikZ/matplotlib 重绘 | 切段/返回契约/帧清单/provenance/矢量图 | LaTeX 专属、无状态、图越多越好、305 行单体 |
| wewrite | claim ledger（id/text/type/source_ids/status/boundary）+ state.yaml + 文件式流程 | claim 字段/状态/来源 ID | 全 ledger 一次喂、无 quote/span、CLI 静默丢 claims |
| Norman | evidence map + paragraph blueprint + 每章 fresh agent + task packet | source ID/usable fact/supported claim/citation slot/risk；packet 只带相关摘录 | citation-count 质量门、全文重读 |
| zenstory | 单一 index + line span + coverage + `_work/` 原子 publish + resume | 单一索引/覆盖检查/断点续跑 | “聚合永不重读原文”（对证据写作不成立） |
| LongWriter | plan → 段落；每段 instruction + 完整 plan + 已写正文 | 分节连续性思路 | 每步重发全文、无证据层、二次成本 |
| wordflowlab | crawl→Markdown KB→Read/Grep | file-to-file/工作区 | 无 ID/span/claim 的检索当证据 |
| crewAI / great-writer | 角色/context 传递；单入口 router + modes + 阶段门 | router/mode/显式上游产物 | 5 角色顺序链、每章重读 outline、6-phase gate |
| avoid-ai-writing | router + handoff envelope + 确定性 preservation verifier + 有界 repair | handoff/保护片段/一次 repair | detector 规则清单进 core |
| seedance | brief/reference-map/plan.json/run-manifest/qa；@ 引用角色；negative 块；状态机 | 媒体 plan/source_type/QA | 整条视频生成 pipeline |
| Agent Skills | metadata 常驻 + SKILL.md 按需 + references/scripts 按需 | 包结构/渐进披露/scripts 做确定性 | 单体 SKILL.md、全量塞入 |

共同模式：

1. **metadata/router + 渐进披露**：先选 skill，再读正文，再按需读 references/scripts。
2. **文件式状态 + coverage/manifest + resume**：不靠会话记忆；未完成/遗漏显式。
3. **claim/evidence ledger + slot/blueprint**：claim 不只文本，还要 source/status/boundary/放哪一段。
4. **单一索引 + parts + lookup**：Grep/检索只用于定位，最终 quote/fact 回到原句/时间码。
5. **默认 1 Writer + 可选 verifier**：不把一件事拆成 5 个 agent；角色要有独立决策权。
6. **风格后处理与事实分离**：humanizer 只改文风；确定性 preservation check 保护 claims/数字/引文。
7. **媒体分 real/derived/generated/prompt**：代码渲染图表/示意图；生成图 editorial。
8. **机械门 vs 人门**：可判定的走代码；读者质量走真人；清单只是 advisory。

### 1.5 读者体验 / TOC / 视觉合同（2026-11-02 强化）

- **体验等价**：读者没看视频也能复述 central question、机制/流程、关键例子/演示/画面、作者判断与边界；不是 coverage 摘要。
- **TOC 标题**：title + H2 构成可读目录；每个 H2 具体、平行、能单独说明本节讲什么；禁止空泛“背景/介绍/总结”；读者扫标题就能知道文章怎么推进。
- **section promise/takeaway**：每节先明确“这节解决什么/读者带走什么”；结尾一句 takeaway；不逐节 recap。
- **视觉优先**：机制/流程/架构/对比/数字优先 diagram/chart/table/real frame；真实帧只在确实展示操作/结果且可读时用；没有合适图时 text/no_visual 并说明；生成图 editorial。
- **简洁**：一段一个意思；能表格/图替代的长描述删掉；不按视频时间顺序复述。
- **模型知识**：可做解释/类比/背景；不得伪造视频事实/数字/引语；reader 文本无 ID/时间码/审计语言。
- **质量门**：TOC/体验/视觉覆盖由 skill rubric + 人工/reader test 判断；不做 per-form 硬 validator。
- **本次教训**：早期草稿的 BV1yb 失败说明“reader-first 方法”不够；必须把教学结构/TOC/视觉/体验写进 skill，而不是只写“找 central question”。

---

## 2. 分层功能地图

```text
┌────────────────────────────────────────────────────────────────────┐
│ 接入层   CLI / API / SDK（后置）                                   │
├────────────────────────────────────────────────────────────────────┤
│ 编排层   Run / Stage / Attempt · TaskPlan · Decision · Budget · Gate│
├────────────────────────────────────────────────────────────────────┤
│ 输入层   VideoSource · WritingRequest · SkillSelection · Supplements│
├────────────────────────────────────────────────────────────────────┤
│ 证据层   Source → Temporal → Transcript → Claims? → Pack? → Frames  │
│          EvidenceIndex (L0)                                         │
│          WorkingContext (L1: full / parts / claim / multi-source)   │
│          Lookup (L2: ID / time / segment / text / visual)           │
│          Audit (L3: pack / provenance / source_map / rights)        │
├────────────────────────────────────────────────────────────────────┤
│ Skill层  Method × Form × Style × OutputContract                     │
│          manifest · SKILL.md · examples · references · scripts      │
├────────────────────────────────────────────────────────────────────┤
│ 生成层   Planner · Writer(1) · Verifier? · Reviser? · VisualPlanner?│
│          VisualRenderer · ImagePromptWriter · StyleEditor?          │
├────────────────────────────────────────────────────────────────────┤
│ 校验层   Structure · ReaderHygiene · QuoteHygiene · FactBinding     │
│          ClaimClosure · VisualProvenance · Rights                   │
├────────────────────────────────────────────────────────────────────┤
│ 输出层   reader.md · audit.json · citations.json · visual assets    │
│          social pack · shot list · image prompt · run bundle        │
├────────────────────────────────────────────────────────────────────┤
│ 质量层   DeterministicEval · ReaderTest · A/B · Expert · PublishGate│
├────────────────────────────────────────────────────────────────────┤
│ 观测层   usage · trace · replay · eval · decisions · cost            │
└────────────────────────────────────────────────────────────────────┘
```

| 层 | 模块 | 状态 | 主要消费者 | 失败状态 |
|---|---|---|---|---|
| 证据 | `transcript/light_context/edited_transcript` | reuse | Writer/视觉 | `index_incomplete` |
| 证据 | `claim_extract/pack_from_claims` | reuse/optional | claim path/audit | `claim_coverage_partial` |
| 证据 | `bind_article/quote_hygiene` | reuse | Validator/audit | `binding_failed` |
| 证据 | `consume-index-v1` | new | Writer/Planner/Visual | `index_incomplete` |
| 证据 | `WorkingContext` | new | Writer | `over_budget` |
| 证据 | `source-map-v1` | new | Planner/Writer | `source_map_incomplete` |
| 证据 | `lookup/slice/visual_lookup` | new | Verifier/Visual/audit | `lookup_miss` |
| Skill | registry/composer | new | Planner/Writer | `skill_not_found/incompatible` |
| 生成 | Planner（TaskPlan/EditorialBrief） | new | Writer/Visual | `brief_invalid` |
| 生成 | Writer | new | Validator | `writer_failed` |
| 生成 | Verifier/Reviser | optional | human/Validator | `verifier_failed` |
| 媒体 | VisualPlanner/Renderer | new | Output | `visual_unbound/render_error` |
| 媒体 | ImagePromptWriter/ImageGenerator | later | Output | `prompt_invalid` |
| 校验 | Validator | new | Renderer/Verifier | `binding_failed` |
| 输出 | Renderer/OutputBundle | new | Reader/Eval | `render_error` |
| 质量 | EvalRunner/ReaderTest/ABTest | new | Human | `eval_incomplete` |
| 编排 | RunStore/TaskPlan/Decision/Tools | new/reuse | all | `run_failed` |
| 后置 | SectionedWriter/MultiSource/Social/VideoScript | later | B/C 簇 | `continuity_gap/source_conflict` |

---

## 3. 消费设计：四层渐进

### 3.1 四层渐进

| 层 | 渐进对象 | 机制 | 目的 |
|---|---|---|---|
| Skill | 技能包 | metadata 常驻 → SKILL.md 按需 → references/scripts/assets 按需 | 防止 prompt 膨胀 |
| Evidence | 证据 | L0 index → L1 working text → L2 lookup → L3 audit | 控制上下文/成本 |
| Writing | 生成 | 默认 1 Writer → 长文 sectioned → 多角色 optional | 保连续性/不加瀑布 |
| Output | 产物 | reader.md → audit/citations → visual assets/provenance | 读者面/审计面分离 |

**核心判断**：模型调用层尽量一次注入（保持连续性）；证据层由代码分层组装（控制预算）；细节层工具回查（保证可审计）。不是“把整个 substrate 塞给模型”，也不是“让模型在语料里 RAG 漫游”。

### 3.2 消费 profile

| 场景 | Profile | Writer 看到 | 调用 | 记录 |
|---|---|---|---|---|
| 单视频、单文体、working text ≤ advisory 预算 | `full_text` | edited text（无 ID/时间码）+ frame captions + request + skill | 1 Writer | chars/tokens/frames/over_budget |
| 超预算、多 section、需断点续跑 | `index_parts` | 先 index（segment/claim 摘要+part_id），再按需读 part | 1 Writer 或分节 | part manifest/coverage/oversize |
| audit/boundary/多文体复用/高风险 | `claim_lean` | claims（status/scope）+ context + frames | 1 Writer + 可选 Verifier | claim coverage/bounded/provenance |
| >30min、长文、多节 | `sectioned` | plan + 当前 part + 前节摘要/约束 | N section + 1 integrate | continuity/overlap/coverage |
| 多视频/多源（后置） | `multi_source` | 跨视频 index + 每源 working text | 1 Writer 或分节 | source/conflict/coverage |
| 探索型/超大语料（后置） | `tool_agent` | index + lookup tools | 多次 | cost/trace/lookup receipts |

**注意**：这里的 `full_text` 不是 raw ASR，而是 `edited_transcript` 编译后的线性文本（sentences/passages 合并、段标题、frame captions）；raw ASR/时间码/speaker/confidence 留在 audit/raw fallback。Agent Skills/context-engineering 的结论也是：one-shot 应指“一次看已编译/裁剪的 pack”，不是把原始 ASR 全量直灌。

**预算阶梯（advisory，不写死数字）**：

| 阶梯 | 内容 | 触发 |
|---|---|---|
| L0 | light edited text + frames | 单视频、单文体、有效上下文够 |
| L1 | claim/anchored pack（boundary/audit/reuse） | 需要 boundary/引用/多文体复用 |
| L2 | sectioned Writer（每节一个 pack） | >30min、单次上下文不够、需断点续跑 |
| L3 | 多视频 index/retrieval | 多源/企业知识（后置） |
| L4 | 全局 synopsis/树摘要 | 超长/多源全局叙事（后置） |

触发靠评测（comprehension/binding/cost），记录 `over_budget`；不按固定分钟/字数硬切。

默认规则：

- **单篇短/中：full_text**。substrate v1 证据：P3 writer-only 10.8k/10.4k/13.9k；M1 real 13.0k/7.5k/21.6k；短文 B+frames 18/18；长文 cw0/merged 14/14；claims/IDs 对 comprehension 不赚成本。
- **claim path 只在 audit/boundary/reuse/高风险**。claim+writer 36.5k/33.3k/60.5k；单篇 one-off 不回本；bounded claim 让 boundary 题 1→2。
- **index+parts 只在超预算/多 section**。28min 的 index+parts 已证明不回本；不默认。
- **anchored 文本在 claims=[] 时为空**；light path 默认 full，不误走 anchored。
- **pack 只保留 selection 句**（如 BV1yb 167/325）；binding 必须回接完整 sentences/source_map。

#### 3.2.1 full_text 与 raw ASR 的区别（实测）

`full_text` **不是 raw ASR**，而是 `edited_transcript` 的编译视图：units → sentences/passages（标点/静默/segment 合并）+ segment 标题 + frame lines；无 ID/时间码；内容是全量（不做 claim selection）；`source_map` 保留 block→sentence 映射用于审计。

| 输入 | BV17 | BV1AC | BV1yb |
|---|---:|---:|---:|
| raw units chars / tok | 2,071 / 1,583 | 4,726 / 3,888 | 8,280 / 7,393 |
| units → sentences | 185 → 53 | 385 → 116 | 1,100 → 325 |
| edited text chars / tok | 3,645 / 2,208 | 6,426 / 4,833 | 8,915 / 7,771 |
| frame lines | 7 | 7 | 8 |
| edited/raw token | 1.39x | 1.24x | 1.05x |
| claim+writer total（对照） | 33,332 | 36,456 | 60,466 |

结论：

- **raw ASR**：token 略少，但无标点/段落/段标题/frame；模型看到的是碎片流；无 source_map/binding。不是我们的默认。
- **full_text**：全量内容 + 编译结构；只比 raw 多 5%–39% token（主要是段标题/frame lines），但可读性/可审计性显著更好。
- **claim_lean**：不是“全文”，是 claim 选择/压缩；总成本 33–60k（含 claim extraction），只在 audit/boundary/reuse/高风险用。
- **index_parts**：不是“选择 claim”，是“按 part 分区”；为超预算/长内容；读全部 parts 仍覆盖全量。
- **sectioned**：多 Writer 调用；为 >30min/超长；有连续性/整合成本。

#### 3.2.2 条件启用：确定性 `select_profile()`，不是模型自选

我们不是 Claude Code 那种 agent；**profile 由代码选，Writer 不选、不漫游**：

```python
def select_profile(request, index, skill, config):
    measured = measure(index.edited_text)  # chars, est_tokens, segments, duration
    if len(request.video_ids) > 1:
        return "multi_source"              # 后置
    if request.audit_level in {"claim", "boundary", "reuse"} or request.risk_level == "high":
        return "claim_lean" if index.claims else "claim_extract_then_lean"
    if measured.tokens <= config.context_budget and request.sections_required <= 1:
        return "full_text"
    if measured.tokens > config.context_budget or measured.segments > config.segment_threshold:
        return "index_parts"
    if measured.duration_s > config.long_threshold or request.sections_required > 1:
        return "sectioned"
    return "full_text"
```

规则：

- 输入：`duration_s`、`edited chars/tokens`、`segment_count`、`claims_available`、`request.audit_level/form/risk_level/reuse`、`video_count`、`config.context_budget`。
- 触发看**实测 token/segment**，不看固定分钟；duration 只是 hint；阈值 advisory/可配置，不按单视频硬编码。
- `--profile` 可强制覆盖；`--budget` 可配置；决策写 `plan.json`/`decision.jsonl`（basis/measured/over_budget）。
- claim 不在但需要 claim path：先跑一次 claim extraction（或显式 `claim_unavailable` 回退 full_text，不静默）。
- Writer 永远只读代码组装好的 working text；`index_parts` 的 part 选择由 request scope/section 映射确定性完成，或由 bounded Planner 选择；不是 open-ended agent loop。
- 长视频只是“先量 edited text”；装得下就 full_text，装不下才 index_parts/sectioned；不为“时长”硬切。

### 3.3 Source matrix：什么内容能当什么用

| 来源 | 当事实？ | 当结构/风格？ | 必须引用？ | 默认 |
|---|---|---|---|---|
| substrate transcript/frames/claims | 是 | — | 时间码/evidence ID | 是 |
| skill references/examples | 否 | 是（方法/文体/平台） | 否 | 是 |
| 模型自身知识 | 否（只能组织/类比/解释） | 是（editorial） | 否 | 是，标 editorial |
| 用户补充素材 | 开启后才可 | 可 | 需 provenance | 否 |
| 外部 web/RAG | 开启后才可 | 否 | 需 citation | 否 |
| 旧 run/旧 artifact | 只作参考 | 可 | 需版本/hash | 否 |
| 真实帧 | 是（画面证据） | — | frame_id/timecode/rights | 是（有条件） |
| 派生图表/示意图/表格 | 派生（data/relations 必须绑定） | — | source evidence IDs | 是（有条件） |
| 生成图 | 否（editorial） | 是 | prompt/model/seed/rights | 可选 |
| 图像/视频 prompt | 否 | 是 | 源帧/高光 | C 簇 |

原则：**事实只来自 substrate；模型知识只做组织/类比；用户补充/外部 web 默认关闭；生成图/派生图只作 editorial。**

### 3.4 `consume-index-v1` 与消费 API

不改 substrate；在 writing 层确定性构建（RunStore 落 artifact）：

```json
{
  "schema": "consume-index-v1",
  "video_id": "BV17DHC6CELr",
  "timebase": "ms",
  "source": {"light_pack_sha256": "...", "edited_sha256": "...", "source_map_sha256": "...", "pack_id": "ep3_..."},
  "segments": [{"segment_id":"seg1","label":"...","t_start_ms":120,"t_end_ms":37330,
                "part_id":"part_01","block_index":0,"text_start":0,"text_end":337,
                "sentence_ids":["seg1-s001"],"passage_ids":["seg1-p01"],
                "claim_ids":["c_..."],"frame_ids":["00000_000015000"]}],
  "claims": [{"claim_id":"c_...","segment_id":"seg1","status":"supported","kind":"fact",
              "t_start_ms":120,"t_end_ms":31310,"block_index":0,"part_id":"part_01",
              "evidence_ids":["ev_..."],"source_assertion_ids":["seg1-a000"]}],
  "sentences": [{"sentence_id":"seg1-s001","segment_id":"seg1","t_start_ms":120,"t_end_ms":8200,"block_index":0,"text":"..."}],
  "frames": [{"frame_id":"00000_000015000","t_ms":15000,"slot_end_ms":45000,"strategy":"fixed_interval",
              "file":"frames/00000_000015000.jpg","caption":"...","caption_chars":98,"segment_ids":["seg1"]}],
  "parts": [{"part_id":"part_01","block_from":0,"block_to":2,"segment_ids":["seg1","seg2"],"chars":1200}]
}
```

API：

```python
index = build_consume_index(video_id)          # 确定性，无模型
ctx   = build_working_context(index, request, skill, profile="auto")
part  = get_part(index, part_id)               # 正文/claim/evidence/句时间/帧
claim = lookup_claim(index, claim_id)          # claim→evidence/quote/sentence/time/block/frames_near/relations
frame = lookup_frame(index, frame_id | t_ms | time_window)
slice_ = slice(index, t0, t1, neighbor=0)      # 按时间/段/claim 切片
vis   = visual_lookup(index, segment_id | claim_id | window)  # 视觉候选
```

服务对象：

- Planner：读 source map/index，选角度/写 brief；不预写 section schema。
- Writer：读 working text（full/parts/claim view），不读 index/ID/audit。
- VisualPlanner：读 visual_lookup + article sections。
- Auditor/Verifier：读 lookup_claim/lookup_frame/source_map。
- Editor/局部重写：读 slice。

### 3.5 substrate 审计：现在有什么、缺什么

**已有（可直接消费）**：

- `edited text`：无 ID/时间码的线性文本；`source_map`：block 级 `text_start/text_end`，含 `segment_id/sentence_ids/passage_ids/claim_ids/boundary/frames`。
- `sentences/passages`：稳定 ID、ms 时间、boundary_reason、filler_only。
- `temporal outline`：segment label/unit_ids/first_ms/last_ms/coverage。
- `claims/evidence/pack`：claim_id/evidence_id/quote/status/scope/sentence_ids/time；pack 有 selection/coverage/frame_selection/provenance/budget/truncation。
- `assertions/relations`：unit/anchor 级 quote/status/frame_refs；relations 有 supports/refines/causes/sequence/contrasts/tension。
- `frames_index/frames_vlm`：fixed/scene 两套策略；frame_id/time/file；`per_frame.text` 是 VLM 对整屏文字的转录（不是画面语义描述）。
- `rights/provenance`：`rights_scope="unknown_public_video"`；源文件 SHA；`media_available`。
- runtime：`RunStore` 不可变写/哈希、`ToolSpec/Registry`、`TaskPlan`、`SemanticMemoryRef`、`TraceRecorder`。

**规模（3 case）**：

| case | light chars/tokens | 句/段 | claims | frames index/VLM/light | light pack |
|---|---:|---:|---:|---|---:|
| BV17 | 3,645 / 2,208 | 53 / 16 | 33 | 15 fixed / 15 / 12 | 29KB |
| BV1AC | 6,426 / 4,833 | 116 / 32 | 36 | 22 fixed+40 scene / 22+12 / 18（9 有 caption） | 59KB |
| BV1yb | 8,915 / 7,771 | 325 / 85 | 37 | 56 fixed+259 scene / 56 / 16 | 131KB |

BV1yb：28.16min、1100 units、264 assertions、134 relations、37 claims、8 段；`media_available=false`（无 raw 媒体），由 units 直接生成 transcript。

**缺口（writing 层要补，不改 substrate）**：

- `consume-index-v1`/part manifest/物化映射（claim→block/part、frame→segment/claims、sentence→block）缺失；可确定性补。
- `source_map` 只有 block 偏移，无逐句/逐 claim 字符偏移；sentence 级引用需重新 substring，歧义降级 block。
- 媒体结构缺失：无 bbox/阅读顺序/表格单元格/chart 轴/系列/代码边界/OCR 置信度；caption 只是整屏文字。
- 视觉候选/图型分类/look-here 生成缺失：候选可确定性生成；“哪张图值得画、是 chart 还是 table、系列对应哪句话”需 vision/模型。
- claim→frame 链接弱：assertions 只有 8/95、18/145、38/264 带 frame_refs；v3 pack evidence 不带 frame_ids；frame 只是按 claim 时间±12s、每段最多 2 张。
- scene caption 覆盖缺口：BV1yb 0/259、BV1AC 28/40 无 VLM；BV17 无 scene 策略。
- `frames_index` 形状不兼容：`light_context` 读 `strategies`，`pack_from_claims` 读顶层 `frames`；需要 normalizer。
- 权属/授权缺：只有 `unknown_public_video`，无逐帧/逐图 license/署名/复用范围；需人工/来源元数据。
- 数字/单位/轴/系列规范化缺：只有原文数字 token；claims 数字覆盖不稳（BV1AC 0/36，assertions 9/145）。
- `contract.components.first_mention/carriers` 未构建；terms 只有 `first_unit_id/first_ms`。

### 3.6 selection / truncation / coverage

- 每次 selection 记录 `considered/selected/dropped/reasons`；不静默删。
- caption cap 必须报告 `caption_truncated`/`caption_full_chars`；空 caption 帧被 edited text/source_map 丢弃时记录。
- 超预算：记录 `over_budget`；按 segment 分区（parts）；单段超预算保留并标 `oversize`。
- coverage：segments/claims/sentences/frames 的 used/dropped/unreported 全部记录；`coverage.json` 进 run bundle。
- pack 只保留 selection 句时，binding 必须回接完整 transcript；不能拿 pack 当唯一事实源。
- **脏 ASR 保真**：保留 raw ASR/时间码/speaker/confidence；不用摘要覆盖 raw；quote 校验回 raw；edited text 只是编译视图，不是事实源。

### 3.7 为什么默认不做 agentic RAG

- 成本/连续性：默认 1 Writer；substrate 证据表明 short/mid full text 更便宜且质量同级/更好。
- 证据可信：Grep/检索只能用于定位 part/claim；最终 quote/fact 必须回到完整 transcript/source_map，由 `bind_article` 绑定。
- 反例：wordflowlab 的 crawl→Markdown→Grep 无稳定 ID/span/claim status，不能当证据源。
- 正例：zenstory 的单一索引 + line span + coverage；我们的 `consume-index-v1` 同构。
- 只有探索型/超大语料才开 `tool_agent`，且必须返回 ID/quote 并受绑定校验。
- **长文重武器后置**：LongWriter/AgentWrite（plan+分节）、WriteHERE（递归规划）、STORM（多视角预写）只在 >30min/多源/长报告时借思想；默认 1 Writer，不照搬多阶段调用。

---

## 4. Skill 系统

### 4.1 本质

Skill 是**程序性知识包**，不是 prompt/pipeline/模板：

- 元数据常驻（name/description/kind/forms/version/triggers）；
- SKILL.md 在选中后加载（角色/读者/方法/证据纪律/输出契约/self-review）；
- references/examples/scripts/assets 按需加载；
- scripts 执行确定性工作，结果回上下文；不把代码逻辑塞进 prompt；
- 不持有事实；不替代 substrate；不替代确定性校验。

### 4.2 包结构

```text
skills/writing/<skill_id>/
  manifest.json      # id/kind/version/forms/compatible_methods/output_contract/media_policy/rubric
  SKILL.md           # 角色/读者/方法/证据纪律/输出契约/self-review
  examples.md        # 2-3 组好/坏对照
  rubric.md          # 质量维度（人评，不是词表）
  references/        # 可选：平台/文体/领域规范，按需读
  scripts/           # 可选：确定性检查/格式化（代码执行）
  assets/            # 可选：模板（Markdown/LaTeX/HTML/SVG）
  SOURCES.md         # 来源/license/改动点
```

官方 spec/最佳实践要点：

- `name` ≤64 字符（小写字母/数字/连字符）；`description` ≤1024 字符，第三人称，写清“做什么+何时用”。
- SKILL.md 建议 <500 行；正文放流程/决策/默认值/检查清单/指针；领域文档、schema、长 API 放 references（一层深、>100 行加 TOC）；确定性/脆弱操放 scripts。
- scripts 是“执行而非阅读”：代码不进上下文，只回 stdout；要明确 `run` 还是 `read as reference`，并处理错误/依赖。
- `allowed-tools` 是实验性预批准，**不是安全边界**；权限/hooks 在执行层。Claude Code 不读 `version`；API 用 `skver_...` 固定快照。

### 4.3 组合：method × form × style × output

| 类型 | 作用 | 例子 | 加载 |
|---|---|---|---|
| Method | 怎么想/怎么写 | reader_first_explainer、procedural、comparison、argument | 核心 |
| Form | 交付物/平台 | article、notes、wechat、zhihu、xiaohongshu、thread、enterprise_doc、faq、sop、video_script、remix、image_prompt | 核心 |
| Style | 语气/平台 voice | humanizer、platform voice | 可选，按需 references |
| Output | schema/renderer | markdown、latex、html、json、prompt_json、shot_list | 核心 |

- 选择：request 显式 `method_id + form_id (+ style_id)`；registry 校验兼容；记录 DecisionRecord。
- **先做组合 skill**（method+form 写在一个 SKILL.md），≥2 文体复现后再拆 method；不预先拆 7 套。
- **入口薄、文体分、视觉独立**：一个写作入口 SKILL.md 做路由/共享规则；文体/平台放 references/子 skill；视觉放独立 visual skill。description 必须能区分文体，避免错触发；有副作用的 skill 用 `disable-model-invocation`/显式 `/name`。
- 不为每个 form 写 validator/gate；通用校验复用。
- 每个 skill 带 SOURCES.md；MIT/Apache 保留声明；CC BY-NC 只借思路；无 license 不逐字复制。

### 4.4 状态 / coverage / subagent 契约

- 长任务状态落文件：`progress.json`、`coverage.json`、`manifest.json`、`decisions.jsonl`；不落会话。
- 分节写作用 `_work/` 候选 + 原子 publish；resume 不重跑已完成 part。
- 子代理返回契约：`section_id/status(DONE|DONE_WITH_CONCERNS|NEEDS_CONTEXT|BLOCKED)/claims_used/evidence_ids/draft/visual_intents/gaps`；主 agent 负责去重/整合/单一叙事。
- 相邻 section 留小 overlap；整合期去重；遗漏/冲突显式。
- **skill 触发测试**：用固定 request 集测“选对 skill/不误触发”；记录 skill hash/version；API 固定 `skver`。

### 4.5 质量门

- 机械层：结构/reader hygiene/quote hygiene/fact binding/claim closure/visual provenance/rights。
- 模型/人层：central question、机制/步骤、边界、连续性、来源归属、平台 voice。
- 清单只是 advisory；不是“技术门全过=读者质量”。

---

## 5. 角色与生成

### 5.1 四个核心角色 + 可选后处理

核心四：**Planner、Writer、Validator/Binder、Publisher（人工）**；Verifier/Reviser/VisualPlanner/Renderer/ImagePromptWriter/StyleEditor 可选或后置。

| 角色 | 类型 | 默认 | 输入 | 输出 |
|---|---|---|---|---|
| Planner | 编辑 brief（模型/人/Writer phase 均可） | 条件启用 | request + source map + skill planning lens | EditorialBrief（reader/core/source question/payoff/throughline/spine/anchors/title/stance/cut/challenge） |
| Writer | 模型 | 是，1 次 | working context+skill+EditorialBrief | article Markdown |
| Validator/Binder | 确定性 | 是 | article+context+substrate | validation/binding |
| Verifier | 模型 | 否，风险触发 | article+context（不看 plan） | findings |
| Reviser | 模型 | 否，最多 1 次 | findings+article+context | revised article |
| VisualPlanner | 确定性+可选模型 | 媒体时 | article sections+index+media policy | VisualPlan |
| VisualRenderer | 确定性 | 媒体时 | VisualPlan | assets+provenance |
| ImagePromptWriter | 模型/确定性 | C 簇 | evidence+skill | prompt JSON/Markdown |
| StyleEditor | 模型 | 否 | article+style skill | styled article |
| Evaluator | 确定性+人 | 是 | output bundle | eval/reader test/A-B |
| Publisher | 人 | 是 | audit/reader test | publish_review |

- 不设 Research/Editor/Humanizer/Reviewer 五个 agent；合并为 skill 阶段/后处理/确定性校验。
- 默认路径：SourceMap（确定）→ [Brief: none/mini/full/human] → Writer（1）→ Validator（确定）→ [绑定 partial] Repair（≤1）→ VisualPlanner（看完成稿）→ Renderer（确定）→ Human。
- Brief 是编辑合同，不是章节 schema；Writer 拥有 H2/段落/句子/视觉意图。高风险才加 Verifier；媒体才加 VisualPlanner/Renderer。

### 5.2 默认数据流

```text
WritingRequest + Skill + consume-index
  → source_map-v1（确定性素材视图：拓扑/anchors/claim type/speaker/frames）
  → EditorialBrief?（none/mini/full/human；不是 7 节 schema）
  → Writer（1 次，Markdown-only；按 brief 的 angle/promise/throughline/anchors 写，自己定 H2）
  → Validator（结构/reader hygiene/quote hygiene/bind_article）
  → [绑定 partial] 最多 1 次 Repair（保持 brief）→ 再校验
  → VisualPlanner（看成稿）→ VisualRenderer（真实帧/图表/示意图/表格）
  → reader.md + audit.json + citations.json + assets + run.json
  → Human reader test/A-B/expert → publish_review.json
```

### 5.2.1 Brief 模式（条件启用，不写死阈值）

| 模式 | 何时 | 产物 |
|---|---|---|
| `none` | 极短/单论点/低风险；Writer skill 内 mini-brief | 不单独产 brief |
| `mini` | 单论点/短中视频；3–5 个决策 | 半页 brief；可由 Writer 同一次调用产生 |
| `full` | 多话题/多视角/长视频/结构不清 | 一页 brief；可先选角度再写 |
| `human_review` | 发布/高风险/品牌敏感 | 人审 brief，必要时人选 title/angle |

Brief 的字段/检查/柔性规则见 [docs/writing-planner-position.md](writing-planner-position.md) 与 `skills/writing/reader_first_explainer/references/planning.md`。

### 5.3 Verifier 规则

- 触发：高风险（数字/因果/医疗/金融/法律/强结论）、绑定有 unsupported/长引号、Writer self-review 标 uncertain、发布前抽样。
- 输入：文章 + working context（不看 plan/self-review）。
- 输出：可定位 findings（axis/target/severity/observation/impact/action）；只读，不改写。
- 有 blocking → 1 次 revise；不 recheck loop；仍不解决交人工。

### 5.4 风格后处理（可选，不默认）

- 链：draft → style skill → humanizer 定向改 → 确定性 preservation check → 可选模型语义复核。
- 保护：claims/数字/引文/因果/不确定性/受保护片段（代码/表格/URL/frontmatter）不得变。
- 风格检查不进入默认写作路径；不写词表/硬规则进 core。

---

## 6. 媒体/视觉层

### 6.1 媒体分类

五类家族：**真实帧族**（real_frame/frame_sequence/crop）、**派生图族**（table/chart/diagram）、**生成图族**（generated_image）、**prompt 族**（image_prompt/video prompt）、**无图族**（text_experiment/no_visual）。

| Kind | 来源 | 是证据？ | 渲染 | 读者标签 | 门 |
|---|---|---|---|---|---|
| `real_frame` | 视频 snapshot | 是 | copy/crop | 视频画面 | 相关性/可读性/时间码 |
| `frame_sequence` | 视频 snapshot | 是 | copy | 视频画面 | progression/去重 |
| `crop` | 真实帧 | 是（派生） | PIL | 视频画面（局部） | 可读性/原帧时间 |
| `table` | claims/evidence | 派生 | Markdown/HTML | 根据视频内容整理 | 数据绑定 |
| `chart` | claims/evidence 数字 | 派生 | SVG/matplotlib | 根据视频数据绘制 | 数据绑定/轴/系列 |
| `diagram` | claims/relations | 派生 | SVG/Mermaid/Graphviz | 根据视频内容绘制 | 关系/节点绑定 |
| `generated_image` | prompt/模型 | 否（editorial） | 图像模型 | AI 生成示意图 | 标注/权利/人审 |
| `image_prompt` | 帧/高光 | 否 | 文本 | 生成提示词 | 字段/来源 |
| `text_experiment` | 散文 | 否 | 文本 | 文字说明 | 不暗示视频演示 |
| `no_visual` | 无 | — | — | — | 显式 |

### 6.2 视觉规划流程

```text
article sections + consume-index + media_policy
  → visual_lookup（确定性候选：帧/数字/关系/流程/对比）
  → VisualPlanner（分类：real_frame / chart / diagram / table / generated / prompt / none）
  → 校验（帧存在/数据绑定/关系绑定/生成标注/权利）
  → VisualRenderer（SVG/Mermaid/matplotlib/PIL/LaTeX）
  → assets + provenance + caption
  → audit（source_type/source_ids/renderer/hash/rights）
```

### 6.3 真实帧：caption-only vs vision-inspected

- 当前 provider 是文本模型；substrate `per_frame.text` 是 VLM 对**整屏文字**的转录，不是画面语义描述。
- 真实帧选择：按 claim/segment 时间窗 + caption 词面相关 + 帧策略/是否代表帧；标 `selection_basis=caption_only`；必须人审。
- 若未来加 vision adapter：逐张看图，按相关性/所需内容可见/最终完整状态/可读性/邻近最佳候选筛选；标 `vision_inspected`。
- 确定性可读性门：渲染前用 PIL 抽样计算 `non_dark` / `stddev` / 尺寸；过暗、过平、过小的帧跳过并记录 `frame_low_readability`，不硬插。这是像素级启发式，不替代人审。
- 不能把 caption 当画面事实；不能凭字幕/文件名/时间戳推断画面。
- 空 caption/截断 caption/低覆盖 scene 帧要显式；不要硬凑。

### 6.4 图表/示意图/表格

**优先级（关键帧不一定好时）**：

1. 若有另一张确实更好/更可读的真实帧或裁剪，先用它（它是证据）；
2. 否则用结构/数据图：数字/对比→chart/table；流程/因果/架构→diagram；
3. 解释图：SVG/Excalidraw；
4. 最后才是生成插图（editorial）；
5. 都没有→`text_experiment`/`no_visual`。

不要为了有图硬插关键帧；真实帧只在它确实展示操作/结果/claim 且可读时用。
- chart 数据必须来自 bound evidence：每个点带 `source_evidence_id`；没有数字就不画；近似/舍入标注。
- diagram 节点/边必须来自 claims/relations（supports/refines/causes/sequence/contrasts/tension）；不补视频没说的边。
- table 行列来自 claims/evidence；不编单元格。
- 渲染器：先做纯 SVG/Markdown/HTML（无新依赖）；Mermaid/Graphviz/matplotlib 作为可选 adapter；当前环境没有 matplotlib/graphviz/mmdc，Node/npx 可用，PIL/imageio-ffmpeg 可用。
- 当前 SVG 渲染规则：文字按实测宽度换行（不按固定字数截断）；DAG 用最长路径分层，源节点贴近消费者；DFS back edge 走右侧 lane，避免穿过节点；小分支树用 tidy tree（思维导图式）；bar chart 用横向条+换行标签+刻度；边标签压到 ≤18 字并对标签做占位避让；不引入新依赖。
- PPTX/LaTeX/HTML 是可选导出 adapter；当前默认 SVG/Markdown，不把 PPTX 运行库作为依赖。视觉先插在本节 takeaway 之前，保持“图/表在前、收束句在后”。
- 真实帧路径用 `pack.video_id`（完整 BV 号）拼 `data/<video_id>/frames/...`，避免短 run key 找不到帧；渲染前过像素级可读性门。
- 生成图只覆盖“证据无法准确画出、但需要示意”的场景；标 editorial；不用来证明视频内容。

### 6.5 图像/视频 prompt（C 簇）

- 结构：主体/角色 + 场景 + 动作 + 运镜 + 时间分段 + 转场/特效 + 音频 + 风格/情绪；负向提示单独成块。
- 参考素材用 `@` 角色映射（首帧/角色外观/场景/运镜/动作/特效/BGM/音效/服装/产品）；每个引用说明“继承什么/不继承什么”。
- 分镜两阶段：先出带编号格子的 storyboard reference，再喂视频模型；prompt 只负责连接。
- 产物：`brief.md`、`reference-map.md`、`plan.json`（shots/start/end/action/camera/audio/entry/exit/references）、`run-manifest.json`、`qa.md`；状态 planned/assets-ready/submitted/generated/reviewed。
- 未生成的 prompt 不能叫“完成视频”。
- **绝不能生成**：证据帧、真实人物/事件/地点、带精确数字的数据图、时间线/年表、地图/平面图/网络拓扑、产品 UI/截图、文档/记录、医疗/法律/金融证据图。

### 6.6 Provenance / 读者标签 / 权利

- 每个资产带 `source_type`：`real_frame|derived_chart|derived_diagram|derived_table|generated_image|prompt`。
- `real_frame/crop/frame_sequence`：frame_id/timecode/file/capture_method/rights。
- `chart/table`：data rows + source_evidence_ids + renderer/code hash。
- `diagram`：nodes/edges + source_claim_ids/relation_ids + renderer/code hash。
- `generated_image`：prompt/model/seed/size/license/editorial=true。
- `image_prompt`：prompt fields + source frame/highlight IDs。
- 读者标签：真实帧“视频画面”；派生“根据视频内容绘制”；生成“AI 生成示意图”；prompt 不是图。
- **figure_spec/re-render**：每个 node/edge/series 带 evidence_id/timecode/source_hash；渲染器记录 code version/data hash/figure_manifest；caption 带来源时间码；可重渲染审计。
- **provenance 不是真伪判决**：C2PA/SynthID/IPTC 是信号；元数据可被剥离，`not_detected` 不代表不是 AI；生成图必须标 editorial，不承担证据功能。
- 权利：当前只有 `unknown_public_video`，无逐帧/逐图授权；对外发布前必须人工确认；不自动发布。

### 6.7 媒体质量检查

- real_frame：相关性/所需内容可见/完整状态/可读性/邻近最佳候选/时间码。
- chart：数据点全部绑定；轴/单位/系列明确；无编造数字；数据表进 audit。
- diagram：节点/边有 source；不补边；不装饰。
- generated_image：editorial 标注；prompt/seed/rights；人审；不当证据。
- caption：只写“看哪里”，不写正文摘要；不与正文矛盾。

---

## 7. 多文体地图：三簇

### 7.1 三簇

| 簇 | 文体 | 共享 | 差异 | 输出 | 质量门 |
|---|---|---|---|---|---|
| A 叙事/解释 | 深度解析、讲义/教程、报告/企业知识、二创/评论 | EvidenceIndex + 1 Writer | method/genre skill、结构、媒体策略 | Markdown + VisualPlan/assets | reader test/A-B、专家 review |
| B 分发 | 公众号、知乎、小红书、微博、thread、LinkedIn | EvidenceIndex + 1 Writer | 平台 form skill、标题/封面/标签/合规 | JSON pack（titles/cover/body/hashtags/checks）+ 可选图 | 平台 reader test/A-B |
| C 时间/媒体 | 视频脚本、分镜、图像/视频 prompt | timeline/frame view + plan schema | 时间/镜头/引用/负面 prompt | `plan.json` + prompt + assets | table read/video review、图像检查/权利 |

- **先做 A**（深度解析），再做 A 的第二个文体（讲义/教程）；然后 B/C。
- A 的媒体层同时服务 C 的真实帧/图表/示意图。
- B/C 不建新 pipeline；复用 EvidenceIndex/Writer/Validator/Renderer 接口。

### 7.2 文体矩阵

| 文体 | Method | Consumption | Output | Media | Quality |
|---|---|---|---|---|---|
| 深度解析 | reader_first_explainer | full_text（短/中）或 claim_lean | Markdown article | real_frame/diagram/chart | reader test/A-B |
| 讲义/教程 | procedural | full_text/index_parts | Markdown/LaTeX/HTML | real_frame/diagram/chart/code | expert/reader |
| 报告/企业知识 | report/enterprise | claim_lean/multi_source（后置） | Markdown/HTML/FAQ/SOP | table/diagram | expert review |
| 社媒 | highlight/argument + form | highlight/quote view | JSON pack | optional generated/diagram | platform reader/A-B |
| 视频脚本 | timeline/beat | timeline/frame view | plan.json + shot list | real_frame/B-roll/prompt | table read/video review |
| 二创 | argument/highlight | claim_lean | Markdown | optional editorial image | human review |
| 生图提示词 | frame/highlight | frame lookup | prompt JSON/Markdown | generated image/prompt | image check/rights |

### 7.3 输出契约

- A：Markdown（H1/H2/段落/图）+ `audit.json`/`citations.json` + assets。
- B：JSON pack：`titles[]`、`cover_copy[]`、`body`、`hashtags[]`、`platform_checks`；可选 `media[]`。
- C：`plan.json`：shots[]（start/end/action/camera/audio/entry/exit/references）、negative[]、source_type；copy-ready prompt。
- 通用：每个媒体资产带 provenance；每个 fact/quote 可回查；reader 文本无 ID/时间码/审计语言。

### 7.4 复用测量

- 同一 `consume-index-v1` 生成第二种文体；记录 reused layers（transcript/claims/frames）、marginal tokens/latency、是否重跑 claim。
- 如果第二文体需要新 View，先证明现有 view 不够；只加 View，不加 pipeline。
- 如果 claim 预计算在多文体下回本，保留；否则继续 light path。

---

## 8. 质量与评测

### 8.1 确定性校验

- 结构：H1/heading/paragraph 非空；brief 可选，不要求逐节 plan 与 sections 一致；只检查标题/结构与 reader 文本。
- reader hygiene：无内部 ID/citation/时间码/审计语言。
- quote hygiene：非精确引号去引号；报告 kept/removed。
- fact binding：数字/Latin token 绑定；unsupported/outside_input 报告。
- quote binding：精确/归一化；long unbound 报告。
- claim closure（claim path）：claim/evidence ID 闭合；quote 是 evidence 连续子串。
- visual provenance：real_frame 存在/时间码；chart/table 数据绑定；diagram 关系绑定；generated 标注；rights。
- 失败：`binding_failed`/`render_error`/`visual_unbound`；不产出成功 artifact。

### 8.2 真实 reader test / A-B

- 5+ 真实读者；5 题：central question、机制/步骤复述、边界、具体事实、偏好/理由。
- 盲读：不告知作者/skill；A/B 随机顺序；记录原始回答。
- A/B 6 维：comprehension/accuracy/expression/structure/memory/willingness；1–5。
- baseline：同模型、同证据、通用 explainer prompt；或上一版 skill。
- 模型/模拟盲读只作 advisory；不冒充 reader test。
- 个人数据只放 `runs/`；`evals/` 放匿名汇总/attestation。

### 8.3 专家/table read/图像检查

- 讲义：专家检查步骤/公式/代码/时间码。
- 企业知识：专家/使用者检查事实/权限/来源。
- 视频脚本：table read/video review；分镜可执行。
- 图像：真实帧可读性/相关性；生成图 editorial/权利；prompt 字段完整。

### 8.4 发布门

- `publish_review.json`：reader/audit/citations hash、reader test/A-B、专家 review、checklist、known risks、status。
- 人工 `publish_approved` 是唯一发布门；不自动发布；不把内部 artifact 当公开发布。

### 8.5 评测维度 / 版本

- 至少 **2 视频 × 2 文体**；测 central question/mechanism/boundary、fact binding、quote precision、timecode accuracy、unsupported claims、真实 reader test、cost/latency。
- 记录 skill hash/view version/prompt hash/model version；skill 触发用固定 request 集测试；API 用 `skver` 固定快照；不按单篇调参。

---

## 9. Harness 与 JD

### 9.1 Run / Stage / Attempt

- `run.json`：run_id、request/skill/evidence hashes、stage 状态、usage、latency、calls、cache。
- `trace.jsonl`：stage/model/params、system/user prompt hash+path、raw response、usage（reasoning/cached）、latency、finish_reason、validation、decision。
- `decisions.jsonl`：skill 选择、verifier 触发、revise 原因、media 选择、human waiver。
- `tool_calls.jsonl`：ToolSpec/args/result/error/latency；真实回执。

### 9.2 TaskPlan / EditorialBrief / Decision

- TaskPlan：执行 DAG（load index/plan/write/validate/verify/visual/render/eval），status/attempts/budget。
- EditorialBrief：reader、core argument、source question、payoff、throughline、spine moves/anchors、chosen title、stance、cut、challenge、evidence status（编辑合同/audit，不是章节 schema）。旧 WritingPlan 是 legacy/replay。
- DecisionRecord：候选/选择/依据/后果/confidence。

### 9.3 Tools

- `load_source`、`build_consume_index`、`get_part`、`lookup_claim`、`lookup_frame`、`slice`、`visual_lookup`、`bind_article`、`render_markdown`、`render_visual`、`render_image_prompt`。
- ToolSpec：input/output schema、allowed roles、side effect、timeout、idempotency；失败不静默。
- 不做 MCP 生态；后续可加 adapter。

### 9.4 Memory

- 语义记忆：EvidenceSnapshot / consume-index / frames（只读快照）。
- 程序性记忆：skill registry/versions。
- 工作记忆：RunState/WorkingContext/decisions。
- 情节记忆：后置；不伪造。

### 9.5 Trace / Replay / Budget

- 同 request/skill/evidence/prompt/model → 可 replay；旧 artifact 冻结。
- 模型调用 cache：request identity；hit 不调 provider；miss 成功写缓存；corrupt 回退真实调用。
- Budget：max calls/tokens；超限显式；不静默降级。

### 9.6 JD 映射与 demo

| JD 能力 | 本层落点 | 阶段 | 最小证据/ demo |
|---|---|---|---|
| 多 Agent 协作 | Writer + optional Verifier/VisualPlanner，共享 evidence | C/D | `runs/<id>/writer/` + `verifier/` + revise 记录 |
| 任务规划/调度 | TaskPlan/EditorialBrief/Decision | B/C | `brief.json` + `decisions.jsonl` |
| 工具调用/MCP | consume-index lookup/binding/render/visual + receipts | B/C | `tool_calls.jsonl` |
| 记忆 | EvidenceIndex/SkillRegistry/RunState | B/F | 同一证据两文体复用报告 |
| 决策/Trace/Budget | decisions/trace/usage/replay | C | `trace.jsonl` + replay |
| 评测/质量 | EvalCase/EvalRun + reader test/A-B | E | `eval/` + 真人原始回答 |
| Prompt/Context | skill + working context + request；hash | C | prompts + token/context report |
| Agent 框架/RAG | lookup/slice/visual_lookup；optional vector | 后置 | 真实检索 demo |
| 工程/成本/观测 | 1 Writer 默认；cost/latency/failure | C | `run.json` + cost |
| 作品/开源 | 2 文体 + reader artifact + replay | G | portfolio |

原则：每项有 artifact + consumer + test + demo；没有实现的不写“已完成”；不为关键词造假。

---

## 10. 失败状态 / 观测 / 版本

### 10.1 失败状态

| 状态 | 含义 |
|---|---|
| `index_incomplete` | consume-index 缺 segment/claim/frame/block 映射 |
| `source_map_incomplete` | source map 缺拓扑/anchor/speaker/claim type；可退回全文或 unknown |
| `evidence_insufficient` | working context 不足以回答 central question |
| `over_budget` | 超 advisory 预算；记录，不静默删 |
| `skill_not_found`/`skill_incompatible` | skill 缺失/不兼容 |
| `brief_invalid` | TaskPlan/EditorialBrief 不合法 |
| `writer_failed` | 结构/绑定/输出不合法；最多 1 repair |
| `provider_outcome_unknown` | 可能已调用但结果未知；不自动重放 |
| `binding_failed` | grounded span 缺 binding/quote/ID 不闭合 |
| `verifier_failed` | Verifier 输出无效；不当 supported |
| `visual_unbound` | 图表/示意图数据/关系未绑定 |
| `render_error` | 渲染/媒体/reader hygiene 失败 |
| `eval_incomplete` | reader test/A-B 未完成；不冒充 |
| `publish_blocked` | 缺人工 `publish_approved` |

### 10.2 观测

- 每次模型调用：stage/model/params、system/user hash+path、raw、usage（prompt/completion/reasoning/cached）、latency、finish、validation、decision。
- 每次工具调用：tool/args/result/error/latency。
- 每个 run：request/skill/index/working context/prompt hash；stage status；cost；cache。
- 每个输出：reader/audit/citations/visual provenance；publish review。
- 静态上下文预算 CI：skill/references/persona chars 纳入测试，防 prompt 膨胀。

### 10.3 版本

- `consume-index-v1`、`writing-request-v1`、`writing-skill-v1`、`working-context-v1`、`visual-plan-v1`、`writer-output-v1`、`run-record-v1`、`eval-case-v1`、`publish-review-v1`。
- 同输入同 hash；旧 artifact 冻结；replay 指向旧版本。
- API 用 `skver_...` 固定 skill 快照；Claude Code 不读 `version` 字段；本层自建 manifest/hash 版本，不依赖宿主字段。

---

## 11. 实施顺序（竖切，不返工）

| 阶段 | 内容 | 验收 | 停止条件 |
|---|---|---|---|
| A 契约/地图/评测集 | 本文件、contracts、request template/eval protocol、5 requests（3 dev+2 holdout） | 文档 review；request 冻结 hash；0 模型 | 契约未确认不写代码 |
| A2 Skill study | 读完 17 仓 + bilibili + Agent Skills；写 `docs/writing-skill-study.md`；第一个 skill 的设计 brief | study doc review；borrow/avoid/license 清楚 | 未学习完不写 SKILL.md |
| B EvidenceAccess | consume-index、working context、lookup/slice/visual_lookup、normalizer、coverage | 3 视频 index；full_text/claim_lean/index_parts 可选；测试；0 模型 | index 不覆盖/映射不闭合不走 C |
| C 核心写作 | 新 skill + Writer + Validator + Renderer + trace | 3 篇技术通过或显式 partial；1 Writer；无 per-case 改 | 两轮通用修复无提升，重审 skill |
| D 媒体 | VisualPlanner/Renderer；real_frame/table/diagram/chart；provenance；生成图后置 | 每图有 source/provenance；无假图；人审 | 媒体不绑证据就不进 render |
| E 真实质量门 | 5+ 读者/5 题/A-B；skill v1.1；before/after（用户确认可招募） | 真实 reader test/A-B；known risks | 招不到真实读者→advisory，不伪造 |
| F 第二文体/复用 | 讲义/教程 或 社媒 pack；同一证据；复用报告 | 2 文体；无 per-form validator；marginal cost | 需要新 pipeline 就停/报告 |
| G C 簇/JD/作品集 | 视频脚本/分镜/图像 prompt；JD evidence；portfolio | plan.json/prompt/QA；2 文体 artifact | 无真实消费者不做 |

当前进度：**完整设计 v1.0** + `skills/writing/reader_first_explainer/` **v1.1**（planning reference + `writing_brief`）+ 视觉层（table / SVG chart / SVG diagram / real frame）+ **EditorialBrief 链路已接**（`source_map.py` → `brief.py` → Writer；`planner.py`/`writing-plan-v1` 仅 legacy）；`consume-index-v1` / lookup / `visual_lookup` + `writing/{request,context,skill,brief,source_map,prompt,writer,validate,pipeline,cli}` + `media/{planner,render}` 已接通；3 个 light index + BV17 claim path index；3 个 dev request 冻结；**3 个 brief complete runs（`runs/_brief_final3/`）**：BV17 mini 5 moves/2,858 chars/2 表+4 assets，68/68 facts、8/8 quotes；BV1AC full 6 moves/4,000 chars/2 表+1 asset，79/79 facts、6/6 quotes；BV1yb full 7 moves/3,825 chars/4 表+1 asset，0/0 facts、28/28 quotes；legacy `runs/_final/` 保留 before/after；bilibili-style 对照 8,234 chars/29,472 tok、7 unsupported facts，不能整条照搬；**brief 盲审实验**（BV1yb A/B、BV17/BV1AC）已做；487 tests。下一步：brief 盲审/复核 → 真实 reader test/A-B + holdout。

原则：JD 证据随 B/C 累积，不等到 G；G 只是打包/demo。

---

## 12. 需要增补 architecture 的地方（先报告，不静默改）

1. §5.3/§15：加入 **Evidence Access L0–L3** 与消费 profile（full/claim_lean/index_parts/sectioned/multi_source/tool）；明确默认 full text，渐进条件启用。
2. §6：加入 **method × form × style × output** skill 组合、references/scripts/assets/SOURCES、state/coverage/subagent 契约。
3. §7：明确 **prose-only 默认**；结构化 audited mode 可选；brief 用 EditorialBrief（可模型/人/Writer phase），不强迫 Writer 输出 JSON/ID；TaskPlan 只做执行调度。
4. §9：加入 **visual provenance/媒体校验**；citations 粒度诚实（fact/quote/block；paragraph/frame approximate）。
5. §12：扩展媒体分类：real_frame/frame_sequence/crop/table/chart/diagram/generated_image/image_prompt/text_experiment/no_visual；派生图/生成图的 editorial 与 provenance 规则。
6. §13：加入 JD artifact/demo map（本文件 §9.6）。
7. §17：更新开放问题/停止条件（reader test、视觉渲染依赖、vision adapter、claim/多文体回本、sectioned 回本、多源）。

---

## 13. 复用与许可

| 来源 | License | 借什么 | 不借什么 |
|---|---|---|---|
| bilibili-render-pdf | 本地未见 LICENSE | 长视频分段/subagent 返回/帧清单/provenance/矢量图 | LaTeX/PDF 专属、无状态、图越多越好、305 行单体 |
| wewrite | MIT | claim ledger/state/source ID | 全 ledger 一次喂、无 quote/span、静默丢 claims |
| Norman | MIT | evidence map/chapter packet/fresh agent | citation-count 门、全文重读 |
| zenstory | MIT | 单一 index/line span/coverage/atomic publish | 聚合永不重读原文（对证据写作不成立） |
| LongWriter | Apache 2.0 | plan+已写正文的分节连续性 | 每步重发全文、无证据层 |
| wordflowlab | 未见 LICENSE | file-to-file/工作区 | 无 ID/span/claim 的 Grep 当证据 |
| crewAI examples | 未见 LICENSE | 角色/context 传递思路 | 5 角色顺序链、每章重读 outline |
| great-writer | MIT | 单入口 router/modes/阶段门 | 6-phase gate、硬词表 |
| avoid-ai-writing | MIT | handoff envelope/preservation verifier | detector 规则清单当 core |
| rednote | MIT | examples voice/写检分离/冷读 | 平台违禁词/标题公式当全局 validator |
| seedance2 | MIT | plan.json/references/negative/status | 整条视频生成 pipeline |
| tomoai | CC BY-NC 4.0 | 只作结构参考 | 商业交付/直接复制 |
| Agent Skills | 官方资料（https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills） | metadata/渐进披露/scripts | 305 行单体、全量塞入 |

规则：MIT/Apache 保留声明；CC BY-NC 只借思路；无 license 只借方法/结构，不逐字复制；每个 skill 带 SOURCES.md。

外部资料（design references）：

- Agent Skills spec：https://agentskills.io/specification
- Skills overview：https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- Context engineering：https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Mermaid：https://mermaid.js.org/；Graphviz：https://graphviz.org/；matplotlib：https://matplotlib.org/；TikZ：https://tikz.dev/
- AP AI standards：https://www.ap.org/the-definitive-source/behind-the-news/standards-around-generative-ai/
- IPTC：https://cv.iptc.org/newscodes/digitalsourcetype/；C2PA：https://c2pa.org/

---

## 14. 开放问题与需要拍板

### 14.1 开放问题

- 真实 reader test 能否招到 5+ 人？招不到则质量标 advisory。
- 视觉渲染依赖：当前无 matplotlib/graphviz/mmdc；先纯 SVG/Markdown/PIL，Mermaid/Matplotlib 作为可选 adapter。
- vision adapter：当前 provider 文本；真实帧只能 caption-only，需人审；是否引入视觉模型？
- claim path 在多文体下是否回本？F 阶段测量。
- sectioned 在 >30min 是否回本？M3 后置。
- 多源/企业知识后置；冲突/权限/来源需要新契约。
- skill 组合何时拆 method/form？≥2 文体复现后。
- 数字/单位/轴/系列规范化：确定性抽 token + 模型语义对齐；不要伪造数据。
- skill 触发误触/漏触：用固定 request 集测 description；有副作用 skill 显式调用。
- `allowed-tools` 不是安全边界；权限/hooks 在执行层。
- C2PA/SynthID/IPTC 只是信号；生成图权利/标注需人工。
- 视觉依赖：Mermaid/Graphviz/matplotlib/TikZ 无头渲染依赖未装；先 SVG/Markdown/PIL。

### 14.2 已确认（2026-11-01）

1. **消费默认**：同意 `full_text` 默认，`claim_lean/index_parts/sectioned` 条件启用。
2. **文体路线**：同意 A 叙事/解释先做，B 分发、C 时间/媒体后置；**先学习参考 skill**（见 [writing-skill-study.md](writing-skill-study.md)），再写第一个 skill。
3. **媒体路线**：同意先做真实帧/表格/示意图/图表（代码渲染）+ 图像 prompt；生成图后置。
4. **读者 test**：用户确认可招真实读者；按 5+ 人执行；未跑则标 `not_run`，不伪造。
5. **目录/命名**：同意 `src/lunograph/writing/` + `src/lunograph/evidence_access/` + `src/lunograph/media/`；新 skill 目录；原占位 skill 已删除。

---

## 15. 一句话

**把 substrate 变成可分层的证据访问层，把写作变成 skill 驱动的 1 Writer + 可选验证/媒体角色，把多文体变成 3 个簇，把媒体变成 VisualPlan；地图画全，竖切实现，不回头重做底座。**
