# JD 映射（2026-11 重新调研版）

> 状态：2026-11-06 重写。上一版把“评测”映射成 per-form case + 结构报告 + 可选 A/B，**这是 smoke test，不是 2026 JD 说的 evaluation**；本版按近期 JD、工程实践和产品真实 consumer 重映射。
> 上位：[architecture.md](../architecture.md)；产品定义见 [product-v1-chat-studio.md](product-v1-chat-studio.md)；复用栈见 [reuse-stack-2026-11.md](reuse-stack-2026-11.md)。
> 2026-11-08 复核：外部 JD 关键词（多 Agent/记忆/规划/评测/Trace/Harness）见 [jd-keywords-2026-11-08.md](jd-keywords-2026-11-08.md)；本文件仍是能力映射主表。
> 原则：每个能力有真实 consumer、可打开的 run 证据和可复跑的数据；不造关键词 demo；不把“跑通”写成“质量通过”。

## 1. 调研结论（2026）

### 1.1 2026 AI Agent / LLM 应用 JD 的高频要求

- **框架**：LangGraph / LangChain 仍是主流，Claude Agent SDK、OpenAI Agents SDK、CrewAI、Google ADK 并存；LangGraph 的 StateGraph、checkpoint、streaming、human-in-the-loop 是常见追问点。
- **工具**：function calling / tool use、MCP（stdio/HTTP、tools/resources/prompts）、工具权限/超时/重试/错误恢复。
- **编排**：planner-executor、supervisor、agents-as-tools、handoff、共享 state；不是“多个角色串固定 pipeline”。
- **记忆**：working / episodic / semantic / procedural；用户画像、偏好、历史；不是只存一个 content hash。
- **评测**：离线评测集、自动化评测流水线、LLM-as-judge + 规则、judge 校准、trajectory 评测、回归门禁、线上 A/B/灰度、bad case → 数据集闭环、pass@k / pass^k。
- **观测**：端到端 trace、span、token/cost/latency/error rate、OpenTelemetry/LangSmith/Langfuse；不是只写 JSONL。
- **HITL**：draft-and-approve、interrupt、review queue；高风险动作人工确认。
- **Guardrails**：输入/输出校验、prompt injection、PII、工具权限、结构化输出。
- **工程**：FastAPI/async/streaming/retry/idempotency/限流/成本；Docker/K8s 视岗位。
- **RAG**：hybrid retrieval + rerank + faithfulness；但不是每个 LLM 应用岗位都要求，内容型产品可用确定性上下文替代。

### 1.2 上一版错在哪

| 上一版 | 问题 | 本版 |
|---|---|---|
| 评测 = per-form EvalCase + 地板/rubric + 小规模 persona 抽查 + 人工 acceptance | 没有数据集版本、指标、judge 校准、trajectory、回归门禁、pass@k/pass^k、线上闭环；只能证明“跑通” | 见 §4：数据集/指标/校准/回归/闭环 |
| 多 Agent = Lead + specialists（含 Consistency/Visual Editor） | 与当前“一个产物一次 writer、没有 editor/checker”冲突 | 产品 chat agent + Lead Planner + writer/typesetter；不恢复 editor/checker |
| 工具调用 = ToolRegistry/Executor | 当前是 orchestrator 调工具，不是模型 function calling | 目标：聊天 agent 用 native function calling 调 MCP 工具 |
| 记忆 = content hash + figure catalog | 只是语义记忆的一部分 | 目标：用户画像/偏好 + 历史 + content hash + skill 版本 |
| 观测 = JSONL | 缺 trace/span/cost/error 聚合和产品内展示 | LibreChat Trace Viewer + Token 统计 + 可选 Langfuse/OTel |
| MCP = 薄 adapter 后置 | 没说明真实 consumer | 产品 MCP 服务 + LibreChat 客户端 + 外部 agent 复用 |

## 2. 能力映射（真实含义 → 产品 consumer）

