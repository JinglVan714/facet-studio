# 文档索引

> 项目现名 **Facet Studio**。公开仓库只保留当前产品/实现文档；内部交接、历史稿和
> 求职材料不随仓库发布。
> 入口：[README.md](../README.md)；产品定义：[product-v1-chat-studio.md](product-v1-chat-studio.md)；
> 系统架构：[architecture.md](../architecture.md) §0–§9。

## 产品 / 架构

| 文档 | 作用 |
|---|---|
| [product-v1-chat-studio.md](product-v1-chat-studio.md) | 产品 v1：聊天式内容工作台；用户怎么用、UI、数据分层、路线 |
| [ui-design-2026-11.md](ui-design-2026-11.md) | UI 设计：chat-first、预览、执行面板、视觉 token、LibreChat 定制点 |
| [architecture.md](../architecture.md) §0–§9 | 目标产品架构、组件、当前代码 vs 目标、路线 |
| [writing-v5-architecture.md](writing-v5-architecture.md) | 当前写作引擎（writing_v4）：planner/orchestrator/writer/skills/tools/bundle |
| [substrate-v1-freeze.md](substrate-v1-freeze.md) | substrate v1 接口（冻结，只读） |

## 可观测 / 评测 / 证据

| 文档 | 作用 |
|---|---|
| [observability-2026-11.md](observability-2026-11.md) | 运行中/复盘两段、消息级运行卡、逐帧审计、Trace/Stats |
| [runtime-evidence-2026-11-09.md](runtime-evidence-2026-11-09.md) | 2026-11-09 运行时证据：P4 cases、最新 E2E、/runs 聚合；含不可引用口径 |
| [visual-strategy-2026-11.md](visual-strategy-2026-11.md) | 视觉策略：关键帧极紧门槛、图注默认不加、语义绘图/原生组件优先 |
| [evidence-layer-2026-11.md](evidence-layer-2026-11.md) | P5 视频证据层：下载/抽帧/ASR/VLM/substrate → content.md |
| [evidence-2026-11.md](evidence-2026-11.md) | 可提交的 run 证据摘要（P1–P5） |
| [evals/product_v1/](../evals/product_v1/README.md) | P4 deterministic + grounding audit：数据集/报告/协议 |

## 复用 / 集成

| 文档 | 作用 |
|---|---|
| [reuse-stack-2026-11.md](reuse-stack-2026-11.md) | LibreChat / MCP / LangGraph / Pandoc / md2wechat / 卡片库复用与 license |
| [integrations/librechat/](../integrations/librechat/README.md) | LibreChat + MCP + preview server 配置/启动/验收 |
| [integrations/xhs/](../integrations/xhs/README.md) | 小红书 3:4 卡片 + App 导入包（Playwright） |
| [integrations/pdf/](../integrations/pdf/README.md) | 深度总结 PDF（Pandoc + Tectonic + ctex 模板） |
| [examples/demo/](../examples/demo/README.md) | 一份可公开的真实产物样本（无视频帧） |
| [demo-script.md](demo-script.md) | 3 分钟 demo 分镜（截图版） |

## 方法与边界

| 文档 | 作用 |
|---|---|
| [writing-rebuild-brief.md](writing-rebuild-brief.md) §2/§3 | 好 writing 的判断标准 + 开发纪律 |
| [jd-mapping-2026-11.md](jd-mapping-2026-11.md) | 2026 JD 能力映射与评测口径（产品视角） |
| [jd-keywords-2026-11-08.md](jd-keywords-2026-11-08.md) | 2026-11-08 外部关键词复核 |

## 冲突处理

- 产品/UX：以 [product-v1-chat-studio.md](product-v1-chat-studio.md) 为准。
- UI/视觉：以 [ui-design-2026-11.md](ui-design-2026-11.md) 为准。
- 系统架构：以 [architecture.md](../architecture.md) §0–§9 为准。
- 写作引擎：以 [writing-v5-architecture.md](writing-v5-architecture.md) 为准。
- JD/评测：以 [jd-mapping-2026-11.md](jd-mapping-2026-11.md) 为准。
- 复用/license：以 [reuse-stack-2026-11.md](reuse-stack-2026-11.md) 为准。
