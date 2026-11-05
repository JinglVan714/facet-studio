# HANDOFF — writing layer clean rebuild（2026-11-05）

> 当前状态（2026-11-05）：多文体进行中；**社媒（小红书 + 公众号）优先，视频脚本第二步；md 内容先过关；HTML 后续；PDF 暂不做；demo shell 完全体后置**。方向/阶段/验收见 [docs/multiform-roadmap.md](docs/multiform-roadmap.md)。
> 已有：一个写作 skill + 3 篇可发布文章；social-note / video-script skills、skill_runner / form_checks、4 个未定稿草稿。旧写作层（brief/verifier/repair/polish/source line/claim status + skill v1/v2）已归档在 tag `archive/writing-v1-2026-11-04`。**不要基于旧链改，不要读旧 memo/runs/skill/judge。**

## 当前方向（2026-11-05）

- **多 Agent 编排**：Lead/Editor orchestrator + `LeadPlan` + specialists（Writer / Consistency / Visual / Platform）+ 共享 RunState + bounded agents-as-tools + trace；当前 writer→consistency→svg→checks 是固定 workflow，待接 Lead。定义见 roadmap §2。
- **JD**：§3 的 10 行全部映射到核心，没有“未覆盖”；`待补/待接` 都有 consumer + 验收。
- **P1（已确认，直接 B）**：LeadPlan orchestrator + Platform Editor + ViewRetriever + run manifest/receipts + per-skill eval；小红书/公众号 × BV1ix/BV17 → 4 个发布包。
  - 小红书包：`card_copy.md` / `title.md` / `body.md` / `tags.md` / `images/` / `publish.md` / `post.md`。
  - 公众号包：`article.md` / `title_candidates.md` / `publish.md`。
  - 不设硬长度；emoji 可用不强制；真实帧优先；不伪造画面。
- **视频脚本（P2）**：同一 orchestrator 加 Script specialist；镜头表/旁白/真实帧 vs 示意；不伪造画面。
- **调研（P0，已完成）**：本地 + GitHub 的小红书/公众号 prompt/写作逻辑，见 [social-writing-reuse-map.md](docs/social-writing-reuse-map.md)。

## 已完成

- 多文体基础（2026-11-05）：`skills/writing/social-note/`、`skills/writing/video-script/`、`src/lunograph/writing_v4/skill_runner.py`、`form_checks.py`、video-article manifest；`tests/writing_v4` 34 passed，全 suite 560 passed；4 个草稿未定稿。
- 新 skill：`skills/writing/video-article/`（内容稿制：角色/读者/方法/形状/证据边界/自审 + 匿名例子 + 素材/写作分离规范）。
- 最小管线：`src/lunograph/writing_v4/`；一次 writer 调用，不做 brief/claim/verifier/repair 多 stage。
- 素材/写作分离：Writer 只读 `content.md`（连续正文 + 图示 N + figures），不知道视频/素材包/管线；出处由 `run.py` 补。
- 写作通路已补齐：`writer → consistency review/edit → SVG spec/render → floor checks`，入口 `src/lunograph/writing_v4/pipeline.py`。
- SVG 通路：writer/editor 只留 `<!-- svg: ... -->`；`svg_pass` 让模型返回图表 JSON 规格，本地确定性渲染 `figures/svg-XX.svg`，模型不写 SVG。严格视觉缺口门槛下，3 篇 CLEAR 都有真实图，未强插 SVG。
- 编辑通路会剥离来源行再 review、edit 后原样接回；新增标题范围、分类层数、证据范围、工作痕迹、视觉缺口检查。本轮由通路自己修掉 CFA 范围、三层/两类、标题承诺、图注口径、动作清单等问题。
- 当前可发布终稿：BV1ix / BV17 `content_final_v4`，BV1B `content_final_v4c`；正文“作者”0 次；地板检查全过。3 篇 HOLD 仍为 `content_final_v3`，不发布。
- 新 3 条从 substrate units 合并 transcript；原数据无 source.json，出处用 BV 号；`material.md` 已补。
- 第一轮评审稿 `content_final/`；第二轮评审稿 `content_final_v2/`。
- 第二轮评审已完成：`review_v2/SUMMARY.md`；团队 76.3 / 76.1 / 72.6，无 RISK HOLD；通用问题为内部矛盾/步骤/范围。
- 历史 30 judge（旧质量门，5 persona × 6 篇）：3 CLEAR（BV1ix 81.65 / BV17 80.48 / BV1B5 74.05）+ 3 HOLD（BV13 77.95 / BV1zn 72.40 / BV1eUh 69.95）；只作参考，不重跑。
- 交付包 `deliverables/writing-skill/` 已改为只呈现文章的作品集：`site/index.html`、`site/print.html`、`site/writing-articles.pdf`；无架构、评分、HOLD、官方 30 证据。内部说明/证据/SKILL 副本在 `runs/writing_rebuild_2026-11-04/deliverable_internal/`。
- 上下文入口已整理：`NEXT_SESSION_PROMPT.md`（认知顺序/边界）、`docs/writing-rebuild-brief.md`（方法/纪律）、`AGENTS.md`（护栏）、`README.md`（项目地图）；旧 `STARTUP_PROMPT.md`/`session-handoff.md` 已标历史，不再作为入口。
- 下一步不预设：对照 JD/岗位要求补作品集、扩多文体 skill、修展示层问题，或其他方向；由新 session 先认知后给 2–3 个方向，用户裁决。
- 输入 A/B：完整素材包 3/4 胜；连续文本在 BV1ix 因配料表/细节胜。格式不是决定因素，编辑距离 + 具体细节/表格才是。
- 证据索引：`runs/writing_rebuild_2026-11-04/INDEX.md`。

## 下一步

- 按 [docs/multiform-roadmap.md](docs/multiform-roadmap.md) 执行：P0 调研已完成（[social-writing-reuse-map.md](docs/social-writing-reuse-map.md)）→ 先讨论 §5 取舍（平台编辑 A/B、emoji、长度、标题候选、图）→ P1 社媒 → P2 视频脚本 → P3 JD 落点（LeadPlan/trace、ViewRetriever、tool receipts、per-skill eval、平台角色）→ P4 HTML → P5 demo shell。**PDF 暂不做。**
- 已生成 4 个草稿在 `runs/writing_rebuild_2026-11-04/multiform/`，不作为最终产物；先修 runner 的 figures 复制、video-script 的“内容稿”泄漏，再按调研结果重跑。
- 历史 30 份 judge 只作参考；**不再跑 5 persona × N 篇的批量 subagent 评审**。需要外部视角时做小规模、针对性抽查 + 人工 acceptance。
- 通用层只收 ≥2 视频/文体复现的规则；不按单篇调参。
- 可选：VLM 画面描述或多模态 writer；当前帧 caption 主要是 OCR，纯文本 writer 不描述没看到的画面。
- 不改 substrate；发现真实阻塞先报告。

## 事实

- 分支 `writing-rebuild`；归档 tag `archive/writing-v1-2026-11-04`。
- 旧写作层 + skill v1/v2：已归档，不是基线。
- 旧 runs、旧 judge、旧 memo：都是历史；不要当当前证据。
- 本次未 commit/push。
