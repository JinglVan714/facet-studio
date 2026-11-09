# Facet Studio 架构（产品 v1，2026-11-07）

> 状态：**目标产品架构**。2026-11-06 已确认产品形态：聊天式内容工作台（LibreChat + MCP + LangGraph + 排版/导出 + 人工验收）。
> 当前代码：substrate v1 + writing_v4 写作引擎 + **P1/P2 产品原型 + P3 workflow 原型 + P4 deterministic/grounding harness + P5 证据层**（LibreChat + MCP 12 tools + preview + review + 公众号 HTML / 小红书卡片 / PDF；LangGraph StateGraph + SQLite checkpoint + plan/review interrupt + trace；P5 新视频下载 + DashScope ASR（Qwen-Audio 3.1）+ VLM + content + workflow 已于 2026-11-08 跑通）。本文 §4–§5 区分“已有”与“目标”。
> 产品定义/UX：[docs/product-v1-chat-studio.md](docs/product-v1-chat-studio.md)；UI：[docs/ui-design-2026-11.md](docs/ui-design-2026-11.md)；写作引擎：[docs/writing-v5-architecture.md](docs/writing-v5-architecture.md)；JD：[docs/jd-mapping-2026-11.md](docs/jd-mapping-2026-11.md)；复用栈：[docs/reuse-stack-2026-11.md](docs/reuse-stack-2026-11.md)。
> 方法/纪律：[docs/writing-rebuild-brief.md](docs/writing-rebuild-brief.md) §2/§3 + [AGENTS.md](AGENTS.md)。§5 开发纪律不要改。
> 旧的 v3 机会地图保留在文末附录，**不是当前实现**。

## 0. 一屏

一条视频 → 一份连续内容稿 + figures → 用户在聊天里说“写什么形态/给谁看/多长/什么语气” → Lead Planner 规划 → 一个 writer 一次写完 → 排版成阅读 HTML / 公众号 HTML / 小红书卡片 / PDF → 聊天内预览 → 用户修改/验收。多形态是能力，不是默认 bundle。

**产品壳**：LibreChat（聊天、Agents、MCP、Artifacts、Trace Viewer、Token 统计）。
**写作服务**：Python MCP server + LangGraph 工作流 + writing_v4 引擎 + 确定性排版。
**数据分层**：产品内只展示本次 run 的 trace/成本/状态；评测数据在独立 dev dashboard；简历数据只取评测报告。

## 1. 目标架构

```text
LibreChat（chat UI / Agents / MCP client / Artifacts / Trace Viewer）
        │  MCP（stdio 或 HTTP）
        ▼
Facet Studio service（Python / FastAPI / MCP server）
  ├─ LangGraph workflow:
  │    intake → resolve_source → compile → plan → write → typeset → review
  │    （checkpoint / stream / interrupt）
  ├─ Tools:
  │    resolve_source / compile_content / plan_article / write_form /
  │    typeset / evaluate / review_artifact
  ├─ Memory:
  │    user profile + style + content hash + artifact versions + skill versions
  └─ Observability:
       spans / tokens / cost / errors → LibreChat + optional Langfuse
        │
        ▼
Artifacts: 阅读 HTML / 公众号 HTML / 小红书卡片 / PDF / Markdown
```

## 2. 组件

| 组件 | 职责 | 不做什么 |
|---|---|---|
| **LibreChat** | chat、Agents、MCP client、Artifacts、Trace Viewer、Token 统计 | 不承载写作逻辑；不直接读 run 目录 |
| **Facet Studio MCP server** | 暴露 `resolve_source` / `compile_content` / `plan_article` / `write_form` / `typeset` / `review_artifact` 等工具；ToolSpec/超时/权限/回执 | 不写 chat UI；不自动发布 |
| **LangGraph workflow** | intake → compile → plan → write → typeset → review；状态/checkpoint/stream/interrupt | 不重写 writing_v4 领域对象；不恢复 supervisor/editor |
| **writing_v4 engine** | content manuscript → planner → 一次 writer → figures/SVG → artifacts | 不知道产品壳；不核验世界 |
| **typesetter** | Markdown → 阅读 HTML / 公众号 HTML / 小红书卡片 / PDF | 不新增事实；不让模型写 HTML/LaTeX |
| **eval harness** | 数据集、指标、judge 校准、回归、pass@k/pass^k | 不进产品 UI；不伪造真人 reader test |
| **memory** | 用户画像/风格、最近 runs、content hash、artifact/skill 版本 | 不是向量库全栈；不做无关的长期记忆 |
| **observability** | trace/span/token/cost/latency/error；run 面板 | 不把评测分数塞进产品 |

## 3. 数据流

```text
用户聊天：来源 + 形态 + 读者 + 长度 + 风格 + must include/avoid
  → resolve_source（BV/本地/缓存；现阶段不重跑视频）
  → compile_content（content.md + figures + content_sha256）
  → plan_article（Lead Planner；一次调用；JSON plan）
  → write_form（一次 writer；只写当前形态）
  → typeset（确定性：HTML/PDF/公众号/卡片）
  → review（用户验收；publish_review.json）
  → artifact + run trace（llm_calls/tool_calls/decisions/usage）
```

- 一个产物一次 writer；没有 editor/checker/草稿阶段。
- 修改 = 新请求 + 新 writer 调用；不是 editor 改稿。
- 多种形态 = 多次请求；不默认一次生成 bundle。
- 失败 partial/failed 显式；单产物失败不影响其他请求。

## 4. 当前代码（已有）

| 模块 | 现状 |
|---|---|
| substrate v1 | `src/facet_studio/writing_v3/`（transcript/sentences/frames/OCR → content manuscript）；冻结 |
| 写作引擎 | `src/facet_studio/writing_v4/`：`planner.py`、`orchestrator.py`、`writer.py`、`skills.py`、`tools.py`、`run_bundle.py`、`run_form.py`、`visual_audit.py`（deepseek-flash 视觉审计候选关键帧） |
| skills | `skills/writing/video-article/`（long_article core）、`wechat-article/`（extends core）、`xiaohongshu-note/`、`bundle-planner/` |
| runtime | `src/facet_studio/runtime/`：RunStore、TaskPlan、ToolRegistry/Executor、WorkingMemory、ArtifactBoard、Decision、Trace |
| 产物 | `runs/writing_v5/bundle_BV17_social_05/`、`bundle_BV1ix_social_04/`；P1/P2 产物在 `runs/product_v1/` |
| P5 证据层 | `src/facet_studio/evidence_layer/`（从 `知识底稿核心-clean` 迁移：acquire/audio/frames/VLM/ASR/substrate）、`src/facet_studio/ingest.py`（新视频 → content.md + figures） |
| P1/P2 + P3 产品原型 | `src/facet_studio/mcp_server.py`（FastMCP 12 tools：ingest/list/resolve/plan/write/typeset/get_run/review + start/resume/get_workflow）、`src/facet_studio/workflow.py`（LangGraph StateGraph + SQLite checkpoint + interrupt + trace）、`src/facet_studio/preview_server.py`（FastAPI reader 预览）、`integrations/librechat/`、`integrations/xhs/`（Playwright 卡片）、`integrations/pdf/`（Tectonic 模板） |
| 测试 | **608 passed**（2026-11-09 实测；含 MCP server / 排版 / PDF / 验收状态 / 视觉模板 / workflow / eval / trajectory / run report / grounding / ingest / 路径配置 / visual svg / PDF SVG 测试） |
| 未接 | 3 个新 machine run 待用户验收；eval pass^k/多 trial；完整模型配置 UI；部署 |

## 5. 当前 vs 目标

| 能力 | 当前 | 目标 |
|---|---|---|
| 产品入口 | CLI `run_bundle` / `run_form` | LibreChat chat + Agents（**P1 原型已跑通**） |
| 生成方式 | 固定 bundle（可 `--forms`） | 按需一种形态；多形态 = 多次请求（**P1 已按需**） |
| 编排 | P3 workflow 原型：LangGraph StateGraph + SQLite checkpoint + plan/review interrupt；P2 逐工具流程仍可用 | 完整 stream/cost 面板 + 默认迁移到 workflow |
| 工具 | orchestrator 调 ToolRegistry | 聊天 agent 用 function calling 调 MCP 工具（**P1 已跑通**） |
| 预览/导出 | Markdown + 旧 articles-only site | 阅读 HTML（P1）；公众号复制 HTML、小红书 3:4 图集 + 导入包、PDF（**P2 已接原型**） |
| 观测 | JSONL/run manifest + `trace.html`（stages/llm_calls/tool_calls/decisions/checks/grounding） | LibreChat tool calls + `get_run` summary + 预览页“运行数据”；Trace Viewer/Token 统计待接 |
| 评测 | P4 deterministic harness + grounding candidate audit + `evals/product_v1/reports` | runtime/grounding 指标、回归/pass^k；不评 writing 质量、不伪造真人 reader test |
| 发布 | 无 | 人工验收 `publish_review.json`（**P1 已跑通**） |

