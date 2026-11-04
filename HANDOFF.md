# HANDOFF — writing layer clean rebuild（2026-11-04）

> 当前任务：写作层**干净重做**。旧写作层（brief/verifier/repair/polish/source line/claim status + skill v1/v2）已归档在 tag `archive/writing-v1-2026-11-04`。**不要基于旧链改，不要读旧 memo/runs/skill/judge。**
> 新 session 入口：`handoffs/2026-11-03/NEXT_SESSION_PROMPT.md`；方法/认知：`docs/writing-rebuild-brief.md`。

## 事实

- 分支 `v3`；归档 tag `archive/writing-v1-2026-11-04`；新 session 直接 `git checkout archive/writing-v1-2026-11-04` 开新分支。
- 归档前测试：526 passed。
- substrate v1 冻结；写作层通过既有接口消费，不改 substrate。
- 旧写作层 + skill v1/v2：已归档，不是基线。
- 旧 runs、旧 judge、旧 memo：都是历史；不要当当前证据。

## 下一步

- 新 session 从归档 tag 开新分支/副本，从零做第一个 skill。
- 只读两份标准 + `docs/writing-rebuild-brief.md` + 开源参考原始仓库 + AGENTS 全局护栏。
- 质量门：LLM-as-Judge；用户会自己跑 30 份。
- 不在旧 pipeline 上修；先让 skill 独立成立，再决定最小管线。
