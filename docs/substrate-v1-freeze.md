# Substrate v1 Freeze：writing 层可以依赖什么

> 状态：2026-11-01 冻结。substrate v1 是 writing 层的可信底座；非必要不再改。
> 这不是 writing 路线；writing 层设计由新 session 自己研究。
> 历史 substrate 文档（S0/S1/view-contract/view-split）只作背景，不是当前基线。

## 1. 一句话

**默认 light path**：transcript（sentences/passages）+ frames → 一段无 claim/ID 的 edited text → Writer 写散文 → 代码做 quote hygiene + fact/quote/paragraph binding。
**可选 claim path**：claim extraction + pack + anchored text，用于 audit/boundary/多文体复用/全文超预算；不是默认输入。

## 2. 数据流

```text
source/video
  → units（ASR，时间码）
  → sentences / passages（确定性）
  → [可选] writing claims（1 次模型/视频）
  → [可选] EvidencePack（claims/evidence/segments/frames/provenance）
  → light context 或 edited text
       ├─ full：transcript + outline labels + frames
       └─ anchored（claim 可选）：claim anchor 句 + boundary + frames
  → prose Writer（一次；Markdown）
  → quote hygiene
  → bind_article（fact / quote / paragraph；input-scope）
  → reader.md + binding.json + audit
```

## 3. 默认 light path 的接口

### 3.1 `light_context.py`

输入：`passages`、`sentences`、`temporal_outline`、`frames_index`、可选 `frame_captions`。
输出：pack-shaped context（`claims=[]`、`evidence=[]`）、full edited text、source_map、manifest。

- 段标签来自 outline；frame 由 `t_start_ms`/`t_end_ms` 分配到 segment；每段最多 `max_frames_per_segment`（默认 2）。
- frame caption 默认 cap 160 chars；记录 `caption_truncated` / `caption_full_chars`。
- 不新增事实；无 claim/boundary marker。

命令示例：

```bash
PYTHONPATH=src python -m lunograph.writing_v3.light_context \
  --passages runs/v3_poc/<video>_transcript/passages.json \
  --sentences runs/v3_poc/<video>_transcript/sentences.json \
  --outline <temporal_outline.json> \
  --frames-index data/<video>/frames_index.json \
  --frame-captions data/<video>/frames_vlm__frames_scene.json \
  --video-id <video> \
  --out runs/<run>/light_pack.json \
  --out-text runs/<run>/light_text.txt \
  --out-source-map runs/<run>/source_map.json \
  --out-manifest runs/<run>/manifest.json
```

### 3.2 `edited_transcript.py`

- `build_edited_transcript(pack_or_light_context, passages, sentences, mode="full"|"anchored"|"auto")`
- 输出：`text`（无 passage/sentence/claim ID、无时间码）、`source_map`（block → IDs）、`decision`。
- full：全量 passages + 段标题 + frames；anchored：claim anchor 句 + boundary（claim path）。
- `source_map` 是 audit-only；不进 Writer 上下文。
- 不硬截断；超预算只记录。

### 3.3 `bind_article.py`

- 输入：article、pack（或 light pack）、完整 transcript sentences、可选 `rendered_text`/`source_map`、`input_text`。
- 输出：`status`、`counts`、`paragraphs`、`unsupported_facts`、`outside_input_facts`、`outside_input_quotes`、`quote_unbound`、`notes`。
- fact：数字/拉丁 token；严格匹配失败后尝试 spacing/unit 变体 → `format_variant`。
- quote：精确匹配 → 标点/填充词归一化；转述 → `unbound`。
- input-scope：`in_input` / `outside_input` / `outside_input_variant` / `unsupported`。
- paragraph：character n-gram 覆盖，近似；不能承诺 span 级。
- 不调用模型；full pack + transcript 是事实源。

### 3.4 `quote_hygiene.py`

- 输入：article + writer input。
- 非精确/非归一化引号只去掉引号，不改文字；报告 `checked/kept/removed`。
- 不调用模型。

### 3.5 `generate.py`（技术接线，不是 skill）

- `edited text/article → prose Writer（可选 --run）→ quote hygiene → bind_article → article/reader/binding/manifest`。
- dry-run 默认；`--run` 才调用模型。
- 这是 substrate v1 到 writing 层的 plumbing，不是 writing 设计基线；writing 层可以改造/替换。

## 4. 可选 claim path

- `claim_extract.py`：passages → writing claims（1 次模型/视频）；`status=supported|bounded`、quote、sentence_ids、scope。
- `pack_from_claims.py`：claims/passages/sentences → pack（segments/sentences/claims/evidence/frames/selection/provenance）。
- `edited_transcript.mode=anchored`：claim anchor 句 + boundary + frames；可在长视频/全文超预算时使用。
- claim 层价值：audit/boundary/多文体复用/selection；**不是 comprehension**。
- 当前证据：单篇 one-off 不跑 claim 更便宜；多文体是否回本未测。

## 5. 已验证证据（3 case）

| 指标 | 结果 |
|---|---|
| light path 总成本（writer only） | 10.8k / 10.4k / 13.9k（P3）；M1 real 13.0k / 7.5k / 21.6k |
| 旧 structured pipeline | 58.2k / 44.6k / 85.4k；light path 平均约 −78% |
| 短视频 comprehension | B+frames = lean view（18/18 + 18/18）；claims/IDs 0 分 |
| 长视频 comprehension | cw0 = merged text（14/14）；claim 的价值是 selection/boundary |
| boundary | bounded claims 让 q5 1→2；3 case 0 unreported |
| fact binding | 43/43、51/52、4/4；BV17 1 个 0.78 舍入 unsupported |
| quote hygiene | P3/M1 articles long quote 归零；binding 2/3 complete |
| 文章质量 | developer advisory；3 篇结构/机制/边界完整；无 ID/timecode/schema |
| 测试 | 426 passed（v3 122 + v2 304） |

## 6. 已知限制（writing 层需要知道）

- 样本：2 短 + 1 长（28.2min）；没有 >30min；没有第二长视频。
- 没有真实 reader test/A-B；文章质量是 developer advisory。
- paragraph provenance 是 n-gram 近似；fact/quote 级可回查，不能承诺 span 级。
- pack 只保留 selection 句（如 67/116），不是完整转写；binding 需要完整 transcript。
- 数字精度/单位/引号仍可能出现；quote hygiene 处理引号；数字规则已加入 prose 契约，但未复测。
- frame caption 是 VLM/OCR 文本，可能不完整；caption cap 160 并报告。

## 7. 稳定性契约

writing 层可以依赖：

- `light_context` / `edited_transcript` 的 text + source_map 形状；
- `bind_article` 的 fact/quote/paragraph/input-scope 报告；
- `quote_hygiene` 的 deterministic 行为；
- `generate` 的 dry-run/run plumbing（可参考/改造，不是 writing 设计基线）；
- 完整 transcript/passages/sentences 作为事实源。

writing 层不要依赖：

- `one_call_writer` 的 3 modes / structured JSON output；
- `prose_writer_probe` 的 evaluation harness（可参考，不是基线）；
- `comprehension_view` dual-mode、`writer_view` A/C、`bind_merged_frames`、`probe_parts`；
- 占位 skill `reader_first_explainer`。

非必要不改 substrate。发现真实阻塞（错误/不可用/审计不可信）先报告，不静默改。
