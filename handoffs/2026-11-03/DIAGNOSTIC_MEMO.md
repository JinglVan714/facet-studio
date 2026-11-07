# Diagnostic Memo — writing 层现状（2026-11-03）

> **历史诊断，已废弃，不要读。** 它基于旧的 brief/verifier/repair 链；当前写作层是 `writing_v4`，入口是 [NEXT_SESSION_PROMPT.md](NEXT_SESSION_PROMPT.md)。不要把本文结论当当前基线。

> 性质：诊断，不是方案冻结；不修改代码/字段/agent/validator，不 commit。
> 方法：按 `STARTUP_PROMPT.md` 顺序读 AGENTS / operating model / architecture / substrate freeze / HANDOFF / STATE / evals / 两份只读标准 / skill / 代码；直接读 `runs/_diag/{BV17_workflow_v5,BV1AC_workflow_v10,BV1yb_workflow_v1}` 的 `reader.md`、`assets/`、`manifest.json`、`verifier_final_report.json`；用当前代码离线复算 `source_map` 与 `contract`；跑全量测试。
> 测试事实：`PYTHONPATH=src python -m pytest` → **508 passed in 5.33s**。

---

## 0. 结论先行

1. **prose Writer 不是当前瓶颈。** 三篇交付的语言、结构、具体例子都成立；binding 是干净的（facts 93/94、66/68、12/12；quotes 100% bound）。真正反复失败的是**语义闭合**：来源归属、机制/推断的 claim status、内部一致性、图注语义。
2. **最贵的两个 stage 没有形成闭环。** initial verifier 能抓到真问题并驱动 repair；但 final verifier 只读，交付稿的 residual 不再修。三篇最终都是 `partial`，而 `reader.md` 仍然照常交付。当前 pipeline 的“检测能力”明显强于“修复能力”。
3. **来源元数据不是没有，而是没取。** 帧 OCR 里已有频道、标题、日期、官方公告；`source_map` 只取 channel，且对 BV1AC 取成了截断的“的编程宇宙”。文章来源行因此把“可得的”写成“未提供”。这是最便宜、最直接的可信度修复。
4. **brief 是错误的上游来源之一。** BV1yb 的“形象第一次被翻译成用途”、“治愈系=于谦的评价”都能在 brief 里找到原文；writer 把它写进正文和 H2。brief 选标题时又看不到 skill 的 `examples.md`，于是 BV1yb 选了一个 examples 明确标为“坏”的同款匿名标题。
5. **judge v5 现在不能跑。** pack 的 new 侧直接复制自 `runs/_diag/*` 的三个 run，而这三个 run 都早于 `source_map` channel 修复、`render` caption 修复、64k verifier 修复；跑出来的分数会归因给已经不存在的代码。**先重跑当前代码、重建 pack，再跑 30 份报告。**
6. **新 workflow 相对旧 current 的增量价值尚未证明。** 旧 current（`_brief_final3`，brief + writer + visual，3 次调用）是 38.6k / 79.2k / 47.4k tokens，三篇 `complete`；新 workflow 是 7 次调用、约 148k / 200k / 186k tokens（含 repair；不含 BV1yb 的 64k probe），三篇 `partial`。新 workflow 明显改善了来源行（旧 current 三篇都没有来源行），但代价与质量增益需要 judge 证明，不能先假定。

---

## 1. 这个系统现在实际是什么

### 1.1 实际数据流（代码事实）

`src/facet_studio/writing/pipeline.py` 的实际顺序：

1. brief（full/mini；`pipeline.py:121-140`）
2. Writer（1 次；`:142-153`）
3. 确定性 validation + contract（`:205-213`）
4. **initial verifier**（`:214-227`）
5. repair（如果 binding/contract/initial verifier blocking；`:257-322`）
6. polish（`:324-362`）
7. visual planner + renderer（`:374-401`）
8. final validation + contract（`:403-414`）
9. **final verifier**（只有 `article_changed_after_verifier` 为真才跑；`:415-434`）
10. 交付 `reader.md` + assets；`final_status = partial` 如果 final verifier blocking/unverified 或 contract partial（`:435-451`）

关键边界事实：

