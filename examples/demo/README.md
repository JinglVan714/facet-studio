# Demo run：一条视频 → 一篇小红书笔记

这是一份**真实本地 run** 的公开样本，不是合成 fixture。视频是 B 站
[BV1brgs6mE7a](https://www.bilibili.com/video/BV1brgs6mE7a)
《突发！DeepSeek Harness 开源，智能体一切皆插件》（机器之心官方，约 2 分钟）。

> 只放生成文本和文字封面卡；**没有放任何视频帧/封面/转写**。来源与权利说明见
> [../NOTICE.md](../NOTICE.md)。

## 这次 run 的事实

| 项 | 值 |
|---|---|
| 形态 | 小红书（`xiaohongshu_note`） |
| 产物 | `note.md`（793 字）+ 1 张 1080×1440 文字封面卡 |
| 关键帧 | 0（4 个候选帧未通过视觉审计，降级文字封面） |
| 模型调用 | 6 次（plan 1 + 视觉审计 4 + write 1） |
| tokens | 15,862（含视觉审计 6,940） |
| 机器链路 | 51.2s 墙钟（LLM 调用合计 44.6s） |
| 人工验收 | approved（用户验收，不是自动发布） |

这是**单条样本**，不是写作质量分，也不是生产 SLA。完整口径见
[docs/runtime-evidence-2026-11-09.md](../../docs/runtime-evidence-2026-11-09.md)。

## 文件

- `note.md` — 最终笔记（Markdown，可编辑源）
- `reader.html` — 排版后的阅读页（含复制按钮；打开可看成品）
- `xhs_export/01_cover.png` — 3:4 文字封面卡（项目生成，不是视频帧）
- `run_meta.summary.json` — 脱敏 run 摘要（阶段/字数/调用/tokens/验收）
- `trace.summary.json` — 脱敏 trace 摘要（stage / LLM call / tool span / decision）

## 怎么复现

公开仓库不包含视频和 `runs/`；复现需要自备 `.env` 和视频：

```bash
# 1) 新视频 → content.md + figures（P5 证据层；需要 DashScope key）
PYTHONPATH=src python -c "from facet_studio.ingest import ingest_source; print(ingest_source('https://www.bilibili.com/video/BV...', profile='fast'))"

# 2) 启动聊天/预览（完整产品壳见 integrations/librechat/README.md）
PYTHONPATH=src python -m facet_studio.preview_server

# 3) 在 LibreChat 里让 Agent 写小红书；或走 CLI/MCP 工具
```

P4 harness 的可复现最小样例见
[evals/product_v1/fixtures/](../../evals/product_v1/fixtures/)（合成 fixture，不是本样本）。

## 边界

- 一个产物一次 writer；没有 editor/checker。
- Writer 只读内容稿，不知道来源；不核验内容本身。
- 视觉审计默认 0 关键帧，宁可不放图。
- 人工验收是唯一发布门；本样本已验收，但仓库不自动发布。
