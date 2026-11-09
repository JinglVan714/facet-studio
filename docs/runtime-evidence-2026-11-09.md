# Runtime / harness evidence（2026-11-09）

> 这是**本地开发证据快照**，不是生产指标。runs 目录包含能力验证、回归、失败实验和重复 UI E2E；看板聚合会把这些都算进去。
> 口径：只引用实际跑出来的数；不把 deterministic 当 writing quality，不把 grounding candidate 当幻觉率，不伪造 pass@k / 线上用户。

## 1. P4 harness（固定 10 cases）

最新报告：

- `evals/product_v1/reports/report-20261109T145839Z.json` / `.md`
- `evals/product_v1/reports/grounding-20261109T145839Z.json` / `.md`

```bash
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.product \
  --cases evals/product_v1/cases.json --out evals/product_v1/reports --gate
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.grounding \
  --cases evals/product_v1/cases.json --out evals/product_v1/reports
```

| 指标 | 结果 | 含义 |
|---|---:|---|
| cases | 10 cases / 9 unique runs，0 missing | 6 capability + 4 regression；有一条重复引用同一 run |
| contract_pass_rate | 1.0（10/10） | reader/格式/图/正文/产物合同 + trajectory，**不含 manual acceptance** |
| trajectory_pass_rate | 1.0（30/30） | 30 = 4 个 workflow case ×6 项 + 6 个 legacy case ×1 项（writer_calls==1）；legacy 没有完整阶段/顺序检查 |
| error_rate | 0.0 | 固定 cases 的 status failed/partial；不是所有本地 run |
| manual_acceptance_rate | 0.9（9/10 cases，8/9 unique） | 仅 BV1ix 公众号 1 个 case 待验收；不自动写 approved |
| deterministic_pass_rate | 0.9 | 包含人工验收，不是 writing quality |
| planner_trace_rate | 0.6（6/10） | 旧 P1/P2 run 没有 planner trace，单独记录 |
| p50 / p95 latency | 52,421 / 92,738 ms | 这 10 个 case 的 plan+write 延迟，不含视觉审计/排版/排队 |
| tokens total | 222,498 | 这 10 个 case 的模型调用总量；9 个 unique run 为 201,350，重复引用多算一次 long run |
| grounding | 9 artifacts / 16 candidate flags | 引语 7 / 范围 6 / 专名 3；候选，不是幻觉率 |
| pass@1 / pass^k | null | 没有 judged trials，不伪造 |

**能证明什么**：评测/回归门禁、产物合同、workflow 轨迹、人工验收与机器检查分离。
**不能证明什么**：文章写得好、用户会喜欢、线上成功率、生产并发。`run_meta` 也没有 git commit，跨 commit 的完全复现有边界；报告里的数字只对应当前本地 run。

## 2. 最新端到端 UI run

Run：`20261109T131911Z_BV1brgs6mE7a_xiaohongshu_note`（小红书，793 字）

单 run report：

- `evals/product_v1/reports/run-report-20261109T131911Z_BV1brgs6mE7a_xiaohongshu_note-20261109T150830Z.json` / `.md`

| 阶段 | 状态 | 耗时（stage duration） |
|---|---|---:|
| intake | succeeded | 0 ms |
| plan（含 4 次视觉审计） | succeeded | 32,251 ms |
| approval | auto_approved | 0 ms |
| write | succeeded | 13,181 ms |
| typeset | succeeded | 5,723 ms |

