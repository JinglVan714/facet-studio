# Writing Skill Study（完整设计 v1.0，skill v1.1）

> **2026-11-05 session 2**：已由 [writing-v5-architecture.md](writing-v5-architecture.md) 取代；本文件是历史学习/设计笔记，不是当前方法。

> **2026-11-03 历史状态**：这是 skill 学习/设计笔记，不是当前 writing 方法。当前写作架构以 [writing-v5-architecture.md](writing-v5-architecture.md) 为准；本文件只作参考学习历史。
>
> 状态：学习/设计笔记；完整 skill v1.1 已落在 `skills/writing/reader_first_explainer/`（含 planning/structure/visuals/evidence references），视觉层已接进 pipeline；EditorialBrief 契约见 [writing-planner-position.md](writing-planner-position.md)。早期草稿的 BV1yb developer read 不通过；完整版加入 TOC 标题 / video-equivalent 体验 / visual-first / 简洁 / model knowledge explanatory。**未做 reader test/A-B，不是已验收基线。**
> 日期：2026-11-01（2026-11-02 增补 planner/brief）
> 范围：本地 `参考素材/skills/` 17 个仓库 + `bilibili-render-pdf` + Agent Skills 官方资料。
> 下一步：按 EditorialBrief 契约迁移 Planner/Writer → 重跑 3 篇 + brief 盲审 → 真实 reader test/A-B（5+ 人）。

---

## 0. 一句话

参考仓库里没有“一个证据库→多文体”的完整实现；最接近的是三条可组合的线：

1. **Mouriya 的“核心流水线 + 可选风格 skill + 中间文件”**：阶段只定义动作/门控，风格 skill 只提供体裁取值，文件逐段收窄。
2. **great-writer 的“单入口 router + modes + 阶段门”**：一个 SKILL.md 路由，按需加载 core/modes，不把所有文体塞一个 prompt。
3. **avoid-ai-writing 的“router + handoff envelope + 确定性 preservation verifier”**：只传意图/范围/保护约束，FAIL 只回修一次。

对我们的含义：**借结构/契约/片段，不搬整条 pipeline；第一个 skill 写短、分层、以证据纪律和读者模型为核心。**

---

## 1. 来源 / license / 借什么

