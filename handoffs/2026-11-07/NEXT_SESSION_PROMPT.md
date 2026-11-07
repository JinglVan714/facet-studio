# 2026-11-07 交接：Facet Studio P1/P2 快照（不是方向指令）

> 接手前先读这份快照，再自己看代码、产出、用户反馈，自己判断问题与下一步。**不要因为已有代码、文档、测试、runs 就默认它对。本 session 的代码和文档也可能是错的、脏的。**
> 当前入口是这份文件；历史 handoff 只作背景，不是方向指令。

## 0. 项目是什么

Facet Studio 是一个**聊天式内容工作台**：用户给一条视频（BV 号 / B 站链接 / 本地路径）+ 写作要求，Agent 按需写**一种**形态（深度总结 / 公众号 / 小红书），在聊天里预览、修改、验收。

- **不是** bundle 工厂、作品集、架构 demo。
- 一个产物一次 writer；Lead Planner 只编排，不写正文；没有 editor/checker/草稿/repair 链。
- Writer 不知道来源；只拿到“这件事的完整内容”；不核验世界、不做百科。
- 用户人工验收是唯一发布门；测试绿/跑通不算通过。
- 目标壳：LibreChat（MIT）+ MCP + LangGraph + 排版/导出 + 人工验收。
- 当前代码：substrate v1（冻结）+ writing_v4 写作引擎 + **P1/P2 产品原型**（LibreChat / MCP / preview / review / 公众号 HTML / 小红书图集 / PDF）。

## 1. 先认知：读什么，背什么

### 1.1 只读顺序（不要先翻历史）

1. [CLAUDE.md](../../CLAUDE.md) — 入口与当前边界。
2. [docs/product-v1-chat-studio.md](../../docs/product-v1-chat-studio.md) — 产品定义/用户怎么用/UI/数据分层/路线。
3. [architecture.md](../../architecture.md) §0–§9 — 目标产品架构、组件、当前代码 vs 目标；文末附录是 v3 机会地图，**不是当前实现**。
4. [docs/writing-v5-architecture.md](../../docs/writing-v5-architecture.md) — 当前写作引擎（writing_v4）：planner/orchestrator/writer/skills/tools/bundle。
5. [docs/jd-mapping-2026-11.md](../../docs/jd-mapping-2026-11.md) — 2026 JD 真实含义、产品 consumer、评测口径。
6. [docs/reuse-stack-2026-11.md](../../docs/reuse-stack-2026-11.md) — LibreChat / MCP / LangGraph / Pandoc / Tectonic / Playwright 的复用与 license。
7. [STATE.md](../../STATE.md) + [HANDOFF.md](../../HANDOFF.md) — 当前快照/接手点（注意可能被本 session 污染）。
8. [docs/writing-rebuild-brief.md](../../docs/writing-rebuild-brief.md) §2（好 writing）+ §3（开发纪律）；[AGENTS.md](../../AGENTS.md) 全局护栏。§5 开发纪律不要改。

需要评测细节时才读 `runs/_reader_test_2026-11-03/reader_pack/评价方法.md` / `5个persona.md`；**不跑 30 judge**。

### 1.2 开发方法/纪律（要背下来）

- **产品优先**：先问“这是产品行为还是调试/作品集行为”。不把架构页/评测页放进产品导航；bundle 是内部调试产物，产品默认按需一种形态。
- **一步一个环节**：每步先说输入/输出/下游消费/失败形态；有界；失败/partial/unknown 显式；不静默截断。
- **证据优先**：视频事实/数字/引语/说话人只来自 substrate evidence；模型知识只解释/类比/组织。写作层保证“视频有就写，没有就不写”，不核实世界。
- **Writer 是产品，检查是地板**：先写得好；不要用 validator、词表、规则怪谈、多 stage 去“保证”质量。一次修复，不做无限“再修一轮看看”。
- **严禁单例**：skill/文档/代码里不能出现某个视频/产品/人物的具体内容、标题、台词、claim；每条规则必须由 ≥2 视频/文体或通用写作原则支持；例子匿名。
- **不按单篇调参**；不手改单篇文章；同 request + 盲评才叫测试。
- **用户人工验收是唯一发布门**；测试绿、跑通、模型说好都不算通过。
- **数据分层**：用户 run 数据（trace/token/cost/status）、开发评测数据、简历数据分开；评测先预留，不伪造 reader test/A-B。
- **复用优先**：能复用就复用；嵌入代码优先 MIT/BSD/Apache；AGPL/BUSL 只作设计参考，除非用户同意合规。
- **禁止**：恢复旧 supervisor/demo/词表/P1 两段式；跑 30 judge；自动 commit/push/publish；读 `data/cookies/`；改冻结的 substrate v1。
- **部署后置**：先本地跑通；公网前加鉴权/限流/成本上限。

### 1.3 思考方法

- 先看**用户实际会怎么用**，再看代码；不要从架构图倒推需求。
- 先找**最小闭环**：一条视频 → 一种形态 → 计划卡 → 一次 writer → 预览/导出 → 验收。
- 先问**这个数字/结论有没有证据**；没有就标 unknown/partial，不编。
- 先问**这是不是单例适配**；如果是，退回通用层或记录为待办。
- 先问**下一步的验收是什么**；没有验收标准就不算任务。

