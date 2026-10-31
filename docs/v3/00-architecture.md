# LunoGraph v3 架构书：证据编译器 + 写作 Skill

> 日期：2026-10-31
> 状态：v3 设计基线（仅架构；尚未写代码）
> v2 材料：`docs/_frozen/v2-2026-10-31/`，只作素材，不是基线
> 自检：见 [00-architecture-self-check.md](00-architecture-self-check.md)

---

## 0. 文档定位

本文件是 v3 的唯一架构入口。它回答：

- 视频如何变成可复用的证据；
- 证据如何组织、如何被多种文体复用；
- 写作如何用尽可能少的模型调用完成；
- Skill、Writer、Verifier、确定性校验各自负责什么；
- 多文体（深度解析、讲义、社媒、企业知识、视频脚本、二创、生图提示词）如何共用一套底座；
- JD 能力在新架构中的落点，以及哪些只做“小号”、哪些后置。

v2 已冻结为素材。v2 的 R1–A5/P1 链路、body/validator/gate、具体 prompt 不作为 v3 默认；只有在明确服务于 v3 原则时才选择性采纳。

---

## 1. 产品定义

**一次证据编译，多文体写作。**

输入：

- 一条视频（或一个视频集合）；
- 一个写作请求（读者、目的、平台、输出形态）；
- 一个写作 skill（角色/方法/输出 schema）。

输出（同一证据库可支持多种）：

- reader-first 深度解析；
- 讲义/课程笔记/教程；
- 社媒文章（公众号、知乎、小红书、微博、thread、LinkedIn 等）；
- 企业知识/FAQ/SOP/内部文档；
- 视频创作脚本（hook、分集、分镜、旁白、B-roll）；
- 二创/发散思考/评论；
- 从视频精华生成图像的提示词；
- 以及未来新增的、由 skill 定义的其他文体。

核心差异：

1. **证据可追溯**：每个事实性句子能回到 claim、quote、时间码、帧；citation 由代码派生。
2. **证据可复用**：同一 EvidenceSnapshot 可以被多个 View/Skill 复用，不为每篇文章重新总结视频。
3. **写作连续**：默认一次 Writer 调用看完整证据包并一次写完；不靠多轮“计划→写作→审稿→修订→复查”拼接。
4. **多文体不复制管线**：文体差异放 Skill/View/输出 schema，不放 per-form pipeline/validator/gate。
5. **质量与速度并重**：默认 1 次模型调用；高风险才加 1 次独立 Verifier；其余靠确定性校验 + 真人/A-B。

**操作范围**：v3 P0/P1 先做 `generate`；产品架构里的 `reconstruct / redesign / review` 是后续操作入口，不在当前 P0 承诺内。`review` 的一部分由可选 Verifier + P1 人工门承担，但不要据此认为 v3 已覆盖四操作。

非目标（当前阶段）：

- 不做全量 Scheduler/MCP/四类 Memory/RAG 全栈/LangGraph 深度；
- 不做每个文体一套 body/validator/gate；
- 不自动发布；不判断作者主张的现实真伪；
- 不把生成图/示意图当视频证据；
- 不为 JD 关键词造假。

---

## 2. 成功标准

### 2.1 业务质量

- 读者只读文章能回答 central question、复述机制/流程、说出边界。
- 事实性句子有绑定；quote 精确；时间码/帧可回查。
- 同一证据在不同文体中说法一致，不出现“这篇一个版本、那篇另一个版本”。
- 文章连续、可读、尽量精简；不是 evidence 清单，也不是 plan 的复述。

### 2.2 速度与成本

- 短文章默认 **1 次 Writer 调用**；结构/绑定失败最多 1 次 repair。
- 高风险内容才加 **1 次 Verifier**；发现问题最多 1 次 revise，不 loop。
- P0 实测：BV1AC 11 分钟视频，claim extraction 31k + writer 38k = **69k tokens**、约 226s、reader 1,865 字（一首样本，尚未 reader test/A-B）。目标仍以实际模型/样本测量为准。
- 每个 stage 的 calls/tokens/latency 可查；失败/partial 不静默。

### 2.3 可复用

- 同一视频可生成 ≥2 种文体，且共享 EvidenceSnapshot/claim/evidence ID。
- 新文体不重读全量 ASR、不重做知识聚类；只新建 View + Skill。
- 证据/技能/输出版本化；旧 artifact 可 replay。

### 2.4 质量门

- reader-first/社媒：真实读者 test + A/B（按文体定义）。
- 讲义/企业知识：专家/使用者 review + 事实绑定检查。
- 视频脚本：table read / 视频团队 review + 真实帧引用。
- 二创：人工 review + 证据段/发散段分离。
- 生图提示词：图像检查 + 真实帧/生成图 provenance。
- 所有公开发布：人工 `publish_approved`；不自动发布。

---

## 3. 设计原则

1. **证据优先**：EvidenceSnapshot 是唯一事实底座；Knowledge/View/Skill/Writer 都不是新事实源。
2. **模型写作，代码编译/校验**：Writer 只负责表达；quote/时间码/citation/绑定/结构由代码做。
3. **Skill 优先，不堆规则**：用角色、读者模型、方法、示例、self-review 控制生成；不用词表/规则怪谈。
4. **默认一次生成**：短文章一次 Writer 看完整证据包；中间摘要越少，连续性越好。
5. **可选 Verifier，不 loop**：只有高风险/确定性失败才加一次独立复核；最多一次 revise。
6. **证据单元带上下文**：不把证据拍平成 claim 列表，也不拆成失去上下文的句子碎片。
7. **一次编译，多视图复用**：View 是引用 ID 的投影，不是模型摘要；换文体不重读 ASR。
8. **ASR 为主，帧为证**：内容以 ASR 为主；关键帧在 ASR 关键节点附近挑，不做全片均匀抽帧。
9. **多文体 = 多 Skill/View**：不为每个文体加 pipeline/body/validator/gate。
10. **小号 Harness**：Run/Stage/Attempt、Writer/Verifier 角色、plan header、tool receipts、usage/trace 足够；不追求大而全。
11. **复用开源**：优先复用/二开成熟 skill、写作引擎、视频工具；不兼容证据优先原则的整条 pipeline 不照搬。
12. **失败一等**：partial/unknown/insufficient evidence 明确记录；不包装成成功；不静默降级。
13. **度量驱动**：每一步都要回答“它是否服务于数据/质量/速度”；不服务就删。
14. **容量 advisory**：不做固定 length/focus 硬门；长度/证据量只作预算、截断、审计；质量由 reader/专家/A-B 判断。

