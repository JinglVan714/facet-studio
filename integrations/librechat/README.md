# LibreChat P1/P2 integration

> 状态：2026-11-06 P1 原型已跑通；2026-11-07 P2 排版/导出/UI 已接；2026-11-09 端到端运行卡/后台 run/右侧预览已接。LibreChat 是外部 clone，不 vendored 进本仓库；这里放可复现配置。
> 目标：聊天 → 一次 writer → 聊天内运行卡/预览/导出 → 用户验收。默认不在计划卡停；缓存内容，不重跑视频。
> 产品定义：[docs/product-v1-chat-studio.md](../../docs/product-v1-chat-studio.md)；架构：[architecture.md](../../architecture.md)。

## 1. 本地环境（已验证）

- LibreChat `v0.8.9-rc1`（MIT），clone 到任意目录；本文用 `<LibreChat>` 表示。已验证目录为外部 clone（不在本仓库内）。
- Node `v22.14.0`（LibreChat 部分包声明 `^22.18.0 || >=24`，有 engine warning；当前 build/run 可通过）。
- MongoDB 用 `mongodb-memory-server` 本地进程，不装 MongoDB 服务。
- Python 用项目 conda 环境（3.11.14）；本文用 `<Python>` 表示。
- 预览服务：`facet_studio.preview_server`（FastAPI/uvicorn，127.0.0.1:8765）。
- MCP：`facet_studio.mcp_server`（FastMCP stdio）。

## 2. 一次性准备

```bash
# 1) clone + install + build（外部目录；<LibreChat> 可任意）
git clone --depth 1 https://github.com/danny-avila/LibreChat.git <LibreChat>
cd <LibreChat>
npm install
npm run build

# 2) 复制配置模板
cp <project>/integrations/librechat/librechat.yaml.example ./librechat.yaml
cp <project>/integrations/librechat/env.example ./.env
cp <project>/integrations/librechat/dev-mongo.cjs ./scripts/dev-mongo.cjs

# 3) 编辑 .env：填入 DEEPSEEK_API_KEY/BASE_URL/MODEL；
#    生成 JWT_SECRET / JWT_REFRESH_SECRET / CREDS_KEY(32B hex) / CREDS_IV(16B hex)
# 4) 编辑 librechat.yaml：替换 __PROJECT_ROOT__ / __PYTHON_EXE__
```

## 3. 启动（三个进程）

一键（Windows PowerShell，先改脚本顶部路径）：

```powershell
powershell -ExecutionPolicy Bypass -File <project>/scripts/start_p1.ps1
```

手动：

```bash
# A. Mongo（LibreChat 依赖）
cd <LibreChat> && node scripts/dev-mongo.cjs

# B. 预览服务
cd <project> && PYTHONPATH=src python -m facet_studio.preview_server

# C. LibreChat
cd <LibreChat> && npm run backend
# open http://localhost:3080
```

## 4. Agent 配置

在 LibreChat 里创建一个 Agent（也可用 API）：

- name: `Facet Studio`
- provider: `DeepSeek`
- model: `deepseek-flash`
- artifacts: `default`
- tools（MCP `facet_studio`）：
  - `ingest_source_mcp_facet_studio`（P5：新 BV/本地视频接入证据层）
  - `list_sources_mcp_facet_studio`
  - `resolve_source_mcp_facet_studio`
  - `compile_content_mcp_facet_studio`
  - `plan_article_mcp_facet_studio`
  - `write_form_mcp_facet_studio`
  - `typeset_article_mcp_facet_studio`
  - `get_run_mcp_facet_studio`
  - `review_artifact_mcp_facet_studio`
  - `start_workflow_mcp_facet_studio`（P3：后台启动 LangGraph 工作流，默认 `auto_plan=True` 端到端直写，只在最终验收暂停；立即返回 run_id）
  - `wait_workflow_mcp_facet_studio`（P3：等待到下一个门，返回摘要/资产数/下一步，不返回完整正文）
  - `resume_workflow_mcp_facet_studio`（P3：确认计划卡/最终验收后恢复）
  - `get_workflow_mcp_facet_studio`（P3：阶段、暂停点、usage、trace）
- instructions: 见 [agent-instructions.md](agent-instructions.md)
- conversation starters: 由外部 clone 的 `ConversationStarters.tsx` 在 agent name = `Facet Studio` 时替换为三张通用引导卡（输入视频 / 选择内容 / 告诉偏好）+ 模型配置提示，不使用某条具体 BV。

