# 产品 v1：Facet Studio 聊天式内容工作台

> 状态：2026-11-06 产品定义已确认；P1/P2 原型已跑通；**P3 workflow 原型、P4 deterministic/grounding harness、P5 证据层已接**；2026-11-09 聊天侧改为后台 run + 消息级运行卡 + 右侧预览抽屉，默认 `auto_plan=True` 直写，计划卡仅在用户明确要求时出现。当前代码/事实见 [architecture.md](../architecture.md) §4；启动见 [integrations/librechat/README.md](../integrations/librechat/README.md)。
> 系统架构见 [architecture.md](../architecture.md)；写作引擎见 [writing-v5-architecture.md](writing-v5-architecture.md)；JD 见 [jd-mapping-2026-11.md](jd-mapping-2026-11.md)；复用栈见 [reuse-stack-2026-11.md](reuse-stack-2026-11.md)。
> 本文只定义产品/UX/数据边界，不复制写作方法。方法/纪律看 [writing-rebuild-brief.md](writing-rebuild-brief.md) §2/§3。

## 0. 一句话

Facet Studio 是一个聊天式内容工作台：你把视频和写作要求丢给它，它按需写成一种形态，在聊天里给你看排版好的成品，并让你检查、修改、导出。

不是“一次生成所有形态”的 bundle 工厂；多形态是能力，不是首页承诺。

## 1. 用户与 job

**用户**：有视频素材、需要公众号 / 小红书 / 长文的内容运营或创作者。

**job to be done**：

- 我有一条视频，但没时间把它写成文章；
- 我不想学 prompt / 架构 / skill；
- 我告诉它：用哪条视频、写什么形态、给谁看、多长、什么语气、必须包含/避免什么；
- 它一次写完，给我能直接用的成品；
- 我能检查它读了什么、花了多少、写了什么、有没有出错；
- 我能改一版、导出、验收；不自动发布。

## 2. 不是什么

- 不是作品集网站、不是首页卡片流；
- 不是一次生成三种形态的 bundle 工厂；
- 不是架构 / 评测演示页；
- 不是 editor/checker 多轮改稿链；
- 不是自动发布工具；
- 不是“视频转写 + 摘要”工具；它的产物是独立文章/笔记，不是 coverage dump。

## 3. 核心交互

### 3.1 输入

用户在聊天框里给：

- **来源**：B 站 BV 号或本地视频/内容位置；
- **形态**：深度总结 / 公众号 / 小红书（一次一种，也可以先让 agent 建议）；
- **读者**：给谁看、什么知识起点；
- **长度**：短 / 中 / 长，或大致字数；
- **风格/个人画像**：语气、人称、偏好、禁用表达；
- **must_include / must_avoid**；
- **其他要求**：图、标签、标题方向、平台限制等。

缺省规则：用户没说的用默认；最多问一个澄清问题，不弹长表单。

### 3.2 写前计划卡（仅在用户要求时）

默认不弹计划卡：用户给 BV + 形态后，Agent 直接启动后台 workflow，聊天里的运行卡显示读取/规划/写作/排版。只有用户明确说“先看计划 / 给我计划 / 确认后再写”时，才出 3 行计划卡：

- 形态 + 角度；
- 读者 + 读完能得到什么；
- 长度 + 图计划 + must include/avoid。

用户可改；计划卡是护栏，不是 section schema。

### 3.3 写作与执行过程

- 读取内容：默认缓存优先；新视频可 `ingest_source`，长视频先用 CLI；写作层仍只读 `content.md`。
- 规划：Lead Planner 决定角度/brief/图；不是固定章节模板。
- 写作：一个产物一次 writer；没有 editor/checker/草稿阶段。
- 运行卡：聊天里每个 assistant 消息只渲染一张运行卡，显示阶段轨、当前步骤/已用时间、计划、视觉审计结论、字数/卡片/关键帧；右侧抽屉打开成品。原始 JSON 和内部 ID 只在 `/runs/<run_id>`（Live SSE / Trace / Stats）；`trace.html` 仅导出/降级，不是写作质量分页。
- 失败：partial/failed 显式显示，不静默截断；单产物失败不影响其他请求。

### 3.4 产物与预览

产物默认是**排版后的预览**，不是裸 Markdown：

- 深度总结：阅读页 HTML（可导出 PDF）；
- 公众号：公众号文章预览 + 可复制富文本 HTML；
- 小红书：笔记预览 + 3:4 卡片（阅读页顶部纵向列出，可直接保存）；
- Markdown 作为“可编辑源”保留，可切换查看/复制。

预览直接出现在聊天里（artifact 卡），可展开/全屏；桌面右侧预览，移动端 sheet。

