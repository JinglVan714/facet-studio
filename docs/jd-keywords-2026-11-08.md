# 2026 JD 关键词复核（2026-11-08）

> 目的：不照抄 `architecture.md` 的落点，独立看 2026 年真实 JD/招聘分析/开源文档在要什么，再对照本项目能拿出什么、缺什么、面试怎么说。
> 口径：这是关键词调研，不是岗位承诺；没跑过的数据不写成结果。
> 关联：[jd-mapping-2026-11.md](jd-mapping-2026-11.md)（旧映射）、[architecture.md](../architecture.md)（项目落点）。

## 1. 2026 高频关键词（按出现频率归并）

### 1.1 编排与任务规划

- **多 Agent 编排**：supervisor/worker、hierarchical、peer-to-peer、handoff、router、shared state、subgraph、error edge、checkpoint。
- **任务规划/调度**：intent recognition、task decomposition、ReAct、plan-and-execute、动态子 agent 分配、停止条件、超时/重试/重规划、失败回退、向用户澄清。
- **状态与恢复**：StateGraph、thread_id、checkpoint、replay、time-travel、幂等、分布式锁。
- **工具协议**：function calling、MCP（tools/resources/prompts）、A2A、工具权限/超时/重试/错误恢复。

### 1.2 记忆与上下文

- **记忆分层**：working / episodic / semantic / procedural；session vs cross-session；用户画像、偏好、历史。
- **上下文工程**：history summarization/compression、retrieval-fragment selection、tool-result re-injection、multi-turn consistency、token 预算。
- **存储**：关系表、向量、图、文件系统；schema 化记忆槽位；append-only/版本/降权/过期。

### 1.3 评测、Trace、观测、Harness

- **评测**：离线数据集 + 自动化评测流水线；LLM-as-judge + 规则；judge 校准；trajectory scoring；回归门禁；bad case → 数据集闭环；pass@1 / pass^k；线上抽样/灰度。
- **观测**：端到端 trace、span、step-level logs/metrics、token/cost/latency/error rate；OpenTelemetry / LangSmith / Langfuse / Arize Phoenix；请求 ID、审计轨迹。
- **Harness engineering（2026 新词）**：把 harness 当成一等工程对象——工具、中间件、记忆、上下文、生命周期、验证、治理；用 trace 做结构化证据，做 trajectory 级评测、失败归因、可复现实验、可回放/可回滚。2026 的综述把它拆成 Execution / Tool / Context / Lifecycle / Observability / Verification / Governance 七层（ETCLOVG）。
- **Human-in-the-loop**：draft-and-approve、interrupt、review queue、敏感动作审批。
- **Guardrails**：输入/输出校验、prompt injection、PII、工具权限、结构化输出、审计/回滚。

### 1.4 工程与产品

- Python/Go、FastAPI/async/streaming/retry/idempotency、Docker/K8s、限流/成本上限。
- RAG：hybrid retrieval + rerank + faithfulness；内容型产品可以用确定性上下文替代，不必硬造向量库。
- 产品化：聊天式交互、artifact 预览、导出、可观测面板、成本面板。

## 2. 本项目当前证据（能拿出的）

| JD 能力 | 项目现有证据 | 状态 |
|---|---|---|
| 多 Agent 编排 | Lead Planner（只编排）+ per-form writer（一次写完）；`task_plan.json`、`decision_records.jsonl` | 有真实 run；不是 supervisor/worker 全形态 |
| 任务规划/调度 | LangGraph StateGraph：intake → plan → approval → write → typeset → review；SQLite checkpoint；plan/review interrupt；`workflow.json` stages/events/usage | P3 原型已跑通；无动态子 agent 调度/重规划 |
| 工具调用 | MCP 12 tools：ingest/list/resolve/plan/write/typeset/get_run/review + start/resume/get_workflow；ToolRegistry/Executor 回执 | 真实 LibreChat → MCP 调用已跑通 |
| 记忆 | content hash / figure catalog / skill registry / working memory；LibreChat 会话 | 缺用户画像/偏好/长期记忆的正式 schema |
| 评测 | P4 deterministic + grounding candidate audit；10 cases；contract/trajectory；`evals/product_v1/reports/` | 有数据集和报告；无 judge 校准、无 pass^k、无 CI 门禁 |
| Trace/观测 | `workflow.json` stages/events + `llm_calls.jsonl` + `tool_calls.jsonl` + `decision_records.jsonl` + Run Detail（Live SSE / Trace / Stats）+ `/runs` 看板（p50/p95/tokens/error/checks/grounding）；`get_run.trace` 摘要 | 有本地实时/事后观测；无 OTel/Langfuse |
| HITL | `review_artifact` + workflow plan/review interrupt | 真实 UI 验收已跑通 |
| Guardrails | 结构化输出、失败状态、工具权限部分；不自动发布 | 未系统化（prompt injection/PII/限流/成本上限） |
| 工程 | Python 包/CLI/pytest/MCP/FastAPI preview | 无 Docker/鉴权/生产部署 |