## 4.1 外部 clone 的 P2 修改（不做 vendored）

LibreChat clone 里只改主题/展示层，不改核心 pipeline：

- `client/src/utils/toolLabels.ts`：`FACET_MCP_TOOL_LABELS` 把 13 个工具映射成中文动作名（接入新视频/查看来源/读取视频/规划/写作/排版/运行数据/验收/启动工作流/等待工作流/继续工作流/工作流状态）。
- `client/src/utils/facet.ts`、`client/src/components/Facet/FacetActivity.tsx`、`FacetRunCard.tsx`、`FacetPreviewPanel.tsx`：消息级只渲染一张运行卡；卡轮询 `/runs/<id>/api/card` 显示阶段、计划、视觉审计、字数和交付物；右侧抽屉预览阅读页/公众号/PDF。Facet tool parts 不再渲染原始 JSON 或“执行过程”分组；`ToolCall.tsx` 只保留中文动作名。
- `start_workflow` 的 MCP 输出很大时会被 LibreChat 截断；`facet.ts` 从截断前缀恢复 `run_id/form/status/trace_url`，详细内容由 card API 补；不完整 run_id 的片段会被丢弃，避免出现第二张重复卡。
- `client/src/components/Chat/Input/ConversationStarters.tsx`：三张引导卡 + 模型配置提示。
- `client/index.html`、`client/src/locales/zh-Hans/translation.json`：品牌/标题/中文 UI。
- `librechat.yaml`：`facet-studio` 暖纸主题、`facet_studio` MCP、欢迎语。
- 改完 client 后：`npm run frontend`，再重启 `npm run backend`（否则可能白屏/旧 chunk）。

补丁文件：[patches/client-ui.patch](patches/client-ui.patch)。在新 clone 上应用：

```bash
cd <LibreChat>
git apply <project>/integrations/librechat/patches/client-ui.patch
npm run frontend
```

补丁含展示层文件（含新增 `client/src/utils/facet.ts`、`client/src/components/Facet/*`）；`librechat.yaml` 主题/MCP 配置用 `librechat.yaml.example`，不放进 patch。

## 4.2 P3 workflow（原型）

`src/facet_studio/workflow.py` 用 LangGraph StateGraph 串 `intake → plan → approval → write → typeset → review`：

- `start_workflow`：默认 `background=True`，立即返回 `run_id` + `status=running`；`auto_plan=True` 时跳过计划卡直接写，只在最终验收 `interrupt`。用户明确要计划时才传 `auto_plan=False`。
- `wait_workflow(run_id)`：轮询到计划门/验收门/终态；返回压缩后的 `summary/assets/plan/typeset/preview_url`，不返回完整正文，避免 MCP 输出被截断后模型读错。
- `resume_workflow(run_id, decision)`：计划卡/最终验收恢复；`decision=approved/changes_requested/rejected`。人工验收仍是唯一发布门。
- `get_workflow(run_id)`：`workflow.json` 里的 `status/next/stages/events/usage/cost_estimate`；MCP 返回同样压缩。
- checkpoint：`runs/product_v1/_workflow_checkpoints.sqlite`；run 目录写 `workflow.json`，`get_run` 也会带回。
- 可选成本：`.env` 里填 `FACET_STUDIO_INPUT_COST_PER_MTOK` / `FACET_STUDIO_OUTPUT_COST_PER_MTOK`；未填时 `cost_estimate=null`。

## 4.3 P5 视频接入（证据层）

- 证据层代码：`src/facet_studio/evidence_layer/`（从 `知识底稿核心-clean` 迁移）；入口 `facet_studio.ingest.ingest_source`。
- 链路：`ingest_source(target)` → yt-dlp/本地登记 → 抽帧 + ASR → VLM → `content_manuscript` → `runs/writing_rebuild_2026-11-04/<vid>/content_final_v3/content.md + figures`。
- 产品默认 `content_only=True`：跳过 contract/L1（写作层只消费 transcript + frames + VLM captions）；需要完整证据层时传 `include_evidence=True`。
- 依赖：`yt-dlp`、`DASHSCOPE_API_KEY`（ASR/VLM）、`DEEPSEEK_API_KEY`（仅完整证据层/L1）；cookie 可选，路径 `data/cookies/bilibili.txt`（不读内容、不提交）。
- **长视频请先用 CLI ingest**：MCP tool 是同步调用，LibreChat 默认 MCP timeout 300s；当前没有后台任务/进度恢复。2 分钟视频实测 158s 可过；更长视频先在终端跑 `facet_studio.ingest.ingest_source`，再在聊天里用缓存内容。
- ASR 默认 `qwen-audio-3.1-asr-flash-streaming`（DashScope）；VLM 默认 `qwen3.8-27b`。3.0 的免费额度可能耗尽（status=44），3.1 同端点可用。
- 设计：新视频接入后立即复用现有 `list_sources → resolve_source → workflow`，写作层不感知视频/证据层。
- 验证：迁移备份的 17 个证据层测试通过；`evidence_mcp --selftest` 对现有 `data/` 通过；`content_manuscript` 从 `data/BV17DHC6CELr` 重建 4,213 字 / 10 图。

