# Substrate View 拆分设计：comprehension / audit 两层

> 状态：**实验记录**（2026-11-01）；builder + merged_frames grounding adapter 已实现，但**不是当前基线**。当前方向见 [HANDOFF.md](../HANDOFF.md) §0。
> **2026-11-01 方向修正（重要）**：本文的 dual-mode builder / grounding adapter / Writer 3 modes 是实验产物；当前方向是**一个保序 thinned text + prose-only Writer + 代码事后 binding + full pack audit**，不再扩 mode/coverage tier/adapter。本文保留作实验记录，后续可能折叠。
> 上位：[architecture.md](../architecture.md) §5.3 / §7 / §9；[substrate-view-contract.md](substrate-view-contract.md)；[AGENTS.md](../AGENTS.md)。
> 证据：`runs/s2_probe/run/analysis.md`、`run_v2/analysis.md`、`run_b_frames/analysis.md`、`run/BV1yb/analysis.md`、`runs/s3_boundary/analysis.md`、`binding_check.md`。

## 1. 为什么要拆

S2/S3 probe 的结论：

| 场景 | 最优输入 | 证据 |
|---|---|---|
| 短视频（BV1AC/BV17）+ 文本理解 | **merged text + frames** | 36/36，与 lean view 同分；prompt tokens 只有 lean view 的 55%–60% |
| 短视频 claims/context/IDs | 不赚 comprehension 成本 | 相对 B+frames 多 2k–3k prompt tokens、0 分 |
| 长视频（BV1yb 28.2min） | **lean view cw0** | 14/14；prompt 6,114 vs B 7,100；boundary 修复后仍 14/14 |
| 长视频 index+parts | 28min/8parts 不回本 | 宽题 8,066 prompt vs one-shot 6,114；窄题 7,406 vs 5,997 |
| claim 层 | **audit / binding / boundary / reuse** | 18/18 关键事实可回查；boundary claim 修复 q5 |

问题不是“claim 层有没有用”，而是**把它放在哪一层**：它不该默认进入短视频的 comprehension 输入，但它是 audit/binding/boundary 的必要材料。

## 2. 两层模型

```text
EvidenceSnapshot
  → full pack（唯一事实/审计源）
       ├─ comprehension view（Writer 读）
       │    ├─ mode=merged_frames（短/中）
       │    └─ mode=lean_cw0（长）
       └─ audit view（binding/citation/验证/人工；Writer 不读）
```

- **comprehension view**：只带写作所需字段；不新增事实；按请求/规模选 mode；超预算只报告/换 mode，不硬删。
- **audit view**：full pack 原样；claims/evidence/quote/timecode/frames/provenance/selection/coverage；用于确定性绑定、citation、验证、人工审计。
- 两层都来自同一 full pack；同一 evidence ID/quote/timecode 保持一致。

## 3. comprehension view 的两种 mode

### 3.1 `merged_frames`（短/中）

内容：

- merged passages（段落 ID + 时间范围 + 原文）；
- 每段的 frame 候选（frame_id + caption，caption 只写“看哪里”）；
- 不带 claims/evidence/IDs/context JSON、不带 provenance/selection/coverage。

适用：

- 短视频、文本理解为主、需要视觉证据；
- 转录本身还不大，merged text + frames 在一个 advisory 预算内；
- 请求只需要机制/步骤/边界，不需要 per-claim binding 作为 Writer 输入。

证据：BV1AC/BV17 v2 36/36；prompt tokens 4,367 / 2,449，vs lean view 7,326 / 4,487。

边界证据：短视频的完整转录通常包含 limitation；Writer 仍要在正文里处理边界，audit view 的 bounded claims 用于复核。若短内容也有重要显式限制，可在 `merged_frames` 末尾加一个小的 `boundaries` 块（bounded claim 的 text/scope，不带 quote/ID），但这是待验证项，不默认。

### 3.2 `lean_cw0`（长）

内容：

- claims：claim_id/text/status/scope/evidence（quote→span 或 quote fallback）；
- context：**只保留 claim 的 anchor sentences**（context_window=0），不补邻居；
- frames：frame_id + caption；
- 不带 provenance/selection/coverage/truncation。

适用：

- 长视频/大内容，merged text + frames 超过 advisory 预算；
- 需要 claim/selection 压缩上下文，且需要 boundary claims；
- 请求以机制/论证/边界为主。

证据：BV1yb cw0 14/14；prompt 6,114 vs B 7,100、vs cw2 7,643；3 个 case 无回退。