---

## 4. 总体架构

### 4.1 分层

```text
接入层        CLI / API / SDK（后置）
编排层        Run / Stage / Attempt / Human Gate（小号）
证据编译层    Source → Temporal → Evidence → Knowledge → Views
写作层        Skill Registry → Writer → optional Verifier → revise
校验渲染层    Bindings / Citations / Audit / Reader render
发布层        Reader test / A-B / 专家 review / 人工 publish
观测层        usage / trace / replay / decisions / eval
```

### 4.2 默认数据流

```text
WritingRequest
  + EvidencePack（来自同一 EvidenceSnapshot 的 View）
  + WritingSkill（角色/方法/示例/输出 schema）
        │
        ▼
Writer（1 次模型）
  → plan header + 全文 + span 级 claim/evidence/quote + self_review
        │
        ▼
确定性校验（binding / quote / ID / 结构 / reader hygiene）
  ├─ 通过 → render reader.md + audit.json + citations.json
  └─ 失败 → 1 次 repair（同一 Skill，带具体错误）
        │
        ▼
可选 Verifier（1 次，风险触发）
  → findings（可定位/可路由）
  → 最多 1 次 revise
        │
        ▼
Reader test / A-B / 专家 review / 人工 publish
```

### 4.3 调用预算

| 场景 | 默认调用 | 说明 |
|---|---|---|
| 普通 reader-first/社媒短文章 | 1 Writer | 确定性校验通过即 render |
| 高风险（数字/因果/医疗/金融/法律） | 1 Writer + 1 Verifier | Verifier 看文章 + EvidencePack，不看 plan 摘要 |
| 结构/绑定失败 | 1 Writer + 1 repair | repair 只修结构/引用，不重新设计文章 |
| Verifier 发现 blocking | +1 revise | revise 后确定性校验 + 人工；不再 recheck loop |
| 长文/多源 | 1 Writer（或分节 Writer）+ 可选 Verifier | 长文分节后置；不先做多阶段瀑布 |

### 4.4 最小 artifact

| Artifact | Producer | Consumers | 说明 |
|---|---|---|---|
| `evidence_snapshot` | 视频证据编译器 | Views/Writer/Verifier/audit | 不可变事实底座 |
| `temporal_outline` | 证据编译器 | Views/Writer | 时间分段/关键节点 |
| `evidence_pack` | View builder（确定性） | Writer/Verifier | 带上下文/预算/截断的证据投影 |
| `writing_skill` | Skill 库 | Writer/Verifier | 角色/方法/示例/输出 schema/版本 |
| `writer_output` | Writer | 校验/渲染/Verifier | plan header + 文章 + spans/bindings + self_review |
| `bindings/citations/audit` | 确定性校验/渲染 | Publish/人工 | 引用/时间码/帧/审核指针 |
| `verifier_report` | 可选 Verifier | revise/人工 | 只读 findings |
| `reader_test`/`ab_test` | 真人采集 | Publish | P1 输入 |
| `publish_review` | 发布门（确定性） | 人工 | 记录签章/风险 |
| `run/usage/trace/decisions` | Harness | 观测/回放 | 小号但真实 |

v3 不保留 v2 的 reader_plan/answerability/selection/context/review/editor/recheck 等默认 artifact；它们是 v2 素材，只有明确需要时才以 v3 的 View/Skill/Verifier 形式重建。

---

## 5. 视频证据编译器

### 5.1 四步编译

```text
Source → Temporal → Evidence → Knowledge（可选）
```

**Source**
- 视频/音频/字幕/关键帧/OCR/VLM 元数据；不可变；记录 SHA/权利/时间基准。
- 外部来源门控；`data/` 只读。

**Temporal（ASR 为主）**
- ASR units：时间码、原文、channel、speaker（如可得）。
- segments/beats：按时间/话题/步骤切成可读单元；带 label、unit_ids、first_ms/last_ms、coverage。
- 关键节点：segment 边界、claim 起止、步骤切换、数字/强调、演示/操作 mention。
- 关键帧候选：在关键节点 ±N 秒/segment 范围内取候选，不做全片均匀抽帧。

**Claim aggregation（一次性，缓存复用）**
- ASR units 先确定性合并成 sentences/passages（按标点、静默、segment），不做逐句 claim。
- 对 passages 做一次 claim extraction：每个 passage 1–3 条写作级 claim；合并碎片；跳过问候/预告/闲聊/赞助/频道 logistics；每条 claim 带 passage 内精确 quote、sentence_ids、time range。
- 目标是一段 10–20 分钟视频约 30–50 条 claim，而不是逐句 100+ 条微 claim；claim 是证据编译产物，不是新事实源。
- claim extraction 只跑一次/视频，结果缓存；不同文体复用同一 claim 集，不重新总结。
- **命名注意**：v3 pack 里的 `claims` 是“写作级聚合 claim”（1–3 句），不是 substrate 的 atomic Claim。substrate 的 atomic Claim + EvidenceClaimLink 仍是底层对象；聚合 claim 必须回指这些原子 claim/evidence，不能成为第二套事实源。未来如重命名，优先用 `claim_groups`/`writing_claims`，但 P0 兼容字段名 `claims`。

