# v3 Substrate 审计：145 claim 从哪来，前序怎么重做

> 日期：2026-10-31
> 对象：BV1ACbi6DEvC（656 秒，约 11 分钟）
> 结论：145 条 claim/evidence 不是写作级 claim，而是 **ASR 碎片 + L1 句级抽取** 的产物。不是 pack 选得太多，是上游粒度太细。

## 1. 实际数字

| 层 | 数量 | 说明 |
|---|---:|---|
| 视频时长 | 656 s | 约 11 分钟 |
| ASR units | 385 | 中位 11 字、1.36 秒/unit；词/短语级 |
| assertions / claims / evidence / links | 145 / 145 / 145 / 145 | 中位 text 28 字、quote 29 字；1 条 claim 每 4.5 秒 |
| 单 unit assertion | 37 | 一个短语就是一条 claim |
| 极短 claim（text ≤ 8 字） | 4 | “我是轩辕”“界面还很粗糙”“配置复杂”等 |
| claim 类型 | fact 107 / opinion 25 / experience 8 / inference 5 | 以句级事实为主 |
| claim 状态 | supported 141 / bounded 4 | 几乎全部 supported |
| relations | 113 | `rel_type` 字段；未进入 pack |
| 帧 | 62 | scene 40 + fixed_interval 22 |
| 有 VLM caption 的帧 | 34 | caption 总 20,379 字，最长 1,745 字 |
| 有 frame_refs 的 evidence | 18 | 帧不是 claim 驱动，是独立采样 |
| 合并后 sentences | 116 | 中位 38 字；由 385 units 合并 |
| 合并后 passages | 32 | 中位 147 字；4 句/passage |

### claim 按 segment 分布

| segment | 内容 | claims |
|---|---|---:|
| seg1 | 开场/被骂/预告 | 9 |
| seg2 | 工具调用/Agent/Harness 科普 | 17 |
| seg3 | Harness 定位 | 10 |
| seg4 | 安装/配置 Key | 16 |
| seg5 | UI 技术细节/工作流 Tab | 9 |
| seg6 | 四种模式定义 | 20 |
| seg7 | 四种模式实测对比 | 29 |
| seg8 | Cordis 插件架构 | 7 |
| seg9 | 批评由来/桌面版增强 | 11 |
| seg10 | 回应被骂/开发者定位 | 17 |

写作需要的是 seg2/3/6/7/8/10 的机制/模式/边界；安装、UI、桌面版增强不是核心。145 条里约 25 条是安装/UI，28 条是批评/回应，真正服务于 central question 的可能只有 40–60 条。

### 典型微 claim

- `seg1-a002`：“我是轩辕。” quote：“大家好，我是轩辕，”
- `seg1-a003`：“今天要把 deepseek harmonyos 拆明白。” quote：“今天咱们就来把 deepseek harmonyos 给拆明白。”
- `seg10-a001`：“界面还很粗糙。”
- `seg10-a002`：“配置复杂。”
- 37 条 assertion 只覆盖 1 个 ASR unit；116 个合并句对应 145 条 claim，说明 L1 抽取把一句话拆成了多条。

## 2. 根因

1. **ASR unit 太细**：385 units，中位 11 字，是词/短语级；没有先合并成句子/段落。
2. **L1 抽取是句级/片段级**：`l1_extract/v6-contract` 几乎逐句抽 claim；atomicity 只抓“过长”，不抓“过短/过碎”。
3. **没有写作级聚合**：145 条 claim 没有按机制/步骤/模式合并成 30–50 条写作 claim；安装、UI、闲聊、预告都保留。
4. **帧独立采样**：40 scene + 22 fixed interval；只有 18 条 evidence 有 frame_refs；VLM caption 无上限，最长 1,745 字。
5. **没有 stage trace**：只有 run manifest/llm_calls；没有每一步的输入/输出/计数/丢弃原因，所以 pack 膨胀到 77k tokens 才发现。

## 3. 前序重做

```text
units.jsonl (385)
  → [deterministic] merge_sentences (116)
  → [deterministic] group_passages (32)
  → [1 model call] claim_extract / aggregate (target 30–50 claims)
  → [deterministic] evidence_link + dedup + teaching filter
  → [deterministic] frame_candidates near claims/passages (2–3/passage)
  → [deterministic] EvidencePack view (4 claims/segment, 2 frames/segment)
  → trace receipts at every stage
```

### 3.1 句子合并（已实现，无模型）