## 6. 数据分层

| 层 | 给谁 | 内容 | 位置 |
|---|---|---|---|
| 用户实时可观测 | 产品用户 | run 状态、来源、模型、calls、tokens、时延、成本、工具调用、计划、错误、验收 | 聊天执行过程面板 |
| 开发评测 | 开发/面试 | 数据集、指标、回归、judge 校准、A/B、bad case | 独立 eval report/dashboard |
| 简历数据 | 面试官 | task success、pass@1/pass^k、事实保真、平台适配、baseline 胜率、时延/成本 | eval report |

## 7. 非目标

- 不做 bundle 营销；不默认一次生成所有形态。
- 不在产品导航放架构页/评测页；它们是 dev/面试材料。
- 不做 editor/checker/草稿阶段；不恢复 supervisor/词表/P1 两段式。
- 不跑 30 judge；不伪造 reader test/A-B/线上数据。
- 不做向量数据库全栈/RAG 全链路；内容稿就是上下文。
- 不做 MCP 生态/K8s/多租户/微调；有真实 consumer 才加。
- 不自动发布；不 commit/push。

## 8. 路线

| 阶段 | 内容 | 验收 |
|---|---|---|
| P0 | 文档收口（本文件 + product + UI + reuse + jd）**已完成 2026-11-06** | 后续 session 不再把 bundle 当产品 |
| P1 | LibreChat + MCP 工具服务原型：缓存内容 → 聊天 → 计划卡 → 一次 writer → 聊天内预览 **已完成原型 2026-11-06** | 一条 BV 走完；run 数据可见；不自动发布 |
| P2 | 排版/导出：阅读 HTML + PDF；公众号 HTML；小红书卡片 **已完成原型 2026-11-07** | 成品可读/可复制/可下载；移动端可用 |
| P3 | LangGraph workflow + HITL + 观测 **原型已接 2026-11-07** | 可暂停/恢复/验收；trace/token/cost 可查 |
| P4 | 评测：deterministic harness + grounding candidate audit **已接 2026-11-07**；回归门禁/pass^k 后续 | 可复跑报告；不评 writing 质量、不伪造真人 reader test |
| P5 | 视频转录接入 **证据层已迁移 2026-11-07** | 用户提供新视频后可跑通；需真实网络/API 验收 |

## 9. JD 映射

完整表见 [docs/jd-mapping-2026-11.md](docs/jd-mapping-2026-11.md)。摘要：

- 多 Agent：聊天 agent + Lead Planner + writer/typesetter；一个产物一次 writer。
- Function Calling / MCP：聊天 agent 调 MCP 工具；LibreChat 连接；外部 agent 可复用。
- LangGraph：StateGraph/checkpoint/stream/interrupt；不是只写文档。
- Memory：用户画像/风格 + 历史 + content hash + skill 版本。
- Observability：LibreChat Trace Viewer + Token 统计 + run 面板。
- Evaluation：数据集/指标/judge 校准/trajectory/回归/pass^k；不是 30 judge。
- HITL：验收门；不自动发布。
- RAG：不是核心；内容稿就是上下文；目标 JD 要求时再加。

---

> **以下为 v3 机会地图 / 早期实现假设（历史，不是当前实现）。** 保留用于产品机会、JD 能力、复用思路；具体实现以当前代码和 [docs/writing-v5-architecture.md](docs/writing-v5-architecture.md) 为准。旧文中的 Writer plan_header / Verifier / repair / polish / 30 judge 等都不是当前实现。

## 1. 产品定义

> **历史 v3 产品定义，不是当前产品。** 当前产品见 [docs/product-v1-chat-studio.md](docs/product-v1-chat-studio.md)；本附录只保留机会地图。

**一次证据编译，多文体写作。**

输入：

- 一条视频（或一个视频集合）；
- 一个写作请求（读者、目的、平台、输出形态）；
- 一个写作 skill（角色/方法/输出 schema）。

输出（同一证据库可支持多种）：

- reader-first 深度解析；
- 讲义/课程笔记/教程；
- 社媒文章（公众号、知乎、小红书、微博、thread、LinkedIn 等）；
- 企业知识/FAQ/SOP/内部文档；
- 视频创作脚本（hook、分集、分镜、旁白、B-roll）；
- 二创/发散思考/评论；
- 从视频精华生成图像的提示词；
- 以及未来新增的、由 skill 定义的其他文体。

核心差异：

1. **证据可追溯**：每个事实性句子能回到 claim、quote、时间码、帧；citation 由代码派生。
2. **证据可复用**：同一 EvidenceSnapshot 可以被多个 View/Skill 复用，不为每篇文章重新总结视频。
3. **写作连续**：默认一次 Writer 调用看完整证据包并一次写完；不靠多轮“计划→写作→审稿→修订→复查”拼接。
4. **多文体不复制管线**：文体差异放 Skill/View/输出 schema，不放 per-form pipeline/validator/gate。
5. **质量与速度并重**：默认 1 次模型调用；高风险才加 1 次独立 Verifier；其余靠确定性校验 + 真人/A-B。

**操作范围**：本架构只承诺 `generate`；`reconstruct / redesign / review` 是后续操作入口，不在当前范围。`review` 的一部分由可选 Verifier + 人工门承担，但不等于四操作都已覆盖。

非目标（本架构范围）：

- 不做全量 Scheduler/MCP/四类 Memory/RAG 全栈/LangGraph 深度；
- 不做每个文体一套 body/validator/gate；
- 不自动发布；不判断作者主张的现实真伪；
- 不把生成图/示意图当视频证据；
- 不为 JD 关键词造假。

---

## 2. 成功标准

### 2.1 业务质量

- 读者只读文章能回答 central question、复述机制/流程、说出边界。
- **未看视频的读者也能获得≈同等认知/体验**：能复述视频讲了什么、怎么讲、展示了什么、留下了什么边界。
- **标题与 H2 本身构成 TOC**：只看标题/章节标题就能理解文章框架与推进顺序。
- **视觉优先**：能用图/表/帧说明的结构、数据、流程，不写成一大段文字硬讲；无图时说明为什么。
- 事实性句子有绑定；quote 精确；时间码/帧可回查。
- 同一证据在不同文体中说法一致，不出现“这篇一个版本、那篇另一个版本”。
- 文章连续、可读、尽量精简；不是 evidence 清单，也不是 plan 的复述。

### 2.2 速度与成本

- 当前默认写作链：brief（条件）+ 1 次 Writer；结构/绑定/contract 失败 → 1 次 bounded repair；semantic verifier 可驱动至多 1 次 repair；polish；visual；final verifier 只读审计。没有无限 loop。
- 不设 per-call `max_tokens`；provider headroom 64k，单次预算 400k，client timeout 300s；以实测 usage/latency 为准。
- claim extraction 一次/视频；实际成本以模型/样本测量为准，不写死。
- 每个 stage 的 calls/tokens/latency 可查；失败/partial 不静默。

### 2.3 可复用

- 同一视频可生成 ≥2 种文体，且共享 EvidenceSnapshot/claim/evidence ID。
- 新文体不重读全量 ASR、不重做知识聚类；只新建 View + Skill。
- 证据/技能/输出版本化；旧 artifact 可 replay。

### 2.4 质量门

> **历史 v3 质量门，已过时。** 当前评测口径见 [docs/jd-mapping-2026-11.md](docs/jd-mapping-2026-11.md) §4；不要按 30 judge/5 persona 做。

- L1 确定性：structure/reader hygiene/quote hygiene/binding/contract；技术 complete 不等于 reader pass。
- L2 semantic verifier：initial 驱动至多 1 次 repair；final 只读审计交付稿；residual findings 保留为 partial/known risk，不自动二次 repair。
- L3 LLM-as-Judge：5 persona × 6 篇，匿名 A/B；两份只读标准（`runs/_reader_test_2026-11-03/reader_pack/5个persona.md`、`评价方法.md`）；团队权重 0.20/0.25/0.20/0.15/0.20；P5 红线；用户 manual acceptance。
- L4 真人 reader test：未做；未来可选；不得用模型/模拟盲读冒充。
- 所有公开发布：人工 `publish_approved`；不自动发布。

### 2.5 阶段门：substrate 先于 skill

