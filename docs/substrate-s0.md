# Substrate S0：质量合同、评测协议与 trace schema

> **历史文档（2026-10-31）**：S0 是当时的 substrate 设计/评测协议；当前 substrate v1 契约/证据/限制见 [substrate-v1-freeze.md](substrate-v1-freeze.md)。
> 状态：S0 设计文档（2026-10-31）
> 范围：只定义 substrate 阶段；不改代码、不跑模型、不做 skill/reader test。
> 上位：[architecture.md](../architecture.md) §2.5、§5、§9、§16；规则见 [AGENTS.md](../AGENTS.md)。

## 1. 目的与边界

当前阶段是 **substrate 打磨**，不是 skill 阶段。先证明 substrate 本身足够好、足够高效、不冗余、不离散、比 raw ASR/merged text 更适合理解+写作，再进入 skill 阶段。

本文件定义三件事：

1. **质量合同**：什么算 substrate 过关，哪些指标必须有数。
2. **评测协议**：怎么测、和谁比、记录什么。
3. **trace schema**：模型调用/阶段的输入输出怎么记录，便于 AI 工程优化。

非目标：

- skill 打磨、真实 reader test/A-B、P1 freeze、第二文体、Verifier、发布门。
- 不按单篇调参；不手改 reader/claim；不为单个视频加特例。
- 不把 P0 的 1,865 字/38k tokens 当质量、成本或长度承诺。

## 2. 分层与消融

Substrate 不是一层，至少四层：

| 层 | 当前产物 | 必须回答 |
|---|---|---|
| L0 raw ASR | units（时间码/原文） | 是否保留原始证据 |
| L1 merged text | sentences/passages | 合并是否降低碎片、保留上下文 |
| L2 claims | writing-level claims（1–3/passage） | 是否抓住机制/步骤/边界，是否去冗余 |
| L3 evidence/context | evidence quote + sentence context + timecode + frames | 是否可回查、带上下文、可用于写作 |
| L4 view/pack | EvidencePack（selection/truncation） | 是否按请求/文体选择，覆盖够、不静默丢 |

评测用 3-way 消融：

- **A = raw ASR units**：原始碎片+时间码。
- **B = merged sentences/passages**：纯文本，无 claim/evidence/frame。
- **C = substrate pack**：claims + evidence + context + frames。
- 可选消融：`C-frames`、`C-context`（只留 claim+quote）、`C-claims`（只留 sentences+quotes），用来判断每个组件是否在赚成本。

## 3. 质量合同（scorecard）

### 3.1 覆盖 Coverage

指标：

- `passages_considered`、`passages_with_selected_claim`、`passages_with_zero_selected_claim`
- `segments_with_zero_claims`（区分 core / intro / outro）
- `claims_considered/selected`、`claims_per_segment`、`claims_per_passage`
- `required_information_coverage`：request.required_information 的每一条是否有 claim/evidence 支撑（人工/probe）

目标（advisory，不写死数值）：

- 每个 core passage/beat 至少有一条可选 claim；
- 没有 core segment 是 0 claim；
- 被丢弃的 passage/claim 必须有原因。

当前事实：40/28 claims；BV1AC seg1、BV17 seg7 是 0 claim（开场/结尾）；per-segment cap 6；BV17 segment labels 全空。需要先测“core passage 有没有 0 claim”，不能只看总 claims。

### 3.2 上下文 Context

指标：

- `claims_with_context / selected_claims`：claim 的 quote 所在 sentence 是否在 pack.sentences 里
- `context_chars_per_claim`、`neighbor_window`
- `context_missing` 列表 + 原因

目标：

- 每条 selected claim 至少带一条 quote 所在 sentence 作为上下文；
- 邻域上下文按预算补，不静默丢；
- context 丢失必须进 selection/truncation 报告。

当前事实：BV1AC 16/40、BV17 8/28 的 claim 没有任何 sentence context；Writer 实际用了 10/23、7/21 条。**不达标**。

### 3.3 忠实 / 可回查 Faithfulness

指标：

- `quote_in_sentence_text`：quote 是否是 `sentence_ids` 拼接文本的连续子串
- `timecode_matches_sentence_union`：evidence 时间范围是否等于这些 sentence 的并集
- `source_claim_ids` / `source_evidence_ids`：是否存在、是否能在 snapshot 里解析
- `stance` / `support_status` / `rights_scope`：是否存在
- `numbers/names_traceable`：claim 里的数字/专名是否能在 quote/evidence 里找到
- `asr_conflicts_surfaced`：ASR vs screen 的冲突是否被记录，而不是静默纠正

