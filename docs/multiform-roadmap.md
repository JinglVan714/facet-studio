# 多文体路线（2026-11-05）

> **状态：上一轮提案/实验，非基线。** 2026-11-05 session 2 已由 [writing-v5-architecture.md](writing-v5-architecture.md) 取代；本文件只作历史/调研参考，不要当方向。可信基线 commit `2f8faea` 也不是已验收好基线。
> **2026-11-06**：产品 v1 已重定义为聊天式内容工作台（[product-v1-chat-studio.md](product-v1-chat-studio.md)）；本文件的“JD 表”是 pre-2026 研究，**评测/Function Calling/MCP/LangGraph 等映射已过时**，以 [jd-mapping-2026-11.md](jd-mapping-2026-11.md) 为准；本文件的“Consistency/Visual Editor”不是当前架构。
>
> 上一轮提案：**先做多种社媒（小红书 + 公众号），再做视频脚本；md 内容先过关；HTML 后续；PDF 暂不做；完全体之后加简易前后端 demo。**
> 上位：`AGENTS.md` 全局护栏、`architecture.md` §6.5/§11（多文体机会）、§13.1（JD 能力）、§14（复用）。
> 方法/纪律看 [writing-rebuild-brief.md](writing-rebuild-brief.md)；本文件只维护“做什么、为什么、验收”，不复制方法或状态。

## 0. 一句话

先把“同一份内容稿 → 多种社媒产物”做稳，再做视频脚本；JD 的每一行都要有真实 consumer，不写“未覆盖”，也不硬塞；HTML/演示壳后置，PDF 暂不做。

## 1. 为什么是这个顺序

- **现有 skill 已稳定**：`skills/writing/video-article/` 是调了很久的内容稿制 skill，核心是从 `bilibili-render-pdf` 教学 flow 长出来的“理解 → 组织 → 表达”，理论上覆盖多种视频类型的深度总结。
- **社媒复用率最高**：小红书/公众号不是另一套方法论，而是同一核心 skill 加“平台/读者/格式层”。它们最直接证明“一次证据编译，多文体写作”，边际成本最低。
- **视频脚本第二步**：脚本也吃 prompt/写作逻辑，但多一层制作约束（镜头、旁白、真实帧 vs 示意、B-roll）；等社媒把 prompt/平台层跑顺再做。
- **md 先过关**：当前 md 文字内容大致过关；HTML 还没具体调整，排版/字体/插图大小都未做；PDF 暂不做。展示层放到内容稳定之后。
- **先调研再写**：社媒/脚本更吃素材组织、表达、文风的 prompt 逻辑。先看本地 + GitHub 开源项目，能借 prompt 结构/例子组织/平台规范就借；借逻辑不抄文本，复用前查 license。
- **JD 服务核心**：多 Agent 编排、View 检索、trace、eval 等必须服务“多文体写作 + 质量 + 复用”，不是为了关键词另起 demo。

## 2. 多 Agent 编排（JD 第 1 行的定义）

**不是**“多个角色串在固定 pipeline 里”。

- Anthropic：workflow 是 predefined code paths；agent 是 LLM 动态决定自己的过程/工具。orchestrator-workers 是中央 LLM 在运行时拆任务、委派 worker、合成结果；子任务不是预定义的。
- OpenAI：编排先决定“谁拥有最终答案”；handoff 是 specialist 接管一段，agents-as-tools 是 lead 保持控制权、把 specialist 当有界能力调用。
- LangGraph：supervisor 是中央路由；worker 不 lateral chat；supervisor 决定下一个 worker 或 FINISH。sequential pipeline 是 topology-encoded routing，不是 orchestration。

**本项目的最小落点：**

