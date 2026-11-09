# Facet Studio — 聊天式内容工作台

把一条视频变成可发布的文章/笔记：用户在聊天框里给视频和写作要求，Agent 按需写一种形态（深度总结 / 公众号 / 小红书），在聊天里预览、修改、验收。

> **2026-11-09 收尾轮**：产品 UI 收口——聊天不再倒 JSON，Facet 工具结果显示为成品卡（预览/公众号/PDF/运行数据）；阅读页按形态显示标签，宽表格可横向滚动；Run Detail 区分“自动通过”和“用户验收”，看板缺 `llm_calls.jsonl` 时显示 —；视觉审计修复旧格式 `图示 N` 漏检，并显示候选/未通过原因；导出补 B 站来源行。最新验收候选：`20261109T072111Z_BV1B5411A7ax_wechat_article`（猫视频，6 候选 0 通过、2,194 字、0 关键帧）和聊天 E2E `20261109T075145Z_BV17DHC6CELr_wechat_article`（2,575 字 / 1 SVG），均待人工验收。测试 608 passed。
>
> **2026-11-08 上一轮状态**：产品 v1 已定义（[docs/product-v1-chat-studio.md](docs/product-v1-chat-studio.md)）；目标壳是 **LibreChat + MCP + LangGraph + 排版/导出**。P1/P2 产品原型、P3 workflow 原型、P4 deterministic/grounding harness、P5 证据层均已接；**P5 新视频下载 + DashScope ASR（Qwen-Audio 3.1）+ VLM + content + workflow 已端到端跑通**（BV1brgs6mE7a，2 分钟）；**视觉策略 + deepseek-flash 视觉审计**已接：关键帧极紧、图注默认不加、SVG/表格优先。P4 10/10 cases、contract 10/10、trajectory 30/30；3 个新 machine run 待用户验收。详见 [architecture.md](architecture.md) §4、[docs/visual-strategy-2026-11.md](docs/visual-strategy-2026-11.md)、[integrations/librechat/README.md](integrations/librechat/README.md)、[docs/evidence-layer-2026-11.md](docs/evidence-layer-2026-11.md)、[docs/evidence-2026-11.md](docs/evidence-2026-11.md)。
> 三种形态：深度总结（long_article）/ 公众号（wechat_article）/ 小红书（xiaohongshu_note）。短视频脚本暂不做。
> **bundle 是内部/调试产物，不是产品默认输出。** 产品按需生成一种形态；用户 run 数据、开发评测数据、简历数据分开。

## 产品一句话

用户：用 BV17DHC6CELr 写一篇公众号，给普通技术读者，2500 字左右，语气克制，重点讲“分数为什么低但排名可靠”。

Agent：确认来源/形态/读者/长度 → 读取内容（缓存）→ 计划卡 → 一次 writer → 排版 → 聊天内预览 → 修改 / 导出 / 验收。

**不是**：作品集网站；一次生成所有形态的 bundle 工厂；架构/评测演示页；自动发布工具；editor/checker 多轮改稿链。

## 仓库边界（公开仓库必读）

- `data/`（视频/帧/ASR/cookies）、`runs/`（用户 run 产物）、`vendor/`（证据层备份）**不入库**；仓库只含代码、skill、文档和示例文章。
- 没有 API key / 视频时，单元与集成测试仍可运行；完整生成需要自备 `.env` 和视频。
- `deliverables/writing-skill/` 是早期 articles-only 示例，**不是当前产品默认输出**；公开分发前请自行确认素材/图片权利。
- 不读 `data/cookies/` 内容；需要登录态时只把路径传给 yt-dlp。
- 不自动 commit/push/publish；用户人工验收是唯一发布门。

## 先读（顺序）

1. [docs/product-v1-chat-studio.md](docs/product-v1-chat-studio.md) — 产品定义/用户怎么用/UI/数据分层/路线。
2. [architecture.md](architecture.md) §0–§9 — 目标架构、组件、当前代码 vs 目标、路线；文末附录是 v3 机会地图，不是当前实现。
3. [docs/writing-v5-architecture.md](docs/writing-v5-architecture.md) — 当前写作引擎（writing_v4）。
4. [docs/jd-mapping-2026-11.md](docs/jd-mapping-2026-11.md) — 2026 JD 真实含义与评测口径。
5. [docs/reuse-stack-2026-11.md](docs/reuse-stack-2026-11.md) — LibreChat/MCP/LangGraph/排版/卡片复用与 license。
6. [docs/evidence-layer-2026-11.md](docs/evidence-layer-2026-11.md) — P5 证据层链路/配置/已验证/未验证。
7. [evals/product_v1/README.md](evals/product_v1/README.md) — P4 deterministic + grounding；不评 writing 质量。
8. [STATE.md](STATE.md)、[HANDOFF.md](HANDOFF.md) — 当前快照/接手点。
9. 方法/纪律：[docs/writing-rebuild-brief.md](docs/writing-rebuild-brief.md) §2/§3、[AGENTS.md](AGENTS.md) §5。

## 当前代码

