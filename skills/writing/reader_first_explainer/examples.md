# Examples：reader-first explainer

> Original good/bad pairs that anchor title, TOC, video-equivalence, visuals, attribution, evidence discipline, boundaries and voice. They are patterns, not templates, and contain no third-party text.
> These examples are generic patterns; they are not tied to any specific video, product or person.

## 1. Title: subject + conflict/payoff

**Bad**

> ## 一个方法：三个步骤和四个原则

**Good**

> ## 把一步拆成两步：为什么反而更快？

**Why**: A title is not a category label or a list. Before clicking, the reader should know who/what the piece is about and what the conflict or payoff is. Do not make the subject anonymous (“她/他/这个工具”).

## 2. TOC: H2s are a table of contents, not a topic list

**Bad**

> ## 背景
> ## 它是什么
> ## 使用
> ## 总结

**Good**

> ## 问题看起来出在最后一步
> ## 真正的限制在中间
> ## 代价落在三个地方
> ## 决定体验的是它愿不愿意暴露失败

**Why**: Reading only the H2s should show how the piece advances. Avoid “背景/介绍/总结/其他”; each section needs a concrete object, action or judgment.

## 3. Video-equivalence: write what was seen, not what was “introduced”

**Bad**

> 视频介绍了四种工作模式，并进行了对比。

**Good**

> 同一个流程换一种组织方式，原本要逐步确认的环节被合并成一个动作；往返次数明显下降，中间细节也不再全部进入上下文。省下的不只是次数，读者也能看清每一步在做什么。

**Why**: A reader who did not watch the video should be able to “see” what happened in the demo: what changed, what remained, and what the cost was. “Introduced four modes” is not writing.

## 4. Visual-first: what a table/diagram can say, do not write as a paragraph

**Bad**

> 方案 A 有完整的步骤和逐步选择；方案 B 保留了这些能力，但把多个步骤合并成一次执行；方案 C 只保留最小入口；方案 D 还能在执行中调整。

**Good**

| 方案 | 改了什么 | 代价/边界 |
|---|---|---|
| A | 保留完整步骤，逐步选择 | 次数多，中间细节进上下文 |
| B | 多个步骤合并成一次执行 | 出错会返工，可能更贵 |
| C | 只保留最小入口 | 依赖执行者自身能力，适合测试 |
| D | 可在执行中查看并调整 | 过程不稳定，示例只跑了两轮 |

**Why**: Differences between approaches are a natural table; a long paragraph forces the reader to hunt for dimensions. A table must not be the only content of a section: add one sentence before or after saying what to notice.

## 5. Attribution: let the content be the subject

**Bad**

> 视频作者认为这个工具适合自动化任务。

**Good**

> 这个工具适合自动化任务；出错会打回重改，反而增加调用。

**Why**: The reader cares about what it is good for and what it costs, not who thinks so. Put the video/author in the subject only when distinguishing opinion from fact, or pointing to a specific demo.

## 6. Attribution: do not attach “unverified” to every sentence

**Bad**

> 视频称该方法支持多种输入（未核实），处理方式是某个固定数字（视频称，未核实），并且放在同一个空间里（待核）。

**Good**

> 视频演示的做法把多种输入转换成同一种表示，放在同一个空间里。它是不是官方能力、支持到什么程度，视频没有展开；来源行只记视频出处。

**Why**: “视频演示的……” already carries attribution. “未核实/待核” on every sentence turns the article into an audit report. Use “视频里/作者说” once only where a sentence could be misread as an official confirmation; let the source line carry the rest.

## 7. Attribution: do not upgrade to “official/confirmed”

**Bad**

> 官方发布了这个工具，支持多种输入。

**Good**

> 视频里说，这个工具昨晚发布；文章只按视频演示的范围写，官方文档和发布日期未核实。

**Why**: “The video says open source” is not the same as official documentation. Do not write it as “official/confirmed”; use “视频里说” once where needed, and let the source line cover provenance.

## 8. Speaker: if you do not know, do not guess

**Bad**

> 她说：“这个我就不太同意了。”

**Good**

> 对话里有一句“这个我就不太同意了”；源文本没有逐句 speaker 标签，不能确认是谁说的。

**Why**: Without a speaker label, assigning the line to the nearest name is fabrication. Write “对话里/视频里”; assign a name only when the source explicitly says “X 说” or uses a third-person address (“X，你……”). Conversely, if the context clearly identifies the speaker, do not flatten every line to “对话里”.

## 9. ASR noise: remove greetings/previews/sponsors

**Bad**

> 大家好，我是某某，今天咱们来聊一个特别有意思的话题，记得一键三连，下面我们进入正题。

**Good**

> 问题不在于工具能不能用，而在于出错之后谁来收拾。

**Why**: Greetings, self-introductions, previews and channel logistics do not serve the central question; cut them and start with the reader's problem.

## 10. Boundary: reader-facing, not an evidence checklist

