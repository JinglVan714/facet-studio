# Writing Layer Contracts（完整设计 v1.0 + EditorialBrief 增补）

> **2026-11-05 session 2**：已由 [writing-v5-architecture.md](writing-v5-architecture.md) 取代；本文件是历史契约设计，不是当前实现契约。

> **2026-11-03 历史状态**：这是早期契约设计，不是当前实现契约。当前写作架构以 [writing-v5-architecture.md](writing-v5-architecture.md) 为准；本文件只作设计历史/假设，冲突时不采用。
>
> 状态：完整契约，供实现使用；**不是 architecture 事实源，不修改 substrate**。
> 上位：[docs/writing-layer-map.md](writing-layer-map.md)；substrate 合同：[docs/substrate-v1-freeze.md](substrate-v1-freeze.md)。
> 日期：2026-11-01（2026-11-02 增补 source-map / EditorialBrief）
> 原则：输入/输出/消费者/失败状态先定；同输入同 hash；不静默截断；reader/audit 分离。

---

## 0. 范围与不变量

本文件定义 writing 层的最小数据契约。实现时可以加字段，但不能改变语义；schema 版本升级时保留兼容字段。

全局不变量：

1. **事实只来自 substrate**：Writer 不新增事实；模型知识只能 editorial（组织/类比/限定）。
2. **Reader/Audit 分离**：reader 文本无内部 ID/citation/时间码/审计语言；audit 侧保留全部指针。
3. **Quote 精确**：正文直接引用必须与 evidence/input 精确匹配；非精确引号由 quote hygiene 去掉引号。
4. **数字精确**：grounded 文本里的阿拉伯数字必须出现在 bound evidence/input；不四舍五入、不换算单位。
5. **不静默截断**：超预算记录 `over_budget`；caption cap 报告 `caption_truncated`/`caption_full_chars`；coverage 记录 dropped/unreported。
6. **失败一等**：partial/failed/unknown 显式；不产出成功 artifact；不自动发布。
7. **同输入同 hash**：request/skill/evidence/context/prompt/visual plan 都可 hash；旧 artifact 冻结、可 replay。
8. **生成图/派生图不当证据**：derived/generated 标 `editorial`；real frame 才可作 video evidence。

---

## 1. 版本 / ID / Hash

- 所有 schema 带 `schema_version`；所有 artifact 带 `*_hash`（sha256 of canonical JSON/text）。
- ID 前缀：
  - `req_` WritingRequest
  - `sk_`/`skill_` SkillManifest
  - `ci_` consume-index
  - `ctx_` WorkingContext
  - `tp_` TaskPlan
  - `eb_` EditorialBrief
  - `wp_` WritingPlan（legacy）
  - `wo_` WriterOutput
  - `vr_` VerifierReport
  - `vp_` VisualPlan
  - `va_` VisualAsset
  - `run_` RunRecord
  - `call_` ModelCallRecord
  - `tc_` ToolCallRecord
  - `dec_` DecisionRecord
  - `ec_` EvalCase
  - `er_` EvalRun
  - `pr_` PublishReview
- 同一输入同 hash；不同 skill/prompt/evidence 版本必须 hash 不同。

---

## 2. `WritingRequest`（`writing-request-v1`）

```json
{
  "schema_version": "writing-request-v1",
  "request_id": "req_...",
  "video_ids": ["BV17DHC6CELr"],
  "method_id": "reader_first_explainer",
  "form_id": "article",
  "style_id": null,
  "central_question": "...",
  "job_to_be_done": "...",
  "reader_before_state": "...",
  "desired_reader_outcome": "...",
  "success_criteria": ["..."],
  "required_information": ["..."],
  "forbidden_information": ["..."],
  "language": "zh",
  "platform": "markdown",
  "risk_level": "low|medium|high",
  "audit_level": "none|claim|boundary|reuse",
  "sections_required": 1,
  "brief_mode": "auto|none|mini|full|human_review",
  "media_policy": {
    "allowed_kinds": ["real_frame", "table", "chart", "diagram", "text_experiment", "no_visual"],
    "max_assets": 6,
    "generated_image_policy": "editorial_only",
    "real_frame_policy": "only_if_relevant"
  },
  "length_advisory": {"unit": "chars", "target": null, "min": null, "max": null},
  "source_policy": {
    "substrate_facts": true,
    "model_knowledge": "editorial_only",
    "user_supplements": false,
    "external_web": false
  },
  "profile_override": null,
  "created_by": "user|system",
  "request_hash": "..."
}
```

字段规则：