- final verifier 是只读的，不触发 repair（`verifier.py:102-263`；`pipeline.py:415-434`）。
- 唯一一次 repair 由 **initial verifier / binding / contract**（都在 polish/visual 之前的 draft）驱动；final verifier 看到的是 polish + visual 之后的交付稿。
- visual caption/table 在 repair 之后才生成；生成后只过 validation/contract（caption 存在性），没有语义重检；final verifier 只读，不能再修。
- `final_verifier` 不是无条件运行：如果文章没有变化，它会被跳过（`pipeline.py:418`）。这意味着在 `--no-polish` 或 polish 无变化时，visual caption 可能完全没有语义审计。
- 当前 `contract` 对三篇交付稿都返回 `complete`（0 blocking），但 final verifier 分别有 5 / 3 / 6 findings；**L1 complete ≠ 语义 clean**。

### 1.2 实际成本与状态（每篇）

| run | 调用 | 实际 tokens（含 repair / 含 verifier） | 状态 | final verifier |
|---|---:|---:|---|---|
| BV17_workflow_v5 | 7 | 147,984 | partial | 5 findings |
| BV1AC_workflow_v10 | 7 | 199,627 | partial | 3 findings |
| BV1yb_workflow_v1 | 7 | 186,445（不含 64k probe 42,241） | partial | 32k invalid；64k probe 6 findings |

对照旧 current（`runs/_brief_final3`，brief + writer + visual，3 次调用；usage 来自各 stage `llm_calls.jsonl`）：

| run | 调用 | tokens | 状态 |
|---|---:|---:|---|
| BV17 | 3 | 38,586 | complete（未跑 verifier/polish） |
| BV1AC | 3 | 79,154 | complete（未跑 verifier/polish） |
| BV1yb | 3 | 47,444 | complete（未跑 verifier/polish） |

> 注：旧 current 的 `complete` 不是 reader pass，只是没有 semantic verifier；新 workflow 的 `partial` 是诚实的 residual 记录。两者不能直接比“谁更好”，但可以比“成本/调用”和“已知 residual”。

### 1.3 文档 vs 代码/artifacts 的冲突

| 文档说法 | 实际 |
|---|---|
| “source_map 从帧 OCR 提 channel（已完成）” | 代码有 `_channel_from_frames`（`source_map.py:27-40`），但**取第一个匹配**；BV1AC 返回 `的编程宇宙`，不是 `轩辕的编程宇宙`。 |
| “judge v5 pack 已建好” | 目录/标准/文章都在，但 new 侧来自三个**早于修复**的 run；pack 不是当前代码的测试。 |
| “final verifier 只读审计，residual 保留为 partial” | 代码确实如此；但这意味着三篇都不收敛，且视觉 caption 在最后一次 repair 之后才生成。 |
| “当前交付未验收” | 准确；三篇 `reader.md` 都成立，但没有真人 reader test，也没有 judge v5 结果。 |
| `STATE.md` “508 passed” | 复算通过。 |

---

## 2. 最新交付实际做到了什么、没做到什么

### 2.1 BV17（`runs/_diag/BV17_workflow_v5/output/reader.md`）

**做到了**

- 标题有具体主体 + 冲突：`0.8 的门槛筛空了，前 9 张仍是蝙蝠：用 EmbeddingGemma 2 搜 300 张照片`（`:1`）。
- 核心数字链完整：0.756、0.8、0.951、0.921、0.781、0.624、0.709、128 维退化；表在 `:43-49`，边界在 `:115`。
- 机制链清楚：阈值筛空 → 同一空间不同区域 → 同模态/跨模态不同尺 → 排名 → 截断/归一化 → 128 维退化。
- 来源行存在（`:117`），这是旧 current 没有的净改进。
- binding 事实 93/94、quotes 11/11，技术上干净。

**没做到**

