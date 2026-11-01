# Substrate S1-2：时间码与 quote 对齐

> 状态：完成（2026-10-31）
> 范围：通用 pack builder；确定性；无模型调用。
> 上位：[docs/substrate-s0.md](substrate-s0.md) §3.3 / §6.2；[architecture.md](../architecture.md) §9.1。

## 1. 改了什么

- [pack_from_claims.py](../src/lunograph/writing_v3/pack_from_claims.py)：
  - evidence 的 `t_start_ms`/`t_end_ms` 改为 anchor sentence 时间并集，不再是整个 passage 的时间。
  - evidence 的 `sentence_ids` 改为 anchor sentence IDs（真正包含 quote 的最小连续 slice）。
  - 校验 `quote ∈ ''.join(anchor sentence texts)`；不满足时在 `selection.context.quote_not_in_sentence_text` 记录，不静默。
  - `selection.context.timecode_source_counts` 记录 `anchor_sentences` / `claim_passage_fallback`。
  - frame 候选窗口改用 anchor time range，不再用 passage start/end。
  - 常见情况（anchor 找到、quote 命中）不逐条写 `timecode_source`/`quote_in_sentence_text`，避免 pack 冗余；只有异常才逐条标记。审计计数在 `selection.context`。
- [test_pack_context.py](../tests/writing_v3/test_pack_context.py)：新增 4 个测试（anchor timecode、跨句 anchor、missing fallback、frame window）。

## 2. Before / After

对比对象：S1-1 后的 pack（passage 级 timecode）→ S1-2 后的 pack（anchor 级 timecode）。输入完全相同。

| 指标 | BV1AC S1-1 → S1-2 | BV17 S1-1 → S1-2 |
|---|---:|---:|
| evidence 时间 == sentence 并集 | 3/40 → **40/40** | 3/28 → **28/28** |
| quote ∈ sentence text | 40/40 → 40/40 | 28/28 → 28/28 |
| quote not in sentence text | 0 → **0** | 0 → **0** |
| timecode source | — → anchor 40 / fallback 0 | — → anchor 28 / fallback 0 |
| frames | 20 → 20 | 13 → 12 |
| frame set changes | 3 removed / 3 added | 1 removed / 0 added |
| pack chars (pretty) | 50,940 → 51,431 (+1.0%) | 32,771 → 32,487 (-0.9%) |
| pack chars (compact) | 40,650 → 41,135 (+1.2%) | 26,099 → 25,848 (-1.0%) |
| claims with context | 40/40 → 40/40 | 28/28 → 28/28 |

- BV1AC 的 3 个 frame 替换：`00007_000099534` / `00016_000240050` / `00023_000511517` → `00008_000106000` / `00017_000266150` / `00017_000525000`。
- BV17 的 1 个 frame 移除：`00006_000195000`；frame 数从 13 降到 12。
- BV17 pack 变小，是因为 tighter frame window 少了一帧，抵消了新增审计字段。
- 独立复核：after pack 的每条 evidence 时间与 anchor sentence 并集完全一致，`wide=0`；`quote_in_sent=40/40`、`28/28`。

## 3. 仍然存在的问题

- **Frame 仍是时间窗候选**：窗口变准了，但没有 claim-level 视觉匹配；`real_frame` 仍靠 VLM caption/人工判断。S1-2 不解决这个。
- **Frame set 变化需要检查**：BV1AC 换了 3 帧、BV17 少 1 帧；目前只验证时间窗，没有人工/ VLM 验证“这帧是否真的展示该 claim”。这是 S2/人工 review 的事。
- **claim_extract 仍写 passage 时间**：`claims.json` 的 `t_start_ms`/`t_end_ms` 还是 passage 级；pack 现在会覆盖成 anchor 时间。未来如重跑 claim extraction，仍由 pack 纠正；不在 S1-2 改 claim 文件格式。
- **claims 顺序仍是 hash 序；BV17 labels 仍空（S1-2 时；S1-3 已修）**：见 [substrate-s1-order.md](substrate-s1-order.md)。

## 4. 验证

- `tests/writing_v3`：9 passed。
- 全量：**313 passed**（S1-1 后 309 + 4）。
- 未跑模型；未按单篇调参；未手改 claim/reader。
- before/after pack 与 trace 在本地 `runs/s1_context/after/`、`runs/s1_timecode/after/`，不入库。

## 5. 下一步

- S1-3：claims 按 passage/time 排序；segment label 从 outline 回退；空 label 记 warning。
- 然后 S1-4 substrate link/stance/rights → S1-5 selection/truncation → S1-6 trace/cache → S1-7 tests。