- `central_question` 是读者问题，不是视频主题；`job_to_be_done` 是写作任务。
- `reader_before_state`/`desired_reader_outcome` 用于 skill 的读者模型；不写空话。
- `required_information`/`forbidden_information` 是内容约束，不是长度/风格硬门。
- `audit_level` 决定是否走 claim path：`none` 默认 light；`claim`/`boundary`/`reuse` 条件启用 claim_lean。
- `sections_required` 用于判断是否 sectioned；不是硬长度，也不是 brief 的节数。
- `brief_mode` 默认 `auto`；`none/mini/full/human_review` 可覆盖策略。`auto` 由 source topology/长度/风险/预算决定，不在契约里写死阈值。
- `profile_override` 可强制 `full_text|claim_lean|index_parts|sectioned`；记录 DecisionRecord。
- `request_hash` 冻结后不得改；改 request 需新 request_id。

## 2A. `ReaderExperienceContract`（嵌入 request/skill）

```json
{
  "experience": "video_equivalent",
  "toc_required": true,
  "visual_first": true,
  "model_knowledge": "explanatory",
  "heading_contract": "specific_parallel_toc",
  "visual_policy": {
    "prefer": ["diagram", "chart", "table", "real_frame"],
    "real_frame_only_if_readable": true,
    "generated_image_policy": "editorial_only",
    "no_visual_requires_reason": true
  }
}
```

规则：

- **video_equivalent**：读者没看视频也能复述 central question、机制/流程、关键例子/演示/画面、作者判断与边界；不是 coverage 摘要。
- **toc_required**：title + H2 构成可读目录；每个 H2 具体、平行、能单独说明本节讲什么；禁止空泛“背景/介绍/总结”。
- **section promise/takeaway**：每节明确“解决什么/带走什么”；结尾一句 takeaway；不逐节 recap。
- **visual_first**：机制/流程/架构/对比/数字优先 diagram/chart/table/real frame；没有合适图时 text/no_visual 并说明；生成图 editorial。
- **model_knowledge=explanatory**：模型可用自身知识解释/类比/组织背景；不得伪造视频事实/数字/引语。
- 这些是 skill rubric/人工/reader test 的检查项，不是 per-form 硬 validator。

---

## 3. `SkillManifest`（`writing-skill-v1`）

```json
{
  "schema_version": "writing-skill-v1",
  "skill_id": "reader_first_explainer",
  "kind": "method|form|style|output",
  "version": "0.1.0",
  "description": "Use when ... (what + when)",
  "forms": ["article", "deep_analysis"],
  "compatible_methods": ["reader_first_explainer"],
  "required_evidence": ["edited_text", "frames"],
  "output_contract": "markdown",
  "media_policy": {
    "allowed_kinds": ["real_frame", "table", "chart", "diagram", "text_experiment", "no_visual"],
    "max_assets": 6,
    "generated_image_policy": "editorial_only"
  },
  "quality_rubric": "reader-first-v1",
  "examples": ["examples.md"],
  "references": [],
  "scripts": [],
  "assets": [],
  "sources": ["SOURCES.md"],
  "manifest_hash": "..."
}
```

包结构：

```text
skills/writing/<skill_id>/
  manifest.json
  SKILL.md          # <500 行；角色/读者/方法/证据纪律/输出契约/self-review
  examples.md       # 2-3 组好/坏对照
  rubric.md         # 人评维度
  references/       # 可选；一层深；>100 行加 TOC
  scripts/          # 可选；确定性/脆弱操作；执行不回读代码
  assets/           # 可选；模板
  SOURCES.md        # license/借用/改动
```

规则：

- `description` 第三人称、含关键词、写清“做什么+何时用”；避免与同簇 skill 重叠。
- 有副作用 skill 用 `disable-model-invocation`/显式 `/name`；不靠语义误触发。
- `allowed-tools` 不是安全边界；权限/hooks 在执行层。
- Skill 不持有事实、不替代校验；Writer 输入由 orchestrator 组装。
- 版本/hash：自建 manifest/hash；API 用 `skver_...` 固定快照；Claude Code 不读 `version`。

---

## 4. `consume-index-v1`

由现有 substrate 产物确定性派生；不改 substrate。

