# Substrate v3 交接快照（2026-10-31）

> 这是历史快照，不是基线。当前权威交接见 [HANDOFF.md](../../HANDOFF.md)，状态见 [STATE.md](../../STATE.md)，契约见 [docs/substrate-view-contract.md](../../docs/substrate-view-contract.md)。
> 本文件只帮助新 session 快速知道“现在在哪、下一步做什么”。

## 1. 当前一句话

substrate 打磨；A（lean view）+ C（index+parts）+ D（audit sidecar）已实现；Writer 还没接 A/C；下一步建议 S2 probe（raw ASR vs merged text vs A），再做 Writer 接线。不做 skill/reader test，不按单例修。

## 2. 架构

```text
units → sentences → passages → claims（1 次模型/视频）
  → full pack（audit：claims/evidence/context/frames/provenance/selection/coverage）
  → A writer_view（lean） / C writer_index+parts（按需）
  → Writer（当前读 full pack；A/C 未接线）
```

- full pack 是唯一 audit 源；A/C 是确定性投影，不新增事实。
- 不硬截断；超预算 advisory/partition/oversize。
- 一次编译，多文体复用 claim/evidence；写作默认一次 Writer。

## 3. 数字（BV1AC 旧 / 新 / BV17）

| 指标 | BV1AC 旧 | BV1AC 新 | BV17 |
|---|---:|---:|---:|
| 转录文本 chars | 4,726 | 4,726 | 2,071 |
| A lean view compact | 15,405 | 15,861 | 9,753 |
| A / 文本 | 3.26x | 3.36x | 4.71x |
| C index compact | 5,803 | 6,007 | 4,339 |
| C part 中位 / 最大 | 1,552 / 2,975 | 1,518 / 2,820 | 1,456 / 2,382 |
| full pack compact | 55,266 | 57,763 | 33,946 |
| over_budget | 10,393 | 13,368 | 0 |

- A 比旧 writer view 降 22.9% / 25.3% / 18.6%。
- BV1AC 新 claims：29 passages with claims + 3 skipped，0 unreported。
- BV17 仍是合同前 claims：0 skipped / 2 unreported。
- 测试 342（v3 38）；A+C+D 构建 0.220s；无模型调用。
- P0 Writer 成本（旧 full pack）：BV1AC 69,348 tokens / 225.8s；BV17 53,822 / 192.7s。

## 4. 决策

- 不默认一次性注入 full pack（体验不好，尤其过大）；默认 A；大内容 C；full pack 只作 audit。
- A+C+D 已确认；B compact schema 暂不默认，先 probe。
- 不硬截断；`max_chars` advisory；`max_claims_per_segment`/`max_sentences_per_segment` 默认 None；frame 全局硬切片移除；caption/selection cap 只报告。
- skill 只作参考：17 个本地 skill 是围绕业务拉下来的素材；全文注入属于微调 writing 产出；业务迁移后置，当前优先 substrate。
- 不按单篇调参；不手改 claim/reader；不恢复 v2；不自动发布。

## 5. 风险

- substrate 未证明比 raw ASR/merged text 更好：S2 probe 未做。
- Writer 未接 A/C：`one_call_writer` 仍读 full pack，prompt 偏大。
- B compact schema 未验证；index BV17 2.10x、part 最大 2.8k；index+parts 总磁盘大于 A。
- claim 合同只验证 BV1AC；BV17 未跑。
- 无 repair/独立 audit.json/citations.json；v3 测试是确定性单测。
- worktree 未提交；不要 revert/commit。

## 6. 下一步

1. **S2 probe**：raw ASR vs merged text vs A；固定问题、同模型/参数、记录 trace；比较质量/成本。
2. **Writer 接 A/C**：短/中 A；大内容 index→parts；测真实 Writer tokens/质量（writing 阶段，需确认）。
3. **B compact schema**：probe 通过后再试。
4. **BV17 claim extraction 新合同**：两视频验证。
5. 之后才是 skill 从零、reader test/A-B、audit/citations/repair、freeze P1。

## 7. 入口

- [AGENTS.md](../../AGENTS.md) / [architecture.md](../../architecture.md) / [HANDOFF.md](../../HANDOFF.md) / [STATE.md](../../STATE.md)
- [docs/substrate-view-contract.md](../../docs/substrate-view-contract.md) / [docs/substrate-s1-view.md](../../docs/substrate-s1-view.md)
- [docs/reference-writing-scan.md](../../docs/reference-writing-scan.md)
