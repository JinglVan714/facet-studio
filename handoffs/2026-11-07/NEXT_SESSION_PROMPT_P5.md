# 2026-11-07 交接（P5 证据层迁移后）

> 接手前先自己看代码、产出、用户反馈；**不要因为已有代码/文档/测试/runs 就默认它对**。本文件是本轮结束时的快照，不是方向指令；旧 handoff 只作背景。
> 上一份同日入口是 [NEXT_SESSION_PROMPT.md](NEXT_SESSION_PROMPT.md)（P1/P2 快照，已被本文件取代，保留不改）。

## 0. 项目是什么

Facet Studio 是一个**聊天式内容工作台**：用户给一条视频（BV / B 站链接 / 本地路径）+ 写作要求，Agent 按需写**一种**形态（深度总结 / 公众号 / 小红书），在聊天里预览、修改、验收。

- **不是** bundle 工厂、作品集、架构 demo、自动发布工具。
- 一个产物一次 writer；Lead Planner 只编排，不写正文；没有 editor/checker/草稿/repair 链。
- Writer 不知道来源；只拿到“这件事的完整内容”；不核验世界、不做百科。
- 用户人工验收是唯一发布门；测试绿/跑通不算质量通过。
- 目标壳：LibreChat（MIT）+ MCP + LangGraph + 排版/导出 + 人工验收。
- 当前已经有的：writing_v4 引擎、P1/P2 产品壳、P3 workflow 原型、P4 deterministic/grounding harness、P5 证据层迁移。

## 1. 先认知：读什么、背什么

### 1.1 只读顺序

1. [CLAUDE.md](../../CLAUDE.md) — 入口/边界。
2. [docs/product-v1-chat-studio.md](../../docs/product-v1-chat-studio.md) — 产品定义/用户怎么用/UI/数据分层/路线。
3. [architecture.md](../../architecture.md) §0–§9 — 目标架构、组件、当前代码 vs 目标；文末附录是 v3 机会地图，不是当前实现。
4. [docs/writing-v5-architecture.md](../../docs/writing-v5-architecture.md) — 当前写作引擎（writing_v4）。
5. [docs/jd-mapping-2026-11.md](../../docs/jd-mapping-2026-11.md) — 2026 JD 真实含义、产品 consumer、评测口径。
6. [docs/reuse-stack-2026-11.md](../../docs/reuse-stack-2026-11.md) — LibreChat / MCP / LangGraph / Pandoc / Tectonic / Playwright 的复用与 license。
7. [docs/evidence-layer-2026-11.md](../../docs/evidence-layer-2026-11.md) — P5 证据层迁移、配置、已验证/未验证。
8. [evals/product_v1/README.md](../../evals/product_v1/README.md) — P4 deterministic + grounding 数据/报告；不评 writing 质量。
9. [STATE.md](../../STATE.md) + [HANDOFF.md](../../HANDOFF.md) — 当前快照/接手点（可能被上一轮污染，自己核对）。
10. [docs/writing-rebuild-brief.md](../../docs/writing-rebuild-brief.md) §2/§3 + [AGENTS.md](../../AGENTS.md) — 好 writing / 开发纪律/护栏；§5 开发纪律不要改。

需要评测细节时才读 `runs/_reader_test_2026-11-03/reader_pack/评价方法.md` / `5个persona.md`；不跑 30 judge。

### 1.2 开发方法/纪律（背下来）