- 模型调用：6 次（plan 1 + visual audit 4 + write 1）；`tool_calls.jsonl` 的 5 条是 workflow stage span，不是 13 个 MCP 工具逐调用
- tokens：15,862（含视觉审计）
- 延迟口径：**6 次 LLM 调用合计 44,578 ms**；**intake→typeset 墙钟 51,220 ms**（不含人工 review 等待、LibreChat 传输和用户输入）。不要写成“用户 44 秒拿到文章”。
- 交付物：reader.html + 1 张 3:4 卡片（1080×1440）+ 0 关键帧
- 视觉审计成本：4 个候选 / 0 通过，6,940 tokens / 23,234 ms，约占 51.2s 墙钟的 45.4%；严格“宁可不放图”的策略有显著延迟成本，不能当免费。
- review：approved（用户验收，不自动发布）
- 口径：聊天卡/`trace.latency_ms` 是 LLM 调用之和，可能少算 intake 到首调用前的排队；不要把它当用户感知 SLA。`get_run` 的 21,344 ms 只含 plan+write，也不含视觉审计。

注意：该 run 不在 P4 的 10 个固定 cases 内；单 run report 的 `contract.passed=true`（15/15 checks），`review=approved`。早期快照曾显示 11/15，是因为还没有 review 阶段；验收后已补 review stage 并重生成 trace。

## 3. 可观测 / 运行时看板快照

来源：`GET http://127.0.0.1:8765/api/runs`（2026-11-09 快照）

| 指标 | 本地全部 runs |
|---|---:|
| runs | 37 |
| calls_total | 152 |
| tokens_total | 1,014,519 |
| latency p50 / p95 | 54,262 / 165,590 ms |
| error_rate | 2.7% |
| checks | 397/460 |
| grounding flags | 83 |
| cost_total | null（未配置费率） |

**口径警告**：这是 `runs/product_v1` 下所有 run 的聚合，包含重复 UI E2E、失败实验和旧原型；不能当成生产 SLA，也不能拿 37 个 run 说“有 37 个用户”。2026-11-09 修正后，未验收 run 的 `manual_acceptance` 不再计为通过；本轮验收 A/B/D 后 checks 为 397/460。可引用的说法是“本地 37 个 run 的 trace 聚合，含失败样本；单 run 页面可下钻到 LLM/tool/decision spans”。

单 run 页面：`/runs/<run_id>`（概览 / Live SSE / Trace / Stats）。
Trace 现在把视觉审计逐帧标成 `视觉审计 · fig-01.jpg` + 未通过原因；决策和阶段是中文标签，原始 ID 收在“开发者详情”。

## 4. 适合写进简历/GitHub 的句子（需按岗位裁剪）

- 用 LangGraph 实现 `intake → plan → approval → write → typeset → review` 工作流，SQLite checkpoint + interrupt，支持端到端直写和人工验收两种模式。
- 通过 MCP 把写作/排版/验收能力暴露给 LibreChat；消息级运行卡轮询 card API，聊天里只保留一张卡和右侧预览，不把工具 JSON 暴露给用户。
- 建立 run-level trace：stage / LLM call / tool span / decision record / token / latency；看板支持 p50/p95、error、checks、grounding candidates。
- 建立 P4 离线 eval harness：10 cases / 9 unique runs，contract 10/10、trajectory 30/30、error 0、manual 9/10（8/9 unique）；人工验收单独统计，不伪造 pass@k。
- 视觉审计：4 个候选关键帧逐帧判定，0 通过时明确降级为文字封面/无截图，而不是硬塞图。

**不要写**：真实用户数、生产 QPS、线上 A/B、幻觉率、writing quality 分数、pass@k、Langfuse/OTel 生产部署、multi-tenant 鉴权；也不要把本项目说成 2026 “Harness engineering（ETCLOVG）”全层实现——这里只有 deterministic eval + trace，没有 Execution/Governance 等完整七层。

## 5. 复现命令

```bash
# 全量测试
PYTHONPATH=src PYTHONUTF8=1 python -m pytest tests

# P4 harness
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.product \
  --cases evals/product_v1/cases.json --out evals/product_v1/reports --gate
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.grounding \
  --cases evals/product_v1/cases.json --out evals/product_v1/reports

# 单 run report
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.run_report \
  --run-id <run_id> --out evals/product_v1/reports

# 预览/看板
PYTHONPATH=src python -m facet_studio.preview_server
# http://127.0.0.1:8765/runs
```
