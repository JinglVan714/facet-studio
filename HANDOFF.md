# HANDOFF — 2026-11-09

> 当前快照/接手点。**新 session 从这里进**：[handoffs/2026-11-09/NEXT_SESSION_PROMPT.md](handoffs/2026-11-09/NEXT_SESSION_PROMPT.md)（判断 + 收尾）；上一轮：[handoffs/2026-11-08/NEXT_SESSION_PROMPT.md](handoffs/2026-11-08/NEXT_SESSION_PROMPT.md)；方法入口：[handoffs/2026-11-07/NEXT_SESSION_PROMPT_P5.md](handoffs/2026-11-07/NEXT_SESSION_PROMPT_P5.md)；旧 P2 快照：[NEXT_SESSION_PROMPT.md](handoffs/2026-11-07/NEXT_SESSION_PROMPT.md)（历史，保留不改）；P2 自检：[ROUND_REVIEW.md](handoffs/2026-11-07/ROUND_REVIEW.md)。
> 产品：[docs/product-v1-chat-studio.md](docs/product-v1-chat-studio.md)；目标架构：[architecture.md](architecture.md) §0–§9；写作引擎：[docs/writing-v5-architecture.md](docs/writing-v5-architecture.md)；JD：[docs/jd-mapping-2026-11.md](docs/jd-mapping-2026-11.md)；复用：[docs/reuse-stack-2026-11.md](docs/reuse-stack-2026-11.md)；证据层：[docs/evidence-layer-2026-11.md](docs/evidence-layer-2026-11.md)；评测：[evals/product_v1/README.md](evals/product_v1/README.md)。旧 handoff 是历史，不是方向指令。

## 当前状态

- **2026-11-08 发布级闭环**：路径/配置/README/死链收口；P5 新视频（BV1brgs6mE7a）下载 + DashScope ASR 3.1 + VLM + content + workflow 真 E2E；P4 10/10 cases、contract 10/10、trajectory 30/30；3 个新 machine run 待用户验收。详见 [STATE.md](STATE.md) 顶部与 [docs/evidence-2026-11.md](docs/evidence-2026-11.md)。
- **2026-11-08 视觉策略落地**：关键帧极紧（默认 0，最多 1）、图注默认不加、表格/代码/清单/SVG 优先；见 [docs/visual-strategy-2026-11.md](docs/visual-strategy-2026-11.md)。关系型 `scatter` / `two-track` / `threshold` 试做后经用户判定效果不如上一版，**已回退**（试跑产物保留为实验）。PDF 先 SVG→PNG 再排版，封面改用证据层视频封面（`data/<vid>/cover.jpg`），SVG 不再当封面。产物在 `runs/_visual_skill_check/` / `runs/product_v1/`，待用户验收。
- **2026-11-09 交接方向**：项目进入**收尾判断**。新 session 先按顺序认知架构/方法/进度，允许联网调研 JD 关键词在真实项目里怎么落地，然后给用户一屏判断（现状 / 差距 / 3 条优先级），再精准收尾；不再铺新功能。详见 [handoffs/2026-11-09/NEXT_SESSION_PROMPT.md](handoffs/2026-11-09/NEXT_SESSION_PROMPT.md)。
- **2026-11-08 SKILL 清理进度（本 session）**：active skills 已去具体视频/产品/人物/单篇数字例子；技术实现细节规则条件化；新增中文标点、`can_skip` 核心证据、禁止另起标签三条通用规则；`reader_first_explainer` 示例/视觉参考已清；当时 601 tests passed。通用验证：`BV1qoHe6mEx6`（Agent Memory）× 三形态、`BV1znXSBqEUP`（观点/分析）× 公众号；产物在 `runs/_skill_check_2026-11-08/`，grounding 4 artifacts/42 candidate flags。新增 [docs/jd-keywords-2026-11-08.md](docs/jd-keywords-2026-11-08.md)（2026 JD 关键词复核）。预览渲染已做一轮：reader 加 hero/目录/阅读元信息/卡片式正文/表格滚动/代码块；wechat 改 520px 手机预览卡 + 元信息 + 衬线 H2；Edge 截图验证。Trace/可观测已接：`observability.py` + `trace.html`（stages/llm_calls/tool_calls/decisions/机器检查/grounding）+ `get_run.trace` + 预览页“运行数据”链接；workflow 产出 tool/decision spans；真实 run `20261108T154015Z_BV1B5411A7ax_wechat_article` 已验证（2 calls / 36,619 tokens / 6 tool spans / 3 decisions / checks 15/15，待验收）。可观测 v2：Run Detail（Live SSE / Trace / Stats）+ `/runs` 看板；去掉 Story/说人话层；聊天 UI 已实测：tool card 出现“运行数据”按钮，点击打开 `/runs/<run_id>`（截图 `runs/product_v1/_ui_chat_run_link.png` / `_ui_run_detail_from_chat4.png`）；设计见 [docs/observability-2026-11.md](docs/observability-2026-11.md)。**不在本地跑 Langfuse**。608 tests。
- **产品 v1 已定义**：聊天式内容工作台。用户给视频 + 写作要求，Agent 按需写一种形态（深度总结 / 公众号 / 小红书），聊天内预览/修改/验收。
- **目标壳**：LibreChat（MIT）+ MCP + LangGraph + 排版/导出 + 人工验收。
- **当前代码**：writing_v4 写作引擎 + **P1/P2 产品原型 + P3 workflow 原型 + P4 deterministic/grounding harness + P5 证据层**：`src/facet_studio/mcp_server.py`（12 tools）、`src/facet_studio/workflow.py`、`src/facet_studio/evidence_layer/`、`src/facet_studio/ingest.py`、`src/facet_studio/preview_server.py`、`integrations/librechat/`、`integrations/xhs/`、`integrations/pdf/`、`evals/product_v1/`；LibreChat 外部 clone `D:/luno_external/librechat`。bundle 是内部/调试产物，不是产品默认输出。
- **P1/P2 已验证（用户大致通过，7 个产物 approved）**：
  - BV17 公众号：`runs/product_v1/20261106T131015Z_BV17DHC6CELr_wechat_article/`（approved；复制正文不含 H1，每图有复制/下载）。
  - BV17 小红书：`runs/product_v1/20261107T032530Z_BV17DHC6CELr_xiaohongshu_note/`（1,274 字 / 6 张 3:4 PNG / 5 标签 / 16,208 tokens）。
  - BV1ix 小红书：`runs/product_v1/20261106T132229Z_BV1ixpd6GENc_xiaohongshu_note/`（3 张 3:4 PNG）。
  - BV13 公众号：`runs/product_v1/20261107T080924Z_BV13EHX64EaY_wechat_article/`（2,734 字 / 3 图）。
  - 深度总结 PDF：`runs/product_v1/smoke_long_pdf/long_article/article.pdf`（6 页）及含代码块长文 `20261106T130634Z_BV17DHC6CELr_long_article`（7 页）。
  - 首页引导、中文工具名、暖纸主题：已在本机 LibreChat clone 验证。