| # | JD 能力 | 2026 真实含义 | 产品落点（真实 consumer） | 当前状态 |
|---|---|---|---|---|
| 1 | 多 Agent 编排 | planner-executor / supervisor；角色、共享 state、handoff、停止条件 | 聊天 agent（LibreChat）→ Lead Planner → writer/typesetter；一个产物一次 writer | **P1 原型已跑通**：LibreChat Agent + planner + writer |
| 2 | 任务规划/调度 | DAG/StateGraph、状态、重试、预算、失败 partial | LangGraph 写作工作流：intake → plan → write → typeset → review；checkpoint/stream | **P3 原型**：StateGraph + SQLite checkpoint + stream events；LibreChat agent 默认流程未迁移 |
| 3 | Function Calling | 模型按 JSON schema 决定调工具；并行/串行、错误恢复、权限 | 聊天 agent 调 `resolve_source` / `plan_article` / `write_form` / `typeset` / `review_artifact` 等 MCP 工具 | **P1 已跑通**：LibreChat native tool calls → MCP |
| 4 | MCP | tools/resources/prompts；stdio/HTTP；auth/discovery | Python MCP server 暴露写作工具；LibreChat 连接；外部 agent 可复用 | **P1 已跑通**：`mcp_server.py` stdio + LibreChat |
| 5 | LangGraph | StateGraph、checkpoint、streaming、interrupt、memory | 写作工作流图；可暂停/恢复/人工审批；stream 执行过程 | **P3 原型**：StateGraph + SQLite checkpoint + plan/review interrupt + stream events；完整 stream UI 未接 |
| 6 | Memory | working / episodic / semantic / procedural；用户画像、偏好、历史 | 用户风格/画像、最近 runs、content hash、skill 版本、artifact 版本 | 当前只有 content hash/figure catalog/skill 库 + LibreChat 会话；用户画像未做 |
| 7 | Observability | 端到端 trace、span、token/cost/latency/error；OTel/Langfuse | LibreChat Trace Viewer + Token 统计；我们的 run 面板/span | **P1 + P3 + 本地 Run Detail**：`/runs/<run_id>`（Live SSE / Trace / Stats）+ `/runs` 看板（p50/p95/tokens/error/checks/grounding）+ `get_run.trace` + 聊天 tool card 链接；`cost_estimate` 未配费率时为 null；OTel/Langfuse 未接 |
| 8 | Evaluation | 数据集、指标、trajectory、回归门禁、pass@k/pass^k、线上闭环；writing 质量不做自动评分 | runtime/grounding eval harness + 独立报告；产品不显示分数 | **P4 原型**：deterministic harness + grounding candidate audit；不做 writing 质量 judge；trajectory 扩展/回归门禁未做 |
| 9 | HITL | draft-and-approve、interrupt、review queue | 导出/发布前验收；LangGraph `interrupt()`；LibreChat tool approval | **P1 + P3**：`review_artifact` + workflow 的 plan/review interrupt；LibreChat tool approval 未接 |
| 10 | Guardrails | 输入/输出校验、prompt injection、PII、工具权限、结构化输出 | 源内容按不可信输入；工具权限；输出 schema；不自动发布 | 当前有部分 schema/失败状态；guardrails 未系统化 |
| 11 | RAG | hybrid retrieval + rerank + faithfulness | **不是核心**：内容稿就是上下文；如目标 JD 要求，再加 style/reference 检索并做 retrieval eval | 当前 deterministic content/figure view；不是向量库 |
| 12 | 工程 | FastAPI/async/streaming/retry/idempotency/限流/成本 | MCP/FastAPI 服务；流式；重试；预算；Docker | **P1 部分**：FastMCP + FastAPI preview；无 Docker/限流 |
| 13 | Prompt/Context | context engineering、结构化输出、缓存 | skill + 内容稿 + plan brief + tool schema；缓存 | **P1 部分**：tool schema + agent instructions；缓存由 provider |
| 14 | 作品/开源 | 可运行 demo + trace/eval 证据 + README | LibreChat 产品 demo + run 证据 + eval report | **P1 demo 已跑通**；trace/eval 未做 |

## 3. 当前能拿出的真实证据