Boundary：`status="bounded"` + `scope` 是显式限制；view 消费说明要求边界问题优先使用这些 claim（S3 修复后 BV1yb q5 1→2）。

### 3.3 mode 选择（advisory，不做硬门）

渲染两个候选，用 [core/tokens.py](../src/lunograph/core/tokens.py) 的 offline 估计：

- 显式 `mode` → 用它；
- 给 `budget_tokens` → `merged_est <= budget` 用 `merged_frames`，否则 `lean_cw0`；
- 不给 budget → 选 `est_tokens` 更小的 mode（auto 默认）。

记录 `chars`/`est_tokens`/`mode`/`reason`/`over_budget`；`budget_tokens` 只作 advisory/over_budget 记录，**不是质量门**。

- 请求/Skill 可以显式指定 mode（如 frame-heavy 请求优先 merged_frames；长机制文优先 lean_cw0），但必须记录原因。
- 不做按视频手选；同一规则跨视频。
- 不硬截断：超预算只换 mode/记录，不删除 claims/context/frames。
- `index+parts` 不默认：28min/8parts 宽窄题都不回本；只有 bundle 远大于 lean view、或 selector 能稳定只选 1–2 parts 时才考虑；需要更便宜的 selector 再评估。

**实现（2026-11-01，未接 Writer/binding）**：[comprehension_view.py](../src/lunograph/writing_v3/comprehension_view.py)；5 tests。auto 在 3 个 case 上与 probe 预期一致：

| case | merged_frames est | lean_cw0 est | auto |
|---|---:|---:|---|
| BV1AC | 5,650 | 7,738 | merged_frames |
| BV17 | 2,282 | 4,854 | merged_frames |
| BV1yb | 8,105 | 6,845 | lean_cw0 |

builder 使用 pack 的完整 frame captions（不再加 80-char 截断）；旧 `writer_view` 的 80-char cap 仍是待处理项。

## 4. audit view

- full pack 原样；是唯一 fact/audit 源。
- Writer 不读；用于：
  - grounded span → claim/evidence/quote/timecode/frame 的确定性绑定；
  - citation 派生（同 evidence 合并）；
  - reader hygiene/数字/专名的回查；
  - 人工审计/gaps/conflicts/boundary 复核。
- audit view 可以超 advisory 预算；不得为了 audit 体积删除 comprehension 内容。

## 5. Writer output 与 binding 的影响

这是拆分后最需要设计的地方。

### 5.1 `lean_cw0`

- Writer 看到 claim/evidence IDs；输出 grounded span 带 `claim_ids`/`evidence_ids`/`quote`（现有 schema）。
- 确定性校验：ID 在 pack；quote ∈ evidence；quote ∈ sentence 拼接；数字在 bound evidence。
- 与现有 `one_call_writer` 的 span/quote/数字校验兼容。

### 5.2 `merged_frames`

- Writer 看不到 claim/evidence IDs；不能要求它输出这些 ID。
- Writer 输出 grounded span 用 **passage/frame + quote** 作为 grounding：
  - `passage_id` + `quote`（可选 `t_start_ms`/`t_end_ms`）；
  - 视觉 span 用 `frame_id` + “看哪里” caption。
- 具体 `grounding_ref`：
  ```json
  {"passage_id":"seg7-p11","quote":"我可能帮不上你的大忙，但是我给你情感的一个认可。"}
  {"frame_id":"00012_000061061","caption":"看这里"}
  ```
- **adapter 已实现**：[bind_merged_frames.py](../src/lunograph/writing_v3/bind_merged_frames.py)；确定性、不 fuzzy、不新增事实。
  - 文本：quote 必须 ∈ passage 文本；在 passage 的 sentence 范围内找包含该 quote 的 evidence；唯一 → `bound`；多个 → `ambiguous`（列出全部 candidates）；quote 覆盖多个 evidence → `partial`；quote 在 passage 但不在任何 evidence → `unbound`；passage 不存在/quote 不在 passage → `error`。
  - 视觉：`frame_id` 必须存在 → `frame_bound`；caption 只作 reader-facing 提示，不要求等于 VLM caption（记录 `caption_matches`）。
  - 报告：`status=complete|partial|failed` + counts（bound/partial/ambiguous/unbound/frame_bound/error/editorial）；不静默。
  - 真实数据检查：BV1yb “可能帮不上你的大忙…” → `ev_9c71eb720693` / `c_9c71eb720693` / 1,464.3–1,475.9s；frame → `frame_bound`。
