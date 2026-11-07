# Writing v5 架构：写作引擎（不是产品壳）

> 状态：2026-11-07。**这是写作引擎（writing_v4）的架构，不是产品壳。** 产品 v1 是聊天式内容工作台（LibreChat + MCP + LangGraph），见 [architecture.md](../architecture.md) 和 [product-v1-chat-studio.md](product-v1-chat-studio.md)。
> 上位：`AGENTS.md`；方法/纪律见 [writing-rebuild-brief.md](writing-rebuild-brief.md) §2/§3。
> 旧实现不是基线：`architecture.md` 附录是 v3 机会地图；`docs/writing-operating-model.md`、`docs/writing-layer-*.md`、`docs/writing-skill-study.md`、`docs/writing-planner-position.md` 是历史，不读、不恢复。
> **当前形态：深度总结（long_article）/ 公众号（wechat_article）/ 小红书（xiaohongshu_note）。短视频脚本暂不做。**
> 当前阶段：三种形态已“大致验收”；Lead Planner + orchestrator + bundle 已跑通。产品层 **P1/P2 原型已跑通**（LibreChat + MCP + preview + review + 公众号 HTML / 小红书图集 / PDF）；LangGraph/评测尚未接入；**bundle 是内部/调试产物，不是产品默认输出。**

## 0. 一句话（写作引擎）

一份 content manuscript + figures，一次编译；Lead Planner 决定这次写什么；每个产物由自己的 writer **一次写完**；确定性工具负责图、SVG、装配和 trace；用户人工验收。产品层按需请求一种形态；bundle 只是内部/调试形态。

## 1. 整体问题（为什么重做）

1. **写作层只有“一个成熟 form + 一个薄弱克隆”**：`video-article` 能写出机制、图、表格、边界；`wechat-article` 是另写的薄 skill。同一条 BV1ix，前者有图有表，后者被否。问题不在 substrate，在 form 层没有复用成熟写作方法。
2. **视觉链路只接在旧 article pipeline 上**：`run_form.py` 不复制 figures、不改路径、不跑 SVG。被否文章“没有帧、配料/流程全塞文字、应该用 SVG”正是这个缺口。
3. **runtime/harness 与写作层断开**：`runtime/` 已有 TaskPlan、ToolRegistry、WorkingMemory、RunStore、Trace、Decision、Eval，但 `writing_v4` 没用。JD 的“多 Agent 编排”目前是摆设。
4. **没有多形态产品闭环**：社媒文章、短视频脚本没有验证过的产物；P1 被删后只剩一个被否的公众号 one-call。
5. **架构文档与代码漂移**：`architecture.md` 仍描述 v3 EvidencePack/View/Verifier/30 judge；当前实际是 substrate v1 + one-call writer。机会地图有效，实现章节已过期。

**一句话**：substrate 和单篇长文是资产；缺的是“一次内容编译 → 多角色产物”的产品闭环，以及把这个闭环真正跑在现有 harness 上。

## 2. 产品定义

**输入**

- 一条视频（substrate v1：transcript / sentences / frames / OCR）。
- 一个 `WritingRequest`，由前端 prompt 驱动：`forms / platform / audience / length / angle / must_include / must_avoid / language`。
- 写作 skill 库。

**输出（写作引擎）**

一次请求可生成一种或多种产物；**bundle 是内部/调试形态，产品默认按需只请求一种**：

- 深度文章（long_article）
- 公众号文章（wechat_article）
- 小红书笔记（xiaohongshu_note）
- 短视频脚本（short_video_script）**暂不做**，后续有需要再加

所有产物共享同一份 content manuscript、同一组 figures、同一个 content hash。

**不是**

- 不是视频摘要 / coverage dump / 逐段搬运。
- 不是每个 form 一套 pipeline / validator / gate。
- 不是聊天式 multi-agent，不是 supervisor 审稿改稿。
- 不是自动发布。

## 2.1 写作输入与核验边界（2026-11-05 用户确认）

- **Writer 不知道来源**：writer 只拿到「这件事的完整内容」；不知道它是视频、素材包、内容稿、转写；正文不出现来源/工作痕迹。
- **不核验内容本身**：不挑内容的错、不写“未证实/待核/需要进一步验证”；不把文章写成百科、论文、体检报告。
- **只处理已有内容 + 用户明确提供的补充 / 联网调研（未来可能有）**；不做外部事实核查。
- 模型知识只用于组织、表达、概括、类比、术语最小解释；不添加内容没有的具体事实/数字/引语/画面。
- 事实、数字、引语、例子只来自已有内容或明确补充；内容说“一次演示/一个案例/可能”，文章保留这个范围。

