# XHS export renderer (P2)

> 用途：把 `note.md` 渲染成便于手动导入小红书 App 的 3:4 图片 + 标题/正文/标签。
> 不是按单篇/单视频调参；所有设计由 `note.md` 的结构（标题、封面文案、配图、标签）驱动。

## 输出

`typeset_article(run_id)` 在 `xiaohongshu_note/xhs_export/` 生成：

```text
01_cover.png      1080×1440 封面（封面文案 + 第一张高信号图）
02_card.png …     1080×1440 正文图（配图/关键帧 + caption）
title.txt
body.txt
tags.txt
source.txt
manifest.json
README.txt
```

App 导入：按 01、02… 顺序上传图片，粘贴 title/body/tags。`README.txt` 里有步骤。

## 渲染器

`render_cards.mjs` 用 Playwright 把 HTML 卡片截图成 PNG。它只依赖 `spec.json`，不读视频/run 状态。

```bash
node integrations/xhs/render_cards.mjs <export_dir>/cards_spec.json
```

Playwright 默认从本地 LibreChat clone 解析：

```text
D:/luno_external/librechat/node_modules/playwright
```

可用 `FACET_STUDIO_PLAYWRIGHT=/path/to/playwright` 覆盖。Node 需在 PATH。

## 设计约束

- 封面 3:4；标题来自 `> 封面：`，没有就用 note 标题。
- 正文图来自 note 的 `## 配图`；caption 原样使用，不新增事实。
- 标签来自 note 的 `## 标签`；没有就空，不编品牌/地点/人群。
- 中文断行用 `word-break: keep-all`，避免把词拆开；长标题自动降字号。
- 无图时只出封面文字卡，不伪造图。
- 不按视频类型/单篇写死分支；kicker 只由 request 决定（request 写“教程”才用教程，否则“笔记”）。
- **图片不裁切**：正文截图放进 3:4 画布内的白色图框，用 `object-fit: contain`，四周保留安全边距；禁止把 16:9 源图用 `cover` 铺满 3:4。
- **统一卡片系统**：封面、正文卡共用纸面底色、品牌眉标、页码和白色图框；正文卡是“图框 + caption + 页码”，不再用满幅黑底截图。
- **阅读页复用导出卡**：`reader.html` 顶部按顺序纵向列出已经渲染好的 3:4 PNG（最大 420px），不做横向滑动；用户可以直接保存/上传。
- 图片数量、构图和水印/字幕属于 skill/素材层，不在渲染器里按单篇修；渲染器只保证已有图片完整、可读、尺寸适配。