- **频道写成“未提供”**（`:117`），但帧 OCR 明确有 `CodingStartup起码课 bilibili`（`context.json` frame `00000_000015000`；`verifier_final_report.json` 第 1 条 same）。
- **机制句没有标“视频的解释/示意”**：`:37`“跨过去比较，分数会被整体压低；区域内部谁离谁近，顺序却没变。”源文本确实说了“原因是文字和照片……各自聚在不同的区域”（`context.json`），但证据是 2D 示意图 + 几组分数；final verifier 认为应标为视频假设/未验证机制。
- **图注承诺图里看不到的东西**：`:35` 配的是 2D 聚类帧，caption 却写“跨模态分数被整体压低”；2D 图只能看到成簇和簇间距离。
- **chart 后缀写成“视频数据”**：`:21`“（根据视频数据绘制）”；这是当前 `render.py` 修复之前的 run，修复后是“根据视频内容绘制”，但仍需要把“观察/单次演示”的 scope 写进 caption，而不是只换一个名词。
- **表把结论写成结果**：`:98` `| 256 | 前 9 张蝙蝠 | 几乎无损 |`；“几乎无损”是观察 + 转述 95% 的混合，不是实测；正文 `:103` 有“是观察”，但表格形式把它固化了。
- **“怎么搜”的机制被压缩**：旧 current `runs/_brief_final3/BV17/output/reader.md:29-33` 有“照片提前算、查询现算、点积排序”的三段流水线；新稿只在 `:59` 说“算完点积从大到小排序”，没有说明照片向量是预先算好的。对没看过视频的读者，`job_to_be_done` 里的“文字如何直接搜照片”少了一环。
- 演示顺序有歧义：开篇 `:7-9` 是“先搜成功，再加 0.8”，`:15` 又说“0.8 是演示里先写下的过滤条件”，`:61` 说“最初不带门槛的搜索”。final verifier 判为 consistency medium；这条可能是 verifier 过度解读（源文本确实先有裸搜索、后有 filter），但读者会感到顺序不稳。

### 2.2 BV1AC（`runs/_diag/BV1AC_workflow_v10/output/reader.md`）

**做到了**

- 标题/主线清楚：`四种模式像四个产品，DeepSeek Harness 只是换了四份插件清单`（`:1`）。
- 四种模式的表格（`:39-44`）和 PTC 的 5→3 假设示例（`:58-66`）是有效的结构。
- 创造模式的具体演示（`:76-80`）、Cordis 插件化（`:88-100`）、开发者预览版边界（`:104-116`）都在。
- 来源行存在（`:136`）；“视频作者自称轩辕”是诚实的。

**没做到**

- **内部矛盾**：`:80`“Agent 真的给自己造了一个新工具，并把一套流程固化成了新模式”；`:96`“所谓现场造一个模式，就是把已有插件重新拼一遍”。源文本明确说“创造了一种新的模式，并且创造了一个新的工具，专门用来从 B 站搜索数据”（`context.json`）。两句不能同时成立；final verifier 第 1 条（medium mechanism）就是这个。
- **Cordis 事实没有归属**：`:92`“Cordis 是一个独立开源的 TypeScript 插件框架……”直接陈述；源文本是视频作者的说法，且没有官方文档/链接。final verifier 第 3 条（low source）指出。
- **假设数字的图注写成“视频数据”**：`:64`“5 次 vs 3 次（根据视频数据绘制）”；正文 `:58` 已说“视频用一条假设的链子”，这是假设示例，不是实测。当前 `render.py` 已把 chart 后缀改成“根据视频内容绘制”，但**这个 run 早于修复**；即使修复后，“根据视频内容绘制”也没有传达“假设”。
- **来源行说“标题、频道、日期未提供”**（`:136`），但帧 OCR 明确有标题 `Agent和Harness到底是什么？一个动画彻底搞懂！`、日期 `2026-05-15 18:02:14`、频道 `轩辕的编程宇宙`（`context.json` frame `00003_000105000`，`:61`），以及画面上的官方公告 `DeepSeek Harness 团队 2026年8月13日`（frame `00017_000525000`，`:215`）。这些不是“未提供”，是“没提取”。
- 标题的“只是”把“四份插件清单”这个源文本确实说过的比喻进一步降格为“只是换清单”，与 `:80` 的“造新工具”张力更大；这不是单句错误，是标题/正文的 claim scope 不一致。

### 2.3 BV1yb（`runs/_diag/BV1yb_workflow_v1/output/reader.md`）

**做到了**

