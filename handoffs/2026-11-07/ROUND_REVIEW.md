# 2026-11-07 P2 轮次自检（交接附件）

> 这份文件记录本轮的改动、验证和问题；不是产品基线，也不是方向指令。新 session 先自己核对代码/产出/用户反馈。

## 1. 本轮范围

P2：排版/导出/UI，在 P1 的 LibreChat + MCP 壳内完成原型。

- 品牌统一 Facet Studio。
- 首页引导 + 模型配置提示。
- 工具调用中文化/去噪。
- 公众号复制 HTML。
- 小红书 3:4 横滑图集 + App 导入包。
- 深度总结 Pandoc + Tectonic PDF。
- 文档收口。

## 2. 关键文件

| 文件 | 作用 |
|---|---|
| `src/facet_studio/mcp_server.py` | 8 个 MCP 工具；`_parse_xhs_note`、`_xhs_export`、`_render_wechat`、`_export_pdf`、`_render_xhs` |
| `src/facet_studio/preview_server.py` | 静态预览服务 `127.0.0.1:8765/runs` |
| `integrations/xhs/render_cards.mjs` | Playwright 1080×1440 卡片 |
| `integrations/pdf/facet-template.tex` | ctex/tcolorbox/longtable PDF 模板 |
| `integrations/librechat/patches/client-ui.patch` | 外部 LibreChat clone 的展示层补丁（5 个文件） |
| `integrations/librechat/agent-instructions.md` | Agent 工作流与产物说明 |
| `skills/writing/xiaohongshu-note/SKILL.md` | 小红书 skill；默认标签、首图封面 |
| `tests/writing_v4/test_mcp_server.py` | 新增 XHS 解析/渲染、WeChat 内联、PDF 缺依赖测试 |

## 3. 验证记录

- 全量测试：**564 passed**（`pytest tests -q`）。
- 完整 Agent 流程：`runs/product_v1/20261107T032530Z_BV17DHC6CELr_xiaohongshu_note/`
  - 1,274 字 / 6 图 / 6 张 3:4 PNG / 5 标签 / 2 次模型调用 / 16,208 tokens。
  - 产物：`reader.html`、`xhs_export/01_cover.png…06_card.png`、`title.txt`、`body.txt`、`tags.txt`、`manifest.json`。
- 公众号：`runs/product_v1/20261106T131015Z_BV17DHC6CELr_wechat_article/wechat_article/wechat.html`（复制正文按钮）。
- PDF：`runs/product_v1/smoke_long_pdf/long_article/article.pdf`（9 页；封面/目录/正文人工检查）。
- UI：首页三卡 + 配置提示；工具调用显示“读取视频 / 规划 / 写作 / 排版 / 运行数据”。
- 预览 URL 均返回 200（reader / PDF / WeChat）。

## 4. 本轮修掉的问题

1. **source 行解析**：`## 标签` 之后 source 行被 tags 分支吞掉 → 调整判断顺序。
2. **导出残留**：重 typeset 旧 PNG / 旧 source.txt 残留 → 生成前清理。
3. **无图封面**：无配图时封面文案丢失 → 纯文字封面 slide。
4. **图集首卡裁切**：scroll-snap 吃 padding → `scroll-padding-left:22px`。
5. **AGPL 校验**：PyMuPDF 只用于本地检查 → 改为 BSD `pypdf` 读页数，中文可搜索性人工检查。
6. **单例偏置**：`resolve_source` 的示例 BV、XHS skill 的烹饪例子 → 通用占位。
7. **工具路径**：Pandoc/Tectonic 硬编码 → `FACET_STUDIO_*` + `shutil.which` 回退。
8. **外部补丁不可复现**：导出 `client-ui.patch`。

## 5. 仍存疑/风险

- 小红书标题仍有第一人称亲历/钩子偏弱；用户明确最后改。
- 公众号数字多/缺图表；内容层，未动。
- `_render_xhs` 与 `_parse_xhs_note` 重复解析；未来可能分叉。
- 本地路径/环境依赖；新机器需配置 Pandoc/Tectonic/Playwright/Node。
- Mongo 是内存服务；重启可能丢用户/agent/会话。
- 没有浏览器端自动化 E2E；P2 流程靠手工验证。
- 预览/导出是本机路径；公网部署需改成可下载 URL + 鉴权/限流/成本上限。
- `runs/product_v1/_*.json` 是历史证据，含旧 `lunograph` 工具名，不是当前实现。

## 6. 给新 session 的核对建议

1. 跑全量测试并打开 UI。
2. 用一条**新缓存视频**走一遍按需形态，不要用 bundle。
3. 检查 `client-ui.patch` 在干净 clone 上可应用。
4. 检查 `librechat.yaml.example` 与 `.env.example` 是否还缺 P2 配置。
5. 逐条核对 §5，判断哪些是 bug / 待办 / 用户后置。
6. 给用户 2–3 个方向 + 验收标准，等用户裁决。