**Evidence**
- 从 assertions/claims 规范化出 claim + evidence + link：
  - claim：text/kind/scope/support_status/source_assertion_id/chunk_id；
  - evidence：`raw_content` 精确 quote、locator（时间/帧/unit）、capture_method、rights、context_refs、frame_refs；
  - link：stance（supports/qualifies/contradicts/contextualizes）+ basis。
- 保留 ASR vs screen 的抽取冲突；不静默消除。
- 每个证据带上下文窗口：所在 segment/beat、前后 unit、邻域 claim、关系提示、帧候选。

**Knowledge（可选）**
- entities/claim_clusters/relations/conflicts/gaps；全部回指 claim/evidence。
- 短单视频：确定性按 segment/topic/claim-link 分组，不默认调用模型聚类。
- 长文/多源/复杂知识：一次模型 Knowledge build，缓存；仍然不是新事实源。
- Knowledge 只服务于 View 选择/关系/冲突/gap，不替代证据。

### 5.2 现有数据结构能不能复用

可以。v2 的 substrate 已经提供了 v3 需要的基础：

- `Unit`：ASR 单元（时间码/原文/channel）。
- `Assertion`：时间码断言（unit_ids/anchors/quote/kind/status/frame_refs/frame_offsets_ms）。
- `Claim`：规范化 claim（kind/scope/support_status/source_assertion_id/chunk_id）。
- `EvidenceSpan`：精确 quote + locator（时间/帧/unit）+ capture_method + context_refs + frame_refs + rights。
- `EvidenceClaimLink`：claim-evidence 的 stance/basis。
- `TemporalOutline`：segments + coverage。
- `FramesIndex`：关键帧 + 时间码 + VLM 文本 + strategy。
- `KnowledgeSnapshot`：entities/clusters/relations/conflicts/gaps（可选）。

v3 不需要重建 substrate；需要的是**在写作层保留上下文、按 View 复用**，不要压平成 cluster 列表或 plan 摘要。需要注意：v2 的 L1 assertion 可能是句级/片段级微 claim（BV1AC：656 秒视频 145 条，中位 28 字）；v3 把它们当原始素材，先合并 sentences/passages，再做一次 claim aggregation（目标 30–50 条），而不是直接拿 145 条微 claim 写文章。

### 5.3 证据组织：不要平铺，也不要过度离散

**Contextual Evidence Unit** 是 v3 的最小组织单位：

```text
claim/evidence 本体
+ 所在 segment/beat + label
+ 前后 unit 窗口（上下文）
+ 邻域 claim + relation hints
+ 帧候选（时间码/VLM/OCR）
+ stance / counterevidence / gaps
```

它不是“一句话一个碎片”，也不是“全量 claim 平铺”。目标是让 Writer 看到**有上下文的证据**，能直接理解机制/步骤/例子，而不是从散点重建。

**View** 是按请求/文体对证据的确定性投影：

- `mechanism`：因果链、why evidence、反证、限定；
- `procedure`：步骤、前置、失败模式、check、演示帧；
- `comparison`：对象、维度、baseline、差异、结论；
- `timeline`：时间/章节/beat；
- `highlight`：可引用金句、关键数字、转折点；
- `quote`：逐字引文；
- `frame`：关键帧候选 + 视觉描述；
- `entity/process`：企业知识/流程/FAQ；
- `argument`：深度解析/评论。

View 的规则：

- 只引用 EvidenceSnapshot 的 ID；不新增事实；
- 有预算/截断，截断显式；不静默裁剪；
- 按时间/认知/论证顺序组织，不是 bag of claims；
- **先覆盖 passage/beat，再按 request focus 补**：每个 passage/beat 至少一条 claim，避免 lexical top-k 把一整个模式/步骤挤掉；
- 带 counterevidence/gaps/conflicts；
- 可缓存；同输入同 hash。

### 5.4 证据如何复用

- 同一 `EvidenceSnapshot` → 多个 View → 多个 Skill → 多个文体；证据 ID/quote/timecode/frame 保持一致。
- 新文体只新建 View + Skill，不重读 ASR、不重做 Knowledge。
- 源变化产生新 snapshot；旧 artifact 冻结；replay 指向旧 snapshot。
- 例：同一 BV13 证据可生成：
  - procedural 步骤 view → 教程/讲义；
  - quote/highlight view → 社媒短文；
  - timeline/beat + frame view → 视频脚本；
  - frame/highlight view → 生图提示词；
  - argument view → 二创/评论。

### 5.5 能服务于什么视频

| 类型 | 适配度 | 说明 |
|---|---|---|
| 口播/课程/讲座/教程 | 高 | ASR 内容丰富；temporal/segment 好用 |
| 产品演示/机制/操作 | 高 | ASR + 关键帧/OCR；demo 帧是关键 |
| 访谈/播客/多说话人 | 中高 | 需要 speaker attribution；ASR 为主 |
| 幻灯片/屏幕/代码/UI | 高 | OCR/VLM 补视觉证据；帧在关键节点附近挑 |
| 长视频/课程合集 | 中高 | 需要 segment/beat + 分节写作；不是一次全塞 |
| 纯视觉/影视/表演/音乐 | 低 | ASR 稀疏；需要 visual-first（shot/scene/action/audio），不是本架构默认 |
| 实时直播 | 低 | 后置 |
| 无授权/隐私敏感 | 不进入 | 入口门控 |

### 5.6 和“Skill 直接看 ASR”有什么区别

