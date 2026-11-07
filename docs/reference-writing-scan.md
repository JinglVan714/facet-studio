# Writing / Agent Skill 参考扫描（2026-10-31）

> **2026-11-05 session 2**：本文件是历史参考扫描，不是当前基线；当前架构见 [writing-v5-architecture.md](writing-v5-architecture.md)。
> **2026-11-06**：当前复用栈见 [reuse-stack-2026-11.md](reuse-stack-2026-11.md)；本文件只作历史扫描。

> 用途：给后续 session 的参考资料，不是 v3 基线。
> 来源：本地 `参考素材/skills/` 17 个仓库 + `bilibili-render-pdf` 的只读扫描；web 的 STORM / WriteHERE / Agent Skills 官方材料。
> 标注：**[verified]** = 直接读了文件/官方页；**[secondary]** = 搜索摘要，未逐代码核实；**[unclear]** = 仓库未说明。

## 1. 结论

- 开源 writing 项目的主流是 **prompt 注入素材**：整段原文、检索片段、摘要、大纲、记忆文件；多 agent 用 artifact/task context 传递。
- **Agent Skills** 是另一种消费方式：metadata 预加载，`SKILL.md`/references 运行时读，scripts 执行，结果进上下文；不是一次性全塞。
- 结构化 evidence 不是零：**wewrite**（claims.yaml C1 IDs/type/source_ids/status/boundary）、**Norman**（Source ID/evidence map/chapter packet）、**zenstory**（source/index refs、chapter spans）都有；但**没有** video transcript → claim/evidence quote/timecode/frame → 一个 Writer 的完整链。
- 最接近视频的是 `bilibili-render-pdf`：CC/Whisper 字幕、时间戳、>20min 或 >300 条字幕切段、并行 segment subagents、最后整合；它是 video→teaching notes，不是文章。
- 这对我们的含义：保留 video-native evidence/frames/provenance 的差异化；借 wewrite 的 claim ledger、Norman 的 evidence packet、zenstory 的 index/resume、bilibili 的切分阈值、Agent Skills 的 progressive disclosure。

## 2. 本地 17 个仓库（按机制）

| 仓库 | 类型 | 素材如何到模型 | 结构化 evidence？ | 关键文件 |
|---|---|---|---|---|
| `aislinn-yang__rednote-writing-skill` | skill | 用户粘贴片段/链接/截图；examples 做 voice few-shot；draft → checks | 否 | `SKILL.md:26,31,39-57`; `examples.md:1-16` |
| `blader__humanizer` | skill | 只改写输入文本，不摄入素材 | 否 | `SKILL.md:34-39,43,49-53` |
| `conorbronsdon__avoid-ai-writing` | skill + JS detector | 只检测/改写，保留 claims | 否 | `SKILL.md:30-32,62-77`; `detector/patterns.js` |
| `crewAIInc__crewAI-examples` | demo collection | 多 agent sequential；上一任务输出经 `context`；search/browser/file/PDF tools；outline crew → chapter crews | 否 | `crews/screenplay_writer/config/tasks.yaml:3-5`; `flows/write_a_book_with_flows/.../main.py:35-87` |
| `d-wwei__great-writer` | skill | 全文/研究材料进 prompt；web search/fetch；research summary → outline gates；project memory | 否 | `SKILL.md:105-113,169-213`; `core/writing-memory.md:41-52` |
| `dexhunter__seedance2-skill` | skill | 不摄入文章；用用户 assets/`@` refs 构造视频 prompt | 否 | `SKILL.md:14-21,74-93` |
| `imraywang__wewrite` | skill suite + CLI | search/fetch → `brief.yaml` + `claims.yaml` + `sources.yaml` → draft → review；file-to-file writer 拿 brief | **是**；C1 IDs、source_ids、status、boundary；sources hash IDs | `skills/wewrite/SKILL.md:82-90`; `skills/wewrite-write/references/article-brief.md:40-55`; `src/wewrite/sources.py:52-96` |
| `LearnPrompt__awesome-seedance` | skill collection | prompt/template 库选择；production brief/plan.json；不摄入文章 | 否 | `agents/skills/seedance-prompt-library/SKILL.md:8-25` |
| `Mouriya-Emma__writing-pipeline-zh` | skill suite | 全文 → topic → outline → draft → article；明确支持视频字幕 | 否 | `skills/writing-pipeline/SKILL.md:12-35`; `skills/wp-write/SKILL.md:18,120-162` |
| `NEKOINEKOI__tomoai-longform-skill` | skill | topic/material → title → outline → section drafting；单 agent | 否 | `SKILL.md:8,119-242` |
| `Norman-bury__research-writing-skill` | skill suite/plugin | scholar search/PDF → evidence map → paragraph blueprint → 每章 fresh agent + evidence IDs | **是**；Source ID/usable fact/supported claim/citation slot/risk | `skills/evidence-driven-writing/SKILL.md:20-47`; `skills/writing-chapters/SKILL.md:46-68` |
| `THUDM__LongWriter` | research/library | plan → paragraph subtasks；每步 instruction + full plan + 已写全文；不摄入 source doc | 否 | `agentwrite/plan.py:56-63`; `agentwrite/write.py:56-85` |
| `VincentOld__stop-slop-zh` | skill | 只风格改写 + 打分 | 否 | `SKILL.md:129-155` |
| `wordflowlab__article-writer` | CLI + skill | crawl → markdown KB；运行时 `Grep`（无 embedding）；brief/spec/materials → draft；outline 模式 | 部分；source URL/date，无 IDs | `templates/commands/write.md:667-687`; `memory/README.md:10-32` |
| `yaoleifly__wechat-writing-style` | skill | 只风格指导，不摄入素材 | 否 | `SKILL.md:73-82` |
| `zenstory-ai__drama-skills` | skill suite | chapter/heading index + line spans → per-chapter extraction → aggregation → episode candidates；batch subagents | **provenance**；source_ref/index_ref/chapter spans/candidate IDs | `skills/short-drama-novel-analyze/SKILL.md:54-127`; `scripts/novel_index.py:244-273` |
| `zwzhangyu__ai-agent-lab` | demo lab | CrewAI task context；LlamaIndex RAG（DashScope + Chroma）；retrieved chunks 进 QA prompt | 部分；file/page/URL/score | `llamaindex-rag/study/llamaindex-rag/03_retrieval.py:8-13`; `.../rag-knowledge-chat/app/services/chat_service.py:13-36` |
| `bilibili-render-pdf`（本地 skill） | skill | CC 字幕/Whisper SRT + frames → segment subagents → LaTeX notes；保留 timestamp | 部分；figure/dialogue time provenance | `SKILL.md:99-104`（>20min/>300 条切段、overlap、整合） |

