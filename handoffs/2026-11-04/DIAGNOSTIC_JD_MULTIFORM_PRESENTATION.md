# 诊断：JD × 多文体 × 展示层（2026-11-05）

> 只读诊断：未改代码、未生成文章、未重跑 judge。对象是当前 writing_v4、`deliverables/writing-skill/` 和 `architecture.md` 的机会地图。
> 结论先行：**多文体是主缺口，JD 是伴随证据，展示层是收口。** JD 只补“对核心业务有真实价值”的小 artifact；不为关键词造全量 harness。

---

## 0. 结论先行

1. **产品核心已成立，但只证明了一种文体。** 1 个 skill + 3 篇 CLEAR 文章（官方 30：81.65 / 80.48 / 74.05），证据纪律和第三人称转述基本过关；但 §6.5/§11 的 7 种文体只覆盖“文章/教程”一种，“一次证据编译，多文体写作”没有被交付证明。
2. **JD 覆盖多数是 partial，且不能拿旧 runtime 冒充。** `src/lunograph/runtime/` 有通用的 DecisionRecord / ToolSpec / RunStore / Budget / EvalCase，但 writing_v4 没有接线；`runtime/task_plan.py` 仍是旧 `brief/verifier/repair` 链，`RunStore.create()` 默认写入旧 plan。当前 v4 的确定性测试只有 **16 个**；全 suite 542 = 旧 writing 100 + writing_v2 304 + writing_v3 122 + writing_v4 16。
3. **展示层不是“差一点”，是有硬伤。** PDF 16 页、字体已嵌入，但中文文本层实测不可用：`pdftotext` 抽出 0 个汉字，PyMuPDF 能取到 CJK 码点但内容是乱码。站点无文章 TOC/封面/移动端表格处理，build 依赖硬编码 Edge 路径。
4. **新增文体前必须先清单例。** [content_manuscript.py:68](src/lunograph/writing_v4/content_manuscript.py#L68) 有视频特定替换，[consistency_pass.py:34](src/lunograph/writing_v4/consistency_pass.py#L34) 有“中国猫里”，[svg_pass.py:4](src/lunograph/writing_v4/svg_pass.py#L4) 有具体视频图例；skill README 还有 BV 号 A/B 表。新文体会直接踩这些坑。
5. **推荐顺序**：0.5 天矩阵/裁决 → 4–5 天多文体垂直切片（社媒 + 视频脚本，2 视频 × 2 文体，至少 1 个视频跨文体）→ 1.5–2 天展示层收口；JD 小 artifact（skill manifest / run manifest / tool receipts / per-skill eval）伴随做，约 2–3 天。总计 8–10 天。
6. **诚实不做**：Agent 框架/RAG 全栈、MCP 生态、全量 Scheduler、四类 Memory、多租户；这些对当前核心业务价值低，architecture §13.3 也明确不追求。

---

## 1. 审计范围与方法

- **读**：`NEXT_SESSION_PROMPT.md`、`docs/writing-rebuild-brief.md` §2/§3、`AGENTS.md`、`architecture.md` §0.1/§1/§4.1/§5/§6.5/§11/§12/§13.1/§14、`STATE.md`、`HANDOFF.md`。
- **代码/产物**：`src/lunograph/writing_v4/`、`src/lunograph/runtime/`、`src/lunograph/writing_v3/` 的 substrate 接口、`skills/writing/video-article/`、`deliverables/writing-skill/`、`runs/writing_rebuild_2026-11-04/`、`evals/writing/`。
- **跑过的只读命令**：`pytest -q`（exit 0）、`pytest --collect-only` 分层计数、`pdftotext`/PyMuPDF 检查 PDF、`grep` 单例扫描、文件/测试/目录清单。
- **没做**：没有调用模型、没有改代码/文章、没有重跑 30 judge、没有浏览器截图（当前环境 Edge headless 复现不稳定）。

---

## 2. JD 覆盖 × 产品价值矩阵

### 2.1 矩阵

| §13.1 JD 能力 | 现状 | 真实证据 | 对核心业务的价值 | 缺口 | 最小真实 artifact | 成本 | 建议 |
|---|---|---|---|---|---|---|---|
| 多 Agent 协作 | Partial | [run.py](src/lunograph/writing_v4/run.py)（writer）、[consistency_pass.py](src/lunograph/writing_v4/consistency_pass.py)（review/edit）、[svg_pass.py](src/lunograph/writing_v4/svg_pass.py)（spec）；共享 content.md | **高**：角色分离已经在修一致性；记录角色/尝试能让失败可查 | 没有 run/attempt/role 记录 | v4 run manifest：stage/role/status/model/usage | 0.5–1 天 | 做 |
| 任务规划/调度 | Partial | [pipeline.py](src/lunograph/writing_v4/pipeline.py) 固定 4 段 DAG | **中**：固定 DAG 够用；全量 scheduler 价值低 | 无 v4 task plan；`runtime/task_plan.py` 是旧链 | v4 专用 task plan（skill_load→writer→consistency→svg→checks）或只写 stages；不复用旧 NODE_SPECS | 0.5 天 | 轻量做 |
| 工具调用/MCP | Partial | substrate ASR/OCR/frames（writing_v3）、content compile、SVG render、checks | **高**：工具回执服务证据审计/调试；MCP 生态价值低 | content compile/SVG/checks 没有 receipt；ToolRegistry 未接线 | `tool_calls.jsonl`：工具名、输入/输出 hash、计数、状态；可选注册 ToolRegistry | 0.5–1 天 | 做 receipts；MCP 不做 |
| 记忆 | Partial | substrate v1 冻结（EvidenceSnapshot/KnowledgeSnapshot）、content.md、skill 库 | **高**：核心就是“一次编译，多文体复用” | 同一视频还没有第二种产物，复用未被证明 | 1 个视频 × 2–3 种文体，共享 content.md；记录复用 hash/边际成本 | 含在多文体 | 做 |
| 决策/Trace/Budget | Partial | `response_meta.json`（model/usage/latency/finish_reason）、consistency/svg reports | **高**：replay/调试/成本 | 无 run-level trace、无 decision record、v4 无 budget | run manifest + `decision_records.jsonl` + `llm_calls.jsonl`；可复用 RunStore/DecisionRecord | 1–1.5 天 | 做（小） |
| 评测/质量 | Partial | 16 个 v4 确定性测试；官方 30（3 CLEAR/3 HOLD）；ab_judge；review_v2 | **高**：回归与质量；但不能再跑 30 | 无 per-skill/form EvalCase；v4 未复审；无真人 reader test；`evals/writing/README` 仍是旧 validate/verifier 协议 | 每 skill 1 个 EvalCase + 固定 request + 地板/ rubric 检查 + replay；新文体做小规模单 persona 抽查 | 1–1.5 天 | 做 per-skill eval；reader test 诚实 not_run |
| Prompt/Context Engineering | Partial | SKILL.md + content.md + run prompt；单 skill | **高**：写作质量核心 | 无 skill manifest/version/hash；无 form 差异 | `manifest.json`（id/version/forms/passes/quality rubric/inputs）；run manifest 记 hash | 0.5 天 | 做 |
| Agent 框架/RAG | Missing（by design） | 无 LangGraph/RAG；architecture §13.3 明确后置 | **低**：当前核心不需要 | — | 无；在 JD 矩阵里标“not pursued” | 0 | 不做；不伪造 |
| 工程/成本/观测 | Partial | response_meta；pipeline 只返回 exit code | **中高**：partial/failed 可查、成本可汇总 | 无统一 run manifest、无 partial/unknown 状态、无成本聚合 | 与 trace 合并：status/error/usage 聚合 | 含在 trace | 做 |
| 作品/开源 | Partial | 3 篇文章，1 种文体；HTML/PDF | **高**：面试第一眼 | 只有 1 种文体；无多产物矩阵；无 trace replay 展示 | 2 种新文体 + 统一作品集 + 一页 JD 证据页；开源可选后置 | 多文体 + 展示层 | 做 |

### 2.2 读法（按“对核心业务的价值”排序）

- **A 类，值得做**：多 Agent 记录、记忆复用（多文体）、Trace/Decision、工具回执、per-skill eval、skill manifest、作品集。这些都直接服务写作质量、证据可信、复用、调试或展示。
- **B 类，轻量做**：任务规划只做 v4 的 4–5 段 plan/manifest，不做 scheduler；成本/观测并入 run manifest。
- **C 类，诚实不做**：Agent 框架/RAG、MCP 生态、全量 Scheduler、四类 Memory、多租户。architecture §13.3 已把它们列为“不追求”；在 JD 矩阵里明确写“未覆盖/不追求”，比造一个假 adapter 更可信。

### 2.3 当前 runtime 的真相

- `runtime/` 的 `DecisionRecord`、`ToolSpec`、`ToolCallRecord`、`RunStore`、`BudgetPolicy`、`EvalCase` 是通用对象，**可复用**；但 writing_v4 没有任何引用（`grep` 为 none）。
- `runtime/task_plan.py` 的 `NODE_SPECS` 仍是 `ingest → build_evidence → plan_draft → selection → content_plan → draft → review → repair → local_edit`，与当前 writer-first 链不一致；`RunStore.create()` 会自动写这个旧 plan。**不能把旧 runtime 当 current evidence**；要么给 v4 新建 plan，要么只写 stages，不写 task_plan。
- `writing_v3/trace.py` 的 `TraceRecorder` 已被 substrate（transcript/claim_extract/pack）使用，但 v4 没用；可以复用它的 receipt 形状，不必重写。

---

## 3. 多文体矩阵

### 3.1 逐文体

| 文体 | §11 要求 | 当前 | 需要的输入/View | 可行性 | 最小 case | 质量门 | 成本 | 优先级 |
|---|---|---|---|---|---|---|---|---|
| 深度解析 / reader-first | mechanism/argument/highlight | **已有**（video-article，3 篇） | content.md + figures | 高 | 已完成 | 官方 30/人工 acceptance | — | 已完成 |
| 讲义 / 课程笔记 / 教程 | procedure/timeline/frame | **部分**（教程型文章） | content.md + figures + 可选 segment labels | 高 | 2 篇（EmbeddingGemma/护肤） | 专家/小规模抽查 | 1–1.5 天 | P1 |
| 社媒短文 | highlight/quote/timeline | **无** | content.md（不需要新 view） | 高 | 2 篇（炸鸡/猫） | 平台 rubric + 单 persona 抽查 | 1–1.5 天 | **P0** |
| 企业知识 / FAQ / SOP | entity/process/argument + 多源 | **无** | 需要多源/权限/冲突 | 低（单视频不够） | 暂不做 | 专家 review | 2–3 天 | P3 |
| 视频创作脚本 | timeline/beat/frame | **无** | content.md + figures + segment/beat（light path 的 outline 已有） | 中高 | 2 篇（炸鸡/技术） | table read/抽查 | 1.5–2 天 | **P0/P1** |
| 二创 / 发散 | argument/highlight/quote + creative brief | **无** | content.md + 明确 editorial 标注 | 中 | 1–2 篇 | 人工 review | 1–2 天 | P3 |
| 生图提示词 | frame/highlight | **无** | frames + caption | 高但价值低 | 1 篇 | 图像/权利检查 | 0.5 天 | P3 |

### 3.2 推荐组合

**社媒短文 + 视频脚本**，2 个视频 × 2 个文体 = 4 个新产物；至少 1 个视频同时有 article + social + script，直接证明“同一份 content.md 复用”。

- 社媒：短、平台化、压缩；适合炸鸡/猫这种生活内容；也能给技术内容做“知乎/公众号”变体。先做一个平台（建议小红书或公众号），不要一次做 5 个平台。
- 视频脚本：hook、3–6 个 beat、旁白、分镜/B-roll、帧引用；适合展示“视觉优先”和“多产物”的差异；内容稿里的“图示 N”和图路径可以直接作为分镜参考。
- 求稳可把视频脚本换成**讲义/课程笔记**：更接近现有 article 能力，风险低，但多产物差异弱。若目标是“漂亮的作品集”，视频脚本更强。

### 3.3 关键设计边界

- **仍是一次 writer 调用**：每种文体一个 skill，共用 `run.py` 的 writer 调用；不新增 per-form pipeline。
- **用户 prompt 不能写死“写一篇文章”**：[run.py](src/lunograph/writing_v4/run.py) 的 `USER_TEMPLATE` 是文章专用；新文体需要 skill manifest 提供 `user_prompt` 或通用模板。
- **地板检查要 form-aware**：[article_checks.py](src/lunograph/writing_v4/article_checks.py) 强制 H1 + 来源行 + 文章泄漏词；社媒/脚本不应被同一套规则误伤。不是“每个文体一个 validator”，而是 skill manifest 声明 `checks: article|social|script`，共用检查函数。
- **来源行 form-aware**：[run.py](src/lunograph/writing_v4/run.py) 的 `_ensure_source_line` 只会追加“本文根据 B 站视频…整理”；社媒/脚本需要不同的出处格式，或者由 skill 输出、编辑后补。
- **视频脚本的 timecode 政策**：文章正文禁止时间码；脚本是制作文档，可以用相对 beat/时长，但不伪造帧内容；真实帧 vs editorial 图要分开。这个差异要写进 script skill，不要复用 article 的泄漏词规则。
- **不做企业知识/FAQ/SOP**：当前 substrate 是单视频；多源冲突/权限/引用是另一个问题，硬做会变成假交付。

---

## 4. 展示层审计

### 4.1 现状与严重度

| 项目 | 现状 | 严重度 | 修法 | 成本 |
|---|---|---|---|---|
| PDF 中文文本层 | 16 页；字体 Microsoft YaHei UI/NSimSun 已嵌入；`pdftotext` 0 个汉字；PyMuPDF 取到 CJK 码点但乱码 | **高** | 选一个 CJK-friendly 生成链路并做文本层验证：Edge tagged PDF / ReportLab+TTF / PyMuPDF Story+font archive / LaTeX（本机无 xelatex/pandoc） | 0.5–1 天 |
| PDF 结构 | 无目录/书签/页码；封面有；图表不跨页 | 中 | 加书签/页码/元数据；目录页 | 0.5 天 |
| 站点首页 | 3 张卡；无封面/阅读时长/文体分区 | 中 | 每篇取首帧做封面；按文体分区；多产物矩阵入口 | 0.5 天 |
| 文章页 | 无 TOC/锚点/上一篇下一篇；h2 有但不可跳转 | 中 | 桌面侧栏 TOC + 移动端折叠；锚点 | 0.5 天 |
| 移动端 | 只有 640px 断点；表格没有横向滚动容器；图片全宽 | 中 | 表格 wrapper + overflow-x；390px 实测 | 0.5 天 |
| 字体/排版 | system-ui + Microsoft YaHei/PingFang；760px/17px/1.75 | 低–中 | 可保留；加 type scale、封面、章节序号即可，不必换 webfont | 0.5 天 |
| build 可重复性 | [build_site.py:42](deliverables/writing-skill/build_site.py#L42) 硬编码 Edge 路径；每次 `rmtree(site)`；PDF 失败无 fallback；当前环境 Edge headless 多次 rc 0 但未产出 | **高** | manifest 驱动文章列表；PDF fallback + 产出校验（页数/文本层）；不要静默成功 | 0.5–1 天 |
| 可访问性/SEO | alt=caption；无 table scope/skip link/meta description/OG | 低 | 补 scope、skip link、description/OG | 0.25 天 |
| 多产物展示 | 只有 3 篇文章，没有“同一来源 → 多种产物”的对照 | **高**（与多文体绑定） | 加“同一视频：文章 / 社媒 / 脚本”对照页；不把架构/评分塞进读者页 | 1 天 |

### 4.2 “漂亮”的具体标准

- **阅读页**：标题—导语—正文层次清楚；每篇有封面/首帧；H2 即 TOC；图表有统一边距/caption；移动端表格可横滑；打印不截断。
- **作品集首页**：按文体分区；每张卡有封面、标题、一句价值、阅读时长；支持“同一来源的多种产物”入口。
- **PDF**：中文可搜索/复制；有封面、目录、页码；图表不跨页；字体嵌入；文件名/元数据干净。
- **构建**：`python build_site.py --pdf` 一条命令可重复；失败时明确报错，不静默产出坏 PDF。

---

## 5. 纪律 / 单例审计

### 5.1 具体 finding

| 位置 | 内容 | 影响 | 修法 |
|---|---|---|---|
| [content_manuscript.py:59](src/lunograph/writing_v4/content_manuscript.py#L59) | `食用小苏打.5克` 的 OCR 修复 | 只适用于食谱类；新文体/新视频可能误伤或失效 | 抽成通用 OCR 数字归一化（前导小数点/单位分隔），或按视频配置 |
| [content_manuscript.py:68](src/lunograph/writing_v4/content_manuscript.py#L68) | “我男朋友他是一个大油皮” → “一个油皮、毛孔粗大的案例” | 视频特定；换视频就是死代码 | 移到 per-video `manuscript_config`；通用层只保留“第一人称经验→一个案例”的规则 |
| [content_manuscript.py:65-91](src/lunograph/writing_v4/content_manuscript.py#L65-L91) | `VOICE_REPLACEMENTS` 大表 | 部分是通用口语归一化，部分会过度归一（“你们/咱们”→“你”） | 拆成通用规则 + 可选 per-video override；新文体（社媒）可能需要保留“你们/咱们” |
| [consistency_pass.py:34](src/lunograph/writing_v4/consistency_pass.py#L34) | prompt 里的“中国猫里” | 具体视频 claim 进了通用 prompt | 换成匿名示例（“某个范围里/这个演示里”） |
| [svg_pass.py:4](src/lunograph/writing_v4/svg_pass.py#L4) | 文档字符串里的“毛色叫法 / 地方类群 / CFA 登记” | 具体视频内容进了代码 | 换成匿名示例（“三层分类：A / B / C”） |
| [skills/writing/video-article/README.md:58-60](skills/writing/video-article/README.md#L58-L60) | BV 号 + 主题的 A/B 表 | skill 包里有具体视频；违反“skill 不出现具体视频” | 移到 `runs/` 或内部证据；skill README 只留匿名方法 |
| [skills/writing/video-article/references/examples.md:305](skills/writing/video-article/references/examples.md#L305) | “CFA 登记”的 SVG 例子 | 具体视频 claim | 换成匿名三层分类例子 |
| [run.py:52-76](src/lunograph/writing_v4/run.py#L52-L76) / [article_checks.py:41-44](src/lunograph/writing_v4/article_checks.py#L41-L44) | 来源行/H1 是文章专用 | 社媒/脚本会被误判 | skill manifest 声明 `source_line`/`checks` 策略；共用函数，不复制 validator |
| [pipeline.py:80-110](src/lunograph/writing_v4/pipeline.py#L80-L110) | 总是跑 consistency → SVG → article checks | 新文体被文章后处理绑架 | 按 skill manifest 的 `passes` 路由；仍是一次 writer + 可选后处理 |
| [build_site.py:24-40](deliverables/writing-skill/build_site.py#L24-L40) | 硬编码 3 篇文章 | 加文体要改代码 | 改成 `works.json` 驱动 |

### 5.2 影响与顺序

这些不是“代码风格”问题，而是**多文体的前置条件**：新文体要复用 content.md 和 writer，但当前素材层/后处理层有视频/文章特定的假设。建议在开新文体前花 0.5–1 天做通用化；不要边写新文体边打补丁，否则会把单例带进新 skill。

---

## 6. 质量 / 评测审计

### 6.1 测试与证据

- **全 suite**：542 passed（本次 `pytest -q` exit 0）。
- **分层**：旧 writing 100 + writing_v2 304 + writing_v3 122 + writing_v4 **16**。
- **v4 测试**：[test_article_checks.py](tests/writing_v4/test_article_checks.py) 7、[test_consistency_pass.py](tests/writing_v4/test_consistency_pass.py) 3、[test_svg_pass.py](tests/writing_v4/test_svg_pass.py) 6。没有 pipeline/run/form 的端到端测试（模型调用不可 deterministic，但可以用固定输入 + mock）。
- **官方 30**：3 CLEAR（BV1ix 81.65 / BV17 80.48 / BV1B 74.05）+ 3 HOLD；对象是 v4 之前的候选（官方 30 时间 17:11，content_final_v4 18:52），**当前 v4 未再评审**。这是模型评审，不是真人 pass。
- **旧评测文档**：[evals/writing/README.md](evals/writing/README.md) 仍写 `lunograph.writing.validate` + verifier + brief 协议，和当前 writer-first 链不一致；没有 cases。
- **A/B**：`ab_judge.py` 存在；输入 A/B 3/4 胜；advisory，不是质量门。
- **真人 reader test**：未做；必须标 `not_run`，不能写成 pass。

### 6.2 跨视频质量债（来自官方 30，不是单篇）

官方 30 的共识缺陷在 ≥2 篇复现，属于通用层，不是单篇调参：

1. **证据范围**：单案例/单次演示/个人判断被写成普遍规则（BV13、BV1zn、BV1eUh；BV1ix/BV17/BV1B 轻度）。
2. **核心价值位置**：最强洞察/公式/判断埋在 60%–80%（BV1ix、BV17、BV1B、BV1zn、BV1eUh）。
3. **标题—正文承诺**：6 篇都有不同程度的标题大于正文或口径不一致。
4. **最后一公里**：结尾缺收藏/评论/转发触发或成品落点（BV1ix、BV13、BV1B、BV1zn）。
5. **绝对/比例语言**：v4 抽查仍有“爆汁”（BV1ix）、“小了 3 倍”（BV17）、“95% 质量”无指标（BV17）、分类主张未完全落地（BV1B）。

建议：不重跑 30；从现有官方 30 提取 3–5 条通用模式，写成**匿名例子 + 1–2 个自审问题**（不是词表、不是 per-video 修法），在多文体开写前花 0.5 天做一次 skill hardening。这样新文体继承的是修正后的通用层，而不是把已知问题复制 4 份。

---

## 7. 排序、成本、验收

### 7.1 推荐顺序（8–10 天）

| 阶段 | 内容 | 产出 | 成本 | 依赖 |
|---|---|---|---:|---|
| P0 | 1 页 JD × 文体矩阵 + 选定 2 文体/2 视频 | 本诊断 + 决策 | 0.5 天 | 用户裁决 |
| P0.5 | 单例通用化（content_manuscript/consistency/svg/checks/source line/build） | 通用层干净 | 0.5–1 天 | P0 |
| P1 | 多文体垂直切片：社媒 + 视频脚本；2 视频 × 2 文体；1 个共享视频 | 4 个新产物 + 2 个 skill + form rubric | 4–5 天 | P0.5 |
| P2 | 展示层：多产物作品集、TOC/封面/移动端、PDF 中文文本层、build 校验 | 可展示的 site/PDF | 1.5–2 天 | P1 |
| P3 | JD 伴随证据：skill manifest、run manifest/decisions、tool receipts、per-skill eval、JD 矩阵回填 | 真实 artifact + 测试 | 2–3 天 | P1 并行 |
| **合计** | | | **8–10 天** | |

### 7.2 三个方向对比

| 方向 | 为什么 | 最小下一步 | 验收 | 几个 case | 成本 |
|---|---|---|---|---|---|
| **A 多文体切片（推荐）** | 补核心产品差异；JD 证据自然产生；作品集从 1 种变 3 种 | 选 2 文体/2 视频；各 1 skill + 1 case；再加第 2 case；至少 1 个共享视频 | 4 个新产物过 form rubric + 地板 + 人工 acceptance；同视频跨文体事实一致；无 per-form pipeline；skill 无单例；作品集/PDF 可用 | 2 视频/文体 + 1 共享视频 = 4 个新产物 | 4–5 天 |
| **B JD 审计 + 最小补齐** | JD 要对上，但不能造假；对调试/复用有真实价值 | 1 页矩阵；补 skill manifest + v4 run manifest/decisions + tool receipts + per-skill eval | 10 行有真实指针或“未覆盖”；3–4 个 artifact 由真实 run 产出并有测试；无新质量门 | 3 篇 CLEAR 各 1 run | 2–3 天 |
| **C 展示层先行** | “务必漂亮”；当前 PDF 中文不可搜索是硬伤 | 修 PDF 文本层；加 TOC/封面/移动端；build 校验 | PDF 中文可搜索；移动端无溢出；TOC/封面；一条命令可重复 | 3 篇 + 1 PDF | 1.5–2 天 |

### 7.3 如果只做一件事

- **要马上能拿出手**：先 C（1.5–2 天）——现有 3 篇 + PDF 立刻从“能读”变“能展示”。
- **要项目完整体**：A（4–5 天）——多产物是 architecture 的核心承诺，也是 JD 作品集最强的证据。
- **B 不建议单独做**：它不产生新产物；最好作为 A 的伴随证据，或 A 之前的 0.5 天矩阵。

---

## 8. 需要用户裁决的 4 件事

1. **两个文体**：社媒 + 视频脚本（推荐，差异大、展示强），还是社媒 + 讲义（稳、接近现有能力）？
2. **两个视频**：炸鸡 + EmbeddingGemma（一个教程、一个技术解释，都有 CLEAR 和完整素材），还是加入猫（文化类，三角覆盖更全）？
3. **JD 目标岗位**：AI 应用/Agent 工程、内容工程、还是多模态应用？这决定 JD 矩阵里优先补“多 Agent/规划”还是“评测/内容质量”。
4. **作品集是否放“怎么做出来的”页**：放，能服务 JD 评审；不放，保持 reader-facing 纯净。建议放一个独立 `process.html`，不混进读者首页。

---

## 9. 证据索引

- 架构机会地图：[architecture.md](architecture.md) §6.5（多文体）、§11（多文体产出）、§13.1（JD）、§14（复用）。
- 当前写作层：[pipeline.py](src/lunograph/writing_v4/pipeline.py)、[run.py](src/lunograph/writing_v4/run.py)、[consistency_pass.py](src/lunograph/writing_v4/consistency_pass.py)、[svg_pass.py](src/lunograph/writing_v4/svg_pass.py)、[article_checks.py](src/lunograph/writing_v4/article_checks.py)。
- 当前 skill：[SKILL.md](skills/writing/video-article/SKILL.md)、[README.md](skills/writing/video-article/README.md)、[examples.md](skills/writing/video-article/references/examples.md)。
- 交付：[site/index.html](deliverables/writing-skill/site/index.html)、[writing-articles.pdf](deliverables/writing-skill/site/writing-articles.pdf)、[build_site.py](deliverables/writing-skill/build_site.py)。
- 质量证据：[official_30/SUMMARY.md](runs/writing_rebuild_2026-11-04/official_30/SUMMARY.md)、[review_v2/SUMMARY.md](runs/writing_rebuild_2026-11-04/review_v2/SUMMARY.md)。
- 旧 harness（不能当 current evidence）：[runtime/task_plan.py](src/lunograph/runtime/task_plan.py)、[runtime/artifact.py](src/lunograph/runtime/artifact.py)、[runtime/tools.py](src/lunograph/runtime/tools.py)、[runtime/decision.py](src/lunograph/runtime/decision.py)。
- Substrate 接口：[substrate-v1-freeze.md](docs/substrate-v1-freeze.md)；[light_context.py](src/lunograph/writing_v3/light_context.py)、[edited_transcript.py](src/lunograph/writing_v3/edited_transcript.py)。
- 测试分层：`pytest --collect-only` 计数；`tests/writing_v4/`。