`src/facet_studio/writing_v3/transcript.py`：

- 合并条件：同 segment、间隔 ≤2s、上一 unit 以句末标点结束、单句 ≤180 字。
- BV1AC 结果：385 units → **116 sentences**（中位 38 字）。
- 句子 boundary reasons：sentence_end 105、segment_change 9、max_chars 1、end 1。

### 3.2 passage 分组（已实现，无模型）

- 每 4 句或 450 字切 passage；segment 边界切。
- BV1AC 结果：116 sentences → **32 passages**（中位 147 字）。
- passage boundary reasons：max_sentences 22、segment_change 9、end 1。

### 3.3 claim 抽取/聚合（下一步，1 次模型调用）

输入：32 passages（带 passage_id/sentence_ids/time/text）。

要求：

- 每个 passage 提取 1–3 条**写作级 claim**；能合并的碎片合并，不要逐句复述。
- 跳过：问候、自我介绍、预告、闲聊、赞助、一键三连、频道 logistics、纯 UI 操作细节（除非 request 需要）。
- 每条 claim 必须带 passage 内的**精确 quote**、sentence_ids、time range；不编造外部事实。
- 标注 kind（fact/opinion/experience/inference/instruction）、scope、confidence、status。
- 输出目标：30–50 条 claim；如果不足，写 gap；如果过多，合并/丢弃低信息片段。
- 确定性后检：quote 是 passage 子串；sentence_ids 存在；近重复 claim 合并；无 quote 的 claim 拒绝。

预期效果：claims 145 → 30–50；evidence quote 29 字 → 1–3 句；pack 从 130k chars/77k tokens → 约 30–50k chars/20–30k tokens。

### 3.4 帧选择（下一步，确定性）

- 以 claim/passage 的时间范围为 key node，在 ±N 秒内取候选帧。
- 优先 OCR/VLM 与 claim 相关、幻灯片/屏幕/代码/UI 完整、清晰、非重复。
- 每个 passage 保留 2–3 帧；VLM caption 截断到 160 字或改为短“看哪里”。
- 真实帧只作演示；没有匹配帧写 text_experiment/no_demo。

### 3.5 EvidencePack（已有，需接新 claim）

- 按 request focus 选 claim；每 segment 最多 4 条。
- 每 segment 最多 2 帧；caption 截断。
- 模型输入用 compact JSON；pack 文件可保留 pretty 供人看。

## 4. Trace / 可观测

每个 stage 写：

- `trace.jsonl`：append-only 事件（stage/status/counts/decision）。
- `stage_receipts/<stage>.json`：inputs/outputs path+sha256+bytes、counts、params、decisions、samples。
- `llm_calls.jsonl`（已有）：stage/model/prompt hash/usage/raw response。
- 原始 stage 输出：units/sentences/passages/claims/evidence/frames/pack，全部保留。

当前已实现：

- `src/facet_studio/writing_v3/trace.py`：TraceRecorder。
- `examples/BV1AC_transcript_receipt.json`：385→116→32 的完整 receipt（input/output hashes、counts、boundary reasons、samples）。

下一步要补：

- `claim_extract` receipt：passages_in/claims_out、drop/merge reasons、模型 usage、quote 校验通过率。
- `evidence_link` receipt：claim/evidence/frame counts、quote 校验、dedup。
- `frame_select` receipt：candidates/kept/dedup/caption truncation。
- `evidence_pack` receipt：claims_in/selected、frames_in/selected、pack chars/tokens estimate、truncation。

## 5. 实际结果（2026-10-31）

### 5.1 claim 聚合

`claim_extract` 在 32 passages 上跑了一次：

- claims：**145 → 43**（raw 43，accepted 43，rejected 0，duplicates 0）
- 中位 text **37 字**、quote **58 字**（原来是 28/29）
- 类型：fact 27 / opinion 9 / experience 5 / instruction 1 / inference 1
- 状态：supported 43（全部）
- 每段：seg6 9、seg4 6、seg10 6、seg2 5、seg7 5、seg3 4、seg5 3、seg8 3、seg9 2、seg1 0（开场/预告被跳过）
- 用量：prompt 5,387 / completion 25,890 / reasoning 21,647 / total 31,277 tokens；latency 115.8s
- trace：[claim_extract receipt](examples/BV1AC_claim_extract_receipt.json)、[pack receipt](examples/BV1AC_pack_receipt.json)

质量示例（写作级 claim）：