- `src/facet_studio/writing_v3/`：substrate v1（冻结）：transcript / sentences / frames / OCR / content manuscript。
- `src/facet_studio/writing_v4/`：content manuscript、skill loader、一次 writer、planner/orchestrator、SVG、bundle、`visual_audit.py`（deepseek-flash 视觉审计候选关键帧）。
- `src/facet_studio/runtime/`：RunStore / TaskPlan / ToolRegistry / WorkingMemory / ArtifactBoard / Decision / Trace / Eval。
- `src/facet_studio/mcp_server.py`：FastMCP **12 tools**（ingest / list / resolve / compile / plan / write / typeset / get_run / review / start_workflow / resume_workflow / get_workflow）。
- `src/facet_studio/workflow.py`：LangGraph StateGraph（intake → plan → approval → write → typeset → review）+ SQLite checkpoint + interrupt + `workflow.json` trace。
- `src/facet_studio/preview_server.py`：FastAPI reader 预览（127.0.0.1:8765）。
- `src/facet_studio/evidence_layer/`：下载/抽帧/ASR/VLM/substrate；`src/facet_studio/ingest.py`：新视频 → `content.md + figures`。
- `src/facet_studio/evals/`：deterministic product checks + grounding candidate audit。
- `integrations/librechat/`、`integrations/xhs/`、`integrations/pdf/`：产品壳配置、3:4 卡片、Pandoc/Tectonic PDF（SVG 图先用 Playwright 渲染成 PNG）。
- `skills/writing/`：video-article（long_article core）、wechat-article（extends core）、xiaohongshu-note、bundle-planner。

## 运行

```bash
# 1) Python 依赖（项目使用 conda 环境 myagent；Python 3.11+）
pip install -r requirements.txt

# 2) 配置
cp .env.example .env
# 填入 DEEPSEEK_API_KEY / DASHSCOPE_API_KEY；可选 Langfuse、成本费率、外部工具路径

# 3) 测试（不依赖 data/ 或 runs/）
PYTHONPATH=src PYTHONUTF8=1 python -m pytest tests -q

# 4) MCP server（stdio；LibreChat 配置见 integrations/librechat/README.md）
PYTHONPATH=src python -m facet_studio.mcp_server

# 5) 预览服务
PYTHONPATH=src python -m facet_studio.preview_server
```

完整产品壳（LibreChat + Mongo + preview）见 [integrations/librechat/README.md](integrations/librechat/README.md)；Windows 一键启动：`scripts/start_p1.ps1`（用 `FACET_STUDIO_PROJECT_ROOT` / `FACET_STUDIO_LIBRECHAT_ROOT` / `FACET_STUDIO_PYTHON` 配置）。

### 写作引擎 CLI（调试/离线）

```bash
PYTHONPATH=src python -m facet_studio.writing_v4.run_form \
  --video-id BV17DHC6CELr \
  --content runs/writing_rebuild_2026-11-04/BV17DHC6CELr/content_final_v3/content.md \
  --out-dir runs/writing_v5/BV17DHC6CELr/wechat_article \
  --skill-dir skills/writing/wechat-article \
  --request "写一篇公众号文章：让没看过内容的人快速理解这件事；一个控制性 idea；数字少而有效；图和表服务理解。" \
  --source-json data/BV17DHC6CELr/source.json
```

### 新视频接入（P5）

```bash
PYTHONPATH=src python -c "from facet_studio.ingest import ingest_source; print(ingest_source('https://www.bilibili.com/video/BV...', profile='fast'))"
# 默认 content-only：抽帧/ASR/VLM → content.md；不跑 contract/L1。
# 需要完整证据层时加 include_evidence=True。
# 长视频先用 CLI；MCP ingest 是同步调用，LibreChat 默认 300s timeout，没有后台任务。
# ASR：DashScope qwen-audio-3.1-asr-flash-streaming；VLM：qwen3.8-27b。
```

### 评测

```bash
PYTHONPATH=src python -m facet_studio.evals.product --cases evals/product_v1/cases.json --out evals/product_v1/reports
PYTHONPATH=src python -m facet_studio.evals.grounding --cases evals/product_v1/cases.json --out evals/product_v1/reports
```

评测只读 run artifacts；不评 writing 质量、不伪造 pass@k；人工验收仍是唯一发布门。

## 已知边界

- **一个产物一次 writer**：没有草稿、editor、checker、词表、核实；Lead Planner 只编排。
- **Writer 不知道来源**：只拿到「这件事的完整内容」；正文不出现来源/工作痕迹。
- **不核验内容本身**：不挑内容错、不做百科；只处理已有内容 + 用户补充/未来联网调研。
- **不写死数量/数字**：字数、H2 数、段落数都跟 request/内容相关；request 优先，没 request 用默认。
- **active skill 不出现具体视频/产品/人物**；例子匿名；≥2 视频/文体复现才改通用层；不按单篇调参。
- **用户验收**：质量和架构由用户判断；测试绿/跑通都不等于通过。
- **未做**：公网部署/鉴权/限流/成本上限、完整模型配置 UI、用户画像记忆、3 个新 machine run 的用户验收、P4 pass^k/多 trial（回归门禁 `--gate` 已接）。
- 不自动发布；不 commit/push；不改 substrate；不读 `data/cookies/`。
- 复用优先；嵌入代码优先 MIT/BSD/Apache；AGPL/BUSL 只作设计参考，除非用户同意合规。
