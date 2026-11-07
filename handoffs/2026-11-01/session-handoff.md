# Substrate v3 交接快照（2026-11-01）

> 这是历史快照，不是基线。当前权威交接见 [HANDOFF.md](../../HANDOFF.md)，状态见 [STATE.md](../../STATE.md)。
> 本文件记录 2026-10-31 晚到 2026-11-01 的两个 session：做了什么、得到什么结论、哪些是实验性过度实现、当前方向是什么。

## 1. 这两个 session 做了什么

### 2026-10-31：S2 probe（短视频）

- 建了 `probe.py`：同一视频、同一题集，比较 **raw ASR / merged text / lean view**；默认 dry-run，`--run` 才调用模型。
- v1：6 题（central/mechanism/procedure/boundary/quote）；BV1AC/BV17 三路各 6 次调用。
- 人工盲评：三路 6 题都是 12/12；raw ASR 表述质感最差，merged/lean 无一致赢家。
- v2 补题：frame-only + 跨段综合；三路理解/综合仍 14/14；lean 只在 frame-only 题赢 4/4 vs 2/4。
- B+frames 对照：merged text + frame captions，不含 claims/IDs；与 lean 同 36/36，prompt tokens 只有 lean 的 55%–60%。
- 结论：**短视频 comprehension 的 lean view 优势全部来自 frames；claims/context/IDs 不赚成本。**

### 2026-11-01：长视频 + boundary + cw0 + Writer 集成

- 用 `data/` 最长的 BV1yb（28.2min，1100 units，325 sentences，85 passages）补长视频 case。
- 旧 claims：37 claims / 48 skipped / **1 unreported**；probe raw/B 14/14、C 13/14。
- 唯一失分 q5 boundary：limitation 句“可能帮不上你的大忙”在 C 的 context 里，但 claim 层没把它提成 claim，模型也没用。
- S3 boundary 修复：claim extraction 合同加通用规则——显式 limitation/uncertainty 提成 `status="bounded"` 独立 claim，limitation 写进 `scope`。
  - 3 case 重跑：BV1AC 36/7 bounded、BV17 33/2、BV1yb 47/4；全部 **complete / 0 unreported**。
  - BV1yb q5 1→2；BV1AC/BV17 无回退（12/12）。
  - 代价：BV1yb C prompt +17.3%、total +42.4%。
- cw0（context_window=0，只保留 anchor sentences）：3 case 仍 12/12、12/12、14/14；BV1yb C prompt 6,114 vs B 7,100，total 10,968 vs 12,975，latency 31.8s vs 40.3s。
- index+parts：BV1yb 宽题 selector 6/8，prompt 8,066；窄题 5/8，prompt 7,406；都高于 one-shot cw0（6,114/5,997）。**28min 不回本。**
- View 拆分实验：`comprehension_view.py`（merged_frames / lean_cw0 + auto/budget）、`bind_merged_frames.py`（grounding adapter）、`one_call_writer.py` 3 view modes。
- Writer 实跑 3 篇：文章结构完整、可读；prompt 7,411/4,931/8,340；completion 24,375/19,629/28,377（reasoning 19,977/15,572/20,499）；total 31,786/24,560/36,717；binding 大量 partial（broader quote/context-only）。
- 消费层分析：**输入变小但 reasoning 变大，总成本没明显下降；主要成本是 schema/绑定税，不是证据体积。**
- 方向修正：不再加 mode/adapter/coverage tier；先测“一个保序消费文本 + prose-only Writer + 代码事后 binding + full pack audit”。

## 2. 关键数字

### 2.1 Probe

| case | raw/B/C 分 | 关键成本 |
|---|---|---|
| BV1AC v2 | 16/18、16/18、18/18 | B+frames prompt 4,367 vs lean 7,326 |
| BV17 v2 | 16/18、16/18、18/18 | B+frames 2,449 vs lean 4,487 |
| BV1yb | 14/14、14/14、14/14（cw0） | C prompt 6,114 vs B 7,100；total 10,968 vs 12,975 |
| BV1yb index+parts | 宽 14/14；窄 6/6 | wide 8,066；narrow 7,406（vs cw0 6,114/5,997） |

### 2.2 Writer（实验集成）

