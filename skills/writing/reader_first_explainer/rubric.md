# Rubric：reader-first explainer

> 人评/LLM-as-Judge 的诊断 rubric，不是词表，也不是硬编码测试。
> 质量门是 LLM-as-Judge（5 persona）× 真人 reader test（未来）；确定性测试（结构/quote/数字/ID）是**地板**，必须过，但不能当“好 writing”的评判。
> 用法：每篇由开发者/评审者按维度打 pass/partial/fail；不要为了 rubric 加规则或字数。

## 1. Title / TOC

- **pass**：title 承诺一个具体 payoff/问题/转变（不是分类标签/架构/设定）；只看 title + H2，读者能理解框架和推进顺序；第一段兑现 title。
- **partial**：有框架，但 title 偏 setup，或部分 H2 空泛/重复/不成体系。
- **fail**：标题只承诺架构/设定/方法，或 H2 是话题清单，看不出推进；article 没有兑现 title。

## 2. Video-equivalent experience

- **pass**：未看视频的读者能复述内容、机制/流程、关键例子/演示/画面、作者判断与边界；能“想象出”视频讲了什么。
- **partial**：内容覆盖够，但例子/演示/画面不足，读者只能记结论。
- **fail**：只有抽象摘要/观点，未看视频的人无法理解视频实际讲了什么。

## 3. Mechanism / chain

- **pass**：一条机制/论证/步骤链；读者能复述因果，而不是背结论；未知的 link 标 unknown，不补因果。
- **partial**：有链，但中间有跳跃/未解释的步骤。
- **fail**：并列 section 拼盘，或只有结论没有机制。

## 4. Boundary

- **pass**：边界是读者向的（能得出什么/不能得出什么），且只在影响判断时出现；正文和边界同 scope。
- **partial**：有边界，但写成“证据缺什么”清单或过于笼统。
- **fail**：把观察写成因果，或对未覆盖内容下强结论。

## 5. Visual-first

- **pass**：机制/流程/架构/对比/数字用图/表/帧替代长段文字；真实帧确实展示操作/结果且可读；图/表/ caption 和正文一致；无图时有理由。
- **partial**：有图/表，但和正文关系弱，或仍有本可画图的长段；或图/表复述正文。
- **fail**：全篇无必要的图/表；为了有图硬插不相关关键帧；图/表和正文矛盾。

## 6. Concision / repetition

- **pass**：一段一个意思；能表格/图替代的长描述已删；没有重复的动作/观察/数字；没有 coverage dump。
- **partial**：有局部长段/重复，但不拖垮阅读。
- **fail**：大量复述/灌水/为长度而写；逐节 recap。

## 7. Source / attribution

- **pass**：来源归属做实事；内容作主语；只在区分观点/事实或指演示时提视频/作者；不猜说话人；不把视频 claim 升级成官方/已证实；不编引语/数字/画面。
- **partial**：偶尔过度归因或过度保守（每段“视频里”/每句“未核实”），但不改变事实。
- **fail**：编造数字/专名/引文/说话人，或把 model knowledge 写成视频事实；把假设/单次演示写成实测/普遍定律。

## 8. Voice / AI-slop

- **pass**：像一个人在讲他知道的事；长短句交错；具体主语/动作/数字；没有模板化开头/结尾、排比三件套、金句收尾、空洞价值判断。
- **partial**：偶有 AI 味/模板句，但不影响阅读。
- **fail**：通篇模板化/八股/金句/假深刻；读起来像报告或 chatbot。

## 9. Reader hygiene（地板）

- **pass**：无内部 ID/citation key/时间码/审计语言；reader 文本干净。
- **partial**：有 1 处轻微审计语言，不影响阅读。
- **fail**：出现 ID/时间码/JSON/schema/审计语言。

## 10. Model knowledge discipline

- **pass**：模型知识只用于解释/类比/背景，来源归属诚实；没有把外部知识写成视频原话。
- **partial**：有 1 处边界模糊，但不改变事实。
- **fail**：用模型知识补视频没有的事实/数字/引语，或伪装成视频观点。

## 汇总（advisory）

- **pass**：1/2/3/7/8 全 pass，其余无 fail；judge/reader 无 red line。
- **partial**：核心维度有 partial，或有 1 个 fail 但不影响事实。
- **fail**：1/2/3/7/8 任一 fail，或 judge 的 P5 red line，或 reader test 未通过。

不要把总分替代 judge/reader test；不要按单篇调 rubric。
