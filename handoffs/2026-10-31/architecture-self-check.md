# v3 架构书自检

> 日期：2026-10-31
> 对象：[architecture.md](../../architecture.md)
> 方法：结构检查 + 关键词覆盖 + 人工通读 + 一致性检查。**未写代码、未跑模型。**

## 1. 自检结论

**通过（设计基线）**。架构书可以作为 v3 的讨论/实现起点，但 P0 PoC 前仍需验证三个关键假设：

1. 一次 Writer + EvidencePack 的质量能否接近/超过 v2 的 7 次链；
2. Skill prompt 能否稳定控制连续性/来源归属/结论写法；
3. EvidencePack 的上下文窗口/预算能否覆盖 2,000 字级文章而不爆上下文。

如果这三个假设不成立，按 Roadmap 的停止条件先加 1 次 Verifier，再考虑分节；**不先恢复 v2  waterfall**。

## 2. 覆盖检查

| 检查项 | 状态 | 说明 |
|---|---|---|
| 产品定义/成功标准 | ✅ | 输入/输出、质量、速度、复用、质量门 |
| 设计原则 | ✅ | 证据优先、一次生成、Skill、可选 Verifier、容量 advisory、复用开源 |
| 总体架构/数据流/调用预算 | ✅ | 分层、默认 1 Writer、高风险 +1 Verifier、最小 artifact |
| 视频证据编译器 | ✅ | Source→Temporal→Evidence→Knowledge；ASR 为主 |
| 当前数据结构 | ✅ | Unit/Assertion/Claim/EvidenceSpan/Link/TemporalOutline/FramesIndex/KnowledgeSnapshot |
| 证据组织/复用/不平铺 | ✅ | Contextual Evidence Unit、View、预算/截断、跨文体复用 |
| 视频类型/边界 | ✅ | 口播/课程/演示/访谈/长视频；纯视觉/直播不默认 |
| 和 Skill 直接看 ASR 的区别 | ✅ | 对比表 + one-off 轻量模式 |
| 写作 Skill 本质/包结构/注册表 | ✅ | 角色/方法/示例/输出 schema/self-review/渐进披露 |
| Skill 解决来源归属/recap/boundary | ✅ | 角色、方法、示例、self-review、一次上下文 |
| Writer 一次调用 | ✅ | 输入/输出/plan header/binding/repair/失败状态 |
| 可选 Verifier | ✅ | 触发条件、只看文章+证据、不 loop、何时不用 |
| 确定性校验/渲染 | ✅ | binding/quote/ID/citation/audit/reader hygiene/media |
| 质量门 | ✅ | 按文体；reader/A-B/专家/table read/人工 publish |
| 多文体 | ✅ | 深度解析、讲义、社媒、企业知识、视频脚本、二创、生图提示词 |
| 关键帧 | ✅ | ASR 定节点、节点附近候选、VLM/OCR 选帧、real vs generated |
| JD 对应 | ✅ | 多 Agent/规划/工具/记忆/决策/评测/Context/框架/工程/作品 |
| 小号 Harness | ✅ | Run/Stage/Attempt、Writer/Verifier、plan header、usage/trace、tool receipts |
| 复用/二开开源 | ✅ | Anthropic Agent Skills、WriteHERE、STORM、InkOS、OmniWriter、视频工具 |
| 最小数据契约 | ✅ | EvidencePack/SkillManifest/WriterOutput/Binding/Audit/Verifier/Publish |
| 失败/观测 | ✅ | writer/binding/render/verifier/partial/unknown；usage/trace/replay |
| Roadmap/停止条件 | ✅ | P0–P4、one-call 失败先加 Verifier |
| 非目标/开放问题 | ✅ | 不做全量 harness/不做 per-form gate/不自动发布 |
| v2 冻结/不干扰 | ✅ | v2 只作素材；无 v2 R1–A5 默认链 |
| 容量 advisory | ✅ | 明确不做固定 length/focus 硬门 |
| 自检链接 | ✅ | 本文件已创建 |

## 3. 结构检查