```json
{
  "schema": "consume-index-v1",
  "video_id": "BV17DHC6CELr",
  "timebase": "ms",
  "source": {
    "light_pack_sha256": "...",
    "edited_sha256": "...",
    "source_map_sha256": "...",
    "pack_id": "ep3_..."
  },
  "segments": [
    {
      "segment_id": "seg1",
      "label": "...",
      "t_start_ms": 120,
      "t_end_ms": 37330,
      "part_id": "part_01",
      "block_index": 0,
      "text_start": 0,
      "text_end": 337,
      "sentence_ids": ["seg1-s001"],
      "passage_ids": ["seg1-p01"],
      "claim_ids": ["c_..."],
      "frame_ids": ["00000_000015000"]
    }
  ],
  "claims": [
    {
      "claim_id": "c_...",
      "segment_id": "seg1",
      "status": "supported|bounded",
      "kind": "fact|opinion|experience|inference|instruction",
      "t_start_ms": 120,
      "t_end_ms": 31310,
      "block_index": 0,
      "part_id": "part_01",
      "evidence_ids": ["ev_..."],
      "source_assertion_ids": ["seg1-a000"]
    }
  ],
  "sentences": [
    {
      "sentence_id": "seg1-s001",
      "segment_id": "seg1",
      "t_start_ms": 120,
      "t_end_ms": 8200,
      "block_index": 0,
      "text": "..."
    }
  ],
  "frames": [
    {
      "frame_id": "00000_000015000",
      "t_ms": 15000,
      "slot_end_ms": 45000,
      "strategy": "fixed_interval|scene",
      "file": "frames/00000_000015000.jpg",
      "caption": "...",
      "caption_chars": 98,
      "segment_ids": ["seg1"]
    }
  ],
  "parts": [
    {
      "part_id": "part_01",
      "block_from": 0,
      "block_to": 2,
      "segment_ids": ["seg1", "seg2"],
      "chars": 1200
    }
  ]
}
```

派生规则：

- `segments`: 来自 contract/outline/pack + source_map 的 `text_start/end`、sentence/passage/claim/frame IDs。
- `claims`: 来自 claims.json + pack evidence；时间来自 passage（不是 anchor），需在 `lookup_claim` 中说明。
- `frames`: 来自 raw `frames_index`（保留 `slot_end_ms`）；不要直接喂 `pack_from_claims` 的 top-level frames（形状不兼容），先 normalizer。
- `parts`: 按 block 预算分组；oversize 保留并标记。
- 物化映射：`claim→block/part`、`frame→segment/claims`、`sentence→block`；一次遍历确定性生成。
- 无 ID 的 KB/Grep 不能当证据源；Grep 只用于定位 part/claim。

---

## 5. `WorkingContext`（`working-context-v1`）

```json
{
  "schema_version": "working-context-v1",
  "profile": "full_text|claim_lean|index_parts|sectioned|multi_source",
  "scope": {
    "video_ids": ["BV..."],
    "segment_ids": [],
    "part_ids": [],
    "time_range": null
  },
  "text": "...",
  "parts": [
    {
      "part_id": "part_01",
      "segment_ids": ["seg1"],
      "chars": 1200,
      "est_tokens": 900,
      "text_ref": "parts/part_01.md"
    }
  ],
  "claims": [
    {
      "claim_id": "c_...",
      "text": "...",
      "status": "supported|bounded",
      "scope": "...",
      "t_start_ms": 120,
      "t_end_ms": 31310,
      "evidence_ids": ["ev_..."]
    }
  ],
  "frames": [
    {
      "frame_id": "00000_000015000",
      "t_ms": 15000,
      "file": "frames/00000_000015000.jpg",
      "caption": "...",
      "capture_method": "vlm|ocr|none",
      "caption_truncated": false
    }
  ],
  "visual_opportunities": [
    {
      "kind": "real_frame|table|chart|diagram|generated_image|image_prompt|none",
      "reason": "...",
      "evidence_ids": ["ev_..."],
      "frame_ids": ["..."],
      "data_ref": null
    }
  ],
  "budget": {
    "context_budget_tokens": 30000,
    "actual_tokens": 2208,
    "over_budget": false,
    "excess_tokens": 0
  },
  "selection": {
    "considered": 0,
    "selected": 0,
    "dropped": [],
    "reasons": {}
  },
  "coverage": {
    "segments_total": 8,
    "segments_used": 8,
    "claims_total": 37,
    "claims_used": 37,
    "frames_considered": 56,
    "frames_used": 16,
    "unreported": []
  },
  "source_map_ref": "source_map.json",
  "context_hash": "..."
}
```

规则：

- `full_text`: `text` = compiled edited text；`claims=[]`；Writer 文本无 ID/时间码。
- `claim_lean`: `claims` + `context` + frames；Writer 不看完整 transcript；claim 时间来自 passage，需标注。
- `index_parts`: `text` 可为空/摘要；`parts` 给出 part 列表；Writer 读 part 文件。
- `sectioned`: 每个 section 一个 context；`parts` 是当前 section 的 part。
- `visual_opportunities` 是 editorial hint，不是事实；Writer 可用它安排段落，但不输出 spec。
- `budget`/`selection`/`coverage` 是 audit-only；不进 Writer 正文。
- 超预算不硬截断；分区/oversize/记录。