- 写作引擎：`src/facet_studio/writing_v4/`（planner/orchestrator/writer/skills/tools/run_bundle）；`skills/writing/`；`runs/writing_v5/`。
- 两套 latest bundle（本地 `runs/writing_v5/`，gitignored，公开仓库不含原始 run）：
  - BV17 social_05：公众号 2,637 字 + 小红书 944 字，complete。
  - BV1ix social_04：公众号 2,514 字 + 小红书 773 字，complete。
- run 证据：`lead_plan.json`、`task_plan.json`、`llm_calls.jsonl`、`tool_calls.jsonl`、`decision_records.jsonl`、`working_memory.json`、`artifact_board.json`、`semantic_memory.json`、`bundle_manifest.json`。
- 成本样例：BV17 3 calls / 35,905 tokens；BV1ix 3 calls / 35,453 tokens；墙钟约 1 分钟；无 repair loop。
- P1 产品原型（2026-11-06）：LibreChat + MCP + preview server；BV17 公众号 2767 字/5 图/approved；BV1ix 小红书 999 字/3 图；证据在 `runs/product_v1/`；配置见 [integrations/librechat/README.md](../integrations/librechat/README.md)。
- 测试：**580 passed**（含 MCP server / 排版 / PDF / 验收状态 / 视觉模板 / workflow / grounding / ingest 测试；旧 skill 断言已修）。
- P5 证据层（2026-11-07）：`src/facet_studio/evidence_layer/` + `src/facet_studio/ingest.py`；迁移备份 17 tests、evidence MCP selftest、BV17 content 重建 4,213 字/10 图；真实新视频下载/ASR/VLM 端到端待验收。见 [evidence-layer-2026-11.md](evidence-layer-2026-11.md)。

## 4. 评测（先预留，产品原型稳定后做）

### 4.1 数据集

- **capability set**：2 视频 × 3 形态 = 6 cases；每条包含 source、request、expected constraints、参考事实/数字、平台 rubric。
- **regression set**：从失败/bad case 收 2 条；修好后永久保留。
- **版本化**：dataset version、prompt/skill version、model version；去污染；固定 case 输入。

### 4.2 指标

| 维度 | 指标 | 方法 |
|---|---|---|
| 任务完成 | task success（rubric ≥4/5） | LLM judge + 人工校准 |
| 事实保真 | 关键数字/事实/范围一致率 | deterministic + judge |
| 平台适配 | 公众号/小红书/长文 rubric 均分 | narrow rubric judge |
| 跨形态一致 | 共享事实/数字/范围一致 | deterministic + judge（如一次请求多种形态） |
| 轨迹 | required tools、顺序、loop、step budget、失败恢复、审批门 | code evaluator |
| 可靠性 | pass@1 / pass^k（每 case 3 trials） | 多次运行 |
| 效率 | p50/p95 latency、tokens/run、cost/run | trace/usage |
| 稳定性 | error rate、partial rate、retry rate | trace |
| 人工 | manual acceptance rate | 用户验收 |

### 4.3 Judge 校准

- 每个形态一套窄 rubric；不要一个开放“写得好不好”的问题。
- 2 次 judge 聚合；用不同/更强 judge，避免 self-judge。
- 用户标注 6–12 个产物（0–5 或 pairwise），报 judge-human 一致率；低于阈值就调 rubric。
- 记录 position/verbosity bias；必要时交换 A/B 顺序。

### 4.4 回归与门禁

- capability vs regression 分开；regression 目标 ~95–100%。
- 固定 cases + snapshot/replay；prompt/skill/model/tool schema 改动跑回归。
- CI 门禁按指标，不只 task success；latency/cost 退化也要拦。
- 失败 → 复现 → 修 → 加入 regression set（failure-to-dataset loop）。

### 4.5 Baseline

- skill writer vs 通用单 prompt writer；pairwise 盲评；报胜率。
- 或者当前 skill 版本 vs 上一版；同一 request、同一内容、同一 judge。
- 不伪造真人 reader test / 线上 A/B；标注“offline model judge”。