| 来源 | License | 借什么 | 不借什么 |
|---|---|---|---|
| `bilibili-render-pdf` | 本地未见 LICENSE | 教学 flow（动机→主 idea→机制→例子→takeaway）；长视频分段；帧候选/完整状态/可读性/时间 provenance；最终 synthesis；能重绘就重绘 | LaTeX/PDF 专属；无状态/无 coverage；图越多越好；305 行单体；视频当主角 |
| `aislinn-yang__rednote-writing-skill` | MIT | examples 锚定 voice；写/检分离；冷读子 agent；标题/封面流程 | 平台违禁词/标题公式当全局 validator；账号定位 |
| `blader__humanizer` | MIT | 结构优先的 AI 痕迹清单（作为 examples/eval） | 词表式 blacklist 进 core |
| `conorbronsdon__avoid-ai-writing` | MIT | handoff envelope；protected content；preservation verifier；一次 repair | detector 规则清单当 core；平台规则当全局 |
| `crewAIInc__crewAI-examples` | 本地未见 LICENSE | 角色/context 传递；Pydantic 结构化产物；有界 self-evaluation loop | 5 角色顺序链；每章重读整本 outline |
| `d-wwei__great-writer` | MIT | 单入口 router + modes；读者立场/核心张力/结构先行；memory | 6-phase gate；字数/句长硬规则 |
| `dexhunter__seedance2-skill` | MIT | 主体+场景+动作+运镜+时间分段+音频+风格；@ 引用角色；negative 块 | 平台参数硬编码；整条视频生成 |
| `LearnPrompt__awesome-seedance` | MIT | 模板库按 useWhen/structure/guidance/pitfalls/exampleCases 组织；plan.json/QA | 24 个重复窄 skill；整条生产链 |
| `imraywang__wewrite` | MIT | claim ledger（id/text/type/source_ids/status/boundary）；state.yaml；文件式流程；source hash | 全 ledger 一次喂；无 quote/span；CLI 静默丢 claims |
| `Mouriya-Emma__writing-pipeline-zh` | MIT | 核心阶段 + 可选风格 skill；中间文件逐段收窄；选题/大纲/写作/润色 | 四阶段 waterfall + 每阶段对抗门 |
| `NEKOINEKOI__tomoai-longform-skill` | CC BY-NC 4.0 | 只作长文/自媒体结构参考（APAG 等） | 商业交付/直接复制 |
| `Norman-bury__research-writing-skill` | MIT | evidence map；paragraph blueprint；每章 fresh agent + task packet；citation slot/risk | citation-count 质量门；全文重读 |
| `THUDM__LongWriter` | Apache 2.0 | plan → 分段；每段 instruction + full plan + 已写正文 | 每步重发全文；无证据层；二次成本 |
| `VincentOld__stop-slop-zh` | MIT | 中文 AI 味评估/五维粗筛 | 词表式规则进 core |
| `wordflowlab__article-writer` | 本地未见 LICENSE | file-to-file；工作区；KB 结构 | 无 ID/span/claim 的 Grep 当证据 |
| `yaoleifly__wechat-writing-style` | MIT | 公众号结论先行/口语化/短段/平台敏感性 | 破折号/emoji/敏感词硬规则进 core |
| `zenstory-ai__drama-skills` | MIT | 单一 index + line span；coverage；`_work/` 原子 publish；resume | “聚合永不重读原文”（对证据写作不成立） |
| `zwzhangyu__ai-agent-lab` | Apache 2.0 | 显式 context 传上游产物；CrewAI/RAG 思路 | 全量 RAG/LangChain 链 |
| Agent Skills 官方 | 官方资料 | metadata/渐进披露；SKILL.md 短；references/scripts 按需；scripts 执行不回读 | 单体 SKILL.md；全量塞入；allowed-tools 当安全边界 |

规则：MIT/Apache 保留声明；CC BY-NC 只借思路；无 license 只借方法/结构，不逐字复制；每个 skill 带 `SOURCES.md`。

---

## 2. Skill 的本质（给实现者的 8 条）

1. **Skill = 文件系统上的按需能力包，不是更长的 prompt**：`SKILL.md` + 可选 `scripts/`、`references/`、`assets/`。
2. **Progressive disclosure**：metadata 常驻；触发后读 `SKILL.md`；references/scripts 按需；未访问文件零 token。
3. **三分法**：SKILL.md 放流程/决策/默认值/检查清单/指针；references 放领域文档/schema/长 API；scripts 放确定性/脆弱操作。
4. **description 是路由器**：第三人称、含关键词、写清“做什么+何时用”；模糊/重叠会漏触发/错触发。
5. **scripts 是“执行而非阅读”**：代码不进上下文，只回 stdout；处理错误/依赖；明确 `run` 还是 `read as reference`。
6. **和 pipeline/subagent 的区别**：skill 是可复用知识/流程包；pipeline 是编排；subagent 是隔离上下文只回摘要；skill 可与两者组合。
7. **状态落文件**：progress/coverage/manifest/decisions；不靠会话记忆；resume 不重跑。
8. **质量门分两层**：可判定的走确定性校验；读者/风格走真人/清单；清单只是 advisory。

官方约束（摘要）：

- `name` ≤64 字符（小写字母/数字/连字符）；`description` ≤1024 字符。
- SKILL.md 建议 <500 行；references 一层深、>100 行加 TOC。
- `allowed-tools` 是实验性预批准，不是安全边界；Claude Code 不读 `version`，API 用 `skver` 固定快照。

---

## 3. 参考仓库的消费/状态模式

### 3.1 wewrite：claim ledger + state