- substrate（units/sentences/passages/claims/evidence/context/frames）是独立阶段；它先用固定 probe 证明自己比 raw ASR / merged text 更适合理解+写作，再进入 skill 阶段。
- 阶段门不是“能写出一篇文章”：P0 文章不能作为 skill 验收；skill 必须从零一个个做、一个个打磨。
- substrate 的验收维度：覆盖、上下文、忠实/可回查、不冗余、不离散、下游 probe、成本/延迟、可观测；具体合同/协议/trace schema 见 `docs/substrate-s0.md`。
- 在 substrate 阶段不做真实 reader test/A-B、不 freeze P1、不扩第二文体；这些是 skill 阶段的 gate。

---

## 3. 设计原则

1. **证据优先**：EvidenceSnapshot 是唯一事实底座；Knowledge/View/Skill/Writer 都不是新事实源。
2. **模型写作，代码编译/校验**：Writer 只负责表达；quote/时间码/citation/绑定/结构由代码做。
3. **Skill 优先，不堆规则**：用角色、读者模型、方法、示例、self-review 控制生成；不用词表/规则怪谈。
4. **连续写作优先**：Writer 一次看完整证据文本/上下文；brief 是护栏，不是 section schema；中间摘要越少，连续性越好。
5. **有界复核，不 loop**：一次 Writer 后跑确定性校验 + contract + semantic verifier；blocking 至多一次 bounded repair；final verifier 只审计交付稿，不再 repair。
6. **证据单元带上下文**：不把证据拍平成 claim 列表，也不拆成失去上下文的句子碎片。
7. **一次编译，多视图复用**：View 是引用 ID 的投影，不是模型摘要；换文体不重读 ASR。
8. **ASR 为主，帧为证**：内容以 ASR 为主；关键帧在 ASR 关键节点附近挑，不做全片均匀抽帧。
9. **多文体 = 多 Skill/View**：不为每个文体加 pipeline/body/validator/gate。
10. **小号 Harness**：Run/Stage/Attempt、Writer/Verifier 角色、plan header、tool receipts、usage/trace 足够；不追求大而全。
11. **复用开源**：优先复用/二开成熟 skill、写作引擎、视频工具；不兼容证据优先原则的整条 pipeline 不照搬。
12. **失败一等**：partial/unknown/insufficient evidence 明确记录；不包装成成功；不静默降级。
13. **度量驱动**：每一步都要回答“它是否服务于数据/质量/速度”；不服务就删。
14. **容量 advisory**：不做固定 length/focus 硬门；长度/证据量只作预算、截断、审计；质量由 reader/专家/A-B 判断。
15. **读者体验等价**：写完不是“摘要了视频”，而是“读者没看视频也能获得≈同等的认知与体验”；具体例子、演示、画面、数字和作者判断都要在文章中站得住。
16. **视觉优先**：机制/流程/架构/对比/数字优先用 diagram/chart/table/real frame；长段文字不能替代本可画出来的结构；生成图只作 editorial。
17. **标题即目录**：标题和 H2 要具体、可读、成框架；不写“背景/介绍/总结”这类空标题；读者扫标题就能知道文章怎么推进。
18. **模型知识可解释、不可伪造事实**：模型可用自身知识做解释、类比、背景组织；但不能把外部知识写成视频里的事实/数字/引语。

---

## 4. 总体架构

> 2026-11-04：§4.1 的分层概念仍可参考；§4.2–4.3 的 Brief / Verifier / polish 是旧写作链，不是当前实现。当前写作层数据流见 [docs/writing-rebuild-brief.md](docs/writing-rebuild-brief.md) §4。

### 4.1 分层

```text
接入层        CLI / API / SDK（后置）
编排层        Run / Stage / Attempt / Human Gate（小号）
证据编译层    Source → Temporal → Evidence → Knowledge → Views
写作层        Skill Registry → Brief（条件）→ Writer → contract + semantic verifier
              → bounded repair → polish → visual → final audit
校验渲染层    Bindings / Citations / Contract / Audit / Reader render
发布层        LLM-as-Judge / 人工 publish（真人 reader test 未来可选）
观测层        usage / trace / replay / decisions / eval
```

### 4.2 当前数据流

```text
WritingRequest（可选 reader_profile）
  + consume index + edited text + source map + light pack
  + WritingSkill（角色/方法/示例/self-review）
        │
        ▼
Editorial Brief（条件；full 时短编辑 brief + knowledge ledger）
        │
        ▼
Writer（1 次；Markdown）
        │
        ▼
确定性校验 + contract audit
  - structure / reader hygiene / quote hygiene / fact+quote binding
  - source line 剥离；模型知识术语 → editorial_terms
  - source line / title quote / title numbers / image captions /
    source gaps / absolute words
        │
        ├─ 失败 → 1 次 bounded repair（带具体 findings）
        │
        ▼
Semantic Verifier（initial；只读 findings）
        │
        ├─ blocking → 1 次 bounded repair（binding + contract + verifier）
        │
        ▼
Polish（style/voice/terms；preserve facts/numbers/quotes/source）
        │
        ▼
Visual planner + renderer（caption-aware；max_assets/genre）
        │
        ▼
Final validation + contract + Final Verifier（只读审计交付稿）
        │
        ▼
render reader.md + assets + audit/citations/validation/manifest
```

### 4.3 调用预算

| 场景 | 当前调用 | 说明 |
|---|---|---|
| 普通 reader-first | brief（条件）+ Writer + initial Verifier + polish + visual + final Verifier | 有 binding/contract/verifier blocking 时 +1 repair；没有无限 loop |
| 结构/绑定/contract 失败 | +1 repair | repair 只修 findings，不重新设计文章；重新 validation/contract |
| Verifier blocking | +1 repair | repair 后不再 recheck loop；final verifier 只 audit |
| 长文/多源 | 同链；视觉/分节后置 | 不先做多阶段瀑布 |
| 不设 per-call max_tokens | provider headroom 64k | 总预算 400k；timeout 300s；usage/latency 可查 |

### 4.4 最小 artifact

| Artifact | Producer | Consumers | 说明 |
|---|---|---|---|
| `evidence_snapshot` | 视频证据编译器 | Views/Writer/Verifier/audit | 不可变事实底座 |
| `temporal_outline` | 证据编译器 | Views/Writer | 时间分段/关键节点 |
| `evidence_pack` | View builder（确定性） | Writer/Verifier | 带上下文/预算/截断的证据投影 |
| `writing_skill` | Skill 库 | Brief/Writer/Verifier | 角色/方法/示例/self-review/版本 |
| `editorial_brief` | Brief planner | Writer/Verifier | 短编辑 brief + concept/mechanism/number/source/texture/next |
| `writer_output` | Writer/repair | 校验/polish/visual | Markdown article + title + self_review + usage |
| `validation/contract` | 确定性校验 | repair/render/人工 | binding / quote / 结构 / 来源行 / 标题 / caption / gaps |
| `verifier_report` | semantic verifier | repair/人工 | 只读 findings（初始） |
| `polish_report` | polish | render/人工 | 风格/voice/term 修改 + preservation 状态 |
| `verifier_final_report` | final verifier | 人工/render | 交付稿只读 findings；不触发 repair |
| `bindings/citations/audit` | 确定性校验/渲染 | Publish/人工 | 引用/时间码/帧/审核指针 |
| `llm_judge` | 5 persona 独立评审 | 人工验收 | 不是真人 reader test；分数不等于发布许可 |
| `publish_review` | 发布门（确定性） | 人工 | 记录签章/风险 |
| `run/usage/trace/decisions` | Harness | 观测/回放 | 小号但真实 |

v3 不保留旧写作链的默认中间 artifact；只有明确需要时才以 v3 的 View/Skill/Verifier 形式重建。

---

## 5. 视频证据编译器

### 5.1 四步编译

```text
Source → Temporal → Evidence → Knowledge（可选）
```

**Source**
- 视频/音频/字幕/关键帧/OCR/VLM 元数据；不可变；记录 SHA/权利/时间基准。
- 外部来源门控；`data/` 只读。

**Temporal（ASR 为主）**
- ASR units：时间码、原文、channel、speaker（如可得）。
- segments/beats：按时间/话题/步骤切成可读单元；带 label、unit_ids、first_ms/last_ms、coverage。
- 关键节点：segment 边界、claim 起止、步骤切换、数字/强调、演示/操作 mention。
- 关键帧候选：在关键节点 ±N 秒/segment 范围内取候选，不做全片均匀抽帧。

