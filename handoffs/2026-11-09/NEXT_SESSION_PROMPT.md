# 2026-11-09 交接快照（收尾版）

> 给新 session 的**唯一入口**。以代码、`runs/`、`evals/product_v1/reports/`、git 为准；不要继承上一 session 对单篇产物的判断。
> 产品定位：**聊天式内容工作台**。用户给一条视频 + 写作要求，Agent 按需写一种形态（深度总结 / 公众号 / 小红书），在聊天里预览、修改、人工验收。
> 当前阶段：**功能收口完成，进入 GitHub / 简历发布前的收尾判断**。不再铺新功能。

## 0. 一句话现状

链路、UI、可观测、P4 harness、P5 证据层都已跑通；最新聊天 E2E 是 `20261109T131911Z_BV1brgs6mE7a_xiaohongshu_note`（793 字 / 1 张卡片 / 0 关键帧 / 6 calls / 15,862 tokens / 51.2s 墙钟（LLM 调用合计 44.6s）/ **待人工验收**）。本轮改动分组提交，未 push。项目现在缺的不是功能，而是**可公开复现的 demo、license/素材边界、README 叙事、CI、简历口径**。

## 1. 新 session 的认知顺序（按这个顺序，别跳）

### 阶段 A：架构与产品（先搞清楚“这是什么”）

1. [CLAUDE.md](../../CLAUDE.md) — 入口、边界、当前状态。
2. [docs/product-v1-chat-studio.md](../../docs/product-v1-chat-studio.md) — 产品定义/用户怎么用/UI/数据分层。确认“这是产品，不是作品集或架构 demo”。
3. [architecture.md](../../architecture.md) §0–§9 — 目标架构、组件、当前代码 vs 目标；文末附录是 v3 机会地图，不是当前实现。
4. [docs/writing-v5-architecture.md](../../docs/writing-v5-architecture.md) — 当前写作引擎（writing_v4）：planner / orchestrator / writer / skills / tools。
5. [docs/observability-2026-11.md](../../docs/observability-2026-11.md) + [docs/runtime-evidence-2026-11-09.md](../../docs/runtime-evidence-2026-11-09.md) — trace/看板/运行卡，以及本轮实际跑出的 P4、E2E、运行时数字。
6. [docs/evidence-layer-2026-11.md](../../docs/evidence-layer-2026-11.md) — P5 视频接入（下载/抽帧/ASR/VLM/content）。

### 阶段 B：JD 外部校准（允许联网，但先读旧结论再用外部资料纠偏）

7. [docs/jd-mapping-2026-11.md](../../docs/jd-mapping-2026-11.md) — 2026 JD 真实含义、产品 consumer、评测口径。
8. [docs/jd-keywords-2026-11-08.md](../../docs/jd-keywords-2026-11-08.md) — 上一轮关键词复核（多 Agent / 记忆 / 规划 / HITL / 评测 / Trace / Harness）。
9. 外部校准问题（不要只搜关键词）：
   - 2026 的 Agent 应用岗真正要的是“能上线/能评测/能排查”的哪一段？多 Agent 是必须，还是 planner-executor 也可？
   - 别人的 harness 怎么把 trace、trajectory、回归门禁、bad case 闭环串起来？哪些是产品级、哪些是面试包装？
   - 我们的“一个产物一次 writer、不做 editor/checker”在真实团队里如何解释取舍？
   - 哪些能力是本项目**有真代码+真 run**，哪些只是文档？哪些不值得为了 JD 硬补？
10. 产出：一页书面判断（事实 / 差距 / 建议），先不写代码。不要部署 Langfuse/ClickHouse/Postgres，不引重依赖。

### 阶段 C：读代码（按产品链路，不要从工具函数开始）