- 写稿一次看 `brief.yaml` + `claims.yaml` + `sources.yaml`；审稿再看 draft + brief + claims + sources。
- claim 字段：`id/text/type/source_ids/status/boundary`；source 有 `verified/unverified/user_provided`。
- `state.yaml` 原子替换；`run resume` 恢复 active/failed；完成后核心 artifact 不可改。
- 问题：claim 无 exact quote/span；SKILL 声称喂 claims/sources，CLI 实际只读 `--brief`，可能静默丢 claims。

**借**：claim 字段/状态/来源 ID/state/resume。
**不借**：全 ledger 一次喂；无 quote；静默丢 claims。

### 3.2 Norman：evidence map + paragraph blueprint + chapter packet

- evidence map 一行一源：`Source ID | Citation | Source type | Abstract-level finding | Usable fact | Supported claim | Citation slot | Risk`。
- 段落 blueprint：`Role | Main claim | Evidence IDs | transition | Forbidden content`。
- 每章 fresh agent 只收 task packet + 相关 excerpts + evidence map + blueprint + min_chars + 拒绝项；不读整篇。
- 问题：citation-count 质量门只数标记，不验证来源存在/支持；假引用可过门。

**借**：source ID/usable fact/supported claim/citation slot/risk；slot/blueprint；chapter packet。
**不借**：citation-count 门；全文重读。

### 3.3 zenstory：单一 index + line span + coverage

- 索引是“唯一切片真源”；各阶段不得各跑正则。
- 每章只读该章 line span；聚合只读逐章 extract，不重读原文。
- `verify` 检查 sequence 连续、line span 覆盖全源；`coverage` 报 missing/unmatched。
- `_work/` 候选 + 原子 publish；`_progress.md` 固定 artifact-id；merge 拒绝未知 ID/重号/超限/冲突。
- 问题：白描是派生摘要，不是 exact quote；对证据写作不能“聚合不重读原文”。

**借**：单一索引/line span/coverage/原子 publish/resume。
**不借**：聚合永不重读原文；白描当 quote。

### 3.4 LongWriter：plan + 已写正文

- plan 把 instruction 拆成 200–1000 词/段、≤50 段。
- 每段把 instruction + 完整 plan + 全部已写文本重发；上下文线性增长、总成本近似二次。
- 无证据层。

**借**：分节连续性/plan 思路。
**不借**：每步重发全文；无证据层。

### 3.5 wordflowlab：file-to-file + Grep

- crawl → raw JSON/indexed Markdown/cache/search-index.db；写作时 AI 直接 Read/Grep Markdown。
- 无 chunk ID/claim/status；检索片段不能当证据。

**借**：file-to-file/工作区/命令边界。
**不借**：无 ID/span/claim 的 Grep 当证据。

---

## 4. 多角色 / 交接 / 输出

### 4.1 角色

参考仓库常见：Outliner/Researcher/Chapter Writer/Reviewer/Editor/Formatter/Scorer。但多数是“把一件事拆成多次模型调用”，角色间没有独立决策权。

我们的选择：

- **默认 1 Writer**；高风险才 1 次 Verifier；不设 Research/Editor/Humanizer/Reviewer 五个 agent。
- 需要长文/多章时才 sectioned Writer；每节返回 `status + claims_used/evidence_ids + draft + visual_intents + gaps`；主 agent 负责整合。
- VisualPlanner/Renderer 是媒体角色，不是写作链的必经阶段。

### 4.2 交接

- 只传下一角色需要的：intent/scope/protected constraints/evidence IDs；不重复全文。
- 有界 repair：FAIL 只回修一次，共用 pass budget；不无限 loop。
- 冷读用独立上下文：只拿初稿 + examples，不拿研究材料。

### 4.3 输出契约

| 簇 | 输出 |
|---|---|
| A 叙事/解释 | Markdown（标题/hook/section/结论）+ audit/citations + VisualPlan |
| B 分发 | JSON pack：`titles[]`、`cover_copy[]`、`body`、`hashtags[]`、`platform_checks` |
| C 时间/媒体 | `plan.json`（shots/start/end/action/camera/audio/entry/exit/references）+ copy-ready prompt |

