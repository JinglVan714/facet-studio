# LunoGraph v3 项目上下文 / 交接

## 1. 项目是什么

以不可变视频资料和可追溯证据为底座，把视频编译成可复用证据，再用写作 Skill + 一次 Writer 生成多种文体；引用/时间码/citation 由代码派生，人工发布门保留。不是“视频转写后让模型自由写”。

## 2. 当前基线（按顺序读）

1. [docs/v3/00-architecture.md](docs/v3/00-architecture.md)：v3 唯一架构基线（证据编译器、View/EvidencePack、Skill、Writer、可选 Verifier、多文体、关键帧、JD、小号 Harness、开源复用）。
2. [docs/v3/00-architecture-self-check.md](docs/v3/00-architecture-self-check.md)：架构书自检、残余风险。
3. [docs/v3/03-p0-one-call.md](docs/v3/03-p0-one-call.md)：P0 一次 Writer 实测。
4. [docs/v3/04-doc-audit.md](docs/v3/04-doc-audit.md)：v3 文档漂移审计、已修问题、仍会带偏后续的风险。
5. [docs/v3/02-substrate-audit.md](docs/v3/02-substrate-audit.md)：BV1AC 145 微 claim 审计、385→116→32→43 的前序重做、trace/receipt。
6. [docs/v3/01-skill-reuse-map.md](docs/v3/01-skill-reuse-map.md)：已有 skill/开源素材的复用与 license 注意。

**有效输入（只读、不在 git）**：

- `data/`：视频数据/字幕/关键帧。要读，但只读；不要改写。
- `参考素材/skills/`：可复用的 skill 参考（含 rednote/great-writer/humanizer/seedance 等）。要读；复用前查 license。
- `docs/_frozen/v2-2026-10-31/`：v2 冻结素材，可作历史参考；不要恢复 v2 的 R1–A5/P1 链路、body/validator/gate。

**已屏蔽（旧/错误架构，不要读）**：

- `_archive/_blocked/video-writing-product-architecture/`：旧领域架构，已判定错误；不要引用它的对象/四操作/流程。
- `_archive/_blocked/AB/`：旧 A/B 结果；不要作为质量依据。
- 旧分支 `rebuild-v2`/`main` 仍有旧代码；不要从它们恢复写作链。

## 3. 当前快照（2026-10-31）

已实现/跑通：

- v3 架构书 + 自检；v2 已冻结为素材。
- P0 原型：`transcript_merge`、`claim_extract`、`pack_from_claims`、`v3_one_call_writer`、`trace`。
- BV1AC（656 秒）：
  - 385 ASR units → 116 sentences → 32 passages（deterministic，0 模型）
  - 32 passages → 43 claims（1 次 claim extraction，31,277 tokens）
  - 43 claims → 40-claim pack（53 sentences/20 frames/7 gaps，47.8k chars）
  - 1 次 Writer：reader **1,865 字**，25 grounded/9 editorial，1 图，38,071 tokens
  - 总调用 **2 次**、总 **69,348 tokens**；校验 `complete`。
- 关键文件：[reader.md](docs/v3/examples/BV1AC_reader.md)、[writer_output.json](docs/v3/examples/BV1AC_writer_output.json)、[pack](docs/v3/examples/BV1AC_pack.json)、[claims](docs/v3/examples/BV1AC_claims.json)、[passages](docs/v3/examples/BV1AC_passages.json)。

**没有做/没有证明**：

- 没有真实 reader test/A-B；不能把 P0 当质量验收或发布通过。
- 只有 BV1AC 一首样本；second video 未跑。
- 没有多文体 skill（只有 reader-first explainer）。
- 没有 Verifier、P1 v3 门、reconstruct/redesign/review 四操作。
- 帧只是时间窗候选，不保证 claim-level 匹配；后续图表/生成图另做。

## 4. 接手点