- 具体场景/对话链很强：1805 岁、丸子头、魔法杖、看脑门、幼儿园、斗地主、分手厨房、于谦改口；读者能“看见”视频。
- 数字边界表（`:87-93`）和“全片没有一位观众出场”的边界（`:95`）是全文最诚实的地方。
- 来源行存在（`:101`），比旧 current（没有来源行）明显改进。
- binding quotes 33/33，引用纪律干净。

**没做到**

- **标题匿名**：`:1`“满脑子问号地来，走时想去她直播间听听”——没有于谦/菜菜子/节目名；信息流里读者不知道写谁。
- **“第一次”历史断言**：H2 `:17`“魔法杖：形象第一次被翻译成用途”；正文 `:29`“一个虚拟形象第一次被翻译成用途”。源文本只有“第一次直播”（`context.json`），没有“第一次被翻译成用途”的行业史断言。**这个说法来自 brief**：`brief.json:25`“但形象第一次被翻译成用途”。writer 直接把它写进 H2/正文。
- **关系模板写成已成立机制**：`:51`“这个关系模板的实际作用，是把陌生人关系变成有剧本的关系：每次开播不用重新商量彼此是什么关系。”后面虽然说“视频里没有这样总结，这是本文的读法”，但前半句仍用“实际作用/每次”写成结论；final verifier 第 3 条（medium mechanism）。
- **“没有新事实”过度**：`:79`“整场没有出现一个新的事实把他推过去。”源文本里明明有魔法杖、几个孩子求助的转述、160/150 万等新信息；准确说法是“没有新的可核验事实/独立证据”。final verifier 第 2 条。
- **“治愈系”归属错**：`:95` 把“治愈系”“半个心理医生”“功德无量”“双向奔赴”都归为“于谦的当场评价”；源文本是于谦转述“大家伙都说你是治愈系的”（`context.json`），不是他本人的直接评价。**brief 也错了**：`brief.json:101`/`:119` 把“治愈系”标成“于谦的评价性说法”。
- **来源行把“验证本文判断”塞给于谦**：`:101`“视频里于谦自己说要去她的直播间，想验证这篇里的判断……”源文本只支持“他想去听”，不支持“验证本文判断”。这是把本文建议塞回视频人物嘴里；final verifier 64k 第 1 条（high source）。
- 第一人称视角跳：`:19`“她说自己特别忙，忙的是我那个朋友的事”——“我”是菜菜子原话，但句子是第三人称转述。final verifier 第 4 条。
- 标题/开头的“改观”预设了一个没有出现的旧立场；这是旧 judge 已经抓过的 P3 问题，新稿仍保留。

---

## 3. Top 5 问题（按“影响读者 / 影响成本 / 影响可迭代性”排序）

### 问题 1：语义缺陷在交付前被检测、但不被修复（设计 + 实现）

**事实**

- 三篇最终 `partial`；final verifier findings 5 / 3 / 6；`reader.md` 仍照常交付。
- 唯一一次 repair 由 initial verifier / binding / contract 驱动，发生在 polish/visual 之前（`pipeline.py:214-227`、`:257-322`）。
- final verifier 只读（`verifier.py:102-263`）；visual caption 在它之前生成，且没有语义重检。
- `final_verifier` 只在文章变化时运行（`pipeline.py:418`），所以“clean”路径可能完全没有 final audit。

**影响**

- 读者拿到的是**已知有 medium/high residual 的稿子**；系统自己知道，但不修。
- 每次迭代都停在“partial”，无法区分“可接受的 known risk”和“应该修的 defect”。
- 修复成本花在 polish 之前的 draft 上；polish/visual 之后的新问题没有再获得 repair 预算。

**分类**：主因设计（stage 顺序 + repair 位置），次因实现（final verifier 条件执行、repair 不接受 final findings）。

**为什么排第一**：它同时影响读者质量、成本（两次 verifier + 一次 repair 仍不收敛）和可迭代性（partial 无法收敛）。

### 问题 2：来源元数据/归属不完整，且新 channel 提取会截断（证据/数据 + 实现）

**事实**