## 2. 当前快照（事实，不是质量结论）

- 分支 `writing-rebuild`；正式基线 commit `2f8faea`；工作树有大量未提交改动；**未 commit/push**。
- **P1/P2 原型已跑通**：LibreChat + MCP + preview + `review_artifact` + 公众号复制 HTML / 小红书 3:4 图集 + 导入包 / Tectonic PDF。
- 8 个 MCP 工具：`list_sources`、`resolve_source`、`compile_content`、`plan_article`、`write_form`、`typeset_article`、`get_run`、`review_artifact`。
- 三种形态：`long_article`（深度总结）/ `wechat_article`（公众号）/ `xiaohongshu_note`（小红书）。短视频脚本暂不做。
- 测试：**564 passed**（2026-11-07）。
- 外部 LibreChat clone：`D:/luno_external/librechat`（v0.8.9-rc1）；展示层补丁已导出到 [integrations/librechat/patches/client-ui.patch](../../integrations/librechat/patches/client-ui.patch)。
- 本地服务（本轮结束时在跑）：Mongo `127.0.0.1:27017`（mongodb-memory-server）、preview `127.0.0.1:8765`、LibreChat `localhost:3080`。
- 启动/配置：[integrations/librechat/README.md](../../integrations/librechat/README.md)。

### 2.1 本轮（2026-11-07）做了什么

- 全项目更名为 **Facet Studio**：包 `src/facet_studio`、品牌、文档、`FACET_STUDIO_` 环境变量前缀；历史文档保留旧名 LunoGraph 并标注。
- 首页：三张通用引导卡（输入视频 / 选择内容 / 告诉偏好）+ 模型配置提示；不指定具体 BV。
- 工具 UI：8 个 MCP 工具显示中文动作名；Facet 工具不再显示“来自 facet_studio”。
- 小红书：顶部横滑 3:4 图集（封面钩子 → 关键帧）、标题/正文/标签；`xhs_export/` 输出 PNG + title/body/tags + manifest + README；默认生成 3–6 个内容话题标签；`## 配图` 第一张作封面；无图时纯文字封面卡；重 typeset 清理旧 PNG。
- 公众号：`wechat.html` 内联样式 + “复制正文”按钮。
- 深度总结：Pandoc → Tectonic PDF（封面/目录/正文/图注），`article.pdf` 可下载；`pypdf` 读页数做结构校验。
- 文档同步：STATE / HANDOFF / CLAUDE / README / AGENTS / architecture / product / UI / reuse / docs index / integrations。

### 2.2 本轮证据

- 完整 Agent 流程（LibreChat → plan → write → typeset）→ 小红书：
  `runs/product_v1/20261107T032530Z_BV17DHC6CELr_xiaohongshu_note/`
  （1,274 字 / 6 图 / 6 张 3:4 PNG / 5 标签 / 2 次模型调用 / 16,208 tokens）
- 单独 typeset 验证 → 小红书：
  `runs/product_v1/20261107T031556Z_BV17DHC6CELr_xiaohongshu_note/`
- 公众号复制页：
  `runs/product_v1/20261106T131015Z_BV17DHC6CELr_wechat_article/wechat_article/wechat.html`
- 深度总结 PDF：
  `runs/product_v1/smoke_long_pdf/long_article/article.pdf`（9 页；封面/目录/正文已人工检查）

## 3. 本轮自检：已修 / 仍存疑

### 3.1 本轮已修（写进交接，避免重复踩）

- `_parse_xhs_note` 的 source 行被 `## 标签` 分支吞掉 → 调整判断顺序，source.txt 现在能写出。
- `xhs_export` 重 typeset 会残留旧 PNG / 旧 source.txt → 生成前清理 `*.png`，无 source 时删除 `source.txt`。
- 小红书无图时封面文案丢失 → 增加纯文字封面 slide（`.slide.cover.text-only`）。
- 横滑图集首卡左边缘被 scroll-snap 吃掉 → 增加 `scroll-padding-left:22px`。
- PDF 中文可提取性检查用了 AGPL 的 PyMuPDF → 改为 BSD 的 `pypdf` 只读页数；中文可搜索性人工打开 PDF 检查。
- `resolve_source` docstring / XHS skill 里的具体视频/烹饪例子 → 改成通用占位，避免单例偏置。
- Pandoc/Tectonic 只认硬编码路径 → 增加 `shutil.which` 回退，仍可用 `FACET_STUDIO_PANDOC` / `FACET_STUDIO_TECTONIC` 覆盖。
- LibreChat 展示层补丁只存在于外部 clone → 导出 `patches/client-ui.patch`，新 clone 可 `git apply`。

### 3.2 仍然存疑 / 已知问题（新 session 要自己核对）