---

## 6. `TaskPlan` / `source-map` / `EditorialBrief`

### 6.1 TaskPlan（执行 DAG）

```json
{
  "schema_version": "task-plan-v1",
  "task_plan_id": "tp_...",
  "run_id": "run_...",
  "nodes": [
    {
      "task_id": "load_index",
      "kind": "deterministic",
      "capability": "evidence",
      "depends_on": [],
      "status": "pending|running|succeeded|partial|failed|skipped|reused",
      "attempts": []
    }
  ],
  "edges": [["load_index", "plan"]],
  "budget_policy": {"max_calls": 2, "max_tokens": 400000},
  "status": "pending|running|succeeded|partial|failed"
}
```

节点建议：`load_index`、`source_map`、`select_profile`、`brief?`（none/mini/full/human）、`write`、`validate`、`repair?`、`verify?`、`visual_plan?`、`render`、`eval`、`publish_review`。

### 6.2 `source-map-v1`（Planner 的素材视图，柔性）

不是新 substrate，也不是全文摘要；它是从 consume-index / edited text / claims / frames 组装的**地形图**。字段按素材可用性可选；不要求固定 enum。

```yaml
schema_version: source-map-v1
topology: single_argument|multi_topic|multi_perspective|timeline|mixed|unknown
sections:
  - id: "..."
    heading: "..."
    span: "..."
    gist: "..."
anchors:
  - id: "..."
    quote_or_paraphrase: "..."
    span: "..."
    claim_type: measured|hypothetical|opinion|unknown
    speaker: explicit|unknown
    relation: same_modal|cross_modal|none|unknown
    note: "..."
numbers:
  - value: "..."
    span: "..."
    status: measured|claimed|estimated|unknown
frames:
  - frame_id: "..."
    caption: "..."
    readability: "..."
gaps: ["..."]
```

- 被 brief 用作核心证据的 anchor 必须有 `span + claim_type + speaker`；其余可缺省。
- `relation` 只对比较/分数类素材有意义，不要求所有素材都填。
- `topology` 是建议值；`mixed/unknown` 允许，Planner 需在 brief 里说明。
- 生成方式不限定：代码从 index 生成、人工补、或混合。

### 6.3 `editorial-brief-v1`（编辑合同，替代 `WritingPlan`）

Planner 的产物不再是 4–7 节 × 5 字段的章节 schema，而是一页编辑合同。字段可随 `shape` 调整；下列是**最小语义**，不是硬 JSON 校验。

```yaml
schema_version: editorial-brief-v1
brief_id: "eb_..."
status: complete|partial|needs_human|invalid
brief_hash: "..."
shape: narrative|analytical|procedural|comparative|mixed
reader: {knows: "...", asks: "...", wants: "..."}
core_argument: "一句可被同意/反对的判断"
source_question: "素材自己让读者追问的问题"
payoff: "读者最后得到什么"
throughline: "全文只服务的一句话"
spine:
  - move: "读者认知/情境发生了什么变化"
    connector: "because|but|therefore|and|..."
    anchors: ["anchor_id 或短引文"]
    weight: slow|fast|gold|optional
titles:
  - text: "..."
    promise: "读者会期待什么"
    fulfilled_by: "move/anchor"
    chosen: true
stance:
  narrator: first_person_source|host_led|third_person
  speaker_policy: explicit_only|unknown_as_video|...
cut: ["不写什么，为什么"]
challenge: "最强替代角度/反方，为什么没选"
evidence_status: ["measured vs hypothetical", "speaker unknown", "single case"]
notes: "form-specific 自由补充"
```

- **不输出** H2 列表、每节 promise/takeaway、visual slot、图表规格；这些归 Writer/VisualPlanner。
- `spine` 3–7 个 move；`shape` 决定 move 的写法（场景/论证/步骤/对照），不强制一种。
- `anchors` 可引用 ID、短引文或 span；核心论证至少一个，不要求每 move 都有。
- `titles` 至少一个 `chosen: true`；候选 1–3 个，Writer 不猜。标题避免清单式副标题/机制清单；优先素材自己的问题/引语、前后反差、具体悖论。
- `evidence_status` 是提示，不是新 validator；用于标明 measured/hypothetical/claimed/single-case。
- `notes`/扩展字段允许 form-specific 差异；不要为字段完整而编内容。`challenge`/`notes` 可放 2–3 个角度候选；不要砍掉核心论证的最佳支线证据。
- request 不是大纲：`required_information` 是覆盖约束，不是节序；request 像 topic list 时，先找 source question/payoff，并记录 request conflict。
- `brief_hash` 只覆盖语义字段（reader/core/spine/titles/stance/cut/challenge），不覆盖 usage/latency；便于 replay 和盲审对比。

