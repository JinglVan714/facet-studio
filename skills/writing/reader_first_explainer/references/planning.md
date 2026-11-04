# Planning reference：动笔前的五个决定

> 这是写作前的编辑判断，不是章节 schema，也不是模型核实世界的清单。
> 目标：在写正文前，把“为谁写、回答什么、给出什么 payoff、沿哪条线、用哪些素材、砍掉什么”定清楚；章节/段落/视觉仍由 Writer 决定。

## 1. Planning 不是 outline

- **Planning**：读者、角度、核心判断、主线、关键锚点、标题、边界、砍什么。
- **Outline**：H2/段落/视觉顺序。Outline 是 Writer 的工作，可以在写的过程中调整。
- 不要提前写 H2、每节 promise/takeaway、visual slot。那会把 Writer 变成填空，也容易产生“场景→表格→总结”的三重编码。

## 2. 五个决定

### 2.1 读者

三句话：

- **知识边界**：读者已经知道什么？哪些术语可直接用？哪些首次出现要一句解释？
- **阅读动机**：读者带着什么问题/困惑/期待来？
- **预期收获**：读完后能解释什么、决定什么、做什么？

不要写“目标读者是技术人员”这种无法指导决策的话；要具体到“知道 X、不知道 Y、想知道 Z”。

### 2.2 核心判断

- 一句可被同意/反对的话。不是话题描述（“AI 对写作的影响”），而是一个判断。
- 写不出一句，说明还没想清楚。
- 这句话是全文的 core；每个 spine move 都要服务它。

### 2.3 Source question / payoff / throughline

- **source_question**：素材自己让读者追问的那个问题。优先用素材里的话/问题，不要自己发明一个更“高级”的问题。
- **payoff**：读者最后真正得到什么？一个反直觉结论、一个决定、一个可操作判断、一个情绪落点。标题应该承诺 payoff，而不是只承诺架构/设定。
- **throughline**：全文只服务的一句话。它应该能解释“为什么下一节还存在”；不能解释的节，考虑砍掉。

### 2.4 Spine：3–5 个 move，不是 3–5 个话题

每个 move 写：

- **move**：读者的认知/情境发生了什么变化（不是“本节讲 X”）。
- **connector**：because / but / therefore / and / meanwhile / before-after；连接词要真的成立。
- **anchors**：1–2 个具体素材（quote/number/scene/span）。不是每个 move 都必须有；但核心论证必须有。
- **weight**：slow（展开）/ fast（过渡）/ gold（记忆点/情绪峰值）/ optional。

Spine 的形状可以随文体变：

- `narrative`：场景 → 转折 → 代价 → 改观/回落。
- `analytical`：问题 → 证据 → 诊断 → 判断 → 边界。
- `procedural`：目标 → 失败 → 修复 → 第二幕 → 限制。
- `comparative`：A/B → 维度 → 反例 → 适用边界。
- `mixed`：组合，但不要变成话题清单。

检查：把 move 的标题遮住，只读 connector，应该还能看出推进；如果 connector 都是“and/also”，它可能还是清单。

### 2.5 标题

- 标题要承诺一个 payoff/问题/转变，不是只承诺“架构/设定/方法”。
- 至少一个主标题；候选可以 1–3 个，但 Writer 不为候选买单。
- 每个候选写：
  - `promise`：读者看到标题会期待什么？
  - `fulfilled_by`：哪个 move/anchor 兑现？
- 不能兑现的标题删掉或降级为候选。
- 标题测试：避免“A：B、C和D”的清单式副标题，也避免“A：如何 B/C/D”的机制清单；优先用素材自己的问题/引语、前后反差、或一个具体悖论。
- 如果素材有明确问题/引语，至少给一个基于它的候选。
- `chosen` 必须是你真的会发的那个，不是第一个候选；在 notes 写一句为什么它赢。
- 标题里的数字/引语必须来自素材，且不能从两个冲突数字里单选一个假装确定；冲突本身可以成为标题/边界。

## 3. 证据状态：不要让 Writer 猜，但也不要让它写“核实报告”

对核心 anchor 标：

- `claim_type`：measured / hypothetical / opinion / claimed / unknown。
- `speaker`：explicit / unknown。
- `relation`（如适用）：same_modal / cross_modal / none。
- `span`：line/segment/quote，便于 Writer 回查。

原则：

- 不确定就标 unknown；不要把“假设”写成“实测”，不要把“某人说”写成“视频事实”，不要把“同模态不同类”写成“跨模态低”。
- 但 **不要** 把“未核实/待核”写进每一句正文。写作层只保证“视频有就写，没有就不写”；视频说的在世界上是否已证实，不是 writer 的职责。正文用自然归属（“视频里/作者说”）一次，source line 记出处；judge 再管 P5 红线。
- 如果一句话可能被读者误读成“官方/已证实”，把主语写成“视频里/作者说”，而不是加一个“未核实”标签。

## 4. Cut / challenge / limits

- **cut**：明确不写什么，为什么。常见：安装/API 细节、泛化风险清单、重复的 thesis、与主线无关的八卦、过度证据审计。
- 不要因为“它像支线”就砍掉核心论证的最佳证据；如果一段小故事是“承诺兑现/边界/关键机制”的最干净证明，应短用它。
- **challenge**：最强替代角度是什么？为什么没选？多话题/host-led 素材至少留 2–3 个角度候选（可以写在 challenge/notes 里），不要让第一个机制角度默认胜出。
- **request conflict**：request 不是大纲；`required_information` 是覆盖约束，不是节序。如果 request 本身列出了“形象/定位/互动/原则”这种话题清单，不要照抄成 spine；先找 source question/payoff，并在 challenge/notes 里说明 request 冲突。
- **limits**：这次不证明什么？一个案例/一次测试/一个模型，不能写成普遍定律。但只在影响读者判断时写，不要列证据清单。

## 5. 四个检查（写正文前）

1. **Core cash**：core 的每个关键词，至少一个 move + anchor 兑现；没有就修 brief。
2. **Anchor correctness**：核心 anchor 的 claim type/speaker/relation/span 正确；不确定标 unknown。
3. **Sequence**：spine 顺序跟素材的发现顺序，或写出重排理由；不能和 challenge/throughline 相反。
4. **Title fulfillment**：chosen title 的 `fulfilled_by` 真实存在。

附加：如果 brief 本身能被一个不看素材的读者挑战（“这标题想让我读什么？这 spine 为什么不是清单？”），先修 brief，再写。

## 6. 和 Writer 的关系

- Brief 是合同/护栏，不是笼子；Writer 保留 H2、段落、句子、视觉意图的自由。
- Writer 发现 brief 与素材冲突：以素材为准，记录 `brief_conflict`，不要静默服从。
- Writer 不要在正文里输出 brief、字段名、plan header、anchor ID。
- 如果系统没有单独 brief：Writer 在“Before writing”里做 5 行 mini-brief（reader/core/source question/payoff/spine/title）再写；不要跳过。