目标：

- selected claim 的 quote/time/source IDs 100% 可回查；
- 任何 ASR 纠正都有记录，quote 保持原始；
- 写作级 claim 不能成为第二套事实源。

当前事实：quote 可检查；timecode 是 passage 级；无 `source_claim_ids`/`source_evidence_ids`；stance 固定 `supports`；缺 `rights_scope`。

### 3.4 不冗余 Non-redundancy

指标：

- `pack_compact_chars`、`pack_tokens_est`、`content_chars`（claims+quotes+sentences）
- `content_chars / pack_compact_chars`、`unique_ngram_ratio`
- claim text / quote / sentence context 的 2-gram 重叠
- `claims_used_by_probe / claims_selected`
- `tokens_per_selected_claim`、`tokens_per_used_claim`
- `frame_candidates_per_used_frame`

目标：

- 没有重复 claim/evidence；
- pack 的 JSON/元数据开销有理由（binding/context/audit）；
- 测一版更紧凑的数组式 schema；如果 probe 不掉分且省 token，就采用。

当前事实：compact pack 38.2k chars / 40 claims；真正内容（claims+quotes+sentences）约 5–6k chars；未度量 unique 比例、Writer/probe 实际使用率。

### 3.5 不离散 Non-fragmentation

指标：

- `claims_with_context`（同 3.2）
- `claim_order_is_time_or_argument`：每个 segment 内 claims 是否按 passage/time 或显式 reader-path 顺序
- `segment_label_present`
- `claim_self_contained`：抽 10 条 claim 人工检查，能否脱离视频理解
- `fragment_claims`：过短/只有代词/无谓语的 claim（人工抽样，不做正则硬门）

目标：

- 不是 hash-order bag；
- segment label 有值，或明确 fallback/warning；
- selected claim 自洽，且有上下文。

当前事实：claims 按 `(segment_id, claim_id)` hash 排序；BV1AC 6/10、BV17 5/7 个 segment 非时间序；BV17 segment labels 全空；zero-context 问题仍在。

### 3.6 下游价值 Downstream

固定 probe（不是 skill）：

- 问题：central question、2–3 个机制/步骤问题、1 个边界/证据不足问题、1 个精确 quote/时间码问题。
- 输入 A/B/C；同一模型、同一参数、同一 prompt；记录 raw output。
- 评分：每题 0–2（0=缺失/错误，1=部分，2=完整且忠实）；C 另外检查 citation/timecode 精度。
- 可选写作 probe：中性 prompt“write a 1,000–1,500 char explainer from the input”，同模型；评为连续性/机制/边界。这不是最终 skill，只作 substrate 相对测试。
- 人工盲评优先；模型 judge 只作 advisory，不作唯一 gate。

目标：

- C 在机制/步骤/边界覆盖上 >= B；C 不能比 B 丢关键事实；
- C 在 quote/timecode 可回查上必须优于 B（B 没有）；
- 如果 C <= B，claim/evidence 层没有赚到成本，先修或简化，不进 skill；
- 如果 B <= A，merge 层没有赚到成本，先修 transcript merge。

当前事实：还没有 A/B/C 对照。

### 3.7 成本 / 延迟

指标：

- calls/video、prompt/completion/reasoning/cached tokens、latency
- claim extraction 摊销：第一个文体 vs marginal 文体
- cost per selected claim / per 1k pack chars / per probe answer
- failure/partial rate

目标：

- 现阶段不设硬门槛；用 before/after 和 per-case delta；
- 每次实验记录 tokens/latency；
- P0 的 69k/226s 是参考，不是承诺。

当前事实：2 calls、69,348 tokens、约 226s（BV1AC）；claim extraction 31k/20k；cache 是手工的。

### 3.8 可观测 Observability

指标：

- 每次模型调用有 trace（见 §5）
- 每个 stage 有 receipt
- 每个实验有 manifest
- replay：同输入 hash → 同输出；cache hit/miss 可见

目标：

- 任何一次调用都能重建输入/输出；
- 任何 selected/dropped 项都有原因；
- 能回答“为什么贵、为什么丢、为什么选”。

当前事实：有 receipts/metrics；无 prompt hash/完整 prompt；无 `llm_calls.jsonl`；无自动 cache/replay。

