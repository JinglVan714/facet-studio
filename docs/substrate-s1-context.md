# Substrate S1-1：上下文覆盖修复

> 状态：完成（2026-10-31）
> 范围：通用 pack builder；确定性；无模型调用。
> 上位：[docs/substrate-s0.md](substrate-s0.md) §3.2 / §6.1；[architecture.md](../architecture.md) §5.3 / §9.1。

## 1. 改了什么

- [pack_from_claims.py](../src/lunograph/writing_v3/pack_from_claims.py)：
  - `_claim_anchor_ids`：为每条 selected claim 找包含其 quote 的最小连续 sentence slice。优先级：claim `sentence_ids` → passage `sentence_ids` → segment sentences → claim sentence_ids fallback；来源写进 pack。
  - `build_pack`：先把所有 anchor sentence 放进 pack，再按 `context_window`（默认 2）补最近邻；`max_sentences_per_segment` 是总上下文预算，anchor 不被它挤掉；超预算的 segment 记入 `over_cap_segments`。
  - `_trim_sentences`：只删非 anchor 句；anchor 永不删；删了哪些句写进 `truncation.dropped_sentence_ids`；如果只剩 anchor 仍超预算，记 `anchors_exceed_budget`。
  - `selection.context`：新增 `claims_total` / `claims_with_context` / `claims_without_context` / `anchor_sentences` / `neighbor_sentences` / `context_sentences` / `over_cap_segments` / `missing_context_claims` / `quote_not_in_claim_sentences` / `anchor_source_counts`。
  - CLI 新增 `--context-window`（默认 2）。
- [test_pack_context.py](../tests/writing_v3/test_pack_context.py)：5 个确定性测试，覆盖 anchor 优先、邻域预算、passage fallback、missing 报告、截断保护。

## 2. Before / After

输入相同：claims / passages / sentences / snapshot / outline / knowledge / request / contract；只改 pack builder。

| 指标 | BV1AC before | BV1AC after | BV17 before | BV17 after |
|---|---:|---:|---:|---:|
| claims selected | 40 | 40 | 28 | 28 |
| claims with context | 24 | **40** | 20 | **28** |
| claims without context | 16 | **0** | 8 | **0** |
| context sentences | 53 | 65 | 33 | 35 |
| anchor sentences | — | 59 | — | 32 |
| neighbour sentences | — | 6 | — | 3 |
| over-cap segments | — | 4 | — | 2 |
| missing anchors | — | 0 | — | 0 |
| pack chars (pretty) | 47,850 | 50,940 | 31,875 | 32,771 |
| pack chars (compact) | 38,200 | 40,650 | 25,421 | 26,099 |
| truncated | false | false | false | false |

- Pack 增长：BV1AC +6.5%（compact +6.4%），BV17 +2.8%（compact +2.7%）。
- BV17 的 before 比 handoff 里的 30,556 高，是因为这次显式传了 outline/knowledge/contract；before/after 用同一组输入，比较的是 delta，不是 P0 绝对值。
- 独立复核：对 after pack 逐条 claim 重新计算 anchor，`zero_anchor_in_pack=0`，`missing_anchor=0`。
- 测试：`tests/writing_v3` 5 passed；全量 309 passed（原 304 + 5）。
- 无模型调用；无单篇调参；无手改 claim/reader。

## 3. 仍然存在的问题

- **Timecode 仍是 passage 级（S1-1 时；S1-2 已修）**：evidence 时间已改为 anchor sentence 并集，见 [substrate-s1-timecode.md](substrate-s1-timecode.md)。
- **Claims 顺序仍是 hash 序**：`pack.claims` 仍按 `(segment_id, claim_id)` 排序；这是 S1-3。
- **BV17 segment labels 仍为空**：pack 只从 contract 取 label，未回退到 outline；这是 S1-3。
- **Over-cap segments**：BV1AC 4 个、BV17 2 个 segment 的 anchors 超过 6，所以这些 segment 没有额外邻域；anchor 句本身保留，Writer 仍能看到每条 claim 的 quote 句。是否提高 cap 由 S2 probe 决定，不现在按单篇调。
- **邻居覆盖不完整**：`neighbor_sentences` 只有 6/3；不是每条 claim 都有 ±2 邻域。当前规则是“anchor 必须，邻域按预算”，S0 的 scorecard 允许这样；S2 再看邻域是否影响理解/写作。

## 4. 下一步

- S1-2：已完成，见 [substrate-s1-timecode.md](substrate-s1-timecode.md)。
- S1-3：claims 按 passage/time 排序；segment label 从 outline 回退；空 label 记 warning。
- 之后才做 S1-4 substrate link、S1-5 selection/truncation report、S1-6 trace/cache、S1-7 tests 扩展。