```text
Lead/Editor orchestrator（运行时决定）
  → LeadPlan：form / platform / specialists / briefs / stop conditions / rationale
  → specialists（agents-as-tools，最多 3 个）：
       Writer
       Consistency Editor
       Visual Spec Editor
       Platform Editor（小红书 / 公众号）
  → 共享 RunState：EvidenceSnapshot + ContentManuscript + SkillManifest
  → 合成最终稿 + trace（role / brief / attempt / handoff / stop / usage）
  → 有界：最多 1 次 revision；显式 FINISH；失败 partial，不静默
```

**为什么服务核心：** 多平台社媒本来就需要平台编辑；文章需要一致性编辑和视觉 spec；脚本需要分镜/视觉判断。Lead 决定“这次叫不叫 visual/platform/editor”，这是“多文体不复制 pipeline”的核心。没有 orchestration，每个文体就会长出一条自己的 pipeline。

## 3. JD 表（全部映射到核心；没有“未覆盖”行）

> **历史 pre-2026 表，已过时。** 评测/Function Calling/MCP/LangGraph 等映射不要用；当前 JD 映射与评测口径见 [jd-mapping-2026-11.md](jd-mapping-2026-11.md)。
> `待补/待接` = 有明确 consumer 和验收，排进路线；不是“不做”。每行都必须有真实 consumer，否则不建。

| # | JD 能力 | 核心业务问题 | 真实落点（最小 artifact） | 消费者 | 验收/证据 | 现状 |
|---|---|---|---|---|---|---|
| 1 | 多 Agent 编排 | 不同文体/平台需要不同 specialist 组合和顺序；固定 pipeline 不能按请求动态路由 | Lead/Editor orchestrator + LeadPlan + specialists（Writer / Consistency / Visual / Platform）+ 共享 RunState + agents-as-tools + 停止/预算 + trace | skill_runner/pipeline；每个文体；demo UI | LeadPlan 显示动态选择；trace 有 role/attempt/handoff/stop；2 视频 × 2 平台对比 fixed pipeline；无 loop、无 50 subagent | 当前是固定 workflow；待接 Lead + 动态 plan |
| 2 | 任务规划/调度 | 不同文体需要不同 stage，跳过不需要的 stage，控制预算 | LeadPlan 即 v4 TaskPlan：skill/form → writer → optional consistency → optional visual → checks → render；stage status/skip reason | skill_runner/pipeline | plan artifact；skip decision；replay | 固定 4 段已有；LeadPlan/status 待补 |
| 3 | 工具调用/MCP | 证据编译、内容稿、SVG、检查、渲染都是工具；要能审计/失败可查 | ToolSpec/Registry/Executor + receipts（content compile / SVG render / checks / render）；MCP 只做薄 adapter | evidence compiler / runner / demo backend | tool_calls.jsonl；超时/失败测试；registry 单测 | 工具已有；receipts 待补；MCP adapter 待补 |
| 4 | 记忆 | 一次证据编译，多文体复用；同事实/同范围；不重读 ASR | EvidenceSnapshot/KnowledgeSnapshot + ContentManuscript + SkillManifest 库；复用 hash/边际成本 | 所有文体；writer/skill router | 同视频多文体共享 content hash；跨文体一致性；成本对比 | substrate 已有；多文体复用证据待补 |
| 5 | 决策/Trace/Budget | 为什么选这个 skill/stage；成本多少；失败可 replay | RunManifest + DecisionRecord + LLMCall/ToolCall receipts + BudgetState；按 hash replay | runner/pipeline、开发者、demo UI | manifest schema；budget exceeded；replay | response_meta 已有；统一 trace 待补 |
| 6 | 评测/质量 | 每个文体有自己的 reader contract；防回退；不靠 30 judge | per-skill EvalCase + 地板/rubric + 小规模单 persona 抽查 + 人工 acceptance；官方 30 只作历史 | CI/pytest、skill 迭代、发布门 | eval case per form；floor tests；manual acceptance | 560 tests（v4 34）；per-skill eval 待补 |
| 7 | Prompt/Context Engineering | 写作质量核心：skill + 内容稿 + 文体 view；不同文体需要不同上下文 | SkillManifest（id/version/forms/prompt/checks/rubric）+ ContentManuscript + View selection；prompt/hash 记录 | writer/skill_runner | manifest 单测；prompt diff；A/B | skill/manifest 已有；view selection 待补 |
| 8 | Agent 框架/RAG | 多文体需要检索“哪段证据/哪种 view”，而不是全文硬塞；可选框架 adapter | deterministic ViewRetriever（mechanism/procedure/timeline/highlight）over EvidenceSnapshot；selection report；LangGraph 可选 adapter | skill_runner/writer | retrieval coverage/recall；selection report；不静默截断 | 待补（真实 consumer；不是向量库全栈） |
| 9 | 工程/成本/观测 | 每个 run 的 calls/tokens/latency/status 可查；partial/failed 不静默 | RunManifest + usage aggregation + status/error + cost；demo 后端读 | 开发者、demo UI | manifest；failure states；cost aggregation | response_meta 已有；聚合/状态待补 |
| 10 | 作品/开源 | 面试官看多文体作品 + 可回放证据；不是只讲架构 | multi-form portfolio（HTML later；PDF 暂不做）+ trace/replay 页 + README；开源可选 | 面试官/用户/demo | build 可重复；链接可用；无评分/架构混入 reader 页 | 3 篇文章已有；多文体作品集待补 |

