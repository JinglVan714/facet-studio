# Writing Planner 的定位：从章节大纲到一页编辑 brief

> **2026-11-03 历史状态**：这是 brief 定位的早期设计笔记，不是当前完整契约；当前两层 brief（短编辑 brief + knowledge ledger）、pipeline、评测以 [writing-operating-model.md](writing-operating-model.md) + 当前代码为准。本文件保留“Planner 是角色不是 section schema”的定位，冲突时以 operating model 为准。
>
> 状态：设计/契约（2026-11-02），先于代码。
> 实现：2026-11-02 已接 `source_map.py` → `brief.py` → Writer；`planner.py`/`writing-plan-v1` 仅 legacy；3 个 dev case 的 brief runs 在 `runs/_brief_final3/`；487 tests。
> 核心：Planner 是**角色**，不是固定的一次模型调用、也不是固定的 7 节 schema。它做的是写作前的高杠杆编辑决策；Writer 保留章节、段落、句子和视觉意图的自由。

## 0. 一句话

**Planner 决定“为谁写、回答什么问题、给出什么 payoff、沿哪条 throughline、用哪些锚点、砍掉什么、站在什么位置说”；Writer 决定“怎么分节、怎么组织段落、怎么用图/表”。**

Planning 不是 outline。Outline 是 Writer 的排布结果；brief 是写之前的编辑合同。

## 1. 为什么现在的 Planner 需要换位

当前 `WritingPlan` 是：

```text
title + controlling_idea + 4–7 节 × (heading / promise / key_example / visual / takeaway)
```

它在做三件本不该由前置 Planner 做的事：

1. **提前写章节**：H2、每节 promise/takeaway、visual slot 都定了，Writer 只剩填空；文章容易变成 topic list + 三重编码（场景→表格→总结）。
2. **用一个扁平全文做编辑判断**：它拿到 request + `evidence_text` + frames，没有素材拓扑、claims/evidence、speaker 状态、候选锚点；也没有 skill 的 planning 方法，只有一份硬编码 system prompt。
3. **把不确定性伪装成结构**：7 个 section 看起来很确定，但标题/角度/重点可能一开始就错；盲审三篇都出现“盲读 7 分 → 看素材 6.5 分”，问题集中在 title/topic/emphasis，而不是句子。

BV1yb 的实际成本：planner 约 18.8k tokens / 72s，Writer 约 24.5k / 84s；Planner 约占写作链 38% token，但产出的是一份 11k completion tokens 的详细章节计划。这不是低成本前置。

## 2. 调研结论：planning 的核心是编辑决策

本地参考比当前 Planner 更接近“写作规划”：

- `wp-topic-select`：先判断素材拓扑（单一论点/多话题/多视角/时间线），从读者需求、素材最强内容、差异化、可论证深度、读者收获五个方向发散角度，再做对抗检验；单一论点可以跳过选题。
- `wp-outline-build`：读者画像（知识边界/阅读动机/预期收获）、核心论点（可被同意/反对）、逻辑线、读者追问链、结构选择、节奏（慢镜头/快进/金币）、标题承诺+兑现、对抗检验。
- `great-writer`：core tension、value carrier、core statement、stress test、narrative arc & weight、reader perspective check。

外部研究也支持“不要把 planning 写死成一次 outline”：

- WriteHERE 批评“先生成 outline 再写”的刚性流程，主张规划与写作交错、动态调整；
- WritingPath 证明显式 outline 能提升文本质量；
- 两者共同指向一个折中：**稳定的编辑合同 + 可调整的章节排布**。

结论：

> planning 的核心是 **angle / reader promise / source question / payoff / throughline / reader question chain / anchors / weight / cut / stance**；H2 是 Writer 的事。

## 3. Planner 的定位

Planner 是 **brief editor（编辑简报角色）**：

- 它不写正文、不写 H2、不写每节 promise/takeaway、不分配 visual slot；
- 它把“这篇文章为什么值得读、从哪个角度读、靠哪些素材读、哪些不读”说清楚；
- 它可以是模型调用、Writer 的一个前置 phase、或人给的一页 brief；调用形态是策略，不是契约；
- brief 是**合同/护栏，不是笼子**：Writer 可以在写作中发现 brief 与素材冲突，记录 `brief_conflict`，以素材为准，而不是盲目执行。

