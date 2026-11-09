# S2 probe：raw ASR / merged text / lean view 三路对照

> 状态：设计 + harness 已完成（2026-10-31）；**模型调用尚未执行**。
> 上位：substrate-s0（历史文档） §3.6 / §4；substrate-view-contract（历史文档）。
> 范围：substrate 评测；不做 skill、不做 reader test/A-B、不按单篇调参。

> **命名说明**：本文沿用 substrate-s0（历史文档） 的三路消融命名：**A = raw ASR，B = merged text，C = lean view**。注意 substrate-view-contract（历史文档） 里的 A = lean view、C = index+parts，是另一套命名；本 probe 的 C 指 lean view，不是 index+parts，也不是 full pack（full pack 只作 audit）。

## 1. 这个 probe 回答什么

substrate 的 claim/evidence/view 层是否值得它的体积和调用成本。具体判断：

- **C（lean view）相比 B（merged text）**：claims/evidence/context/frames/IDs 有没有带来更好的机制、步骤、边界和引用表现？
- **B（merged text）相比 A（raw ASR）**：确定性合并有没有降低碎片、保留上下文？
- 如果 C ≤ B，claim/evidence 层没有赚到成本，先简化，不进入 skill 阶段。
- 如果 B ≤ A，merge 层没有赚到成本，先修 transcript merge。

这不是“能写一篇文章”的测试；写作质量由后续 skill/reader 阶段负责。

## 2. Cases 与输入

两个 case：BV1AC（DeepSeek Harness）、BV17（EmbeddingGemma 2）。同一 case 的三路输入只改变证据形式，题目、模型、参数、prompt 完全一致。

| case | A raw ASR chars | B merged text chars | C lean view chars |
|---|---:|---:|---:|
| BV1AC | 11,553 | 5,589 | 15,861 |
| BV17 | 5,331 | 2,500 | 9,753 |

渲染规则（[probe.py](../../src/facet_studio/writing_v3/probe.py)）：

- **A raw ASR**：`units.jsonl` 每行一个 unit，格式 `[start-end s] 原文`；保留 raw 单元边界和时间码；不含 segment label/claim/evidence/frame。
- **B merged text**：`passages.json` 每个 passage 一行，格式 `[passage_id start-end s] 合并原文`；segment 之间空行；不含 claim/evidence/quote/frame。
- **C lean view**：`writer_view.json` 的 compact JSON 原样；`span` 是 `"".join(segment.context)` 的下标区间，`quote` 是 fallback；保留 claim/evidence/frame ID。
- 三路使用同一个 system prompt；user prompt 只在 input block 不同。
- **C 比 A/B 大**：BV1AC C 15.9k vs A 11.6k vs B 5.6k；BV17 C 9.8k vs A 5.3k vs B 2.5k。因此 C 必须用质量赢，不能用“更长”解释。

## 3. 固定题集与参考答案

每个 case 6 题，固定写入：

- [questions_BV1AC.json](questions_BV1AC.json) / [reference_BV1AC.md](reference_BV1AC.md)
- [questions_BV17.json](questions_BV17.json) / [reference_BV17.md](reference_BV17.md)

题型：central ×1、mechanism/procedure ×3、boundary ×1、quote ×1。参考答案从 **merged ASR** 整理，不拿 claims 当金标；评分前必须由开发者对照视频复核。quote 题要求原文连续子串，用来测 C 的 span/quote 是否可还原。

## 4. 模型、参数与 trace

- 模型：`.env` 的 `DEEPSEEK_MODEL`（当前 `deepseek-flash`）；同一 case 三路同模型。
- `temperature=0`；probe **不暴露、也不设** max_tokens 参数，使用 provider/settings 的 `max_output_tokens`；不做输入截断，也不对答案做长度硬校验。每个 variant 1 次调用（6 题一起答），不重试。如果出现 `provider_output_empty`，检查 provider 的 `max_output_tokens` 配置；不要靠截断输入解决。
- cache：默认 `runs/_cache/llm`，按 provider request identity 命中；hit 记录 `cached=true`，不调用 provider。
- trace 目录（每个 case 一个）：
  - `manifest.json`：case、inputs/hashes、questions/hash、model/params、每个 variant 的 rendered/prompt/response/usage/latency/finish_reason。
  - `llm_calls.jsonl`：provider 调用记录（prompt hash、usage、latency、finish_reason、decision）。
  - `<variant>/rendered.txt`、`<variant>/prompts/{system,user}.txt`、`<variant>/response.txt`（仅 `--run`）。
- 不把 response 写进 jsonl；原文单独存文件。

## 5. 执行顺序（需用户确认后才跑模型）

### 5.1 前置：BV17 用新 claim 合同重跑

BV1AC 的 C 使用新合同 claims；BV17 仍是旧合同。为保证两 case 同合同，先跑：