- **产品优先**：先问“这是产品行为还是调试/作品集行为”。不把架构页/评测页放进产品导航；bundle 是内部调试产物，产品默认按需一种形态。
- **一个产物一次 writer**；Lead Planner 只编排；没有 editor/checker/草稿/repair 链；修改 = 新请求 + 新 writer。
- **Writer 不知道来源**；只拿到内容；不核验世界、不写“未证实/待核”、不做百科/论文/体检报告。
- **证据优先**：视频事实/数字/引语/说话人来自内容稿；模型知识只解释/类比/组织；不新增事实。
- **严禁单例**：skill/文档/代码不能出现某个视频/产品/人物的具体内容；每条规则 ≥2 视频/文体或通用写作原则支持；例子匿名。
- **不按单篇调参**；不手改单篇文章；同 request + 盲评才叫测试。
- **用户人工验收是唯一发布门**；测试绿、跑通、模型说好都不算通过。
- **不评 writing 质量**：用户明确说写作质量难评、不做人工/LLM 打分；P4 只测运行数据和 grounding / hallucination candidates。
- **数据分层**：用户 run 数据、开发评测数据、简历数据分开；评测先预留，不伪造 reader test/A-B。
- **复用优先**：LibreChat / MCP / LangGraph / Pandoc / Tectonic / Playwright；嵌入代码优先 MIT/BSD/Apache；AGPL/BUSL 只作设计参考。
- **禁止**：恢复旧 supervisor/demo/词表/P1 两段式；跑 30 judge；自动 commit/push/publish；读 `data/cookies/`；改冻结的 substrate v1。
- **部署后置**：先本地跑通；公网前加鉴权/限流/成本上限。
- **P5 边界**：证据层只是输入适配器；不把视频/证据层概念带进 writer；`content.md + figures` 是写作层唯一输入。

### 1.3 思考方法

- 先看用户实际会怎么用，再看代码；不要从架构图倒推需求。
- 先找最小闭环：一条视频 → 一种形态 → 计划卡 → 一次 writer → 预览/导出 → 验收。
- 先问这个数字/结论有没有证据；没有就标 unknown/partial，不编。
- 先问这是不是单例适配；如果是，退回通用层或记录为待办。
- 先问下一步的验收是什么；没有验收标准就不算任务。
- 评测只测可观察的东西：运行状态、产物存在、tokens/时延/错误、轨迹、grounding candidate；不给 writing 打分。

## 2. 当前快照（事实）

- 分支 `writing-rebuild`；最新 commit `6f3246d`；工作树有本轮交接文档更新（未提交）；**未 push**。
- 最近 commits：`6f3246d` P5 证据层迁移；`04cb6c5` grounding audit；`791d247` P4 deterministic harness；`48c13b4` P3 UI 验收；`98a558c` P3 UI/labels；`fd16e3e` workflow；`78a2a67` copy UI；`fba0200` P1/P2 + 视觉收口。
- 测试：**580 passed**（2026-11-07；含 MCP/排版/PDF/验收/视觉/workflow/eval/grounding/ingest）。
- 本地服务（本轮结束已停）：Mongo `mongodb-memory-server`、preview `127.0.0.1:8765`、LibreChat `localhost:3080`；重启见 [integrations/librechat/README.md](../../integrations/librechat/README.md)。
- 外部 LibreChat clone：`D:/luno_external/librechat`（v0.8.9-rc1）；`client-ui.patch` 已更新；frontend 已 rebuild；后端需重启后加载 12 tools。
- MCP 工具：12 个 = `ingest_source` / `list_sources` / `resolve_source` / `compile_content` / `plan_article` / `write_form` / `typeset_article` / `get_run` / `review_artifact` / `start_workflow` / `resume_workflow` / `get_workflow`。
- 三种形态：`long_article` / `wechat_article` / `xiaohongshu_note`；短视频脚本暂不做。
- P1/P2 已验收（用户“大致通过”）：BV13/BV17 公众号、BV17/BV1ix 小红书、smoke/第二篇长文 PDF 已记 approved（`runs/product_v1/**/publish_review.json`，不入库）。重新 typeset 会把旧验收标 stale。
- P3 workflow：`src/facet_studio/workflow.py`，StateGraph `intake → plan → approval → write → typeset → review`，SQLite checkpoint，plan/review interrupt，`workflow.json` stages/events/usage；真实 UI E2E 会话 `19e3aeb3-0854-549b-b18e-a37df12e8812` → run `20261107T132341Z_BV1B5411A7ax_xiaohongshu_note`（2 calls / 17,327 tokens / approved）。
- P4：`evals/product_v1/cases.json` + `src/facet_studio/evals/product.py` / `grounding.py`；7/9 cases 有 artifact（BV1ix long/wechat missing），deterministic 7/7、manual 7/7、planner trace 4/7；grounding 6 artifacts / 17 candidate flags（不是幻觉率，不评 writing 质量）；报告 `evals/product_v1/reports/`；`pass@1/pass@k = null`。
- P5：`src/facet_studio/evidence_layer/`（从 `知识底稿核心-clean` 迁移，路径适配环境变量）+ `src/facet_studio/ingest.py`；MCP `ingest_source`。链路：下载/本地登记 → 抽帧 + ASR → VLM + substrate → `content_manuscript` → `runs/writing_rebuild_2026-11-04/<vid>/content_final_v3/content.md + figures`。
- P5 验证：迁移备份 17 tests、`evidence_mcp --selftest` 对 `data/` 通过、`acquire_local` 成功、`run_ingest` 在缓存 metadata 上无模型复用通过、BV17 content 重建 4,213 字/10 图；**尚未真实跑新视频下载/ASR/VLM 端到端**。
- 备份：`vendor/evidence_core/` 是本地原始备份（gitignored，不入库；不要提交，不含 data/cookies）。集成副本在 `src/facet_studio/evidence_layer/`。
- 后续待修：见 [docs/backlog-2026-11.md](../../docs/backlog-2026-11.md)（选图/造图、正文调整、标题/图注/短标题、视觉审查剩余项）。

