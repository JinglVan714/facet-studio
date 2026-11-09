# 2026-11-09 交接快照

> 给新 session 的**干净入口**，不是上一轮聊天记录。以代码、`runs/`、`evals/product_v1/reports/`、git 为准；不要继承上一 session 对单篇产物的判断。
> 项目定位：**内容向视频 → 写作**。给一条视频 + 写作要求，按需写一种形态（深度总结 / 公众号 / 小红书），让没看视频的人获得接近亲自看过的理解与体验。
> **本轮性质：判断 + 收尾，不是继续铺功能。**

## 0. 上一轮（2026-11-08–09）做了什么

- **链路**：锁定 `mcp<2`，补 `langgraph` / `langgraph-checkpoint-sqlite` / `markdown-it-py` / `pypdf`；修 MCP 在 Python 3.11 下的 f-string 兼容；LibreChat MCP 12 tools 可加载。
- **正文与图**：SKILL 去污染（active skills 不再出现具体视频/产品/人物/单篇数字例子）；技术实现规则条件化；新增三条通用规则（中文标点统一、`can_skip` 不放核心证据、不给内容里的做法另起模型知识标签）；reader / wechat / xhs 预览模板调整（hero、目录、520px 手机预览、文字封面居中、表格列宽/滚动、代码块）。
- **可观测（新）**：`observability.py` + `observability_ui.py`；`/runs` 看板 + `/runs/<run_id>`（Live SSE / Trace / Stats）；`trace.json/html`；workflow 把每个 stage 写成 tool span，并记录 plan/approval/review decision；`get_run.trace`；LibreChat tool card 的“运行数据”按钮已实测。设计见 [docs/observability-2026-11.md](../../docs/observability-2026-11.md)。
- **明确没做**：不本地跑 Langfuse（无 Docker/ClickHouse/Postgres）；不新增架构/页面。
- **测试**：608 passed（2026-11-08 最后一次全量）。
- **工作树**：约 100 个修改/未跟踪文件，**未 commit / 未 push**（最新 commit `6f3246d`）。

## 1. 阶段一：认知（按顺序，别跳）

### 1.1 架构与产品

1. [CLAUDE.md](../../CLAUDE.md) — 入口、边界、当前状态。
2. [docs/product-v1-chat-studio.md](../../docs/product-v1-chat-studio.md) — 产品定义/交互/UI/数据分层。先确认“这是产品，不是作品集或架构 demo”。
3. [architecture.md](../../architecture.md) §0–§9 — 目标架构、组件、当前代码 vs 目标；文末附录是 v3 机会地图，**不是当前实现**。
4. [docs/writing-v5-architecture.md](../../docs/writing-v5-architecture.md) — 当前写作引擎（writing_v4）：planner/orchestrator/writer/skills/tools。
5. [docs/evidence-layer-2026-11.md](../../docs/evidence-layer-2026-11.md) — P5 证据层：下载/抽帧/ASR/VLM/content。
6. [docs/observability-2026-11.md](../../docs/observability-2026-11.md) — trace/看板设计，含“为什么不上 Langfuse”。

### 1.2 方法、纪律、标准

7. [docs/writing-rebuild-brief.md](../../docs/writing-rebuild-brief.md) §2（好 writing）+ §3（开发纪律）— 最重要的方法入口。
8. [AGENTS.md](../../AGENTS.md) — 全局护栏。
9. [docs/visual-strategy-2026-11.md](../../docs/visual-strategy-2026-11.md) — 关键帧/图注/载体策略。
10. [docs/reuse-stack-2026-11.md](../../docs/reuse-stack-2026-11.md) — 复用栈与 license。

### 1.3 进度与口径

11. [docs/jd-mapping-2026-11.md](../../docs/jd-mapping-2026-11.md) + [docs/jd-keywords-2026-11-08.md](../../docs/jd-keywords-2026-11-08.md) — JD 真实含义与关键词。
12. [evals/product_v1/README.md](../../evals/product_v1/README.md) + [reports/](../../evals/product_v1/reports/) — P4 只测 runtime/contract/grounding，不评 writing 质量。
13. [STATE.md](../../STATE.md) / [HANDOFF.md](../../HANDOFF.md) — 快照。
14. 需要 reader 测试细节时再读 `runs/_reader_test_2026-11-03/reader_pack/`；不跑 30 judge。

## 2. 阶段二：外部校准（允许联网）

- 看别人怎么把 JD 关键词落地：多 Agent 编排、记忆、规划、HITL、评测/harness、trace/可观测。参考官方文档、开源仓库、工程博客（LangGraph examples、MCP、Langfuse/LangSmith 文档、开源 agent 产品）。
- 对照 [docs/jd-keywords-2026-11-08.md](../../docs/jd-keywords-2026-11-08.md) 逐条判断：
  - 有真代码 + 真实 run；
  - 只有文档/说法；
  - 值得补（对个人项目有意义）；
  - 不值得补（生产级需求，硬做是负担）。
- **不本地部署** Langfuse/ClickHouse/Postgres；不引重依赖。
- 产出：一页书面判断（事实 / 差距 / 建议），先不写代码。

## 3. 阶段三：判断 + 收尾

用户意图：项目接近收尾。新 session 的首要产出是**判断**，然后**精准执行**。

判断要回答：

