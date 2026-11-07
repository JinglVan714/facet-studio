# video-article skill

> **2026-11-06 说明**：这是写作引擎的 skill 说明；**SKILL.md 是 active**。文中的“一致性 pass”是旧 article pipeline，不是当前 `writing_v4` writer 的默认后处理；当前写作引擎见 [docs/writing-v5-architecture.md](../../../docs/writing-v5-architecture.md)，产品/架构见 [docs/product-v1-chat-studio.md](../../../docs/product-v1-chat-studio.md) / [architecture.md](../../../architecture.md)。skill 里不要出现具体视频/产品/人物。

把一份关于某个主题的完整内容稿写成一篇独立文章。读者没接触过原始内容，读完应获得接近亲自了解过的理解与体验。

## 核心方法

1. **读全内容稿**：完整段落 + 图示说明；不抽样，不先做 claim/brief。
2. **找控制性 idea**：一句话说出读者最该记住的判断/机制/做法，并检查新意、边界、反方。
3. **证据地图**：在脑子里分开“内容稿事实 / 内容里的观点 / 我的解释 / 不写”，文章里不混层。
4. **内容账本**：列出关键数字、步骤、条件、结论；标记冲突/缺口；选一个口径全篇一致，或省略。
5. **节拍地图**：每个节拍只做一件事；概念先落地；每节回答上一节留下的问题；砍掉 coverage。
6. **写 + 一致性回读 + 自审**：按内容选形状；写完先查数字/步骤/标题/表格/例子/结论是否对得上，再用 fresh eyes 过 5 个视角、证据保真、中文 AI 味八条；最多一轮修正。

## 一致性 pass（写后，最多一次）

写完后单独跑一次两步编辑，不混在写作调用里：

1. **consistency review**：只列 Must fix 的内部一致性项——数字/单位/用量/步骤/条件/结论、标题/开头/表格/正文/例子/结论、动作字面矛盾或缺一拍、声称范围 vs 演示/例子、默认/可选反转、术语。
2. **consistency edit**：只按 fix list 做最小修改；不加事实/机制/安全/百科，不改观点/结构/语气；内容内无法修的跳过并报告。

借了 `avoid-ai-writing` 的 detect/edit 分离 + 有界修复、`wewrite-review` 的 review→direct revise、`great-writer` 的 self-contradiction scan。它不是质量门，也不做外部核查。

## 素材 / 写作分离

这是本 skill 的硬边界：

- **素材层**：`src/facet_studio/writing_v4/content_manuscript.py` 把 substrate 编成 `content.md` + `figures/fig-XX.jpg`。它负责转写、分段、选帧、复制图示、去掉标题/UP 主/时长/链接/时间码/ID/帧号/出处。
- **写作层**：Writer 只读 `content.md` + `SKILL.md`。它不知道有视频、素材包、claim 表或任何管线。正文里不出现“内容稿/素材/原文/转写/视频里/视频中/这条视频/本期视频/UP 主”。
- **出处**：文章写成后由 `run.py` 按 `source.json` 补一行；Writer 不写。
- **图示**：素材层复制并重命名为 `figures/fig-XX.jpg`；Writer 只看到“图示 N”和路径，不知道它是视频帧。

规范见 [references/material_prep.md](references/material_prep.md)。这份规范不给 Writer 看。

## 刻意没做

- 不做 brief/claim/verifier/repair/polish 多 stage。理解与取舍由 Writer 在写作过程中完成，不产出前置台账。
- 不做词表、硬分数、validator gate。确定性检查（quote hygiene / fact binding）是文章写完之后的地板，不是 skill 的一部分。
- 不按单篇调参；skill 里没有具体视频、产品、人物、台词、claim。例子全部匿名。
- 不把文章写成论文、百科、体检报告；不逐句“内容稿称/未核实”。
- 不伪造 reader test / A-B；judge 是模型评审，不是真人通过。

## 借了哪些开源逻辑

- `imraywang/wewrite`：一页 brief 的思考问题（读者、takeaway、thesis、novelty、boundary、counterpoint）、claim 类型分层、五项编辑标准。借问题，不借 YAML/台账。
- `VincentOld/stop-slop-zh`：中文 AI 味八条、五维“直/实/变/散/真”。借判断，不借词表和 35/50 硬分数。
- `conorbronsdon/avoid-ai-writing`：detect/edit 分离、source fidelity、protected content、两轮修正上限、“never inject”清单。借约束，不借英文 detector。
- `anthropics/skills` 的 `doc-coauthoring`：context → structure → reader testing。借 reader testing 的自问方法，不做交互式多阶段。
- `mattpocock/skills` 的 `writing-beats` / `writing-shape`：grounding、beats、prose/list/table/quote 的格式论证。借逻辑，不照抄流程。
- `d-wwei/great-writer`：reader stance、core tension、结构先行、删 significance inflation。借姿态与几个判断，不抄 6-phase。
- 本地 `bilibili-render-pdf`：教学 flow（动机 → idea → 机制 → 例子 → takeaway）、section takeaway、最终综合。借教学顺序，不抄 LaTeX/图越多越好。

## A/B 记录（2026-11-04，advisory）

三条视频、四次盲评（同一请求/模型/温度，只换输入形态；单模型评审，不是用户的 30 份 judge）。注意：A/B 跨了几轮 skill 迭代，且是在“内容稿制”之前做的，不是当前形态的严格对照，只作方向信号。

| 内容类型 | 胜出 | 观察 |
|---|---|---|
| 操作教程 | 素材包 ×2 | 素材包更容易写出开场、主线和行动收尾；连续文本更像“忠实整理”。 |
| 技术解释 | 素材包 | 交换 A/B 顺序后仍然胜出；结构判断和行动清单更清楚。 |
| 配方/清单型 | 连续文本 | 连续文本保留了配料表；离散版的完整帧表把这张表淹没了。 |

结论：格式本身不是决定因素。**编辑距离**（素材包更容易让 Writer 重组）和**具体细节/表格**（连续文本更容易保留）才是。当前的内容稿制同时保留这两点：连续内容 + 精选图示 + 无元数据/时间码。

## 地板检查

`src/facet_studio/writing_v4/article_checks.py` 检查：正文里不能出现“内容稿/素材/原文/转写/证据/视频里/UP 主”等泄漏词、不能有时间码；图示路径必须存在；标题和一行出处必须在。地板检查不等于质量评判。

## 边界

- 证据优先：事实/数字/引语/说话人只来自内容稿；模型知识用来组织语言/改写，以及给术语做一句最小解释；不补事实、机制、因果或结论。
- 写作层只保证“内容稿有就写，没有就不写”；不核实世界，不把内容稿说法升级成官方/已证实。
- 不自动发布；不 commit/push 到用户没让动的分支。

## License notes

- wewrite、stop-slop-zh、avoid-ai-writing、mattpocock/skills、great-writer：MIT；只借逻辑，未抄文本。
- anthropics/skills 的 doc-coauthoring：下载快照里没有 LICENSE 文件；只借 reader testing 的方法，未抄文本。若对外分发，先核 upstream license。