```bash
PYTHONPATH=src python -m facet_studio.writing_v3.claim_extract \
  --passages runs/v3_poc/BV17_transcript/passages.json \
  --out-dir runs/s2_probe/BV17_claims
```

然后确定性重建 BV17 pack + views（不调用模型）：

```bash
PYTHONPATH=src python -m facet_studio.writing_v3.pack_from_claims \
  --claims runs/s2_probe/BV17_claims/claims.json \
  --passages runs/v3_poc/BV17_transcript/passages.json \
  --sentences runs/v3_poc/BV17_transcript/sentences.json \
  --snapshot runs/run_20261029T163854Z_BV17DHC6CELr_1451/evidence_snapshot.json \
  --outline runs/run_20261029T163854Z_BV17DHC6CELr_1451/temporal_outline.json \
  --knowledge runs/run_20261029T163854Z_BV17DHC6CELr_1451/knowledge_snapshot.json \
  --request runs/_scripts/requests/BV17DHC6CELr.json \
  --contract data/BV17DHC6CELr/substrate/contract.json \
  --video-id BV17DHC6CELr \
  --out runs/s2_probe/BV17/pack.json \
  --writer-out runs/s2_probe/BV17/writer_view.json \
  --writer-bundle-dir runs/s2_probe/BV17/bundle
```

### 5.2 Dry-run（不调用模型）

```bash
# BV1AC
PYTHONPATH=src python -m facet_studio.writing_v3.probe \
  --case-id BV1AC \
  --units data/BV1ACbi6DEvC/substrate/units.jsonl \
  --passages runs/v3_poc/BV1AC_transcript/passages.json \
  --writer-view runs/s1_view/after/BV1AC_new/writer_view.json \
  --questions docs/s2-probe/questions_BV1AC.json \
  --out-dir runs/s2_probe/dry_run/BV1AC

# BV17（重跑 claims 后用新 writer view）
PYTHONPATH=src python -m facet_studio.writing_v3.probe \
  --case-id BV17 \
  --units data/BV17DHC6CELr/substrate/units.jsonl \
  --passages runs/v3_poc/BV17_transcript/passages.json \
  --writer-view runs/s2_probe/BV17/writer_view.json \
  --questions docs/s2-probe/questions_BV17.json \
  --out-dir runs/s2_probe/dry_run/BV17_new
```

Dry-run 只写 rendered/prompts/manifest，不写 response、不写 llm_calls。

### 5.3 正式跑（3 variants × 2 cases = 6 次调用）

```bash
# BV1AC
PYTHONPATH=src python -m facet_studio.writing_v3.probe \
  --case-id BV1AC \
  --units data/BV1ACbi6DEvC/substrate/units.jsonl \
  --passages runs/v3_poc/BV1AC_transcript/passages.json \
  --writer-view runs/s1_view/after/BV1AC_new/writer_view.json \
  --questions docs/s2-probe/questions_BV1AC.json \
  --out-dir runs/s2_probe/run/BV1AC \
  --run

# BV17
PYTHONPATH=src python -m facet_studio.writing_v3.probe \
  --case-id BV17 \
  --units data/BV17DHC6CELr/substrate/units.jsonl \
  --passages runs/v3_poc/BV17_transcript/passages.json \
  --writer-view runs/s2_probe/BV17/writer_view.json \
  --questions docs/s2-probe/questions_BV17.json \
  --out-dir runs/s2_probe/run/BV17 \
  --run
```

加 `--no-cache` 可强制真实调用；默认 cache 命中会返回已有响应并记录 `cached=true`。

### 5.4 v2 补题（已准备，未跑）

v2 保留 q1–q6 不变，新增：

- **q7/q8 frame-only**：BV1AC 问界面本地地址、`AGENT = MODEL + HARNESS`；BV17 问分数轴最低刻度、黑白色查询最高分。答案都在 lean view 的 frame caption 前 80 chars 内，避免被 caption cap 污染。
- **q9 跨段综合**：BV1AC 把 PTC 定义、实测工具列表、失败风险连起来；BV17 把 768→256→128 的存储、归一化、检索结果连起来。

题集：[questions_v2_BV1AC.json](questions_v2_BV1AC.json)、[questions_v2_BV17.json](questions_v2_BV17.json)；参考：[reference_v2_BV1AC.md](reference_v2_BV1AC.md)、[reference_v2_BV17.md](reference_v2_BV17.md)。

frame 题评分：**有帧证据且答对 = 2；没有帧证据但诚实说“证据不足” = 1；编造/答错 = 0**。不要把“输入没有帧”本身当成模型失败；frame 题单独统计，不混进 comprehension 总分。

运行方式：把 `--questions` 换成 v2 文件，`--out-dir` 用 `runs/s2_probe/run_v2/<case>`。

