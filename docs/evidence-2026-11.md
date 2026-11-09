# Run evidence（2026-11）

> 可提交的证据摘要。原始 run 在本地 `runs/`（gitignored，不入库）；本文件只记录可核对的 run id、形态、产物规模、tokens、时延和人工验收状态。
> 这些数字是**运行证据**，不是 writing quality 分数；人工验收仍是唯一发布门。
> 评测口径见 [jd-mapping-2026-11.md](jd-mapping-2026-11.md) §4；P4 报告见 `evals/product_v1/reports/`。

## P1/P2/P3 产品 run（LibreChat + MCP）

| run_id | 视频 | 形态 | 状态 | 正文 | 图 | 调用 | tokens | 时延 | 验收 |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| `20261106T131015Z_BV17DHC6CELr_wechat_article` | BV17 | 公众号 | approved | 2,767 | 5 | 1 | 23,216 | 45.0s | approved |
| `20261106T130634Z_BV17DHC6CELr_long_article` | BV17 | 深度总结 | approved | 2,985 | 6 | 1 | 21,148 | 58.8s | approved |
| `20261107T032530Z_BV17DHC6CELr_xiaohongshu_note` | BV17 | 小红书 | approved | 1,274 | 6 | 2 | 16,208 | 49.4s | approved |
| `20261106T132229Z_BV1ixpd6GENc_xiaohongshu_note` | BV1ix | 小红书 | approved | 999 | 3 | 1 | 8,405 | 16.4s | approved |
| `20261107T080924Z_BV13EHX64EaY_wechat_article` | BV13 | 公众号 | approved | 2,734 | 3 | 2 | 31,157 | 51.0s | approved |
| `20261107T132341Z_BV1B5411A7ax_xiaohongshu_note` | BV1B | 小红书 | approved | 725 | 3 | 2 | 17,327 | 53.9s | approved |
| `20261108T040941Z_BV1ixpd6GENc_long_article` | BV1ix | 深度总结 | approved | 2,130 | 4 | 2 | 21,153 | 61.4s | approved |
| `20261108T041238Z_BV1ixpd6GENc_wechat_article` | BV1ix | 公众号 | typeset | 1,876 | 2 | 2 | 31,513 | 92.7s | pending |
| `20261108T095810Z_BV1brgs6mE7a_wechat_article` | BV1brgs6mE7a（新视频，含视觉审计） | 公众号 | approved | 1,720 | 1 | 7 | 32,363 | 74.6s | approved |
| `20261109T125434Z_BV1brgs6mE7a_xiaohongshu_note` | BV1brgs6mE7a | 小红书 | typeset | 697 | 1 张卡片 / 0 关键帧 | 6 | 17,642 | 59.4s 墙钟 | pending |
| `20261109T131911Z_BV1brgs6mE7a_xiaohongshu_note` | BV1brgs6mE7a | 小红书 | approved | 793 | 1 张卡片 / 0 关键帧 | 6 | 15,862 | 51.2s 墙钟 | approved |
| `smoke_long_pdf` | BV17 | 深度总结 | approved | 2,813 | 4 | 2 | 19,608 | 47.2s | approved |

- P3 workflow run `20261107T132341Z_BV1B5411A7ax_xiaohongshu_note`：LangGraph stages `intake → plan → approval → write → typeset → review`；plan/review 两次 interrupt；`workflow.json` 记录 stages/events/usage；2 calls / 17,327 tokens / approved。
- P3 manual plan gate `20261107T124434Z_BV1B5411A7ax_wechat_article`：plan 暂停 → `changes_requested`，未写正文；用于验证 HITL 不会绕过审批。
- 原始 run 目录含 `run_meta.json`、`lead_plan.json`、`workflow.json`、`publish_review.json`、`reader.html`、`wechat.html`、`xhs_export/`、`article.pdf`；本地可查，不入库。

## Run trace / 可观测（2026-11-08）

- 本地 Run Detail：`/runs/<run_id>`（Live SSE / Trace / Stats）；`/runs` 看板：最近 runs + p50/p95/tokens/error/checks/grounding；`/runs/<run_id>/api/trace` + `/stream` 读本地 JSONL/JSON。workflow stages、`llm_calls.jsonl`、`tool_calls.jsonl`（workflow stage 作为 tool/step span）、`decision_records.jsonl`、P4 机器检查、grounding candidates；预览页右上/页脚“运行数据”链接；`get_run.trace` 返回摘要；`trace.html` 仅作导出/降级。
- 真实 run 的 trace 示例（拷贝 `20261108T095810Z_BV1brgs6mE7a_wechat_article` 到 `_trace_demo_wechat` 验证，不改原 run）：6 stages / 7 LLM calls / 6 tool spans / 3 decisions / 32,363 tokens / 74,597 ms / checks 15/15 / grounding 4 candidates。
- 真实 workflow run `20261108T154015Z_BV1B5411A7ax_wechat_article`（BV1B 中华田园猫，auto approve）：6 stages / 2 LLM calls / 6 tool spans / 3 decisions / 36,619 tokens / 105,409 ms / checks 15/15 / grounding 0 / 正文 2,288 字 / 内容稿 10 图 / **正文引用 0**（旧内容格式 `图示 N` 未进入视觉审计）；`trace.html` 自动生成，**待用户验收**。
- 视觉审计修复后重跑 `20261109T072111Z_BV1B5411A7ax_wechat_article`：6 候选 / 0 通过（B 站水印/人物/UI）、0 关键帧、2,194 字、8 LLM calls / 43,841 tokens / 128.3s / checks 15/15 / grounding 4；来源行已补“本文根据 B 站视频（BV1B5411A7ax）整理”；**待用户验收**（不在本轮 A/B/D 验收内）。0 图是审计结果，不是渲染丢图。
- 端到端聊天 run `20261109T131911Z_BV1brgs6mE7a_xiaohongshu_note`：用户给 BV 号后直接 `start_workflow(background=True, auto_plan=True)`，不再先 resolve；消息级运行卡从“正在启动”更新到“等待验收”；`wait_workflow` 只返回摘要/资产数，最终回复 793 字 / 1 张卡片 / 0 关键帧，没有裸 URL，聊天里只有一张运行卡，无“执行过程”分组。
- 这是开发/面试观测页，不是写作质量分，也不是幻觉率；工具/决策 span 来自 workflow stage 边界，不伪造额外执行层。