## 4. Planner 接收什么

### 4.1 必需

| 输入 | 用途 |
|---|---|
| `request` | 读者 before/after、job、success criteria、forbidden、risk、form；不是章节大纲 |
| `source_map` | 素材的“地形”，不是全文再摘要：拓扑、section/turn、claims/evidence、数字、候选 anchors、speaker/claim 状态、frames、gaps |
| `planning_lens` | skill 的 planning reference（`references/planning.md`），不是 Writer 的完整 skill/examples |

### 4.2 可选（按素材/风险/成本）

- **全文或代表段落**：短视频可给全文；长视频默认给 source map + 代表段落，必要时扩展到相关 part。全文不是问题本身，“全文 + 7 节 schema”才是。
- **2–3 个同文体 brief/title 例子**：只给 taste，不给整包 examples。
- **人的 angle/title 偏好**：发布/高风险时，人可以只改 brief 的一行，而不是重写 7 节大纲。
- **工具结果/外部约束**：平台、长度、版权、必须覆盖/禁止内容；来自 request，不塞进 Writer prompt。

### 4.2.1 request 不是大纲

- `central_question`/`job_to_be_done` 描述读者问题/任务，不应列“形象/定位/互动/原则”这种节序；`required_information` 是覆盖约束，不是顺序。
- 如果 request 本身像 topic list，Planner 应先找 source question/payoff，并在 challenge/notes 里记录 request conflict；不要照抄成 spine。

### 4.3 不该给

- Writer 的风格 examples/完整 skill（角色混淆、token 膨胀）；
- visual slot / 图表规格（视觉应在成稿后由 VisualPlanner 决定）；
- 没有结构的全文 wall（除非短/必要）；
- 未经确认的 speaker 归属（宁可标 `unknown`，不要猜）。

### 4.4 `source-map-v1`（柔性视图）

不是新 substrate，也不是全文摘要。字段是**视图**，按素材可用性可选：

```json
{
  "schema_version": "source-map-v1",
  "topology": "single_argument|multi_topic|multi_perspective|timeline|mixed|unknown",
  "sections": [{"id": "...", "heading": "...", "span": "...", "gist": "..."}],
  "anchors": [
    {
      "id": "...",
      "quote_or_paraphrase": "...",
      "span": "...",
      "claim_type": "measured|hypothetical|opinion|unknown",
      "speaker": "explicit|unknown",
      "relation": "same_modal|cross_modal|none|unknown",
      "note": "..."
    }
  ],
  "numbers": [{"value": "...", "span": "...", "status": "measured|claimed|estimated|unknown"}],
  "frames": [{"frame_id": "...", "caption": "...", "readability": "..."}],
  "gaps": ["..."]
}
```

- 不要求每条 anchor 都完整；但被 brief 用作核心证据的 anchor 必须有 span + claim_type + speaker 状态。
- `relation` 是给对比/分数类素材的；不是所有素材都需要。
- `topology` 是建议值，不是强制 enum；可以写 `mixed`/`unknown`，让 Planner 说明。
- `source_map` 可以由代码从 consume-index 生成，也可以人工补；不绑定某一种实现。

## 5. Planner 输出什么

### 5.1 `editorial-brief-v1`：一页编辑合同

最小决策（按需可省略/扩展）：

```yaml
schema_version: editorial-brief-v1
brief_id: "eb_..."
status: complete|partial|needs_human|invalid
brief_hash: "..."
shape: narrative|analytical|procedural|comparative|mixed
reader:
  knows: "..."
  asks: "..."
  wants: "..."
core_argument: "一句可被同意/反对的判断"
source_question: "素材自己让读者追问的问题"
payoff: "读者最后得到什么（反直觉结论/决定/情绪落点）"
throughline: "全文只服务的一句话"
spine:
  - move: "读者认知/情境发生了什么变化"
    connector: "because|but|therefore|and|..."
    anchors: ["anchor_id 或短引文"]
    weight: "slow|fast|gold|optional"
titles:
  - text: "..."
    promise: "读者会期待什么"
    fulfilled_by: "beat/anchor"
    chosen: true
stance:
  narrator: "first_person_source|host_led|third_person"
  speaker_policy: "explicit_only|unknown_as_video|..."
cut: ["不写什么，为什么"]
challenge: "最强替代角度/反方，为什么没选"
evidence_status:
  - "measured vs hypothetical vs claimed"
  - "speaker unknown"
  - "single case / not a benchmark"
notes: "form-specific 自由补充"
```

