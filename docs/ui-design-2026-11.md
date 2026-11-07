# UI 设计（2026-11-06）

> 状态：目标设计；**P1 已用 LibreChat + reader 预览跑通（2026-11-06）；P2 已接暖纸主题、中文工具名、首页引导、公众号/小红书/PDF 平台预览（2026-11-07）**。运行面板/完整模型配置 UI 仍待后续。产品定义见 [product-v1-chat-studio.md](product-v1-chat-studio.md)；壳/复用见 [reuse-stack-2026-11.md](reuse-stack-2026-11.md)；架构见 [architecture.md](../architecture.md)。
> 目标：用户用得舒服（chat-first、少表单）、看得舒服（排版后的成品，不是裸 Markdown）、用得放心（run trace/成本/状态可见；评测数据不混进产品）。

## 1. 原则

1. **Chat-first**：首页就是聊天框，不是 dashboard/卡片流/作品集。
2. **Preview-first**：产物默认展示排版后的成品；Markdown 是“可编辑源”，不是默认视图。
3. **Progress in chat**：计划、工具调用、tokens、时延、错误放在聊天里的可折叠执行面板，不跳独立 debug 页。
4. **Reader vs process 分开**：读者页只放成品；执行过程/架构/评测在独立面板或 dev 文档，不混进成品页。
5. **Trust by default**：每次 run 可查来源 hash、内容字数/图数、模型、calls、tokens、时延、成本、错误、验收状态。
6. **复用优先**：LibreChat 做壳；Artifacts/Reasoning/Tool 组件现成；不自己造 chat/streaming/artifact 基础设施。

## 2. 布局

### 桌面

```text
┌ 侧栏 240–280 ─┬ 聊天 420–560 ──────────────┬ 预览 自适应 ────────┐
│ 最近 runs      │ 消息流                     │ Artifact 预览       │
│ 内容库         │ 计划卡                     │ 阅读页/公众号/小红书 │
│ 设置           │ 执行过程（折叠）            │ PDF/卡片            │
│                │ 成品卡 + 操作               │                    │
│                │ 输入框                     │                    │
└────────────────┴────────────────────────────┴────────────────────┘
```

### 移动

- 聊天全屏；预览以 bottom sheet / 全屏页打开。
- 计划卡、执行过程、成品卡都可折叠；不横向滚动。
- 表格在窄屏转卡片或横向滚动容器。

## 3. 聊天消息解剖

```text
[用户]
用 BV17 写一篇公众号，给普通技术读者，2500 字左右，语气克制。

[Agent]
计划卡：
  形态：公众号
  角度：分数为什么低但排名可靠
  读者：普通技术读者；读完能解释“看排名不看门槛”
  长度：约 2500 字；图：fig-01/07/08
  [开始写] [调整]

[执行过程]（默认折叠）
  ✓ 读取内容  4,213 字 / 10 图 / content hash 87705d…
  ✓ 规划      1 次调用 / 3.3k tokens / 17s
  ⟳ 写作      15.4k prompt / 6.6k completion
  ○ 排版
  tokens 24.6k · 时延 40s · 成本（可选）

[成品卡]
  [公众号预览] [打开阅读页] [复制 Markdown] [复制公众号 HTML]
  [下载 PDF] [再来一版] [验收通过]
```

要求：

- 计划卡是护栏，不是 section schema；不超过 6 行。
- 执行过程默认折叠；失败节点强制展开；不显示内部 prompt/密钥。
- 成品卡先给预览，再给操作；不先给 Markdown。
- “再来一版”是新 writer 请求，版本化；不是 editor 改稿。
- “验收通过”写 `publish_review.json`；不自动发布。

## 4. 预览类型

| 形态 | 预览 | 操作 |
|---|---|---|
| 深度总结 | 阅读 HTML：标题/导语/TOC/正文/图注/表格；桌面侧栏 TOC，移动单栏 | 打开全屏、复制 MD、下载 PDF |
| 公众号 | 手机框：标题/账号/日期/正文/图；白底 + 绿色点缀 | 复制公众号 HTML、打开预览 |
| 小红书 | 手机框：3:4 封面卡 + 标题/正文/标签/配图；不伪造点赞/评论 | 下载卡片 PNG、复制文案 |
| PDF | 浏览器内嵌或下载 | 下载 |