| | Skill 直接看 ASR | EvidencePack |
|---|---|---|
| 内容 | 全量 ASR 原流 | 相关证据 + 上下文窗口 |
| 引用 | 模型复述，易改写 | 精确 quote/timecode/frame |
| 帧 | 没有/另找 | 关键节点附近候选帧 |
| 复用 | 每个文体重新读/总结 | 同一 ID 多 View 复用 |
| 审计 | 无 binding/citation | bindings/audit/citations |
| 上下文 | 长视频易爆 | 确定性预算 + 显式截断 |
| 一致性 | 多文体容易说法不一 | 同一证据同一事实 |
| 成本 | 预处理低、每次调用上下文大 | 预处理高、每次调用更小 |
| 适用 | 一次性短文案 | 多文体/长视频/需审计 |

**不是二选一**：

- 一次性短社媒文案，可以“直接 ASR + 轻结构”；
- 多文体复用、需要时间码/帧/审计时，用 EvidencePack。
- v3 默认 EvidencePack；如果 request 明确是 one-off、无引用需求，可用轻量 transcript 模式。

---

## 6. 写作 Skill

### 6.1 Skill 的本质

Skill 不是模板，也不是 pipeline 阶段。它是一包**程序性知识**：

- 角色/读者模型：为谁写、读者读前/读后是什么；
- 方法：怎么想、怎么组织、什么算讲清楚；
- 语气/文风：内容为主语，来源归属只在需要时出现；
- 示例：2–3 段好/坏对照，比词表更能控制文风；
- 输出 schema：plan header + 文章 + span 绑定 + self_review；
- 可选脚本：确定性检查/格式化（由代码执行，不进模型上下文）。

Skill 采用渐进披露：

1. 元数据（name/description/forms）常驻，用于选择；
2. 触发后加载 SKILL.md 主体（角色/方法/示例/输出）；
3. 需要时加载 references/examples/scripts；
4. 版本化：id/version/hash；旧版本可 replay。

### 6.2 Skill 包结构

```text
skills/writing/<skill_id>/
  SKILL.md          # 角色、读者、方法、输出 schema、self-review
  examples.md       # 好/坏段落、边界写法、来源归属、结论写法
  references/       # 可选：文体规范、平台规则、领域提示
  scripts/          # 可选：确定性检查/格式化（代码执行）
  manifest.json     # id/version/forms/required_views/quality_rubric
```

### 6.3 Skill 注册表（小号）

```json
{
  "skill_id": "reader_first_explainer",
  "version": "0.1.0",
  "forms": ["deep_analysis", "article"],
  "required_views": ["mechanism", "highlight", "frame"],
  "output_schema": "writer-output-v3",
  "quality_rubric": "reader-first-v1",
  "examples": ["examples.md"],
  "scripts": []
}
```

- 选择方式：request 显式指定 skill；后续可加确定性过滤/可选模型排序。
- 不为每个文体加 pipeline；Skill 只是同一 Writer 的输入。
- Skill 不注入新事实、不绕过 EvidencePack、不改变确定性校验。

### 6.4 Skill 如何解决连续性与“来源归属”

- **角色**：写作者是“为读者解释内容的人”，不是“汇报视频的人”。
- **方法**：一个主问题、一条机制/流程、一个演示、术语首次解释、结论新增综合。
- **示例**：
  - “视频作者认为它适合自动化任务” → “它适合自动化任务；脚本出错会打回重改，反而增加调用”。
  - “两个 encoder 内部如何……都还没有确切答案” → “在这组证据里，只能确定同一查询下的排序仍然可用；encoder 内部结构不是这次能回答的”。
  - 长 caption → 一句“看哪里”。
- **Self-review**：Writer 在同一次输出里标出“是否在复述前文/是否在解释来源而不是内容/是否在列 coverage”，供确定性检查和人工 review。
- **一次上下文**：Writer 看 EvidencePack + 读者合同，不需要一边满足 plan ledger、一边向 review 解释；来源归属自然减少。

### 6.5 多文体 Skill 矩阵

| 文体 | 主要 View | Skill 输出 | 质量门 |
|---|---|---|---|
| 深度解析 | mechanism/argument/highlight | reader-first 文章 | reader test/A-B |
| 讲义/notes/教程 | procedure/timeline/frame | 结构化讲义/步骤/示例 | reader test/专家 |
| 社媒 | highlight/quote/timeline | 帖子/线程/短文 | reader/A-B per platform |
| 企业知识 | entity/process/argument | 文档/FAQ/SOP | 专家 review |
| 视频脚本 | timeline/beat/frame | hook/分镜/旁白/B-roll | table read/video review |
| 二创/发散 | argument/highlight/quote | 评论/创意稿 | 人工 review |
| 生图提示词 | frame/highlight | prompt JSON/Markdown | 图像检查/权利 |

每个 Skill 自带 rubric；不为每个文体写 validator/gate。通用校验只做 binding/quote/ID/结构/reader hygiene。

---

## 7. Writer（默认一次调用）

### 7.1 输入

- `WritingRequest`：central question、job to be done、读者 before/after、平台、输出形态、required/forbidden。
- `EvidencePack`：Contextual Evidence Units + gaps/conflicts + frames + budget/truncation。
- `WritingSkill`：角色/方法/示例/输出 schema/self-review。
- `OutputContract`（最小）：format、language、citation display、media policy；length 只作 advisory。

Writer 看不到：

- 其他 run 的文章/reader/review；
- 全量 ASR（只看到 EvidencePack）；
- 内部 ID 作为读者文本；
- 人工笔记（除非 request 显式提供）。

### 7.2 输出

