# Substrate S1-7：A+C+D View 实现

> 状态：完成（2026-10-31）
> 范围：substrate；确定性；无模型调用。
> 契约：[substrate-view-contract.md](substrate-view-contract.md)。

## 1. 实现

- [writer_view.py](../src/lunograph/writing_v3/writer_view.py)：
  - A：`build_writer_view(pack)` → lean single view（schema `writer-view-v1`）。
    - quote 唯一命中 context 时写 `span:[start,end]`；否则 `quote` fallback。
    - 去 `segment_id`/`kind`/gap severity；caption ≤80；保留 full claim/evidence/frame IDs。
  - C：`build_writer_index(pack)` + `build_writer_bundle(pack, max_chars_per_part=None)`。
    - index：segment label + claim id/text/status/scope + `part_id`；无 quote/context/frames。
    - parts：默认一 segment 一 part；`max_chars_per_part` 可合并连续 segments；单 segment 超预算保留并标记 oversize。
    - manifest：`parts_count`、part 文件/char/claim 数、segments/claims 总数、oversize、note。
  - D：writer view/index/parts 不含 provenance/selection/coverage/truncation；full pack 仍是 audit。
- [pack_from_claims.py](../src/lunograph/writing_v3/pack_from_claims.py)：
  - `--writer-out` 写 lean view。
  - `--writer-bundle-dir` 写 `writer_index.json`、`manifest.json`、`writer_parts/part_XX.json`。
  - `--writer-part-max-chars` 控制 part 合并预算。
- 测试：新增/更新 A/C/D view 测试；`tests/writing_v3` 38 passed，全量 **342 passed**。

## 2. 实测（BV1AC 新 claims / BV17）

| 指标 | BV1AC 旧 claims | BV1AC 新 claims | BV17 |
|---|---:|---:|---:|
| 转录文本 chars | 4,726 | 4,726 | 2,071 |
| 之前 writer view compact | 19,990 | 21,227 | 11,987 |
| **A lean view compact** | **15,405** | **15,861** | **9,753** |
| A / 转录文本 | 3.26x | 3.36x | 4.71x |
| A 相对之前 writer view | -22.9% | -25.3% | -18.6% |
| **C index compact（full IDs）** | **5,803** | **6,007** | **4,339** |
| index / 转录文本 | 1.23x | 1.27x | 2.10x |
| C parts 数 | 10 | 10 | 7 |
| part chars 中位 / 最大 | 1,552 / 2,975 | 1,518 / 2,820 | 1,456 / 2,382 |
| parts chars 合计 | 15,498 | 15,954 | 9,782 |
| full pack compact（audit） | 55,266 | 57,763 | 33,946 |
| full pack over_budget | 10,393 | 13,368 | 0 |

- A 把 writer view 降低 18.6–25.3%；BV17 仍略高于 4.5x 目标（4.71x），advisory。
- index 是“选择层”，不含 quote/context/frames；BV17 2.10x 高于 1.5x 目标（full IDs/status/scope），仍约 4.3k chars；B/短 ID 可再压。
- parts 默认一 segment 一 part；部分 segment 2.3–2.8k，超过 2k 目标，但保留并标记，不删。
- `--writer-part-max-chars 2000` 在 BV1AC 新 claims 上得到 9 parts、3 个 oversize（2.1k/2.8k/2.5k）；不丢内容。

## 3. 验证

- 覆盖：A 的 claims/evidence/frames 与 full pack **完全一致**；index 覆盖全部 claims；parts 覆盖全部 claims/evidence。
- quote：所有 span 都能还原为 full pack 的精确 quote；fallback 0 条（BV1AC/BV17 当前数据）。
- 无 audit 字段：A/C 的 serialized 不含 provenance/selection/coverage/truncation/segment_id/passage_id/sentence_id/times/kind 等。
- 测试：`tests/writing_v3` 38 passed；全量 **342 passed**。
- 确定性：A+C+D 构建 **0.220s（BV1AC，含 full pack + lean view + index/parts/manifest）**；无模型调用。
- 未按单篇调参；未手改 claim/reader；未 commit。

## 4. 结论

- **A+C+D 已落地**：短/中内容读 lean view；长/大内容读 index→parts；full pack 只作 audit。
- **A 的收益**：writer view 降低 18.6–25.3%，主要来自 quote→span、去 kind/segment_id/severity、caption 80；context/claims 结构保留。
- **C 的收益**：index 3.6–6.0k，part 中位 1.5k；单次消费比一次性 A 更小；总磁盘/总调用会更大，这是按需的代价。
- **B 仍后置**：compact schema 能到 ~2.3x/3.0x 文本，但模型理解/绑定未验证。
- **Writer 仍未接线**：`one_call_writer` 仍读 full pack；接线 A/C 属于 writing 阶段。

## 5. 下一步

1. 把 `one_call_writer` 接到 A（短）或 C（长），测真实 Writer tokens/质量；writing 阶段，需单独确认。
2. S2 probe：raw ASR vs merged text vs A lean view，判断 3.3–4.7x 的体积溢价是否值得。
3. B compact schema 作为实验；只有 probe 通过再进默认。
4. BV17 claim extraction 合同仍未跑；后置。