**Claim aggregation（一次性，缓存复用）**
- ASR units 先确定性合并成 sentences/passages（按标点、静默、segment），不做逐句 claim。
- 对 passages 做一次 claim extraction：每个 passage 1–3 条写作级 claim；合并碎片；跳过问候/预告/闲聊/赞助/频道 logistics；每条 claim 带 passage 内精确 quote、sentence_ids、time range。
- 目标是一段 10–20 分钟视频约 30–50 条 claim，而不是逐句 100+ 条微 claim；claim 是证据编译产物，不是新事实源。
- claim extraction 只跑一次/视频，结果缓存；不同文体复用同一 claim 集，不重新总结。
- **命名注意**：v3 pack 里的 `claims` 是“写作级聚合 claim”（1–3 句），不是 substrate 的 atomic Claim。substrate 的 atomic Claim + EvidenceClaimLink 仍是底层对象；聚合 claim 必须回指这些原子 claim/evidence，不能成为第二套事实源。未来如重命名，优先用 `claim_groups`/`writing_claims`，但兼容字段名先保留 `claims`。

**Evidence**
- 从 assertions/claims 规范化出 claim + evidence + link：
  - claim：text/kind/scope/support_status/source_assertion_id/chunk_id；
  - evidence：`raw_content` 精确 quote、locator（时间/帧/unit）、capture_method、rights、context_refs、frame_refs；
  - link：stance（supports/qualifies/contradicts/contextualizes）+ basis。
- 保留 ASR vs screen 的抽取冲突；不静默消除。
- 每个证据带上下文窗口：所在 segment/beat、前后 unit、邻域 claim、关系提示、帧候选。

**Knowledge（可选）**
- entities/claim_clusters/relations/conflicts/gaps；全部回指 claim/evidence。
- 短单视频：确定性按 segment/topic/claim-link 分组，不默认调用模型聚类。
- 长文/多源/复杂知识：一次模型 Knowledge build，缓存；仍然不是新事实源。
- Knowledge 只服务于 View 选择/关系/冲突/gap，不替代证据。

### 5.2 现有数据结构能不能复用

可以。现有 substrate 已经提供了 v3 需要的基础：

- `Unit`：ASR 单元（时间码/原文/channel）。
- `Assertion`：时间码断言（unit_ids/anchors/quote/kind/status/frame_refs/frame_offsets_ms）。
- `Claim`：规范化 claim（kind/scope/support_status/source_assertion_id/chunk_id）。
- `EvidenceSpan`：精确 quote + locator（时间/帧/unit）+ capture_method + context_refs + frame_refs + rights。
- `EvidenceClaimLink`：claim-evidence 的 stance/basis。
- `TemporalOutline`：segments + coverage。
- `FramesIndex`：关键帧 + 时间码 + VLM 文本 + strategy。
- `KnowledgeSnapshot`：entities/clusters/relations/conflicts/gaps（可选）。

v3 不需要重建 substrate；需要的是**在写作层保留上下文、按 View 复用**，不要压平成 cluster 列表或 plan 摘要。需要注意：现有 L1 assertion 可能是句级/片段级微 claim；v3 把它们当原始素材，先合并 sentences/passages，再做一次写作级 claim aggregation，而不是直接拿微 claim 写文章。

### 5.3 证据组织：不要平铺，也不要过度离散

**Contextual Evidence Unit** 是 v3 的最小组织单位：

```text
claim/evidence 本体
+ 所在 segment/beat + label
+ 前后 unit 窗口（上下文）
+ 邻域 claim + relation hints
+ 帧候选（时间码/VLM/OCR）
+ stance / counterevidence / gaps
```

它不是“一句话一个碎片”，也不是“全量 claim 平铺”。目标是让 Writer 看到**有上下文的证据**，能直接理解机制/步骤/例子，而不是从散点重建。

**View** 是按请求/文体对证据的确定性投影：

- `mechanism`：因果链、why evidence、反证、限定；
- `procedure`：步骤、前置、失败模式、check、演示帧；
- `comparison`：对象、维度、baseline、差异、结论；
- `timeline`：时间/章节/beat；
- `highlight`：可引用金句、关键数字、转折点；
- `quote`：逐字引文；
- `frame`：关键帧候选 + 视觉描述；
- `entity/process`：企业知识/流程/FAQ；
- `argument`：深度解析/评论。

View 的规则：

- 只引用 EvidenceSnapshot 的 ID；不新增事实；
- 有预算/截断，截断显式；不静默裁剪；
- 按时间/认知/论证顺序组织，不是 bag of claims；
- **先覆盖 passage/beat，再按 request focus 补**：每个 passage/beat 至少一条 claim，避免 lexical top-k 把一整个模式/步骤挤掉；
- 带 counterevidence/gaps/conflicts；
- 可缓存；同输入同 hash。
- **View 必须带 selection/truncation report**：claims considered/selected/dropped by reason；每个 selected claim 至少保留一条 quote 所在 sentence 作为上下文；截断/上下文丢失必须显式，不静默。
- **写作级聚合 claim 必须在 pack 的 provenance 块回指 `source_claim_ids`/`source_evidence_ids`**；provenance 是 audit-only，不进 writer view；View 只引用 EvidenceSnapshot 的 ID，不能成为第二套事实源。
- **Writer-facing View 只带写作所需字段**：segments/claims/evidence quotes/context/frames/gaps/conflicts；selection/provenance/budget/truncation/hashes 等审计字段不进 Writer 上下文。audit metadata 不能挤掉 writer context 预算。
- **默认不一次性注入 full pack**：Writer 读 lean view；大内容先读 index，再按需读 parts；full pack 只作 audit sidecar。契约见 `docs/substrate-view-contract.md`。
- **pack 不做硬截断**：full pack 超出 advisory 预算时保留全部 claims/context/frames，记 `over_budget`；预算由 writer view 处理，超预算按 segment 分区（parts），不丢内容；单个 segment 超预算时保留并标记 oversize。

### 5.4 证据如何复用

- 同一 `EvidenceSnapshot` → 多个 View → 多个 Skill → 多个文体；证据 ID/quote/timecode/frame 保持一致。
- 新文体只新建 View + Skill，不重读 ASR、不重做 Knowledge。
- 源变化产生新 snapshot；旧 artifact 冻结；replay 指向旧 snapshot。
- 例：同一 BV13 证据可生成：
  - procedural 步骤 view → 教程/讲义；
  - quote/highlight view → 社媒短文；
  - timeline/beat + frame view → 视频脚本；
  - frame/highlight view → 生图提示词；
  - argument view → 二创/评论。

### 5.5 能服务于什么视频

| 类型 | 适配度 | 说明 |
|---|---|---|
| 口播/课程/讲座/教程 | 高 | ASR 内容丰富；temporal/segment 好用 |
| 产品演示/机制/操作 | 高 | ASR + 关键帧/OCR；demo 帧是关键 |
| 访谈/播客/多说话人 | 中高 | 需要 speaker attribution；ASR 为主 |
| 幻灯片/屏幕/代码/UI | 高 | OCR/VLM 补视觉证据；帧在关键节点附近挑 |
| 长视频/课程合集 | 中高 | 需要 segment/beat + 分节写作；不是一次全塞 |
| 纯视觉/影视/表演/音乐 | 低 | ASR 稀疏；需要 visual-first（shot/scene/action/audio），不是本架构默认 |
| 实时直播 | 低 | 后置 |
| 无授权/隐私敏感 | 不进入 | 入口门控 |

### 5.6 和“Skill 直接看 ASR”有什么区别

| | Skill 直接看 ASR | EvidencePack |
|---|---|---|
| 内容 | 全量 ASR 原流 | 相关证据 + 上下文窗口 |
| 引用 | 模型复述，易改写 | 精确 quote/timecode/frame |
| 帧 | 没有/另找 | 关键节点附近候选帧 |
| 复用 | 每个文体重新读/总结 | 同一 ID 多 View 复用 |
| 审计 | 无 binding/citation | bindings/audit/citations |
| 上下文 | 长视频易爆 | 确定性预算 + 显式截断 |
| 一致性 | 多文体容易说法不一 | 同一证据同一事实 |
| 成本 | 预处理低、每次调用上下文大 | 预处理高、每次调用更小 |
| 适用 | 一次性短文案 | 多文体/长视频/需审计 |

**不是二选一**：

- 一次性短社媒文案，可以“直接 ASR + 轻结构”；
- 多文体复用、需要时间码/帧/审计时，用 EvidencePack。
- v3 默认 EvidencePack；如果 request 明确是 one-off、无引用需求，可用轻量 transcript 模式。

---

## 6. 写作 Skill

### 6.1 Skill 的本质

Skill 不是模板，也不是 pipeline 阶段。它是一包**程序性知识**：

