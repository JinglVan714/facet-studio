# 可观测设计（2026-11-09）

> 产品形态：**聊天式内容工作台**。用户通过 prompt 给一条视频 + 写作要求，按需生成**一种**形态（深度总结 / 公众号 / 小红书）；多形态是多次请求，不是一次性 bundle 工厂。
> 因此可观测的单位是**一次用户请求 / 一次 run / 一条 assistant turn**，不是一个批处理 dashboard。
> 本文回答：可观测放在哪里、给谁看、怎么看、和 2026 JD 怎么对上。

## 1. 调研：别人怎么做

| 产品/规范 | 核心结构 | 值得借的 UI/数据 |
|---|---|---|
| Langfuse | trace → observations（event / span / **generation**，可嵌套） | trace detail 的 Tree / Timeline / Graph 视图；点 observation 看 input/output/usage/metadata；scores 挂在 trace/observation 上；session 串多轮 |
| LangSmith | Threads / Traces / Runs | Messages（对话层）/ Turns（每轮）/ Details（调试层）；每条模型调用显示 token/cost/model；feedback |
| LibreChat v0.8.8+ 原生 Trace Viewer | 从 Langfuse 读 conversation trace | Steps、Sequence Scale、Preview、Roles/Agent Identity、Tool Rounds、把一次模型调用当对话看、Cost per record/step/response |
| OpenTelemetry GenAI | `invoke_agent` / `chat` / `execute_tool` spans | `gen_ai.*` 属性：provider/model、input/output tokens、tool name/args/result、conversation id、finish reasons；prompt/response 内容放 span event 并截断 |
| Langfuse/LibreChat 集成 | 每条 chat message 一条 trace | 消息反馈作为 `user-feedback` score；session = conversation；不阻塞主流程 |

共同点：

1. **trace 是树，不是一张表**：一个 run 下面有阶段/工具/模型调用；每条 observation 可展开。
2. **两段时间**：运行中看“现在到哪、花了多少”；结束后看“为什么这样、哪里失败”。
3. **两层读者**：普通用户看状态/进度/统计；开发者/面试官展开参数、I/O、错误、检查。
4. **评测挂在 trace 上**：scores/checks 是 trace 的一部分，不是另一个孤立的分数页。
5. **本地/云端可替换**：本地 JSONL 是真源，云端（Langfuse）只是视图。

## 2. 我们的约束

- **不在本地跑 Langfuse**：不自建 Docker/ClickHouse/Postgres；不为了观测把电脑跑爆。
- 本地 JSONL 是真源：`workflow.json`、`llm_calls.jsonl`、`tool_calls.jsonl`、`decision_records.jsonl`。
- 主界面是本地 Run Detail（`/runs/<run_id>`，Live/Trace/Stats）；`trace.html` 只作导出/降级，不参与写作/验收。
- 可选：未来若要接 LibreChat 原生 Trace Viewer / Langfuse Cloud，只发送 trace 元数据（默认不采集正文），并且是旁路，不影响主流程。

## 3. 设计：放在哪里、给谁看、怎么看

### 3.1 两个界面

1. **运行中：消息级运行卡**
   - 位置：当前 assistant turn 下方，每条消息只渲染一张卡；点“打开成品”开右侧抽屉，点“运行详情”进 `/runs/<run_id>`。
   - 内容：阶段轨、当前步骤/已用时间、计划、视觉审计结论、字数/卡片/关键帧、交付物入口、验收提示。
   - 目的：用户知道“它现在在干什么、做了什么决策、还要多久、有没有卡住”。
2. **结束后：Run Detail（复盘）**
   - 位置：同一个“运行数据”入口，或预览页右上/页脚的“运行数据”。
   - 结构：
     - **头部统计**：calls / tokens / latency / cost / checks / grounding 数量。
     - **配置（参数）**：来源/形态/请求/模型/temperature/max_tokens/skill 版本/内容字数/图数/中心判断；先只给值，不写解释。
     - **时间线**：stages（intake → plan → approval → write → typeset → review），每阶段可展开。
     - **模型调用**：每条 generation 可展开（stage/key/model/tokens/latency/finish/error/usage）。
     - **工具/步骤**：每条 span 可展开（名称/actor/耗时/参数/回执/错误）。
     - **决策**：问题、候选、选择、依据、由谁决定。
     - **机器检查**：P4 contract/trajectory；通过不等于写作质量。
     - **Grounding**：候选标记 + 上下文；不是幻觉率。
   - 目的：复盘“为什么这篇是这样、哪里慢/贵/失败、下次改什么”。

### 3.2 三种读者

| 读者 | 看什么 | 不看什么 |
|---|---|---|
| 产品用户 | 当前阶段、tokens/时间、草稿/已验收、失败原因 | 内部 hash、完整 prompt、评测分数 |
| 开发者 | 每条 LLM/tool/decision、参数、错误、检查、grounding | 把检查当写作质量 |
| 面试官 | trace 树、LangGraph 阶段、HITL、token/cost/latency、评测闭环 | 伪造 pass@k/线上 A/B |

### 3.3 运行中 vs 结束后

- 运行中：`workflow.json` 在每个 stage 后更新；`/runs/<run_id>/stream` 通过 SSE 推送 trace；页面增量更新，不整页刷新。只显示已完成事实，不做检查/grounding。
- 结束后：生成完整 trace，包含 checks/grounding；页面不再刷新。
- 每次请求都是独立 run；多形态是多次 run，不合并成一个“全形态” dashboard。

## 4. 当前实现（本地轻量）