## P4 deterministic + grounding（2026-11-09 复跑）

- 最新报告：`report-20261109T145839Z.json` / `.md`；grounding：`grounding-20261109T145839Z.json` / `.md`。
- `cases.json`：capability 6（2 视频 × 3 形态，全部有 run）+ regression 4（含 1 条 P5 新视频 E2E）。
- `cases_run`：10 cases / 9 unique runs；`cases_missing`：0（`reg_pdf_code_block` 与 `cap_bv17_long` 指向同一 run）。
- `contract_pass_rate`：1.0（10/10 cases；含 artifact/trajectory，机器合同，不含人工验收）。
- `trajectory_pass_rate`：1.0（30/30 checks；30 = 4 个 workflow case ×6 项 + 6 个 legacy case ×1 项）。
- `error_rate`：0.0；`planner_trace_rate`：0.6（6/10；旧 P1/P2 run 没有 planner trace，单独记录）。
- `manual_acceptance_rate`：0.9（9/10 cases，8/9 unique；仅 BV1ix 公众号 1 个 case **待用户验收**）。
- `deterministic_pass_rate`：0.9（包含待验收；不是 writing quality）。
- p50/p95 latency：52,421 / 92,738 ms（plan+write）；tokens total：222,498（10 cases；9 unique runs 201,350，重复 long run 多算一次）。
- grounding：9 artifacts / 16 candidate flags（引语 7 / 范围 6 / 专名 3；数字 0，修复了 CJK 相邻数字被漏检的 regex）；**不是幻觉率，不是 writing 质量分**；未做人工 adjudication。
- `pass@1/pass^k = null`：没有 judged trials，不伪造。
- 最新端到端 UI run `20261109T131911Z_BV1brgs6mE7a_xiaohongshu_note` 已验收（6 calls / 15,862 tokens / 51.2s 墙钟（LLM 调用合计 44.6s）；review=approved，15/15 checks），它不在 10 个固定 cases 内，不计入 manual acceptance。
- 报告：`evals/product_v1/reports/report-20261109T145839Z.{json,md}`、`grounding-20261109T145839Z.{json,md}`；单 run 报告：`run-report-...-20261109T150830Z.md`。
- 修复：Pandoc 无 caption 的 longtable 在 PDF 模板里触发 `No counter 'none' defined`；模板加 `\newcounter{none}`，BV1ix long PDF 已重排 6 页。重新 typeset 现在也会同步 `workflow.json` 的 typeset stage/errors，避免旧的 partial 永久留在 trace 里。

## P5 证据层（2026-11-07/08）

- 迁移备份 17 tests、`evidence_mcp --selftest` 对 `data/` 通过。
- `content_manuscript` 从 BV17 缓存重建 4,213 字 / 10 图。
- 新视频缓存桥（BV1AC，无 content 缓存）：`run_ingest` 复用缓存、无模型调用，`build_content_manuscript` 产出 21,823 字 / 23 图；说明“证据层 → content.md”桥可用。
- 产品 ingest 默认 `content_only=True`：跳过 contract/L1（写作层不消费）；完整证据层用 `include_evidence=True`。
- **真实新视频 E2E（BV1brgs6mE7a，2 分钟）**：
  - yt-dlp 下载 + 抽帧成功；DashScope ASR **3.0** 的免费额度耗尽（status=44），没有伪造成功。
  - 切到同一端点的 `qwen-audio-3.1-asr-flash-streaming` 后直接可用：2 分钟音频 40.9s、rtf 0.339、字级时间戳可用；没有使用本地 ASR/OCR。
  - `content_only` 跳过 L1；ingest 53.8s（layer0 53.7s，VLM 复用已有 4 帧缓存），content 1,577 字 / 4 图；短画面参考格式重建后 1,052 字 / 4 图。
  - 之后走完整 workflow（plan → write → typeset），run `20261108T052817Z_BV1brgs6mE7a_wechat_article`：1,981 字 / 2 图 / 2 calls / 24,563 tokens / 54.3s。
  - 视觉审计接入后，产品 run `20261108T095810Z_BV1brgs6mE7a_wechat_article`：审计 4 个候选 / 0 通过（UI/水印）、0 关键帧、1 个 SVG；1,720 字 / 7 calls（4 审计 + plan + 2 write）/ 32,363 tokens；合同与轨迹全过，**人工验收 approved**。
  - 结论：新视频下载 + DashScope ASR 3.1 + VLM + content + 产品 workflow + deepseek-flash 视觉审计已验证；3.0 的免费额度问题不再阻塞。

## 观察（不是质量分）

- 旧 content manuscript 的“图示”OCR 注释占比高（7 条视频约 16%–75%；BV17 约 50%，BV1brgs6mE7a 约 56%，BV1AC 约 75%）；新流程改为短 `画面参考（可选）` + writing-layer 视觉审计，已不再把 OCR 全文塞给 writer。
- 小红书标题/第一人称亲历、公众号数字偏多/图表不足属于内容层 backlog；用户已明确后续统一改，不按单篇调参。