- **P3 workflow**：StateGraph + checkpoint + plan/review interrupt + `workflow.json` trace；真实 UI E2E 会话 `19e3aeb3-0854-549b-b18e-a37df12e8812` → run `20261107T132341Z_BV1B5411A7ax_xiaohongshu_note`（2 calls / 17,327 tokens / approved）。
- **P4**：10 cases 全有 run；contract 10/10、trajectory 30/30、error 0；manual 7/10（3 个新 run 待验收）；grounding 9 artifacts / 16 candidate flags（不是幻觉率、不评 writing 质量）。报告 `evals/product_v1/reports/`。
- **P5**：证据层 `src/facet_studio/evidence_layer/` + `ingest.py` + MCP `ingest_source`；2026-11-08 新视频下载 + DashScope ASR（Qwen-Audio 3.1）+ VLM + content + workflow 已跑通；3.0 的免费额度会耗尽，3.1 同端点可用。
- 测试：**601 passed**。
- 文档收口：product / UI / architecture / JD / reuse / docs index / integrations / evidence / eval 已更新；旧 roadmap/JD 表加历史标记。

## 接手先读（顺序）

1. [docs/product-v1-chat-studio.md](docs/product-v1-chat-studio.md) — 产品定义/交互/UI/数据分层/路线。
2. [architecture.md](architecture.md) §0–§9 — 目标架构、组件、当前代码 vs 目标；文末附录是 v3 机会地图，不是当前实现。
3. [docs/writing-v5-architecture.md](docs/writing-v5-architecture.md) — 当前写作引擎。
4. [docs/jd-mapping-2026-11.md](docs/jd-mapping-2026-11.md) — 2026 JD 真实含义/评测口径。
5. [docs/reuse-stack-2026-11.md](docs/reuse-stack-2026-11.md) — 复用与 license。
6. [docs/evidence-layer-2026-11.md](docs/evidence-layer-2026-11.md) — P5 证据层迁移/链路/未验。
7. [evals/product_v1/README.md](evals/product_v1/README.md) — P4 deterministic + grounding，不评 writing 质量。
8. [STATE.md](STATE.md) + 本文件。

## 当前任务

