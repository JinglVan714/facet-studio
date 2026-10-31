# Reader-first examples

Annotated good/bad pairs. The point is the move, not the exact words. Do not copy these sentences into an article unless the evidence supports them.

## 1. Source attribution

**Bad**
> 视频作者认为，这个工具很适合自动化任务。

**Good**
> 这个工具适合自动化任务；脚本一旦出错，会被打回重改，反而增加模型调用。

**Why**：第二版把内容（工具、脚本、调用）放在主语位置；来源关系在开头建立一次就够了。只有要区分“作者观点”与“事实”时，才需要再提来源。

## 2. Boundary

**Bad**
> 两个 encoder 内部如何把内容读成数字，以及区域差异为什么不打乱排序，都还没有确切的答案。

**Good**
> 在这组证据里，只能确定同一句查询下的排序仍然可用；encoder 内部结构不是这次能回答的。

**Why**：bad 版是“证据缺什么”的清单；good 版是读者能用的范围限定。边界只在影响读者判断时写，不列 coverage。

## 3. Conclusion

**Bad**
> 综上，我们讲了同一套坐标、低分看排名、切短后归一化三件事。

**Good**
> 把三件事放在一起看，真正要判断的是：这套方法省下的是空间和调用次数，不是比较能力；所以切短之后仍要回到同一把尺子上。

**Why**：bad 版是逐节 recap；good 版给了一个新的综合/判断，仍然由前文支撑。

## 4. Caption

**Bad**
> *这张图展示了文字查询、照片对照片、文字对文字三组分数，以及 0.8 门槛和分数分布的关系，说明固定门槛会把结果筛空。*

**Good**
> *看这里：文字查询那一行最靠前的分数。*

**Why**：caption 只写“看哪里”；解释放在正文。不要把图注写成正文摘要。

## 5. Repetition

**Bad**
> 点一下搜索。点下搜索，前 9 张结果全是蝙蝠。

**Good**
> 点下搜索，前 9 张结果全是蝙蝠。

**Why**：同一动作只写一次。后文需要回指时用一句指代，不重复动作句。

## 6. Mechanism vs vague claim

**Bad**
> 这个系统很强大，能处理很多任务。

**Good**
> 模型只负责给出调用意图；Harness 在执行前后接住参数校验、权限、重试和运行记录，所以模型不用自己处理这些工程问题。

**Why**：good 版把“谁做什么、为什么能成立”写出来；bad 版只有评价，没有机制。若证据只支持“能处理很多任务”，就写观察和边界，不补机制。

## 7. Editorial span

**Bad**
> （editorial）因此，这套架构未来一定会成为行业标准。

**Good**
> （editorial）把这组证据放在一起，能确定的是这套架构把工具、模型和运行环境拆成了可替换插件；它是否会成为标准，不在这次证据范围内。

**Why**：editorial 可以做综合/限定，但不能借机写新事实、新预测或新因果。

## 8. Demo choice

**Bad**
> 这段演示清楚地展示了四种模式的所有差异。

**Good**
> 这段演示只对比了标准模式和 PTC 的工具调用次数；极简模式和创造模式没有对应画面，正文用文字说明。

**Why**：`real_frame` 只在画面确实展示该 operation/result 时使用；没有匹配帧就写 `text_experiment`/`no_demo`，不要用生成图或示意图冒充视频证据。