- 角色/读者模型：为谁写、读者读前/读后是什么；
- 方法：怎么想、怎么组织、什么算讲清楚；
- 语气/文风：内容为主语，来源归属只在需要时出现；
- 示例：2–3 段好/坏对照，比词表更能控制文风；
- 输出：文章 + binding/audit + self_review；写作前如需 brief，brief 是编辑合同，不是 per-form validator，也不预写章节；
- 可选脚本：确定性检查/格式化（由代码执行，不进模型上下文）。
- 读者体验/标题 TOC/视觉计划合同：skill 定义文章如何形成框架、如何用图/表替代长文、读者应带走什么；不是 per-form validator。

Skill 采用渐进披露：

1. 元数据（name/description/forms）常驻，用于选择；
2. 触发后加载 SKILL.md 主体（角色/方法/示例/输出）；
3. 需要时加载 references/examples/scripts；
4. 版本化：id/version/hash；旧版本可 replay。

### 6.2 Skill 包结构

```text
skills/writing/<skill_id>/
  SKILL.md          # 角色、读者、方法、输出 schema、self-review
  examples.md       # 好/坏段落、边界写法、来源归属、结论写法
  references/       # 可选：文体规范、平台规则、领域提示
  scripts/          # 可选：确定性检查/格式化（代码执行）
  manifest.json     # id/version/forms/required_views/quality_rubric
```

### 6.3 Skill 注册表（小号）

```json
{
  "skill_id": "reader_first_explainer",
  "version": "0.1.0",
  "forms": ["deep_analysis", "article"],
  "required_views": ["mechanism", "highlight", "frame"],
  "output_schema": "writer-output-v3",
  "quality_rubric": "reader-first-v1",
  "examples": ["examples.md"],
  "scripts": []
}
```

- 选择方式：request 显式指定 skill；后续可加确定性过滤/可选模型排序。
- 不为每个文体加 pipeline；Skill 只是同一 Writer 的输入。
- Skill 不注入新事实、不绕过 EvidencePack、不改变确定性校验。

### 6.3.1 Editorial Brief（可选/条件启用）

Planner 不是固定的一次模型调用，也不是 4–7 节 section schema；它是**编辑 brief 角色**：

- 决定 angle、reader、core argument、source question、payoff、throughline、spine moves、must-use anchors、stance/speaker policy、cut、challenge、evidence status；
- 不写 H2/段落/每节 promise/takeaway/visual slot；Writer 保留章节/句子/视觉意图的自由；
- 输入是 request（含可选 reader_profile）+ 结构化 source map + skill 的 `references/planning.md`；不是“全文 + 硬编码大纲 prompt”；
- 可条件启用：`none/mini/full/human_review`，按素材拓扑/长度/风险/预算决定，不在架构里写死阈值；
- **full brief 两层**：短编辑 brief + knowledge ledger（`concept_ledger` / `mechanism_chain` / `number_ledger` / `source_block` / `texture_policy` / `next_step`）；知识 brief 是护栏，不要求 Writer 粘贴；
- brief 是合同/护栏，不是笼子；Writer 发现 brief 与素材冲突时以素材为准并记录，不静默服从。

详见 [docs/writing-operating-model.md](docs/writing-operating-model.md) 和 [docs/writing-planner-position.md](docs/writing-planner-position.md)（后者是历史定位笔记）。

### 6.4 Skill 如何解决连续性与“来源归属”

- **角色**：写作者是“为读者解释内容的人”，不是“汇报视频的人”。
- **方法**：一个主问题、一条机制/流程、一个演示、术语首次解释、结论新增综合。
- **示例**：
  - “视频作者认为它适合自动化任务” → “它适合自动化任务；脚本出错会打回重改，反而增加调用”。
  - “两个 encoder 内部如何……都还没有确切答案” → “在这组证据里，只能确定同一查询下的排序仍然可用；encoder 内部结构不是这次能回答的”。
  - 长 caption → 一句“看哪里”。
- **Self-review**：Writer 在同一次输出里标出“是否在复述前文/是否在解释来源而不是内容/是否在列 coverage”，供确定性检查和人工 review。
- **一次上下文**：Writer 看 EvidencePack + 读者合同，不需要一边满足 plan ledger、一边向 review 解释；来源归属自然减少。

### 6.5 多文体 Skill 矩阵

| 文体 | 主要 View | Skill 输出 | 质量门 |
|---|---|---|---|
| 深度解析 | mechanism/argument/highlight | reader-first 文章 | reader test/A-B |
| 讲义/notes/教程 | procedure/timeline/frame | 结构化讲义/步骤/示例 | reader test/专家 |
| 社媒 | highlight/quote/timeline | 帖子/线程/短文 | reader/A-B per platform |
| 企业知识 | entity/process/argument | 文档/FAQ/SOP | 专家 review |
| 视频脚本 | timeline/beat/frame | hook/分镜/旁白/B-roll | table read/video review |
| 二创/发散 | argument/highlight/quote | 评论/创意稿 | 人工 review |
| 生图提示词 | frame/highlight | prompt JSON/Markdown | 图像检查/权利 |

每个 Skill 自带 rubric；不为每个文体写 validator/gate。通用校验只做 binding/quote/ID/结构/reader hygiene。

---

## 7. Writer（默认一次调用）

> 2026-11-03 注：以下 §7–§10 是早期设计假设，特别是 JSON `plan_header`/span-level 输出、可选 Verifier、reader test 作为默认质量门，均已被当前实现取代。当前契约/流程/评测以 [docs/writing-operating-model.md](docs/writing-operating-model.md) + 当前代码为准；本节保留作为设计历史。

### 7.1 输入

- `WritingRequest`：central question、job to be done、读者 before/after、平台、输出形态、required/forbidden。
- `EvidencePack`：Contextual Evidence Units + gaps/conflicts + frames + budget/truncation。
- `WritingSkill`：角色/方法/示例/输出 schema/self-review。
- `OutputContract`（最小）：format、language、citation display、media policy；length 只作 advisory。

Writer 看不到：

- 其他 run 的文章/reader/review；
- 全量 ASR（只看到 EvidencePack）；
- 内部 ID 作为读者文本；
- 人工笔记（除非 request 显式提供）。

### 7.2 输出

```json
{
  "plan_header": {
    "title": "...",
    "controlling_idea": "...",
    "reader_path": ["..."],
    "sections": [{"section_id": "...", "role": "...", "goal": "..."}],
    "mechanism_or_steps": [{"step_id": "...", "why": "..."}],
    "demo_choice": {"representation": "real_frame|text_experiment|no_demo", "frame_id": "..."}
  },
  "sections": [
    {
      "section_id": "...",
      "heading": "...",
      "paragraphs": [
        {
          "spans": [
            {
              "text": "...",
              "role": "grounded|editorial",
              "claim_ids": ["..."],
              "evidence_ids": ["..."],
              "quote": "...|null",
              "scope_note": "..."
            }
          ]
        }
      ]
    }
  ],
  "media_choices": [{"frame_id": "...", "section_id": "...", "caption": "看哪里"}],
  "self_review": {
    "risks": ["..."],
    "uncertain_claims": ["..."],
    "coverage_gaps": ["..."]
  }
}
```

- `plan_header` 是审计/计划 artifact，不是单独模型调用。
- grounded span 必须有 claim/evidence；`quote` 是 audit binding（必须是 bound evidence 的精确子串），正文可以改写、不要求逐字出现；只有正文直接引用时才要求与 quote 一致。数字必须在 bound evidence；editorial 不带绑定。
- 读者文本无内部 ID/citation/时间码/审计语言；来源归属自然，不按词表。
- 结论做 synthesis，不逐节 recap；boundary 只在影响读者判断/行动时写。
- 长度 advisory：能讲清楚就尽量精简；不填 min/target。

### 7.3 生成与修复

- 第一次 Writer 调用；结构/绑定/quote 失败 → 1 次 repair（同一 Skill，带具体错误）。
- 第二次仍失败 → `writer_failed`，保留 raw，不进入 render。
- Provider outcome unknown 原样传播，不自动重放。
- 不 loop、不按单条 finding 反复修。

### 7.4 失败状态

| 状态 | 含义 |
|---|---|
| `validation_error` | 输入/证据包不可 replay/provenance 不一致 |
| `writer_failed` | 两次仍不合法（结构/绑定/quote/长度 unit） |
| `evidence_insufficient` | EvidencePack 缺少回答 central question 的必要证据；Writer 只能写 boundary |
| `provider_outcome_unknown` | 可能已调用但结果未知；不自动重放 |
| `complete` | 结构/绑定通过；不是 reader pass |

### 7.5 读者体验 / 标题 / 视觉合同