```json
{
  "plan_header": {
    "title": "...",
    "controlling_idea": "...",
    "reader_path": ["..."],
    "sections": [{"section_id": "...", "role": "...", "goal": "..."}],
    "mechanism_or_steps": [{"step_id": "...", "why": "..."}],
    "demo_choice": {"representation": "real_frame|text_experiment|no_demo", "frame_id": "..."}
  },
  "sections": [
    {
      "section_id": "...",
      "heading": "...",
      "paragraphs": [
        {
          "spans": [
            {
              "text": "...",
              "role": "grounded|editorial",
              "claim_ids": ["..."],
              "evidence_ids": ["..."],
              "quote": "...|null",
              "scope_note": "..."
            }
          ]
        }
      ]
    }
  ],
  "media_choices": [{"frame_id": "...", "section_id": "...", "caption": "看哪里"}],
  "self_review": {
    "risks": ["..."],
    "uncertain_claims": ["..."],
    "coverage_gaps": ["..."]
  }
}
```

- `plan_header` 是审计/计划 artifact，不是单独模型调用。
- grounded span 必须有 claim/evidence；`quote` 是 audit binding（必须是 bound evidence 的精确子串），正文可以改写、不要求逐字出现；只有正文直接引用时才要求与 quote 一致。数字必须在 bound evidence；editorial 不带绑定。
- 读者文本无内部 ID/citation/时间码/审计语言；来源归属自然，不按词表。
- 结论做 synthesis，不逐节 recap；boundary 只在影响读者判断/行动时写。
- 长度 advisory：能讲清楚就尽量精简；不填 min/target。

### 7.3 生成与修复

- 第一次 Writer 调用；结构/绑定/quote 失败 → 1 次 repair（同一 Skill，带具体错误）。
- 第二次仍失败 → `writer_failed`，保留 raw，不进入 render。
- Provider outcome unknown 原样传播，不自动重放。
- 不 loop、不按单条 finding 反复修。

### 7.4 失败状态

| 状态 | 含义 |
|---|---|
| `validation_error` | 输入/证据包不可 replay/provenance 不一致 |
| `writer_failed` | 两次仍不合法（结构/绑定/quote/长度 unit） |
| `evidence_insufficient` | EvidencePack 缺少回答 central question 的必要证据；Writer 只能写 boundary |
| `provider_outcome_unknown` | 可能已调用但结果未知；不自动重放 |
| `complete` | 结构/绑定通过；不是 reader pass |

---

## 8. Verifier（可选）

### 8.1 触发条件

默认不跑。只在以下情况跑一次：

- 高风险内容：数字、因果、医疗、金融、法律、强结论；
- 确定性检查发现未绑定/多义/quote 可疑的 grounded span；
- Writer `self_review` 标记 uncertain/coverage gap；
- 发布前抽样/高风险文体（企业知识、讲义、严肃评论）；
- reader test/A-B 之前需要独立事实复核。

### 8.2 输入/输出

- 输入：文章 + EvidencePack（**不看 plan 摘要**）+ 检查清单（支持/过度外推/范围/来源归属/连续性）。
- 输出：可定位 findings（axis/target/severity/observation/impact/action）。
- 只读；不改文章；不生成替代段落；不判断作者主张现实真伪。

### 8.3 修复

- 有 blocking/major → 最多 1 次 revise（同一 Writer Skill，带 findings + 原文 + EvidencePack）。
- revise 后确定性校验；不再 recheck loop；仍不解决交人工。
- minor 可以记录为 known risk，不强制修。
- Verifier 的 independent perspective 是它的价值；不要让它复用 Writer 的 plan/self-review 作为前提。

### 8.4 何时不用

- 普通 reader-first/社媒短文章，确定性绑定通过，Writer self_review 无高风险；
- 真人 reader test/A-B + 人工 publish 已经是更强的质量门；
- 加 Verifier 只在它能降低事实风险/发布风险时；不为“流程完整”而跑。

---

## 9. 确定性校验与渲染

### 9.1 校验

- 每个 grounded span 有 claim/evidence；ID 在 EvidencePack；claim-evidence 闭合。
- quote 是 evidence `raw_content` 的精确连续子串；它是 audit binding，不要求逐字出现在 span text 中；只有正文直接引用时才要求与 span text 一致。
- grounded span 的 ASCII 数字必须出现在 bound evidence；不新增专名/说话人。
- editorial span 不带 claim/evidence/quote；只能做组织/限定/综合。
- 结构：section/heading/paragraph/span 非空；plan_header 与 sections 一致。
- reader hygiene：无内部 ID/citation/时间码/证据审计语言。
- media：real_frame 只来自固定 snapshot；caption 只写“看哪里”；生成图 editorial。
- 失败：`binding_failed` / `render_error`；不产出成功 artifact。

### 9.2 渲染

- `reader.md`：单 H1、H2、段落、图片；无 citation/时间码/内部 ID。
- `audit.json`：span→claim/evidence/quote/timecode/frame/capture/rights；gaps/conflicts；review/verifier 指针。
- `citations.json`：代码从 bindings/evidence 派生；同 evidence 合并。
- assets：固定 snapshot 的帧；sha/rights；缺失 → partial，不伪造。
- 同输入同 hash；可 replay。

### 9.3 复用 v2 代码

v2 的 binding/render/audit/citation 代码可以作为素材选择性复用；但 v3 的输入是 EvidencePack + WriterOutput，不是 v2 的 plan/context/draft 链。复用时加适配层，不把 v2 的 pipeline 类型带进 v3。

---

## 10. 质量门

### 10.1 按文体

| 文体 | 主要质量门 | 说明 |
|---|---|---|
| reader-first/深度解析 | 真实读者 test + A/B | 同视频同 request，baseline 固定；读者能回答/复述/边界 |
| 社媒 | reader test/A-B per platform | 平台 voice/长度 advisory；不伪造读者 |
| 讲义/notes | reader test + 专家 review | 步骤/公式/代码/时间码准确 |
| 企业知识 | 专家/使用者 review | 事实/权限/来源；可回查 |
| 视频脚本 | table read/video review | 真实帧引用；分镜可执行 |
| 二创 | 人工 review | 证据段/发散段分离；不伪造事实 |
| 生图提示词 | 图像检查/权利 | 真帧 vs 生成图 provenance |

