# HANDOFF.md — writing 层设计/落地交接（2026-11-01）

> 新 session 启动顺序：`AGENTS.md` → `architecture.md` → 本文件 → `STATE.md` → `docs/substrate-v1-freeze.md` → 代码。
> 本文件只说明**现在做到了什么**与**期望后续做到什么**，不提供 writing 路线；路线由新 session 自己研究。
> substrate v1 已冻结，非必要不改；writing 层从零设计，不依赖现有 writing 实验或占位 skill。

## 0. 当前阶段

- **substrate v1 已冻结并可信**：默认 light path（transcript + frames → edited text → prose Writer → quote hygiene + binding）；claim 层可选 audit/reuse。
- **writing 层尚未开始**：现有 `reader_first_explainer` 是占位；`one_call_writer` / `prose_writer_probe` / `comprehension_view` / `writer_view` / `bind_merged_frames` 是历史实验，不是基线。
- 新 session 的目标：**对照 JD，从零设计/落地 writing 层**；先用 substrate v1 作为可信底座，不重新设计 substrate。
- 读 `architecture.md` 时：其 §2.5 的“substrate 先于 skill”是设计原则；substrate v1 已冻结，当前 writing 阶段以 `AGENTS.md`/本文件/`docs/substrate-v1-freeze.md` 为准。
- 非必要不再优化/改动 substrate；发现真实阻塞（错误/不可用/审计不可信）先报告，不静默改。

## 1. substrate v1 现在做到了什么

### 1.1 能力

- units → sentences/passages（确定性）。
- writing-level claims（1 次模型/视频，可选）：`supported|bounded`、quote、sentence_ids、scope。
- EvidencePack（可选）：segments/sentences/claims/evidence/frames/selection/provenance；audit/selection 用。
- light context：transcript + outline + frames_index + captions；**无 claim**、无 ID/timecode。
- edited text：full/anchored；保序、去重、段标题、frames、boundary（claim path）；source_map audit-only。
- prose Writer：一次调用、Markdown-only；无 JSON/ID/quote 义务。
- quote hygiene：非精确引号只去引号；无模型。
- article binding：fact/quote/paragraph + input-scope；fact 精确/格式变体，quote 精确/归一化，paragraph n-gram 近似。
- 技术接线：`generate.py`（text/article → Writer → hygiene → binding）；不是 skill。

### 1.2 已测结果（3 case；2 短 1 长 28.2min）

| 指标 | 结果 |
|---|---|
| light path 总成本（writer only） | 10.8k / 10.4k / 13.9k（P3）；M1 real 13.0k / 7.5k / 21.6k |
| 旧 structured pipeline | 58.2k / 44.6k / 85.4k；light path 平均约 −78% |
| 短视频 comprehension | B+frames = lean view（18/18 + 18/18）；claims/IDs 0 分 |
| 长视频 comprehension | cw0 = merged text（14/14）；claim 的价值是 selection/boundary |
| boundary | bounded claims 让 q5 1→2；3 case 0 unreported |
| fact binding | 43/43、51/52、4/4；BV17 1 个 0.78 舍入 unsupported |
| quote hygiene | P3/M1 文章 long quote 归零；binding 2/3 complete |
| 文章质量 | developer advisory；结构/机制/边界完整；无 ID/timecode/schema |
| 测试 | **426 passed**（v3 122 + v2 304） |

### 1.3 已知限制

- 没有 >30min；没有第二长视频；没有多文体复用回本实验。
- 没有真实 reader test/A-B；文章质量是 developer advisory。
- paragraph provenance 是 n-gram 近似；fact/quote 级可回查，不能承诺 span 级。
- pack 只保留 selection 句（如 67/116），不是完整转写；binding 需要完整 transcript。
- 数字精度/单位/引号仍可能出现；quote hygiene 处理引号，数字规则已加入 prose 契约但未复测。
- frame caption 是 VLM/OCR 文本，可能不完整；caption cap 160 并报告。

## 2. substrate v1 的边界（writing 层可以依赖什么）

**可以依赖**：`light_context` / `edited_transcript` 的 text + source_map；`bind_article` 的 fact/quote/paragraph/input-scope 报告；`quote_hygiene`；完整 transcript/passages/sentences 作为事实源；可选 claim pack（audit/reuse）。
**不要依赖**：`one_call_writer` 的 3 modes/structured JSON；`prose_writer_probe` 的 evaluation harness；`comprehension_view` dual-mode、`writer_view` A/C、`bind_merged_frames`、`probe_parts`；占位 skill `reader_first_explainer`。`generate.py` 是 substrate v1 的 plumbing 参考，不是 writing 设计基线；writing 层可以自建入口。
**改动规则**：substrate v1 只读；writing 层可以适配/包装，但不重写 substrate；发现真实阻塞先报告。

详细接口/字段/命令见 [docs/substrate-v1-freeze.md](docs/substrate-v1-freeze.md)。

## 3. writing 层期望做到什么（不是路线）