- 帧 OCR 有：BV17 `CodingStartup起码课`；BV1AC `轩辕的编程宇宙`、标题 `Agent和Harness到底是什么？一个动画彻底搞懂！`、日期 `2026-05-15 18:02:14`、官方公告 `DeepSeek Harness 团队 2026年8月13日`；BV1yb `于谦`、`多新鲜呐`。
- 当前 `source_map._channel_from_frames` 取第一个匹配：BV1AC 返回 `的编程宇宙`（截断）；`source_map.py:247-275` 只把 channel 写进 provenance，title/date/official 仍硬编码为 missing。
- `brief.py:194-230` 如果模型给了 `source_block` dict，就直接用模型值，不会用 source_map 的确定性值补齐；模型若写 `channel: unknown`，code 的 channel 修复到不了 writer。
- 三篇来源行：BV17 `:117` 说频道未提供（错）；BV1AC `:136` 说标题/频道/日期未提供（错）；BV1yb `:101` 说画面字幕显示于谦/多新鲜呐（对），但把“验证本文判断”归给于谦（归属错）。

**影响**

- P5 红线/可信度的核心；读者无法回查，文章把“可得的”说成“未提供”。
- 成本很低（确定性，不需要新模型调用），却能同时改善三篇的来源行。
- `contract` 的 source-gap 检查太宽：`MISSING_MARKERS` 包含“搜索”（`contract.py:29`），所以“可在 B 站搜索”会被当成已披露所有缺失字段；三篇 contract 都 `complete`，但来源行仍有事实错。

**分类**：主因证据/数据（substrate 没有结构化 metadata），次因实现（source_map 不提取/截断、brief 不合并、contract 不校验）。

### 问题 3：机制/推断写成事实，brief 是错误上游（设计 + 实现）

**事实**

- BV1AC `:80` vs `:96`：造新工具 vs 只是重排已有插件；源文本支持前者。
- BV17 `:37`：把视频的 2D 几何解释写成已成立机制，没有标“视频的解释/示意”。
- BV1yb H2 `:17` + 正文 `:29`：“第一次”历史断言；brief `:25` 是同一句。
- BV1yb `:51`：“实际作用/每次”写成机制；`:79`“没有新事实”；`:95`“治愈系”归属。
- 这些不是“句子像 AI”，而是**claim status 没有被强制执行**：skill 说了 `事实（有来源）/视频作者说法（待核）/本文判断` 三分，但 brief 和 writer 没有在每个承重句上落实。

**影响**

- 读者会把推断记住为事实；P2/P5 的主要扣分点。
- brief 是上游：它一旦写了“第一次/治愈系是于谦评价”，writer 很难不跟；最终 verifier 只能事后抓，不能修。
- 分类：主因设计（brief 的权威 + 缺少 brief 级 source/claim 检查），次因实现（writer 综合错误、final verifier 不闭环）。

### 问题 4：视觉层能生成，但没有语义审计（设计 + 评测）

**事实**

- BV17 `:35` 2D 聚类帧 caption 承诺“跨模态分数被整体压低”；`:98` 表把“几乎无损”写成结果。
- BV1AC `:64` 假设 5 vs 3 的图注写成“视频数据”；当前 `render.py:1026-1039` 已改为“根据视频内容绘制”，但这是本 run 之后的修复，且“内容”仍不等于“假设”。
- `media/planner.py:139-312` 只校验 frame ID、chart 数字、table 数字/标识符；**不校验 caption/表意是否真的被图展示**。
- BV17 frame `00003_000105000` 的 readability 是 `non_dark=0.055, stddev=24.4`，靠 `caption_dark_slide` override 通过（`render.py:974-1018`）；旧 judge 已经说过这张首图太暗、聚类几乎看不见。新 workflow 仍用了它。
- final verifier 是文本的，看不到图；它能从 source_text 推断 caption 不匹配，但不能判断“图上到底看不看得见”。

**影响**

- 图是“证据/结构”，caption 过度承诺会直接损害可信度；旧 judge 的图片/图注问题是 5/6 篇复现。
- 分类：主因设计（visual planner 是模型，语义校验只有结构），次因评测（没有 VLM/visual semantic audit）。

### 问题 5：标题/可分享单元/受众适配仍是弱项（skill + 评测）

**事实**