| case | view | prompt | completion（reasoning） | total | reader |
|---|---|---:|---:|---:|---:|
| BV1AC | merged_frames | 7,411 | 24,375（19,977） | 31,786 | 1,835 字 |
| BV17 | merged_frames | 4,931 | 19,629（15,572） | 24,560 | 1,710 字 |
| BV1yb | lean_cw0 | 8,340 | 28,377（20,499） | 36,717 | 2,104 字 |

- 旧 P0 full-pack Writer：BV1AC 38,071 / 110s；BV17 33,583 / 108s；1,865 / 1,497 字。
- 结论：**input tokens 降 80%+，但 completion/reasoning 涨到 19–28k，total 只降 16%–27%。**
- binding：BV1AC 21 bound/1 partial/3 unbound；BV17 10/5/1/1 error；BV1yb 9 个 quote 不在 bound evidence。多为 broader quote/context-only，不是编造。

## 3. 已验证 vs 实验性过度

**已验证（keep）：**

- 短文本：B+frames = lean view 同分；claims/IDs 不赚 comprehension。
- 长视频：cw0 同分且比 B 便宜；boundary claims 必要。
- 3 case claim extraction complete / 0 unreported；bounded 7/2/4。
- full pack 是 audit；claim 层 = selector/audit/binding/boundary/reuse。
- 18/18 关键事实可回查；真实 quote/frame binding 验证。
- index+parts 在 28min 不回本。

**实验性/过度（不要当基线）：**

- `comprehension_view.py` 的 dual external mode + auto budget。
- `bind_merged_frames.py` 的 6 statuses；coverage tiers 只是提议，未实现。
- `one_call_writer.py` 的 3 view modes + `grounding_ref` 义务；默认仍是 full_pack。
- `probe_parts.py` index+parts 评估工具。
- `docs/substrate-view-split.md` 是设计/实验记录，不是 architecture。
- 这些实体数量超过当前证据需要；下一步应先测 prose-only + 文本 view，再决定折叠。

## 4. 当前方向（交接重点）

> **一次 Writer + 一段保序、去重、高信号消费文本 + prose-only Writer + 代码事后 binding + full pack audit。**

- 短/中：merged text + frames。
- 长：claims + anchors + boundaries + frames；但渲染成一段文本，不是 claims/context JSON。
- Writer 主要写散文；ID/quote/timecode/binding 由代码用 full pack 事后对齐；不要把 schema/ID 义务塞给模型。
- 不再加 mode/coverage tier/adapter；index+parts 不默认。
- 长视频 >30min 向用户要；不自行下载。

**下一步：**

1. Prose-only Writer 测试（3 case）：B+frames 文本 / cw0 文本 + minimal output contract；测 completion/reasoning、total、文章质量、事后 binding。
2. Edited-transcript renderer：cw0 anchors + boundaries + frames → 一段保序文本。
3. 测试通过则收敛 surface；不通过则保留最小 claims/IDs 仅作 audit。
4. 之后才是 Writer 完整接线、skill、reader test/A-B。

## 5. 产物 / 测试

- 代码：`src/facet_studio/writing_v3/{claim_extract,pack_from_claims,writer_view,probe,probe_parts,comprehension_view,bind_merged_frames,one_call_writer}.py`。
- 分析：`runs/s2_probe/run/analysis.md`、`run_v2/analysis.md`、`run_b_frames/analysis.md`、`run/BV1yb/analysis.md`、`runs/s3_boundary/analysis.md`、`runs/s2_probe/binding_check.md`。
- Writer 实跑：`runs/s3_boundary/writer/{BV1AC,BV17,BV1yb}/`。
- 测试：**375 passed**（v3 71）。
- 工作树未 commit；不要 revert/commit。

## 6. 入口

- [HANDOFF.md](../../HANDOFF.md) — 当前方向/交接
- [STATE.md](../../STATE.md) — 当前代码/测试
- [AGENTS.md](../../AGENTS.md) / [architecture.md](../../architecture.md)
- [docs/substrate-view-contract.md](../../docs/substrate-view-contract.md) / [docs/substrate-s0.md](../../docs/substrate-s0.md)
- [docs/s2-probe/protocol.md](../../docs/s2-probe/protocol.md) / [docs/substrate-view-split.md](../../docs/substrate-view-split.md)（实验，注意方向修正）