**P1 + P2 原型已完成（2026-11-07）**：LibreChat + MCP + 缓存内容 → 计划卡 → 一次 writer → 阅读预览 → 公众号 HTML / 小红书图集 / PDF → `review_artifact` 验收。

**P2 收口（2026-11-07 本轮）**：已修公众号复制正文带 H1、`title_candidates` 的 ` / ` 分隔、typeset 失败落盘为 `partial` + `typeset_errors`、`get_run` 的 `review_status`（draft/stale/approved/草稿摘要）、`review_artifact` 的排版门槛、重新 typeset 后旧验收标 stale。视觉模板也收口：小红书卡片改为 3:4 图框 `contain`（不裁 16:9）、阅读页纵向复用导出卡；PDF 图片限制在正文版心 / 62% 页高、剥离正文来源行消除孤儿页、首行缩进、代码块用 `--listings`；公众号图片限高 520px。图片数量/水印/字幕/低信息素材属于 skill/素材层，本轮不按单篇修。测试 **580 passed**。用户 2026-11-07 大致通过；BV13/BV17 公众号、BV17/BV1ix 小红书、smoke/第二篇长文 PDF 已记 approved（`runs/product_v1/**/publish_review.json`，不入库）。P3/P4/P5 已接原型，见下；P5 真实新视频端到端已于 2026-11-08 跑通（DashScope ASR 3.1）。
**后续待修（本轮不修）**：[docs/backlog-2026-11.md](docs/backlog-2026-11.md)（选图/造图、正文调整、标题/图注/短标题、视觉审查剩余 P1/P2）。

下一步按优先级：

1. **P2 收尾（已验收 2026-11-07）**：公众号/小红书/PDF 已按用户“大致通过”记 approved；剩首页模型配置入口（用户说先留口子，后置）。
2. **内容层待改**：见 [docs/backlog-2026-11.md](docs/backlog-2026-11.md)；不按单篇调。
3. **P3（原型已跑通 2026-11-07）**：`workflow.py` 用 LangGraph StateGraph + SQLite checkpoint + plan/review interrupt；MCP 增加 `start_workflow` / `resume_workflow` / `get_workflow`；真实 auto run（BV1B 小红书，2 calls / 13,019 tokens）已写 `workflow.json`；真实 manual plan gate（`20261107T124434Z_BV1B5411A7ax_wechat_article`）已验证暂停→changes_requested、未写正文。LibreChat 后端在 P3 时已加载 11 tools；P5 后新增 `ingest_source`，应重启确认 12 tools。agent instructions 已改为 workflow 默认（P1/P2 为 fallback）；`client-ui.patch` 增加中文动作名，frontend 已重建。真实 UI E2E 已跑通：会话 `19e3aeb3-0854-549b-b18e-a37df12e8812` → run `20261107T132341Z_BV1B5411A7ax_xiaohongshu_note`（计划卡暂停→approved→写/排版→验收 approved；2 calls / 17,327 tokens；标签“启动工作流/继续工作流/运行数据”可见）。待做：cost 面板（当前 rates 未配置时 `cost_estimate=null`）、完整 stream UI。
4. **P4（deterministic + grounding harness 已接 2026-11-07）**：`evals/product_v1/cases.json` + `src/facet_studio/evals/product.py`、`grounding.py`；当前 7/9 cases 有 artifact（BV1ix long/wechat missing），deterministic 7/7、manual 7/7、planner trace 4/7；grounding audit 6 artifacts / 17 candidate flags（不是幻觉率、不评 writing 质量）。报告在 `evals/product_v1/reports/`。待做：补 2 个 capability cases、人工 adjudicate flags（可选，仅事实判定）、trajectory 扩展、回归门禁、pass@k。
5. **P5（证据层已迁移；2026-11-08 真 E2E）**：`src/facet_studio/evidence_layer/` + `src/facet_studio/ingest.py`，MCP 新增 `ingest_source`；链路为下载/本地 → 抽帧/ASR → VLM → `content_manuscript` → `content_final_v3/content.md + figures`。BV1brgs6mE7a（2 分钟）已验证：下载 + DashScope ASR 3.1 + VLM + content 1,577 字/4 图（短参考重建后 1,052 字/4 图）。审计前 run `20261108T052817Z`（1,981 字/2 图/24,563 tokens）；审计后产品 run `20261108T095810Z`（4 个候选/0 通过、1 SVG、1,720 字、含审计 31,223 tokens）。3.0 免费额度耗尽，3.1 同端点可用；不使用本地 ASR/OCR。产品默认 `content_only=True`（跳过 contract/L1）；完整证据层用 `include_evidence=True`。

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
