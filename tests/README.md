# tests

v3 的测试还没有正式建立。当前 P0 的验证是运行记录 + trace，不是测试套件：

- [P0 one-call 报告](../handoffs/2026-10-31/p0-one-call.md)
- [substrate 审计](../handoffs/2026-10-31/substrate-audit.md)
- 样例 reader/claims/pack：[handoffs/2026-10-31/examples/](../handoffs/2026-10-31/examples/)

v2 测试（`tests/writing_v2/`）是冻结素材，不在 v3 分支；不要从它恢复 R1–A5/P1 链路。

下一步：为 `transcript` / `claim_extract` / `pack_from_claims` / `one_call_writer` 建离线 fixture + fake provider 测试；先覆盖 determinism、quote/ID 校验、coverage-aware selection、trace receipt。