- **体验等价**：读者未看视频也能复述 central question、机制/流程、关键例子/演示/画面、作者判断与边界；不是 coverage 摘要。
- **TOC 标题**：title 承诺一个 payoff/问题/转变，不只是架构/设定；title + H2 构成可读目录；每个 H2 具体、平行、能单独说明本节讲什么；禁止空泛“背景/介绍/总结”；H2 数量按内容定，不硬凑。
- **section job/takeaway**：每节先明确“这节让读者理解/带走什么”；结尾一句 takeaway；这是 Writer 的写作检查，不是 Planner 的 7 节 schema；不逐节 recap。
- **视觉优先**：机制/流程/架构/对比/数字优先 diagram/chart/table/real frame；真实帧只在确实展示操作/结果且可读时用；没有合适图时 text/no_visual 并说明；生成图 editorial。VisualPlanner 在成稿后决定视觉，不预写 visual slot。
- **简洁**：一段一个意思；能表格/图替代的长描述删掉；不按视频时间顺序复述。
- **模型知识**：可做解释/类比/背景；不得伪造视频事实/数字/引语；reader 文本不出现 ID/时间码/审计语言。
- **质量门**：TOC/体验/视觉覆盖由 skill rubric + 人工/reader test 判断；不做 per-form 硬 validator。

---

## 8. Verifier（可选）

> 2026-11-03 更新：当前 pipeline 默认跑 initial verifier（驱动至多 1 次 repair）+ final verifier（只读审计交付稿，不 repair）。本节旧的“默认不跑/revise”是历史设计；当前以 [docs/writing-operating-model.md](docs/writing-operating-model.md) 为准。

### 8.1 触发条件

默认不跑。只在以下情况跑一次：

- 高风险内容：数字、因果、医疗、金融、法律、强结论；
- 确定性检查发现未绑定/多义/quote 可疑的 grounded span；
- Writer `self_review` 标记 uncertain/coverage gap；
- 发布前抽样/高风险文体（企业知识、讲义、严肃评论）；
- reader test/A-B 之前需要独立事实复核。

### 8.2 输入/输出

- 输入：文章 + EvidencePack（**不看 plan 摘要**）+ 检查清单（支持/过度外推/范围/来源归属/连续性）。
- 输出：可定位 findings（axis/target/severity/observation/impact/action）。
- 只读；不改文章；不生成替代段落；不判断作者主张现实真伪。

### 8.3 修复

- 有 blocking/major → 最多 1 次 revise（同一 Writer Skill，带 findings + 原文 + EvidencePack）。
- revise 后确定性校验；不再 recheck loop；仍不解决交人工。
- minor 可以记录为 known risk，不强制修。
- Verifier 的 independent perspective 是它的价值；不要让它复用 Writer 的 plan/self-review 作为前提。

### 8.4 何时不用

- 普通 reader-first/社媒短文章，确定性绑定通过，Writer self_review 无高风险；
- 真人 reader test/A-B + 人工 publish 已经是更强的质量门；
- 加 Verifier 只在它能降低事实风险/发布风险时；不为“流程完整”而跑。

---

## 9. 确定性校验与渲染

> 2026-11-03 更新：当前实现是 Markdown Reader 文章的 binding/quote/README hygiene + `contract`（source line/title quote/title numbers/image captions/source gaps/absolutes）；source line 在 binding 前剥离；模型知识拉丁术语降为 `editorial_terms`（advisory）。旧 span-level 校验是历史设计；以 [docs/writing-operating-model.md](docs/writing-operating-model.md) + 当前代码为准。

### 9.1 校验

- 每个 grounded span 有 claim/evidence；ID 在 EvidencePack；claim-evidence 闭合。
- quote 是 evidence `raw_content` 的精确连续子串；它是 audit binding，不要求逐字出现在 span text 中；只有正文直接引用时才要求与 span text 一致。
- quote 必须是对应 `sentence_ids` 拼接文本的连续子串；evidence 的 `t_start_ms`/`t_end_ms` 取这些 sentence 的并集；不满足 → `binding_failed`。
- pack 的 selection/truncation 必须可回查：dropped claim/sentence/frame 带原因；任何 claim 的上下文句丢失必须显式记录。
- grounded span 的 ASCII 数字必须出现在 bound evidence；不新增专名/说话人。
- editorial span 不带 claim/evidence/quote；只能做组织/限定/综合。
- 结构：section/heading/paragraph/span 非空；plan_header 与 sections 一致。
- reader hygiene：无内部 ID/citation/时间码/证据审计语言。
- media：real_frame 只来自固定 snapshot；caption 只写“看哪里”；生成图 editorial。
- 失败：`binding_failed` / `render_error`；不产出成功 artifact。

### 9.2 渲染

- `reader.md`：单 H1、H2、段落、图片；无 citation/时间码/内部 ID。
- `audit.json`：span→claim/evidence/quote/timecode/frame/capture/rights；gaps/conflicts；review/verifier 指针。
- `citations.json`：代码从 bindings/evidence 派生；同 evidence 合并。
- assets：固定 snapshot 的帧；sha/rights；缺失 → partial，不伪造。
- 同输入同 hash；可 replay。

### 9.3 复用现有代码

现有 binding/render/audit/citation 代码可以作为素材选择性复用；但 v3 的输入是 EvidencePack + WriterOutput，不是旧写作链的中间产物。复用时加适配层，不把旧 pipeline 类型带进 v3。

---

## 10. 质量门

> 2026-11-03 更新：当前默认质量门是 L1 确定性 + L2 semantic verifier（initial/final）+ L3 LLM-as-Judge（5 persona × 6 篇，两份只读标准，manual acceptance）；真人 reader test 未做，未来可选。本节旧的“真实读者 test 是默认门”是历史设计；不得用模型盲读冒充真人，也不要把 verifier/judge 分数当发布许可。

### 10.1 按文体

| 文体 | 主要质量门 | 说明 |
|---|---|---|
| reader-first/深度解析 | 真实读者 test + A/B | 同视频同 request，baseline 固定；读者能回答/复述/边界 |
| 社媒 | reader test/A-B per platform | 平台 voice/长度 advisory；不伪造读者 |
| 讲义/notes | reader test + 专家 review | 步骤/公式/代码/时间码准确 |
| 企业知识 | 专家/使用者 review | 事实/权限/来源；可回查 |
| 视频脚本 | table read/video review | 真实帧引用；分镜可执行 |
| 二创 | 人工 review | 证据段/发散段分离；不伪造事实 |
| 生图提示词 | 图像检查/权利 | 真帧 vs 生成图 provenance |

### 10.2 通用规则

- 技术门（binding/quote/ID/render）不等于 reader pass。
- findings=0 / Verifier complete / Writer complete 都不是发布通过。
- 真人数据必须 attestation；模型/模拟盲读只能 advisory。
- 人工 `publish_approved` 是唯一发布门；不自动发布。
- A/B 阈值按文体定义；不为所有文体套同一把尺。
- 失败/partial/unknown 不静默；成本/延迟可查。

---

## 11. 多文体产出

所有文体共用“读者体验等价 / TOC 标题 / 视觉优先 / 简洁”合同；文体差异放 Skill/View/输出 schema，不复制管线。

### 11.1 深度解析 / reader-first 文章

- View：mechanism/argument/highlight/frame。
- 输出：一个主问题、一条机制/论证、一个演示、术语首次解释、结论 synthesis。
- 质量：读者能复述机制、说出边界；A/B 严格优于 baseline。
- 约束：不写 coverage 清单；不逐节 recap；来源归属自然。

### 11.2 讲义 / 课程笔记 / 教程

- View：procedure/timeline/frame（含公式/代码抽取）。
- 输出：章节、步骤、前置、失败模式/check、示例、练习（可选）。
- 质量：读者能按步骤执行/复述；专家检查公式/代码/时间码。
- 约束：帧只作演示；时间码/来源进 audit；步骤顺序按依赖。

### 11.3 社媒文章

- View：highlight/quote/timeline。
- 输出：hook、1–3 个核心点、例子、结尾判断；公众号/知乎/小红书/微博/thread/LinkedIn 各一个 Skill。
- 质量：reader test/A-B per platform；平台长度/格式 advisory。
- 约束：不把长文硬切成 thread；不同平台不同 skill，不复制粘贴。

### 11.4 企业知识 / FAQ / SOP

- View：entity/process/argument + 多源。
- 输出：文档/FAQ/SOP/流程；引用/权限/来源。
- 质量：专家/使用者 review；事实绑定；可回查。
- 约束：多源冲突显式；不把模型知识当公司事实。

### 11.5 视频创作脚本

- View：timeline/beat/frame/highlight。
- 输出：hook、分集/分段、分镜、旁白、B-roll、字幕/字卡建议；帧引用。
- 质量：table read/video review；分镜可执行；真实帧/生成图分开。
- 约束：不伪造画面；生成图只 editorial。

### 11.6 二创 / 发散思考