1. 产品离“可演示、可面试讲”还差什么？按价值排序。
2. 哪些是收尾必需（证据、文档一致性、可跑 demo、仓库整洁），哪些可以放弃？
3. 哪些 JD 关键词已有真实证据，哪些不该吹？现有文档有没有夸大？

收尾候选（供判断，不是指令）：

- 人工验收待验收 run，或明确“不验收，直接进入收尾”。
- 3 分钟 demo：聊天 → 视频 → 计划卡 → 写 → 预览 → 运行数据 → 导出。
- 对外叙述：README 30 秒能看懂“做什么 / 怎么做 / 证据在哪”。
- 文档与实际一致：不夸大 P4 / grounding / 可观测。
- git 提交计划：分组、message，**等用户点头再提交**。
- LICENSE / 是否公开仓库（用户未定）。

**认知完成后，先给用户一屏判断（现状 / 差距 / 3 条优先级），再执行；不要先铺代码。** 不依赖用户输入的部分可以直接做，涉及验收、提交、方向取舍再问。

## 4. 当前事实（2026-11-09 快照）

- **壳**：LibreChat（外部 clone `D:/luno_external/librechat`，不 vendored）+ MCP 12 tools + LangGraph workflow + 三种排版/导出 + 人工验收。服务当前**全部停止**；启动见 §5。
- **形态**：`long_article` / `wechat_article` / `xiaohongshu_note`；一次一种，不默认 bundle；多形态 = 多次请求。
- **最新真实 run**：`20261108T154015Z_BV1B5411A7ax_wechat_article`（中华田园猫，公众号）— 2 calls / 36,619 tokens / 105.4s / 6 stages / 3 decisions / checks 15/15 / grounding 0 / content 2,288 字 / 输出 2,363 字 / 10 图；**待人工验收**。产物：`wechat_article/reader.html`、`wechat_article/wechat.html`；运行数据页 `/runs/<run_id>`。
- **P4 最新报告** `report-20261108T135625Z.json`：10/10 cases 有 run；deterministic 7/10；contract 10/10；trajectory 30/30；error 0；manual 7/10；planner trace 6/10；p50/p95 = 52,421 / 92,738 ms；tokens 215,273；`pass@1`/`pass^k` 为 null（不伪造）。
- **P4 标记 user-review-pending 的 3 个 machine run**：`20261108T040941Z_BV1ixpd6GENc_long_article`、`20261108T041238Z_BV1ixpd6GENc_wechat_article`、`20261108T095810Z_BV1brgs6mE7a_wechat_article`。最新猫视频 run（15:40）在报告之后，未纳入 P4，也待验收。
- **可观测截图**（gitignored）：`runs/product_v1/_ui_chat_run_link.png`（聊天 tool card）、`_ui_run_detail_from_chat4.png`（Run Detail）、`_dashboard4.png`（看板）。
- **测试**：608 passed（2026-11-08 全量）。此后只改了文档和外部 LibreChat 展示层；若要引用该数字，先重跑确认。
- **工作树**：约 100 个修改/未跟踪文件；最新 commit `6f3246d`；未 push。

## 5. 常用命令

```bash
# 测试
PYTHONPATH=src PYTHONUTF8=1 python -m pytest tests -q

# P4 eval + gate
PYTHONPATH=src python -m facet_studio.evals.product --cases evals/product_v1/cases.json --out evals/product_v1/reports --gate
PYTHONPATH=src python -m facet_studio.evals.grounding --cases evals/product_v1/cases.json --out evals/product_v1/reports
PYTHONPATH=src python -m facet_studio.evals.run_report --run-id <run_id> --out evals/product_v1/reports

# 预览 / 看板（http://127.0.0.1:8765/runs）
PYTHONPATH=src python -m facet_studio.preview_server

# P5 新视频（长视频用 CLI；DashScope ASR 3.1 + VLM）
PYTHONPATH=src python -c "from facet_studio.ingest import ingest_source; print(ingest_source('https://www.bilibili.com/video/BV...', profile='fast'))"
```

LibreChat 启动见 [integrations/librechat/README.md](../../integrations/librechat/README.md)；展示层改动在 [patches/client-ui.patch](../../integrations/librechat/patches/client-ui.patch)（含新增 `FacetRunLinks.tsx`），换 clone 先 `git apply` 再 `npm run frontend`；Mongo 是内存版，重启后 user/agent 要重建。

## 6. 需要用户做的事

1. 人工验收（唯一发布门）；不验收就明确说不验收。
2. 收尾优先级拍板 / 接受“不再加功能”。
3. LICENSE、是否公开仓库。
4. 提交前点头（不自动 commit/push）。

## 7. 边界（不变）

- 一个产物一次 writer；Lead Planner 只编排，不写正文；没有 editor/checker。
- Writer 不知道来源；只拿到“这件事的完整内容”；不核验内容本身、不做百科。
- 不写死字数/结构；不按单篇调参；active skill 不出现具体视频/产品/人物。
- 用户人工验收是唯一发布门；测试绿/跑通不算通过。
- 不评 writing 质量；不做 judge/人工质量打分；不伪造 pass@k。
- 不恢复旧 supervisor/demo/词表/P1 两段式；不跑 30 judge。
- 不自动 commit/push/publish；不读 `data/cookies/`；不改 substrate v1。
- 复用优先；AGPL/BUSL 只作设计参考，除非用户同意合规。