## 3. 数据流（干净链路）

```text
video / substrate v1（冻结）
  → content manuscript：content.md + figures/ + content_sha256
  → WritingRequest（前端 prompt）
  → Lead Planner（1 次调用）→ lead_plan.json
  → TaskPlan（确定性 DAG）
  → per-form writer（每个产物 1 次调用）
       → article.md / note.md
       → response_meta.json
  → deterministic tools
       → copy figures / render SVG / inspect / assemble
  → bundle.md + bundle_manifest.json
  → llm_calls.jsonl + tool_calls.jsonl + decision_records.jsonl
  → human acceptance（唯一发布门）
```

**每个箭头只有一个 producer 和一个 consumer。** 中间层不互相读私有文件；writer 只读 content manuscript + 自己的 skill + plan brief。

## 4. 多 Agent 编排

### 4.1 角色

| 角色 | 做什么 | 不做什么 |
|---|---|---|
| **Lead Planner** | 读 content + form catalog + request；决定生成哪些 form、每个 form 的 angle/brief/must-use figures；输出 JSON plan | 不写正文；不评审；不改稿 |
| **Specialist Writer** | 每个 form 一个 writer；读 content + plan brief + skill；一次写完 | 不看其他 writer 的输出；不互聊；不自审成另一轮 |
| **Tool Executor** | 确定性工具：compile / inspect / assemble；回执 | 不调用模型写正文 |
| **Human** | 验收、发布门 | — |

### 4.2 不是 supervisor

- 旧 supervisor 是“writer 写完 → supervisor 审 → 再改”，那是第二 writer/editor，用户已否。
- 本架构是 **planner-executor / orchestrator-workers**：planner 只决定“做什么”，writer 各自一次写完，工具只做确定性装配。
- 每个产物仍然 **一次 writer**；没有草稿阶段、editor、checker。

### 4.3 为什么这能接 JD

- 运行时决定 form / angle / brief（不是固定 pipeline）。
- 共享内容稿 + content hash（记忆复用）。
- ToolRegistry/Executor + 回执（工具调用）。
- RunStore：llm_calls / tool_calls / decisions / task_plan / usage（可观测、成本）。
- 有界：无 loop、无 30 subagent；失败 partial，不静默。
- Replay：按 request identity 回放。

## 5. 写作层：core skill + form layer

### 5.1 Skill 分层

```text
skills/writing/video-article/        # 核心方法（现有，保留）
  SKILL.md                          # 角色/读者/事实边界/形状/自审
  references/examples.md            # 匿名例子

skills/writing/wechat-article/      # 平台层（extends video-article）
  SKILL.md                          # 公众号读者/结论先行/短段/H2/视觉要求
  references/wechat.md              # 平台规范
  references/examples.md            # 平台例子

skills/writing/xiaohongshu-note/    # 独立 form：一个点/hook/短段/图/标签
# 短视频脚本暂不做；后续有需要再加 skills/writing/short-video-script/
skills/writing/bundle-planner/      # 编排 skill：输出 JSON plan，不写正文
```

**为什么公众号要 `extends`**：被否那篇的根因不是“公众号这个文体不行”，而是它用了一份薄 skill，没有继承 `video-article` 的机制、例子、边界、视觉方法。平台层只加“读者/形状/标题/视觉要求”，核心方法复用。

### 5.2 Form 矩阵

| form | 读者 | 形状（默认，可按 request 调） | 视觉 | 输出 |
|---|---|---|---|---|
| `long_article` | 愿意读 5–10 分钟 | 控制性 idea → 机制 → 例子 → 边界 | 真实帧 + 表格 + SVG | `article.md` |
| `wechat_article` | 已点开/订阅，3–5 分钟 | 结论先行 → 2–4 个 H2（默认） → 短段 | 至少 1–2 张真实图/表 + SVG | `article.md` |
| `xiaohongshu_note` | 刷信息流，0.5 秒 | 一个点 → hook → 2–4 短段（默认） → 动作 | 封面 + 1–3 张真实图 | `note.md` |
| ~~`short_video_script`~~ | 暂不做 | 后续有需要再加 | — | — |