- “Harness 是管理工具、上下文、权限、校验、重试和运行记录的工程系统。”
- “四种工作模式本质上是四套 Agent 组装方案。”
- “PTC 让模型写脚本把中间工具串起来调用，从而减少大模型交互次数。”
- “四种模式不是四套程序，而是同一个 Harness 加载四份插件清单。”

仍存在的上游问题：

- ASR 误识别：`harmonyos`（Harness）、`Share`（Shell）、`cortis`（Cordis）等；claim 文本有时做了纠正，quote 仍是原始 ASR。
- 少数 quote 被 ASR 标点/断句截断（如“时间的验”）；claim 文本是完整语义，但 quote 不完整。
- 这些不是 claim 聚合能完全修的；需要在 `quote_normalized`/ASR correction 或 Writer 的 claim 选择层处理，不能假装 quote 是干净的。

### 5.2 重建 pack（coverage-aware）

第一次按“每段 top-k lexical”重建时，seg6 的 5 个 passage（四种模式）会被压成 4 条，标准模式可能被 PTC/极简/创造挤掉。这是**选择机制问题**，不是单篇问题。已改为：

1. 每个 passage/beat 先选 1 条最佳 claim；
2. 剩余名额再按 request focus 补；
3. 同时带 gaps/conflicts 和 snapshot/outline provenance。

结果：

- segments 10、sentences 53、claims **40**、evidence 40、frames 20
- pack chars **47,850**（pretty）、**38,200**（compact）
- 无截断
- passage coverage：seg6 覆盖 p01–p05（四种模式 + 总述），seg7 覆盖 p01/p03/p05/p06（标准、PTC、创造、总结），seg8 覆盖 Cordis/插件
- 4 种模式都有 claim：标准、PTC、极简、创造；gaps 7 条
- 预计 Writer 输入约 22–25k tokens，而不是 77k

### 5.3 手工检查：给后续写作的输入是否合理

**覆盖**：central question 需要的四块都在：
- Harness 是什么/负责什么：seg2（5 条）
- 四种模式：seg6（6 条，含标准/PTC/极简/创造）+ seg7（5 条对比/总结）
- Cordis 插件化为什么能支撑四模式：seg8（3 条）
- 边界/定位：seg9（2 条）+ seg10（6 条）

**分布**：40 条中约 23 条是核心机制/模式/插件，17 条是安装/UI/批评/定位。核心占 57%，足够写 2k 字；上下文偏多，但 Writer skill 可以按 central question 取舍。安装/UI 不应成为独立章节；如果 Writer 把它们写成 walkthrough，是 skill 的取舍问题，不是 pack 缺数据。

**是否比只看 ASR 好**：是。Writer 拿到的是 40 条规范化 claim（中位 37 字）、53 句上下文、20 个帧候选、7 条 gap、精确 quote/timecode；不是 385 个 ASR 碎片或 145 条微 claim。Writer 不需要自己从 transcript 里抽 claim。

**顺序**：pack 仍按视频 segment 时间顺序，不是读者认知顺序。Writer 必须重组（先 Harness/问题，再四模式，再 Cordis，再边界）；skill 已要求 reader_path，但这是 Writer 的负担。后续可加一个 `reader_path` View（按 claim 角色/依赖重排），但当前 40 条规模下一次 Writer 可以处理。

**帧**：20 个候选，每段 2 个，按 claim/passage 时间窗选；不保证和 claim 对得上——按你的要求，关键节点前后+时间段候选即可，后续用图表/生成图补美观。

**仍存在的上游问题**：
- ASR 误识别（harmonyos/Share/cortis）和 quote 截断（“时间的验”）；claim 文本有时纠正，quote 仍原始。
- 帧没有 claim-level 匹配保证；只做时间窗候选。
- 视觉 caption 有长有短；已截断 160 字，但仍只是选帧依据，不是事实。

## 6. 结论

- **不要继续在 145 条微 claim 上做 pack 过滤**；那是下游补丁。
- 385 units → 116 sentences → 32 passages → 43 claims 已经跑通；coverage-aware pack 选 40 条，pack 从 130k chars 降到 47.8k chars（compact 38.2k）。
- 每次 stage 留 receipt，后续调参看 trace，而不是靠猜 token 为什么高。
- P0 Writer 已用这份 40-claim pack 跑通：reader 1,865 字、38k tokens、校验 complete；见 [p0-one-call.md](p0-one-call.md)。下一步是 BV17 第二视频 + reader test/轻量 A-B；不按 BV1AC 调参。