- `src/facet_studio/observability.py`：collect trace、写 `trace.json`、聚合 runs dashboard。
- `src/facet_studio/observability_ui.py`：`/runs` 看板 + Run Detail（Live / Trace / Stats）。
- `preview_server.py`：`/runs`、`/runs/<run_id>`、`/runs/<run_id>/api/card`（聊天运行卡轮询）、`/runs/<run_id>/api/trace`、`/runs/<run_id>/stream`（SSE）、`/api/runs`。
- `typeset_article`：生成最终 trace，写 `artifacts.trace_html` / `trace_url`（`trace.html` 仅作导出/降级）。
- `get_run.trace`：返回 stages/calls/tools/decisions/usage/latency/cost 摘要。
- `workflow.py`：每个 stage 后写 live trace；stage 作为 tool span；plan/approval/review 写 decision record。
- 预览页：reader / 公众号 / 小红书右上或页脚“运行数据” → `../../<run_id>`。
- 真实 run 验证：`20261108T154015Z_BV1B5411A7ax_wechat_article`（2 calls / 36,619 tokens / 105.4s / 6 tool spans / 3 decisions / checks 15/15 / grounding 0 / 2,288 字 / 内容稿 10 图 / 正文引用 0，待验收）。
- 视觉审计修复后 run `20261109T072111Z_BV1B5411A7ax_wechat_article`：8 calls / 43,841 tokens / 128.3s / 6 候选 0 通过（水印/人物/UI）/ 0 关键帧 / 2,194 字 / checks 15/15 / grounding 4；Stats 运行配置里显示“视觉审计 6 候选 / 0 通过”和未通过原因。
- 聊天侧（`client/src/components/Facet/*`）：每个 assistant 消息只渲染一张运行卡，不再有 `FacetRunLinks` 或“执行过程”分组；卡轮询 `/api/card`，显示消息级阶段轨、当前步骤/已用时间、计划、视觉审计结论、字数和交付物；原始 JSON 只留在 Run Detail/Trace。`wait_workflow` 只返回压缩摘要，避免 MCP 输出被截断后模型读错图数。
- 端到端 run `20261109T131911Z_BV1brgs6mE7a_xiaohongshu_note`：后台启动 → 卡片“正在启动 → 正在进行 → 规划完成 → 等待验收 → 已验收”；793 字 / 1 张卡片 / 0 关键帧 / 6 calls / 15,862 tokens / 51.2s 墙钟（LLM 调用合计 44.6s）/ review=approved；聊天一张卡，无重复按钮、无“执行过程”分组、无裸 URL。

## 5. JD 映射

| JD 关键词 | 落点 |
|---|---|
| Observability | trace 树、span、token/cost/latency/error、运行中/结束后两种视图 |
| Harness | stage/tool/decision spans + P4 checks + grounding；trace 是 harness 的证据 |
| Evaluation | checks 挂在 trace 上；grounding 候选；不伪造分数 |
| 多 Agent 编排 | plan/write/typeset/review 阶段；plan 只编排，writer 一次写完 |
| 任务规划/调度 | stage 顺序、checkpoint/暂停点、auto/human 决策 |
| HITL | approval/review gate + decision records |
| 记忆/上下文 | 内容字数/图数、skill 版本、request、中心判断 |
| 工具/MCP | tool spans；MCP 工具调用可继续细化到 args/receipt |
| 前端 | 运行数据入口 + 预览页链接；不把 eval 页放进产品导航 |

## 6. 不做

- 不在本地自建 Langfuse / Docker / ClickHouse；不为了观测增加重依赖。
- 不把 trace 页做成写作质量评分页；checks/grounding 是开发证据。
- 不把多形态 bundle 当产品默认；一次 prompt 一种形态。
- 不伪造 pass@k、线上 A/B、真人 reader test。
- 不采集完整 prompt/正文到外部服务；除非显式开启并说明隐私/成本。

## 7. 后续

1. SSE + `/runs` 看板、消息级运行卡、右侧预览抽屉已接；真实聊天 E2E 已截图验收（一张卡、无原始 JSON、无“执行过程”分组）。
2. 如果目标 JD 需要 Langfuse/LibreChat 原生 Trace Viewer：只接 Langfuse Cloud（已配置 key），默认关闭正文采集；不自建。
3. 细化 tool span 到 MCP args/receipt；补 session/conversation 关联。
4. 评测闭环：checks/grounding → 回归报告；trace 里可跳转 run report。

## 8. 来源

- [Langfuse：Observability Data Model](https://langfuse.com/docs/observability/data-model)（trace / observation / generation / score / session）
- [Langfuse：Tracing overview](https://langfuse.com/docs/tracing)（Tree / Timeline / Graph、observation inspector）
- [Langfuse：Best practices](https://langfuse.com/docs/observability/best-practices)（root I/O、metadata、成本/token）
- [LangSmith：View traces](https://docs.langchain.com/langsmith/view-traces)（Threads / Traces / Runs；Messages / Turns / Details）
- [LibreChat v0.8.8 changelog](https://www.librechat.ai/changelog/v0.8.8)（Trace Viewer：steps、sequence scale、previews、roles、tool rounds、cost per record/step/response）
- [LibreChat：Langfuse 配置](https://www.librechat.ai/zh/docs/configuration/langfuse)（每条 chat message 一条 trace、feedback score、session）
- [OpenTelemetry GenAI agent spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/7fc967e5ea0c0b60af15d6d939790276f6e909e0/docs/gen-ai/gen-ai-agent-spans.md)（invoke_agent / chat / execute_tool、`gen_ai.*` 属性、conversation id、token usage）
- [OpenTelemetry for AI Systems (2026)](https://uptrace.dev/blog/opentelemetry-ai-systems)（每次 tool call 一个 span、prompt 内容放 event、user/session id）
- [LLM Observability: Langfuse / LangSmith / Helicone / Phoenix](https://www.premai.io/blog/llm-observability-setting-up-langfuse-langsmith-helicone-phoenix/)（工具选型/指标）
