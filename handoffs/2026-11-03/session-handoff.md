# Session handoff — 2026-11-03

> **快照，不保真。** 新 session 先读 [STARTUP_PROMPT.md](STARTUP_PROMPT.md) 和 [docs/writing-operating-model.md](../../docs/writing-operating-model.md)，再用代码/最新 runs 验证本文件。不要把它当结论。

## 本轮做了什么

- 诊断：当前问题不是“句子像 AI”，而是证据链、机制、内部一致性、来源归属、图注语义、标题/CTA/可分享单元；30 份 LLM-as-Judge + final verifier 反复抓到。
- 通用修复（不是单篇手修）：
  - reader_profile + 两层 brief（短编辑 brief + concept/mechanism/number/source/texture/next）；
  - contract audit（source line/title quote/title numbers/image captions/source gaps/absolutes）；
  - semantic verifier（initial 驱动至多 1 次 repair；final 只读审计交付稿）；
  - polish（风格/voice/术语；保 facts/numbers/quotes/source/claim status）；
  - binding 的 `editorial_terms`（模型知识拉丁术语不再被硬门误杀；numbers/quotes/outside-input 仍是硬门）；
  - 64k provider headroom + 300s timeout；不设 per-call max_tokens；
  - source_map 从帧 OCR 提 channel；chart 图注“视频内容”不是“视频数据”；caption 只描述图里能看到的。
- 最新 runs：`runs/_diag/BV17_workflow_v5/`、`runs/_diag/BV1AC_workflow_v10/`、`runs/_diag/BV1yb_workflow_v1/`。
- judge v5 pack：`runs/_reader_test_2026-11-03/judge_v5/`（A/B 匿名；两份标准 byte-identical copies；旧 `reader_pack/` 未动；尚未跑 30 个 subagent）。

## 当前事实（需自行验证）

- 508 tests passed；分支 `v3`；未提交。
- `BV17_workflow_v5`：partial；final verifier 5（source line channel/演示顺序/机制写成事实/2D caption/“几乎无损”）。
- `BV1AC_workflow_v10`：partial；final verifier 3（创造模式“就是重排”/5 vs 3 图注/Cordis 来源）。
- `BV1yb_workflow_v1`：final article；32k final verifier invalid；64k probe 6（来源行归属/“没有新事实”/“实际作用/每次”/第一人称引语/“第一次”/“治愈系”归属）。64k probe：`runs/_diag/BV1yb_workflow_v1/verifier_final_64k/verifier_report.json`。
- 第一轮 LLM-as-Judge（旧 pack）：current 赢 2/3；candidate P2 −8.0；3/6 红线。
- 真人 reader test：未做。LLM-as-Judge 不是真人。

## 接手点（上一轮判断，供挑战）

- 下一步优先跑 judge v5，验证“新 workflow 是否比旧 current 好”，再按 top problems 做通用修复；不要继续加 stage、不要按单篇手修。
- 最终 verifier residual 是真实问题，当前设计不二次 repair；是否加第二次 bounded repair 是开放问题。
- 视觉图注的语义一致性仍靠 judge/VLM/人工；contract 只查 caption 存在。
- source line 的频道/标题/日期/链接/官方文档仍是最大来源风险；帧 OCR 只能补一部分。
- reader profile 冲突（judge 标准 AI 初学者 vs writer technical baseline）仍未裁决。

## 不要做

- 不伪造 reader test/A-B；不把模型/模拟盲读写成真人。
- 不按单篇/单条 finding 手改；不为单个视频加 hardcode validator/gate/词表。
- 不必要不改 substrate；不读 `_archive/_blocked`、v2 冻结链路、旧 branch/run。
- 不设 per-call max_tokens；不静默截断；partial/unknown 显式。
- 不擅自 commit/revert/publish。