## 3. Web 开源项目

| 项目 | 类型 | 素材消费方式 | 结构化 evidence？ |
|---|---|---|---|
| **STORM** [verified] | research → article | 每 section 用 outline 生成 query；检索 snippets 编号拼成 `info`，限制 1,500 words，送 `WriteSection`；outline 只用于检索；citation `[1]`，无 URL/evidence graph | 否；编号 snippets |
| **WriteHERE** [verified high-level] | recursive planning | retrieval / reasoning / composition 任务，memory/workspace、task DAG；README 未说明具体 prompt 数据路径 | unclear |
| **Agent Skills** [verified] | skill framework | metadata 预加载；SKILL.md/references 运行时读；scripts 执行，结果进上下文 | 否 |
| **InkOS / WenShape / webnovel-writer** [secondary] | long-form agent | 搜索摘要称 planner/composer、SQLite/时间线记忆、BM25/词重叠、context pack、outline is law | 有 memory/context pack，不是 claim/evidence graph；未代码核实 |

## 4. 跨项目模式

1. Outline/plan-first 是默认。
2. 文件式状态是实际记忆（outline/draft/notes/progress/claims/sources）。
3. 切块多为结构性（时间/章节/段落），少数 token chunking。
4. 检索多为工具调用或 Grep，不是向量 RAG；向量 RAG 是少数。
5. 结构化 evidence 稀有；wewrite/Norman 最强，zenstory 是 provenance，bilibili 是 timestamp。
6. 多 agent 用 artifact/task packet 传递，不共享聊天。
7. 风格类 skill 是后处理器，不摄入素材。
8. 显式 token/长度预算只有少数项目（wewrite、LongWriter、bilibili、zenstory、crewAI、wordflowlab）。

## 5. 与我们的关系

- **差异点**：video-native evidence（transcript → claim → exact quote/timecode → frame → provenance）+ lean view/index+parts + audit sidecar；参考集里没有完整同链。
- **可借用**：
  - wewrite：claim ledger（source IDs/status/boundary）用于 writer view 的边界 claim；不要全量注入。
  - Norman：长文/多章时 evidence packet + fresh agent；我们已有 parts 骨架。
  - zenstory：chapter/line index + progress/resume；我们的 segment 索引还没有 resume。
  - bilibili：>20min/>300 字幕切段、overlap、并行；我们的 `--writer-part-max-chars` 方向一致。
  - Agent Skills：full pack 放磁盘，Writer 按需读 index/parts；避免一次性注入。
- **不要照搬**：全文注入 + 无 claim 层的 pipeline；参考 skill 的整条链不是 v3 基线。

## 6. 来源

- 本地路径：`参考素材/skills/<repo>`、`C:/Users/30279/.claude/skills/bilibili-render-pdf/SKILL.md:99-104`。
- [STORM](https://github.com/stanford-oval/storm) / [article_generation.py](https://github.com/stanford-oval/storm/blob/main/knowledge_storm/storm_wiki/modules/article_generation.py)
- [WriteHERE](https://github.com/principia-ai/WriteHERE) / [arXiv:2503.08275](https://arxiv.org/abs/2503.08275)
- [Anthropic Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)
- [InkOS](https://www.everydev.ai/tools/inkos) / [WenShape](https://www.sourcepulse.org/projects/25774867)（secondary）
