# LunoGraph v3 — 证据驱动的视频理解与多形态写作

把视频编译成**可复用、带上下文的证据**，再由**写作 Skill + 一次 Writer**生成文章；引用、时间码、citation 由代码校验/派生，人工发布门保留。

> 当前阶段：**writing 层设计/落地**。substrate v1 已冻结并作为可信底座；writing 层从零设计，不沿用现有 writing 实验或占位 skill。先读 [HANDOFF.md](HANDOFF.md) 和 [docs/substrate-v1-freeze.md](docs/substrate-v1-freeze.md)。

## 先读

1. [AGENTS.md](AGENTS.md) — Agent 全局规则/护栏（最高优先）。
2. [architecture.md](architecture.md) — v3 架构事实源（只读为主）。
3. [HANDOFF.md](HANDOFF.md) — 当前任务交接。
4. [STATE.md](STATE.md) — 当前分支/代码/测试状态。
5. [docs/substrate-v1-freeze.md](docs/substrate-v1-freeze.md) — 已冻结的 substrate v1 接口/证据/限制。
6. [handoffs/](handoffs/) — 历史交接快照（只读）。

## 结构

- `src/lunograph/writing_v3/`：substrate v1 = transcript / claim_extract / pack_from_claims / light_context / edited_transcript / bind_article / quote_hygiene / generate / trace；实验/历史 = one_call_writer / prose_writer_probe / comprehension_view / writer_view / bind_merged_frames / probe 等（不是 writing 基线）。
- `docs/substrate-v1-freeze.md`：substrate v1 的接口、证据、限制；writing 层可信底座。
- `src/lunograph/{core,evidence,knowledge,providers,runtime}/`：substrate。
- `docs/substrate-s0.md`、`docs/substrate-s1-*.md`、`docs/substrate-view-contract.md`、`docs/substrate-view-split.md`：历史/实验记录（不是当前基线；当前看 freeze doc）。
- `docs/reference-writing-scan.md`：本地 17 个 skill + STORM/WriteHERE/Agent Skills 的只读扫描。
- `skills/writing/reader_first_explainer/`：自动生成的占位 skill（未验收；见 `STATUS.md`；不作为 writing 起点）。
- [REFERENCES.md](REFERENCES.md)：参考 skill 与 data 的 git 可见索引。
- `data/`、`参考素材/skills/`：有效只读输入；完整素材本地只读、不在 git。
- `_archive/_blocked/`：旧架构/旧 AB，已屏蔽。

## 运行

```bash
PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m pytest -q
```

Python 3.11.14。当前测试 **426 passed**。substrate v1 链路与命令见 [src/lunograph/writing_v3/README.md](src/lunograph/writing_v3/README.md)；writing 层从零设计，不复用其中的 writing 实验。

## 边界

- `data/`、`参考素材/` 只读；不自动 commit/push/publish。
- 证据优先：不编造画面/引用；生成图只作 editorial。
- 默认 1 次 Writer；高风险才加 1 次可选 Verifier。
