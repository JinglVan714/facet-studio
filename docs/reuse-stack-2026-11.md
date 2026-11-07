# 复用栈（2026-11-07）

> 目的：记录已调研的开源复用选择、license 边界、替代方案和集成风险；后续 session 不要重复调研。
> 上位：[architecture.md](../architecture.md)；产品定义见 [product-v1-chat-studio.md](product-v1-chat-studio.md)。
> 原则：能复用就复用；借结构/组件/CLI，不搬不兼容的 pipeline；嵌入代码优先 MIT/BSD/Apache；AGPL/BUSL 只作设计参考，除非用户同意合规。

## 0. 结论

- **产品壳**：LibreChat（MIT）。现成的 chat UI、Agents、MCP、Artifacts、Token 统计、Trace Viewer、Docker。
- **轻量替代**：assistant-ui（MIT）+ Vercel AI Elements（MIT）。如果 LibreChat 的 Docker/MongoDB 太重，用这套自己搭壳。
- **文档画布参考**：Open Canvas（MIT，已归档）。借 chat + artifact editor + 版本历史 + LangGraph 结构，不建议直接作为底座。
- **长文排版（已采用）**：Pandoc + Tectonic（XeTeX 引擎）+ ctex/tcolorbox 模板，产物 `integrations/pdf/facet-template.tex`；比 Typst 更贴近本地已有 `bilibili-render-pdf` 的 `.tex` 结构。备选 Pandoc + XeLaTeX + Eisvogel（BSD-3）。
- **公众号排版（已采用）**：自建 Markdown → 内联样式 HTML + 复制按钮（`_render_wechat`）；`Lifa-su/md2wechat` / `Mapoet/MD2WeChat` 作为后续模板参考。
- **小红书卡片（已采用）**：自建 HTML/CSS + Playwright（`integrations/xhs/render_cards.mjs`），3:4 封面/正文卡；`helloianneo/ian-xhs-carousel` 只作设计参考。
- **编排**：LangGraph（已在 requirements，MIT）。
- **工具协议**：MCP Python SDK。
- **观测**：LibreChat Trace Viewer + Token 统计；可选 Langfuse / OpenTelemetry。
- **评测**：自建 eval harness；可选 LangSmith / Langfuse / DeepEval / RAGAS，先不绑定。

## 1. 产品壳：LibreChat

