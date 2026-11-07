# AGENTS.md — 全局规则 / 护栏

本文件是任何 agent 的防跑偏入口。**先读 [docs/product-v1-chat-studio.md](docs/product-v1-chat-studio.md)（产品 v1：聊天式内容工作台）+ [architecture.md](architecture.md) §0–§9（目标架构/当前代码），再读本文件护栏，然后读 [docs/writing-v5-architecture.md](docs/writing-v5-architecture.md)（当前写作引擎）。** 旧 handoff、旧 roadmap、旧 JD 表是历史，不是方向指令。

## 1. 事实源与边界

- **产品**：2026-11-06 已定义 v1——聊天式内容工作台。用户给视频 + 写作要求，Agent 按需写一种形态，聊天内预览/修改/验收。目标壳是 LibreChat + MCP + LangGraph + 排版/导出。
- **当前代码**：substrate v1 + `writing_v4` 写作引擎（planner/orchestrator/writer/skills/tools）+ **P1/P2 产品原型**（`mcp_server.py` / `preview_server.py` / `integrations/librechat` / `integrations/xhs` / `integrations/pdf`）；LangGraph/评测未接。`architecture.md` §4 有 current vs target。
- **写作引擎事实源**：[docs/writing-v5-architecture.md](docs/writing-v5-architecture.md)。`architecture.md` 文末附录是 v3 机会地图，不是当前实现。
- **产品/UX 事实源**：[docs/product-v1-chat-studio.md](docs/product-v1-chat-studio.md)；UI 细节 [docs/ui-design-2026-11.md](docs/ui-design-2026-11.md)。**bundle 是内部/调试产物，不是产品默认输出。**
- **JD 事实源**：[docs/jd-mapping-2026-11.md](docs/jd-mapping-2026-11.md)。旧 roadmap 的 JD 表（含“评测=per-form case+rubric”）已过时，不要用。
- **复用事实源**：[docs/reuse-stack-2026-11.md](docs/reuse-stack-2026-11.md)。LibreChat（MIT）是选定产品壳；AGPL/BUSL 只作设计参考。
- 当前快照：`HANDOFF.md`/`STATE.md`；历史：`handoffs/`，只追加。

## 2. 写作硬规则

> **2026-11-05 修订**：新 form 的 writer 只忠于内容想表达的意思和范围；不做核实、不写“未证实/待核”、不加词表/检查；writer 不知道内容来自视频/素材包。旧的“证据优先/核实分离”只作背景，不进入新 skill 的 prompt。以下旧条目不删除，但新 form 以本条为准。

- **Writer 不知道来源**：writer 只拿到「这件事的完整内容」，不知道是视频/素材包/内容稿/转写；正文不出现来源/工作痕迹。
- **不核验内容本身**：不挑内容的错、不写“未证实/待核”、不做百科/论文/体检报告；只处理已有内容 + 用户明确提供的补充/联网调研（未来可能有）。
- **证据优先**：视频事实/数字/引语/说话人只来自 substrate evidence；模型知识只解释/类比/组织；不伪造。
- **读者体验等价 / 标题 TOC / 视觉优先**：未看视频的读者获得≈同等认知与体验；标题/H2 能当目录；能用图/表/帧说明的结构不堆长文。
- **写作层只保证“视频有就写，没有就不写”**：这是对视频内容的忠实，不是核实世界。视频说假设/单次演示，保留 scope；视频说 X，不要升级成“官方/已证实”。**“未证实”不是写作层的事**；不要每句“视频称/未核实”，不要写成论文/百科/体检报告。judge 的 P5 管红线；写作层不管。
- **主语是内容，不是视频**：模型采用并组织 substrate 内容来表述；不需要“知道自己在总结视频”，也不要显式说“视频里/作者说”，除非真的需要区分观点/事实或指演示。source line 只做一行出处。
- **Writer 是产品，检查是地板**：先写得好；不要用 validator/规则怪谈/多 stage 去“保证”质量。
- **只对写作逻辑负责**：写作层负责组织、表达、结构、范围、文风；不核实世界、不给素材挑毛病、不把源材料冲突写成纠错清单。允许围绕原文语义/结构做补充、重写、修饰、精简；不新增事实/机制/因果。
- **Skill 优先**：角色/读者/方法/示例/self-review；不用词表/规则怪谈。
- **多文体 = 多 Skill/View**：不为每个文体加 body/validator/gate。
- **容量 advisory**：不做固定 length/focus 硬门；只作预算/截断/审计。
- **证据带上下文**：不拍平成 claim 列表，不拆成失去上下文的句子碎片。
- **ASR 为主**：关键帧在 ASR 关键节点附近挑；`real_frame`/`text_experiment`/`no_demo`；生成图不当视频证据。
- **Reader/Audit 分离**：reader 无内部 ID/citation/时间码/审计语言；来源归属按读者影响判断，不按词表。**核实/审计与正文绝对分离**；“未证实”不是正文该管的事，不要每句“视频称/未核实”。
- **失败一等**：partial/unknown/insufficient evidence 明确记录；不静默降级；不自动发布；人工 `publish_approved` 是唯一发布门。
- **不单例适配**：≥2 视频/知识形态/文体结构复现才进通用层；不按单条 finding/单篇/单个例子调参；不手改单篇文章；skill 里不能出现某个视频/产品/人物的具体内容；例子匿名。
- **复用优先**：本地 skill/知识文档 → 开源项目 → 自己写；借逻辑不抄文本，查 license，不造轮子。
- **评审成本**：不要再跑 5 persona × N 篇的 30 份 subagent 评审；太贵，收益递减。需要外部视角时做小规模、针对性的单 persona 抽查。