1. 先读 §2 的 v3 文档；不要先读 v2 或旧 run。
2. 用 **BV17 第二视频**跑同一链路（transcript → claims → pack → 1 Writer），验证不是 BV1AC 单例；**不按 BV1AC 调参**。
3. 第二视频也成立后，做真实 reader test + 轻量 A-B（至少 2 视频/2 知识形态）。
4. 再决定是否把 transcript/claim/pack/writer 固化为 P1 短文体默认。
5. 多文体（社媒/讲义/企业知识/脚本/二创/生图提示词）后置；先证明 reader-first 闭环。

P0 命令/文件：

- `src/lunograph/writing_v3/transcript.py`：units → sentences/passages
- `src/lunograph/writing_v3/claim_extract.py`：passages → claims（1 次模型）
- `src/lunograph/writing_v3/pack_from_claims.py`：claims → EvidencePack（coverage-aware）
- `src/lunograph/writing_v3/one_call_writer.py`：pack + skill + request → reader
- `skills/writing/reader_first_explainer/`：SKILL.md/examples/manifest/SOURCES
- trace：`trace.jsonl` + `stage_receipts/`（inputs/outputs/sha/counts/decisions/samples）

## 5. 接手时优先质疑

允许质疑已有实现；先报告，再改。重点怀疑：

1. **一次 Writer 是否真的够**：只有 BV1AC 一首；没有 reader test/A-B；第二视频可能完全不同。
2. **claim 聚合粒度**：43 条是“写作级 aggregate claim”，不是 substrate 的 atomic Claim；可能压掉限定/反证。要不要保留 atomic ClaimGroup/关系？
3. **claim extraction 成本**：31k tokens/视频，其中 21.6k reasoning；对 11 分钟视频是否值得？能否换更便宜模型/降 reasoning，或对短社媒直接用 ASR？
4. **pack 组织**：仍按视频 segment 时间顺序，Writer 需要重组；是否需要 `reader_path` View？还是让 skill 承担？
5. **EvidencePack 是否过重**：40 claims/47.8k chars 对 2k 文章是否仍偏多；能否更少但更准？
6. **skill 质量**：reader-first skill 只跑过一次；来源归属/结论/boundary 是否稳定，未验证。
7. **帧**：20 个时间窗候选，claim-level 匹配未保证；后续图表/生成图方案可能改变需求。
8. **四操作/长期对象**：generate/reconstruct/redesign/review、Feasibility、VideoContentProfile、KnowledgeRelation 等是产品方向，但旧架构文档已屏蔽；是否在 P1/P2 加，是新决策，不从旧文档继承。
9. **license**：bilibili-render-pdf 本地 skill 未见 LICENSE；tomoai 是 CC BY-NC，只作参考；对外发布前要审。

## 6. 不要做

- 不恢复 v2 多阶段链；不把 v2 body/validator/gate 搬回来。
- 不手改单篇 reader/claim；只修工作流。
- 不为单个文体/单条 finding 加 validator/gate/词表。
- 不伪造 reader test/A-B；不自动发布。
- 不把 P0 的 1,865 字/38k tokens 当最终质量或成本承诺。

## 7. 开发纪律（不变）

- 证据优先：EvidenceSnapshot 是唯一事实底座；模型写作，代码编译/校验引用。
- 默认 1 次 Writer；高风险才加 1 次可选 Verifier；不恢复 v2 的多阶段 waterfall。
- 多文体 = 多 Skill/View；不为每个文体加 body/validator/gate。
- 不做固定 length/focus 硬门；容量只作预算/截断/审计。
- 失败/partial/unknown 一等；不静默降级；不自动发布。
- `data/`、`参考素材/` 只读；不伪造画面/生成图当证据。
- 复用开源前先审 license/安全/维护；不照搬与证据优先冲突的整条 pipeline。

完整项目纪律见 [CLAUDE.md](CLAUDE.md)；本文件只做交接快照，不替代 CLAUDE.md。