- BV1yb 标题 `:1` 匿名；`examples.md:196-212` 已经把**同款匿名标题**标为“坏”，并给出“于谦为什么愿意去菜菜子的直播间……”的好例；但 brief planner 只收到 `planning.md`（`brief.py:371-374`），看不到 examples；writer 又把 brief 的 title 当合同（`SKILL.md:18`），于是坏标题直达交付。
- BV1AC 标题 `:1` 的“只是”是 downplayer，和 `:80` 的“造新工具”张力；contract 的 absolute 列表没有“只是”（`contract.py:28`）。
- 受众冲突：writer 默认 technical baseline（`request.py:57-62`），judge 标准默认 AI 初学者；旧 judge 的 P2 candidate −8.0 有一部分是 `profile_mismatch`，不完全是写作缺陷。
- 旧 judge 的 P4（传播）是六篇里最弱的一层；新稿的标题/结尾有改善（BV17 标题、三篇来源行），但 BV1yb 的匿名标题和 BV1AC 的“只是”说明还没有稳定的 title gate。

**影响**

- 影响 Engagement/Shareable，不影响核心准确性；所以排在 1–4 之后。
- 分类：主因 skill/设计（brief 选标题时看不到 examples；writer 不能/不敢覆盖坏标题），次因评测（P4 权重 15%，且 judge 受众与 writer 默认不一致）。

### 跨切面：评测完整性（评测/流程）

- judge v5 pack 的 new 侧来自三个早于修复的 run（`build_judge_pack_v5.py:29-45`；run 时间 15:14–15:44，`source_map.py` 15:45、`render.py`/`config.py` 15:41）；pack 15:46 构建。跑它=评旧代码。
- 新 workflow 的成本是旧 current 的约 2.5–3.9 倍；旧 judge 的结论是 candidate 没有整体优于 current（current 赢 2/3；candidate P2 −8.0）。新 workflow 的增量价值没有被 judge v5 证明。
- 这条不影响单篇读者，但影响我们是否能相信任何“下一步”；所以必须在 memo 里单列。

---

## 4. 分类汇总

| 问题 | 设计 | 实现 | 证据/数据 | 评测 |
|---|---|---|---|---|
| 1. final semantic 不修 | 主（stage 顺序/repair 位置） | 次（final verifier 条件执行） | — | 次（final 只读） |
| 2. 来源元数据/归属 | 次（brief/source 合并策略） | 主（source_map 截断/不提取；contract 过宽） | 主（substrate 无结构化 metadata） | 次（verifier 漏检） |
| 3. 机制/推断写成事实 | 主（brief 权威；claim status 未强制） | 主（writer 综合；brief 错误） | —（证据足够，主要是读法） | 次（final 不闭环） |
| 4. 视觉语义 | 主（planner 是模型，只有结构校验） | 次（caption 后缀/readability override） | — | 主（没有 VLM/semantic audit） |
| 5. 标题/传播/受众 | 主（brief 看不到 examples；title 权威） | 次（writer 跟随） | — | 主（P4 弱；audience mismatch） |
| 评测完整性 | — | 次（pack 构建脚本固定旧路径） | — | 主（pack stale；成本/质量未证明） |

---

## 5. 保留 / 改 / 删

### 保留（有证据支持）

- **substrate v1 light path**：binding/quotes 干净（93/94、66/68、12/12；quotes 100%），不需要动 substrate。
- **一次 Writer + skill**：语言/结构/具体例子成立；prose 不是瓶颈。
- **source line + contract 的方向**：旧 current 三篇没有来源行；新稿三篇都有。方向是对的，问题在字段准确性和归属。
- **bounded repair**：BV17 的归一化机制、BV1AC 的“官方标的是”→视频作者说、BV1yb 的“她这样做了”→她这样说了，都是 repair 修好的。repair 本身有效。
- **final verifier 作为 detector**：它抓到的多数 residual 是真的；不能因为它是只读的就否定它。
- **visual planner/renderer 的 provenance/readability 结构**：有 frame ID/数字校验、像素门、caption 结构；问题在语义层，不在“有没有做”。
- **audit artifacts**：manifest/prompt/raw/usage/latency/final verifier 都可查；508 tests 通过。

### 改（通用、跨 ≥2 case）

