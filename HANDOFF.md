# HANDOFF.md — 当前任务交接

> 2026-10-31。规则见 [AGENTS.md](AGENTS.md)，设计见 [architecture.md](architecture.md)，事实状态见 [STATE.md](STATE.md)。

## 1. 项目现在能做什么

一条视频可以走通：

```text
substrate units
  → sentences / passages（deterministic）
  → writing-level claims（1 次模型/视频）
  → coverage-aware EvidencePack（deterministic）
  → 1 次 Writer
  → reader-first explainer（含 span 绑定/quote）
```

当前能力边界：

- 已跑通两个 P0 样本：BV1AC（reader 1,865 字）、BV17（reader 1,497 字）；两者 writer 校验 complete。
- 有模型 advisory 冷读（BV1AC/BV17），但**不是真实 reader test/A-B**；不能当质量验收。
- 只有 reader-first explainer v0.1（**provisional**）一个 skill；社媒/讲义/企业知识/脚本/二创/生图提示词还没有 skill。
- 没有 Verifier、没有发布门实现、没有多视频/多源。
- 帧是时间窗候选，不保证 claim-level 匹配；后续图表/生成图另做。

## 2. 大致结构

- `architecture.md`：v3 架构事实源（证据编译器 / EvidencePack / Skill / Writer / 可选 Verifier / 多文体 / JD）。
- `AGENTS.md`：全局规则/护栏。
- `STATE.md`：当前分支、代码、测试、样本状态。
- `REFERENCES.md`：参考 skill 与 data 的 git 可见索引。
- `handoffs/2026-10-31/`：本次 P0 的审计、报告、样例（历史快照）。
- `src/lunograph/writing_v3/`：transcript / claim_extract / pack_from_claims / one_call_writer / trace。
- `src/lunograph/{core,evidence,knowledge,providers,runtime}`：substrate。
- `skills/writing/reader_first_explainer/`：当前唯一写作 skill（v0.1 provisional）。
- `data/`、`参考素材/skills/`：有效只读输入；完整素材本地只读、不在 git，索引见 `REFERENCES.md`。
- `_archive/_blocked/`：旧架构/旧 AB，已屏蔽。

## 3. 接手任务

1. 对 BV1AC/BV17 做**真实 reader test + 轻量 A/B**（当前只有模型 advisory，不算）。
2. 两篇都过 reader/A-B 后，再决定是否把 transcript/claim/pack/writer 固化为 P1 短文体默认。
3. 做第二个 skill 前，先重新大量调研/二开 `参考素材/skills/` 与本地 `bilibili-render-pdf`；当前 reader-first 只作 provisional，不直接复用。
4. 再考虑第二个 skill（如社媒或讲义）；不要先扩多文体。
5. 不按单篇调参；不手改 reader/claim；不恢复旧链路。

## 4. 当前风险 / 未证明

- 一次 Writer 只有两个样本；质量未由真实读者证明。
- claim extraction 成本：BV1AC 31k、BV17 20k tokens；reasoning 占比高，可优化模型/参数，不加阶段。
- 43/31 条聚合 claim 可能压掉限定/反证；底层 atomic claim/evidence link 仍在。
- pack 按视频时间顺序，Writer 需要重组；若第二文体出现“按视频顺序写”，加 `reader_path` View。
- ASR 误识别/quote 截断仍有（harmonyos/Share/cortis/“时间的验”）；正文用 claim text，quote 只作 audit。
- 当前 skill 只验证 reader-first，且是 provisional；未来可能重写/二开，不把 v0.1 当最终。
- 参考 skill license（bilibili-render-pdf 未知、tomoai CC BY-NC）待审；data 含 cookies，不能入库/外传。

## 5. 关键入口

- 架构：[architecture.md](architecture.md)
- 规则：[AGENTS.md](AGENTS.md)
- 状态：[STATE.md](STATE.md)
- P0 证据：[handoffs/2026-10-31/](handoffs/2026-10-31/)
- 代码： [src/lunograph/writing_v3/README.md](src/lunograph/writing_v3/README.md)
