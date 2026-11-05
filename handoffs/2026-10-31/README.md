# 2026-10-31 — v3 P0 快照

当时的项目能力：单视频 → sentences/passages → claims → EvidencePack → 1 次 Writer，reader-first 文章；BV1AC/BV17 两个样本校验 `complete`。

文档：

- [architecture-self-check.md](architecture-self-check.md) — 架构书自检与残余风险。
- [skill-reuse-map.md](skill-reuse-map.md) — skill/开源素材复用与 license 注意。
- [substrate-audit.md](substrate-audit.md) — ASR 碎片/145 微 claim 审计与前序重做。
- [p0-one-call.md](p0-one-call.md) — BV1AC P0 实测。
- [doc-audit.md](doc-audit.md) — 架构/入口文档漂移审计。
- [examples/](examples/) — BV1AC/BV17 reader、claims、pack、receipts、metrics；`BV1AC_BV17_advisory_blind_read.json` 是模型冷读，不是真实 reader test。

说明：

- 架构以 [../../architecture.md](../../architecture.md) 的 §0.1 阅读地图为准；本目录只作历史证据，不要当当前实现。
- reader 中引用的 `assets/` 图片未随 git 保存；媒体在本地 run/data 目录。
- 当时尚未做真实 reader test/A-B，只有两个 P0 样本。
