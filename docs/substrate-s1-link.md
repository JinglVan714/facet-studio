# Substrate S1-4：substrate link、覆盖报告与 writer view

> 状态：完成（2026-10-31）；S1-6 已移除硬截断，见 [substrate-s1-no-trunc.md](substrate-s1-no-trunc.md)。本文的 full pack 截断数字是 S1-4 历史。
> 范围：通用 pack builder / View；确定性；无模型调用；不碰 frame 时间窗。
> 上位：[docs/substrate-s0.md](substrate-s0.md) §3.1 / §3.3 / §3.4；[architecture.md](../architecture.md) §5.3 / §15 / §16。

## 1. 改了什么

- [provenance.py](../src/lunograph/writing_v3/provenance.py)：写作 claim → snapshot 原子 claim/evidence 的确定性 join（sentence → unit → assertion → snapshot claim/evidence）。
  - 只在 full pack 的 `provenance` 块出现，audit-only；不进 writer view。
  - 记录 `source_claim_ids` / `source_evidence_ids`；`support_statuses`/`stances` 只在非默认时逐条写；`rights_scopes` 只在全局不唯一时逐条写；summary 记 counts 与 `asr_correction_count`。
- [writer_view.py](../src/lunograph/writing_v3/writer_view.py)：lean writer-facing View。
  - 只保留 `segments`（claim_id/text/kind/status/scope/evidence_id/quote/context/frame_id/caption）与 `gaps`/`conflicts` 的 description/severity。
  - 去掉 `pack_id`/`selection`/`provenance`/`budget`/`truncation`/IDs/times/passage_id/sentence_id/file/strategy 等审计字段。
  - CLI 新增 `--writer-out`；writer view 从 **untruncated** pack 构建，audit 字段不能挤掉写作上下文。
- [pack_from_claims.py](../src/lunograph/writing_v3/pack_from_claims.py)：新增 `selection.coverage`（passages total/with extracted/with selected/without extracted/dropped by selection；zero-claim segments）；`truncation.context_sentences_before/after`；full pack 超预算后记 `pack_over_budget_after_metadata`。
- 测试：新增 coverage/provenance/writer view 测试；`tests/writing_v3` 21 passed，全量 **325 passed**。

## 2. Provenance（audit-only）

| 指标 | BV1AC | BV17 |
|---|---:|---:|
| claims with source | **40/40** | **28/28** |
| claims without source | 0 | 0 |
| source claims / evidence | 93 / 93 | 58 / 58 |
| support status counts | supported 39, partially_supported 1 | supported 28 |
| stance counts | supports 40 | supports 28 |
| rights scope counts | unknown_public_video 40 | unknown_public_video 28 |
| asr correction count（linked assertions） | 9 | 1 |

- 写作 claim 全部能回接 substrate 原子 claim/evidence；不是第二套事实源。
- 写作 claim 的 `status` 全是 supported，但 provenance 露出 1 条 `partially_supported`（BV1AC）；边界写作可以用这个信号。
- stance 全是 supports、rights 全是 unknown_public_video；因此逐条 stance 只在非默认时写，rights 只在全局不唯一时逐条写，避免字段污染。
- join 是 unit-overlap 近似：同一句的相邻 atomic claims 可能都算 source；audit 可接受，但不宣称 claim-level 精确。

## 3. Coverage（内容组织）

| 指标 | BV1AC | BV17 |
|---|---:|---:|
| passages total | 32 | 16 |
| passages with extracted claim | 26 | 14 |
| passages with selected claim | 26 | 14 |
| passages dropped by selection | **0** | **0** |
| zero-claim segments | seg1（开场） | seg7（结尾） |

- **0 个 passage 是被 pack selection 丢掉的**；所有缺口都在 claim extraction 阶段。
- BV1AC 零 claim passages：`seg1-p01/p02`（开场/预告）、`seg2-p05`（推广/预告）、`seg7-p02/p04`（四模式 UI/操作对比）、`seg9-p02`（桌面 UI 细节）。
- BV17 零 claim passages：`seg7-p01/p02`（结尾总结/互动）。
- `seg7-p02/p04` 可能承载四模式对比的核心信息；这是上游提取覆盖问题，不能靠 pack builder 补，也不能手改单例。通用修法是给 claim extraction 加 `skipped_passages` 合同：每个 passage 要么有 claim，要么给出 skip 原因；需要下一次模型重跑才能测量。
- 这不是 selection cap 的问题：`passages_dropped_by_selection=0`。

## 4. Writer view（下游效率）

| 指标 | BV1AC | BV17 |
|---|---:|---:|
| full pack pretty | 60,057 | 38,646 |
| full pack compact | 47,048 | 30,146 |
| writer view pretty | 22,662 | 14,191 |
| writer view compact | 17,709 | 10,841 |
| writer/full compact ratio | **0.376** | **0.360** |
| claims / evidence 保留 | 40 / 40 | 28 / 28 |
| context sentences 保留 | 65 | 35 |
| frames 保留 | 20 | 12 |
| gaps 保留 | 7 | 4 |

- writer view 保留了所有 claim/evidence ID、quote、上下文、frame、gap；去掉的是审计字段。
- **字段污染的实证**：full pack 因 provenance/coverage/selection 等审计字段达到 60k，BV1AC 触发截断，删掉 4 个非 anchor 邻域句（`context_sentences 65→61`）；writer view 从 untruncated pack 构建，仍保留 65 句。这说明 audit metadata 不能和 writer context 共用同一个预算。
- writer view 还没有接到 `one_call_writer`；下一步（writing 阶段）才用它并测量真实 Writer tokens/质量。S1-4 只提供 substrate 侧的确定性 View。

## 5. 仍然存在的问题

- **claim extraction 覆盖缺口**：6/32、2/16 passages 无 claim；需要 `skipped_passages` 合同和一次模型重跑来验证。不是 pack selection 问题。
- **full pack 审计体积**：provenance/coverage 让 full pack 到 60k；后续可把 audit 字段拆到 `audit.json` sidecar，或保持 writer view 为唯一写作输入。
- **writer view 未接线**：`one_call_writer` 仍读 full pack；接线和 token/质量测量属于 writing 阶段。
- **provenance 近似**：unit-overlap join，不宣称 claim-level 精确；stances/rights 当前无变化信号。
- **frame 时间窗不改**：按用户确认，关键点附近候选就是预期；不做 claim-level 视觉匹配。

## 6. 验证

- `tests/writing_v3`：21 passed。
- 全量：**325 passed**（S1-3 后 318 + 7）。
- 未跑模型；未按单篇调参；未手改 claim/reader。
- before/after pack 与 writer view 在本地 `runs/s1_link/after/`，不入库。

## 7. 下一步

- S1-5：已完成，见 [substrate-s1-coverage-trace.md](substrate-s1-coverage-trace.md)。
- 之后才是 writing 阶段：writer view 接线、Writer tokens/质量、真实读者测试。