**检查（语义，不是硬门）**：`core_not_cashed`（core 关键词没有 move/anchor 兑现）、`anchor_unverified`（claim type/speaker/span 不确定）、`sequence_conflict`（spine 与 source 发现顺序/challenge 相反）、`title_unfulfilled`（chosen title 没有 `fulfilled_by`）。是否阻断由风险/发布策略决定。

**brief 模式**：`none`（Writer 内 mini-brief）、`mini`（半页）、`full`（一页，多话题/长/复杂）、`human_review`（发布/高风险人审）。不写死阈值；由 request/素材/预算/发布策略决定。

### 6.4 `writing-plan-v1`（legacy）

旧 `WritingPlan`（title + controlling_idea + 4–7 节 × heading/promise/key_example/visual/takeaway）保留为 legacy/replay，不再作为新 run 默认。迁移期 Writer 可把 `writing_plan` 当 brief-like guardrail，但不得把它当固定 section schema；新 run 使用 `editorial-brief-v1`。

---

## 7. `WriterOutput`（`writer-output-v1`）

```json
{
  "schema_version": "writer-output-v1",
  "status": "complete|partial|failed",
  "format": "markdown",
  "title": "...",
  "article": "# ...\n\n...",
  "sections": [
    {"section_id": "sec_1", "heading": "...", "text": "..."}
  ],
  "self_review": {
    "risks": [],
    "uncertain_claims": [],
    "coverage_gaps": []
  },
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "reasoning_tokens": 0,
    "cached_tokens": 0,
    "total_tokens": 0
  },
  "prompt_hashes": {"system": "...", "user": "..."},
  "model": "...",
  "temperature": 0.3,
  "finish_reason": "stop",
  "latency_ms": 0,
  "output_hash": "..."
}
```

规则：

- 默认 prose-only：`article` 是 Markdown；`sections` 可由 heading 派生；不要求 Writer 输出 JSON/ID。
- Writer 可接收可选 `EditorialBrief`；brief 是 angle/promise/throughline/anchors/cut 的护栏，不是 section schema。Writer 自己决定 H2/段落/视觉意图；发现 brief 与素材冲突时以素材为准并记录。
- 无 brief 时，Writer 在 skill 的 before-writing 阶段做 mini-brief；不把 topic list 直接写成文章。
- `self_review` 可选；若 skill 要求，作为 audit 文本；不替代确定性校验。
- Writer 不输出 claim/evidence/timecode；reader 文本无内部 ID；也不输出 brief 字段/plan header。
- 失败：`writer_failed`；保留 raw_response；不进入 render。

## 7A. Repair（最多 1 次）

- **触发**：确定性 validation 为 `partial` 且 failures 含 `binding`（或结构/reader hygiene）；只在 `run=True` 时。
- **输入**：draft + findings（unsupported facts/quotes/outside/structure）+ 同一 evidence/context + 同一 brief（如有）。
- **输出**：同一 skill 的完整 Markdown 修订；不得新增事实/数字/引语/视觉；只修 listed problems。
- **记录**：`mode=repair`、findings、prompt/usage/latency；最多 1 次，不 loop。
- **后处理**：re-validate 一次；仍 partial 则保留修复稿 + failures（不静默成功）。

---

## 8. `BindingReport` / `ValidationReport`

### 8.1 BindingReport（复用 `bind_article`）

```json
{
  "schema": "article-binding-v1",
  "status": "complete|partial",
  "pack_id": "...",
  "input_scope_checked": true,
  "counts": {
    "paragraphs": {"total": 0, "bound": 0, "partial": 0, "unbound": 0},
    "facts": {"total": 0, "bound": 0, "unsupported": 0, "in_input": 0, "outside_input": 0, "format_variant": 0, "coverage": 1.0},
    "quotes": {"total": 0, "bound": 0, "unbound": 0, "unbound_long": 0, "in_input": 0, "outside_input": 0, "coverage": 1.0}
  },
  "paragraphs": [],
  "unsupported_facts": [],
  "outside_input_facts": [],
  "outside_input_quotes": [],
  "quote_unbound": [],
  "notes": []
}
```

### 8.2 ValidationReport（writing 层组合）

```json
{
  "schema_version": "validation-report-v1",
  "status": "complete|partial|failed",
  "structure": {"ok": true, "problems": []},
  "reader_hygiene": {"ok": true, "problems": []},
  "quote_hygiene": {"checked": 0, "kept": 0, "removed": 0},
  "binding": {"status": "complete|partial", "counts": {}},
  "claim_closure": {"ok": true, "problems": []},
  "visual_provenance": {"ok": true, "problems": []},
  "rights": {"ok": true, "problems": []},
  "failures": []
}
```

