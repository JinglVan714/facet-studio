# 文档索引（2026-11-07）

> **项目现名：Facet Studio（原 LunoGraph）**。当前代码/文档已统一更名；`docs/_frozen/`、`_archive/` 保留旧名/旧路径，只作历史。
> 目的：区分 **current（当前产品/实现）** 与 **historical（旧设计/旧 JD/旧 handoff）**，避免后续 session 把历史当基线。
> 入口：[CLAUDE.md](../CLAUDE.md)；护栏：[AGENTS.md](../AGENTS.md)。

## Current — 产品 / 架构 / 实现

| 文档 | 作用 |
|---|---|
| [product-v1-chat-studio.md](product-v1-chat-studio.md) | 产品 v1：聊天式内容工作台；用户怎么用、UI、数据分层、路线 |
| [ui-design-2026-11.md](ui-design-2026-11.md) | UI 设计：chat-first、预览、执行面板、视觉 token、LibreChat 定制点 |
| [architecture.md](../architecture.md) §0–§9 | 目标产品架构、组件、当前代码 vs 目标、路线；**文末附录是 v3 机会地图（历史）** |
| [writing-v5-architecture.md](writing-v5-architecture.md) | 当前写作引擎（writing_v4）：planner/orchestrator/writer/skills/tools/bundle；不是产品壳 |
| [jd-mapping-2026-11.md](jd-mapping-2026-11.md) | 2026 JD 真实含义、产品 consumer、评测口径（数据集/指标/校准/回归/pass^k） |
| [reuse-stack-2026-11.md](reuse-stack-2026-11.md) | LibreChat / MCP / LangGraph / Pandoc / md2wechat / 卡片库复用与 license |
| [integrations/librechat/](../integrations/librechat/README.md) | P1/P2 LibreChat + MCP + preview server 配置/启动/验收；外部 clone 主题/工具名补丁 |
| [integrations/xhs/](../integrations/xhs/README.md) | 小红书 3:4 卡片 + App 导入包（Playwright） |
| [integrations/pdf/](../integrations/pdf/README.md) | 深度总结 PDF（Pandoc + Tectonic + ctex 模板） |
| [evidence-layer-2026-11.md](evidence-layer-2026-11.md) | P5 视频证据层迁移：下载/抽帧/ASR/VLM/substrate → content.md；配置/验证/未验证 |
| [evals/product_v1/](../evals/product_v1/README.md) | P4 deterministic + grounding audit 数据集/报告/协议 |
| [writing-rebuild-brief.md](writing-rebuild-brief.md) §2/§3 | 好 writing / 开发纪律；§4–§9 是历史/写作引擎背景 |
| [substrate-v1-freeze.md](substrate-v1-freeze.md) | substrate v1 接口（冻结，只读） |

## Current — 快照 / 证据

| 文档 | 作用 |
|---|---|
| [STATE.md](../STATE.md) | 当前分支/代码/测试/未做项事实 |
| [HANDOFF.md](../HANDOFF.md) | 当前接手点/下一步 |
| [handoffs/2026-11-07/NEXT_SESSION_PROMPT.md](../handoffs/2026-11-07/NEXT_SESSION_PROMPT.md) | **新 session 入口**：产品/方法/纪律/本轮自检/下一步思考 |
| [handoffs/2026-11-07/ROUND_REVIEW.md](../handoffs/2026-11-07/ROUND_REVIEW.md) | 本轮 P2 自检：改动、验证、已修/存疑 |
| [runs/writing_v5/](../runs/writing_v5/) | 最新 bundle 与 trace 证据 |
| [runs/product_v1/](../runs/product_v1/) | P1/P2 产品原型 run：内容稿、article/note、reader.html、wechat.html、xhs_export、PDF、run_meta、publish_review |

## Historical — 不要当 current

| 文档 | 说明 |
|---|---|
| [multiform-roadmap.md](multiform-roadmap.md) | 2026-11-05 多文体路线；JD 表是 pre-2026，已被 [jd-mapping-2026-11.md](jd-mapping-2026-11.md) 取代 |
| [social-writing-reuse-map.md](social-writing-reuse-map.md) | 2026-11-05 社媒调研；当前复用栈见 [reuse-stack-2026-11.md](reuse-stack-2026-11.md) |
| [writing-reuse-map.md](writing-reuse-map.md) | 旧复用决策；当前复用栈见 [reuse-stack-2026-11.md](reuse-stack-2026-11.md) |
| [reference-writing-scan.md](reference-writing-scan.md) | 2026-10-31 参考扫描；历史 |
| [evals/writing/](../evals/writing/) | 旧 request 模板；不是当前 eval；当前见 [evals/product_v1/](../evals/product_v1/README.md) |
| [writing-layer-map.md](writing-layer-map.md) | v1 写作层设计；历史 |
| [writing-layer-contracts.md](writing-layer-contracts.md) | v1 契约设计；历史 |
| [writing-operating-model.md](writing-operating-model.md) | v1 operating model；历史 |
| [writing-planner-position.md](writing-planner-position.md) | 旧 planner 定位；历史 |
| [writing-skill-study.md](writing-skill-study.md) | 旧 skill 学习笔记；历史 |
| [architecture.md](../architecture.md) 文末附录 | v3 机会地图/早期实现假设；不是当前实现 |
| [runs/_reader_test_2026-11-03/reader_pack/](../runs/_reader_test_2026-11-03/reader_pack/) | 12 维/5 层写作标准与 persona；评测设计参考，不是当前 eval 流程 |
| [handoffs/](../handoffs/) | 历史交接，只追加 |
| [_archive/](../_archive/) | 归档；不恢复 |
| [portfolio/](../portfolio/) | 旧 P1 作品案例；历史，不是 current eval |
| [deliverables/writing-skill/](../deliverables/writing-skill/) | 旧 articles-only 作品集；历史，不是当前产品 |
| [skills/writing/video-article/README.md](../skills/writing/video-article/README.md) | 旧 article pipeline 说明；SKILL.md 仍是 active，README 的一致性 pass 不是当前默认 |

## 冲突处理

- 产品/UX 冲突：以 [product-v1-chat-studio.md](product-v1-chat-studio.md) 为准。
- UI/视觉冲突：以 [ui-design-2026-11.md](ui-design-2026-11.md) 为准。
- 系统架构冲突：以 [architecture.md](../architecture.md) §0–§9 为准。
- 写作引擎冲突：以 [writing-v5-architecture.md](writing-v5-architecture.md) 为准。
- JD/评测冲突：以 [jd-mapping-2026-11.md](jd-mapping-2026-11.md) 为准；旧 roadmap 的 JD 表不要用。
- 复用/license 冲突：以 [reuse-stack-2026-11.md](reuse-stack-2026-11.md) 为准。
- 当前状态冲突：以 [STATE.md](../STATE.md) 为准。