**两条边界：**

- **RAG 在这里是 View 检索**，不是向量数据库全栈；没有 writer consumer 就不建。
- **MCP 只做薄 adapter**，核心仍是本地 ToolRegistry + receipts；不为生态而生态。

## 4. 阶段与验收

> 2026-11-05 确认：**P1 直接建 LeadPlan + Platform Editor**，不再“先单 writer 试水、P3 再重构”。一步到位，符合 JD 第 1 行。

| 阶段 | 内容 | 产出 | 验收 | 成本 |
|---|---|---|---|---|
| P0 冻结 | 架构/交付包/平台 references；reuse map | 文档 + 平台 references | 用户确认；不写代码 | 0.5 天 |
| P1 社媒 + 编排 | LeadPlan orchestrator + Platform Editor（小红书/公众号）+ ViewRetriever + run manifest/receipts + per-skill eval；BV1ix/BV17 × 2 平台 | 4 个发布包 + trace/eval | 过 form floor + 5 维 rubric + 人工 acceptance；同视频跨平台事实/范围一致；LeadPlan/trace 可查；不新增 per-form pipeline | 4–5 天 |
| P2 视频脚本 | 同一 orchestrator 加 Script specialist；BV1ix/BV17 | 2 个脚本包 | 镜头表/旁白/真实帧 vs 示意；无伪造画面；floor + 人工 | 1–2 天 |
| P3 HTML | 多文体作品集 | HTML（含排版/字体/插图大小；小红书卡片/公众号文章） | 桌面/移动可读；构建可重复；**PDF 暂不做** | 1–2 天 |
| P4 demo 壳 | 简易前后端 | FastAPI + 简单前端；选择视频/文体/平台 → 生成 → 查看产物/trace | 本地可演示；不重复业务逻辑；**不写进 architecture** | 1–2 天 |

### 4.1 交付包格式

**小红书（干货/教程）**

```text
social/xiaohongshu/<video>/
  card_copy.md      # 封面 + 5–7 张卡片，每张一句/一个点；可粘贴模板生图或替换
  title.md          # 1 主标题 + 3 备选
  body.md           # 正文 only text：短段、emoji 可选、可直接粘贴
  tags.md           # 5–10 个标签
  images/           # 真实帧 1–3（封面/细节/结果）；后续可换图表/模板图
  publish.md        # 发布顺序：贴正文→生成模板图→替换卡片/真实帧→标题+标签
  post.md           # 人类可读合并版（作品集用）
```

**公众号**

```text
social/wechat/<video>/
  article.md            # 标题 + 正文（短段；可含真实帧）
  title_candidates.md   # 3–5 个候选
  publish.md            # 复制到公众号编辑器；图注/图片位置
```