规则：

- 技术门不等于 reader pass；`complete` 不代表发布通过。
- `binding_failed`/`render_error`/`visual_unbound` 时不出成功 artifact。
- 中文专名只能 paragraph n-gram 覆盖；不能承诺 fact 级核验。

---

## 9. `VerifierReport`（`verifier-report-v1`）

```json
{
  "schema_version": "verifier-report-v1",
  "status": "complete|partial|failed",
  "findings": [
    {
      "finding_id": "vf_...",
      "axis": "support|overreach|scope|attribution|continuity|reader",
      "target": "sec_2/p3/s1",
      "severity": "blocking|major|minor",
      "observation": "...",
      "impact": "...",
      "action": "..."
    }
  ],
  "provenance": {"model": "...", "prompt_hash": "...", "context_hash": "..."}
}
```

规则：

- Verifier 只看文章 + working context；不看 plan/self-review。
- 只读 findings；不改写；不生成替代段落。
- blocking/major → 最多 1 次 revise；不 recheck loop；minor 可记录 known risk。

---

## 10. `VisualPlan` / `VisualAsset`

### 10.1 VisualPlan

```json
{
  "schema_version": "visual-plan-v1",
  "plan_id": "vp_...",
  "entries": [
    {
      "visual_id": "v_...",
      "section_id": "sec_2",
      "kind": "real_frame|frame_sequence|crop|table|chart|diagram|generated_image|image_prompt|text_experiment|no_visual",
      "intent": "...",
      "source": {
        "claim_ids": ["c_..."],
        "evidence_ids": ["ev_..."],
        "frame_ids": ["..."],
        "timecode": {"t_start_ms": 0, "t_end_ms": 0}
      },
      "spec": {
        "chart_type": "bar|line|scatter|histogram",
        "diagram_type": "flow|architecture|causal|timeline|comparison",
        "data": [{"label": "...", "value": 0.0, "unit": null, "source_evidence_id": "ev_..."}],
        "nodes": [],
        "edges": [],
        "table": {"columns": [], "rows": []},
        "prompt": {}
      },
      "caption": "看哪里",
      "provenance": {
        "source_type": "real_frame|derived_chart|derived_diagram|derived_table|generated_image|prompt",
        "renderer": "svg|mermaid|graphviz|matplotlib|latex|image_model",
        "editorial": false,
        "rights": "..."
      },
      "checks": {
        "frame_exists": true,
        "data_bound": true,
        "relations_bound": true,
        "generated_labeled": true,
        "caption_ok": true
      }
    }
  ]
}
```

### 10.2 VisualAsset

```json
{
  "schema_version": "visual-asset-v1",
  "visual_id": "v_...",
  "path": "assets/visual_001.svg",
  "kind": "chart|diagram|table|real_frame|crop|generated_image",
  "source_type": "real_frame|derived_chart|derived_diagram|derived_table|generated_image",
  "source_ids": {"claim_ids": [], "evidence_ids": [], "frame_ids": []},
  "renderer": "svg|mermaid|graphviz|matplotlib|latex|image_model",
  "renderer_version": "...",
  "data_hash": "...",
  "figure_manifest": "...",
  "caption": "看哪里",
  "editorial": true,
  "rights": "...",
  "checks": {}
}
```

规则：

- `real_frame/crop/frame_sequence` 才可作 video evidence；`derived_*`/`generated_image` 是 editorial。
- `chart` 每个数据点带 `source_evidence_id`；无数据不画。
- `diagram` 每个 node/edge 带 source claim/relation；不补边。
- `generated_image` 带 prompt/model/seed/license/editorial=true；不承担证据功能。
- `caption` 只写“看哪里”；不写正文摘要；generated 标“AI 生成示意图”。
- `figure_manifest` 记录 renderer code version/data hash，可重渲染审计。
- C2PA/SynthID/IPTC 是信号，不是真伪判决；元数据可被剥离。

---

## 11. `OutputBundle` / Audit / Citations