- Writer output schema 需要新增可选 `grounding_ref`；`claim_ids`/`evidence_ids` 在 merged_frames 模式下为空，由 adapter 生成独立 binding report（不回写 Writer 输出）。
- 现有 `one_call_writer` 仍是旧 schema；Writer 接线时要让它输出 `grounding_ref`，再把 adapter 接到 deterministic 校验/render。3 个 case 的结构化 Writer output 还没跑。

### 5.3 共同不变量

1. 每个 grounded span 最终必须能回查 full pack 的 evidence/claim/timecode；不能回查 → 失败/partial。
2. editorial span 不带绑定。
3. reader 文本不出现 ID/citation/时间码/审计语言。
4. 同一 evidence 在不同文体中引用一致。

## 6. 不变量（拆分本身）

1. full pack 是唯一事实/审计源；comprehension view 是投影，不新增事实。
2. 不硬截断；超预算 → advisory/换 mode/报告，不删内容。
3. Writer-facing view 不带 provenance/selection/coverage/truncation/hashes。
4. 同一输入同 hash；mode 决策可 replay。
5. 不按单视频/单文体调 mode；≥2 视频复现才进通用层。
6. 不删 claim 层；audit/binding/boundary/reuse 仍需要。
7. 不为每个文体加 pipeline/validator/gate；通用校验只做 binding/quote/ID/结构/hygiene。

## 7. 未决问题

1. **comprehension_budget 的度量**：chars 还是 tokens？当前用 chars/token 粗估；有真实 tokenizer 后再校准。预算默认值需要 3+ cases 测量，不写死质量含义。
2. **merged_frames 的 grounding 映射精度**：quote/passage/time → evidence/claim 的唯一性；多命中/无命中怎么记录；需要在 BV1AC/BV17/BV1yb 上测。
3. **短视频的 boundary 块**：是否在 merged_frames 末尾附加 bounded claims 的 text/scope？附加多少成本、是否提升 q5？先在 ≥2 视频测。
   - 当前 builder 的 merged_frames 不带 gaps/conflicts/segment label（与 probe B+frames 一致）；lean_cw0 带 gaps/conflicts。两者需要统一，待确认。
4. **长视频 cw0 的邻居上下文**：cw0 在 3 个 case 没回退，但指代/隐含因果可能需要邻居；需要更多问题类型/视频。
5. **frame caption 截断**：现有 writer_view 的 80-char cap 是静默截断，与“不硬截断/只报告”冲突；拆分时应改成保留全文+报告，或至少标记 `caption_truncated`。
6. **index+parts 的适用边界**：28min 不回本；需要 >60min bundle 或更便宜 selector 才值得再评估。
7. **mode 选择是否应由请求/Skill 显式指定**：当前提案是 advisory 预算 + 可显式覆盖；需要真实请求样本。
8. **audit view 的消费接口**：citation/binding 代码复用哪些现有模块；v3 还没有独立 audit.json/citations.json。

## 8. 实施阶段

1. **设计确认**（本文）：两层、两种 mode、advisory budget、grounding 方向已确认。
2. **确定性 builder（已实现）**：[comprehension_view.py](../src/lunograph/writing_v3/comprehension_view.py)；两种 mode + auto/budget/explicit + 记录；5 tests；3 case auto 与 probe 预期一致；不改 Writer。
3. **binding adapter（已实现）**：[bind_merged_frames.py](../src/lunograph/writing_v3/bind_merged_frames.py)；quote/passage/frame → full pack evidence/claim/timecode；6 tests；BV1yb 真实数据检查；Writer output 的 `grounding_ref` 还未接。
4. **3 case 复验（部分）**：builder 的 mode/token 估计已复验；adapter 用 BV1yb 真实 quote/frame 检查；3 case 的结构化 Writer output 未跑。
5. **Writer 接线（未开始，writing 阶段，需确认）**：短读 merged_frames，长读 lean_cw0；测真实 Writer tokens/质量；不跑 skill 验收。
6. **之后**才更新 architecture.md、做 skill/reader test。

## 9. 不做

- 不把 full pack 塞给 Writer。
- 不默认 index+parts（28min 不回本）。
- 不为每个文体加 body/validator/gate。
- 不按单视频/单题调 mode 或 budget。
- 不删 claim 层；不把 claim 层当 comprehension 层。
- 不自动发布/不伪造 reader test。