---

## 5. 完整 skill 的设计 brief：`reader_first_explainer` v1.1

### 5.1 定位

为“想理解视频内容”的聪明读者写一篇连续的 reader-first 解释文：一个 central question、一条机制/论证链、一个演示或明确 no-demo、术语首次解释、结论做 synthesis。不是章节摘要，不是 coverage dump。

### 5.2 输入

- `request`：central question、job to be done、reader before/after、required/forbidden、language、media policy。
- `evidence_text`：compiled edited text（无 ID/时间码/claim）+ frame captions。
- 可选 `claim_view`：claim/status/scope/context（claim path）。
- 可选 `writing_brief`（editorial brief）：angle/reader/core/source question/payoff/throughline/spine/anchors/title/stance/speaker policy/cut/challenge；Writer 自己定 H2/段落/视觉意图，不把 brief 当 section schema。旧 `writing_plan` 是 legacy guardrail。
- `output_contract`：Markdown-only；长度 advisory。

### 5.3 输出

- 一个 Markdown 文章：单 H1、H2、段落；可选图片行（由代码渲染/插入）。
- 无 JSON、无 code fence、无 plan header、无 self-review、无 claim/evidence ID、无时间码。
- 直接引用必须精确；转述不加引号；数字照抄；不新增事实/专名/说话人。

### 5.4 方法

0. **Brief first**：reader/core/source question/payoff/throughline/spine/anchors/cut；没有单独 brief 时，Writer 在 before-writing 做 5 行 mini-brief。不要让 H2/visual slot 先于这些判断。
1. **Find the one thing**：central question + 单一解释目标（机制/流程/tradeoff）。
2. **Build one chain**：每步有证据；只有观察就写观察；不发明因果。
3. **Choose one demo**：真实帧只在它确实展示操作/结果且可读时用；否则 text/no-demo；不暗示视频没有的演示。
4. **Explain terms at first use**：用读者语言；不用更难术语定义术语。
5. **Conclusion is synthesis**：新增连接/判断/决策；不逐节 recap；不新增未支持的因果。
6. **Boundary only when it changes judgment/action**：说能从证据得出什么，不是列证据缺什么。
7. **ASR noise**：跳过问候/自我介绍/预告/赞助/频道 logistics；合并重复片段；不把口播碎片原样复述。

### 5.5 Evidence discipline

- 事实/数字/专名/说话人只来自 evidence；不扩写缩写/规范名/单位（除非 evidence 有）。
- 数字照抄；不四舍五入/换算/加精度。
- 引号只包精确原文；转述用普通散文。
- Editorial 句只组织/限定/综合；不引入新事实/因果。
- Reader 文本无内部 ID/citation/时间码/审计语言。
- 来源归属自然：内容作主语；只有区分观点/事实或指演示时提“视频/作者”。

### 5.6 Self-review（写进 SKILL.md）

1. 开头是否建立读者问题，文章是否回答？
2. 是否一条机制/论证链，而不是一堆 section？
3. 结论是否新增 synthesis，而不是 recap？
4. 来源归属是否做实事，而不是默认主语？
5. 每个事实是否有 evidence；是否有 outside evidence？
6. 每个引号是否精确？不精确是否去引号转述？
7. 是否有重复的动作/观察/数字？
8. 边界是否是读者向的限制，而不是证据清单？

### 5.7 Examples（原创，不复制 NC/未确认 license 文本）

至少 3 组好/坏对照：

- **来源归属**：坏：“视频作者认为它适合自动化任务。” 好：“它适合自动化任务；脚本出错会打回重改，反而增加调用。”
- **边界**：坏：“两个 encoder 内部如何对齐还没有答案。” 好：“在这组证据里，只能确定同一查询下的排序仍然可用；encoder 内部结构不是这次能回答的。”
- **caption/图**：坏：把 VLM 整屏文字复述成正文。好：一句“看这里”，正文解释机制。
- **ASR noise**：坏：复述“大家好/一键三连”。好：直接进入问题。
- **重复**：坏：同一数字在 3 段重复。好：首次解释，后文指代。

