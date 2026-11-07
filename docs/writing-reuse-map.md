# Writing Reuse Map（完整设计 v1.0 + EditorialBrief 增补）

> **2026-11-05 session 2**：已由 [writing-v5-architecture.md](writing-v5-architecture.md) 取代；本文件是历史复用决策，不是当前契约。
> **2026-11-06**：当前复用栈见 [reuse-stack-2026-11.md](reuse-stack-2026-11.md)；本文件只作历史。

> **2026-11-03 历史状态**：这是早期复用决策笔记，不是当前实现契约。当前写作架构以 [writing-v5-architecture.md](writing-v5-architecture.md) 为准；本文件只作复用历史/参考。
>
> 状态：实现层复用决策；不是架构基线。日期：2026-11-01（2026-11-02 增补 brief）。
> 当前：`skills/writing/reader_first_explainer/` v1.1 已按本图复用 MIT 方法 + bilibili 教学结构；视觉层（table/SVG chart/SVG diagram/real frame）+ repair pass 已接进 pipeline；EditorialBrief 契约见 `docs/writing-planner-position.md`；3 个 dev brief complete runs（`runs/_brief_final3/`；BV17/BV1AC/BV1yb complete；legacy `runs/_final/` 保留对照）；`evidence_access/consume_index.py` 已复用 `light_context` 帧 helper + `writer_view` 分组逻辑；`writing/{request,context,skill,prompt,writer,validate,pipeline,cli}` + `media/{planner,render}` 已落；487 tests。
> 原则：**先查现成实现/方法；能复用就复用；不能复用才写；不搬整条不兼容 pipeline。**
> 上位：[docs/writing-layer-map.md](writing-layer-map.md)、[docs/writing-layer-contracts.md](writing-layer-contracts.md)、[docs/writing-skill-study.md](writing-skill-study.md)。

---

## 0. 复用判定规则

1. **格式/组件/skill 优先复用**，不照搬整条 pipeline。
2. **License 先审**：MIT/Apache 可复用（保留声明）；CC BY-NC 只借思路；无 license 只借方法/结构，不逐字复制。
3. **语义兼容才复用**：与 evidence-first / reader-audit 分离冲突的中间摘要链不搬。
4. **不重复造抽象**：已有函数/库能覆盖的，不新写同名模块；新写必须在 PR/文档里说明“为什么现成的不够”。
5. **复用不是依赖**：外部 skill/库只通过 manifest/adapter 进入，不把框架类型带进领域对象。

---

## 1. 按层复用