## 4. 评测协议

### 4.1 Cases

- 当前用 BV1AC、BV17；第三个视频等用户提供 data 结构后再加，不先扫描 `data/`。
- 每个 case 固定：video、request.json、question set、reference answers（人工从视频/substrate 写）、模型/参数、probe prompt。
- 不按 case 调参；报告 per-case 和 aggregate。

### 4.2 Inputs

- **A raw ASR**：units + 时间码，原样。
- **B merged text**：sentences/passages 纯文本，无 claim/evidence/frame；默认保留句/段时间码，另做 `B-no-timecode` 消融，避免把 timecode 差异当成 merge 差异。
- **C substrate pack**：当前 pack（claims + evidence + context + frames）。
- 可选：`C-frames`、`C-context`、`C-claims`，只在 A/B/C baseline 之后做。

### 4.3 Probe

- 固定 system prompt：只从输入回答；证据不足就说不足；要求引用时给精确 quote/时间码。
- 固定 user template：input + questions。
- 同一模型/参数；temperature 0；max_tokens 固定；每个 input/case 跑 1 次（需要方差时再 3 次）。
- 保存 raw prompt/response；不使用 reader-first skill prompt。

### 4.4 Scoring

- 人工盲评优先：0/1/2；边界题单独记。
- Citation：引用的 quote 是否在输入里；timecode 是否匹配。
- 模型 judge 只作 advisory。
- 记录 tokens/latency per input。
- 报告：per case、per input、per question；C-B、B-A delta；失败样例。

### 4.5 Acceptance（advisory）

- C >= B on mechanism/step/boundary in both cases；C 不丢 B 的关键事实。
- C > B on quote/timecode traceability（确定性）。
- 如果 C <= B，claim/evidence 层不赚成本；如果 B <= A，merge 层不赚成本。
- A/B/C 输入长度不同：记录 tokens，报告 per-1k-token 收益；C 不能只靠更长上下文赢。
- 成本只记录，不设硬阈值，直到 3+ cases。

## 5. Trace schema

### 5.1 每次模型调用

字段：

- `call_id`、`stage`、`key`、`model`、`provider`、`params`（temperature/max_tokens/reasoning 配置）
- `system_sha`、`user_sha`、`system_path`、`user_path`
- `input_refs`（passage_ids/pack_id/request_id）、`output_refs`（claim_ids/section_ids）
- `raw_response_path`、`parsed_output_path`
- `usage`：prompt/completion/reasoning/cached/total tokens
- `latency_ms`、`finish_reason`、`status`、`error_kind`
- `validation`：issues 分类计数（quote/timecode/ID/number/structure/hygiene）
- `decision`：为什么用这个模型/参数/输入（如 extraction baseline、probe C）
- `created_at`

存储：

- `runs/<experiment>/calls.jsonl`：每行一次调用。
- `runs/<experiment>/prompts/<call_id>.system.txt` / `.user.txt`
- `runs/<experiment>/responses/<call_id>.txt`
- 不写 cookies/密钥；必要时 redact。

### 5.2 每个 stage

- inputs/outputs：path + sha256 + bytes
- counts：in/out/selected/dropped
- decisions：selection policy、focus、budget、truncation reasons
- coverage/context/redundancy metrics
- usage/cost 聚合
- samples：少量代表项，不塞全量

### 5.3 实验 manifest

- `experiment_id`、date、git commit、case、input variant（A/B/C）、model/params/prompt version、question set version、scoring version
- before/after 对比表
- artifacts 路径（pack、claims、traces、probe outputs）

## 6. S1 backlog（按优先级）

1. **Context coverage**：每条 selected claim 至少带 quote 所在 sentence；再补 ±2 邻域；报告 missing；不要在覆盖前按 6 句截断。当前 16/40、8/28 missing。
2. **Timecode/quote alignment**：quote ∈ sentence text；evidence 时间 = sentence 并集；用于 frame window；不满足则 `binding_failed`。当前 passage 级；22/40、19/28 偏宽。
3. **Order/labels**：claims 按 passage/time 或显式 reader-path 排序；segment label 从 outline 取，contract 只作 fallback；空 label 记 warning。当前 hash 序；BV17 labels 空。
4. **Substrate link**：加 `source_claim_ids`/`source_evidence_ids`；按 sentence/unit/time 确定性 join；带 stance/support_status/rights_scope/extraction conflicts。当前没有。
5. **Selection/truncation report**：dropped claim/sentence/frame 带原因；不静默丢。当前只统计 pack-size 裁剪。
6. **Trace/cache**：`call_sink`、prompt hash/原文、`llm_calls.jsonl`、content-addressed cache；测 prompt 顺序/前缀缓存。当前没有。
7. **v3 tests**：transcript merge、pack coverage/order/context、validator quote/timecode、pack hash/replay。当前没有。
8. **Long-video/truncation policy**：每个 passage 至少留一条 claim；不删某 segment 的唯一 claim；先删冗余上下文；记录原因。当前样本未触发，后置。

