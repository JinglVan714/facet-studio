# v3 文档审计：有没有走偏 / 会不会带偏后续

> 日期：2026-10-31
> 范围：当时的 docs/v3/00–03（现 handoffs/2026-10-31/）、README、self-check、skill reuse map；入口文档。
> 结论：v3 架构方向没有走偏，但原文有 7 处会误导后续实现/验收的点，已修；剩余风险见 §3。

## 1. 已修（会直接带偏）

1. **`quote` 是否必须在正文**
   - 原文 §9.1 说“quote 必须在 span text 中”；P0 Writer 的 `quote` 是 audit binding，正文改写后不在 text 里，导致 25 个假失败。
   - 已改为：quote 是 bound evidence 的精确子串；正文可改写，不要求逐字出现；只有正文直接引用时才要求一致。
   - 影响：避免后续把“干净改写”误判为绑定失败，也避免为了过校验把 ASR 原文塞进正文。

2. **v3 `claims` 与 substrate atomic Claim 混淆**
   - v3 pack 的 43 条是“写作级聚合 claim”（1–3 句）；substrate 的 `Claim` 是 atomic proposition + EvidenceClaimLink。
   - 原文没有区分，后续可能把聚合 claim 当原子事实源，或丢掉限定/反证。
   - 已加命名说明：pack `claims` 是 writing-level aggregate；atomic Claim/EvidenceClaimLink 仍是底层；未来可重命名为 `claim_groups`/`writing_claims`。

3. **操作范围未写**
   - `generate / reconstruct / redesign / review` 是长期操作入口；v3 只实现 generate，review 只由可选 Verifier + P1 部分承担。
   - 原文没有说明，后续可能误以为 v3 已覆盖四操作。
   - 已在 §1 加操作范围：v3 P0/P1 先 generate；其余后置。

4. **P0 Roadmap 过期**
   - 原文 P0 还写“1 次 Writer PoC，对比 v2 approved reader”；实际已完成 BV1AC，2 次调用（claim extraction + writer），未做 reader test/A-B。
   - 已更新 P0 状态、总成本 69k、下一步 BV17 + reader/A-B。
   - `03-p0-one-call.md` 标题“one-call”已注明：指写作链 1 次 Writer；上游 claim extraction 1 次/视频，总 2 次。

5. **View 选择缺少覆盖约束**
   - 原文 View 规则只说预算/顺序；P0 用 lexical top-k 时差点把 seg6 的标准模式挤掉。
   - 已加：**先覆盖 passage/beat，每个 passage 至少一条 claim，再按 request focus 补**；这是工作流规则，不是单篇修。

6. **旧架构/旧 AB 仍在可见环境**
   - `video-writing-product-architecture/` 和 `AB/` 是旧/错误架构/旧结果，之前仍作为本地参考出现在入口文档里，会误导新 session。
   - 已移到 `_archive/_blocked/`，并在 agent/docs 里标明“不要读、不要引用”；v3 文档不再以它为参考。

7. **入口快照低估成本**
   - agent/CLAUDE/README 只写 writer 38k，没写 claim extraction 31k；会让人以为总额 38k。
   - 已统一为 claim extraction 31k + writer 38k = 69k。

## 2. 已屏蔽旧架构

`_archive/_blocked/video-writing-product-architecture/` 和 `_archive/_blocked/AB/` 已移出可见目录：

- 不要读、不要引用、不要按它的对象/四操作/流程实现。
- 旧分支 `rebuild-v2`/`main` 仍保留历史代码；不要从它们恢复写作链。
- v3 的 `Claim / Plan header / EvidencePack / Skill / Writer / Verifier` 术语以 [architecture.md](../../architecture.md) 为准。
- v2 只保留为 `docs/_frozen/v2-2026-10-31/` 素材；`data/` 和 `参考素材/skills/` 是有效只读输入。

## 3. 仍会带偏后续的风险

1. **把 P0 当质量验收**：只有 BV1AC 一首，1,865 字，reader test/A-B 未做。文档已标“不是 reader pass”，但后续仍可能误读。
2. **把一次 Writer 当“总一次调用”**：上游 claim extraction 是 1 次/视频；同视频换文体可复用，但新视频仍有 extraction 成本。
3. **claim 聚合压掉限定/反证**：43 条聚合 claim 可能合并了多个命题；底层 atomic Claim/EvidenceClaimLink 仍在，后续要检查聚合 claim 是否丢失 counterevidence/qualifier。
4. **pack 时间顺序 ≠ 读者路径**：Writer 这次重组成功，不代表每次都能；如果第二视频/社媒出现“按视频顺序写”，应加 `reader_path` View，而不是改单篇。
5. **EvidencePack 仍可能偏大**：40 claims/47.8k chars；对 2k 文章可接受，但社媒/短脚本应更小；按文体 view budget，不写死。
6. **帧候选不是演示匹配**：20 帧只是时间窗候选；后续图表/生成图会改变媒体策略，不要把 current frame selection 当最终方案。
7. **skill 只验证过一次**：reader-first skill 的来源归属/结论/boundary 还不稳定；第二视频/reader test 前不要扩多文体。
8. **license**：bilibili-render-pdf 本地 skill 未见 LICENSE；tomoai 是 CC BY-NC；对外发布前必须审。
9. **旧架构残留**：旧目录已屏蔽，但旧分支/旧 run/旧文档仍可能在别处被搜到；不要从 `_archive/`、旧分支、旧 run 恢复对象或链路。

## 4. 结论

- v3 架构方向与 P0 实现基本一致：证据编译、一次 Writer、确定性校验、多文体后置。
- 已修的 7 处是“会直接把实现带错”的文档问题；剩余 9 条是待验证/待产品化风险，不是当前 blocker。
- 新 session 读文档时：**v3 是唯一基线；v2 是冻结素材；旧架构/AB 已屏蔽；P0 是原型，不是验收。**
