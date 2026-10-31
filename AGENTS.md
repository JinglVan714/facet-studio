# AGENTS.md — 全局规则 / 护栏

本文件是任何 agent 的防跑偏入口。**先读 [architecture.md](architecture.md)，再读 [HANDOFF.md](HANDOFF.md)、[STATE.md](STATE.md)。** 架构只读；状态/历史不进架构。

## 1. 事实源与边界

- `architecture.md` 是 v3 设计事实源；只读为主。不要往架构里写“现在做到哪/我曾经改了什么”。
- `HANDOFF.md` 是当前任务交接；`STATE.md` 是当前分支/代码/测试事实；`handoffs/` 是历史快照，只读。
- 旧架构/旧结果已屏蔽：`_archive/_blocked/video-writing-product-architecture/`、`_archive/_blocked/AB/`。不要读、不要引用、不要恢复。
- v2 只作冻结素材：`docs/_frozen/v2-2026-10-31/`。不要恢复 v2 的 R1–A5/P1 链路、body/validator/gate、旧 prompt。
- 旧分支 `rebuild-v2`/`main` 仍有历史代码；不要从旧分支/旧 run 恢复对象或链路。

## 2. 写作硬规则

- **证据优先**：EvidenceSnapshot 是唯一事实底座；模型写作，代码编译/校验引用/时间码/citation。
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

- `data/`：视频数据，有效只读输入；不改写。
- `参考素材/skills/`：skill 参考，有效只读输入；复用前查 license。
- `_archive/`、旧 run、旧 audit/reader：不读，除非用户明确要求。
- 不自动 commit/push/publish；不伪造 reader test/A-B；不编造画面/生成图当证据。
- 复用开源/第三方 skill 前审 license、安全、维护状态；不照搬与证据优先冲突的整条 pipeline。

## 4. 上下文维护

- 断点/换 session：更新 `HANDOFF.md`（当前任务、能做什么、下一步）和 `STATE.md`（分支/代码/测试事实）。
- 历史交接放 `handoffs/<date>/`，只追加，不改旧快照。
- `architecture.md` 只写设计；发现架构问题先报告，确认后再改。
- 不要把“操作记录/历史决策”写进 `HANDOFF.md`；写当前快照和接手点。
- 文档之间出现冲突：以 `architecture.md` + `AGENTS.md` 为准；先报告，不静默改架构。
