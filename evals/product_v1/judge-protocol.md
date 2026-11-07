# Judge protocol（未运行，先定义）

> P4 的 LLM judge 只作 advisory，不是发布许可；用户人工验收仍是唯一发布门。
> 不做 30 judge；每个形态一套窄 rubric，2 次聚合，用人工标注校准。

## 1. 标注与样本

- 从 `cases.json` 的已生成 artifact 中选 6–12 个（覆盖 long / wechat / xhs）。
- 用户按每形态 rubric 打 0–5 分；记录 `reviewer`、`artifact_hash`、`rubric_version`。
- 人工标注与 judge 分离，不让 judge 看人工分数。

## 2. 窄 rubric

### long_article

- 读者能否复述控制性 idea、机制/流程、关键例子和边界。
- 结构是否可读（标题/H2 是否构成目录）。
- 视觉是否服务理解（图/表/帧，不堆文字）。
- 事实/数字/范围是否与内容稿一致（抽查绑定/关键词）。
- 语言是否自然、不模板化。

### wechat_article

- 开头是否给结论/框架，而不是背景铺垫。
- H2 是否并行、具体、能扫读。
- 段落是否短、移动端可读。
- 图/表是否至少一处承担解释，不是装饰。
- 标题承诺是否在正文兑现。

### xiaohongshu_note

- 标题/封面是否 3 秒说清“讲什么、为什么点开”。
- 是否一个核心点 + 具体例子，而不是功能清单。
- 卡片是否一图一焦点、caption 能读。
- 正文是否短、可粘贴，标签是否相关。
- 是否保留 scope，不把一次演示写成普遍规律。

## 3. Judge 运行

- 2 次独立 judge（不同模型或不同顺序），每次只输出 JSON 分数 + 一句理由。
- 交换 A/B 顺序做位置偏差检查；记录 verbosity bias。
- 聚合取中位数/均值，保留两次分歧。
- 输出 `judge-<case>.json`，不写入产品 UI。

## 4. 校准与门禁

- 用 6–12 个人工标注算 judge-human 一致率（Spearman / pairwise agreement）。
- 低于阈值先调 rubric，不调文章；不按单篇调 prompt。
- 通过后 judge 只作 regression advisory；发布仍需用户人工验收。
- 不做真人 reader test 的替代声明；模型 judge 不能写成 reader pass。

## 5. 当前状态（2026-11-07）

- 未运行 judge；`evals/product_v1/reports` 只有 deterministic checks。
- `pass@1/pass^k` 为 null，等 judged trials。
- 下一步：补 BV1ix long/wechat，收 6–12 个人工标注，再跑 2 次 judge 校准。