## 3. 本轮工作自检（新 session 要自己核对）

### 3.1 已完成/已修

- P2 真 bug：公众号复制正文不带 H1；`title_candidates` 支持 `/` 分隔；typeset 失败 `partial` + `typeset_errors`；`get_run` 的 `review_status`（draft/stale/approved）；`review_artifact` 只允许已排版有产物的 run；重新 typeset 旧验收 stale。
- 视觉模板：XHS 卡片 3:4 内 `contain` 不裁切；阅读页纵向复用导出卡；PDF 图片限制版心/62% 页高、去来源孤儿页、首行缩进、`--listings` 代码块；公众号图片限高；复制图片/正文按钮已接并浏览器验证。
- P3 workflow + HITL + trace；真实 UI 三回合验收；12 tools 中文标签；backend 日志显示 11 tools（加入 `ingest_source` 后应为 12，需重启确认）。
- P4 deterministic + grounding audit；judge/writing 质量评分明确不做。
- P5 证据层迁移与静态链路检查；`content_manuscript` 能从证据层数据重建 content。

### 3.2 仍存疑/风险（不要当基线）

1. **P5 没有真实端到端**：新视频下载、ASR、VLM、L1 是否在当前网络/`DASHSCOPE_API_KEY` 下可用，未验证；`ingest_source` 是长任务，MCP timeout 300s 可能不够，当前没有后台任务/进度恢复。
2. **证据层是整体复制**：包含 `evidence_mcp` / `research_mcp` 等本次未用的模块；有多个 `.env` 读取实现、模型默认值硬编码、`settings/params.json` 只是登记表；源项目没有 CLI；`content.md` 由我们的 `content_manuscript` 生成，不是证据层产出。
3. **P3 UI/Mongo**：agent 是 Mongo 内存库里的手工记录；重启会丢；新 session 需要在 Agent Builder 勾选 12 tools（含 `ingest_source`）。progress notification 是否在 UI 可见未单独验证；cost 未配费率时 `null`。
4. **P4**：deterministic pass 不是 writing quality；2 个 capability case missing；grounding 17 candidate flags 未做人工事实判定；没有回归门禁/replay/pass^k；不要重新引入 writing judge。
5. **内容质量**：选图/造图、图表、正文精炼、标题/图注/短标题仍是 backlog；视觉修复只是模板级，不代表内容质量过关。
6. **测试**：580 主要是单元/集成；P2/P3 的浏览器流程是手工 E2E，没有提交自动化 browser test。
7. **服务/仓库**：LibreChat/Mongo/preview 本轮结束已停；frontend 已 rebuild 但 backend 未重启到 12 tools；`vendor/` 不入库；`.env`/data/cookies 不读、不提交；工作树干净但未 push。
8. **P5 数据**：`data/` 是用户数据，不入库；cookie `bilibili.txt` 是敏感文件，未复制、未读取；需要登录态时只传路径给 yt-dlp。

## 4. 整体如何高效推进（分析，不是指令）