### 10.2 通用规则

- 技术门（binding/quote/ID/render）不等于 reader pass。
- findings=0 / Verifier complete / Writer complete 都不是发布通过。
- 真人数据必须 attestation；模型/模拟盲读只能 advisory。
- 人工 `publish_approved` 是唯一发布门；不自动发布。
- A/B 阈值按文体定义；不为所有文体套同一把尺。
- 失败/partial/unknown 不静默；成本/延迟可查。

---

## 11. 多文体产出

### 11.1 深度解析 / reader-first 文章

- View：mechanism/argument/highlight/frame。
- 输出：一个主问题、一条机制/论证、一个演示、术语首次解释、结论 synthesis。
- 质量：读者能复述机制、说出边界；A/B 严格优于 baseline。
- 约束：不写 coverage 清单；不逐节 recap；来源归属自然。

### 11.2 讲义 / 课程笔记 / 教程

- View：procedure/timeline/frame（含公式/代码抽取）。
- 输出：章节、步骤、前置、失败模式/check、示例、练习（可选）。
- 质量：读者能按步骤执行/复述；专家检查公式/代码/时间码。
- 约束：帧只作演示；时间码/来源进 audit；步骤顺序按依赖。

### 11.3 社媒文章

- View：highlight/quote/timeline。
- 输出：hook、1–3 个核心点、例子、结尾判断；公众号/知乎/小红书/微博/thread/LinkedIn 各一个 Skill。
- 质量：reader test/A-B per platform；平台长度/格式 advisory。
- 约束：不把长文硬切成 thread；不同平台不同 skill，不复制粘贴。

### 11.4 企业知识 / FAQ / SOP

- View：entity/process/argument + 多源。
- 输出：文档/FAQ/SOP/流程；引用/权限/来源。
- 质量：专家/使用者 review；事实绑定；可回查。
- 约束：多源冲突显式；不把模型知识当公司事实。

### 11.5 视频创作脚本

- View：timeline/beat/frame/highlight。
- 输出：hook、分集/分段、分镜、旁白、B-roll、字幕/字卡建议；帧引用。
- 质量：table read/video review；分镜可执行；真实帧/生成图分开。
- 约束：不伪造画面；生成图只 editorial。

### 11.6 二创 / 发散思考

- View：argument/highlight/quote + creative brief。
- 输出：评论、创意稿、改写、续写、角色/世界观发散（如适用）。
- 质量：人工 review；证据段与发散段分离；发散标注为 editorial。
- 约束：不把发散写成视频事实；不伪造引语/画面。

### 11.7 生图提示词

- View：frame/highlight。
- 输出：图像 prompt（主体/构图/风格/光线/负面提示）、可选的帧引用/风格参考。
- 质量：图像检查；权利/来源；真实帧 vs 生成图 provenance。
- 约束：生成图不作为视频证据；prompt 不伪造视频中不存在的关键内容。

### 11.8 新文体接入

- 先写 Skill + 一个案例；至少 2 个案例/结构复现才进通用层。
- 不新增 body/validator/gate；通用校验复用；文体 rubric 放 Skill/评测。
- 新文体需要新 View 时，先证明现有 View 不够用；View 也是复用单位。

---

## 12. 关键帧与视觉

### 12.1 ASR 定节点，帧在节点附近挑

1. **关键节点**：segment 边界、claim 起止、步骤切换、数字/强调、演示/操作 mention。
2. **候选窗口**：节点 ±N 秒或 segment 范围内；N 由 method/request 配置，core 不写死。
3. **候选排序**：OCR/VLM 与 claim 的相关性、幻灯片/屏幕/代码/UI、清晰度、与相邻帧去重。
4. **写作选择**：`real_frame` 只在候选帧确实展示该 operation/result/claim 时用；否则 `text_experiment`/`no_demo`。
5. **生图/二创**：从 segment/highlight 选代表帧；VLM 描述 + 风格 prompt；生成图 editorial；权利/来源记录。
6. **VLM/OCR 文本只作选帧依据**，不是事实；`capture_method` 必须记录。

### 12.2 不应该做的

- 全片均匀抽帧、按帧写文章；
- 让 VLM caption 变成事实 claim；
- 用生成图/示意图冒充视频证据；
- 没有匹配帧却写“这段演示”；
- 把 caption 写成正文摘要；caption 只写“看哪里”。

### 12.3 视频类型与视觉策略

- ASR 丰富：ASR 为主，帧为证；关键节点附近挑帧。
- 幻灯片/屏幕/代码：OCR/VLM 辅助；帧在关键节点附近。
- 纯视觉/影视/表演：需要 visual-first；不是本架构默认；如要做，另立 pipeline。
- 多说话人：speaker attribution；帧在发言/演示节点附近。

---

## 13. JD 对应与小号 Harness

### 13.1 JD 映射

| JD 能力 | v3 落点 | 最小证据 | 优先级 |
|---|---|---|---|
| 多 Agent 协作 | Writer + optional Verifier/Editor Skill；共享 EvidencePack | 两个角色、同一证据包、run/attempt；不是聊天式多 Agent | P0 |
| 任务规划/调度 | Writer plan_header + verifier 触发；小 DAG | plan_header artifact + stage 记录；不做全量 Scheduler | P0 |
| 工具调用/MCP | ASR/帧/OCR/VLM/EvidencePack/生图/render | ToolSpec/Registry/receipt 最小实现；白名单/超时/失败不静默 | P0/P1 |
| 记忆 | EvidenceSnapshot/KnowledgeSnapshot = 语义记忆；Skill 库 = 程序性记忆 | 证据不进聊天记忆；同一快照多文体复用 | P0 |
| 决策/Trace/Budget | skill 选择、verifier 触发、模型/用量 | DecisionRecord + usage + trace + replay | P0 |
| 评测/质量 | per-skill 回归 + reader test/A-B + binding | 固定案例/回放/回归；judge advisory | P0 |
| Prompt/Context Engineering | Skill + EvidencePack + Request | skill/pack hash、输出 schema；核心能力 | P0 |
| Agent 框架/RAG | View 检索；可选 LangGraph adapter | 先做视图/检索 hook；领域对象不依赖框架 | P2 |
| 工程/成本/观测 | 1 Writer 默认；usage/latency | 成本可见；失败/partial 一等 | P0 |
| 作品/开源 | 多文体 + reader artifact + A/B | ≥2 文体、真实 reader artifact、trace replay | P1 |