## 7. S2 / S3

- **S2**：在 BV1AC/BV17 跑 3-way probe；记录 trace；计算 scorecard；判断每层是否赚成本。
- **S3**：用 trace 对比 extraction 模型/参数/prompt；比较 probe 分数和成本；不加新阶段；保留通用配置，不按视频调。

## 8. 当前实测事实（S1 的种子）

> 以下为 S1-1 前的基线；S1-1…S1-6 后的数字见 [substrate-s1-context.md](substrate-s1-context.md)、[substrate-s1-timecode.md](substrate-s1-timecode.md)、[substrate-s1-order.md](substrate-s1-order.md)、[substrate-s1-link.md](substrate-s1-link.md)、[substrate-s1-coverage-trace.md](substrate-s1-coverage-trace.md)、[substrate-s1-no-trunc.md](substrate-s1-no-trunc.md)。

- P0：BV1AC 40 claims/20 frames/47,850 pretty/38,200 compact；Writer 38,071 tokens；claim extract 31,277；约 226s。BV17 28 claims/13 frames/30,556；Writer 33,583；claim extract 20,239。
- 上下文：BV1AC 16/40 zero；BV17 8/28 zero + 1 partial；Writer 用了 10/23、7/21。
- 时间码：BV1AC 22/40 比 sentence 并集宽 5s 以上；BV17 19/28；1 条 BV17 quote 不在列出的 sentence 文本里。
- 顺序：top-level claims 按 hash 排序；BV1AC 6/10、BV17 5/7 个 segment 的 top-level claims 非时间序；`segments.claim_ids` 是选择顺序。S1-3 已修，见 [substrate-s1-order.md](substrate-s1-order.md)。
- 状态：BV1AC 40/40 supported/high；BV17 27/28 supported/high + 1 bounded/medium。
- Pack builder：S1-4 已修；`provenance` 通过 unit overlap 回接 snapshot atomic claims/evidence（40/40、28/28），见 [substrate-s1-link.md](substrate-s1-link.md)。
- Trace：S1-5 已加 prompt 原文/`llm_calls.jsonl`/`CachedLLM`；S1-6 实测 cache hit；`ReplayLLM` 仍未接这两个 stage，见 [substrate-s1-coverage-trace.md](substrate-s1-coverage-trace.md)、[substrate-s1-no-trunc.md](substrate-s1-no-trunc.md)。
- 硬截断：S1-6 已移除；full pack 超预算只记 `over_budget`，writer view 用 `parts` 分区。
- 测试：342 passed（v3 38 + v2 304）。

## 9. 开放问题

- “core passage/segment”怎么定义？先用 request.required_information + 人工标注，不做固定规则。
- probe 每个 case 多少题？先 5–6 题：central、2 个机制/步骤、1 个边界、1 个 quote/时间码。
- 人工 vs 模型 judge：人工盲评主，模型 advisory。
- 第三个视频：等用户提供结构，不扫描 `data/`。
- B 是否保留时间码/段标：默认保留，另做 `B-no-timecode` 消融。
- A/B/C 输入长度不同时怎么归因：记录 tokens，报告 per-1k-token 收益；必要时做等长截断对照。
- 成本目标：3+ cases 前只记录，不设硬门。
- ASR 纠正：quote 保持原始；claim text 的纠正在 trace 里记 correction note，不静默改写 quote。
- pack schema：数组式 vs 对象式；probe 不掉分才换。
- `reader_path` View：等 S2 出现第二个文体/读者顺序问题再加，不现在加。

## 10. 交付 / 下一步

- 本文件是 S0 交付物；不改代码、不跑模型。
- 下一步：确认 S0 后进 S1（确定性修复，带 before/after），再做 S2 3-way probe；substrate 过关后才做 skill。
