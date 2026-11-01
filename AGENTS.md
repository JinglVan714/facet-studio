# AGENTS.md — 全局规则 / 护栏

本文件是任何 agent 的防跑偏入口。**先读 [architecture.md](architecture.md)，再读 [HANDOFF.md](HANDOFF.md)、[STATE.md](STATE.md)。** 架构只读；状态/历史不进架构。

## 1. 事实源与边界

- `architecture.md` 是 v3 设计事实源；只读为主。不要往架构里写“现在做到哪/我曾经改了什么”。
- `HANDOFF.md` 是当前任务交接；`STATE.md` 是当前分支/代码/测试事实；`handoffs/` 是历史快照，只读。
- 旧架构/旧结果已屏蔽：`_archive/_blocked/video-writing-product-architecture/`、`_archive/_blocked/AB/`。不要读、不要引用、不要恢复。
- v2 只作冻结素材：`docs/_frozen/v2-2026-10-31/`。不要恢复 v2 的 R1–A5/P1 链路、body/validator/gate、旧 prompt。
- 旧分支 `rebuild-v2`/`main` 仍有历史代码；不要从旧分支/旧 run 恢复对象或链路。

## 2. 写作硬规则

- **证据优先**：EvidenceSnapshot 是唯一事实底座（暂时不开启外部联网+用户补充素材注入，但可以由模型自身知识调整）；模型写作，代码编译/校验引用/时间码/citation。
- **默认 1 次 Writer**：短文章一次生成；高风险才加 1 次可选 Verifier；不先恢复多阶段 waterfall。
- **Skill 优先**：角色/读者模型/方法/示例/self-review 控制写作；不用词表/规则怪谈。
- **多文体 = 多 Skill/View**：不为每个文体加 body/validator/gate。
- **容量 advisory**：不做固定 length/focus 硬门；只作预算/截断/审计。
- **证据带上下文**：不拍平成 claim 列表，不拆成失去上下文的句子碎片；View 引用 ID，不新增事实。
- **ASR 为主**：关键帧在 ASR 关键节点附近挑；`real_frame`/`text_experiment`/`no_demo`；生成图不当视频证据。
- **Reader/Audit 分离**：reader 无内部 ID/citation/时间码/审计语言；来源归属按读者影响判断，不按词表。
- **失败一等**：partial/unknown/insufficient evidence 明确记录；不静默降级；不自动发布；人工 `publish_approved` 是唯一发布门。
- **不单例适配**：≥2 视频/知识形态/文体结构复现才进通用层；不按单条 finding/单篇调参；不手改 reader/claim。

## 3. 输入与安全

- `data/`：9 个视频证据，有效只读输入；不改写。结构以用户后续提供为准；`data/cookies/` 不读、不入库、不外传。
- `参考素材/skills/`：17 个参考仓库，有效只读输入；复用前查 license。当前 `reader_first_explainer` 是前序 session 自动生成的 v0.1 provisional **占位**；它不是已验收 skill，不作为基线；writing 层从零设计，不继承它。skill 从零一个个做，开始前先重新调研/二开这些参考 + 本地 `bilibili-render-pdf`。
- `REFERENCES.md`：本地参考/证据的 git 可见索引；完整 `data/`、`参考素材/skills/` 保持本地只读，不入库。
- `_archive/`、旧 run、旧 audit/reader：不读，除非用户明确要求。
- 不自动 commit/push/publish；不伪造 reader test/A-B；不编造画面/生成图当证据。
- 复用开源/第三方 skill 前审 license、安全、维护状态；不照搬与证据优先冲突的整条 pipeline。

## 4. 上下文维护

- 断点/换 session：更新 `HANDOFF.md`（当前任务、能做什么、下一步）和 `STATE.md`（分支/代码/测试事实）。
- 历史交接放 `handoffs/<date>/`，只追加，不改旧快照。
- `architecture.md` 只写设计；发现架构问题先报告，确认后再改。
- 不要把“操作记录/历史决策”写进 `HANDOFF.md`；写当前快照和接手点。
- 文档之间出现冲突：以 `architecture.md` + `AGENTS.md` 为准；先报告，不静默改架构。

## 5. 开发纪律（不变）