- 当前已有一个**本地可演示闭环**：缓存视频 → 计划卡 → 一次 writer → 三种排版/复制/导出 → 人工验收；P3 给了 workflow/HITL/trace，P4 给了 deterministic/grounding 基线，P5 给了“新视频进来”的桥。
- **最大的产品验证缺口**是 P5 真实新视频端到端；**最大的用户可见价值缺口**是内容/图片质量 backlog；**最大的 JD/作品集证据缺口**是 P3/P4/P5 运行证据还没有被整理成一份可展示的报告/演示。
- 高效的做法通常是把“一条新视频”作为共同验收：它同时验证 P5 下载/ASR/VLM、content 生成、P3 workflow、P2 排版和 P4 运行数据；比单独补评测/补 UI 更能暴露真实问题。
- 另一个方向是先做内容质量（选图/图表/正文/标题），因为它是用户能不能发布的直接因素；但它属于 skill 层，按纪律需要 ≥2 视频/文体复现，不能按单篇调参。
- 不建议再把时间投入 writing quality judge/人工评分；用户已明确否掉。可测的是运行数据、产物合同、grounding candidate flags。
- 以上只是分析；新 session 应先自己检查 P5 链路、测试、run 证据和用户反馈，再判断下一步。可以问用户要一条新视频，或先做内容质量/部署，但不要默认某条路线。

## 5. 边界 / 不要做

- 不恢复旧 supervisor/demo/词表/P1 两段式；不跑 30 judge；不伪造 reader test/A-B。
- 不按单篇调参；不手改单篇文章；active skill 不出现具体视频/产品/人物。
- 不评 writing 质量；不做 judge/人工质量打分。
- 不自动 commit/push/publish；不读 `data/cookies/`；不改 substrate v1。
- 不把 bundle 当产品默认输出；不把架构页/评测页放进产品导航。
- 不把 `STATE`/`HANDOFF`/`README`/本文件当干净真相；先看代码、runs、用户反馈。

## 6. 常用命令

```bash
# 全量测试
cd D:/秋招/个人作品/1023视频写作
PYTHONPATH=src PYTHONUTF8=1 D:/anaconda/envs/myagent/python.exe -m pytest tests -q

# 本地启动（三个进程）
cd D:/luno_external/librechat && node scripts/dev-mongo.cjs
cd D:/秋招/个人作品/1023视频写作 && PYTHONPATH=src D:/anaconda/envs/myagent/python.exe -m facet_studio.preview_server
cd D:/luno_external/librechat && npm run backend
# http://localhost:3080

# P5 新视频接入（会下载 + ASR/VLM，timeout 可能长；profile=fast 先 smoke）
cd D:/秋招/个人作品/1023视频写作
PYTHONPATH=src D:/anaconda/envs/myagent/python.exe -c "from facet_studio.ingest import ingest_source; print(ingest_source('BV...', profile='fast'))"

# P4 deterministic + grounding
PYTHONPATH=src D:/anaconda/envs/myagent/python.exe -m facet_studio.evals.product --cases evals/product_v1/cases.json --out evals/product_v1/reports
PYTHONPATH=src D:/anaconda/envs/myagent/python.exe -m facet_studio.evals.grounding --cases evals/product_v1/cases.json --out evals/product_v1/reports

# 证据层备份测试（备份目录，gitignored）
cd D:/秋招/个人作品/1023视频写作/vendor/evidence_core
PYTHONPATH=. D:/anaconda/envs/myagent/python.exe -m pytest -q
PYTHONPATH=. D:/anaconda/envs/myagent/python.exe -m lmind.evidence_mcp.server --selftest
```

## 7. 接手清单

- [ ] 按 §1.1 读完当前文档；能用一句话说清“产品是什么/不是什么”。
- [ ] 复述 §1.2 纪律：一次 writer、无 editor/checker、Writer 不知道来源、人工验收、严禁单例、不评 writing 质量、不跑 30 judge、不自动 commit/push、不读 cookies。
- [ ] 跑测试；检查工作树/commits；打开 UI（需重启服务）；看 P1/P2/P3 产物和 run 证据。
- [ ] 核对 §3.2 的风险，判断哪些是 bug/待办/用户后置。
- [ ] 重点核对 P5：`ingest_source` 真实新视频端到端是否成立；`content_manuscript` 输出是否接上；MCP 12 tools/agent 是否加载。
- [ ] 自己判断下一步，给用户 2–3 个方向 + 验收标准；不要直接开写。