11. `src/facet_studio/mcp_server.py` — 13 个 MCP tools；先看 `start_workflow` / `wait_workflow` / `resume_workflow` / `typeset_article`，再看 ingest/list/resolve。
12. `src/facet_studio/workflow.py` — LangGraph StateGraph（intake → plan → approval → write → typeset → review）、SQLite checkpoint、interrupt、后台 run、`agent_view` 压缩返回。
13. `src/facet_studio/writing_v4/` — planner / writer / skills / bundle / visual_audit / svg_pass；重点看“一次 writer”和视觉审计边界。
14. `src/facet_studio/observability.py` + `observability_ui.py` + `preview_server.py` — trace 生成、`/api/card`、`/runs` 看板、Live SSE、Trace/Stats。
15. `integrations/librechat/` — 外部 clone 的 UI patch、agent instructions、yaml 示例；`client-ui.patch` 是展示层改动的唯一可复现文件。
16. `evals/product_v1/` — `cases.json`、`product.py`、`grounding.py`、`run_report.py`、最新报告。
17. `tests/` — 先跑 clean clone 测试；注意 `tests/writing_v2/` 是 gitignored 旧测试，不在公开仓库里。

### 阶段 D：判断“怎么收”

18. 读 [docs/github-resume-checklist-2026-11-09.md](../../docs/github-resume-checklist-2026-11-09.md) 和 [docs/runtime-evidence-2026-11-09.md](../../docs/runtime-evidence-2026-11-09.md)。
19. 给用户一屏判断：现状 / 差距 / 3 条优先级；然后才执行。涉及 license、公开素材、是否录 demo、是否验收，先问。

## 2. 当前事实（2026-11-09）

- **壳**：LibreChat（外部 clone `D:/luno_external/librechat`，不 vendored）+ MCP 13 tools + LangGraph + 三种排版/导出 + 人工验收。
- **形态**：`long_article` / `wechat_article` / `xiaohongshu_note`；一次一种，不默认 bundle。
- **服务**：LibreChat `http://localhost:3080`、preview `http://127.0.0.1:8765`、Mongo `127.0.0.1:27017` 当前在跑；本地测试账号 `facet@example.com / Facet12345!`。
- **最新 E2E**：`20261109T131911Z_BV1brgs6mE7a_xiaohongshu_note` — 793 字 / 1 张卡片 / 0 关键帧 / 6 calls（plan 1 + visual audit 4 + write 1）/ 15,862 tokens（含视觉审计）/ 51.2s 墙钟（intake→typeset；LLM 调用合计 44.6s）/ review=missing。聊天里只有一张运行卡，无 “执行过程” 分组，最终回复无裸 URL。
- **P4 最新报告**：`evals/product_v1/reports/report-20261109T135534Z.json` + `.md`；grounding `grounding-20261109T135557Z.json` + `.md`。10 cases / 9 unique runs，0 missing；contract 1.0（10/10 cases）；trajectory 1.0（30/30 checks）；error 0.0；manual 0.7（7/10 cases，6/9 unique；3 个新 machine run 待验收）；planner_trace 0.6；p50/p95 52,421 / 92,738 ms（plan+write）；tokens 222,498（case-level，含视觉审计）；grounding 9 artifacts / 16 candidate flags（不是幻觉率）；pass@k = null。
- **测试**：clean archive（公开代码面）**315 passed**；本地全量 **619 passed**，差额是 gitignored 的 `tests/writing_v2/` 旧测试。不要把 619 当成公开仓库数字。
- **干净 clone**：`git archive HEAD` 解压后 full tests 通过；已修 skill manifest hash 的 CRLF 可移植性 bug。
- **Git**：分支 `writing-rebuild`；本轮之前最新 commit 见 `git log`；未 push。`runs/`、`data/`、`vendor/`、`.env` 均不入库。
- **旧公众号清理**：`20261109T075145Z_BV17DHC6CELr_wechat_article` 的第一张 two-axis 关系图已从 md/HTML/SVG 文件删除，run_meta 的 `svg_assets/figures_referenced` 已同步清空并重新排版；Stats 现在 SVG=0、关键帧=0。
- **可观测快照**：`/api/runs` 本地全部 runs = 37 / 152 calls / 1,014,519 tokens / p50 54.3s / p95 165.6s / error 2.7% / checks 393/460 / grounding 83。**这是开发机全量，不是生产**。

