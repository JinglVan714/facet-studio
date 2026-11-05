# Claude Code 入口

开始任何任务前，按顺序只读：

1. `handoffs/2026-11-03/NEXT_SESSION_PROMPT.md` — 先认知，再决定下一步。
2. `docs/writing-rebuild-brief.md` 的 §2（好 writing）+ §3（开发纪律）；其余按需。
3. `AGENTS.md` 的全局护栏。
4. `architecture.md`：先看 §0.1 阅读地图；机会地图看 §1/§6.5/§11/§13.1/§14，分层看 §4.1，substrate 看 §5/§12。§4.2–4.3、§6.3.1、§7–§10 是旧实现，不要当当前代码。
5. 最后看 `STATE.md` + `HANDOFF.md` 的当前快照。
6. 只有需要评测时，才读 `runs/_reader_test_2026-11-03/reader_pack/评价方法.md`、`5个persona.md`。

**不要再跑 5 persona × N 篇的 30 份 subagent 评审**：太贵，收益递减。

**不要读**旧写作层的 memo/runs/skill/judge/operating model（已归档，历史，不是基线）。

本文件只做入口，不复制规则或状态。