1. **小红书标题**：钩子偏弱，个别标题把演示写成第一人称亲历（如“我用一句话搜出了蝙蝠”）。用户明确说“标题最后改”，本轮未修；不要按单篇调参。
2. **公众号正文**：数字偏多、图表不足、不够精炼；属于内容/写作认知层，本轮只做版式，未动。
3. **`_render_xhs` 与 `_parse_xhs_note` 有重复解析逻辑**：后续改 sidecar 格式时容易分叉；可考虑合并，但不要为合并而引入单例逻辑。
4. **本地路径依赖**：Pandoc/Tectonic/Playwright 默认路径仍是本机路径；已支持环境变量与 `which` 回退，但新机器要显式配置。
5. **模型配置入口**：首页只有 `.env` 提示，没有真正设置页；用户说“先留口子”。
6. **MongoDB 是 mongodb-memory-server**：进程重启后用户/agent/会话可能丢失；需要按 README 重建 agent。
7. **没有自动化端到端测试**：P2 的 UI/agent 流程是手工验证；现有 564 个测试主要是单元/集成，不覆盖 LibreChat 浏览器流。
8. **预览服务只监听 127.0.0.1**：公网部署前必须加鉴权/限流/成本上限；小红书“导入包目录”是本地 Windows 路径，部署后要改成可下载 URL。
9. **`runs/product_v1/_*.json` 里还有旧 `lunograph` 工具名**：历史证据，不是当前实现；不要当基线。
10. **P2 只做了“能看/能复制/能下载/能导入”**：没有做真实读者评测；不要用测试绿代替质量结论。

## 4. 下一步怎么想（不是指令）

先做一次**独立核对**，不要直接开写：

1. 跑全量测试，确认 564 passed；打开 UI，确认首页/工具调用/三种产物可看。
2. 选一条**没在本轮用过**的缓存视频，走一遍按需形态（不要 bundle），检查计划卡、writer、typeset、验收是否还成立。
3. 检查 `patches/client-ui.patch` 能否在干净 clone 上应用；检查 `librechat.yaml.example` 的 MCP/主题配置是否完整。
4. 检查本轮自检里的 10 个存疑项，判断哪些是 bug、哪些是待办、哪些是用户明确后置。

然后按“产品价值/风险/依赖”排序，给用户 2–3 个方向，让用户裁决。候选（不预设）：

- **A. P2 验收收口**：只修 P2 真 bug + 用户验收；不碰内容层。
- **B. 内容质量层**：小红书标题、公众号数字/图表；用户已说标题最后改，先别自作主张。
- **C. P3 LangGraph + HITL + 观测**：StateGraph、checkpoint、stream、interrupt、trace/token/cost 面板；这是 architecture 里的下一步。
- **D. 模型配置 UI / 部署**：设置页、Docker、鉴权/限流/成本上限；产品化前置。
- **E. P4 评测**：capability/regression、deterministic checks、trajectory、judge 校准、pass@k/pass^k；产品稳定后再做，不要 30 judge。
- **F. P5 视频转录**：最后做；现阶段用缓存内容。

**本 session 的判断（仅供参考）**：P3 是最自然的下一步，但先做一轮 P2 独立验收；在用户确认前不要开始评测/转录，也不要把 P2 的“跑通”当成“验收通过”。

## 5. 边界 / 不要做

- 不恢复旧 supervisor/demo/词表/P1 两段式；不跑 30 judge；不伪造 reader test/A-B。
- 不按单篇调参；不手改单篇文章；active skill 不出现具体视频/产品/人物。
- 不自动 commit/push/publish；不读 `data/cookies/`；不改 substrate v1。
- 不把 bundle 当产品默认输出；不把架构页/评测页放进产品导航。
- 不把 `STATE`/`HANDOFF`/`README`/本文件当干净真相；先看代码、runs、用户反馈，自己核对。

## 6. 常用命令

```bash
# 全量测试
cd D:/秋招/个人作品/1023视频写作
PYTHONPATH=src PYTHONUTF8=1 D:/anaconda/envs/myagent/python.exe -m pytest tests -q

# 本地启动（先改脚本顶部路径）
powershell -ExecutionPolicy Bypass -File scripts/start_p1.ps1

# 或手动
cd D:/luno_external/librechat && node scripts/dev-mongo.cjs
cd D:/秋招/个人作品/1023视频写作 && PYTHONPATH=src D:/anaconda/envs/myagent/python.exe -m facet_studio.preview_server
cd D:/luno_external/librechat && npm run backend
# http://localhost:3080
```

外部 clone 展示层补丁：

```bash
cd D:/luno_external/librechat
git apply D:/秋招/个人作品/1023视频写作/integrations/librechat/patches/client-ui.patch
npm run frontend
# 再重启 backend
```

## 7. 接手清单

- [ ] 按 §1.1 读完当前文档；确认自己能用一句话说清“产品是什么/不是什么”。
- [ ] 复述 §1.2 的纪律，特别是：一次 writer、无 editor/checker、人工验收、严禁单例、不跑 30 judge、不 commit/push。
- [ ] 跑测试；打开 UI；看三种产物和 run 证据。
- [ ] 检查 §3.2 的存疑项，给用户一份“问题/风险/待办”清单。
- [ ] 给用户 2–3 个下一步方向 + 验收标准，等用户裁决；不要直接开写。