新 session 自己研究如何推进；期望后续达到：

- 对照 JD 定义 writing 层的范围与能力，不沿用现有 writing 实验的架构。
- 一个从零设计的、可验收的 writing skill/writing layer，不是占位；不把模型/模拟盲读当 reader test。
- 使用 substrate v1 的 light text/source_map/binding；不把 claim/ID/JSON 重新塞回 Writer 输入。
- 质量：reader-first 文章能回答 central question、复述机制、说出边界；事实可回查；引用/时间码/审计由代码派生。
- 多文体通过 Skill/View 复用 substrate v1，不为每个文体加 pipeline/validator/gate。
- 真实 reader test/A-B、人工 publish 门、trace/usage/cost 可查；不伪造、不自动发布。
- JD 能力有落点：Writer/optional Verifier、skill/context engineering、评测、工具/trace、成本/观测；不做大而全框架。
- 所有设计先写清输入/输出/消费者/失败状态；先测后调；不按单篇调参。

架构/设计理念见 [architecture.md](architecture.md)；JD 映射参考其 §13。具体 writing 方案、skill 结构、评测方式、代码组织由新 session 自行定义。

## 4. 现有 writing 资产（明确不是基线）

- `skills/writing/reader_first_explainer/`：自动生成占位，未验收；**不要当起点**。见其 `STATUS.md`。
- `src/lunograph/writing_v3/one_call_writer.py`：旧 structured Writer（full_pack/merged_frames/lean_cw0）；历史实验。
- `src/lunograph/writing_v3/prose_writer_probe.py`：P1/P1b/P3 评估 harness；只作参考，不是产品 path。
- `comprehension_view.py` / `writer_view.py` / `bind_merged_frames.py` / `probe*.py`：历史/实验。
- 可以参考它们的 trace/usage/cache 实现和失败状态，但不要继承其 writing 设计。

## 5. 约束 / 纪律

- 先读 `AGENTS.md`（护栏）、`architecture.md`（设计）、本文件、`STATE.md`、`docs/substrate-v1-freeze.md`，再读代码、再规划。
- 非必要不改 substrate；不新增 substrate mode/adapter/coverage tier。
- writing 层从零设计；不直接搬参考 skill 的整条 pipeline/prompt；不复用占位 skill。
- 证据优先；默认 1 Writer；高风险才加 1 次 Verifier；不 loop。
- 多文体 = Skill/View；不为单个文体/单条 finding/单个视频加 validator/gate/词表。
- 不伪造 reader test/A-B；不自动发布；不按单篇调参；不手改 claim/reader。
- `data/`、`参考素材/skills/` 只读；`data/cookies/` 不读。
- 模型调用记录 prompts/usage/latency/trace；失败/partial 不静默。
- worktree 未提交；不要擅自 revert/commit。

## 6. 项目快照

- 分支：`v3`；工作树有未提交改动（substrate v1 + 历史实验）。
- 测试：`PYTHONPATH=src python -m pytest -q` → **426 passed**（v3 122 + v2 304）。
- substrate v1 关键产物：`runs/m1_light/`、`runs/m1_real/`、`runs/p3_light/`；历史：`runs/p0_edit/`、`runs/p1_prose/`、`runs/p1b_prose/`、`runs/s2_probe/`、`runs/s3_boundary/`、`runs/v3_poc/`。
- 分析/证据：`runs/m1_real/analysis.md`、`runs/m1_light/analysis.md`、`runs/p3_light/analysis.md`、`runs/p1b_prose/analysis.md`、`runs/p1_prose/analysis.md`、`runs/p0_edit/analysis.md`。
- 当前 writing 层状态：**未开始**；只有占位 skill 和 substrate plumbing。

## 7. 关键入口

- 规则：[AGENTS.md](AGENTS.md)
- 架构：[architecture.md](architecture.md)
- 状态：[STATE.md](STATE.md)
- substrate v1 合同：[docs/substrate-v1-freeze.md](docs/substrate-v1-freeze.md)
- 旧 substrate 文档（历史）：`docs/substrate-s0.md`、`docs/substrate-s1-*.md`、`docs/substrate-view-contract.md`、`docs/substrate-view-split.md`
- 历史交接：`handoffs/2026-10-31/`、`handoffs/2026-11-01/`

## 8. 启动方式（只规定阅读顺序，不规定路线）

1. 读 `AGENTS.md`、`architecture.md`、本文件、`STATE.md`、`docs/substrate-v1-freeze.md`。
2. 再读实际代码：substrate v1 的 `transcript.py` / `claim_extract.py` / `pack_from_claims.py` / `light_context.py` / `edited_transcript.py` / `bind_article.py` / `quote_hygiene.py` / `generate.py`。
3. 再读现有 writing 实验只作背景（`one_call_writer.py`、`prose_writer_probe.py`），不要当基线。
4. 理解架构/设计理念/开发纪律后，自行研究 writing 层如何设计/落地；不要求沿用任何现有 writing 路线。
