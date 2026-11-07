# Facet Studio — 聊天式内容工作台

把一条视频变成可发布的文章/笔记：用户在聊天框里给视频和写作要求，Agent 按需写一种形态（深度总结 / 公众号 / 小红书），在聊天里预览、修改、验收。

> **2026-11-07 当前状态**：产品 v1 已定义（[docs/product-v1-chat-studio.md](docs/product-v1-chat-studio.md)）；目标壳是 **LibreChat + MCP + LangGraph + 排版/导出**。**P1/P2 原型已跑通**：LibreChat + MCP server + preview server + `review_artifact` + 公众号复制 HTML / 小红书 3:4 图集 + 导入包 / Tectonic PDF；LangGraph/评测未接。见 [integrations/librechat/README.md](integrations/librechat/README.md)。bundle 是内部/调试产物，不是产品默认输出。
> 三种形态：深度总结（long_article）/ 公众号（wechat_article）/ 小红书（xiaohongshu_note）。短视频脚本暂不做。
> 不把架构页/评测页放进产品；用户 run 数据、开发评测数据、简历数据分开。

## 产品一句话

用户：用 BV17DHC6CELr 写一篇公众号，给普通技术读者，2500 字左右，语气克制，重点讲“分数为什么低但排名可靠”。

Agent：确认来源/形态/读者/长度 → 读取内容（缓存）→ 计划卡 → 一次 writer → 排版 → 聊天内预览 → 修改 / 导出 / 验收。

**不是**：作品集网站；一次生成所有形态的 bundle 工厂；架构/评测演示；自动发布工具。

## 先读（顺序）

1. [docs/product-v1-chat-studio.md](docs/product-v1-chat-studio.md) — 产品定义/用户怎么用/UI/数据分层/路线；UI 细节见 [docs/ui-design-2026-11.md](docs/ui-design-2026-11.md)。
2. [architecture.md](architecture.md) §0–§9 — 目标架构、组件、当前代码 vs 目标、路线；文末附录是 v3 机会地图，不是当前实现。
3. [docs/writing-v5-architecture.md](docs/writing-v5-architecture.md) — 当前写作引擎（writing_v4）。
4. [docs/jd-mapping-2026-11.md](docs/jd-mapping-2026-11.md) — 2026 JD 真实含义与评测口径。
5. [docs/reuse-stack-2026-11.md](docs/reuse-stack-2026-11.md) — LibreChat/MCP/LangGraph/排版/卡片复用与 license。
6. [STATE.md](STATE.md)、[HANDOFF.md](HANDOFF.md) — 当前快照/接手点。
7. 方法/纪律：[docs/writing-rebuild-brief.md](docs/writing-rebuild-brief.md) §2/§3、[AGENTS.md](AGENTS.md) §5。
8. 历史索引：[docs/README.md](docs/README.md)。

## 当前代码（写作引擎）

- `src/facet_studio/writing_v3/`：substrate v1（冻结）：transcript / sentences / frames / OCR / content manuscript。
- `src/facet_studio/writing_v4/`：
  - `content_manuscript` / `continuous_text` / `material_packet`：substrate → 连续内容稿。
  - `skills.py`：core + form layer skill loader（支持 `extends`）。
  - `writer.py` / `run_form.py`：单 form 路径：一次 writer + figures + SVG + title candidates + reader contract + source line + meta。
  - `planner.py` / `tools.py` / `orchestrator.py` / `run_bundle.py`：Lead Planner → TaskPlan → per-form writers → tools → bundle + trace。
  - `svg_pass.py`：占位符 → JSON 规格 → 本地确定性 SVG。
- `src/facet_studio/runtime/`：RunStore / TaskPlan / ToolRegistry / WorkingMemory / ArtifactBoard / Decision / Trace / Budget / Eval。
- `src/facet_studio/mcp_server.py`：P1/P2 MCP server（FastMCP）；`src/facet_studio/preview_server.py`：P1 reader 预览服务。
- `integrations/librechat/`：LibreChat 配置/启动/Agent instructions（P1/P2）；`integrations/xhs/`：Playwright 3:4 卡片；`integrations/pdf/`：Pandoc + Tectonic 模板。
- `skills/writing/video-article/`：深度总结 core（`long_article`）。
- `skills/writing/wechat-article/`：公众号 platform layer（`extends ../video-article`）。
- `skills/writing/xiaohongshu-note/`：小红书短版（一条主线覆盖整体）。
- `skills/writing/bundle-planner/`：内容包总编辑（只输出 JSON plan，不写正文）。
- `runs/writing_v5/`：当前运行产物；最新 bundle：`bundle_BV17_social_05/`、`bundle_BV1ix_social_04/`。
- `docs/substrate-v1-freeze.md`：substrate v1 接口；只读。