### 13.2 小号 Harness

- `Run/Stage/Attempt`：writer、optional verifier、render；status/usage。
- `DecisionRecord`：skill 选择、verifier 触发、revision 原因。
- `Tool receipt`：ASR/帧/OCR/VLM/生图/render；真实回执。
- `Trace/Replay`：skill hash、evidence pack hash、prompt/model/usage。
- `Eval`：per-skill 固定案例 + reader/A-B + binding regression。

### 13.3 不追求的

- 全量 Scheduler/并行/取消/checkpoint；
- MCP 生态/工具市场；
- 四类 Memory 深度；
- LangGraph 全栈/RAG 全链路；
- 多租户/权限/平台适配；
- 大而全 JD 覆盖。

原则：JD 能力“有就行”，每个能力有一个小号 artifact + consumer + test；不为关键词造假。

---

## 14. 复用 / 二开开源

### 14.1 原则

1. 优先复用**格式/组件/skill**，不照搬不兼容的整条 pipeline。
2. License/安全/维护状态先审；pin 版本；adapter 边界。
3. Third-party skill 要审计 prompt injection/工具权限。
4. 与 EvidencePack/证据优先冲突的中间摘要链，不搬。
5. 复用代码要有测试/可回退；不把框架类型带进领域对象。

### 14.2 候选

| 方向 | 候选 | 复用方式 | 阶段 |
|---|---|---|---|
| Skill 格式 | Anthropic Agent Skills / `anthropics/skills` | SKILL.md + progressive disclosure + scripts；写自己的写作 skill | P0 |
| 长文规划 | WriteHERE | 递归/图规划思想；长文再借，不做短文章默认 | P2 |
| 研究/长文 | STORM | research→outline→write→polish；多源/长文再借 | P3 |
| 长文/多 Agent | InkOS / OmniWriter | 记忆/角色/长文编排；后置 | P3 |
| 视频 | ffmpeg / faster-whisper / PaddleOCR / Qwen2.5-VL / InternVL | 现有 substrate 工具链；按需替换 | P0 |
| 渲染 | 现有 Markdown/asset render | 选择性复用；v3 适配 WriterOutput | P0 |
| 评测 | reader test/A-B 模板；开源 eval harness 可选 | 固定案例/回放/回归 | P1 |

### 14.3 集成边界

- Skill：只通过 `SkillManifest` + `SKILL.md` 进入 Writer；不直接改 core。
- 视频工具：只通过证据编译器 adapter；输出 Unit/Assertion/Evidence/Frames。
- 长文引擎：只通过 View/Writer adapter；不替换 EvidencePack/校验/渲染。
- Render/Eval：只通过输入/输出 schema；不引入 v2 pipeline 类型。

---

## 15. 最小数据契约

v3 只保留必要 schema；详细字段在实现时定，不先写 18 个合同。

### 15.1 EvidencePack

```json
{
  "schema_version": "evidence-pack-v3",
  "pack_id": "ep3_...",
  "request_id": "req_...",
  "skill_id": "reader_first_explainer",
  "evidence_snapshot_id": "...",
  "temporal_outline_id": "...",
  "view_types": ["mechanism", "highlight", "frame"],
  "units": [
    {
      "unit_id": "u_...",
      "segment_id": "seg_...",
      "t_start_ms": 0,
      "t_end_ms": 0,
      "text": "...",
      "speaker": "...",
      "neighbor_claim_ids": ["..."],
      "frame_candidates": ["f_..."]
    }
  ],
  "claims": [{"claim_id": "c_...", "text": "...", "kind": "...", "scope": {}}],
  "evidence": [
    {
      "evidence_id": "ev_...",
      "claim_ids": ["..."],
      "quote": "...",
      "t_start_ms": 0,
      "t_end_ms": 0,
      "frame_ids": ["..."],
      "capture_method": "asr|ocr|vlm|manual",
      "rights_scope": "..."
    }
  ],
  "gaps": [],
  "conflicts": [],
  "budget": {"max_chars": 0, "max_frames": 0},
  "truncated": false,
  "pack_hash": "..."
}
```

### 15.2 SkillManifest

```json
{
  "schema_version": "writing-skill-v3",
  "skill_id": "reader_first_explainer",
  "version": "0.1.0",
  "forms": ["deep_analysis", "article"],
  "required_views": ["mechanism", "highlight", "frame"],
  "output_schema": "writer-output-v3",
  "quality_rubric": "reader-first-v1",
  "examples": ["examples.md"],
  "scripts": []
}
```

### 15.3 WriterOutput

- plan_header：title/controlling_idea/reader_path/sections/mechanism_or_steps/demo_choice；
- sections/spans：text/role/claim_ids/evidence_ids/quote/scope_note；
- media_choices：frame_id/section_id/caption；
- self_review：risks/uncertain_claims/coverage_gaps；
- status：complete|partial|failed；
- prompt/model/usage/skill hash/evidence pack hash。

### 15.4 Binding / Audit / Citations

- 每个 grounded span 一条 binding：span_ref/claim/evidence/quote/timecode/frame/capture/rights。
- audit：sections/spans/binding/gaps/conflicts/verifier/rights。
- citations：evidence 去重、span_refs、quote/timecode/frame。
- 同输入同 hash；可 replay。

