# Substrate S1-5：claim 覆盖合同与模型调用 trace/cache

> 状态：完成（2026-10-31）；S1-6 已移除本文提到的硬截断，见 [substrate-s1-no-trunc.md](substrate-s1-no-trunc.md)。本文的 pack 截断数字是 S1-5 历史。
> 范围：substrate；确定性验证 + 模型调用基础设施；未运行模型。
> 上位：[docs/substrate-s0.md](substrate-s0.md) §3.1 / §3.8 / §5；[architecture.md](../architecture.md) §16。

## 1. Claim extraction 覆盖合同

[claim_extract.py](../src/lunograph/writing_v3/claim_extract.py)：
- Prompt 要求每个 passage 恰好出现一次：要么在 `claims`，要么在 `skipped_passages` 并给 short reason（greeting/self_intro/teaser/sponsorship/logistics/ui_detail/duplicate/low_information/other）；不得静默跳过。
- 输出 schema 增加 `skipped_passages`。
- `_validate` 增加：
  - 未知 passage / 空 reason / passage 同时有 claim 和 skip / 重复 skip / 非 dict 条目 → 拒绝并记录；
  - `coverage`：passages_total、with_claims、skipped、unreported、skip_reason_counts；
  - `unreported_passages` 非空时 trace status=`partial`，但 claims 仍保留。
- `claims.json` 增加 `skipped_passages` 和 `coverage`。
- [pack_from_claims.py](../src/lunograph/writing_v3/pack_from_claims.py) 的 `selection.coverage` 读取 skipped：
  - `passages_skipped`、`skipped_passages`（带 segment/reason）、`skip_reason_counts`、`unreported_passages`；
  - 保留 `passages_dropped_by_selection`，用于区分“提取没 claim”和“pack 没选”。

当前 P0 claims 产生于该合同之前，因此：

| 指标 | BV1AC | BV17 |
|---|---:|---:|
| passages total | 32 | 16 |
| passages skipped（有 reason） | 0 | 0 |
| passages unreported | **6** | **2** |
| passages dropped by selection | 0 | 0 |

- 这说明 6/2 个 passage 是 claim extraction 没覆盖，不是 pack selection；下一次模型重跑才会产生 skipped reasons。
- 本轮没有跑模型，所以不评价模型是否能遵守 `skipped_passages` 合同；合同和 validator 已由合成测试覆盖。

## 2. 模型调用 trace

- `claim_extract` 和 `one_call_writer` 现在写：
  - `prompts/claim_extract.system.txt` / `.user.txt`
  - `prompts/v3_writer.system.txt` / `.user.txt`
  - `llm_calls.jsonl`：每条调用含 stage/key/input_hash/system_hash/user_hash/model/provider/max_tokens/temperature/status/raw_response/finish_reason/usage/latency/error/replayed。
- `claim_extract` 的 `claims.json` / trace receipt 增加 coverage；`one_call_writer` 的 `metrics.json` 增加 prompt 路径、`llm_calls` 路径、`pack_hash`、`cache_dir`、`cached`。
- 目的：能从 trace 回答“输入是什么、输出是什么、用了多少 reasoning/cached tokens、为什么贵/为什么丢”。

## 3. Content-addressed cache

[providers/llm.py](../src/lunograph/providers/llm.py) 增加 `CachedLLM`：
- cache key = provider 的精确 request identity：model + system + user + max_tokens + temperature。
- hit：不调用 inner，返回 `cached=True`/`replayed=True`，写一条 replay-style call record；latency=0。
- miss：调用 inner，成功且非空才写缓存；cache 文件损坏时回退真实调用。
- 默认目录：`runs/_cache/llm`（`runs/` 已在 `.gitignore`）；`claim_extract` / `one_call_writer` 新增 `--cache-dir`、`--no-cache`。
- 测试用 fake inner 验证：第一次 miss、第二次 hit、不同 request miss、corrupt entry fallback；没有真实模型调用。

## 4. Before / After（pack 侧）

| 指标 | BV1AC | BV17 |
|---|---:|---:|
| full pack pretty / compact | 60,027 / 46,969 | 38,901 / 30,329 |
| writer view pretty / compact | 22,662 / 17,709 | 14,191 / 10,841 |
| writer/full compact ratio | 0.377 | 0.357 |
| skipped / unreported passages | 0 / 6 | 0 / 2 |
| full pack truncation | 6 sentences + 1 frame dropped | none |
| writer view context/frames | 65 / 20 | 35 / 12 |

- `selection.coverage` 的审计字段让 full pack BV1AC 超过 60k，触发 6 句 + 1 帧裁剪；writer view 从未截断 pack 构建，仍保留 65 句 / 20 帧。
- 这再次说明：audit 字段不能和 writer context 共用预算；下一步要么把 writer view 接入 Writer，要么把 audit 字段拆到 `audit.json` sidecar。

## 5. 验证

- `tests/writing_v3`：30 passed。
- 全量：**334 passed**（S1-4 后 325 + 9）。
- 新增测试：claim coverage（5）、LLM cache（3）、pack skipped coverage（1）。
- 未跑模型；未按单篇调参；未手改 claim/reader。
- 本地产物：`runs/s1_coverage/after/`（pack + writer view），不入库。

## 6. 仍然存在的问题

- **模型重跑未做**：`skipped_passages` 合同、cache 真实命中率、prompt 遵守度都没有在真实模型上验证；需要用户确认一次模型运行。
- **full pack 审计体积**：coverage/provenance 让 BV1AC 超过 60k；下一轮应考虑 `audit.json` sidecar 或只让 Writer 读 writer view。
- **writer view 未接线**：`one_call_writer` 仍读 full pack；接线属于 writing 阶段，需要用真实 Writer 测 tokens/质量。
- **cache 只覆盖 provider 层**：claim_extract/Writer 的 stage 级缓存/回放还未接；`ReplayLLM` 仍未用于这两个 stage。

## 7. 下一步

- S1-6 已完成并有 BV1AC claim extraction 实测：见 [substrate-s1-no-trunc.md](substrate-s1-no-trunc.md)。
- 接下来二选一：接 writer view 测真实 Writer，或补 BV17 claim extraction。
- 在用户确认前，不再跑模型、不 commit。