1. **把唯一一次 semantic verifier + bounded repair 移到 polish + visual 之后**，针对交付稿；取消 initial verifier 的独立 repair（或只保留为 cheap pre-check）。理由：final verifier 已经证明能抓到交付稿的 residual；现在的问题是抓到了不修。见 §6。
2. **source_map 提取 channel/title/date/官方公告候选**，带 provenance/confidence；channel 用“出现频率最高/最长、排除更长短语的 suffix”这类通用规则，不硬编码具体频道；brief 的 source_block 用确定性候选补齐模型输出；source line 允许写“画面显示/未核实”。理由：帧 OCR 已有这些信息；这是 P5 红线最便宜的修复。
3. **brief 输入加 `examples.md` 的 title/claim 例子**（至少 title 好/坏对照），并在 brief 里加一个 advisory 的 title 检查：具体主体 + 冲突/问题，引语/数字必须在 source。理由：BV1yb 的坏标题在 examples 里已经被标为坏；brief 看不到 examples 是结构性遗漏。
4. **visual caption/table 的语义约束**：caption 只能描述图里实际能看到的东西；假设/单次演示的图表必须写“假设/示意”，不能写“数据/实测/基准”；表格的“结果”列不能放未绑定的结论（如“几乎无损”）。先改 prompt + renderer 后缀，不新增 VLM stage；如果 judge v5 显示视觉仍是 top，再加 VLM/semantic audit。
5. **contract 的 source-gap 检查**：不要用“搜索”作为 blanket marker；至少要求 source line 提到每个 missing 字段或明确说“未核实”。这是小实现修复，不是新 validator。
6. **final verifier 无条件运行**（当 `verifier=True`），不要依赖 `article_changed_after_verifier`；否则 clean 路径可能跳过视觉语义审计。

### 删 / 退（不做）

- **不做第二次无限 repair loop**。只保留一次 bounded repair，但把它放在正确的位置；不是“final 再修一轮看看”。
- **不为单篇/单 finding 加 validator/词表/gate**。不硬编码“轩辕”“于谦”“第一次”“几乎无损”。
- **不恢复 v2 多阶段 waterfall**；不新增 agent/validator 数量。
- **不因为 judge 的 AI 初学者标准就把所有术语删掉**；默认读者是 technical baseline，先按标准评分并单列 `profile_mismatch`。
- **不在 pack 未重建前跑 judge v5**；不把旧 run 的分数当当前代码的结果。

---

## 6. 下一步最小、最有杠杆的实验

### 假设

交付稿的 residual 主要不是 writer 不会写，而是**唯一的 repair 预算花在了 polish/visual 之前的 draft 上**；把 semantic verifier + repair 移到交付稿，能在不增加调用数的前提下减少 residual。

### 最小改动（推荐 A）

- 保留 brief + Writer + polish + visual。
- 删除 initial verifier 的独立 semantic gate（或降级为 cheap pre-check）；在 visual 之后跑 **一次** verifier，blocking findings 驱动 **一次** bounded repair；repair 必须保留 image markdown/assets/source line；repair 后重新 validation + contract；不再跑第二次 verifier（或只做只读确认）。
- 只把 critical/high + 有具体证据的 material medium 交给 repair；low/debatable 留作 known risk（例如 BV17 的演示顺序可能是 verifier 过度解读）。
- 预期调用数减少一次 verifier（当前 verifier ×2 + repair ×1；改为 verifier ×1 + repair ×1）。

### 可选的便宜第二刀（推荐 B，但不是“只能做一件”时的第一件）

- source_map 提取 channel/title/date/官方公告候选；brief 合并；source line 用“画面显示/未核实”。这不需要模型调用，直接改善三篇来源行和 P5 风险。

### Case

- BV17（短、analytical、数字/机制）
- BV1AC（中、product analysis、流程/产品 claim）
- BV1yb（长、narrative/interview、来源/视角/claim status）

**为什么是 3 个**：三个 case 覆盖三种 genre/长度/claim 类型；AGENTS 要求 ≥2 视频/文体才进通用层，3 个 dev case 满足“不是单例”的最低要求。holdout（BV13/BV1ix）仍不跑，不能据此说泛化。

### 验收标准

