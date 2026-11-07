# Claude Code 入口

> **2026-11-07 当前状态**：产品 v1 已定义——**聊天式内容工作台**。用户给一条视频 + 写作要求，Agent 按需写一种形态（深度总结 / 公众号 / 小红书），在聊天里预览、修改、验收。目标壳是 **LibreChat + MCP + LangGraph + 排版/导出**。**P1/P2 原型已跑通**：LibreChat + MCP server + preview server + `review_artifact` + 公众号复制 HTML / 小红书 3:4 图集 + 导入包 / Tectonic PDF；LangGraph/评测未接。见 [integrations/librechat/README.md](integrations/librechat/README.md)。
> 三种形态：深度总结（long_article）/ 公众号（wechat_article）/ 小红书（xiaohongshu_note）。短视频脚本暂不做，后续有需要再加。
> **bundle 是内部/调试产物，不是产品默认输出；产品按需生成一种形态。** 不把架构页/评测页放进产品导航。用户 run 数据、开发评测数据、简历数据分开。

开始任何任务前，**按这个顺序**只读：

0. [handoffs/2026-11-07/NEXT_SESSION_PROMPT.md](handoffs/2026-11-07/NEXT_SESSION_PROMPT.md) — 新 session 入口：产品认知、开发方法/纪律/思考方法、本轮自检、下一步思考；附件 [ROUND_REVIEW.md](handoffs/2026-11-07/ROUND_REVIEW.md)。先读它，再按下面顺序核对。
1. [docs/product-v1-chat-studio.md](docs/product-v1-chat-studio.md) — 产品定义/用户怎么用/UI/数据分层/路线；UI 细节见 [docs/ui-design-2026-11.md](docs/ui-design-2026-11.md)。先搞清楚“这是产品，不是作品集或架构 demo”。
2. [architecture.md](architecture.md) §0–§9 — 目标产品架构、组件、当前代码 vs 目标、路线；文末附录是 v3 机会地图，**不是当前实现**。
3. [docs/writing-v5-architecture.md](docs/writing-v5-architecture.md) — 当前写作引擎（writing_v4）：planner/orchestrator/writer/skills/tools/bundle。
4. [docs/jd-mapping-2026-11.md](docs/jd-mapping-2026-11.md) — 2026 JD 真实含义、产品 consumer、评测口径（评测不是 30 judge）。
5. [docs/reuse-stack-2026-11.md](docs/reuse-stack-2026-11.md) — LibreChat / MCP / LangGraph / Pandoc / md2wechat / 卡片库的复用与 license。
6. [STATE.md](STATE.md) + [HANDOFF.md](HANDOFF.md) — 当前快照/接手点。
7. 方法与纪律：[docs/writing-rebuild-brief.md](docs/writing-rebuild-brief.md) §2（好 writing）+ §3（开发纪律）；[AGENTS.md](AGENTS.md) 全局护栏；§5 开发纪律不要改。
8. 需要评测细节时，才读 `runs/_reader_test_2026-11-03/reader_pack/评价方法.md` / `5个persona.md`；不跑 30 judge。

**当前边界**：

- 一个产物一次 writer；Lead Planner 只编排，不写正文；没有 editor/checker。
- Writer 不知道来源；只拿到“这件事的完整内容”；不核验内容本身、不做百科。
- 不写死字数/结构；不按单篇调参；active skill 不出现具体视频/产品/人物。
- 产品按需一种形态；不默认 bundle；多形态 = 多次请求。
- 用户人工验收是唯一发布门；测试绿/跑通不算通过。
- 不恢复旧 supervisor/demo/词表/P1 两段式；不跑 30 judge。
- 复用优先：LibreChat（MIT）/ MCP / LangGraph / Pandoc / md2wechat / 开源卡片；AGPL/BUSL 只作设计参考，除非用户同意合规。
- 不自动 commit/push/publish；不读 `data/cookies/`。

本文件只做入口，不复制规则或状态。历史文档见 `docs/README.md` 的“历史”列表；不要把历史 JD 表/架构当当前。