## 3. 判断：哪些是“真缺口”，哪些不用补

### 3.1 值得补（有真实 consumer）

1. **Trace 面板/span 聚合**：已接 `trace.html`（stage/tool/tokens/latency/error + 机器检查 + grounding 候选）和 `get_run.trace`；下一步把 span 细化到工具参数/回执，并考虑 OTel/Langfuse 导出。
2. **评测闭环**：把 P4 的 deterministic + grounding 接成固定回归命令；补 1–2 个 bad case → 数据集；不急着做 judge。JD 问的是“怎么证明改动没退化”，不是“打分多高”。
3. **记忆 schema**：先把“用户偏好/最近 runs/content hash/skill 版本”写成一份显式 schema 和读写接口；不要一上来做向量库。JD 问的是“记忆怎么分层、怎么过期、怎么冲突”，不是“用了什么数据库”。
4. **任务调度边界**：给 StateGraph 补失败分类、超时/重试、partial 状态、恢复路径；不要为了“多 agent”加 supervisor。现有 planner-executor 是合法编排模式，面试要能解释取舍。

### 3.2 不该硬补

- **不要为了 JD 加 editor/checker/supervisor**：与“一个产物一次 writer”冲突；面试时讲清楚“为什么不是 supervisor”比堆角色加分。
- **不要造 RAG/向量库全栈**：内容稿就是上下文；如果目标 JD 明确要 RAG，再做 style/reference 检索 + retrieval eval，不假装是 RAG 项目。
- **不要伪造 pass@k/线上 A/B/judge 校准**：没有就跑，没跑就不写。
- **不要堆 MCP 工具数量**：工具有真实 consumer 才加；12 个已经够讲清“工具是产品接口”。

## 4. 面试叙事（30 秒版，按 2026 关键词）

> 这是一个聊天式内容工作台：用户给一条视频和写作要求，Agent 用 MCP 工具读取内容、做 planner-executor 编排、一次写完一种形态，排版成公众号/小红书/长文，在聊天里预览、人工验收。LangGraph 管状态、checkpoint 和 interrupt；trace 记录每一次 LLM/tool 调用和决策；评测用离线数据集做 deterministic + trajectory + grounding 检查，不做“写得好不好”的模型打分。多 Agent 这里故意不是 supervisor：planner 只决定做什么，writer 一次写完，避免第二作者改稿。

## 5. 来源

- [ai-agent-interview-guide：2026 企业招聘分析](https://github.com/bcefghj/ai-agent-interview-guide/tree/main/docs/02-%E4%BC%81%E4%B8%9A%E6%8B%9B%E8%81%98%E5%88%86%E6%9E%90)（已抓取；多 agent/记忆/规划/评测/观测关键词）
- [B 站「大模型 Agent 研发工程师」招聘页](https://jobs.bilibili.com/social/positions/29499)（搜索摘要；页面 JS 渲染，未直接抓取）
- [海康机器人「算法工程师-AI-Agent」](https://talent.hikvision.com/home/socity/position?postId=15EF0D842E2B4369CD2134D70A5B7016)（搜索摘要）
- [R2 Technologies Agentic AI Engineer (Q3-2026)](https://www.ziprecruiter.com/c/R2-Technologies/Job/Agentic-AI-Engineer-(LLM-Orchestration-&-Multi-Agent-Systems)-Q3-2026/-in-Alpharetta,GA?jid=a7160d8d32e1279f)（搜索摘要；页面 403）
- [alexeygrigorev/ai-engineering-field-guide：2026 job-market YAML](https://github.com/alexeygrigorev/ai-engineering-field-guide/blob/main/job-market/data_structured/2026-02-04/8064361_LangChain_AI_Engineer.yaml)
- [LangGraph + LangSmith: Building & Monitoring Production Multi-Agent Systems (2026)](https://ideatomvp.ai/en/blog/langgraph-langsmith-agent-orchestration)
- [Diagrid: LangGraph Agent — From Demo to Production Checklist](https://www.diagrid.io/blog/langgraph-agent-production-checklist)
- [Agentic Harness Engineering: Observability-Driven Automatic Evolution of Coding-Agent Harnesses (arXiv:2604.25850)](https://arxiv.org/html/2604.25850)
- [From Failed Trajectories to Reliable LLM Agents: Diagnosing and Repairing Harness Flaws (arXiv:2606.06324)](https://browse-export.arxiv.org/abs/2606.06324?context=cs.SE)
- [From Prompts to Contracts: Harness Engineering for Auditable Enterprise LLM Agents (arXiv:2607.08028)](https://export.arxiv.org/api/query?search_query=&id_list=2607.08028)
- [OpenLIT（OTel-native agent observability/evals）](https://github.com/openlit/openlit)
