# STATE.md — 当前项目快照（2026-11-01）

> 当前阶段：**writing 层设计/落地**。substrate v1 已冻结并作为可信底座；writing 层从零设计，不沿用现有 writing 实验/占位。
> 本文件只记录事实；路线/设计由新 session 自己研究。

## 1. 分支 / 工作树 / 测试

- 分支：`v3`；工作树有未提交改动（substrate v1 + 历史实验）。
- 不擅自 revert/commit；`data/`、`参考素材/skills/` 只读；`data/cookies/` 不读。
- 测试：`PYTHONPATH=src python -m pytest -q` → **426 passed**；v3 122 + v2 304。

## 2. 阶段

- substrate v1：**冻结/可信**；默认 light path；claim 可选 audit/reuse。接口见 [docs/substrate-v1-freeze.md](docs/substrate-v1-freeze.md)。
- writing 层：**未开始**；只有占位 skill 和 substrate plumbing。
- 非必要不改 substrate；发现真实阻塞先报告。

## 3. substrate v1 代码（可用）

| 模块 | 作用 | 状态 |
|---|---|---|
| `writing_v3/transcript.py` | units → sentences/passages | baseline |
| `writing_v3/claim_extract.py` | passages → writing claims（1 次模型/视频，可选） | baseline/optional |
| `writing_v3/pack_from_claims.py` | claims → EvidencePack | baseline/optional |
| `writing_v3/light_context.py` | transcript+outline+frames → 无 claim context | baseline |
| `writing_v3/edited_transcript.py` | full/anchored text + source_map | baseline |
| `writing_v3/bind_article.py` | fact/quote/paragraph + input-scope | baseline |
| `writing_v3/quote_hygiene.py` | 非精确引号去引号 | baseline |
| `writing_v3/generate.py` | text/article → Writer → hygiene → binding（plumbing，不是 skill；可参考/改造，不是 writing 设计基线） | plumbing |
| `writing_v3/trace.py` | trace/receipt | baseline |

**不是基线**（历史/实验）：`one_call_writer.py`、`prose_writer_probe.py`、`comprehension_view.py`、`writer_view.py`、`bind_merged_frames.py`、`probe.py`、`probe_parts.py`；`skills/writing/reader_first_explainer/` 是占位。

## 4. substrate v1 已验证（3 case：2 短 + 1 长 28.2min）

- light path writer-only total：10.8k / 10.4k / 13.9k（P3）；M1 real 13.0k / 7.5k / 21.6k。
- 旧 structured pipeline：58.2k / 44.6k / 85.4k；light path 平均约 −78%。
- 短文本 B+frames = lean view（18/18 + 18/18）；claims/IDs 0 分。
- 长文本 cw0 = merged text（14/14）；claim 的价值是 selection/boundary。
- boundary：bounded claims 让 q5 1→2；3 case 0 unreported。
- fact binding：43/43、51/52、4/4；BV17 1 个 0.78 舍入 unsupported。
- quote hygiene：P3/M1 文章 long quote 归零；binding 2/3 complete。
- 文章质量：developer advisory；结构/机制/边界完整；无 ID/timecode/schema。
- 测试：426 passed。

## 5. 已知限制

- 没有 >30min；没有第二长视频；没有多文体复用回本实验。
- 没有真实 reader test/A-B；文章质量是 developer advisory。
- paragraph provenance 是 n-gram 近似；fact/quote 级可回查，不能承诺 span 级。
- pack 只保留 selection 句（如 67/116），不是完整转写；binding 需要完整 transcript。
- 数字精度/单位/引号仍可能出现；quote hygiene 处理引号，数字规则已加入 prose 契约但未复测。
- frame caption 是 VLM/OCR 文本，可能不完整；caption cap 160 并报告。

## 6. writing 层状态

- 未开始；没有可验收 skill；没有真实 reader test/A-B；没有多文体复用；没有 publish/citations 工作流。
- 现有 writing 实验（`one_call_writer`、`prose_writer_probe`、`comprehension_view`、`writer_view`、`bind_merged_frames`）只作历史/参考；占位 skill 不作为起点。
- 期望后续（由新 session 自行研究如何做）：对照 JD 从零设计/落地 writing 层，使用 substrate v1 的 light text/source_map/binding；真实评测/reader test；多文体；trace/cost；不伪造、不自动发布。

## 7. 关键产物

- substrate v1：`runs/m1_light/`、`runs/m1_real/`、`runs/p3_light/`。
- 历史/证据：`runs/p0_edit/`、`runs/p1_prose/`、`runs/p1b_prose/`、`runs/s2_probe/`、`runs/s3_boundary/`、`runs/v3_poc/`。
- 分析：`runs/m1_real/analysis.md`、`runs/m1_light/analysis.md`、`runs/p3_light/analysis.md`、`runs/p1b_prose/analysis.md`、`runs/p1_prose/analysis.md`、`runs/p0_edit/analysis.md`。

## 8. 关键入口

- 规则：`AGENTS.md`
- 架构：`architecture.md`
- 交接：`HANDOFF.md`
- substrate v1 合同：`docs/substrate-v1-freeze.md`
- 旧 substrate 文档（历史）：`docs/substrate-s0.md`、`docs/substrate-s1-*.md`、`docs/substrate-view-contract.md`、`docs/substrate-view-split.md`
- 历史交接：`handoffs/2026-10-31/`、`handoffs/2026-11-01/`