**默认不是硬门。** 文章篇幅、H2 数量、段落数、镜头数、脚本时长都跟 request、视频时长、内容量相关；request 优先，没有 request 才用默认。

### 5.3 每个 form 开发前必须先汇报写法

按用户要求：**每个文体动手前，先调研开源/本地 skill，再汇报“读者、形状、hook、视觉、长度策略、借什么/不借什么、验收方式”**；用户确认后再写 skill、跑 2 条视频。不先写代码再解释。

当前顺序：

1. 社媒（公众号 + 小红书）——先做。
2. 短视频脚本——暂不做，后续有需要再加。
3. 深度文章——现有底座，后续一并优化。

### 5.4 读者契约、内容地图与路标（2026-11-05）

- **默认目标 = video-equivalent understanding**：让没看过内容的人快速、舒服地理解这件事的大致内容、关键机制/步骤、例子、边界；不是摘要，也不是一个 hook 的展开。
- **文章是 new composition**：可以重排、合并、拆分、删减、改写、统一术语；可以用模型知识把说法规范化（如“768 个数字”→“768 维向量”）；不能加内容没有的事实/数字/引语/画面/机制/因果。
- **读者契约 = request + 最小读者 + 知识契约**：不假定具体人设；request 优先，没给就用“聪明、好奇、没有话题先验知识的普通读者”；只问假设已知什么 / must ground 什么 / can_skip 什么 / reader_goal / title_promise。
- **reader_contract sidecar 前置**：writer 开头输出 `<!-- reader_contract: {...} -->`，runner 抽到 `reader_contract.json`；`can_skip` 是硬切清单，正文出现就删或缩成一句备注。
- **写前内容地图**：一句话整体承诺 → 3–6 步读者路径 → 内容取舍/合并/调序 → 每层一个组织维度 → 术语/数字预算 → 图计划 → 开头框架。
- **标题 = 主题 + 整体收益/范围**：清楚第一、钩子第二；必须包含读者在找的主题/对象；不用内部数字/窄机制/行话；3 秒陌生人能说出“这是什么、我为什么读”。
- **开头先给框架**：这是什么、读完得到什么、整体路径；钩子放在框架里，不要用细节代替框架。
- **H2 / 结构**：同一层只能一个维度（阶段 / 肉类 / 概念 / 问题）；需要另一个维度用表格/H3；最后一节不能是“最后/总结/结语”。
- **技术解释用概念阶梯**：目标 → 它做什么 → 怎么运作 → 直觉做法 → 为什么失败 → 真正原因 → 该怎么做 → 代价；一个概念一次，先现象后名字。
- **有效数字**：只留强数字/必要数字；每个数字要能说明“是什么 / 说明什么 / 为什么需要”；社媒宁少勿多，宁可没有；实现数字压成结论/方法/大致过程或删；表格列数字，正文不复述。
- **术语**：同一东西全篇统一一个说法；3–5 个 essential；标题/H2 不放术语；中文为主，英文括号一次；实现细节 cut/footnote。
- **图**：每张图回答一个读者问题；caption 写“看哪里 + 这说明什么”；隐喻图无法映射就删。
- **写完做一次陌生人通读**（同一次 writer 内，最多一轮）：标卡点/无效数字/未落地术语/标签 H2/看不懂的图/表格复述；对照 reader_contract 检查 can_skip/must_ground/reader_goal；不默认加 editor/checker。

## 6. Request / 长度策略（不写死数字）

`WritingRequest` 由前端 prompt 驱动：

```json
{
  "forms": ["wechat_article", "xiaohongshu_note"],
  "platform": "wechat",
  "audience": "...",
  "length": "default | short | medium | long",
  "angle": "...",
  "must_include": ["..."],
  "must_avoid": ["..."],
  "language": "zh"
}
```

> 2026-11-06：`forms` 是写作引擎的请求形状；**产品层默认只填一个 form**，多 form 是内部/调试形态。产品是聊天式按需生成，不是 bundle 工厂。

规则：

- **不写死字数、H2 数、段落数、镜头数、脚本时长。**
- request 给了长度/结构要求 → 服从 request。
- 没给 → 用 form 默认；默认随视频时长/内容量调整。
- Planner 把 request 变成 per-form brief；brief 是护栏，不是 section schema。
- Writer 决定实际长度/结构；内容讲清楚就停，不硬凑。

## 7. 视觉链路