## 3. 输入与安全

- `data/`：有效只读输入；不改写；`data/cookies/` 不读、不入库、不外传。
- `参考素材/skills/`、`参考素材/skills_downloaded/`：只读；复用前查 license；不运行仓库内脚本；不把其中示例当本项目事实；不照搬与证据优先冲突的 pipeline。
- `REFERENCES.md`：本地参考/证据的 git 可见索引。
- 不自动 commit/push/publish；不伪造 reader test/A-B；不编造画面/生成图当证据。
- 复用开源/第三方 skill 前审 license、安全、维护状态；借逻辑，不抄文本。**嵌入代码优先 MIT/BSD/Apache；AGPL/BUSL 只作设计参考，除非用户同意合规。**

## 4. 上下文维护

- 核心入口：`CLAUDE.md`（入口/阅读顺序）、`docs/product-v1-chat-studio.md`（产品）、`docs/ui-design-2026-11.md`（UI）、`architecture.md` §0–§9（目标架构/当前代码）、`docs/writing-v5-architecture.md`（写作引擎）、`docs/jd-mapping-2026-11.md`（JD）、`docs/reuse-stack-2026-11.md`（复用）、`AGENTS.md`（护栏）。
- 断点/换 session：更新 `HANDOFF.md`（当前任务/接手点）和 `STATE.md`（分支/代码/测试事实）；方法/评测变化还要更新 `docs/writing-rebuild-brief.md`。
- 历史交接放 `handoffs/<date>/`，只追加，不改旧快照。
- `architecture.md` 只写设计；发现架构问题先报告，确认后再改。
- 文档冲突：先报告，不静默改架构。`docs/README.md` 有 current vs historical 索引。

## 5. 开发纪律

- 先想每个步骤的输入/输出：是否最有效、最清晰、最符合该阶段和整体 workflow；输出是否结构化、低摩擦、能被下一 stage 低成本消费。模型调用尤其如此。
- 证据 vs 编辑：视频事实/数字/引语只来自 evidence；模型知识只解释/类比/组织；不伪造。
- 读者优先，不是 coverage：一个控制性 idea、一条机制、具体例子/画面、边界；不是把视频每段都搬。
- Skill 优先，不堆规则：用角色/读者模型/方法/示例/self-review；不要为单条 finding 加 validator/词表/硬编码 gate。
- ≥2 视频/文体复现才进通用层；不按单篇调参；不手改单篇文章；不硬编码个例。
- trace/成本/状态：prompt/system/user/raw/usage/latency/finish_reason/validation/decision 可查；partial/unknown 显式；不静默截断。
- 有界 loop：一次修复；不做无限“再修一轮看看”。
- 不要过度离散：关系/连续性/上下文是写作的一部分；不要为了“结构清晰”把内容切成孤立 claim/表格/小节。
- 先测后调：改模型/参数/prompt 前先有 before/after；同一 request + 盲评；不用“测试通过”代替读者质量。
- 不伪造：不伪造 reader test/A/B；不编来源/数字/画面；不把模型/模拟盲读写成真人；不自动发布。
- 改文档：architecture 只写设计；HANDOFF 写当前快照/接手点；STATE 写事实；历史只追加。
- 遇到冲突：先判断是设计/实现/证据/评测问题；不要用加字段/加 stage/加 validator 掩盖。发现真实阻塞先报告，不静默改 substrate/架构。

