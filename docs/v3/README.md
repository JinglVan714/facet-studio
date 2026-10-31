# docs/v3

v3 唯一架构基线。

1. [00-architecture.md](00-architecture.md)：证据编译器 + 写作 Skill + 一次 Writer + 可选 Verifier + 确定性校验/渲染；视频处理、证据复用、多文体、关键帧、JD、小号 Harness、开源复用。
2. [00-architecture-self-check.md](00-architecture-self-check.md)：架构书自检清单、覆盖检查、发现的问题与修正、残余风险。
3. [01-skill-reuse-map.md](01-skill-reuse-map.md)：已有 skill/开源素材的复用映射与 license 注意。
4. [02-substrate-audit.md](02-substrate-audit.md)：BV1AC 145 微 claim 审计、385→116→32→43 的前序重做、trace/receipt。
5. [03-p0-one-call.md](03-p0-one-call.md)：P0 一次 Writer 实测（1,865 字、writer 38k + claim extraction 31k、校验 complete）。
6. [04-doc-audit.md](04-doc-audit.md)：v3 文档漂移审计、已修问题、仍会带偏后续的风险。

v2 已冻结为素材：本地磁盘 `docs/_frozen/v2-2026-10-31/`（不入 v3 git 分支），只作参考，不是基线。

有效输入（只读、不在 git）：`data/`（视频数据）、`参考素材/skills/`（skill 参考）。

已屏蔽（旧/错误架构，不要读）：`_archive/_blocked/video-writing-product-architecture/`、`_archive/_blocked/AB/`。

当前阶段：v3 架构 + P0 原型（Skill / EvidencePack / one-call Writer）已跑通一次；尚未做真实 reader test/A-B，未跑第二视频。下一步：第二视频验证 + reader test/轻量 A-B；不按单篇调参。