## 5. P1/P2 验收

已跑通：

- BV17 → 公众号：`runs/product_v1/20261106T131015Z_BV17DHC6CELr_wechat_article/`（2767 字 / 5 图；2026-11-07 重排版后已重新 approved）。
- BV1ix → 小红书：`runs/product_v1/20261106T132229Z_BV1ixpd6GENc_xiaohongshu_note/`（999 字 / 3 图）。
- 完整 Agent 流程 → 小红书（2026-11-07）：`runs/product_v1/20261107T032530Z_BV17DHC6CELr_xiaohongshu_note/`（1,274 字 / 6 图 / 5 标签 / 6 张 3:4 PNG）。
- 单独 typeset 验证 → 小红书：`runs/product_v1/20261107T031556Z_BV17DHC6CELr_xiaohongshu_note/`（1,172 字 / 2 图 / 5 标签 / 2 张 3:4 PNG）。
- 深度总结 → PDF：`runs/product_v1/smoke_long_pdf/long_article/article.pdf`（6 页）；含代码块长文 `20261106T130634Z_BV17DHC6CELr_long_article`（7 页）。
- 工具调用：`resolve_source → plan_article → write_form → typeset_article → get_run`；人工 `review_artifact` 写 `publish_review.json`。
- 预览：`http://127.0.0.1:8765/runs/<run_id>/<form>/reader.html`。
- 运行数据：`http://127.0.0.1:8765/runs/<run_id>`（Live SSE / Trace / Stats；运行中 SSE 增量更新，结束后同一页复盘；没有 Story/说人话层）；`/runs` 是最近 runs + p50/p95/tokens/error/checks/grounding 看板；预览页右上/页脚有“运行数据”链接；`get_run.trace` 返回摘要；`start_workflow`/`resume_workflow` 返回 `trace_url`。
- 聊天 turn 入口：`client-ui.patch` 渲染一张消息级运行卡（轮询 `/api/card`）和右侧预览抽屉；不贴裸 URL、不显示原始 JSON；运行详情跳 `/runs/<run_id>`。
- 公众号复制页：`.../wechat.html`（“复制正文”不含 H1 标题；每张图有“复制图片/下载”）；小红书导入包：`.../xhs_export/`（阅读页可复制标题/正文/标签和每张卡）；PDF：`.../article.pdf`。
- P2 收口（2026-11-07）：`get_run` 返回 `review_status`（draft/stale/approved）；未验收显示“草稿”；typeset 失败返回 `typeset_errors` 且状态 `partial`；重新 typeset 会把旧验收标 stale。

## 6. 已知问题

- LibreChat 默认 UI 仍是通用 chat；运行卡/Run Detail/SSE 已接；成本面板/完整模型配置 UI 未做。
- 首页模型配置提示目前指向 `.env`，没有真正的设置页；这是“先留口子”。
- `npm run backend` 会报 `[schedules] scheduler NOT started`；单机不影响聊天，设置 `SCHEDULES_SINGLE_PROCESS=true` 可消掉（未验证）。
- Node engine warning：升级到 22.18+ 或 24 更稳。
- 某些 npm 解析会漏 `unrun`，前端 build 报缺模块时：`npm install unrun --save-dev` 再 `npm run frontend`。
- MongoDB 用 `mongodb-memory-server`，进程重启后用户/agent/会话可能丢失；按 §4 重建 agent。
- 预览服务只监听 127.0.0.1；公网部署前加鉴权/限流/成本上限。
- 小红书标题钩子/第一人称亲历是内容层待改；公众号数字偏多/缺图表也是内容层，不在排版层解决。
- P4 deterministic + grounding 已接（本地 `--gate`）；无 judge 校准、pass^k、CI。