## 6. 阶段门（2026-11-06）

- 当前方向：产品 v1（聊天式内容工作台）。目标壳 LibreChat + MCP + LangGraph；**P1/P2 原型已跑通**（LibreChat + MCP server + preview server + `review_artifact`；缓存内容 → 聊天 → 计划卡 → 一次 writer → 预览/导出）。下一步：P3 LangGraph + HITL + 观测；P2 内容层遗留（小红书标题、公众号数字/图表）按用户指示最后改。
- **产品按需一种形态**；bundle 是内部/调试产物，不是产品默认输出。多形态 = 多次请求。
- **用户 run 数据 / 开发评测数据 / 简历数据分开**：产品只展示本次 run 的 trace/成本/状态；eval 在独立 dashboard；简历只取 eval 报告。
- 当前没有已验收的产品基线：`video-article` 是写作引擎底座；公众号/小红书“大致验收”；旧 P1/supervisor/demo/词表已删除，不要恢复。架构推进由用户裁决。
- 用户边界：一个产物一次 writer；没有草稿/editor/checker/词表/核实；writer 不知道内容来自视频/素材包；输入只是“这件事的完整内容”；用户验收质量和架构。
- **不写死字数、H2 数、段落数、镜头数、脚本时长**；request 优先，没 request 用默认。
- substrate v1 已冻结；非必要不改；发现真实阻塞先报告。
- 质量门/评测：用户 manual acceptance 是唯一发布门；不跑 30 judge；不伪造 reader test；评测先预留，产品稳定后再做。
- 先测后调；同 request；不按单条 finding/单篇调参；不手改单篇文章。

## 7. 素材消费（2026-11-04）

- 默认路径：素材层产出 `content.md` + `figures/`；Writer 只读连续内容，不知道这是内容稿/视频/素材包/管线。
- **不硬截断**：`max_chars` 只 advisory；`over_budget` 记录；caption cap 报告 `caption_truncated`/`caption_full_chars`；不静默删内容。
- **写作层不核实世界**：视频有就写，没有就不写；不每句“未核实”；source line 只做出处；P5 只是质量红线概念，不等于要跑 30 份评审。
- **不按单篇修**：任何 view/排序/覆盖/格式修复都必须跨 ≥2 视频复现；不手改单篇文章来“证明”方法有效。
- **substrate v1 只读**：writing 层通过 [docs/substrate-v1-freeze.md](docs/substrate-v1-freeze.md) 的接口使用它；非必要不改。

## 8. 产品 / 数据 / 复用护栏（2026-11-06）

- **产品不是作品集**：首页是 chatbox；不发生成所有形态的 bundle 营销；不把架构页/评测页放进产品导航。
- **产品层与写作引擎分开**：LibreChat 只做壳；写作逻辑在 Python MCP 服务；LangGraph 只跑工作流；不把 pipeline 塞进 LibreChat 核心。
- **数据分层**：用户实时可观测（run trace/成本/状态）≠ 开发评测（数据集/指标/回归）≠ 简历数据（eval report）。不混用、不伪造。
- **JD 不为关键词造假**：Function Calling/MCP/LangGraph/Evaluation 必须有真实 consumer 和可复跑数据；没有就写“未实现/不追求”。
- **评测口径**：数据集、指标、judge 校准、trajectory、回归门禁、pass@k/pass^k、失败→数据集闭环；不是 30 judge，不是一次结构报告。
- **复用**：LibreChat/MCP/LangGraph/Pandoc/md2wechat/卡片库；先审 license、pin 版本、留替换边界；不把 AGPL/BUSL 默认嵌入。
- **部署**：先缓存内容跑通产品；视频转录最后接；不为了 demo 重跑全量视频。