**未接**：LangGraph workflow、eval harness、视频转录、完整模型配置 UI；LibreChat/MCP/排版导出已有 P1/P2 原型。

## 运行（当前写作引擎）

```bash
PYTHONPATH=src python -m pytest -q

# 单 form（公众号）
PYTHONPATH=src python -m facet_studio.writing_v4.run_form \
  --video-id BV17DHC6CELr \
  --content runs/writing_rebuild_2026-11-04/BV17DHC6CELr/content_final_v3/content.md \
  --out-dir runs/writing_v5/BV17DHC6CELr/wechat_article \
  --skill-dir skills/writing/wechat-article \
  --request "写一篇公众号文章：让没看过内容的人快速理解这件事；一个控制性 idea；数字少而有效；图和表服务理解。" \
  --source-json data/BV17DHC6CELr/source.json

# 多 form bundle（内部/调试形态；产品默认按需一种）
PYTHONPATH=src python -m facet_studio.writing_v4.run_bundle \
  --video-id BV17DHC6CELr \
  --content runs/writing_rebuild_2026-11-04/BV17DHC6CELr/content_final_v3/content.md \
  --out-root runs/writing_v5 \
  --request-file runs/writing_v5/request_bundle.txt \
  --forms wechat_article,xiaohongshu_note \
  --source-json data/BV17DHC6CELr/source.json \
  --run-id bundle_BV17_social_05
```

## 产品原型（P1/P2 已跑通）

- **壳**：LibreChat（MIT）：chat、Agents、MCP、Artifacts、Trace Viewer、Token 统计。外部 clone 在 `D:/luno_external/librechat`；配置见 [integrations/librechat/README.md](integrations/librechat/README.md)。
- **服务**：`src/facet_studio/mcp_server.py`（FastMCP 8 tools）+ `src/facet_studio/preview_server.py`（FastAPI reader 预览）+ writing_v4 引擎。
- **已验证**：BV17 → 公众号（2767 字 / 5 图 / approved）；BV1ix → 小红书（999 字 / 3 图）；新 skill → 小红书（1,172 字 / 2 图 / 5 标签）；完整 Agent → 小红书（1,274 字 / 6 图 / 6 张卡片）；深度总结 → PDF（9 页）；`review_artifact` 写 `publish_review.json`。
- **启动**：`powershell -ExecutionPolicy Bypass -File scripts/start_p1.ps1`（先改脚本顶部路径）；详见 [integrations/librechat/README.md](integrations/librechat/README.md)。
- **未做**：LangGraph workflow、eval、视频转录、完整模型配置 UI。
- **路线**：P3 LangGraph + HITL + 观测 → P4 评测（先预留）→ P5 视频转录。

## 边界

- **一个产物一次 writer**：没有草稿、editor、checker、词表、核实；Lead Planner 只编排。
- **Writer 不知道来源**：只拿到「这件事的完整内容」；正文不出现来源/工作痕迹。
- **不核验内容本身**：不挑内容错、不做百科；只处理已有内容 + 用户补充/未来联网调研。
- **不写死数量/数字**：字数、H2 数、段落数都跟 request/内容相关；request 优先，没 request 用默认。
- **active skill 不出现具体视频/产品/人物**；例子匿名；≥2 视频/文体复现才改通用层；不按单篇调参。
- **用户验收**：质量和架构由用户判断；测试绿/跑通都不等于通过。
- **不加**：validator、词表、规则怪谈、30 judge、旧 supervisor/demo/P1 两段式。
- 不自动发布；不 commit/push；不改 substrate；不读 `data/cookies/`。
- 复用优先；嵌入代码优先 MIT/BSD/Apache；AGPL/BUSL 只作设计参考，除非用户同意合规。