- 开发时，将每一个步骤做扎实，不要动不动就端到端，动手前思考这个环节的所有输入（接收到的所有输入是否极致高效合理、逻辑清晰且符合该阶段及整体工作流。同样适用于输出）、输出（是否是满足现阶段、是否结构清晰流畅能被后续高效消费快速成本低）。（尤其是涉及到模型调用）。
- 客观分析写作层怎么样才能最高效率利用写作、最快理解（注意力不涣散）、成本最低？（以上同样适用于substrate以及其他部分）
- 思考数据的trace是否合理，最好保存下来便于迭代；不要设什么最小门槛/硬指标/现阶段开发（容易越走越深，越走越错）给后续挖坑。
- 思考清楚每一个开发环节的边界，不要死磕，从整体业务出发思考开发到哪里就收益不高。
- 只修整体的通用工作流，不手改单篇出现的问题；不按单条 finding 调参；不要硬编码硬适配个例。
- 不为单个文体/单条 finding /单个视频加 validator/gate/词表等硬编码；≥2 视频/知识形态/文体结构复现才进通用层。
- 不恢复 v2 多阶段链；不把 v2 body/validator/gate 搬回来。
- 不伪造 reader test/A-B（要让开发者自己测）；不自动发布。
- 不把 P0 样本或者其他任何历史样本的 1,865 字/38k tokens 当最终质量、成本或长度承诺。

## 6. 阶段门（2026-11-01 修正：进入 writing 层）

- 当前阶段是 **writing 层设计/落地**。substrate v1 已冻结并作为可信底座；默认 light path，claim 可选 audit/reuse。参考 [docs/substrate-v1-freeze.md](docs/substrate-v1-freeze.md)。
- **非必要不再优化/改动 substrate**；除非发现真实阻塞（错误、不可用、审计不可信）。发现 substrate 问题先报告，不静默改。
- writing 层**从零设计，对照 JD**；不继承现有 writing 实验/占位 skill（`skills/writing/reader_first_explainer`、`one_call_writer`、`prose_writer_probe`、`comprehension_view`、`writer_view`、`bind_merged_frames`）。它们只作历史/参考，不是基线。
- 新 session 先读 architecture/AGENTS/HANDOFF/STATE/substrate freeze，再读代码，再自行规划；本文件不提供 writing 路线。
- writing 层仍遵守 §2/§3/§5：证据优先、默认 1 Writer、多文体 = Skill/View、不伪造 reader test/A-B、不自动发布、不按单篇调参、不为单个文体加 validator/gate。
- 质量门/评测由 writing 设计定义；reader test/A-B 必须真实，不能用模型/模拟盲读冒充。模型调用仍记录 system/user prompt（hash + 原文路径）、raw response、usage（含 reasoning/cached）、latency、finish_reason、validation、decision。
- 先测后调：优化模型/参数/prompt 前先有 trace 和 before/after；不凭感觉调，不按单条 finding/单篇调参。
- 详细 substrate v1 合同/接口见 [docs/substrate-v1-freeze.md](docs/substrate-v1-freeze.md)；S0/S1/view 文档是历史，不是当前基线。

## 7. 素材消费与硬性措施（2026-11-01 修正）

- **默认 light path**：Writer 读 edited text（no claims/IDs/timecodes）+ frames；claim 层是可选 audit/reuse，不是默认输入。full pack/source_map 只作 audit。旧的 A+C+D、lean view、index+parts 是历史实验，不是当前默认。
- **不硬截断**：`max_chars` 只 advisory；`over_budget` 记录；frame caption cap 必须报告 `caption_truncated`/`caption_full_chars`；不静默删内容。
- **skill 只作参考**：本地 17 个 skill 是素材；当前 writing 层从零设计，不直接搬参考 skill 的整条 pipeline/prompt，也不复用占位 skill。
- **不按单篇修**：任何 view/排序/覆盖/格式修复都必须跨 ≥2 视频复现；不手改 claim/reader。
- **substrate v1 只读**：writing 层通过 [docs/substrate-v1-freeze.md](docs/substrate-v1-freeze.md) 的接口使用它；非必要不改 substrate。
- 详细契约见 [docs/substrate-v1-freeze.md](docs/substrate-v1-freeze.md)；旧 [docs/substrate-view-contract.md](docs/substrate-view-contract.md) 是历史。