- View：argument/highlight/quote + creative brief。
- 输出：评论、创意稿、改写、续写、角色/世界观发散（如适用）。
- 质量：人工 review；证据段与发散段分离；发散标注为 editorial。
- 约束：不把发散写成视频事实；不伪造引语/画面。

### 11.7 生图提示词

- View：frame/highlight。
- 输出：图像 prompt（主体/构图/风格/光线/负面提示）、可选的帧引用/风格参考。
- 质量：图像检查；权利/来源；真实帧 vs 生成图 provenance。
- 约束：生成图不作为视频证据；prompt 不伪造视频中不存在的关键内容。

### 11.8 新文体接入

- 先写 Skill + 一个案例；至少 2 个案例/结构复现才进通用层。
- 不新增 body/validator/gate；通用校验复用；文体 rubric 放 Skill/评测。
- 新文体需要新 View 时，先证明现有 View 不够用；View 也是复用单位。

---

## 12. 关键帧与视觉

### 12.1 ASR 定节点，帧在节点附近挑

1. **关键节点**：segment 边界、claim 起止、步骤切换、数字/强调、演示/操作 mention。
2. **候选窗口**：节点 ±N 秒或 segment 范围内；N 由 method/request 配置，core 不写死。
3. **候选排序**：OCR/VLM 与 claim 的相关性、幻灯片/屏幕/代码/UI、清晰度、与相邻帧去重。
4. **写作选择**：`real_frame` 只在候选帧确实展示该 operation/result/claim 时用；否则 `text_experiment`/`no_demo`。
5. **生图/二创**：从 segment/highlight 选代表帧；VLM 描述 + 风格 prompt；生成图 editorial；权利/来源记录。
6. **VLM/OCR 文本只作选帧依据**，不是事实；`capture_method` 必须记录。

### 12.2 不应该做的

- 全片均匀抽帧、按帧写文章；
- 不要把机制/流程/数据写成一大段文字而不给图/表；能画出来的结构优先画；
- 让 VLM caption 变成事实 claim；
- 用生成图/示意图冒充视频证据；
- 没有匹配帧却写“这段演示”；
- 把 caption 写成正文摘要；caption 只写“看哪里”。

### 12.3 视频类型与视觉策略

- ASR 丰富：ASR 为主，帧为证；关键节点附近挑帧。
- 幻灯片/屏幕/代码：OCR/VLM 辅助；帧在关键节点附近。
- 纯视觉/影视/表演：需要 visual-first；不是本架构默认；如要做，另立 pipeline。
- 多说话人：speaker attribution；帧在发言/演示节点附近。

---

## 13. JD 对应与小号 Harness

### 13.1 JD 映射

> **历史 v3 表，已过时。** 评测/Function Calling/MCP/LangGraph 等映射不要用；当前 JD 映射与评测口径见 [docs/jd-mapping-2026-11.md](docs/jd-mapping-2026-11.md)。

| JD 能力 | v3 落点 | 最小证据 | 优先级 |
|---|---|---|---|
| 多 Agent 协作 | Writer + optional Verifier/Editor Skill；共享 EvidencePack | 两个角色、同一证据包、run/attempt；不是聊天式多 Agent | 核心 |
| 任务规划/调度 | Writer plan_header + verifier 触发；小 DAG | plan_header artifact + stage 记录；不做全量 Scheduler | 核心 |
| 工具调用/MCP | ASR/帧/OCR/VLM/EvidencePack/生图/render | ToolSpec/Registry/receipt 最小实现；白名单/超时/失败不静默 | 核心/后续 |
| 记忆 | EvidenceSnapshot/KnowledgeSnapshot = 语义记忆；Skill 库 = 程序性记忆 | 证据不进聊天记忆；同一快照多文体复用 | 核心 |
| 决策/Trace/Budget | skill 选择、verifier 触发、模型/用量 | DecisionRecord + usage + trace + replay | 核心 |
| 评测/质量 | per-skill 回归 + reader test/A-B + binding | 固定案例/回放/回归；judge advisory | 核心 |
| Prompt/Context Engineering | Skill + EvidencePack + Request | skill/pack hash、输出 schema；核心能力 | 核心 |
| Agent 框架/RAG | View 检索；可选 LangGraph adapter | 先做视图/检索 hook；领域对象不依赖框架 | 后续 |
| 工程/成本/观测 | 1 Writer 默认；usage/latency | 成本可见；失败/partial 一等 | 核心 |
| 作品/开源 | 多文体 + reader artifact + A/B | ≥2 文体、真实 reader artifact、trace replay | 后续 |

### 13.2 小号 Harness

- `Run/Stage/Attempt`：writer、optional verifier、render；status/usage。
- `DecisionRecord`：skill 选择、verifier 触发、revision 原因。
- `Tool receipt`：ASR/帧/OCR/VLM/生图/render；真实回执。
- `Trace/Replay`：skill hash、evidence pack hash、prompt/model/usage。
- `Eval`：per-skill 固定案例 + reader/A-B + binding regression。

### 13.3 不追求的

- 全量 Scheduler/并行/取消/checkpoint；
- MCP 生态/工具市场；
- 四类 Memory 深度；
- LangGraph 全栈/RAG 全链路；
- 多租户/权限/平台适配；
- 大而全 JD 覆盖。

原则：JD 能力“有就行”，每个能力有一个小号 artifact + consumer + test；不为关键词造假。

---

## 14. 复用 / 二开开源

### 14.1 原则

1. 优先复用**格式/组件/skill**，不照搬不兼容的整条 pipeline。
2. License/安全/维护状态先审；pin 版本；adapter 边界。
3. Third-party skill 要审计 prompt injection/工具权限。
4. 与 EvidencePack/证据优先冲突的中间摘要链，不搬。
5. 复用代码要有测试/可回退；不把框架类型带进领域对象。
6. 2026-10-31 的本地 17 个 skill + web writing 项目扫描见 [docs/reference-writing-scan.md](docs/reference-writing-scan.md)；只作参考，不是 v3 基线。

### 14.2 候选

| 方向 | 候选 | 复用方式 | 阶段 |
|---|---|---|---|
| Skill 格式 | Anthropic Agent Skills / `anthropics/skills` | SKILL.md + progressive disclosure + scripts；写自己的写作 skill | 初期 |
| 长文规划 | WriteHERE | 递归/图规划思想；长文再借，不做短文章默认 | 后期 |
| 研究/长文 | STORM | research→outline→write→polish；多源/长文再借 | 后期 |
| 长文/多 Agent | InkOS / OmniWriter | 记忆/角色/长文编排；后置 | 后期 |
| 视频 | ffmpeg / faster-whisper / PaddleOCR / Qwen2.5-VL / InternVL | 现有 substrate 工具链；按需替换 | 初期 |
| 渲染 | 现有 Markdown/asset render | 选择性复用；v3 适配 WriterOutput | 初期 |
| 评测 | reader test/A-B 模板；开源 eval harness 可选 | 固定案例/回放/回归 | 后续 |

### 14.3 集成边界

- Skill：只通过 `SkillManifest` + `SKILL.md` 进入 Writer；不直接改 core。
- 视频工具：只通过证据编译器 adapter；输出 Unit/Assertion/Evidence/Frames。
- 长文引擎：只通过 View/Writer adapter；不替换 EvidencePack/校验/渲染。
- Render/Eval：只通过输入/输出 schema；不引入旧 pipeline 类型。

---

## 15. 最小数据契约

v3 只保留必要 schema；详细字段在实现时定，不先写 18 个合同。

### 15.1 EvidencePack

```json
{
  "schema_version": "evidence-pack-v3",
  "pack_id": "ep3_...",
  "request_id": "req_...",
  "skill_id": "reader_first_explainer",
  "evidence_snapshot_id": "...",
  "temporal_outline_id": "...",
  "view_types": ["mechanism", "highlight", "frame"],
  "units": [
    {
      "unit_id": "u_...",
      "segment_id": "seg_...",
      "t_start_ms": 0,
      "t_end_ms": 0,
      "text": "...",
      "speaker": "...",
      "neighbor_claim_ids": ["..."],
      "frame_candidates": ["f_..."]
    }
  ],
  "claims": [
    {
      "claim_id": "c_...",
      "text": "...",
      "kind": "...",
      "scope": {}
    }
  ],
  "evidence": [
    {
      "evidence_id": "ev_...",
      "claim_ids": ["..."],
      "quote": "...",
      "t_start_ms": 0,
      "t_end_ms": 0,
      "sentence_ids": ["..."],
      "frame_ids": ["..."],
      "capture_method": "asr|ocr|vlm|manual",
      "stance": "supports|qualifies|contradicts|contextualizes",
      "rights_scope": "..."
    }
  ],
  "provenance": {
    "summary": {
      "claims_total": 0,
      "claims_with_source": 0,
      "claims_without_source": 0,
      "source_claim_count": 0,
      "source_evidence_count": 0,
      "stance_counts": {},
      "support_status_counts": {},
      "rights_scope_counts": {}
    },
    "claims": {
      "c_...": {
        "source_claim_ids": ["..."],
        "source_evidence_ids": ["..."]
      }
    }
  },
  "gaps": [],
  "conflicts": [],
  "budget": {"max_chars": 0, "max_frames": 0},
  "truncated": false,
  "over_budget": false,
  "budget_excess_chars": 0,
  "pack_hash": "..."
}
```