- 文件：`architecture.md`，917 行、约 26k 字符。
- 20 个 H2 章节：文档定位、产品定义、成功标准、设计原则、总体架构、视频证据编译器、写作 Skill、Writer、Verifier、确定性校验与渲染、质量门、多文体、关键帧、JD/小号 Harness、复用开源、最小数据契约、失败/观测、Roadmap、非目标/开放问题、术语/总结。
- 没有把 v2 的 R1–A5/P1 链路写成 v3 默认；v2 仅作为冻结素材/可选复用。
- 没有新增 per-form body/validator/gate；多文体由 Skill/View 表达。
- 没有固定 length/focus 硬门；容量只作预算/截断/审计。

## 4. 发现的问题与修正

1. **初稿没有显式写“容量 advisory”**：只在 Writer 里写长度 advisory，原则层不够显眼。已增加原则 14：“不做固定 length/focus 硬门；长度/证据量只作预算/截断/审计。”
2. **“写入一次”关键词检查是误报**：正文使用“一次写完/一次生成/默认一次 Writer”，语义覆盖；不改。
3. **P0 的 `<150k tokens` 是目标，不是实测**：已在 §2.2 写明“以实际模型为准；先测量，不写死”。自检记为“待 PoC 验证”。
4. **“light transcript mode”只提了概念，没有 schema**：保留为开放问题；P0 先做 EvidencePack 默认，one-off 轻量模式后置。
5. **长文/多源只给了方向，没有详细合同**：这是有意的（后置 P3）；v3 当前只做短/中等文章的设计基线。
6. **开源复用只列候选，没有 license/安全结论**：已在 §14 写明“License/安全/维护先审；pin 版本；adapter 边界”；P0 再调研，不直接依赖。
7. **讲义 View 写成 `procedure/timeline/frame/formula/code`，但 §5.3 View 列表没有 formula/code**：已改为 `procedure/timeline/frame（含公式/代码抽取）`，避免把内容类型误写成 View。
8. **链接检查**：v3 文档、根入口、frozen README 的相对链接全部通过；`docs/v2` 已不存在，v2 内容完整移入 `docs/_frozen/v2-2026-10-31/`。

## 5. 一致性检查

- “默认 1 Writer”与“高风险 +1 Verifier”一致：Verifier 不是默认阶段，是风险触发。
- “plan header 同一次输出”与“小号 plan/harness”一致：保留 plan artifact，不保留 plan 调用。
- “多文体”与“不做 per-form validator/gate”一致：Skill/View 承载差异，通用校验复用。
- “证据可追溯”与“一次生成”一致：Writer 输出 span 级 binding，代码校验；不靠多轮 review。
- “ASR 为主 + 关键帧”一致：关键帧是证据候选，不是独立摘要源。
- “v2 冻结”与“选择性复用”一致：v2 代码/报告作为素材，不作为 v3 默认链路。

## 6. 残余风险 / 待 PoC 验证

1. **Skill prompt 质量**：角色/方法/示例能否稳定控制来源归属、结论 synthesis、boundary，而不是靠规则。
2. **EvidencePack 预算**：2,000 字文章需要多少证据/上下文；长视频如何截断而不丢关键机制。
3. **一次 Writer 的事实风险**：无独立 Verifier 时，grounded span 的语义支持是否足够；高风险触发条件是否可靠。
4. **多文体一致性**：同一证据在深度解析/社媒/脚本/生图中是否保持一致；View 是否足够。
5. **开源 license/安全**：第三方 skill/工具的 license、prompt injection、维护状态。
6. **长文/多源**：分节 Writer、多源冲突、检索视图；当前只给方向。
7. **质量门成本**：reader/A-B/专家 review 的采集成本；不能伪造读者。

## 7. 通过/不通过标准

**通过**：架构书覆盖产品、证据、Skill、Writer、Verifier、校验、渲染、多文体、关键帧、JD、开源、失败/观测、Roadmap；没有把 v2 链路/ per-form gate / 固定容量门带回来。

**不通过**：缺少视频处理/证据复用、缺少多文体、缺少 JD、缺少失败状态、把 v2 链路当默认、为每个文体加 validator/gate、把一次 Writer 写成多阶段 waterfall、没有质量门。

当前结论：**通过设计自检**；下一步是 P0 Skill/EvidencePack 原型与一次 Writer PoC，待用户确认后再写代码。
