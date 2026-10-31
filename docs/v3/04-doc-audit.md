# v3 文档审计：有没有走偏 / 会不会带偏后续

> 日期：2026-10-31
> 范围：docs/v3/00–03、README、self-check、skill reuse map；video-writing-product-architecture/（非历史领域参考）；agent/CLAUDE/README 入口。
> 结论：v3 架构方向没有走偏，但原文有 7 处会误导后续实现/验收的点，已修；剩余风险见 §3。

## 1. 已修（会直接带偏）

1. **`quote` 是否必须在正文**
   - 原文 §9.1 说“quote 必须在 span text 中”；P0 Writer 的 `quote` 是 audit binding，正文改写后不在 text 里，导致 25 个假失败。
   - 已改为：quote 是 bound evidence 的精确子串；正文可改写，不要求逐字出现；只有正文直接引用时才要求一致。
   - 影响：避免后续把“干净改写”误判为绑定失败，也避免为了过校验把 ASR 原文塞进正文。

2. **v3 `claims` 与 substrate atomic Claim 混淆**
   - v3 pack 的 43 条是“写作级聚合 claim”（1–3 句）；产品架构/证据层的 `Claim` 是 atomic proposition + EvidenceClaimLink。
   - 原文没有区分，后续可能把聚合 claim 当原子事实源，或丢掉限定/反证。
   - 已加命名说明：pack `claims` 是 writing-level aggregate；atomic Claim/EvidenceClaimLink 仍是底层；未来可重命名为 `claim_groups`/`writing_claims`。

3. **四操作范围未写**
   - 产品架构有 generate/reconstruct/redesign/review；v3 只实现 generate，review 只由可选 Verifier + P1 部分承担。
   - 原文没有说明，后续可能误以为 v3 已覆盖四操作。
   - 已在 §1 加操作范围：v3 P0/P1 先 generate；reconstruct/redesign/review 后置。

4. **P0 Roadmap 过期**
   - 原文 P0 还写“1 次 Writer PoC，对比 v2 approved reader”；实际已完成 BV1AC，2 次调用（claim extraction + writer），未做 reader test/A-B。
   - 已更新 P0 状态、总成本 69k、下一步 BV17 + reader/A-B。
   - `03-p0-one-call.md` 标题“one-call”已注明：指写作链 1 次 Writer；上游 claim extraction 1 次/视频，总 2 次。

5. **View 选择缺少覆盖约束**
   - 原文 View 规则只说预算/顺序；P0 用 lexical top-k 时差点把 seg6 的标准模式挤掉。
   - 已加：**先覆盖 passage/beat，每个 passage 至少一条 claim，再按 request focus 补**；这是工作流规则，不是单篇修。

6. **产品架构 README 的“当前基线”指向不存在的 docs**
   - 它写 `docs/architecture-overview.md`/`project-snapshot.md`/`roadmap.md`，这些不存在；会误导新 session。
   - 已改为：当前基线是 docs/v3/00-architecture.md；本目录是 v0.5 领域参考，不是实现规格。

7. **入口快照低估成本**
   - agent/CLAUDE/README 只写 writer 38k，没写 claim extraction 31k；会让人以为总额 38k。
   - 已统一为 claim extraction 31k + writer 38k = 69k。

## 2. v3 与产品架构的关系（防走偏）

产品架构 01–12（v0.5，2026-10-28）是**领域参考**，不是当前实现规格。可参考的长期对象/原则：

- SourceAsset/DerivedAsset → Observation/EvidenceSpan → EvidenceSnapshot；
- TemporalOutline 与 KnowledgeSnapshot 两套坐标系；
- Claim/EvidenceClaimLink、ClaimBinding、冲突/缺口/来源独立；
- 四操作 generate/reconstruct/redesign/review；
- 语义模式（expository/procedural/narrative/dialogic/...）；
- 质量/版本/安全/评测边界；
- WritingFeasibility、VideoContentProfile、Semantic Views 等长期对象。

v3 当前有意简化掉/后置：

- 四操作只做 generate；
- 没有独立 Feasibility/VideoContentProfile/Method Router；
- KnowledgeSnapshot/relations 在短单视频不是默认必需；
- 没有 PlanDraft/ContentPlan/PresentationPlan 的完整对象链，plan_header 代替；
- 没有完整 Review/Repair/Revision 链，optional Verifier + P1 代替。

**不要因为产品架构写了这些对象，就在 P1 前把它们全部实现**；也不要因为 v3 简化了，就把长期对象全删。先证明 reader-first 短文体闭环，再按需接。

## 3. 仍会带偏后续的风险

1. **把 P0 当质量验收**：只有 BV1AC 一首，1,865 字，reader test/A-B 未做。文档已标“不是 reader pass”，但后续仍可能误读。
2. **把一次 Writer 当“总一次调用”**：上游 claim extraction 是 1 次/视频；同视频换文体可复用，但新视频仍有 extraction 成本。
3. **claim 聚合压掉限定/反证**：43 条聚合 claim 可能合并了多个命题；产品架构要求 atomic Claim。后续需要检查聚合 claim 是否丢失 counterevidence/qualifier；必要时保留 atomic `claim_ids`。
4. **pack 时间顺序 ≠ 读者路径**：Writer 这次重组成功，不代表每次都能；如果第二视频/社媒出现“按视频顺序写”，应加 `reader_path` View，而不是改单篇。
5. **EvidencePack 仍可能偏大**：40 claims/47.8k chars；对 2k 文章可接受，但社媒/短脚本应更小；按文体 view budget，不写死。
6. **帧候选不是演示匹配**：20 帧只是时间窗候选；后续图表/生成图会改变媒体策略，不要把 current frame selection 当最终方案。
7. **skill 只验证过一次**：reader-first skill 的来源归属/结论/boundary 还不稳定；第二视频/reader test 前不要扩多文体。
8. **license**：bilibili-render-pdf 本地 skill 未见 LICENSE；tomoai 是 CC BY-NC；对外发布前必须审。
9. **产品架构/v3 两套术语**：新 session 若混用 Claim/Plan/ContextPack 会重复造对象；以 v3 术语为准，产品架构只取长期概念。

## 4. 结论

- v3 架构方向与 P0 实现基本一致：证据编译、一次 Writer、确定性校验、多文体后置。
- 已修的 7 处是“会直接把实现带错”的文档问题；剩余 9 条是待验证/待产品化风险，不是当前 blocker。
- 新 session 读文档时：**v3 是基线，产品架构是参考，v2 是素材**；P0 是原型，不是验收。