### 15.5 VerifierReport / PublishReview

- VerifierReport：findings（axis/target/severity/observation/impact/action）+ provenance。
- PublishReview：reader/audit/citations hash、reader test/A-B/human review、checklist、known risks、status。
- 不把 v2 的 14 gates/10 risk kinds 直接搬来；v3 按文体定义最小 gate。

---

## 16. 失败 / 观测

### 16.1 失败状态

| 状态 | 含义 |
|---|---|
| `validation_error` | 输入/provenance 不一致；不可 replay |
| `evidence_insufficient` | EvidencePack 缺少回答 central question 的必要证据 |
| `writer_failed` | 两次仍不合法（结构/绑定/quote） |
| `binding_failed` | grounded span 缺 binding/quote/ID 不闭合 |
| `render_error` | 渲染/媒体/reader hygiene 失败 |
| `verifier_failed` | Verifier 输出无效；不当作 supported |
| `partial` | 媒体缺失/证据不足/非 blocking 风险；显式记录 |
| `provider_outcome_unknown` | 可能已调用但结果未知；不自动重放 |

### 16.2 观测

- 每次调用：stage、model、prompt/skill hash、evidence pack hash、tokens、latency、cost。
- 每个关键选择：skill 选择、verifier 触发、revise 原因、human waiver。
- Trace/replay：固定 skill/evidence/prompt/model；旧 artifact 冻结。
- 质量：reader test/A-B/专家 review；binding/quote 通过率；失败/partial 统计。

---

## 17. Roadmap

### P0：设计与 PoC（已完成一次）

- 本架构书 + 自检；
- `reader_first_explainer` SKILL.md；
- transcript merge / claim extraction / EvidencePack / one-call Writer 原型；
- BV1AC 实测：385 units → 116 sentences → 32 passages → 43 claims → 40-claim pack → 1 Writer；total **69k tokens**（claim extraction 31k + writer 38k），reader **1,865 字**，binding/quote/hygiene 校验 complete；
- **未做 reader test/A-B，未跑第二视频**；不能把这次当质量验收。
- 下一步：BV17 第二视频同链路验证 + reader test/轻量 A-B；不按 BV1AC 调参。详见 [03-p0-one-call.md](03-p0-one-call.md)。

### P1：短文体默认

- reader-first/社媒两个 skill；
- 1 Writer + 确定性校验/render；
- 可选 Verifier（高风险）；
- reader test/A-B；
- 2 个视频/2 种知识形态验证。

### P2：多文体

- 讲义/notes、企业知识、视频脚本、二创、生图提示词；
- 每文体 1 skill + 1 rubric + 2 案例；
- 不新增 per-form validator/gate；
- 质量门按文体。

### P3：长文/多源

- 长文分节 Writer；
- 多源 Evidence/Knowledge；
- 可选检索 View；
- WriteHERE/STORM/InkOS 等按需借鉴/二开。

### P4：Harness/接入

- 小号 Scheduler/Tools/Memory/Decision/Trace/Budget；
- CLI/API；
- Eval regression；
- LangGraph adapter 可选；
- Portfolio/开源。

### 停止条件

- 如果 one-call Writer 质量明显低于 v2 approved reader，先加 1 次 Verifier，再考虑分节/分阶段；**不要先恢复 7 次链**。
- 如果某文体需要新 View/新 Skill 才能成立，先做 2 案例；不直接加 pipeline。
- 如果开源项目与证据优先冲突，只借组件/skill，不搬整条链。

---

## 18. 非目标与开放问题

### 18.1 非目标

- 不做全量 Scheduler/MCP/Memory/RAG/LangGraph；
- 不做 per-form body/validator/gate；
- 不自动发布；不判断作者主张现实真伪；
- 不伪造画面/生成图当证据；
- 不为 JD 关键词造假；
- 不把 v2 的 18 合同全部搬进 v3。

### 18.2 开放问题

- Skill prompt 的质量/长度/示例数量：需要 PoC 测量。
- EvidencePack 的上下文窗口/预算：按视频类型/文体调，不写死。
- Verifier 触发阈值：高风险分类/抽样/self_review；先人工判断。
- 长文分节：按 section/beat 分 Writer，还是单 Writer + 更长上下文；后置。
- 多源/多视频：View/Knowledge 的合并与冲突；后置。
- 开源 license/安全/维护：P0 先调研，不直接依赖。
- 质量门：不同文体的 reader/A-B/专家比例；先按文体定义，不套一把尺。

---

## 19. 术语

- **EvidenceSnapshot**：不可变事实底座；units/assertions/claims/evidence/links/frames。
- **TemporalOutline**：时间分段/关键节点。
- **Contextual Evidence Unit**：带 segment/neighbor/frame/stance 的证据单元。
- **View / EvidencePack**：按请求/文体对证据的确定性投影。
- **Skill**：角色/方法/示例/输出 schema/可选脚本的程序性知识包。
- **Writer**：一次生成文章/输出的模型调用。
- **Verifier**：可选独立复核；只看文章+证据，不看 plan 摘要。
- **Binding/Audit/Citations**：确定性引用/回查/审计产物。
- **Plan header**：Writer 同一次输出里的轻量计划，不是单独调用。
- **Small Harness**：Run/Stage/Attempt、Writer/Verifier、usage/trace、tool receipts；不追求大而全。

---

## 20. 一句话总结

v3 把视频编译成**可复用、带上下文的证据**，把写作交给**一次 Skill 驱动的 Writer**，把引用/审计交给**确定性代码**，把多文体交给**View + Skill**，把 JD 交给**小号 Harness**。默认一次调用；高风险才加一次独立 Verifier；不为每个文体、每条 finding、每个视频加规则。