- **真实图示优先**：content manuscript 里的 `图示 N` + `figures/...` 是可用素材；能证明/展示文字说不清的东西才用。
- **SVG 占位符**：三步以上流程、三层以上分类、两条轴/两把尺子、分支对比；长文最多 2 个/篇，社媒按需；Writer 只写 `<!-- svg: 一句话关系 -->`，不写 SVG。
- **SVG 渲染**：模型返回图表 JSON 规格 → 本地确定性渲染；标注“示意”；不引入新数字/事实。
- **caption**：只写“看哪里”，不复述正文。
- **没有合适图**：文字/表格说清楚，不硬编画面。
- **展示页**：静态 HTML + CSS，响应式、可读、图表/SVG 正常显示；内容验收通过后再做。

## 8. Harness 与 artifacts

| Artifact | Producer | Consumer |
|---|---|---|
| `content.md` + `figures/` + `content_sha256` | substrate v1 → content manuscript（确定性） | planner / 所有 writer |
| `lead_plan.json` | Lead Planner（1 次模型调用） | orchestrator / writers |
| `task_plan.json` | orchestrator（确定性 DAG） | RunStore / 观测 |
| `article.md` / `note.md` | 对应 writer（各 1 次） | bundle / 用户 |
| `response_meta.json` | writer | 观测 |
| `bundle_manifest.json` | orchestrator | 评测 / 作品集 / 面试 |
| `llm_calls.jsonl` | DeepSeekLLM + RunStore sink | 观测 / replay |
| `tool_calls.jsonl` | ToolExecutor + RunStore sink | 观测 / 面试 |
| `decision_records.jsonl` | orchestrator | 观测 / 面试 |
| `working_memory.json` | orchestrator | 当前 run |
| `artifact_board.json` | orchestrator | 一 writer 一 artifact 约束 |
| `semantic_memory.json` | orchestrator（只读指针） | 多 form 复用 |
| `publish_review` | 人工 | 发布门 |

### 8.1 记忆

- **语义记忆**：content hash + figure catalog + skill registry；只读，不覆盖。
- **工作记忆**：当前 run 的 stage / artifact / budget / open questions。
- **程序性记忆**：skill 库（core + form layer）。

### 8.2 工具

- `compile_content`：content + figures 落到 run 目录；返回 hash / chars / figure count。
- `inspect_output`：文件、图路径、结构计数；只做 plumbing 报告，不做质量门。
- `assemble_bundle`：bundle.md + manifest。
- 每个工具有 ToolSpec、超时、幂等、允许角色、真实回执。
- MCP 只做薄 adapter，有真实 consumer 才加。

### 8.3 评测

> 2026-11-06：评测口径已重写，完整定义见 [jd-mapping-2026-11.md](jd-mapping-2026-11.md) §4。这里只留写作引擎视角的摘要。

- 数据集：capability set（2 视频 × 3 形态）+ regression set（失败样本）；版本化、去污染。
- 指标：任务完成、事实/数字保真、平台适配、跨形态一致、trajectory、pass@1/pass^k、latency、tokens/cost、error rate。
- 方法：deterministic checks + trajectory checks + 窄 rubric LLM judge；judge 用人工标注校准；2 次聚合。
- 回归：固定 cases + snapshot/replay；prompt/skill/model/tool schema 改动跑回归；capability vs regression 分开。
- 用户人工验收是唯一发布门；不跑 30 judge；不伪造 reader test / 线上 A/B。
- P4 deterministic + grounding candidate harness（2026-11-07）：`evals/product_v1/`，只读 run artifacts，输出可复跑报告；不评 writing 质量，回归门禁/pass@k 后续，不伪造。

### 8.4 Replay

- `ReplayLLM` 按 `(stage, key, input_hash)` 回放。
- `--replay-from <run_dir>` 复跑同一 bundle；hash 不一致显式报错。

## 9. JD 映射

完整表见 [jd-mapping-2026-11.md](jd-mapping-2026-11.md)。摘要：

> 2026-11-06：下表是写作引擎视角；**产品目标**（LibreChat + MCP + LangGraph + 评测）见 [architecture.md](../architecture.md) 和 [jd-mapping-2026-11.md](jd-mapping-2026-11.md)。旧“评测 = per-form cases + 结构报告”已过时。

