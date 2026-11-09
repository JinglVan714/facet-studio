# HANDOFF — 2026-11-09（收尾版）

> 新 session 从这里进：[handoffs/2026-11-09/NEXT_SESSION_PROMPT.md](handoffs/2026-11-09/NEXT_SESSION_PROMPT.md)。
> 当前事实以 [STATE.md](STATE.md)、[docs/runtime-evidence-2026-11-09.md](docs/runtime-evidence-2026-11-09.md)、`git log`、`runs/` 为准；旧 handoff 只作历史。
> 项目阶段：**功能收口完成，进入 GitHub / 简历发布前的收尾判断**；不再铺新功能。

## 当前是什么

- 产品：**Facet Studio，聊天式内容工作台**。用户给一条视频 + 写作要求，Agent 按需写一种形态（深度总结 / 公众号 / 小红书），在聊天里预览、修改、人工验收。
- 壳：LibreChat（外部 clone `D:/luno_external/librechat`）+ MCP 13 tools + LangGraph workflow + reader/公众号/小红书/PDF。
- 写作：一个产物一次 writer；Lead Planner 只编排，没有 editor/checker；Writer 不知道来源，只读内容稿。
- 证据层：新视频 → 下载/抽帧/ASR/VLM/content.md + figures；写作层仍只读内容稿。
- 可观测：消息级运行卡 + 右侧预览抽屉 + `/runs` 看板 + `/runs/<run_id>`（概览 / Live SSE / Trace / Stats）。

## 当前事实（2026-11-09）

- MCP：13 tools（ingest / list / resolve / compile / plan / write / typeset / get_run / review / start / wait / resume / get_workflow）。
- 最新端到端 run：`20261109T131911Z_BV1brgs6mE7a_xiaohongshu_note` — 793 字 / 1 张卡片 / 0 关键帧 / 6 calls / 15,862 tokens（含视觉审计）/ 51.2s 墙钟（intake→typeset；LLM 调用合计 44.6s）/ `review=missing`（待人工验收）。
- P4 最新：`report-20261109T135534Z` + `grounding-20261109T135557Z`；10 cases / 9 unique runs；contract 1.0；trajectory 30/30；error 0；manual 0.7（7/10 cases，6/9 unique）；planner trace 0.6；p50/p95 52,421 / 92,738 ms；tokens 222,498；grounding 9 artifacts / 16 flags（candidate，不是幻觉率）；pass@k = null。
- 测试：clean clone **315 passed**；本地全量 **619 passed**（差额是 gitignored 的 `tests/writing_v2/` 旧测试）。干净 clone 全量测试已实测通过；skill manifest hash 的 CRLF 可移植性 bug 已修。
- Git：分支 `writing-rebuild`；最新 commit 以 `git log` 为准；**未 push**。`runs/`、`data/`、`vendor/`、`.env` 均不入库。
- 服务（本轮验证时在跑）：LibreChat `http://localhost:3080`、preview `http://127.0.0.1:8765`、Mongo `127.0.0.1:27017`；账号 `facet@example.com / Facet12345!`。Mongo 是内存版，重启后 user/agent 要重建。
- 旧公众号 `20261109T075145Z_BV17DHC6CELr_wechat_article` 的第一张 two-axis 关系图已从 md/HTML/SVG 文件删除，run_meta 的 `svg_assets/figures_referenced` 同步清空并重新排版；Stats 现在 SVG=0、关键帧=0。

## 下一步（按顺序）

1. **认知**：按 [handoffs/2026-11-09/NEXT_SESSION_PROMPT.md](handoffs/2026-11-09/NEXT_SESSION_PROMPT.md) 的阶段 A–D 读架构/产品、做 JD 外部校准、按链路读代码、再判断怎么收。
2. **判断**：先给用户一屏“现状 / 差距 / 3 条优先级”，不要先铺代码。
3. **收尾**：按 [docs/github-resume-checklist-2026-11-09.md](docs/github-resume-checklist-2026-11-09.md) 做 GitHub/简历前检查。
4. **验收**：最新 E2E 仍是 `review=missing`；人工验收是唯一发布门，不自动 approved；验收后重生成 trace.json 和单 run report。

## GitHub / 简历前的主要缺口

- **LICENSE**：根目录没有，需要用户拍板。
- **可公开 demo**：`runs/` 不入库，README 的 run 链接只在本机；需要 `examples/demo` 或脱敏截图。
- **P4 复现**：P4 依赖本地 `runs/`；公开仓库跑不了 10 cases，需要最小 fixture。
- **素材版权**：`deliverables/writing-skill/` 含 B 站视频帧（58 files / 5.8MB），公开前要删/换或明确版权边界。
- **LibreChat 外部 clone**：没有 vendored；需要 bootstrap 脚本/10 分钟启动文档，并在 clean clone 实测。
- **CI**：未接；先跑 clean clone 315 tests，P4 fixture 后再接 gate。
- **README 顶部**：需要 30 秒定位 + 架构图 + demo + 测试/证据命令 + Known limitations。

## 常用命令

```bash
# 本地全量测试
PYTHONPATH=src PYTHONUTF8=1 python -m pytest tests

# clean clone / 公开代码面
git archive HEAD | tar -x -C /tmp/facet_clean
cd /tmp/facet_clean && PYTHONPATH=src PYTHONUTF8=1 python -m pytest tests

# P4 harness（需要本地 runs/）
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.product \
  --cases evals/product_v1/cases.json --out evals/product_v1/reports --gate
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.grounding \
  --cases evals/product_v1/cases.json --out evals/product_v1/reports

# 单 run report
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.run_report \
  --run-id <run_id> --out evals/product_v1/reports

# 预览/看板
PYTHONPATH=src python -m facet_studio.preview_server
# http://127.0.0.1:8765/runs
```

LibreChat 启动见 [integrations/librechat/README.md](integrations/librechat/README.md)；展示层改动在 [patches/client-ui.patch](integrations/librechat/patches/client-ui.patch)。

## 边界（不变）

- 一个产物一次 writer；Lead Planner 只编排；没有 editor/checker。
- Writer 不知道来源；只拿到“这件事的完整内容”；不核验内容本身、不做百科。
- 产品按需一种形态；不默认 bundle；多形态 = 多次请求。
- 不写死字数/结构；不按单篇调参；active skill 不出现具体视频/产品/人物。
- 用户人工验收是唯一发布门；测试绿/跑通不算通过。
- 不评 writing 质量；不做 judge/人工质量打分；P4 只测运行数据/产物合同/grounding candidates。
- 不自动 commit/push/publish；不读 `data/cookies/`；不改 substrate v1。
