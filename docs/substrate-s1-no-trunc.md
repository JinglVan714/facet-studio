# Substrate S1-6：移除硬截断、writer view 分区、claim 合同实测

> 状态：完成（2026-10-31）
> 范围：substrate；确定性修复 + 一次 claim extraction 实测（BV1AC）。
> 上位：[docs/substrate-s0.md](substrate-s0.md) §3.1 / §3.4 / §3.7；[architecture.md](../architecture.md) §5.3 / §15 / §16。

## 1. 原来的截断机制（问题）

`pack_from_claims.build_pack` 之前：

1. 组装 full pack 后，用 pretty JSON 的 `max_chars`（默认 60,000）做硬预算；
2. 超预算时从最后一个 segment 的最后一个 sentence 开始删，跳过 anchor sentence；
3. 再删未被 evidence 引用的 frame；
4. 仍超预算则写 notes，但 pack 继续输出；
5. 没有自动修复；被删的上下文/帧除了 `truncation` 记录外不会回来；
6. writer view 之前靠“untruncated rebuild”绕过，但 full pack（当时也是 Writer 输入）已经丢内容。

这违反开发原则：**用审计字段和 writer context 共用硬预算、按位置而非重要性丢内容、长视频/复杂视频会放大丢失、没有修复路径**。BV1AC 在 S1-5 就被删了 6 句 + 1 帧。

## 2. 修复后的规则

- **full pack 不做硬截断**：超出 advisory `max_chars` 时保留全部 claims/evidence/context/frames，只记 `over_budget` / `budget_excess_chars` / `truncation.notes=["advisory_budget_exceeded"]`。
- `max_claims_per_segment` 默认 `None`：不再按 segment 硬压 claim；显式传 cap 时仍报告 `passages_dropped_by_selection`。
- `max_sentences_per_segment` 默认 `None`：anchor + 邻域全保留；显式传 cap 时报告 `over_cap_segments`。
- frame 的全局 `frames_out[:max_frames]` 硬切片移除；新增 `selection.frame_selection` 报告：candidates/selected/per-segment cap/over_global_cap/captions_truncated。每 segment 2 帧的选择保留（用户确认时间窗候选没问题）。
- `writer view` 新增 `max_chars` 预算：超预算时按 segment 分区为 `parts`，**不丢内容**；单个 segment 超预算时保留并标记 `oversize_parts`。CLI `--writer-max-chars`。
- `evidence_pack.py` 早期路径仍带硬 `max_chars` trim；已在 docstring 标记 **legacy**，不是 v3 默认路径，不再扩展该行为。
- `claim_extract` / `one_call_writer` 的 `max_tokens` 是输出预算；输出被截断会产生 invalid JSON / partial，不会静默改输入。

## 3. claim extraction 实测（BV1AC，一次）

命令：

```bash
python -m lunograph.writing_v3.claim_extract \
  --passages runs/v3_poc/BV1AC_transcript/passages.json \
  --out-dir runs/s1_claim_verify/BV1AC \
  --cache-dir runs/_cache/llm
```

结果：

| 指标 | 值 |
|---|---:|
| status | complete |
| passages | 32 |
| passages skipped（带 reason） | 3（teaser / other / ui_detail） |
| passages unreported | **0** |
| claims raw / accepted / rejected | 43 / 43 / 0 |
| usage | 30,102 tokens（prompt 5,480 / completion 24,622 / reasoning 19,763 / cached 128） |
| latency | 115.3s |
| cached | false（首次） |

- 新 claims 覆盖 29 passages；3 个 skipped；0 unreported。
- 之前零 claim 的 `seg7-p02/p04` 现在有 claim；`seg9-p02/seg1-p01` 也有 claim；skipped 是 `seg1-p02`（teaser）、`seg2-p05`（other）、`seg7-p01`（ui_detail）。
- 3 条 claim 的 quote 不在其列出的 `sentence_ids` 里，但在 passage 内；pack 用 passage anchor 回退，timecode source 43 anchor / 0 fallback，`quote_not_in_claim_sentences=3` 显式记录。
- 这是**一视频的机制验证**，不是两视频验收；BV17 仍是合同前 claims（0 skipped / 2 unreported）。

### cache 验证

同一命令重跑到 `runs/s1_claim_verify/BV1AC_cached`：

- `cached=true`，`latency_ms=0`，usage 仍 30,102；
- `claims.json` 与首次 sha256 完全一致；
- `llm_calls.jsonl` 首次是 `provider=deepseek, replayed=false`，第二次是 `provider=cache, replayed=true`；
- prompt 原文/hash 两处一致。