- 真实帧优先；没有合适图就不放；不生成假截图。
- 平台预览用中性手机框，不冒充真实 App 截图；不显示伪造互动数据。
- 图片懒加载；caption 说“看哪里 + 说明什么”，不复述正文。

## 5. 视觉系统

### 5.1 读者页 / 成品（暖纸编辑感）

| Token | 值 |
|---|---|
| 页面底色 | `#F4F3EE` |
| 正文 | `#191817` |
| 次级文字 | `#5A554E` |
| Hairline | `#D8D3C8` |
| 强调 | `#C96442`（每屏一次） |
| 标题 | `"Noto Serif SC", "Source Han Serif SC", "Songti SC", SimSun, Georgia, serif` |
| 正文 | `system-ui, "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif` |
| 阅读栏 | 680px；65–72 字符；1.75 行高 |
| 字阶 | 13 / 15 / 17 / 21 / 26 / 32 / 40 / 50 / 62（1.25） |
| 间距 | 8px 基线；section 96px；12 栏 / 24px gutter |
| 形状 | 平面、hairline、无阴影（modal 除外）；卡片 8px 圆角 |

参考：WIRED 的编辑排版、Claude Warm Editorial 的暖纸/衬线/单一强调色。不要紫色渐变、玻璃拟态、霓虹、夸张 hover。

### 5.2 平台预览（公众号 / 小红书）

- 中性手机框；浅色背景；平台色只做小面积点缀。
- 公众号：白底、标题大、正文短段、图全宽；不伪造“阅读原文”链接。
- 小红书：3:4 封面（真实帧）；标题短；正文短段；标签 request 要求才写；不伪造点赞/收藏数。
- 卡片模板可复用开源（MIT）：`ian-xhs-carousel` 或自建简单模板；不嵌入 AGPL 的 guizang，除非合规。

### 5.3 执行过程 / 技术工作台（深色）

| Token | 值 |
|---|---|
| 底色 | `#0B1220` |
| 卡片 | `#111A2B` |
| 正文 | `#E5E7EB` |
| Muted | `#94A3B8` |
| 成功/进行/失败 | `#22C55E` / `#F59E0B` / `#EF4444` |
| 字体 | `"JetBrains Mono", "SFMono-Regular", Consolas, monospace` |

- 运行头：run id、status、elapsed、calls、tokens、cost（可选）。
- 树：stage → tool → artifact；状态符号 + 进度；父节点 rollup。
- 点击节点 → 输入/输出摘要、usage、错误、artifact 链接；不显示密钥/完整 prompt。
- 默认折叠已完成；失败强制展开。

## 6. LibreChat 定制点

| 点 | 做法 |
|---|---|
| 主题 | CSS override（暖纸/深色执行面板）；不改核心逻辑 |
| Artifacts | HTML artifact 输出阅读页/公众号/小红书预览；必要时 fork artifact renderer |
| Reasoning/Tool UI | 用 LibreChat 现成工具调用/推理展示；不够再用 assistant-ui/AI Elements 组件 |
| MCP | `librechat.yaml` 配我们的 MCP server；Agent Builder 启用工具 |
| Token/Trace | 用 LibreChat Token 统计/Trace Viewer；我们的 run 数据作为工具回执 |
| 审批 | 工具审批 + 我们的 `publish_review.json` |

如果 LibreChat 的 artifact 面板不够：只 fork renderer/主题，不 fork 核心 agent 逻辑；或者换 assistant-ui + AI Elements 自建壳。

## 7. 可访问性 / 性能

- alt/caption、键盘焦点、对比度、skip link。
- 390px 移动端实测；表格横向滚动/卡片化。
- `prefers-reduced-motion`；不做重动画。
- 静态资源优先；图片懒加载；不引入大前端框架只为预览。

## 8. 不要做

- 不要把首页做成 dashboard/作品集/架构页。
- 不要把 eval 分数/评分卡放进产品成品页。
- 不要默认展示裸 Markdown。
- 不要伪造平台数据/截图/点赞。
- 不要把执行过程做成独立 debug 页；它是聊天里的折叠面板。
- 不要为了“好看”加渐变/玻璃/霓虹/过度动画。