### 3.5 修改

“再短一点 / 更口语 / 换个标题 / 换开头”是**新的 writer 请求**，不是 editor/checker 改稿：

- 保留上一版 artifact；
- 新请求 + 新 writer 调用；
- 版本化，可回看；
- 不按单篇手改，不把修改写成通用规则。

### 3.6 验收

- 用户点“验收通过”才写 `publish_review.json`；未验收的产物标“草稿”；
- 不自动发布；
- 验收状态显示在 run 面板和 history；
- 排版失败（PDF/卡片渲染）显式标“部分完成”，错误进 run 数据，不静默当成功；
- 重新排版会生成新产物版本，旧验收标“待重新验收”，不静默沿用；
- 只有已排版且有产物的 run 能“验收通过”。

### 3.7 历史与记忆

- 最近 runs：按时间/来源/形态筛选；
- “基于同一内容再写一版”：复用 content hash，不重读视频；
- 用户风格/画像：记住长度、语气、人称、禁用表达；
- 程序性记忆：skill 库版本；语义记忆：content hash + figure catalog；工作记忆：当前 run 状态。

## 4. 界面

> 具体布局/视觉 token/LibreChat 定制点见 [ui-design-2026-11.md](ui-design-2026-11.md)。
> 产品壳已定：LibreChat（MIT）——chat、Agents、MCP、Artifacts、Trace Viewer、Token 统计；写作逻辑在 Python MCP 服务。见 [reuse-stack-2026-11.md](reuse-stack-2026-11.md)。

Chat-first，不是首页卡片流：

```text
┌ 侧栏 ─────┬ 聊天 ────────────────────────┬ 预览 ─────────────┐
│ 最近 runs │ 用户：用 BV17 写公众号…       │ 阅读页 / 公众号   │
│ 内容库    │ Agent：运行卡                 │ 手机预览 / 小红书 │
│ 设置      │ 运行详情：/runs/<run_id>       │ 卡片 / PDF        │
│           │ Agent：成品卡 + 操作           │                   │
│           │ 输入框：BV/本地/要求           │                   │
└───────────┴───────────────────────────────┴───────────────────┘
```

- 桌面：聊天 + 右侧预览；移动：聊天全屏，预览 sheet。
- 产品导航只有：聊天、历史/内容库、设置。
- **架构页、评测页不进产品导航**；它们是开发/面试材料，放在 `docs/` 或独立 dev 页面。
- 视觉：编辑杂志感 + 平台预览 + 技术工作台；技术工作台是消息级运行卡 + `/runs/<run_id>`，不是独立产品页。

### 4.1 三个体验目标

- **用得舒服**：chat-first；默认值 + 最多一个澄清问题；常用请求有快捷入口；最近 runs 可复用；修改只需一句话；不用理解 planner/bundle/DAG。
- **看得舒服**：默认看排版后的成品（阅读页/公众号/小红书卡片），不是裸 Markdown；TOC/图注/表格/移动端可用；平台预览像真实成品，但不伪造互动数据。
- **用得放心**：run 面板显示来源 hash、内容字数/图数、模型、calls、tokens、时延、成本、工具调用、错误、验收状态；不静默失败；不伪造数据；不自动发布。

## 5. 输出格式

| 形态 | 源 | 成品 |
|---|---|---|
| 深度总结 | Markdown | 阅读页 HTML；PDF（Pandoc + Typst/LaTeX 中文模板） |
| 公众号 | Markdown | 公众号富文本 HTML（可复制）；预览 |
| 小红书 | Markdown + 配图 | 笔记预览；3:4 卡片 PNG；标签/title candidates |

Markdown 是编辑源；HTML/PDF/卡片是成品。最终排版复用开源，不自己造排版引擎。

## 6. 三类数据必须分开

| 层 | 给谁 | 内容 | 放在哪 |
|---|---|---|---|
| **用户实时可观测** | 产品用户 | run 状态、阶段、计划、视觉审计、字数/卡片/关键帧、验收状态 | 消息级运行卡 + 右侧预览抽屉 |
| **开发评测数据** | 开发/面试 | 数据集、指标、回归、judge 校准、A/B、bad case、成本分布 | 独立 eval report/dashboard，不进产品 |
| **简历数据** | 面试官 | task success、pass@1/pass^k、事实保真、平台适配、baseline 胜率、时延/成本、人工验收 | eval report / 作品集页 |

不要把 eval 分数塞进产品 UI；产品里只显示“草稿 / 已验收”和这次 run 的事实。不把“跑通”当“质量通过”。

## 7. 内容选择

