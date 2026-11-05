# LunoGraph v3 — 证据驱动的视频理解与多形态写作

把视频编译成可复用、带上下文的证据，再由写作 Skill 生成文章/社媒/脚本等多文体产物。

> 当前阶段（2026-11-05）：**多文体进行中**；社媒（小红书 + 公众号）优先，视频脚本第二步；md 内容先过关；HTML 后续；PDF 暂不做；demo shell 完全体后置。方向/JD/验收见 [docs/multiform-roadmap.md](docs/multiform-roadmap.md)。先读 [NEXT_SESSION_PROMPT.md](handoffs/2026-11-03/NEXT_SESSION_PROMPT.md)。

## 先读（按顺序，不要多读）

1. [NEXT_SESSION_PROMPT.md](handoffs/2026-11-03/NEXT_SESSION_PROMPT.md) — 先认知，再决定下一步。
2. [docs/writing-rebuild-brief.md](docs/writing-rebuild-brief.md) 的 §2（好 writing）+ §3（开发纪律）。
3. [AGENTS.md](AGENTS.md) — 全局护栏。
4. 架构看 [architecture.md](architecture.md)：先看 §0.1 阅读地图；机会地图看 §1/§6.5/§11/§13.1/§14，分层看 §4.1，substrate 看 §5/§12。§4.2–4.3、§6.3.1、§7–§10 是旧实现，不要当当前代码。
5. 最后看 [STATE.md](STATE.md)、[HANDOFF.md](HANDOFF.md) 的当前快照。
6. 需要评测时，再读两份 reader_pack 标准；不要一开始就读。

## 结构

- `src/lunograph/writing_v3/`：substrate v1（冻结）：transcript / claim_extract / pack_from_claims / light_context / edited_transcript / bind_article / quote_hygiene / generate / trace。只读 substrate 相关文件，不要读同目录的旧写作实验。
- `src/lunograph/writing_v4/`：当前写作层：`run`（一次 writer）/ `consistency_pass`（review → Must fix → 最小 edit）/ `svg_pass`（占位符 → JSON 规格 → 本地渲染）/ `pipeline`（全通路）/ `article_checks`（地板）/ `skill_runner`（按 manifest 跑任意文体）/ `form_checks`（article/social/script floor）。
- `skills/writing/video-article/`：当前写作 skill（内容稿制；角色/读者/方法/形状/证据边界/自审 + 匿名例子）。
- `skills/writing/social-note/`、`skills/writing/video-script/`：多文体 skill（社媒先做，脚本第二步）；各自有 manifest/prompt/匿名例子。
- `docs/multiform-roadmap.md`：多文体方向、JD 表、阶段与验收。
- `deliverables/writing-skill/site/`：articles-only HTML / PDF 作品集；`site/index.html` 是入口。HTML/PDF 展示层后续再调；PDF 暂不做。
- `runs/writing_rebuild_2026-11-04/`：当前运行产物与历史评审；`deliverable_internal/` 是内部说明/证据。
- `docs/substrate-v1-freeze.md`：substrate v1 接口/证据/限制；只读。
- `REFERENCES.md`、`参考素材/skills/`、`参考素材/skills_downloaded/`：本地参考索引与原始 skill；只读，复用前查 license。
- `data/`：有效只读输入；完整素材本地只读、不在 git。
- `_archive/_blocked/`：旧架构/旧 AB，已屏蔽。

## 运行

```bash
PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m pytest -q
```

Python 3.11.14。当前 **560 passed**（其中 `tests/writing_v4` 34）。substrate v1 链路见 [src/lunograph/writing_v3/README.md](src/lunograph/writing_v3/README.md)；写作层从 `writing_v4/run.py`、`writing_v4/pipeline.py` 或 `writing_v4/skill_runner.py` 进入。

## 边界

- `data/`、`参考素材/` 只读；不自动 commit/push/publish；不读 `data/cookies/`。
- 证据优先：不编造画面/引用；生成图只作 editorial。
- 一次 Writer + 一次有界 consistency edit；不加 verifier/brief/claim 多 stage。
- 不要再跑 5 persona × N 篇的 30 份 subagent 评审；太贵，收益递减。
- 不把个例写进 skill；通用层只收 ≥2 视频/文体复现的规则。