```text
runs/<run_id>/
  run.json
  request.json
  skill/
    manifest.json
    SKILL.md
    examples.md
    rubric.md
    SOURCES.md
  evidence/
    consume_index.json
    working_context.json
    source_map.json
    coverage.json
  brief/
    brief.json          # editorial-brief-v1（full/mini；可为空）
    brief_review.json   # 可选：盲审/人审记录
    decisions.jsonl
  plan/
    task_plan.json
    writing_plan.json   # legacy only
  prompts/
    system.txt
    user.txt
  writer/
    raw_response.md
    article.md
    writer_output.json
  validation/
    structure.json
    reader_hygiene.json
    quote_hygiene.json
    binding.json
    validation_report.json
  verifier/
    report.json
  visual/
    plan.json
    assets/
    provenance.json
  output/
    reader.md
    audit.json
    citations.json
  eval/
    deterministic.json
    reader_test.json
    ab_test.json
  publish_review.json
  trace.jsonl
  tool_calls.jsonl
```

`audit.json` 至少包含：

- request/skill/evidence/context/prompt hashes；
- binding/validation/verifier/visual provenance；
- gaps/conflicts/known risks；
- citations 指针；
- failure/partial 状态。

`citations.json` 诚实粒度：

- sentence/evidence：ID + timecode；
- block：精确字符区间；
- claim/evidence：pack ID；
- paragraph→claim/segment、frame→claim、中文专名：标 `approximate`；
- 不承诺 span 级语义引用。

---

## 12. `RunRecord` / `ModelCallRecord` / `ToolCallRecord` / `DecisionRecord`

### 12.1 RunRecord

```json
{
  "schema_version": "run-record-v1",
  "run_id": "run_...",
  "request_hash": "...",
  "skill_hash": "...",
  "evidence_index_hash": "...",
  "context_hash": "...",
  "profile": "full_text|claim_lean|index_parts|sectioned|multi_source",
  "status": "complete|partial|failed|unknown",
  "stages": [],
  "usage": {},
  "latency_ms": 0,
  "cache": {"hit": false},
  "errors": []
}
```

### 12.2 ModelCallRecord

```json
{
  "call_id": "call_...",
  "stage": "writer",
  "model": "...",
  "provider": "...",
  "params": {"temperature": 0.3, "max_tokens": 0},
  "system_hash": "...",
  "user_hash": "...",
  "system_path": "prompts/system.txt",
  "user_path": "prompts/user.txt",
  "raw_response_path": "writer/raw_response.md",
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "cached_tokens": 0},
  "latency_ms": 0,
  "finish_reason": "stop",
  "validation": "complete|partial|failed",
  "decision": "...",
  "cached": false,
  "error": null
}
```

### 12.3 ToolCallRecord

```json
{
  "call_id": "tc_...",
  "tool_name": "lookup_claim|lookup_frame|bind_article|render_visual|...",
  "arguments": {},
  "result": {},
  "error": null,
  "latency_ms": 0,
  "idempotency": "key|none"
}
```

### 12.4 DecisionRecord

```json
{
  "decision_id": "dec_...",
  "stage": "profile|skill|verifier|revise|visual|publish",
  "question": "...",
  "candidates": [],
  "selected": "...",
  "basis": "...",
  "measured": {},
  "consequences": "...",
  "created_at": "..."
}
```

---

## 13. `EvalCase` / `EvalRun` / `ReaderTest` / `ABTest`

### 13.1 EvalCase

```json
{
  "schema_version": "eval-case-v1",
  "case_id": "case_...",
  "video_id": "BV...",
  "request_path": "evals/writing/requests/BV17.json",
  "request_hash": "...",
  "skill_id": "...",
  "skill_version": "...",
  "baseline": "generic_prompt|previous_skill",
  "checks": ["structure", "reader_hygiene", "binding", "visual_provenance"],
  "split": "dev|holdout"
}
```

### 13.2 EvalRun

```json
{
  "schema_version": "eval-run-v1",
  "eval_id": "er_...",
  "cases": [],
  "results": [
    {
      "case_id": "...",
      "status": "complete|partial|failed",
      "usage": {},
      "latency_ms": 0,
      "validation": {},
      "reader_test": null,
      "ab_test": null
    }
  ],
  "summary": {}
}
```

### 13.3 ReaderTest

```json
{
  "schema_version": "reader-test-v1",
  "reader_count": 5,
  "method": "blind|open",
  "questions": [],
  "responses": [
    {"reader_id": "r1", "answers": [], "attestation": true}
  ],
  "summary": {"pass": 0, "partial": 0, "fail": 0},
  "provenance": {"curated": false, "simulated": false}
}
```

### 13.4 ABTest

```json
{
  "schema_version": "ab-test-v1",
  "reader_count": 5,
  "dimensions": ["comprehension", "accuracy", "expression", "structure", "memory", "willingness"],
  "order_randomized": true,
  "responses": [],
  "summary": {"ours": 0.0, "baseline": 0.0, "preference_rate": 0.0},
  "provenance": {"curated": false, "simulated": false}
}
```

规则：