### 5.8 Rubric（人评，不是词表）

| 维度 | 问题 |
|---|---|
| central question | 读者能否说出文章回答了什么？ |
| mechanism/chain | 能否复述因果/步骤，而不是背结论？ |
| boundary | 能否说出证据覆盖/未覆盖？ |
| continuity | 是否一条线，而不是 section 拼盘？ |
| source attribution | 来源是否自然、不喧宾夺主？ |
| evidence discipline | 事实/数字/引号是否可回查？ |
| concision | 是否有重复/coverage dump？ |
| reader hygiene | 是否有 ID/时间码/审计语言？ |

### 5.9 包结构

```text
skills/writing/reader_first_explainer/
  manifest.json
  SKILL.md
  examples.md
  rubric.md
  SOURCES.md
```

先不做 references/scripts/assets；等第二个文体/真实需求出现再加。

---

### 5.10 完整版强化（2026-11-02）

早期草稿的 3 dev real 暴露了问题：BV17/BV1AC 可用但偏长，BV1yb developer read 不通过（结构/标题/无图/冗长）。完整版增加：

- **video-equivalent experience**：未看视频的读者也能复述内容、机制、关键例子/演示/画面与边界；不是 coverage 摘要。
- **TOC 标题合同**：title + H2 构成目录；4–7 个具体、平行、可独立理解的 H2；禁止“背景/介绍/总结”。
- **section promise/takeaway**：每节先明确“解决什么/带走什么”；结尾一句 takeaway。
- **visual-first**：机制/流程/架构/对比/数字优先 diagram/chart/table/real frame；真实帧只在可读且确实展示操作/结果时用；无图时说明。
- **简洁**：一段一个意思；能图/表替代的长描述删掉；不按视频时间顺序复述。
- **model knowledge=explanatory**：可解释/类比/背景；不得伪造视频事实/数字/引语。
- **rubric** 增加 TOC/framework、video-equivalent、visual-first、concision、model knowledge discipline。

bilibili-render-pdf 的对照结论：教学 flow、每节小结、图/表、最终 synthesis 值得借；但其“图越多越好/不控长度/LaTeX 专属”不能照搬。完整版保留教学结构，但加 TOC/视觉/简洁合同。

---

## 6. Skill 选择 / 状态 / 评测

- 选择：request 显式 `method_id + form_id`；registry 校验兼容；记录 DecisionRecord；不靠模型自由触发。
- 状态：`run.json`/`progress.json`/`coverage.json`/`decisions.jsonl`；长任务 resume；不重跑已完成。
- 评测：固定 request 集测“选对 skill/不误触发”；至少 2 视频 × 2 文体；central question/mechanism/boundary、binding、quote precision、timecode accuracy、unsupported、真实 reader test、cost/latency。
- 版本：skill manifest/hash；API `skver`；旧 artifact 冻结。

---

## 7. 明确不要做

- 不把参考 skill 的整条 pipeline/prompt 搬进来；只借结构/字段/片段。
- 不写 305 行单体 SKILL.md；不把平台词表/标题公式当全局 validator。
- 不设 5 角色顺序链；默认 1 Writer。
- 不每章重读全文；不把摘要/白描写成 quote。
- 不把 `allowed-tools` 当安全边界；不把 C2PA/SynthID 当真相。
- 不按单篇/单词调参；不写死字数/句长/emoji。
- 不伪造 reader test/A-B；不自动发布。

---

## 8. 下一步

1. 写 `skills/writing/reader_first_explainer/{manifest.json,SKILL.md,examples.md,rubric.md,SOURCES.md}`。
2. Dry-run：3 个 dev request 生成 system/user prompt，检查 token/结构；不调模型。
3. 真实 Writer 跑 3 case；确定性校验；人读。
4. 真实 reader test/A-B；skill v1.1；before/after。
5. 第二个文体（讲义/教程）再抽 method；不预先拆。