| JD 能力 | 本项目落点 |
|---|---|
| 多 Agent 编排 | Lead Planner + specialist writers（planner-executor，不是 supervisor） |
| 任务规划/调度 | TaskPlan DAG + stage 状态 + partial/failed；产品目标用 LangGraph 工作流 |
| 工具调用 | ToolRegistry/Executor + receipts；产品目标用 MCP + function calling |
| 记忆 | content hash / figure catalog / skill 库 / working memory；产品目标加用户画像/历史 |
| RAG/检索 | 内容稿 + figure catalog + per-form view 的确定性检索；不做向量库全栈 |
| 评测 | **不是 per-form case + 结构报告**；2026 口径见 [jd-mapping-2026-11.md](jd-mapping-2026-11.md) §4（数据集/指标/judge 校准/trajectory/回归/pass^k） |
| 观测/成本 | llm_calls / tool_calls / decisions / usage；产品目标加 LibreChat Trace Viewer/run 面板 |
| 决策/Trace/Replay | DecisionRecord + RunStore + ReplayLLM |
| Human-in-the-loop | 写作引擎暂无 publish gate；产品目标加验收门/LangGraph interrupt |
| Prompt/Context | core skill + form layer + content manuscript + plan brief |
| 工程 | Python 包 / CLI / pytest；产品目标加 MCP/FastAPI/LibreChat |

## 10. 开发阶段

> 2026-11-06：下表是**写作引擎历史阶段**（产品 v1 之前）。产品路线见 [architecture.md](../architecture.md) §8；不要按本表的 Phase 4 展示页/Phase 6 作品集当产品方向。

| Phase | 内容 | 输入 | 输出 | 验收 |
|---|---|---|---|---|
| 0 | 上下文文档清理 | 交接文档 + 代码 + JD 调研 | 本文件 + JD 映射 + 干净入口 | 用户确认方向 |
| 1a | 公众号写法调研 + 汇报 | 本地/GitHub 开源 + 被否文章 + `video-article` | 写法方案 | 用户确认后写 skill |
| 1b | 公众号 skill + 跑 2 视频 | content manuscript + skill | 2 篇公众号稿 | 有图/表/SVG；用户验收 |
| 2a | 小红书写法调研 + 汇报 | 本地/GitHub 开源 | 写法方案 | 用户确认后写 skill |
| 2b | 小红书 skill + 跑 2 视频 | content manuscript + skill | 2 篇笔记 | 用户验收 |
| 3 | 编排与 harness | planner skill + form catalog | lead_plan/task_plan/tool_calls/decisions/bundle | 动态选择可查；失败 partial |
| 4 | bundle + 展示页 | 2 视频 × 多 form | bundle.md / HTML | 页面美观；用户验收 |
| 5 | 短视频脚本（**暂不做**，后续有需要再加） | 时长讨论 + 调研 | skill + 2 脚本 | 用户验收 |
| 6 | 评测/作品集 | 全部产物 | eval cases + 作品集 | 可复跑 |

**2026-11-06 状态**：Phase 0–3 已完成；Phase 4 的 bundle 已完成（`bundle_BV17_social_05` / `bundle_BV1ix_social_04`），展示页未做；Phase 5 视频脚本暂不做；Phase 6 评测/作品集未做。`long_article` 尚未接进 bundle。
**2026-11-06 产品层重定义**：bundle 不再是产品卖点；产品按需一种形态，目标是 LibreChat + MCP + LangGraph + 排版/导出 + 人工验收（见 [architecture.md](../architecture.md)）。写作引擎保留，作为产品 service 的核心；本文件的 orchestrator/CLI 是当前实现，不是最终产品壳。

## 11. 非目标

- 不做 editor/checker/草稿阶段；每个产物一次 writer。
- 不加词表、validator、质量硬门。
- 不做 per-form pipeline。
- 不跑 30 judge；不伪造 reader test/A/B。
- 不做向量数据库全栈/MCP 生态/K8s/微调，除非有真实 consumer。
- 不自动发布；不 commit/push。
- 不写死字数、H2 数、段落数、镜头数、脚本时长。
- 不按单篇调参；≥2 视频/文体复现才改通用层。

## 12. 开放问题

- 短视频脚本暂不做；后续有需要时再讨论时长和平台。
- 社媒是否只做公众号 + 小红书，还是还要微博/知乎/thread（默认先这两个）。
- 展示页的视觉方向（干净技术感 / 杂志感 / 平台卡片感）。
- MCP 薄 adapter 的优先级（JD 需要才做）。
- 深度文章的后续优化点（等社媒稳定后一并做）。