- 不设硬长度；按内容，短内容不硬凑。
- 小红书 emoji 可用、不强制；标题 emoji 可选。
- 图先放真实帧；效果不好再生成图表/模板图；不伪造画面。
- 产物不直接兼容小红书 app，按 `publish.md` 手动复制/替换；HTML 后置做作品集。

## 5. 调研 reuse map（P0，已完成）

**本地只读：**

- `参考素材/skills/aislinn-yang__rednote-writing-skill` — 小红书标题/hook/正文/标签/平台语气。
- `参考素材/skills/yaoleifly__wechat-writing-style` — 公众号长文结构/开头/论证/结尾。
- `参考素材/skills_downloaded/anthropics__skills/skills/internal-comms` — 结构化沟通。
- `参考素材/skills_downloaded/mattpocock__skills/skills/in-progress/writing-beats`、`writing-shape` — beats/形状。
- `参考素材/skills/zenstory-ai__drama-skills`、`dexhunter__seedance2-skill`、`LearnPrompt__awesome-seedance` — 短视频脚本/分镜/画面提示词。
- `参考素材/skills/crewAIInc__crewAI-examples`、`zwzhangyu__ai-agent-lab` — 多 Agent/规划/工具回执工程写法。
- 本地 `bilibili-render-pdf` — 教学 flow；只借顺序，不抄 LaTeX/图越多越好。

**GitHub：** social writing skill、platform style guide、hook/thread 结构、video script prompt；先看 license/维护状态；借 prompt 结构和例子组织，不抄文本、不运行不可信脚本。

**输出：** 已落 [social-writing-reuse-map.md](social-writing-reuse-map.md)：平台矩阵、每个平台借什么/不借什么、现有 video-article skill 如何加平台层、质量 rubric、prompt 草案、待讨论取舍。

## 6. 非目标 / 边界

- **PDF 暂不做**；HTML 后置；排版/字体/插图大小等展示层等内容稳定后再调。
- **写作层只对写作逻辑负责**：不核实世界、不给素材挑毛病、不把源材料冲突写成纠错清单；允许围绕原文语义/结构做补充、重写、修饰、精简；不新增事实/机制/因果。例子匿名；不按单篇/单个例子调参。
- 不重跑 5 persona × N 篇的 30 judge；官方 30 只作历史证据。
- 不为每个文体加 per-form pipeline/validator/gate；文体差异放 skill/platform 层。
- 不做聊天式 multi-agent、50 subagent、无限 repair；orchestration 有界、可停、可 trace。
- 不为 JD 硬塞：没有 consumer 的 artifact 不建；不伪造 reader test/A-B。
- 不改 substrate；不 commit/push；不自动发布；不读 `data/cookies/`。
- demo shell 不进 architecture；单独 `demo/` 或 `docs/demo.md`。

## 7. 当前状态（2026-11-05）

- 已有：`skills/writing/social-core/`、`social-note/`、`wechat-article/`、`video-script/`；`src/facet_studio/writing_v4/` 的 `skill_runner`、`form_checks`、`orchestrator`、`package`、`view_retriever`；`tests/writing_v4` 55 passed；全 suite 581 passed。
- P1 首轮：LeadPlan → writer → platform editor → visual → package → checks 已跑通；xhs 2 篇（BV1ix/BV17）+ 公众号 2 篇（BV1ix/BV17）草稿在 `runs/.../multiform/v2*`；**不按单篇调参，草稿不作最终产物**。
- P0 调研已落 [social-writing-reuse-map.md](social-writing-reuse-map.md)；取舍已确认（emoji 可用不强制；不设硬长度；标题候选可；**P1 直接 B：LeadPlan + Platform Editor**；真实帧优先；md 先、HTML 后、PDF 不做）。
- 下一步：人工 acceptance 4 个发布包 → 按通用层修写作逻辑（≥2 视频/文体）→ P3 HTML 作品集；不按单篇/单例调参。