默认缓存优先；新视频可 `ingest_source`（长视频先用 CLI）；写作层仍只读内容稿。

新视频选择标准（等接入时用）：

- 5–20 分钟，有一个清楚的机制/流程/演示；
- 聪明普通读者会在意，3 秒能说出“为什么看”；
- 有足够材料撑 3–5k 字深度文章，也能压出一条小红书主线；
- 真实帧/封面好看，不是纯口播；
- 不需要大量外部事实核查，不涉及医疗/金融等敏感建议；
- 有画面使用权。

组合：技术解释（机制）+ 实操教程（步骤/数字）+ 可选生活/文化（视觉强）。当前 BV17/BV1ix 是前两类的骨架；新视频最后替换，不阻塞产品。

## 8. 产品边界

- 一个产物一次 writer；没有 editor/checker/草稿阶段。
- 按需生成一种形态；不默认 bundle；用户要多种就分多次请求。
- Writer 不知道来源；只拿到“这件事的完整内容”；不核验内容本身。
- 不写死字数/结构；request 优先，没 request 用默认。
- 不按单篇调参；active skill 不出现具体视频/产品/人物。
- 用户人工验收是唯一发布门；测试绿/跑通不算通过。
- 不恢复旧 supervisor/demo/词表/P1 两段式；不跑 30 judge。
- 可观测数据分三层（见 §6）；不伪造 reader test/A-B/线上数据。
- 复用优先：LibreChat / MCP / LangGraph / Pandoc / md2wechat / 开源卡片；license 先审。

## 9. 路线

| 阶段 | 内容 | 验收 |
|---|---|---|
| P0 | 产品/UI/架构/复用/JD 文档收口（本文件 + ui-design + architecture + reuse + jd） | 后续 session 不再把 bundle 当产品 |
| P1 | LibreChat + MCP 工具服务原型：缓存内容 → 聊天 → 一次 writer → 运行卡/预览 **已完成原型 2026-11-06**（见 [integrations/librechat](../integrations/librechat/README.md)） | 一条 BV 能走完；run 数据可见；不自动发布 |
| P2 | 排版/导出：阅读 HTML + PDF；公众号 HTML；小红书卡片 **已完成原型 2026-11-07**（见 [xhs](../integrations/xhs/README.md) / [pdf](../integrations/pdf/README.md)） | 成品可读/可复制/可下载；移动端可用 |
| P3 | LangGraph 工作流 + HITL + 观测：状态/checkpoint/stream/interrupt；trace/token/cost **原型已接 2026-11-07** | 可暂停/恢复/验收；run 数据可查 |
| P4 | 评测（先预留）：runtime/grounding 指标、回归/pass^k **deterministic + grounding harness 已接 2026-11-07** | 有可复跑报告；不评 writing 质量、不伪造真人 reader test |
| P5 | 视频转录接入 **证据层已迁移 2026-11-07；真实下载/ASR/VLM/content/workflow 已跑通 2026-11-08** | 用户提供新视频后可跑通；剩用户验收与长视频体验 |

## 9.1 已知内容层待改（不阻塞 P2 壳）

- **小红书标题**：钩子偏弱/个别标题把演示写成第一人称亲历。用户明确说“标题最后改”，不按单篇调参。
- **公众号正文**：数字偏多、图表不足、不够精炼。属于写作认知/内容层，不在排版层解决。
- 这两项只记录；P2 只保证版式、预览、复制/下载/导入可用。

## 10. 开放问题

- 部署形态：本地 Docker（LibreChat + MongoDB + Python MCP）还是公网 URL？公网需要鉴权/限流/成本上限。
- LibreChat 的自定义程度：只换主题 + artifact renderer，还是 fork 更深？
- 评测什么时候做、做多大：先预留，等产品原型稳定后再定。
- 目标 JD/公司：需要 2–3 份真实 JD 再收紧映射。
- License：AGPL/BUSL 是否接受；默认只嵌入 MIT/BSD/Apache。

## 11. 决策记录（2026-11-06）

- 产品 = 聊天式内容工作台；**不是** bundle 工厂/作品集/架构页。
- 产品壳 = **LibreChat**（MIT）；写作逻辑 = Python MCP 服务；编排 = LangGraph；排版 = 开源模板。
- **一次一个形态**；默认直写，只有用户明确要求时出计划卡；最多一个澄清问题；修改 = 新 writer 请求。
- 评测先预留；产品原型稳定后再做；不跑 30 judge。
- 默认缓存优先；新视频走证据层接入；写作层不感知视频/证据层。
- 嵌入代码优先 MIT/BSD/Apache；AGPL/BUSL 只作设计参考，除非用户同意合规。