### 5.2 柔性规则

- `shape` 决定 spine 的形状：narrative 可以是场景/转折；analytical 可以是问题→证据→判断；procedural 可以是步骤/失败/修复；comparative 可以是对照/边界；mixed 可以组合。不要强推 4–7 节。
- `spine` 3–7 个 move 即可；不需要每节 promise/takeaway；weight 可选。
- `anchors` 可以引用 ID、短引文或 span；**核心论证至少一个 anchor**，不是每个 move 都要。
- `titles` 至少一个 `chosen: true`；可以有 1–3 个候选，但 Writer 不为候选买单。标题避免“A：B、C和D”清单式副标题/“如何...”机制清单；优先素材自己的问题/引语、前后反差、具体悖论。素材有明确问题时，至少给一个基于它的候选。`chosen` 必须是真会发的那个，不是第一个候选；在 notes 写一句为什么它赢。
- `evidence_status` 是提示，不是新 validator；它让 Writer 知道哪些是 measured、hypothetical、claimed、unknown。
- `notes`/`extensions` 允许 form-specific 字段；不要为了字段完整而编内容。

### 5.3 明确不输出

- H2 列表、每节 promise/takeaway、visual slot、图表规格；
- 正文段落、标题党/摘要、reader-facing 的 plan header；
- 未在 source 中确认的 speaker/数字/因果。

## 6. 四个检查（语义，不是硬 validator）

1. **Core cash**：`core_argument` 的每个关键词，至少有一个 spine move + anchor 兑现；没有就标 `core_not_cashed`，先修 brief，不写正文。
2. **Anchor correctness**：核心 anchor 的 `claim_type` / `speaker` / `relation`（same/cross、measured/hypothetical）必须正确；不确定就标 `unknown`，不要猜。
3. **Sequence**：spine 顺序跟 source 的发现顺序，或明确写出重排理由；不能和 `challenge`/`throughline` 相反。
4. **Title fulfillment**：chosen title 必须写 `fulfilled_by`；不能兑现的标题降级为候选或删掉。

附加（建议）：

- **Cut/limits**：明确不写什么、这次不证明什么；防止安装步骤/泛化风险/证据审计吃掉结尾。
- **Brief blind review**：发布/高风险时，让一个不看 source 的读者只看 brief（title/promise/spine）判断“想不想读/期待什么”，再看 source 判断“取重对不对”。这比等 Writer 写完再评便宜得多。

这些检查产生 `brief_incomplete|core_not_cashed|anchor_unverified|sequence_conflict|title_unfulfilled` 等**警告**；是否阻断由风险/发布策略决定，不在契约里写死。

## 7. 条件启用：brief 是策略，不是必经阶段

| 模式 | 何时 | 产物 |
|---|---|---|
| `none` | 极短/单论点/低风险；Writer 的 skill 内有 mini-brief | 不单独产 brief |
| `mini` | 单论点/短中视频；3–5 个决策 | 半页 brief，可由 Writer 同一次调用产生 |
| `full` | 多话题/多视角/长视频/结构不清 | 一页 brief；可先选角度再写 |
| `human_review` | 发布/高风险/品牌敏感 | 人审 brief，必要时人选 title/angle |

- 不写死阈值；由 `request.risk_level`、素材拓扑、长度、预算、发布策略决定。
- 同一套 brief 语义可被不同形态实现：独立模型调用、Writer 前置 phase、人写、或模板 + 人补。
- 默认不要为简单素材多跑一次贵模型；也不要为复杂素材省掉 brief。

## 8. 所有权 / 失败状态

