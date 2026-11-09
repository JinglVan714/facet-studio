# 2026-11-08 交接快照

> 这是给新 session 的**干净入口**，不是本轮聊天记录。以代码、`runs/`、`evals/product_v1/reports/` 为准；不要继承本 session 对单篇文章的判断。
> 项目定位：**内容向视频 → 写作**。给一条视频 + 写作要求，按需写一种形态（深度总结 / 公众号 / 小红书），让没看视频的人获得接近亲自看过的理解与体验。不是技术教程排版器，也不是数字解释器。

## 1. 先读（按顺序）

1. [CLAUDE.md](../../CLAUDE.md) — 入口、边界、当前状态。
2. [docs/product-v1-chat-studio.md](../../docs/product-v1-chat-studio.md) — 产品定义/交互/UI/数据分层。
3. [architecture.md](../../architecture.md) §0–§9 — 目标架构、当前代码 vs 目标；文末附录不是当前实现。
4. [docs/writing-v5-architecture.md](../../docs/writing-v5-architecture.md) — 当前写作引擎（writing_v4）。
5. [docs/writing-rebuild-brief.md](../../docs/writing-rebuild-brief.md) §2（好 writing）+ §3（开发纪律）。
6. [docs/visual-strategy-2026-11.md](../../docs/visual-strategy-2026-11.md) — 图/关键帧/载体策略（含已回退的实验）。
7. [docs/jd-mapping-2026-11.md](../../docs/jd-mapping-2026-11.md)、[docs/reuse-stack-2026-11.md](../../docs/reuse-stack-2026-11.md)。
8. [STATE.md](../../STATE.md) / [HANDOFF.md](../../HANDOFF.md) — 快照。
9. 需要评测细节时再读 `runs/_reader_test_2026-11-03/reader_pack/`；不跑 30 judge。

## 2. 当前状态（2026-11-08）

- 产品 v1 已定义；P1/P2 产品原型 + P3 workflow 原型 + P4 deterministic/grounding harness + P5 证据层已接。
- 写作引擎：content manuscript → Lead Planner（只编排）→ 一次 writer → SVG pass → 排版/导出；没有 editor/checker/repair。
- 形态：`long_article` / `wechat_article` / `xiaohongshu_note`；产品按需一种形态，不默认 bundle。
- 证据层：yt-dlp + 抽帧 + DashScope ASR 3.1 + VLM；新视频 `ingest_source` 已端到端跑通；不使用本地 ASR/OCR。
- 关键帧：writing layer 的 `visual_audit.py`（deepseek-flash vision）审计；默认 0，最多 1；B 站素材首轮 0 通过。
- 图：SVG/表格/代码/清单优先；图的数量**不设固定上限**，按关系/步骤复杂度决定；现有 kind 画不出就用表格/文字，不硬配 `compare`/`cards`/`two-axis`；图注默认不加。
- PDF：SVG 先由 Playwright 渲染 PNG（`integrations/pdf/render_svg_png.mjs`）再进 XeLaTeX；封面优先证据层视频封面 `data/<video_id>/cover.jpg`（`acquire_url` 下载 + `source.json` 的 `cover_path`），无封面退回正文第一张真实照片，SVG 永不当封面。
- 测试：**601 passed**（2026-11-08）。未 commit / 未 push。
- P4：10 cases 全有 run；contract 10/10、trajectory 30/30、error 0；manual 7/10（3 个新 machine run 待用户验收）。
- 已回退：`scatter` / `two-track` / `threshold` 三种关系图（用户判定效果不如上一版）；相关代码/skills/测试已删除。

## 3. 新 session 的首要方向

### A. 先把 SKILL 整理干净（明确方向）

- 本 session 已清掉 `skills/writing/reader_first_explainer/` 里直接出现 BV17 / 具体视频数字 / 具体产品的例子（`examples.md`、`SKILL.md`、`STATUS.md`）。
- 但 **SKILL 仍需整体审计**：逐个检查 `skills/writing/**` 的 `SKILL.md` / `examples.md` / `README.md` / `STATUS.md`，把具体视频、产品、人物、单篇数字例子改成通用模式或删掉。
- 检查标准：active skill 不出现具体视频/产品/人物；每个规则至少由 ≥2 视频/文体或通用写作原则支持；不按单篇调参。
- 不要为了“补例子”新增单例；宁可用匿名/通用句式。

### B. 选任意视频，修核心逻辑和面子工程

- 不要从本 session 的 BV17 变体出发；从 `runs/`/`data/` 里**随便选一条没参与过规则设计的视频**，用同一套通用逻辑跑。
- 核心逻辑：
  - **是什么 — 为什么 — 做了什么 — 怎么做**；四问不必对应四个 H2，但读者要能按顺序复述。
  - 关键信息（概念、指标、结果、条件）第一次出现，读者要有足够背景；不是只针对数字。
  - 默认传播版控制信息密度（术语/数字/并列点都算），但**不设固定数字上限**；核心论点/证据需要时保留；用户可以在前端 prompt 里要求“详细说例子 / 少数字 / 多图”等，request 优先。
  - 一段一个意思；开头不写目录段；不指代不存在的图/轴。
- 面子工程：
  - 统一字体/字号/表格/间距/图/封面；公众号、阅读页、PDF、小红书各形态一致。
  - 图要辅助理解，不是复述正文；可以多，但每张都要有明确任务；没有合适载体就表格/文字。
  - 关键帧仍极紧（默认 0，最多 1，必须过审计）。

### C. 不要先做的事

- 不新增架构/页面；不加新的 SVG kind（除非先做独立视觉验证）；不恢复旧 supervisor/demo/词表/P1 两段式。
- 不跑 30 judge；不评 writing 质量分；测试绿/跑通不算内容质量通过。
- 不自动 commit/push/publish；不读 `data/cookies/`；不改 substrate v1。
- 不按单篇调参；不把一篇的“数字/技术教程”问题写成通用 skill 规则。

## 4. 常用命令

```bash
# 测试
PYTHONPATH=src PYTHONUTF8=1 python -m pytest tests -q

# P4 eval + gate
PYTHONPATH=src python -m facet_studio.evals.product --cases evals/product_v1/cases.json --out evals/product_v1/reports --gate
PYTHONPATH=src python -m facet_studio.evals.grounding --cases evals/product_v1/cases.json --out evals/product_v1/reports
PYTHONPATH=src python -m facet_studio.evals.run_report --run-id <run_id> --out evals/product_v1/reports

# P5 新视频（长视频用 CLI；DashScope ASR 3.1 + VLM）
PYTHONPATH=src python -c "from facet_studio.ingest import ingest_source; print(ingest_source('https://www.bilibili.com/video/BV...', profile='fast'))"

# 预览
PYTHONPATH=src python -m facet_studio.preview_server
```

## 5. 需要用户做的事

1. 验收 3 个新 machine run（人工验收是唯一发布门）。
2. 决定 GitHub 公开仓库 license（目前没有 LICENSE）。
3. 内容质量/图的主线仍由用户定方向；新 session 先审计 skill，不要自行改写作认知。

## 6. 边界（不变）

- 一个产物一次 writer；Lead Planner 只编排，不写正文；没有 editor/checker。
- Writer 不知道来源；只拿到“这件事的完整内容”；不核验内容本身。
- 用户人工验收是唯一发布门；不评 writing 质量；不伪造 pass@k。
- 不按单篇调参；active skill 不出现具体视频/产品/人物。
- 不自动 commit/push/publish；不读 `data/cookies/`；不改 substrate v1。
