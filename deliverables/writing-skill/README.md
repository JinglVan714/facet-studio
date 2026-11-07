# 写作作品

> **2026-11-06 历史标记**：这是旧 articles-only 作品集，**不是当前产品**。当前产品是聊天式内容工作台（[docs/product-v1-chat-studio.md](../../docs/product-v1-chat-studio.md)）；当前写作引擎/产物见 [docs/writing-v5-architecture.md](../../docs/writing-v5-architecture.md) 和 `runs/writing_v5/`。旧 PDF 中文文本层问题已知，不要当 current 排版方案。

三篇文章的阅读版：一篇教程，一篇技术解释，一篇关于猫的名字的文化随笔。

- 打开：[site/index.html](site/index.html)
- PDF：[site/writing-articles.pdf](site/writing-articles.pdf)
- 打印源：[site/print.html](site/print.html)
- 单篇 Markdown：[articles/](articles/)

作品集只呈现文章与配图。重建：

```bash
python build_site.py --pdf
```

PDF 由 Edge headless 打印；中文视觉完整，文本层可能不可搜索。