### 4.6 报告

- 独立 eval report/dashboard，不进产品 UI。
- 内容：pass@1/pass^k、事实保真、平台适配、trajectory success、p50/p95、tokens/cost、error rate、judge-human agreement、baseline win rate、bad cases。
- 简历只用报告里的真实数字；没有跑就不填。

## 5. 简历数据模板（跑完后填）

> 示例口径，不是已得结果：

- 2 视频 × 3 形态 × 3 trials；pass@1 = __%，pass^3 = __%；
- 事实/数字保真 = __%；平台适配均分 = __/5；
- baseline 胜率 = __%；judge-human 一致率 = __%；
- p50 = __s，p95 = __s；tokens/run = __；cost/run = __；
- 人工验收 = __/6；error rate = __%；无 repair loop。

## 6. 面试叙事

**30 秒版**

> 这是一个聊天式内容工作台：用户给一条视频和写作要求，Agent 用 MCP 工具读取内容、规划、一次写完一种形态，排版成公众号/小红书/长文，在聊天里预览；LangGraph 管状态和人工验收，LibreChat 提供 chat/agents/artifacts/trace。评测不是跑几个 judge，而是离线数据集 + 事实/轨迹检查 + 校准过的 LLM judge + 回归门禁 + pass^k；产品内只展示本次 run 的 trace/成本，评测数据独立。

**展开点**

- 为什么不是 supervisor：planner 只决定“做什么”，writer 一次写完；没有 editor/checker。
- 为什么用 MCP：工具是产品接口，LibreChat 和外部 agent 都能复用；不是为一个 UI 造协议。
- 为什么用 LangGraph：状态/checkpoint/stream/interrupt 是产品需要的（进度、恢复、人工验收），不是为了框架。
- 为什么不是 RAG 项目：内容稿就是上下文；检索是确定性的；如果目标 JD 要求 RAG，再加 style/reference 检索并做 retrieval eval。
- 评测：数据集、指标、judge 校准、trajectory、回归、pass^k；不伪造真人 reader test。

## 7. 诚实缺口 / 不追求

- 当前没有 LibreChat/MCP/LangGraph/排版/eval 的产品实现；只有 writing engine。
- 没有向量数据库/RAG 全栈；不要把它说成 RAG 项目。
- 没有线上 A/B、真人 reader test、生产监控；只有离线评测/模型 judge/用户验收。
- 没有 K8s/多租户/权限系统；个人作品，不是生产平台。
- 没有微调/推理加速；应用层项目。
- MCP 生态/多框架 adapter 不追求；有真实 consumer 才加。

## 8. 来源

- [Planera Senior AI Agent Engineer JD](https://www.ziprecruiter.com/c/Planera/Job/Senior-AI-Agent-Engineer-Job/-in-Concord,NC?jid=a34be7356c71f793)
- [AgentOps 平台工程师 JD（离线评测/回归门禁/观测/成本）](https://www.zhaopin.com/jobdetail/CC152681820J40834422009.htm)
- [LangChain LLM evaluation framework](https://www.langchain.com/resources/llm-evaluation-framework)
- [Langfuse agent evaluation](https://github.com/langfuse/langfuse-docs/blob/8ffb78684e3c135320683101531aa714f8c2cd60/content/resources/engineering/ai-agent-evaluation.mdx)
- [LLM Function Calling Guide 2026](https://www.premai.io/blog/llm-function-calling-complete-implementation-guide-2026/)
- [MCP specification](https://modelcontextprotocol.io)
- [LangGraph 2026 overview](https://futureagi.com/blog/what-is-langgraph-2026/)
- [Agent memory & state guide](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/05-agent-memory-and-state.md)
- [RAG SOTA 2026 reference](https://github.com/raphaelmansuy/edgequake/blob/52d7332c28194eaf45bb4cacff7679f4e98b7bd3/specs/025-egdequake-audit/006-sota-rag-expert-lens.md)
- [AI agent guardrails 2026](https://www.akto.io/blog/ai-agent-input-validation-output-guardrail)