1. 三篇都仍产出 `reader.md` + assets；不新增 binding/contract failure。
2. 交付稿的 final audit 没有 critical/high；material medium ≤1/篇，且每条要么已修，要么在 manifest 里标为 accepted known risk。
3. 对比 before/after：final findings 5 / 3 / 6 → 目标 ≤2 / ≤1 / ≤2；至少 BV1AC 的 `:80` vs `:96` 和 BV1yb 的 `:101` 被修掉。
4. repair 不删图/不改 image 路径；source line 仍在；标题/H2 不被 repair 重写成新 thesis。
5. 成本不高于当前（理想：少一次 verifier；最差：持平）。
6. 如果 1/3 case 变差，或 repair 引入新的 binding/contract failure，停止并把 case 作为反例报告；不要为了“通过”调单篇。

### 然后才跑 judge

- 用当前代码重跑 3 个 dev case，重建 judge v5 pack（不要复用旧 `runs/_diag/*`）。
- 跑 30 份 subagent 报告；按 `profile_mismatch` 单列受众差异；P5 红线优先。
- judge 是外部检查，不是替代 final verifier；两者都过才谈“可发布”，最终仍要用户 manual acceptance。

---

## 7. 需要用户裁决的事

1. **是否允许把 final verifier 变成“可驱动一次 bounded repair”？** 这是问题 1 的核心。推荐：允许，且只修 critical/high + 有具体证据的 material medium；不做第二次 loop。若坚持 final verifier 只读，就要接受三篇继续 `partial`，并把 residual 当 known risk。
2. **是否允许从帧 OCR 提取 channel/title/date/官方公告，并写成“画面显示/未核实”？** 推荐：允许。否则 P5 的“来源不可追溯”无法改善；不要编 URL，只写画面可见信息 + 搜索词。
3. **judge v5 的受众按哪套？** 两份标准默认 AI 初学者，writer 默认 technical baseline。推荐：仍按标准评分 + 单列 `profile_mismatch`，不把 P2 绝对分当唯一目标；如果你要 technical baseline 的结论，就开第二个 audience arm，而不是改标准。
4. **是否重建 judge v5 pack？** 推荐：重建，且只在新 runs 上跑。当前 pack 是旧代码的快照；跑它会把旧 residual 误算到新 workflow。
5. **如果只能做一件事：选 final verifier+repair（推荐）还是 source metadata？** 前者覆盖面更大（机制/一致性/归属/图注都能修）；后者更便宜、直接改善 P5 来源红线。我的推荐：先做 final verifier+repair，紧接着做 source metadata；如果你的优先级是“先能发布/先过 P5”，则先做 source metadata。

---

## 8. 与上一轮接手点/文档的冲突（需要报告）

1. **“judge v5 pack 已建好”**：目录是建好的，但不是当前代码的 pack；new 侧 run 早于 `source_map`/`render`/`config` 修复。跑之前必须重建。
2. **“source_map 从帧 OCR 提 channel 已完成”**：代码在，但对 BV1AC 取成 `的编程宇宙`；且 title/date/official 仍未提取。不是“完成”，是“半完成 + 一个截断 bug”。
3. **“新 workflow 比旧 current 好”**：未被证明。旧 judge 的 candidate 没有整体赢 current；新 workflow 的成本是旧 current 的 2.5–3.9 倍，三篇 `partial`。新稿的净改进是来源行、部分 repair、标题（BV17），但这些需要 judge 证明。
4. **“final verifier 只读是设计，residual 保留”**：设计如此，但它导致三篇不收敛；operating model §7 的开放问题 4 仍然成立。不要把“partial 是诚实记录”当成“partial 可以交付”。
5. **“技术 complete ≠ reader pass”**：完全成立；三篇 contract 都 complete，但 final verifier 5/3/6。当前 L1 的 source-gap 检查尤其不够。
6. **“当前问题不是句子像 AI”**：成立；但需要补一句——**也不是“证据不够”**。binding 干净，证据足够；问题是 claim status/归属/图注的编辑纪律，以及 final 不修。

---

## 9. 一句话

**这套系统已经会“检测”一篇稿子哪里不可信，但还没学会在交付前把检测到的问题修掉；同时它把证据里已经有的来源信息写成了“未提供”。先修这两个闭环，再谈 judge 分数和下一轮 stage。**