**Bad**

> 这两类表示内部如何对齐，视频里还没有答案；也没有独立测试，没有更大范围的数据，没有对比实验。

**Good**

> 在这组证据里，只能确定同一条件下的排序仍然可用；内部结构不是这次能回答的。换一批数据是否还成立，视频没有复测。

**Why**: A boundary says what the reader can and cannot conclude from the evidence, not what the evidence lacks. It appears only when it changes judgment or action.

## 11. Quote discipline: quote only exact words

**Bad**

> 它说“可以自动处理所有任务”。

**Good**

> 它能处理其中一部分任务；超出范围时仍要人工接手。

**Why**: If the source only says “some tasks”, turning it into “all tasks” and adding quotation marks is fabricated quotation. Quotation marks wrap exact source text only; paraphrase without quotes. An approximate ASR variant is not an exact quote.

## 12. Repetition and coverage dump

**Bad**

> 首先讲了准备，其次讲了处理，然后讲了检查，最后讲了收尾。每个部分都很重要。

**Good**

> 准备让材料能进入下一步；真正的难点是进入下一步之后——条件是否满足、顺序是否对、出错怎么回退。这三件事决定了能不能稳定完成。

**Why**: The reader wants a mechanism chain, not a chapter list. Organize parallel items into cause/dependency relations; do not give every item equal weight.

## 13. Screen text: a frame marker is OCR, not visual semantics

**Bad**

> 画面里写着：1 接收 2 处理 3 检查 4 返回。所以流程就是这样。

**Good**

> 一次流程要经过四步：先接收，再处理，然后检查，最后返回。真正的成本在第二到第三步之间——每一次检查都要重新确认前面的条件。

**Why**: A frame line / OCR is whole-screen text, not visual semantics; do not paste it as body text. Understand it, then explain the mechanism in your own words.

## 14. Conclusion: synthesis + natural exit

**Bad**

> 总结一下：本文讲了 A、B、C 三个方面。

**Good**

> 真正决定体验的，不是单个步骤多强，而是这套流程愿不愿意把失败暴露出来：条件不满足、步骤超时、权限不足，只有被看见，才有机会被修。
>
> 来源：视频标题（频道）；标题/日期未提供。

**Why**: A conclusion should add synthesis/judgment/decision; a section-by-section recap adds no information. The source line is short and natural, provenance only, not an audit report.

## 15. Term at first use: keep the term, one definition

**Bad**

> 这个指标叫 F1，是精确率和召回率的调和平均。

**Good**

> 先看两个数：一个是有多少判断是对的，一个是有多少该找到的找到了。把这两个数合起来看，就是这个指标。代价是它只反映这两件事，不告诉你错在哪里。

**Why**: Explain in reader language what it does and what it costs, then give the term; do not define a term with a harder term. If the reader already knows it, skip; if it is load-bearing, one sentence; if truly unfamiliar, add one analogy or counterexample.

## 16. Model knowledge: explanation/analogy yes, pretending to be video fact no

**Bad**

> 视频说这套系统采用了微内核架构。

**Good**

> 可以把它理解成“核心 + 外挂”的思路：核心只保留最小部分，能力都从外部来。视频本身没有用“微内核”这个词；它展示的是同一套系统换不同配置。

**Why**: Model knowledge may explain, analogize or provide background; it must not become a video fact or quote. Attribution should be honest, but not on every sentence.

## 17. Voice: like a person, not a report/AI boilerplate

**Bad**

> 首先，AI 正在重塑我们的工作方式。其次，它带来了效率提升。最后，值得注意的是，我们需要拥抱变化。这，就是 AI 的力量。

**Good**

> 我们组三个工程师，过去半年有两个把日常调试交给了模型。真正的变化不是“写代码更快”，而是调试从“自己一行行看”变成“先让模型解释它为什么这么改”，再决定信不信。

**Why**: Cut “首先/其次/最后/值得注意的是”, “这，就是…的力量”, and rule-of-three parallelism; use concrete people/numbers/scenes. Vary sentence length so it does not read like a template.

## 18. Title quotation: a quote in the title must appear verbatim in the body

**Bad**

> ## 「你们永远不用毕业」
>
> ……（正文只写了近似意思，没有原句。）

**Good**

> ## 「原话就是这一句」
>
> ……正文出现同一句原话，并说明它是在什么语境下说的。

**Why**: If the title uses a quotation, the body must contain that exact line; otherwise remove the quotation marks and stop pretending it is a quote.

## 19. Do not say “视频里” in every paragraph

**Bad**

> 视频里说……视频里还提到……视频里最后说……

**Good**

> 先看第一个演示：……。第二段把问题推到……。最后，作者回到开头那个问题：……。

**Why**: The article is a standalone piece, not video notes. Use “视频里/作者说” only when distinguishing opinion from fact, pointing to a specific demo, or when the speaker is uncertain.