- `simulated=true`/`curated=true` 只能 advisory；不能写 reader pass。
- 个人数据只放 `runs/`；`evals/` 放匿名汇总/attestation。
- 至少 2 视频 × 2 文体才做通用结论。

---

## 14. `PublishReview`（`publish-review-v1`）

```json
{
  "schema_version": "publish-review-v1",
  "run_id": "run_...",
  "reader_hash": "...",
  "audit_hash": "...",
  "citations_hash": "...",
  "reader_test": {"path": "...", "status": "pass|partial|fail|not_run"},
  "ab_test": {"path": "...", "status": "pass|partial|fail|not_run"},
  "expert_review": {"path": "...", "status": "..."},
  "checklist": {},
  "known_risks": [],
  "status": "approved|blocked|needs_human",
  "publish_approved": false,
  "approved_by": null,
  "approved_at": null
}
```

规则：

- 人工 `publish_approved` 是唯一发布门；不自动发布。
- 技术门全过 ≠ 发布通过；reader test/A-B 缺失标 `not_run`，不伪造。
- 对外发布前检查 rights/生成图标注/引用。

---

## 15. 失败状态

| 状态 | 含义 | 出口 |
|---|---|---|
| `index_incomplete` | consume-index 缺映射 | 修复/显式 partial |
| `source_map_incomplete` | source map 缺拓扑/anchor/speaker/claim type | 退回全文/unknown；不猜 |
| `evidence_insufficient` | context 不足以回答 central question | Writer 只写 boundary；标 partial |
| `over_budget` | 超 advisory 预算 | 分区/记录；不静默删 |
| `skill_not_found`/`skill_incompatible` | skill 缺失/不兼容 | 报错；不猜 |
| `brief_invalid` | TaskPlan/EditorialBrief 不合法 | 修复/报错；可退回 none/mini |
| `writer_failed` | 结构/绑定/输出不合法 | 最多 1 次 repair；保留 raw |
| `provider_outcome_unknown` | 可能已调用但结果未知 | 不自动重放 |
| `binding_failed` | grounded span 缺 binding/quote/ID | 不 render 成功 artifact |
| `verifier_failed` | Verifier 输出无效 | 不当 supported |
| `visual_unbound` | 图表/示意图数据/关系未绑定 | 不 render |
| `render_error` | 渲染/媒体/reader hygiene 失败 | 报错/partial |
| `eval_incomplete` | reader test/A-B 未完成 | 标 not_run；不冒充 |
| `publish_blocked` | 缺人工批准 | 等人工 |

---

## 16. 文件/目录约定

- 代码：`src/facet_studio/writing/`、`src/facet_studio/evidence_access/`、`src/facet_studio/media/`；不修改 `writing_v3`。
- Skill：`skills/writing/<skill_id>/`；新 skill 目录；占位已删除。
- 评测：`evals/writing/requests/`、`evals/writing/cases/`、`evals/writing/protocols/`。
- 运行产物：`runs/<run_id>/`（git ignored）。
- 文档：`docs/writing-layer-map.md`、`docs/writing-layer-contracts.md`、`docs/writing-skill-study.md`、`docs/jd-evidence.md`（后建）。

---

## 17. 实现前检查清单

- [ ] request/skill/index/context 字段与消费者明确。
- [ ] 每个 profile 的输入/输出/失败状态明确。
- [ ] `consume-index-v1` 覆盖 segments/claims/sentences/frames/parts；映射闭合。
- [ ] frames_index normalizer；source_map block 偏移；coverage/over_budget。
- [ ] Writer 输入无 ID/时间码/audit 字段。
- [ ] Validator 复用 `bind_article`/`quote_hygiene`；不手改 claim/reader。
- [ ] VisualPlan 的 source/provenance/checks 完整；generated 标 editorial。
- [ ] trace/usage/decision/tool receipt 落盘；可 replay。
- [ ] eval 固定 case + holdout；reader test/A-B 真实。
- [ ] 不自动发布；人工 `publish_approved`。

---

## 18. 未决

- `context_budget_tokens` 的初始值：按模型有效上下文/成本测量，不写死。
- `segments_required`/`sections_required` 的判定：按 request/skill，不按单视频。
- `claim_lean` 的 claim 时间来自 passage 还是 anchor：当前 passage；需要时补 anchor。
- `index_parts` 的 part 选择：确定性 scope/section 映射 vs bounded planner；先确定性。
- `visual_plan` 的模型参与：先确定性候选；分类/系列/轴需要视觉模型后再加。
- `sectioned` 的整合：deterministic merge + 一次总检；不做多轮瀑布。
- 多源/企业知识的冲突/权限契约：后置。
