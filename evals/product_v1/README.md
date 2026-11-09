# Product v1 eval (P4)

> 独立开发评测，不进产品 UI；只读 run artifacts，不改文章、不改 run。
> **不评 writing 质量**：没有 LLM judge、没有人给文章打分。只测运行数据、产物合同、轨迹和 grounding / hallucination candidates。
> `pass@1/pass^k` 不伪造；`pass_at_1` / `pass_at_k` 保持 `null`，直到有 judged trials。

## 数据

- `cases.json`：capability 6 cases（2 视频 × 3 形态，**全部已有 run**）+ regression 4 cases（含 1 条 P5 新视频 E2E；旧 PDF/复制路径回归）。
- 每个 case 指向一个真实 `runs/product_v1/<run_id>`，检查：
  - run 状态 / 人工验收；
  - reader + 形态产物（WeChat 复制页、XHS 3:4 卡、PDF）；
  - 图数、缺图、正文长度、事实关键词；
  - 轨迹（workflow stages 顺序、interrupt/人工门、无 editor/checker、无 failed stage、usage 存在）；
  - tokens / latency。
- 新生成的 machine run 会标 `user review pending`；**不会自动写 approved**。

## 运行

```bash
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.product \
  --cases evals/product_v1/cases.json \
  --out evals/product_v1/reports

# CI 门禁：所有 case 都有 run、contract/trajectory 通过率 >= 1.0、error rate 0
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.product \
  --cases evals/product_v1/cases.json \
  --out evals/product_v1/reports --gate

# 如果门禁还要包含人工验收，加 --gate-require-manual（默认不要求，
# 因为人工验收是用户动作，不是自动化能替代的）
```

输出 `report-<timestamp>.json` + `.md`。报告区分：
- `contract_pass_rate`：机器合同通过率（不含人工验收）；
- `deterministic_pass_rate`：包含人工验收的 per-case pass 率；
- `manual_acceptance_rate`：人工验收率；
- `trajectory_pass_rate`：workflow 轨迹检查通过率；
- `pass_at_1` / `pass_at_k`：`null`，不伪造。

## Grounding / hallucination candidates

```bash
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.grounding \
  --cases evals/product_v1/cases.json \
  --out evals/product_v1/reports
```

- 对每个 artifact 的 Markdown 与同 run 的 `content/content.md` 对比：
  - 数字：不在内容稿的列为 `number_not_in_content` candidate；
  - 引语：长度 ≥6 的引号内容，不在内容稿列为 `quote_not_in_content` candidate；短引语按强调处理；
  - 专名：未在内容稿的拉丁专名列 `entity_not_in_content` candidate；
  - 范围升级：`所有/一定/唯一/官方/已证实/永远` 等不在内容稿的列 `scope_term_not_in_content`；
  - 跨形态：同一视频各形态的数字覆盖集合，只作信息，不判定矛盾。
- **candidate 不是幻觉率**：模型知识/解释是允许的；要算可信幻觉率，需要对 flags 做人工事实判定（可选，不是给文章打分）。

## 单 run trace 页面（前端可打开）

`typeset_article` 会在 `runs/product_v1/<run_id>/trace.html` 生成只读运行数据页，包含：

- workflow stages（状态/耗时/tokens/错误）；
- `llm_calls.jsonl`（stage/model/tokens/latency/error）；
- `tool_calls.jsonl`（workflow stage 作为 tool/step span）；
- `decision_records.jsonl`；
- P4 deterministic contract/trajectory 检查（不是写作质量分）；
- grounding candidate flags（候选，不是幻觉率）。

预览页右上/页脚有“运行数据”链接；`get_run.trace` 返回同一份摘要。它不是产品评分页，也不自动发布。

## 单 run 报告

```bash
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.run_report \
  --run-id <run_id> --out evals/product_v1/reports
```

把 `workflow.json` 轨迹、`llm_calls.jsonl`（如果该 run 有）、产物合同检查、grounding flags 合成一份 developer run report；只读，不写 run 目录。

## 当前基线（2026-11-08）

- cases：10 run / 10 total，0 missing（6 capability + 4 regression）。
- `contract_pass_rate`：1.0（10/10）。
- `trajectory_pass_rate`：1.0（30/30 checks）。
- `error_rate`：0.0。
- `manual_acceptance_rate`：0.7（7/10；3 个新 machine run 待用户验收：BV1ix long/wechat、P5 新视频 wechat）。
- `deterministic_pass_rate`：0.7（含待验收；不是 writing quality）。
- p50/p95 latency：52,421 / 92,738 ms；tokens total 215,273。
- grounding：9 artifacts / 16 candidate flags（引语 7 / 范围 6 / 专名 3；数字 0 after the CJK-adjacent number fix）；不是幻觉率。

## 后续

- 用户验收 3 个新 machine run；验收后 `manual_acceptance_rate` 会更新。
- 人工 adjudicate grounding flags（可选，只判事实真/假，不打 writing 分）；有标注才报 precision/flag rate。
- pass@k / 多 trial：需要固定 case 多次运行和 judged trials；没有就不报。
- regression gate 已接 `--gate`；后续可接 CI。
- 不把 deterministic pass 当 reader quality；人工验收仍是唯一发布门。
