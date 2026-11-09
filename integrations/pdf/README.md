# PDF / Tectonic (P2)

> 用途：深度总结（`long_article`）的最终交付物。Markdown → Pandoc → LaTeX → Tectonic PDF。
> 模板是通用中文文章版式，不绑定某个视频/主题。

## 依赖

| 工具 | 用途 | 默认路径 / 环境变量 |
| --- | --- | --- |
| Pandoc | Markdown → LaTeX body | `pandoc`（PATH），可用 `FACET_STUDIO_PANDOC` 覆盖 |
| Tectonic | LaTeX → PDF（自动拉取宏包） | `tectonic`（PATH），可用 `FACET_STUDIO_TECTONIC` 覆盖 |
| pypdf (Python, BSD-3-Clause) | 读取 PDF 页数做结构校验 | `requirements.txt` |

首次编译需要网络下载 ctex/tcolorbox 等宏包；之后走 Tectonic 缓存。

## 产物

`typeset_article(run_id)` 在 `long_article/` 生成：

```text
article.tex        完整 LaTeX（含封面/目录/正文）
article.pdf        最终 PDF
_pdf_body.md       Pandoc 输入（调试用）
_pdf_body.tex      Pandoc 输出（调试用）
```

返回 `pdf.pdf_path`、`pdf.pdf_url`、`pdf.pages`。`pages` 用 BSD-3-Clause 的 `pypdf` 读取，仅作结构校验；中文可搜索性由人工打开 PDF 检查（字体由 ctex/fandol 嵌入）。

## 模板

`facet-template.tex`：ctex + tcolorbox + longtable，占位符：

```text
@@TITLE@@  @@DATE@@  @@SOURCE@@  @@COVER@@  @@BODY@@
```

版式是通用文章：封面、目录、正文分节、图表、页脚。改模板只动版式，不改写作内容。

## 版式约束

- **正文图不溢出**：模板用 `\setkeys{Gin}{width=\linewidth,height=0.62\textheight,keepaspectratio}`，Pandoc 生成的 `\includegraphics` 自动缩进正文版心并保持比例；不再按原始像素铺满页面。
- **正文首行缩进**：`\parindent=2em` + `indentfirst`，章节标题后的第一段也缩进，避免正文顶格。
- **来源只出现一次**：来源行在封面 `@@SOURCE@@`；`_export_pdf` 从正文 Markdown 里剥掉末尾来源行和尾部分隔线，避免生成只有两行字的孤儿页。
- 页码从正文开始保留；封面单独使用 `titlepage`。
- 代码块：Pandoc 使用 `--listings`，由模板里的 `listings` 样式渲染，避免 `Shaded` 环境缺失导致 PDF 导出失败。
- 图片裁切/水印/字幕属于 skill/素材层，不在模板里按单篇修；模板只负责适配大小和页面网格。

## 边界

- 只对 `long_article` 出 PDF；公众号出复制用 HTML，小红书出图片 + 文本。
- 图片路径相对 `form_dir`，Pandoc 用 `--resource-path=.` 解析。
- 缺 Pandoc/Tectonic/模板时返回 `error`，不阻断 Markdown/预览。
- 不按单篇调字号/页数；标题来自产物 `# `，不额外编造。
