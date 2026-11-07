# HANDOFF — 2026-11-07

> 当前快照/接手点。**新 session 从这里进**：[handoffs/2026-11-07/NEXT_SESSION_PROMPT.md](handoffs/2026-11-07/NEXT_SESSION_PROMPT.md)；本轮自检：[handoffs/2026-11-07/ROUND_REVIEW.md](handoffs/2026-11-07/ROUND_REVIEW.md)。
> 产品：[docs/product-v1-chat-studio.md](docs/product-v1-chat-studio.md)；目标架构：[architecture.md](architecture.md) §0–§9；写作引擎：[docs/writing-v5-architecture.md](docs/writing-v5-architecture.md)；JD：[docs/jd-mapping-2026-11.md](docs/jd-mapping-2026-11.md)；复用：[docs/reuse-stack-2026-11.md](docs/reuse-stack-2026-11.md)。旧 handoff 是历史，不是方向指令。

## 当前状态

- **产品 v1 已定义**：聊天式内容工作台。用户给视频 + 写作要求，Agent 按需写一种形态（深度总结 / 公众号 / 小红书），聊天内预览/修改/验收。
- **目标壳**：LibreChat（MIT）+ MCP + LangGraph + 排版/导出 + 人工验收。
- **当前代码**：writing_v4 写作引擎 + **P1/P2 产品原型**：`src/facet_studio/mcp_server.py`、`src/facet_studio/preview_server.py`、`integrations/librechat/`、`integrations/xhs/`、`integrations/pdf/`；LibreChat 外部 clone `D:/luno_external/librechat`。LangGraph/评测未接。bundle 是内部/调试产物，不是产品默认输出。
- **P1 已验证**：
  - BV17 公众号：`runs/product_v1/20261106T131015Z_BV17DHC6CELr_wechat_article/`（2767 字 / 5 图；原 approved，2026-11-07 重排版后标 stale，需重新验收）。
  - 启动/配置：[integrations/librechat/README.md](integrations/librechat/README.md)。
- **P2 已验证（2026-11-07）**：
  - **完整 Agent 流程**：`runs/product_v1/20261107T032530Z_BV17DHC6CELr_xiaohongshu_note/`（LibreChat → plan → write → typeset；1,274 字 / 6 张 3:4 PNG / 5 标签 / 2 次模型调用 / 16,208 tokens）。
  - 小红书横滑图集 + App 导入包：同上 `xhs_export/`（6 张 PNG + title/body/tags + manifest + README）。
  - 公众号复制页：`wechat.html`（内联样式 + 复制正文）。
  - 深度总结 PDF：`runs/product_v1/smoke_long_pdf/long_article/article.pdf`（9 页；封面/目录/正文已人工检查）。
  - 首页引导、中文工具名、暖纸主题：已在本机 LibreChat clone 验证。
- 测试：**570 passed**。
- 文档收口：product / UI / architecture / JD / reuse / docs index / integrations 已更新；旧 roadmap/JD 表加历史标记。

## 接手先读（顺序）

1. [docs/product-v1-chat-studio.md](docs/product-v1-chat-studio.md) — 产品定义/交互/UI/数据分层/路线。
2. [architecture.md](architecture.md) §0–§9 — 目标架构、组件、当前代码 vs 目标；文末附录是 v3 机会地图，不是当前实现。
3. [docs/writing-v5-architecture.md](docs/writing-v5-architecture.md) — 当前写作引擎。
4. [docs/jd-mapping-2026-11.md](docs/jd-mapping-2026-11.md) — 2026 JD 真实含义/评测口径。
5. [docs/reuse-stack-2026-11.md](docs/reuse-stack-2026-11.md) — 复用与 license。
6. [STATE.md](STATE.md) + 本文件。

## 当前任务

**P1 + P2 原型已完成（2026-11-07）**：LibreChat + MCP + 缓存内容 → 计划卡 → 一次 writer → 阅读预览 → 公众号 HTML / 小红书图集 / PDF → `review_artifact` 验收。

**P2 收口（2026-11-07 本轮）**：已修公众号复制正文带 H1、`title_candidates` 的 ` / ` 分隔、typeset 失败落盘为 `partial` + `typeset_errors`、`get_run` 的 `review_status`（draft/stale/approved/草稿摘要）、`review_artifact` 的排版门槛、重新 typeset 后旧验收标 stale。视觉模板也收口：小红书卡片改为 3:4 图框 `contain`（不裁 16:9）、阅读页纵向复用导出卡；PDF 图片限制在正文版心 / 62% 页高、剥离正文来源行消除孤儿页、首行缩进、代码块用 `--listings`；公众号图片限高 520px。图片数量/水印/字幕/低信息素材属于 skill/素材层，本轮不按单篇修。测试 **570 passed**。等用户人工验收三种产物；验收通过后进入 P3（LangGraph + HITL + 观测）。

下一步按优先级：

1. **P2 收尾**：用户人工验收新小红书/PDF 产物；把首页模型配置提示换成真正的配置入口（当前是 `.env` 提示）。
2. **内容层待改**：小红书标题钩子（用户明确说最后改，不按单篇调）；公众号数字过多/缺图表（只记录，不在排版层解决）。
3. **P3**：LangGraph workflow + checkpoint + streaming + interrupt/HITL；把 MCP 工具编排迁进去。
4. **P4**：评测 harness（capability/regression、deterministic checks、trajectory、judge 校准、pass@k/pass^k）；不要 30 judge。
5. **P5**：视频转录接入（最后）。

## 边界

- 一个产物一次 writer；Lead Planner 只编排；没有 editor/checker。
- Writer 不知道来源；只拿到“这件事的完整内容”；不核验内容本身、不做百科。
- 产品按需一种形态；不默认 bundle；多形态 = 多次请求。
- 不写死字数/结构；不按单篇调参；active skill 不出现具体视频/产品/人物。
- 用户人工验收是唯一发布门；测试绿/跑通不算通过。
- 不恢复旧 supervisor/demo/词表/P1 两段式；不跑 30 judge；不自动发布；不 commit/push。
- 复用优先；嵌入代码优先 MIT/BSD/Apache；AGPL/BUSL 只作设计参考，除非用户同意合规。

## 开放问题（只记录，不预设）

- 部署形态：本地 Docker（LibreChat + MongoDB + Python MCP）还是公网 URL？公网需要鉴权/限流/成本上限。
- LibreChat 自定义程度：只换主题 + artifact renderer，还是 fork 更深？
- 评测什么时候做、做多大：先预留；产品原型稳定后再定。
- 目标 JD/公司：需要 2–3 份真实 JD 再收紧映射。
- 视频转录接入：最后做；现阶段用缓存内容。