```bash
# BV1AC v2
PYTHONPATH=src python -m facet_studio.writing_v3.probe \
  --case-id BV1AC \
  --units data/BV1ACbi6DEvC/substrate/units.jsonl \
  --passages runs/v3_poc/BV1AC_transcript/passages.json \
  --writer-view runs/s1_view/after/BV1AC_new/writer_view.json \
  --questions docs/s2-probe/questions_v2_BV1AC.json \
  --out-dir runs/s2_probe/run_v2/BV1AC --run

# BV17 v2
PYTHONPATH=src python -m facet_studio.writing_v3.probe \
  --case-id BV17 \
  --units data/BV17DHC6CELr/substrate/units.jsonl \
  --passages runs/v3_poc/BV17_transcript/passages.json \
  --writer-view runs/s2_probe/BV17/writer_view.json \
  --questions docs/s2-probe/questions_v2_BV17.json \
  --out-dir runs/s2_probe/run_v2/BV17 --run
```

长视频 case 需要用户指定具体视频后再加，不扫描 `data/`。

### 5.5 B+frames 对照（已跑）

`--variant merged_text_frames`：合并转写 + 每段 frame captions（与 lean view 同一批 80-char caption），**不含 claims/IDs/evidence/context JSON**。用于拆出“帧值多少、claims 值多少”。

```bash
PYTHONPATH=src python -m facet_studio.writing_v3.probe \
  --case-id BV1AC \
  --passages runs/v3_poc/BV1AC_transcript/passages.json \
  --writer-view runs/s1_view/after/BV1AC_new/writer_view.json \
  --questions docs/s2-probe/questions_v2_BV1AC.json \
  --out-dir runs/s2_probe/run_b_frames/BV1AC \
  --variant merged_text_frames --run
```

结果（2026-11-01）：B+frames 与 lean_view 同 36/36；prompt tokens 只有 lean_view 的 59.6%（BV1AC）/ 54.6%（BV17）。相对 B，帧 +909/+569 tokens 买到 +4 分；claims/context/IDs +2,959/+2,038 tokens 买到 0 分。确定性 binding 检查（18/18 关键事实可回查）见 `runs/s2_probe/binding_check.md`。详见 `runs/s2_probe/run_b_frames/analysis.md`。

## 6. 评分

- 人工盲评优先：评分者先不看 variant 名，按每题 0/1/2 打分；模型 judge 只作 advisory，不作唯一 gate。
- 每题 key points 和 0/1/2 anchor 见 reference 文件。
- quote 题额外做确定性检查：回答中的引文是否是输入原文的连续子串；C 的回答如果用了 span，检查能否还原。
- 记录每题分数、总分、明显编造/漏答；记录 tokens/latency per variant。
- 评分表模板：[scoring_template.csv](scoring_template.csv)。复制一份填分，不要改模板。

## 7. 决策规则（advisory）

先看 per-case，再看 aggregate；不按单题/单篇调参。

1. **C ≥ B（机制/步骤/边界，两 case）且 C > B（quote 可回查）**：claim/evidence/view 层赚到成本；进入下一步调优（claim prompt/数量、B compact schema、Writer 接线）。
2. **C ≤ B（两 case，机制/边界）**：claim/evidence 层没有赚到成本；先简化（减少 claim/IDs、或短内容直接用 B），不进入 skill。
3. **B ≤ A**：merge 层没有赚到成本；先修 sentences/passages 边界和合并策略，再谈 claims。
4. **C 只在 quote 题赢、机制/边界不赢**：C 的价值主要是 citation，不是理解；考虑把 claim 层定位为 audit/citation 层，Writer 读更小的 B+frames。
5. **C 赢但 tokens 溢价过高**：报告 per-1k-token 收益；不要用更长上下文解释赢。
6. 任一 case 出现编造/超出输入的事实：该题记 0，并在报告中单列；不要用另一 case 掩盖。

## 8. 已知限制

- **C 没有时间码**：A/C 契约刻意去掉 times；quote 可回查由 binding 层负责。probe 不要求 C 回答时间码；A/B 的时间码优势不计入 C 的失败。
- **参考答案来自 ASR**：不是人工对照视频的金标；评分前需开发者复核。ASR 错字（如“半型工具”“3级字节”）在 reference 中已标注，不要求模型复述。
- **BV17 旧 claims**：5.1 重跑后 C 才与新合同一致；重跑前不要用旧 writer view 下结论。
- **单次调用**：每 cell 1 次，temperature 0；不测方差。需要方差时再对同一 cell 跑 3 次并记录。
- **不是 reader test/A-B**：不能当 skill 或发布验收。
- **模型 judge 不作 gate**：只作辅助对照；人工评分优先。

## 9. 不做

- 不按单题/单篇改 claim/view/prompt。
- 不为 probe 加 per-video 提示、词表、硬规则。
- 不把 probe 结果写成 skill 验收或 reader pass。
- 不自动 commit/push。
