# Product v1 eval (P4)

> 独立开发评测，不进产品 UI；只读 run artifacts，不改文章、不改 run。
> **不评 writing 质量**：没有 LLM judge、没有人给文章打分。只测运行数据和 grounding / hallucination candidates。
> `pass@1/pass^k` 不伪造；当前报告里的 deterministic pass 只是产品合同通过率。

## 数据

- `cases.json`：capability 6 cases（2 视频 × 3 形态；BV1ix 的 long/wechat 尚未生成，明确标 `not_run`）+ regression 3 cases。
- 每个 case 指向一个真实 `runs/product_v1/<run_id>`，检查：
  - run 状态 / 人工验收；
  - reader + 形态产物（WeChat 复制页、XHS 3:4 卡、PDF）；
  - 图数、缺图、正文长度、事实关键词；
  - 轨迹（P3 workflow stages；旧 run 的 planner trace 单独报告，不当作单 writer 失败）；
  - tokens / latency。

## 运行

```bash
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.product \
  --cases evals/product_v1/cases.json \
  --out evals/product_v1/reports
```

输出 `report-<timestamp>.json` + `.md`。报告里的 `deterministic_pass_rate` 只是产品合同通过率，不是 task success；`pass_at_1` / `pass_at_k` 为 null，直到有 judged trials。

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

当前基线（2026-11-07，6 个唯一 artifact）：17 candidate flags（数字 5 / 引语 6 / 范围 5 / 专名 1）；0.709 等计算派生数字、SPF30、俗语等属于需要人工判断的候选，不是已确认错误。

## 当前基线（deterministic）

- 7/9 cases 有 artifact；2 个 capability missing（BV1ix long/wechat）。
- deterministic pass: 7/7 run cases；manual acceptance: 7/7。
- planner trace: 4/7（旧 P1 产物缺 planner usage，新 P3 workflow 有完整 stages）。
- p50/p95 latency：50,970 / 58,757 ms；tokens total 138,609。

## 后续（P4 收口）

- 生成 BV1ix long/wechat，补满 6 capability cases。
- 人工 adjudicate grounding flags（可选，只判事实真/假，不打 writing 分）；有标注才报 precision/flag rate。
- trajectory 扩展：required tools、loop、step budget、失败恢复、审批门。
- regression gate：固定 cases + snapshot/replay；失败样本进 regression set。
- 不把 deterministic pass 当 reader quality；人工验收仍是唯一发布门。
