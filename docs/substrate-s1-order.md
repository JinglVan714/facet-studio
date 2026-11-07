# Substrate S1-3：claims 排序与 segment label

> 状态：完成（2026-10-31）
> 范围：通用 pack builder；确定性；无模型调用。
> 上位：[docs/substrate-s0.md](substrate-s0.md) §3.1 / §3.5 / §6.3。

## 1. 改了什么

- [pack_from_claims.py](../src/facet_studio/writing_v3/pack_from_claims.py)：
  - `claims` 与 `segments[].claim_ids` 统一按 `segment → passage → sentence → time → claim_id` 排序，不再用 hash/选择顺序。
  - `passage_coverage` 按 passage 顺序输出。
  - segment label 解析改为 **outline 优先，contract fallback**；两者都空时记 `selection.labels.warnings`，不再静默输出空字符串。
  - `selection.labels` 新增 `sources` / `source_counts` / `warnings`。
- [test_pack_context.py](../tests/writing_v3/test_pack_context.py)：新增 5 个测试（sentence 排序、passage 排序、outline 优先、contract fallback、missing label 报告）。

## 2. Before / After

对比对象：S1-2 后的 pack → S1-3 后的 pack。输入相同。

| 指标 | BV1AC S1-2 → S1-3 | BV17 S1-2 → S1-3 |
|---|---:|---:|
| top-level claims 有序 | false → **true** | false → **true** |
| 非时间序 segment | 8/10 → **0** | 5/7 → **0** |
| segment label 非空 | 10/10 → 10/10 | 7/7 → 7/7 |
| label source | 未记录 → outline 10 | 未记录 → outline 7 |
| label warnings | — → 0 | — → 0 |
| pack chars (pretty) | 51,431 → 51,766 (+0.65%) | 32,487 → 32,751 (+0.81%) |
| pack chars (compact) | 41,135 → 41,374 (+0.58%) | 25,848 → 26,034 (+0.72%) |

- “非时间序 segment”按 `segments[].claim_ids` 的排序检查；top-level `claims` 也从 hash 序改为 segment→passage→sentence→time 序。
- **P0 BV17 的 label 为空**，原因是 P0 pack 构建时没有传 `contract`；S1-3 之后，即使不传 contract，也会从 outline 取 label。验证：`runs/s1_order/no_contract/` 的 BV1AC/BV17 pack，label source 分别为 outline 10/7、warnings 0。
- **with contract 与 no_contract 的 pack 字符数相同**：两个视频的 outline/contract label 当前一致，说明 label 解析不再依赖调用方是否记得传 contract。
- claims/evidence/frames/context 计数不变：40/28 claims、40/28 evidence、20/12 frames、context 40/40 与 28/28。

## 3. 仍然存在的问题

- **claims 排序只改展示顺序，不改变选择**：coverage-aware selection 仍是同一套；排序让 `claims`、`segments[].claim_ids`、`sentences` 的顺序一致，但不会自动形成“读者论证顺序”。`reader_path` 仍后置。
- **label 只做解析/报告**：没有对 label 做质量判断；空 label 会 warning，但不会让 pack 失败。
- **Frame / timecode 的上游问题**：S1-2 已修 evidence 时间；frame 仍是时间窗候选，不是 claim-level 视觉匹配。
- **substrate link（S1-3 时仍缺；S1-4 已修）**：见 [substrate-s1-link.md](substrate-s1-link.md)。

## 4. 验证

- `tests/writing_v3`：14 passed。
- 全量：**318 passed**（S1-2 后 313 + 5）。
- 未跑模型；未按单篇调参；未手改 claim/reader。
- before/after pack 与 trace 在本地 `runs/s1_order/after/`、`runs/s1_order/no_contract/`，不入库。

## 5. 下一步

- S1-4：写作 claim 回接 substrate 原子 claim/evidence；补 `source_claim_ids`/`source_evidence_ids`、stance/support_status/rights_scope。
- 然后 S1-5 selection/truncation → S1-6 trace/cache → S1-7 tests。