## 4. Before / After（pack 侧）

| 指标 | S1-5（硬截断） | S1-6 旧 claims | S1-6 新 claims（BV1AC） | S1-6 BV17 |
|---|---:|---:|---:|---:|
| selected claims | 40 | 43 | 43 | 31 |
| evidence | 40 | 43 | 43 | 31 |
| full pack sentences | 59 | 102 | 108 | 47 |
| full pack frames | 19 | 20 | 20 | 12 |
| full pack pretty / compact | 60,027 / 46,969 | 70,393 / 55,266 | 73,368 / 57,763 | 43,495 / 33,946 |
| over_budget | — | yes, 10,393 | yes, 13,368 | no |
| truncation drops | 6 sentences + 1 frame | **0** | **0** | **0** |
| writer view compact | 17,709 | 19,990 | 21,227 | 11,987 |
| writer view context / frames | 65 / 20 | 102 / 20 | 108 / 20 | 47 / 12 |
| coverage skipped / unreported | 0 / 6 | 0 / 6 | **3 / 0** | 0 / 2 |

- full pack 超预算现在是 advisory，不再丢内容。
- writer view 比 full pack 小很多，但不再靠截断；如果设置 `--writer-max-chars`，超预算会分区而不是丢内容。
- 当前 full pack 超过 60k；如果 Writer 继续读 full pack，prompt 会变大。writer view 仍是预期入口，但尚未接线。
- 确定性 pack+view 构建：**0.167s（BV1AC）/ 0.164s（BV17）**；单次构建，无模型调用。

## 5. 类似机制审计

| 机制 | 之前 | 现在 |
|---|---|---|
| `max_chars` pack trim | 硬删上下文/帧 | advisory；`over_budget`，不删 |
| `max_claims_per_segment=6` | 可能丢 passage/claim | 默认 `None`；显式 cap 时报告 `passages_dropped_by_selection` |
| `max_sentences_per_segment=6` | 可能丢邻域 | 默认 `None`；显式 cap 时报告 `over_cap_segments` |
| `frames_out[:max_frames]` | 全局硬切片 | 移除；`frame_selection.over_global_cap` 报告 |
| `max_frame_caption_chars=160` | caption 静默截断 | 保留行为；`captions_truncated` 计数 |
| `evidence_pack.py` trim | 早期路径硬删 | 标记 legacy，不用于 v3 默认 |
| `claim_extract`/`one_call_writer` max_tokens | 输出可能被截断 | invalid JSON / partial 显式；不改输入 |
| transcript sentence/passage caps | 切分而不是丢弃 | 保持；不属于内容丢失 |
| claim near-duplicate dedup | 丢重复 claim | 保持；`duplicates` 记录 |

## 6. 仍然存在的问题

- **writer view 未接线**：`one_call_writer` 仍读 full pack；full pack 现在 70k/73k/43k，Writer prompt 会偏大。下一步应让 Writer 读 writer view，或按 `--writer-max-chars` 分区消费。
- **BV17 未跑新合同**：只有 BV1AC 的 skipped/unreported=3/0；BV17 仍 0/2。两视频验收还差一次 BV17 claim extraction。
- **quote/sentence 对齐**：BV1AC 新 claims 有 3 条 quote 不在列出的 sentence_ids；pack fallback 能处理，但 claim 侧仍应尽量列全。
- **cache 只覆盖 provider 层**：stage 级 cache/replay 还没接；真实命中率只在 BV1AC claim extraction 上验证了一次。
- **frame caption 截断**：当前只报告，不保留全文；caption 是选帧依据，不是事实，暂可接受。

## 7. 验证

- `tests/writing_v3`：33 passed。
- 全量：**337 passed**。
- 新增/更新测试：无硬截断（budget advisory）、默认 claim/sentence 不设 cap、writer view 分区不丢内容、frame 超全局 cap 不丢。
- 一次真实 claim extraction + 一次 cache hit；未做 BV17 模型调用。
- 未按单篇调参；未手改 claim/reader；未 commit。

## 8. 下一步

- A+C+D 消费契约已确认：[substrate-view-contract.md](substrate-view-contract.md)；实现 lean view / index+parts / audit sidecar，并重建 BV1AC/BV17 产物。
- Writer 接线、BV17 claim extraction、full pack sidecar 都后置；当前先完成 A+C+D。
