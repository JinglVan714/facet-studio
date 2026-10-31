# LunoGraph v3 — 证据驱动的视频理解与多形态写作

把视频编译成**可复用、带上下文的证据**，再由**写作 Skill + 一次 Writer**生成文章；引用、时间码、citation 由代码校验/派生，人工发布门保留。

## 先读

1. [architecture.md](architecture.md) — v3 架构事实源（只读为主）。
2. [AGENTS.md](AGENTS.md) — Agent 全局规则/护栏（最高优先）。
3. [HANDOFF.md](HANDOFF.md) — 当前任务交接。
4. [STATE.md](STATE.md) — 当前分支/代码/测试状态。
5. [handoffs/](handoffs/) — 历史交接快照（只读）。

## 结构

- `src/lunograph/writing_v3/`：transcript / claim_extract / pack_from_claims / one_call_writer / trace。
- `src/lunograph/{core,evidence,knowledge,providers,runtime}/`：substrate。
- `skills/writing/reader_first_explainer/`：当前写作 Skill（v0.1 provisional）。
- [REFERENCES.md](REFERENCES.md)：参考 skill 与 data 的 git 可见索引。
- `data/`、`参考素材/skills/`：有效只读输入；完整素材本地只读、不在 git。
- `_archive/_blocked/`：旧架构/旧 AB，已屏蔽。

## 运行

```bash
PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m pytest -q
```

Python 3.11.14。P0 链路与命令见 [src/lunograph/writing_v3/README.md](src/lunograph/writing_v3/README.md)。

## 边界

- `data/`、`参考素材/` 只读；不自动 commit/push/publish。
- 证据优先：不编造画面/引用；生成图只作 editorial。
- 默认 1 次 Writer；高风险才加 1 次可选 Verifier。