| 项 | 内容 |
|---|---|
| Repo | [danny-avila/LibreChat](https://github.com/danny-avila/LibreChat) |
| License | MIT |
| 提供 | Chat UI、Agents、MCP servers、Artifacts（React/HTML/Mermaid）、Token 统计、Trace Viewer、Docker/Helm、Admin Panel |
| 集成方式 | 在 `librechat.yaml` 配 `mcpServers`，连我们的 Python MCP 服务；Agent Builder 里启用工具；Artifacts 用 HTML 输出阅读页/公众号/小红书预览 |
| 部署 | Docker Compose；MongoDB 必需；Redis 单实例可选；默认 compose 还带 Meilisearch/RAG API，可裁剪；官方建议 2GB+ RAM |
| 风险 | Node/MongoDB 依赖重；Artifacts 侧栏/自定义 renderer 可能需要 fork；部分 Agent/文件 API 仍是 beta/experimental |
| 复用边界 | 只改主题、artifact renderer、MCP 配置；不要把写作 pipeline 塞进 LibreChat 核心 |
| P1 状态 | 2026-11-06 本地跑通：外部 clone `D:/luno_external/librechat`；配置/启动见 [integrations/librechat/README.md](../integrations/librechat/README.md) |

**为什么选它**：它是“chat + agents + MCP + artifacts + token/trace”最完整的 MIT 产品壳，和我们要的“聊天框里生成/预览/检查”最接近；MCP 是官方支持，不用自己造协议层。

## 2. 轻量替代：assistant-ui + Vercel AI Elements

| 项 | 内容 |
|---|---|
| Repo | [assistant-ui](https://www.assistant-ui.com/components/assistant-ui)（MIT）、[vercel/ai-elements](https://github.com/vercel/ai-elements)（MIT，需核实） |
| 提供 | Reasoning（可折叠思考）、Tool（工具调用状态）、Artifact/WebPreview、ChainOfThought、Plan、Task、Markdown/代码、流式 |
| 集成 | React 组件；assistant-ui 支持 AI SDK / LangGraph / AG-UI 等 runtime；FastAPI 可用 `assistant-stream`/SSE 接 |
| 风险 | 不是完整产品：没有 Agents/MCP/Token 统计/登录/持久化；要自己搭壳和状态 |
| 适合 | 不想背 LibreChat 的 Docker/MongoDB；想要完全自定义视觉 |

## 3. 文档画布参考：Open Canvas

| 项 | 内容 |
|---|---|
| Repo | [langchain-ai/open-canvas](https://github.com/langchain-ai/open-canvas) |
| License | MIT |
| 状态 | 2026-02-26 归档，只读；仍可作为结构参考 |
| 提供 | Chat + artifact editor（BlockNote/CodeMirror）、版本历史、memory/reflection、quick actions、LangGraph agents |
| 依赖 | Next.js、LangGraph CLI、Supabase auth、LangSmith tracing；较重 |
| 用法 | 借“chat + canvas + 版本 + 记忆”的交互和目录结构；不建议直接 fork 作为底座（归档 + 依赖重） |

## 4. 排版/导出

### 4.1 长文 HTML / PDF

| 方案 | License | 说明 |
|---|---|---|
| [Pandoc](https://pandoc.org) | GPL-2.0+ | 作为独立 CLI 调用；不要把二进制打包进闭源分发 |
| [Eisvogel](https://github.com/Wandmalfarbe/pandoc-latex-template) | BSD-3 | Pandoc LaTeX 模板；XeLaTeX + xecjk 支持中文；成熟 |
| [openwhale-labs/md2pdf](https://github.com/openwhale-labs/md2pdf) | 需核实（倾向 MIT） | Pandoc + Typst，CJK 一等公民；新项目（2026-09），轻、快；先 pin 版本 |
| [Typst](https://typst.app) | Apache-2.0（需核实） | 现代排版；中文模板可用；`--pdf-engine=typst` |

建议：先 Pandoc + Typst（快、轻），失败/复杂排版回退 Pandoc + XeLaTeX + Eisvogel。Markdown 是源；HTML/PDF 是成品。

### 4.2 公众号

| 方案 | License | 说明 |
|---|---|---|
| [Lifa-su/md2wechat](https://github.com/Lifa-su/md2wechat) | MIT | 纯前端单文件，4 主题，CSS 内联，一键复制富文本 |
| [Mapoet/MD2WeChat](https://github.com/Mapoet/MD2WeChat) | MIT | Python，多模板、代码高亮、Mermaid、Base64 图片、Playwright 发布 |
| geekjourneyx/md2wechat | BUSL-1.1（Source Available） | 个人/非商业免费；商业托管/SaaS/白标需付费；不要默认嵌入 |
| geekjourneyx/md2wechat-mcp-server | 同上 | 有 MCP server，但 license 不适合默认复用 |

建议：用 MIT 的 Lifa-su 或 Mapoet；不要把 BUSL 版本嵌入产品。

### 4.3 小红书卡片

| 方案 | License | 说明 |
|---|---|---|
| [helloianneo/ian-xhs-carousel](https://github.com/helloianneo/ian-xhs-carousel) | MIT（需核实；项目很新） | 3:4 卡片、模板、HTML → PNG；先 pin 版本 |
| [bozhouDev/xhs-article-to-images](https://github.com/bozhouDev/xhs-article-to-images) | 需核实 | Markdown → 3:4 PNG，8 skins |
| [op7418/guizang-social-card-skill](https://github.com/op7418/guizang-social-card-skill) | AGPL-3.0 | 设计质量高，但 AGPL 网络使用需开源；只作视觉参考，不嵌入，除非同意合规 |
| 自建 | — | HTML/CSS + Playwright；最可控，但工作量更大 |

建议：优先 MIT 的 ian-xhs-carousel；如果项目太新/不稳，自建一个简单 3:4 模板。

## 5. 编排 / 工具 / 观测

| 层 | 选择 | License/状态 | 说明 |
|---|---|---|---|
| 工作流 | [LangGraph](https://github.com/langchain-ai/langgraph) | MIT（需核实） | StateGraph、checkpoint、streaming、interrupt/HITL；已在 requirements |
| 工具协议 | [MCP Python SDK](https://modelcontextprotocol.io) | MIT（需核实） | 暴露 tools/resources/prompts；stdio/HTTP；LibreChat 官方支持 MCP |
| API | FastAPI | MIT | MCP/健康检查/文件服务；不要重复 LibreChat 的 chat API |
| 观测 | LibreChat Trace Viewer + Token 统计 | MIT | 产品内 run 数据；够用 |
| 观测（可选） | Langfuse | MIT core（需核实） | trace/eval/dashboard；自托管较重 |
| 观测（可选） | Phoenix | ELv2 | 开发期 tracing；不是 OSI，谨慎 |
| 评测 | 自建 harness；可选 LangSmith/Langfuse/DeepEval/RAGAS | 各自 license | 先自建，避免绑定；数据集/指标/回归/校准 |

## 6. License 表（默认嵌入规则）

| 项目 | License | 能否嵌入 | 备注 |
|---|---|---|---|
| LibreChat | MIT | 可以 | 保留版权/许可 |
| assistant-ui | MIT | 可以 | 保留版权/许可 |
| Vercel AI Elements | MIT（需核实） | 可以 | 保留版权/许可 |
| Open Canvas | MIT | 可以 | 已归档；自行维护 |
| Pandoc | GPL-2.0+ | 作为 CLI 可以 | 不打包进闭源分发 |
| Eisvogel | BSD-3 | 可以 | 保留版权/许可 |
| md2pdf | 需核实 | 待定 | 先 pin 版本 |
| Lifa-su/md2wechat | MIT | 可以 | 保留版权/许可 |
| Mapoet/MD2WeChat | MIT | 可以 | 保留版权/许可 |
| ian-xhs-carousel | MIT（需核实） | 待定 | 新项目，先审 |
| guizang-social-card | AGPL-3.0 | 默认不嵌入 | 只作设计参考；嵌入需合规 |
| geekjourneyx/md2wechat | BUSL-1.1 | 默认不嵌入 | 商业使用需付费 |
| Open WebUI | 自定义 license | 默认不嵌入 | 有品牌/商业限制 |
| LobeChat | 2026 license 有争议 | 默认不嵌入 | 先核实，不默认 |
| LangGraph | MIT（需核实） | 可以 | 已在 requirements |
| Phoenix | ELv2 | 可选，不嵌入 | 开发期 tracing |

## 7. 集成边界 / 风险

- **LibreChat 只做壳**：MCP 配置、主题、artifact renderer；写作逻辑在 Python 服务。
- **MCP 是产品接口**：工具要有 ToolSpec、超时、幂等、错误语义、权限；不要让 LibreChat 直接读 run 目录。
- **LangGraph 只跑写作工作流**：checkpoint/stream/interrupt；不要为了框架重写领域对象。
- **排版是确定性步骤**：模型只输出 Markdown/结构化字段；HTML/PDF/卡片由模板/渲染器生成。
- **评测先预留**：产品原型稳定后再做；不要把 eval 分数塞进产品 UI。
- **风险**：LibreChat 依赖重；Open Canvas 归档；md2pdf/ian-xhs 很新；License 需逐项核实；Pandoc GPL 分发边界。
- **先 pin 版本**：所有复用项目记录 commit/tag；升级前跑回归。

## 8. 来源

- [LibreChat](https://github.com/danny-avila/LibreChat)
- [LibreChat MCP docs](https://www.librechat.ai/zh/docs/features)
- [LibreChat Artifacts docs](https://www.librechat.ai/docs/configuration/artifacts)
- [assistant-ui](https://www.assistant-ui.com/components/assistant-ui)
- [Vercel AI Elements](https://github.com/vercel/ai-elements)
- [Open Canvas](https://github.com/langchain-ai/open-canvas)
- [Pandoc](https://pandoc.org)
- [Eisvogel](https://github.com/Wandmalfarbe/pandoc-latex-template)
- [md2pdf (Pandoc + Typst CJK)](https://github.com/openwhale-labs/md2pdf)
- [Lifa-su/md2wechat](https://github.com/Lifa-su/md2wechat)
- [Mapoet/MD2WeChat](https://github.com/Mapoet/MD2WeChat)
- [ian-xhs-carousel](https://github.com/helloianneo/ian-xhs-carousel)
- [guizang-social-card](https://github.com/op7418/guizang-social-card-skill)
- [geekjourneyx/md2wechat](https://github.com/geekjourneyx/md2wechat-skill)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [MCP](https://modelcontextprotocol.io)
- [Langfuse agent evaluation](https://github.com/langfuse/langfuse-docs/blob/8ffb78684e3c135320683101531aa714f8c2cd60/content/resources/engineering/ai-agent-evaluation.mdx)
