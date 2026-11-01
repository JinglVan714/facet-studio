# 2026-11-01 substrate v1 freeze（历史快照，只读）

> 本文件是历史快照，不是当前基线；当前接口/证据/限制见 `docs/substrate-v1-freeze.md`。

- P0：edited transcript + source_map + article binding；BV1yb anchored 3,521 chars（旧 lean_cw0 12,658，−72%）。
- P1：prose-only + edited text；writer 平均 31,021 → 13,823（−55.4%）。
- P1b：契约加固（不补 acronym/单位、引号逐字、数字逐字）后 unsupported=0；全部样本 writer 均值 11,708（−62.3%）。
- P3：无 claim 轻路径 writer-only 10,766 / 10,374 / 13,931；比 claim+writer 省 69–77%。
- M1：light_context + quote_hygiene + generate；P3 文章经 hygiene 后 binding 全部 complete，long quote=0。
- M1 real：新 light text 真实 Writer 12,988 / 7,492 / 21,577；旧 pipeline −77.7%；BV17 1 个 0.78 舍入。
- 测试：426 passed（v3 122 + v2 304）。
- 当前结论：substrate v1 作为可信底座；claim 可选 audit/reuse；writing 层从零设计。