## 3. 收尾优先级（建议，不是指令）

1. **P0 发布边界**：用户拍板 LICENSE；处理 `deliverables/writing-skill/` 的 B 站视频帧版权（58 files / 5.8MB）；确认哪些 run 截图/产物可公开。
2. **P0 可复现 demo**：加 `examples/demo/`（合成内容稿 + reader + run_meta 摘要 + 截图），让陌生人 clone 后至少能看到一份产物；P4 需要最小 fixture，否则公开仓库跑不了 10 cases。
3. **P1 README 顶部重排**：一句话 / 三个能力 / 一张架构图 / 3 分钟 demo / 测试与 P4 命令 / Known limitations；把本文件、runtime evidence、checklist 放到显眼位置。
4. **P1 CI**：`.github/workflows/ci.yml` 只跑 clean clone 的 315 tests（不依赖 API key）；P4 fixture 后再接 gate。
5. **P1 简历**：3–5 条 bullet，只引用 runtime evidence 的数字；明确“不做 writing quality judge / 不伪造 pass@k”。
6. **P2 optional**：3 分钟录屏、架构图、issue template、tag/release；不要再加 supervisor/RAG/向量库/Langfuse 生产部署。

## 4. 常用命令

```bash
# 测试（本地全量）
PYTHONPATH=src PYTHONUTF8=1 python -m pytest tests

# clean clone / 公开代码面
git archive HEAD | tar -x -C /tmp/facet_clean
cd /tmp/facet_clean && PYTHONPATH=src PYTHONUTF8=1 python -m pytest tests

# P4 harness（需要本地 runs/）
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.product \
  --cases evals/product_v1/cases.json --out evals/product_v1/reports --gate
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.grounding \
  --cases evals/product_v1/cases.json --out evals/product_v1/reports

# 单 run report
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.run_report \
  --run-id <run_id> --out evals/product_v1/reports

# 预览 / 看板
PYTHONPATH=src python -m facet_studio.preview_server
# http://127.0.0.1:8765/runs
```

LibreChat 启动见 [integrations/librechat/README.md](../../integrations/librechat/README.md)；展示层改动在 [patches/client-ui.patch](../../integrations/librechat/patches/client-ui.patch)。Mongo 是内存版，重启后 user/agent 要重建。

## 5. 需要用户拍板

1. **LICENSE**：MIT / Apache-2.0 / AGPL / 暂不公开？
2. **公开素材**：`deliverables/writing-skill/` 的 B 站帧是否删除/替换？能不能放 demo 截图？
3. **是否录 3 分钟 demo**、是否接受“只做本地可跑、不部署公网”。
4. **人工验收**：最新 E2E 仍是 `review=missing`；不验收就明确“不验收，进入收尾”，不要自动 approved；验收后重生成 `trace.json` 和单 run report。

## 6. 边界（不变）

- 一个产物一次 writer；Lead Planner 只编排，不写正文；没有 editor/checker。
- Writer 不知道来源；只拿到“这件事的完整内容”；不核验内容本身、不做百科。
- 产品按需一种形态；不默认 bundle；多形态 = 多次请求。
- 不写死字数/结构；不按单篇调参；active skill 不出现具体视频/产品/人物。
- 用户人工验收是唯一发布门；测试绿/跑通不算通过。
- 不评 writing 质量；不做 judge/人工质量打分；P4 只测运行数据/产物合同/grounding candidates。
- 不恢复旧 supervisor/demo/词表/P1 两段式；不跑 30 judge；不自动发布。
- 不在本地部署 Langfuse/ClickHouse/Postgres；不为了 JD 硬加 supervisor/RAG/向量库。
- 不自动 commit/push；不读 `data/cookies/`；不改 substrate v1。