- `provenance` 与 `selection/truncation` 是 audit-only；Writer-facing View 只带写作字段，不带这些块。
- `budget.max_chars`/`max_frames` 是 advisory；full pack 不做硬截断；`over_budget`/`budget_excess_chars` 记录超预算；writer view 超预算按 segment 分区（parts）。
- View 产物：`writer_view`（lean single）、`writer_index` + `writer_parts` + `manifest`（按需）、full pack（audit）；详细 schema/不变量见 `docs/substrate-view-contract.md`。

### 15.2 SkillManifest

```json
{
  "schema_version": "writing-skill-v3",
  "skill_id": "reader_first_explainer",
  "version": "0.1.0",
  "forms": ["deep_analysis", "article"],
  "required_views": ["mechanism", "highlight", "frame"],
  "output_schema": "writer-output-v3",
  "quality_rubric": "reader-first-v1",
  "examples": ["examples.md"],
  "scripts": []
}
```

### 15.3 WriterOutput

> 2026-11-03 更新：当前 Writer 输出是 Markdown article（单 H1 + H2 + 段落 + 可选图片）+ title/self_review/usage，不是下面的 plan_header/span JSON；校验在 article 文本上做。以 [docs/writing-operating-model.md](docs/writing-operating-model.md) 为准。

- plan_header：title/controlling_idea/reader_path/sections/mechanism_or_steps/demo_choice；
- sections/spans：text/role/claim_ids/evidence_ids/quote/scope_note；
- media_choices：frame_id/section_id/caption；
- self_review：risks/uncertain_claims/coverage_gaps；
- status：complete|partial|failed；
- prompt/model/usage/skill hash/evidence pack hash。

### 15.4 Binding / Audit / Citations

> 2026-11-03 更新：当前是 article 的 paragraph/fact/quote binding + contract audit + citations，不是 span-level binding；source line/heading 在 binding 前剥离；模型知识拉丁术语进入 `editorial_terms`。以 [docs/writing-operating-model.md](docs/writing-operating-model.md) 为准。

- 每个 grounded span 一条 binding：span_ref/claim/evidence/quote/timecode/frame/capture/rights。
- audit：sections/spans/binding/gaps/conflicts/verifier/rights。
- provenance：写作 claim → substrate atomic claim/evidence；audit-only，不进 writer view。
- writer view：lean projection（segments/claims/evidence/context/frames/gaps/conflicts）；audit 字段不进 Writer 上下文。
- citations：evidence 去重、span_refs、quote/timecode/frame。
- 同输入同 hash；可 replay。

### 15.5 VerifierReport / PublishReview

> 2026-11-03 更新：当前有 `verifier-report-v1` 的 initial + final 两份；final 只读审计，不触发第二次 repair；发布仍由人工 `publish_approved`，LLM judge 不是发布许可。以 [docs/writing-operating-model.md](docs/writing-operating-model.md) 为准。

- VerifierReport：findings（axis/target/severity/observation/impact/action）+ provenance。
- PublishReview：reader/audit/citations hash、reader test/A-B/human review、checklist、known risks、status。
- 不把旧架构的 gate/risk 清单直接搬来；v3 按文体定义最小 gate。

---

## 16. 失败 / 观测

### 16.1 失败状态

| 状态 | 含义 |
|---|---|
| `validation_error` | 输入/provenance 不一致；不可 replay |
| `evidence_insufficient` | EvidencePack 缺少回答 central question 的必要证据 |
| `writer_failed` | 两次仍不合法（结构/绑定/quote） |
| `binding_failed` | grounded span 缺 binding/quote/ID 不闭合 |
| `render_error` | 渲染/媒体/reader hygiene 失败 |
| `verifier_failed` | Verifier 输出无效；不当作 supported |
| `partial` | 媒体缺失/证据不足/非 blocking 风险；显式记录 |
| `provider_outcome_unknown` | 可能已调用但结果未知；不自动重放 |

### 16.2 观测

- 每次调用：stage、model、prompt/skill hash、evidence pack hash、tokens、latency、cost。
- 每个关键选择：skill 选择、verifier 触发、revise 原因、human waiver。
- Trace/replay：固定 skill/evidence/prompt/model；旧 artifact 冻结。
- 质量：reader test/A-B/专家 review；binding/quote 通过率；失败/partial 统计。
- **模型调用 trace**：每次记录 stage/model/params、system/user prompt 的 hash 与原文路径、raw response、usage（prompt/completion/reasoning/cached）、latency、finish_reason、validation、decision；prompt 原文按 hash 存文件，不塞进 jsonl。
- **实验记录**：输入变体（raw ASR/merged text/pack）、模型/参数、probe 分数、tokens/latency；同 case 同 prompt 可比；不按单篇调参。
- **writer view 与 full pack 分开计**：writer_view chars/tokens、full pack chars/tokens；audit 字段不能挤掉 writer context 预算。
- **views 分开计**：lean view、index、parts、full pack 的 chars/tokens/part 数/oversize 都记录；index+parts 的消费方不读 full pack。
- **模型调用 cache**：按 provider request identity（model/system/user/max_tokens/temperature）做 content-addressed cache；hit 不调用 provider，记录 cached/replayed 与 usage；miss 成功后写缓存；corrupt 回退真实调用。

---

## 17. 非目标与开放问题

### 17.1 非目标

- 不做全量 Scheduler/MCP/Memory/RAG/LangGraph；
- 不做 per-form body/validator/gate；
- 不自动发布；不判断作者主张现实真伪；
- 不伪造画面/生成图当证据；
- 不为 JD 关键词造假；
- 不把旧架构合同全部搬进 v3。

### 17.2 开放问题

- **标题 TOC / 视觉覆盖 / 体验等价如何测量？** 先用 skill rubric + 人工 reader test，不写死字数/图数。
- **视觉规划/图表生成的模型参与与验证**：先确定性候选，再考虑模型；图表数据必须绑定 evidence。
- Skill prompt 的质量/长度/示例数量：需要真实案例测量。
- EvidencePack 的上下文窗口/预算：按视频类型/文体调，不写死。
- Verifier 触发阈值：高风险分类/抽样/self_review；先人工判断。
- 长文分节：按 section/beat 分 Writer，还是单 Writer + 更长上下文；后置。
- 多源/多视频：View/Knowledge 的合并与冲突；后置。
- 开源 license/安全/维护：先审再依赖。
- 质量门：不同文体的 reader/A-B/专家比例；先按文体定义，不套一把尺。

### 17.3 停止条件

- 如果 one-call Writer 质量明显低于完整链基线，先加 1 次 Verifier，再考虑分节/分阶段；**不要先恢复多阶段链**。
- 如果某文体需要新 View/新 Skill 才能成立，先做 2 案例；不直接加 pipeline。
- 如果开源项目与证据优先冲突，只借组件/skill，不搬整条链。

---

## 18. 术语

- **EvidenceSnapshot**：不可变事实底座；units/assertions/claims/evidence/links/frames。
- **TemporalOutline**：时间分段/关键节点。
- **Contextual Evidence Unit**：带 segment/neighbor/frame/stance 的证据单元。
- **View / EvidencePack**：按请求/文体对证据的确定性投影。
- **Skill**：角色/方法/示例/输出 schema/可选脚本的程序性知识包。
- **Writer**：一次生成文章/输出的模型调用。
- **Verifier**：可选独立复核；只看文章+证据，不看 plan 摘要。
- **Binding/Audit/Citations**：确定性引用/回查/审计产物。
- **Plan header**：Writer 同一次输出里的轻量计划，不是单独调用。
- **Small Harness**：Run/Stage/Attempt、Writer/Verifier、usage/trace、tool receipts；不追求大而全。

---

## 19. 一句话总结

v3 把视频编译成**可复用、带上下文的证据**，把写作交给**一次 Skill 驱动的 Writer**，把引用/审计交给**确定性代码**，把多文体交给**View + Skill**，把 JD 交给**小号 Harness**。默认一次调用；高风险才加一次独立 Verifier；不为每个文体、每条 finding、每个视频加规则。