| 层 | 复用来源 | 怎么用 | 不做什么 |
|---|---|---|---|
| Skill 格式 | Agent Skills spec / `anthropics/skills` | `SKILL.md` + frontmatter + references/scripts/assets + 渐进披露 | 不自定义一套 skill 格式 |
| Skill 方法 | `great-writer`（MIT）、`Norman`（MIT）、`bilibili-render-pdf`（方法）、`rednote`（MIT）、`avoid-ai-writing`（MIT） | 读者立场/核心张力/结构先行；evidence map；教学 flow；examples voice；写检分离；preservation | 不复制 NC/无 license 文本；不搬 6-phase/5 角色/平台词表 |
| Claim/evidence | 我们的 substrate v1 + `wewrite` claim 字段 + `Norman` evidence map + `zenstory` index | claim id/text/status/scope/evidence；slot/blueprint；单一 index/coverage | 不做无 quote/span 的 claim；不把摘要当 quote |
| Index/parts | `src/facet_studio/writing_v3/writer_view.py` / `pack_from_claims.py`（历史，只借逻辑） | 复用 index/part 分组、oversize 保留、coverage 思路；输出新 `consume-index-v1` | 不把历史 writer view 当产品 path；不保留旧 schema |
| 证据读取 | `light_context.py` / `edited_transcript.py` / `bind_article.py` / `quote_hygiene.py`（substrate v1） | 直接复用；writing 层只适配/包装 | 不重写 substrate；不改 frozen 接口 |
| Harness | `src/facet_studio/writing_v3/trace.py` + `runtime/{artifact,tools,task_plan,decision,memory}.py` | `TraceRecorder` 收据；RunStore 不可变写/哈希；ToolSpec/Registry；TaskPlan；DecisionRecord；SemanticMemoryRef | 不新写大而全 Scheduler/Memory |
| LLM/cache/budget | `providers/llm.py` 的 `DeepSeekLLM`/`CachedLLM`；`runtime/budget.py`；`core/hashing.py`；`core/tokens.py` | 直接用；已有 prompt hash/raw/usage/latency/缓存/预算 | 不新写 provider/cache |
| Schema | Pydantic 2（已装） | contracts 用 Pydantic model 或 dict+schema；已有 evidence/runtime 用 Pydantic | 不新写序列化框架 |
| CLI/tests | argparse + pytest（项目惯例） | 新 CLI 用 argparse；测试用 pytest | 不引入新 CLI/测试框架 |
| 媒体渲染 | Mermaid / Graphviz / matplotlib / SVG / TikZ / Excalidraw | 优先 Mermaid（流程/时序/时间线）、Graphviz（DAG/关系）、matplotlib（数字图）、SVG/TikZ（精确标注）；统一 adapter | 不手写一套图表引擎；不为图写专用 pipeline |
| 图像生成 | Gemini / OpenAI GPT Image / SD / FLUX（后置） | 只做 editorial；prompt/model/seed/rights；IPTC/C2PA 记录 | 不用生成图当证据；不自建图像模型 |
| 评测 | `runtime/eval_harness.py`（先看是否适配）+ pytest/golden + 简单 JSON reader test | 固定 case/回归/人工原始数据 | 不自建大而全 eval 平台；不用模型冒充读者 |
| Reader test | 简单 Markdown/JSON 表单 | 5+ 真人、盲读、原始回答、attestation | 不自建问卷平台；不伪造 |

---

## 2. 代码复用清单（具体）

### 2.1 直接复用（substrate v1，已冻结）

- `src/facet_studio/writing_v3/transcript.py`：units → sentences/passages。
- `src/facet_studio/writing_v3/light_context.py`：light context + edited text。
- `src/facet_studio/writing_v3/edited_transcript.py`：text + source_map（full/anchored）。
- `src/facet_studio/writing_v3/bind_article.py`：fact/quote/paragraph/input-scope。
- `src/facet_studio/writing_v3/quote_hygiene.py`：非精确引号去引号。
- `src/facet_studio/writing_v3/trace.py`：stage receipt/trace。

### 2.2 可选/按需复用（claim path）

- `src/facet_studio/writing_v3/claim_extract.py`：claims（supported/bounded/scope/quote）。
- `src/facet_studio/writing_v3/pack_from_claims.py`：pack/selection/provenance。
- `src/facet_studio/writing_v3/writer_view.py`：index/parts/oversize/coverage 思路；**只借逻辑，不把旧 schema 当产品**。

### 2.3 Harness 复用

- `runtime/artifact.py`：RunStore 不可变 artifact/哈希；先验证接口是否适配 writing run。
- `runtime/tools.py`：ToolSpec/Registry/Executor；直接包 substrate 函数。
- `runtime/task_plan.py`：TaskPlan DAG；用其 shape，不新增 scheduler。
- `runtime/decision.py`：DecisionRecord。
- `runtime/memory.py`：SemanticMemoryRef/WorkingMemory；不要伪造 episodic。
- `providers/llm.py`：DeepSeekLLM/CachedLLM；`BudgetState`。
- `core/hashing.py`：semantic_hash/canonical_json。
- `core/tokens.py`：estimate_text_tokens。

### 2.4 参考但不作为产品 path

- `prose_writer_probe.py`：prompt 契约/评估 harness 思路；新 `writer.py` 可复用其 prose contract 常量，但不直接调用其 CLI。
- `generate.py`：技术接线；新 writing CLI 可参考，不继承。
- `one_call_writer.py` / `comprehension_view.py` / `bind_merged_frames.py` / `probe*.py`：历史实验，不接。

### 2.5 明确不复用