- **Planner**：angle / reader / core / payoff / throughline / spine / anchors / title candidates / stance / cut / challenge。
- **Writer**：H2、段落、句子、例子组织、视觉意图；可以在发现素材冲突时记录 `brief_conflict`，以 source 为准。
- **VisualPlanner**：成稿后的视觉选择；不读 plan visual slot（因为不存在）。
- **Validator**：确定性 binding/structure/hygiene；不把 brief 当文章。
- **人**：发布前审 brief/标题/边界；不自动发布。

失败状态不静默：brief 失败可退回 `none/mini`；Writer 仍可写，但 manifest 记录 `brief_status` 和 warnings。

## 9. 成本 / 质量

- **输入**：source map + request + planning lens；`mini` 默认 source-map-only；`full` 默认再加全文（宿主 `full` 的 tone/争议需要时）。source map 是结构化视图，不是全文摘要。
- **产物**：一页 brief（artifact 约 2–4k chars），不是 11k 的 section schema；但模型 usage 还包含 reasoning，不能按 artifact 大小估算。
- **实测 dev（`runs/_brief_final3/`）**：brief total tokens 约 17.3k（BV17 mini）、31.1k（BV1AC full）、22.3k（BV1yb full）；旧 planner 约 18.8k（BV1yb）。所以 brief **不是天然更便宜**：短/单论点 mini 更省；多话题 full 大约持平或更贵，换来更好的 title/arc/claim typing。不要把“更便宜”当默认结论。
- **调用**：`none` 省一次；`full` 一次；不新增 Verifier/第二 Planner 作为默认。
- **质量门**：brief 盲审/人审比成稿盲审便宜；它检查 title/promise/spine/anchors，而不是句子。
- **不承诺固定节省比例**；以实际 manifest 的 usage 为准；后续可优化 source map/tone anchors/模型选择。

## 10. 迁移

- 新契约 `editorial-brief-v1`；当前 `writing-plan-v1` 标记 legacy，保留 replay/旧 run，不立即删除。
- **已做（2026-11-02）**：
  1. `source-map-v1` 生成器（从 consume-index/edited text）；
  2. `editorial-brief-v1` planner/prompt；
  3. Writer prompt 支持 `writing_brief`（`writing_plan` 作 legacy alias）；
  4. pipeline 支持 `brief_mode`、失败回退、manifest 记录；
  5. 停用 plan visual slots；VisualPlanner 只看成稿。
- **已做 runs**：`runs/_brief_final3/` 三篇 complete；legacy `runs/_final/` 保留 before/after。
- **剩余**：brief 盲审/复核 → 真实 reader test/A-B；不破坏现有 `writing-plan-v1` replay。

## 11. 开放问题（先记录，不写死）

- `source_map` 的拓扑/关系检测：多少算多话题？谁标 speaker？没有 diarization 时如何保守？
- brief 的自动评估：core cash/anchor correctness 能否部分确定性检查？哪些必须人/读者？
- title：默认自动选一个，还是发布/高风险时人从 2–3 个候选里选？
- 不同文体（社媒/报告/教程/剧本）的 brief shape 差异；不要用一个 schema 套所有。
- 全文 vs source map 的切换点：按长度/拓扑/预算，先配置，不写死。
- Brief 失败时 Writer 是否应继续写：低风险可继续并记录；高风险应停/人审。

---

## 附：研究依据

- 本地：[wp-topic-select](../参考素材/skills/Mouriya-Emma__writing-pipeline-zh/writing-pipeline-zh-main/skills/wp-topic-select/SKILL.md)、[wp-outline-build](../参考素材/skills/Mouriya-Emma__writing-pipeline-zh/writing-pipeline-zh-main/skills/wp-outline-build/SKILL.md)、[great-writer](../参考素材/skills/d-wwei__great-writer/great-writer-main/SKILL.md)
- 外部：[WriteHERE / Beyond Outlining](https://aclanthology.org/2025.emnlp-main.1254/)、[WritingPath](https://aclanthology.org/2025.naacl-industry.20/)
- 本轮盲审实验：`runs/_planner_experiment/BV1yb/`、`runs/_planner_experiment/BV17/`、`runs/_planner_experiment/BV1AC/`（已 v2；未再第三轮盲审）。
