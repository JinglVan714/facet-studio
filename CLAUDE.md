# Claude Code 入口

本项目当前唯一架构基线是 [docs/v3/00-architecture.md](docs/v3/00-architecture.md)；自检见 [docs/v3/00-architecture-self-check.md](docs/v3/00-architecture-self-check.md)。

v2 已冻结为素材：本地磁盘 `docs/_frozen/v2-2026-10-31/`（不入 v3 git 分支）。只作参考，不自动继承；不要默认恢复 v2 的 R1–A5/P1 链路、body/validator/gate。

## 当前阶段

- v3 架构书 + v2 冻结已完成；P0 原型（Skill / EvidencePack / one-call Writer）已跑通一次。
- BV1AC：385 units → 116 sentences → 32 passages → 43 claims → 40-claim pack → 1 次 Writer；claim extraction 31k + writer 38k = 69k tokens；reader 1,865 字，校验 complete。
- 尚未做真实 reader test/A-B，未跑第二视频；**不按单篇调参**。下一步：第二视频验证 + reader test/轻量 A-B，再决定固化。
- 新 session 先读 v3 架构书/自检/P0 报告；需要历史素材时再看 frozen，但不要把 v2 当基线。

## v3 硬规则

- **证据优先**：EvidenceSnapshot 是唯一事实底座；模型写作，代码编译/校验引用/时间码/citation。
- **默认 1 次 Writer**：短文章一次生成；高风险才加 1 次可选 Verifier；不先恢复多阶段 waterfall。
- **Skill 优先**：角色/读者模型/方法/示例/self-review 控制写作；不用词表/规则怪谈。
- **多文体 = 多 Skill/View**：不为每个文体加 body/validator/gate。
- **容量 advisory**：不做固定 length/focus 硬门；只作预算/截断/审计。
- **证据带上下文**：不拍平成 claim 列表，不拆成失去上下文的句子碎片；View 引用 ID，不新增事实。
- **ASR 为主**：关键帧在 ASR 关键节点附近挑；`real_frame`/`text_experiment`/`no_demo`；生成图不当视频证据。
- **Reader/Audit 分离**：reader 无内部 ID/citation/时间码/审计语言；来源归属按读者影响判断，不按词表。
- **失败一等**：partial/unknown/insufficient evidence 明确记录；不静默降级；不自动发布；人工 `publish_approved` 是唯一发布门。
- **不单例适配**：≥2 视频/知识形态/文体结构复现才进通用层；不按单条 finding loop。
- **复用开源**：先审 license/安全/维护；只借组件/skill，不照搬与证据优先冲突的整条 pipeline。
- `data/`、`参考素材/` 只读；不读封存目录/旧 run/audit/reader.md；不自动 commit/publish。