- `src/facet_studio/writing_v2/` 整条链、body/validator/gate。
- 旧占位 skill（已删除）。
- 与 evidence-first 冲突的全文注入/多阶段 waterfall/摘要链。

---

## 3. 外部库/工具现状

| 工具 | 状态 | 用法 |
|---|---|---|
| `openai` / `pydantic` / `tiktoken` / `numpy` / `pillow` | 已装 | LLM/schema/token/图处理 |
| `imageio-ffmpeg` | 已装（requirements） | 需要 ffmpeg 时用它定位二进制 |
| Node / npx | 已装 | `npx @mermaid-js/mermaid-cli` 渲染 Mermaid（可能需要下载 Chromium；先验证） |
| Mermaid | 未装 | 先用 `.mmd` 文本 + 可选 npx 渲染；无渲染时明确 `unrendered` |
| Graphviz `dot` | 未装 | 需要时装/用 Mermaid 替代 |
| matplotlib/seaborn | 未装 | 数字图优先用 SVG 手写或装 matplotlib；不默认依赖 |
| TikZ/LaTeX | 未确认 | 讲义/PDF 后置；Markdown 形态不需要 |
| 图像生成 API | 未配置 | 后置；先输出 image prompt |

策略：**先做零新依赖的真实帧/表格/SVG/Mermaid 文本；需要时再加 adapter，不在 P0 装一堆库。**

---

## 4. Skill 内容复用与许可

| 来源 | License | 复用方式 |
|---|---|---|
| `great-writer` | MIT | 读者立场/核心张力/结构先行的方法，重写文本；保留 MIT 声明 |
| `Norman` | MIT | evidence map/slot/blueprint 结构，重写文本 |
| `bilibili-render-pdf` | 本地未见 LICENSE | 只借方法/结构（教学 flow/分段/帧清单），不逐字复制；发布前再确认 |
| `rednote` | MIT | examples voice/写检分离/冷读方法，重写文本 |
| `avoid-ai-writing` | MIT | handoff/preservation/一次 repair 方法，重写文本 |
| `zenstory` | MIT | 单一 index/coverage/atomic publish 方法 |
| `tomoai` | CC BY-NC 4.0 | 只作结构参考，不进入商业交付 |
| `crewAI examples` / `wordflowlab` | 本地未见 LICENSE | 只借方法，不复制代码/文本 |

每个 skill 带 `SOURCES.md`；MIT 保留版权声明；不复制 NC/无 license 文本。

---

## 5. 防造轮子检查

新增模块前问：

1. substrate v1 已有函数能做吗？（`light_context`/`edited_transcript`/`bind_article`/`quote_hygiene`）
2. runtime 已有 harness 能做吗？（`TraceRecorder`/`RunStore`/`ToolRegistry`/`TaskPlan`/`DecisionRecord`）
3. 已装库能做吗？（Pydantic/openai/tiktoken/numpy/PIL）
4. 开源库/ skill 有兼容方法吗？（Mermaid/Graphviz/matplotlib/Norman/wewrite/zenstory）
5. 如果都不够：写最小新模块，并在文档/测试里说明“为什么现成的不够”。

不新增：第二套 schema/序列化、第二套 cache、第二套 trace、第二套图表引擎、第二套 eval 平台、第二套 skill 格式。

---

## 6. 下一步复用动作

1. 新 skill 用 Agent Skills 格式 + MIT 方法，写 `skills/writing/reader_first_explainer/`。
2. `consume-index-v1` 用 `light_context`/`edited_transcript` + `writer_view.py` 的 index/parts 逻辑，不重写分组器。
3. Writer 复用 `prose_writer_probe` 的 prose contract 常量 + `DeepSeekLLM`/`CachedLLM`，新写最小 `writer.py`。
4. Validator 直接调用 `bind_article` + `quote_hygiene`。
5. Harness 用 `TraceRecorder` + `runtime/tools.py` + `runtime/task_plan.py` + `runtime/decision.py`。
6. 媒体先用真实帧/表格/Mermaid 文本/SVG；图渲染 adapter 后置。
7. Eval 先 pytest/golden + 简单读者表单；不自建平台。
