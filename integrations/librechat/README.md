# LibreChat P1/P2 integration

> 状态：2026-11-06 P1 原型已跑通；2026-11-07 P2 排版/导出/UI 已接。LibreChat 是外部 clone，不 vendored 进本仓库；这里放可复现配置。
> 目标：聊天 → 计划卡 → 一次 writer → 聊天内预览/导出 → 用户验收。缓存内容，不重跑视频。
> 产品定义：[docs/product-v1-chat-studio.md](../../docs/product-v1-chat-studio.md)；架构：[architecture.md](../../architecture.md)。

## 1. 本地环境（已验证）

- LibreChat `v0.8.9-rc1`（MIT），clone 在 `D:/luno_external/librechat`。
- Node `v22.14.0`（LibreChat 部分包声明 `^22.18.0 || >=24`，有 engine warning；当前 build/run 可通过）。
- MongoDB 用 `mongodb-memory-server` 本地进程，不装 MongoDB 服务。
- Python 用项目 conda 环境 `D:/anaconda/envs/myagent/python.exe`（3.11.14）。
- 预览服务：`facet_studio.preview_server`（FastAPI/uvicorn，127.0.0.1:8765）。
- MCP：`facet_studio.mcp_server`（FastMCP stdio）。

## 2. 一次性准备

```bash
# 1) clone + install + build（外部目录）
cd D:/luno_external
git clone --depth 1 https://github.com/danny-avila/LibreChat.git librechat
cd librechat
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
cd D:/luno_external/librechat && node scripts/dev-mongo.cjs

# B. 预览服务
cd <project> && PYTHONPATH=src python -m facet_studio.preview_server

# C. LibreChat
cd D:/luno_external/librechat && npm run backend
# open http://localhost:3080
```

## 4. Agent 配置

在 LibreChat 里创建一个 Agent（也可用 API）：

- name: `Facet Studio`
- provider: `DeepSeek`
- model: `deepseek-flash`
- artifacts: `default`
- tools（MCP `facet_studio`）：
  - `list_sources_mcp_facet_studio`
  - `resolve_source_mcp_facet_studio`
  - `compile_content_mcp_facet_studio`
  - `plan_article_mcp_facet_studio`
  - `write_form_mcp_facet_studio`
  - `typeset_article_mcp_facet_studio`
  - `get_run_mcp_facet_studio`
  - `review_artifact_mcp_facet_studio`
- instructions: 见 [agent-instructions.md](agent-instructions.md)
- conversation starters: 由外部 clone 的 `ConversationStarters.tsx` 在 agent name = `Facet Studio` 时替换为三张通用引导卡（输入视频 / 选择内容 / 告诉偏好）+ 模型配置提示，不使用某条具体 BV。

## 4.1 外部 clone 的 P2 修改（不做 vendored）

LibreChat clone 里只改主题/展示层，不改核心 pipeline：

- `client/src/utils/toolLabels.ts`：`FACET_MCP_TOOL_LABELS` 把 8 个 MCP 工具映射成中文动作名（查看来源/读取视频/规划/写作/排版/运行数据/验收）。
- `client/src/components/Chat/Messages/Content/ToolCall.tsx`：使用中文动作名；Facet 工具不再显示“来自 facet_studio”。
- `client/src/components/Chat/Input/ConversationStarters.tsx`：三张引导卡 + 模型配置提示。
- `client/index.html`、`client/src/locales/zh-Hans/translation.json`：品牌/标题/中文 UI。
- `librechat.yaml`：`facet-studio` 暖纸主题、`facet_studio` MCP、欢迎语。
- 改完 client 后：`npm run frontend`，再重启 `npm run backend`（否则可能白屏/旧 chunk）。

补丁文件：[patches/client-ui.patch](patches/client-ui.patch)。在新 clone 上应用：

```bash
cd D:/luno_external/librechat
git apply <project>/integrations/librechat/patches/client-ui.patch
npm run frontend
```

补丁只含 5 个展示层文件；`librechat.yaml` 主题/MCP 配置用 `librechat.yaml.example`，不放进 patch。

## 5. P1/P2 验收

已跑通：

- BV17 → 公众号：`runs/product_v1/20261106T131015Z_BV17DHC6CELr_wechat_article/`（2767 字 / 5 图；原 approved，2026-11-07 重排版后标 stale，需重新验收）。
- BV1ix → 小红书：`runs/product_v1/20261106T132229Z_BV1ixpd6GENc_xiaohongshu_note/`（999 字 / 3 图）。
- 完整 Agent 流程 → 小红书（2026-11-07）：`runs/product_v1/20261107T032530Z_BV17DHC6CELr_xiaohongshu_note/`（1,274 字 / 6 图 / 5 标签 / 6 张 3:4 PNG）。
- 单独 typeset 验证 → 小红书：`runs/product_v1/20261107T031556Z_BV17DHC6CELr_xiaohongshu_note/`（1,172 字 / 2 图 / 5 标签 / 2 张 3:4 PNG）。
- 深度总结 → PDF：`runs/product_v1/smoke_long_pdf/long_article/article.pdf`（9 页；封面/目录/正文已人工检查）。
- 工具调用：`resolve_source → plan_article → write_form → typeset_article → get_run`；人工 `review_artifact` 写 `publish_review.json`。
- 预览：`http://127.0.0.1:8765/runs/<run_id>/<form>/reader.html`。
- 公众号复制页：`.../wechat.html`（“复制正文”不含 H1 标题）；小红书导入包：`.../xhs_export/`；PDF：`.../article.pdf`。
- P2 收口（2026-11-07）：`get_run` 返回 `review_status`（draft/stale/approved）；未验收显示“草稿”；typeset 失败返回 `typeset_errors` 且状态 `partial`；重新 typeset 会把旧验收标 stale。

## 6. 已知问题

- LibreChat 默认 UI 仍是通用 chat；完整运行面板/成本面板是 P3。
- 首页模型配置提示目前指向 `.env`，没有真正的设置页；这是“先留口子”。
- `npm run backend` 会报 `[schedules] scheduler NOT started`；单机不影响聊天，设置 `SCHEDULES_SINGLE_PROCESS=true` 可消掉（未验证）。
- Node engine warning：升级到 22.18+ 或 24 更稳。
- 某些 npm 解析会漏 `unrun`，前端 build 报缺模块时：`npm install unrun --save-dev` 再 `npm run frontend`。
- MongoDB 用 `mongodb-memory-server`，进程重启后用户/agent/会话可能丢失；按 §4 重建 agent。
- 预览服务只监听 127.0.0.1；公网部署前加鉴权/限流/成本上限。
- 小红书标题钩子/第一人称亲历是内容层待改；公众号数字偏多/缺图表也是内容层，不在排版层解决。
- 评测未做；按 [docs/jd-mapping-2026-11.md](../../docs/jd-mapping-2026-11.md) §4 预留。
