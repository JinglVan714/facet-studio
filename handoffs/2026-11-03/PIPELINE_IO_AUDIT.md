# Pipeline I/O & Prompt Audit（2026-11-03）

> **历史审计，已废弃，不要读。** 它描述的是旧 brief/verifier/repair 管线；当前写作层是 `writing_v4`，入口是 [NEXT_SESSION_PROMPT.md](NEXT_SESSION_PROMPT.md)。

> 目的：在实现 1–5 项之前，先拆每个 stage 的输入/输出、prompt 体积与冗余、架构重复，给出目标 pipeline 和 A/B 计划。
> 数据来源：三篇 dev run 的 `prompts/*.txt`、`llm_calls.jsonl`、`manifest.json`；本地参考 skill；一次 VLM 能力探测。
> 约束：不改代码、不 commit；测量只用于设计，不写死预算/门槛。

---

## 0. 结论先行

1. **最大的 prompt 冗余不是 writer，而是 brief + visual 的 frame captions。** BV1AC 的 brief 输入里 `source_map.frames` 约 7.3k tokens，visual planner 输入里 frames 约 7.5k tokens；这些是整屏 OCR（代码/UI/官方公告），而 `evidence_text` 里已经有同样的 frame marker。两项加起来约 15k tokens/篇，接近一次 verifier 的成本。
2. **brief system 是规则密度最高的 prompt。** 8.9k chars / 3.5k tokens，70 个 bullet、44 个规则词；`planning.md` 已经承载方法，`BRIEF_INSTRUCTION` 又重复了一遍。应改成“输出 schema + 少量硬规则 + 2–3 个例子”，把 title/claim status 用例子锚定。
3. **writer 的 brief payload 有 0.4–0.6k 可删字段**：`reader`（request 已有）、`payoff`（core/throughline 已有）、`challenge`（planner 自用）、`evidence_status`（ledger 已有）、非 chosen 的 title 候选。删掉后 writer 更聚焦，不改变事实。
4. **两个 verifier + 一个 pre-polish repair 是架构冗余。** initial verifier 在 polish/visual 之前；final verifier 在交付稿上只读。真正该修的是交付稿。目标：一次 final verifier（含 VLM 视觉）+ 一次 bounded repair，删掉 initial verifier 的独立 semantic gate。
5. **polish 目前值得保留，但要放在 final repair 之前。** 三篇 polish 都改善了 voice/boundary/claim scope（例如 BV17 的 boundary、BV1yb 的“是否适用于别人”），没有证据表明它整体有害；保留它，让 final verifier+repair 兜底，而不是把它当第二个 semantic 修复。
6. **VLM 图片输入可用。** 一次带图 probe 返回了图像里的具体文字（控制台编码乱码，但内容与帧一致）；无图对照返回“未提供图片”。说明 API 接受 `image_url`；还需一次干净的 caption-vs-image probe（工具分类器临时超时，待重试）。
7. **本地开源参考已经足够，不需要再引入新框架。** `avoid-ai-writing` 的 detect/edit 分离、source fidelity、protected content、two-pass ceiling；`wewrite-review` 的“review 必须直接改，最多两轮”；`wewrite-visual` 的“检查实际文件”；`wewrite` 的 context budget 脚本。`great-writer` 的 6-phase 太重，不抄。

---

## 1. 每 stage 的输入/输出/成本

| stage | 类型 | 输入 | 输出 | 观测成本（3 篇） | 主要失败 |
|---|---|---|---|---|---|
| source_map | 确定性 | consume index + edited text | sections/anchors/numbers/frames/provenance/gaps | 0 模型 | channel 截断；title/date/official 未提取；frames 太长 |
| brief | 模型 ×1 | request + reader_profile + source_map + full text（full）/ source_map（mini） | editorial brief + knowledge ledger + source_block | system 3.5k；user 9.1–17.6k；completion 12.5k 左右；total 23.7–32.5k | title 匿名；`第一次`/`治愈系` 等 claim 错；source_block 不合并 |
| writer | 模型 ×1 | request + reader_profile + evidence_text + writing_brief | Markdown | system 7.4k；user 6.5–12.3k；completion 8.6–13.9k | 机制/归属错误；内部矛盾；跟随坏 title |
| validation/contract | 确定性 | article + edited text + pack + sentences + source_map | binding/structure/hygiene/contract | 0 模型 | contract source-gap 太宽；caption 只查存在 |
| initial verifier | 模型 ×1 | article + source_text + source_block/number/concept/mechanism ledger | findings | system 631；user 6.4–12.6k；completion 25–28k | 抓得到，但只驱动 pre-polish repair |
| repair | 模型 ×1（条件） | draft + findings + evidence + brief | repaired Markdown | completion 19–30k | 修得动，但目标不是交付稿 |
| polish | 模型 ×1 | article + source_text + source_block/number/concept/mechanism ledger | polished Markdown | system 313；user 6.4–12.5k；completion 10–22k | 改善 voice/boundary；可能保留/放大语义错 |
| visual planner | 模型 ×1 | article sections + frames + claims/evidence + media policy | visual JSON | system 574；user 3.8–11.6k；completion 2.9–4.8k | 选暗图；caption 过度承诺；table 写结论 |
| renderer | 确定性 | article + visual plan + index + frames | article with images + assets | 0 模型 | readability override 太宽；caption 后缀不区分假设 |
| final verifier | 模型 ×1 | article + source_text + ledgers | findings | system 631；user 6.8–12.6k；completion 9–36k | 抓得到，但只读；32k 曾 invalid（64k 已修） |
| publish | 无 | artifacts | status | — | 无 publish gate；partial 仍渲染 |

**Total（每篇）**：新 workflow 7 calls，约 148k / 200k / 186k tokens（含 repair/verifier）；旧 current 3 calls，约 39k / 79k / 47k。新 workflow 的调用/成本约 2.5–3.9×，但 final status 全部 `partial`。

---

## 2. Prompt 审计

### 2.1 体积与规则密度

| stage | system chars / tok | user chars / tok（3 篇范围） | completion tok（3 篇） | bullet / rule words |
|---|---|---|---|---|
| brief | 8,888 / 3,529 | 20,925–34,690 / 9,108–17,563 | ~12,500 | 70 / 44 |
| writer | 21,163 / 7,392 | 12,517–16,521 / 6,451–12,251 | 8,560–13,885 | 61 / 92 |
| verifier | 2,334 / 631 | 11,286–15,617 / 6,379–12,478 | 25,285–27,748 | 18 / 11 |
| polish | 1,168 / 313 | 11,338–15,665 / 6,420–12,539 | 10,169–21,794 | 5 / 7 |
| visual | 2,101 / 574 | 6,256–22,140 / 3,761–11,614 | 2,892–4,846 | 10 / 13 |
| final verifier | 2,334 / 631 | 11,988–15,844 / 6,782–12,632 | 9,042–36,524 | 18 / 11 |

Note：`rule words` 是“必须/不要/不得/禁止/只能/务必/Do not/must/never/only”等词的粗略计数，不是质量指标；只用来找“规则怪谈”密度。

### 2.2 具体冗余

**A. brief / visual 的 frame captions（最大）**

- BV1AC brief user 17,563 tok；其中 `source_map.frames` 7,324 tok（22 帧的整屏 OCR，包括官方公告、代码、UI）。
- BV1AC visual user 11,614 tok；其中 `frames` 7,535 tok（同一批 caption）。
- BV17 brief frames 1,648 tok；BV1yb 1,343 tok。长视频/密集 UI 的 BV1AC 是极端值，但这是结构问题，不是个例。
- 同一信息在 `evidence_text` 的 frame marker 里已经出现；brief/visual 不需要完整 OCR 才能做编辑/选图。
- **处理**：给 brief/visual 的 frame caption 加确定性 cap（例如 240 chars），记录 `caption_truncated`/`caption_full_chars`；完整 caption 留在 source_map/audit 供回查。不是静默截断。
- 预期收益：BV1AC 约 −10k tokens；其他两篇约 −1k。

**B. brief system 规则过密**

- `BRIEF_INSTRUCTION` + `planning.md` 共 8.9k chars；70 bullets、44 规则词；`planning.md` 已经讲了 planning 不是 outline、spine、title、evidence status；`BRIEF_INSTRUCTION` 又重复“don't write H2s / title test / spine 3-5 / anchors / claim type / cut / challenge / knowledge brief…” 
- 规则多并不等于可控；brief 仍然选匿名 title、写“第一次”、把“治愈系”归给于谦。说明需要例子和更少的重复，而不是更多规则。
- **处理**：把 `BRIEF_INSTRUCTION` 压缩成“输出 schema + 8 条硬规则 + 3 个例子”（title good/bad、spine vs topic list、claim status），删掉与 `planning.md` 重复的段落；在 brief 输入里加 `examples.md` 的 title/claim 例子（可以只加 2–3 条，不必整份 examples）。
- 预期收益：system 3.5k → 2.5–3k；title/claim 质量更稳；不增加规则密度。

**C. writer 的 brief payload**

- writer user 6.5–12.3k；其中 writing_brief 3.3–3.8k。可删/降噪：
  - `reader`（request 已有 reader_before/after/profile；brief 的 reader 是重复）
  - `payoff`（core_argument/throughline 已表达）
  - `challenge`（planner 的角度选择理由，writer 不需要）
  - `evidence_status`（concept/mechanism/number ledger 已带 status）
  - `titles` 只保留 chosen；候选 title 对 writer 是噪声（也容易让 writer 混用）
- 保留：shape/core_argument/source_question/throughline/spine/chosen title/stance/cut/concept_ledger/mechanism_chain/number_ledger/source_block/texture_policy/next_step。
- 预期收益：−0.4–0.6k tokens/篇；writer 更聚焦。

**D. writer system**

- 21,163 chars = SKILL.md 17,225 + examples 4,049 + input note/final line。SKILL.md 4.65k tokens，examples 2.78k。
- `References`/`Attribution` 段是给人类维护者的指针，writer 实际不会加载 references（`build_system_prompt` 只拼 body + examples），这两段对模型是噪声；可以从 model prompt 里去掉/移到 manifest/SOURCES。
- Self-review 15 问有重复（title promise/title TOC/first paragraph、facts/numbers/quotes、speaker/claim type、boundary）；可合并成 10–11 问，减少“扫清单”感。
- 不建议大砍 SKILL.md 的方法/证据纪律；writer 的 prose 质量是当前最强的一环，别为了省 0.5k 把纪律砍掉。

**E. verifier / polish 的 ledger 偏差**

- verifier 和 polish 都收到 `concept_ledger` + `mechanism_chain`，它们是 **brief planner 的解释**，不是 source。BV1yb 的“第一次”就在 brief 里；如果 verifier 把 ledger 当 expected，可能降低发现率。
- **处理**：把 ledger 标成 `planner_hint`，并在 prompt 里明确“source_text 优先；ledger 可能错；不要把 ledger 当事实”。或者 verifier 只保留 `source_block` + `number_ledger`，把 concept/mechanism 留给 writer。建议前者（保留覆盖提示，但降权），因为 concept/mechanism 对“文章漏讲机制”的检查有用。
- polish 的 concept/mechanism 对 style pass 不是必需；可以只给 source_block + number_ledger + source_text，减少 brief 错误对 polish 的污染。

**F. visual planner**

- system 574 tokens，规则 10 条；不算过密。user 的 frames 是主要 bloat。
- 需要新增一个结构化 `status`（measured/hypothesis/demo/illustration）给 chart/table；caption 后缀和 verifier 都用它，避免“根据视频数据/视频内容”这种名词替换无法表达假设。
- caption 规则已经有“caption 只描述图里能看到的”；模型仍会违反（BV17 2D caption）。这说明需要**视觉审计**，不是再加一条规则。

### 2.3 过度离散

- brief 的 spine 3–5 moves 是编辑判断，不是 section schema；保持。
- visual 分 table/chart/diagram/frame 是必要的结构；保持。
- 真正的过度离散是 **两个 verifier + 一个 pre-polish repair** 把“检测/修复”拆成三处；以及 brief 的 70 条规则把编辑判断拆成清单。目标是把语义检测/修复合成一个闭环，把 brief 改成“schema + 例子 + 少量硬规则”。

---

## 3. 架构审计：哪些 stage 保留/合并/删除

| stage | 结论 | 理由 |
|---|---|---|
| source_map | 保留，改进 | 确定性、便宜；metadata 提取 + frame cap 是纯收益 |
| brief | 保留，条件化 + 减规则 + 加例子 | 编辑决策/ledger/source_block 有价值；full 对短 case 过重，auto/mini 可省 |
| writer | 保留 | prose 质量最强；只删 brief 冗余字段 |
| validation/contract | 保留 | 技术门；修 source-gap/caption 语义辅助 |
| initial verifier | **删除独立 semantic gate** | 与 final verifier 重复；repair 目标错位；保留只作为可选 pre-check（默认不跑） |
| repair | 保留，移到 final verifier 之后 | 一次 bounded repair；目标交付稿；加 diff guard 防重写 |
| polish | 保留（待 A/B） | 三篇都有 voice/boundary 改善；放在 final repair 之前，让 repair 兜底 |
| visual planner/renderer | 保留，减 frames + 加 status/VLM audit | 视觉是文章的一部分；语义审计缺口用 VLM 补 |
| final verifier | 保留，变成唯一 semantic gate + 可驱动 repair | 它已经证明能抓到交付稿的 residual；只读是当前最大浪费 |
| publish | 不新增 stage | 人工 manual acceptance；partial 不自动发布 |

**目标 pipeline（6 calls）**：

```text
source_map（compact metadata + capped frame captions）
  → brief（auto；mini/full；schema + examples + 少量规则）
  → writer（1；compact brief）
  → validation + contract（audit only）
  → polish（1；validate；invalid 则丢弃）
  → visual planner + renderer（1；status-aware captions；capped frames）
  → final validation + contract
  → final verifier（1；text + real-frame images via VLM）
  → if blocking: one bounded repair（all findings；preserve visuals/source；diff guard）
  → re-validation/contract → final status
```

- 调用数：brief + writer + polish + visual + verifier + repair = **6**（当前 7，且当前 verifier ×2）。
- 预期 token：prompt trims 约 −10–15k；少一次 verifier 约 −15–45k；VLM images 约 +3–10k；净省约 20–50k/篇。
- 如果 A/B 证明 polish 不增值，可再降到 5 calls；先不预设。

---

## 4. 本地开源参考（可复用的方法，不抄 pipeline）

- **avoid-ai-writing（MIT）**：detect vs edit 分离；source fidelity（不新增事实/归属/数量/因果）；protected content（quotes/tables/code/URLs）；最多两次 editing pass（初始 + 一次 corrective），audit 不消耗 pass。→ 支持“一次 verifier + 一次 repair”，repair 只改 findings，保护 quotes/tables/source line。
- **wewrite-review**：review 必须直接修改，不是只给建议；最多两轮；无法核实时删除/缩小/改成推断；只有 `publishable=true` 才算可交付。→ 支持 final verifier 驱动 repair，residual 不能伪装成 pass。
- **wewrite-visual**：检查实际文件（能打开、格式、核心实体可辨、风格连贯）；不覆盖原始正文。→ 支持 VLM/asset 检查；repair 不改原图/资产。
- **wewrite context_budget.py**：静态 prompt load 回归；→ 我们只做测量/报告，不设硬门槛（遵守“不设最小门槛”）。
- **great-writer**：acceptance criteria/red lines 有价值，但 6-phase + 大量词表/规则与我们的“skill-first/不堆规则”冲突；不抄。
- **article-writer ai-detector**：词表/正则打分，正是我们要避免的“规则怪谈”；只作反例。

---

## 5. VLM 能力与视觉审计设计

**已观测**：

- `deepseek-flash` + `image_url`（data URL）调用成功；带图 prompt 的 `prompt_tokens` 约 632，无图对照 42；带图返回了帧内的具体文字（控制台编码乱码，内容与帧一致）；无图对照返回“未提供图片”。
- 说明 API 接受图像内容；还需一次干净的 caption-vs-image probe（工具分类器临时超时）。

**设计**：

- 只在 **final verifier** 加图片，不新增 stage：verifier 收到 article + source_text + metadata + number_ledger + **article 实际使用的 real_frame 图片**（3–6 张，downscale 到 ≤1024px，JPEG q80）。
- verifier prompt 增加 `visual` axis：caption 是否只描述图里看得到的东西；图是否太暗/不可读；图注是否承诺数值/机制；图表是否把假设写成实测。
- 图片以 data URL 传入；`request_identity`/cache key 必须包含图片 hash；`LLMCallRecord` 记录 image hashes/paths，不记录 raw bytes。
- 模型/接口不支持图片时，fallback 到 text-only，记录 `visual_unverified`，不伪称看过图。
- 只发送 real_frame；chart/diagram/table 是文本/结构化 spec，verifier 用 article + chart data 检查，不需要图片。
- 如果 VLM 说某张图不可读/与 caption 不符：repair 只能改 caption 或移除该图（不发明新图）；移除后要保留 assets/audit 记录。若需要换图，另开 visual planner 调用（本轮不做，避免加 stage）。

**Prompt 增量**（verifier system 631 tokens，仍可控）：

```text
visual: if article images are provided, compare each caption with the image.
Report only what is visible. Flag: caption claims a number/mechanism the image
does not show; image too dark/unreadable; caption points to the wrong region.
Do not infer from the caption. If no images are provided, do not invent visual findings.
```

---

## 6. A/B 计划（简单、内部、advisory）

1. **brief auto/mini vs full（BV17）**
   - 目的：短 single-argument case 是否需要 full brief；mini 是否能保住 title/core/source line。
   - 指标：final verifier findings、tokens、title/来源行质量；1 case 只作方向，不推广。
2. **polish vs no-polish（BV17 + BV1yb）**
   - 目的：polish 是否值得 20–28k tokens；是否改善 voice/boundary 而不引入新问题。
   - 指标：final verifier findings、内部 style preference（advisory，不冒充 reader test）、diff 大小。
   - 如果 polish 无稳定增益，再考虑删除；本轮先保留。
3. **final verifier text-only vs VLM（BV17 + BV1AC）**
   - 目的：VLM 是否能抓到文本 verifier 抓不到的 caption/图像问题（BV17 2D caption、BV1AC chart/图）。
   - 指标：visual findings 数量/真伪；token 增量；不把 VLM 结论当真人 reader test。

**不跑**：5-persona × 6 篇 judge，直到 pipeline 稳定、pack 用新 runs 重建。

---

## 7. 实现顺序（先低风险，再闭环）

1. **VLM clean probe**（一次调用，确认 caption-vs-image；工具分类器恢复后做）。
2. **source_map metadata + channel fix**（确定性；独立可测）。
3. **prompt/data trims**：frame caption cap（brief/visual）、writer brief payload、brief system 压缩 + examples、polish ledger 降权。
4. **pipeline reorder**：final verifier（含 VLM）+ one bounded repair；删除 initial verifier 的语义 repair；final verifier 无条件运行；diff guard。
5. **visual status/caption/readability**：planner `status` 字段；renderer 后缀；dark frame 短 caption 拒收。
6. **contract source-gap**：去掉“搜索” blanket marker；逐字段披露。
7. **tests + 3 dev runs + A/B**；然后重建 judge v5 pack。

**验收（与 diagnostic memo §6 一致）**：三篇无 critical/high；material medium ≤1/篇；无新 binding/contract failure；成本不高于当前；repair 不删图/不改 source line/不重写 thesis；3 个 dev case 覆盖三种 genre。

---

## 8. 实现后回填（2026-11-03）

### 8.1 VLM 能力

- 带图 probe 返回了帧内实际文字；无图对照返回“未提供图片”。
- 关键 probe：BV17 的 2D 聚类帧 + 问题“图中是否显示跨模态分数被整体压低？”→ VLM 回答“图中**未显示**该数值现象”。说明 VLM 可用于 caption-vs-image 审计。
- 已接入 final verifier：只发送 article 实际引用的 real_frame（3–6 张，≤1024px，JPEG q80），chart/diagram 仍用文本 spec。

### 8.2 已实现的改动

| 改动 | 结果 |
|---|---|
| source_map channel | BV1AC 从 `的编程宇宙` 修正为 `轩辕的编程宇宙`；BV17/BV1yb 正确 |
| source_map title/date/official hints | BV1AC 提取到标题、`2026-05-15`、官方公告 hint；标记 `frame_ocr/unverified` |
| frame caption cap | brief/visual 的整屏 OCR 截到 240 chars，记录 `caption_truncated`/`caption_full_chars` |
| brief 压缩 + examples | BRIEF_INSTRUCTION 从重复规则改为 schema + 少量硬规则；planning.md 加 title/spine/claim/speaker 例子 |
| writer brief payload | 去掉 challenge/evidence_status/非 chosen title；保留 core/spine/ledger/source |
| polish ledger | 去掉 concept/mechanism，只保留 source_block/number_ledger；加“不得计算新数字” |
| pipeline | 删除 initial verifier；final verifier（VLM）+ one bounded repair；post-repair read-only audit；repair diff guard + caption restore + post-audit comparison |
| contract | source-gap 不再把“搜索”当披露；增加“source line 必须含 request video id”检查 |
| verifier | 增加 speaker attribution、video_ids、visual axis；ledger 标注 planner hint |
| visual | planner 增加 `status`；renderer 的 caption 后缀区分假设/示意/单次演示；dark frame 短 caption 拒收 |
| title check | 匿名/绝对词 advisory；能识别 source_map 里的嘉宾名（菜菜子） |

### 8.3 Prompt 体积（新 runs）

| stage | BV17 v7 | BV1AC v14 | 对比旧 run |
|---|---:|---:|---|
| brief system/user | 3,954 / 7,153 | 3,954 / 14,179 | BV1AC user 17,563 → 14,179（−3.4k） |
| writer system/user | 7,520 / 6,263 | 7,520 / 9,161 | writer system +128（speaker example） |
| visual system/user | 745 / 3,824 | 745 / 7,146 | BV1AC user 11,614 → 7,146（−4.5k） |
| verifier system/user | 938 / 7,237 | 938 / 10,624 | system +307（speaker/visual/video id） |
| polish system/user | 313 / 5,643 | 313 / 8,872 | BV1AC user 10,131 → 8,872 |

### 8.4 实际结果（实现后）

| run | 状态 | 调用 | tokens | pre-repair findings | post-repair findings |
|---|---|---:|---:|---|---|
| BV17 v7 | partial | 7 | 137,564 | 3 medium + 1 low | 1 medium + 2 low |
| BV1AC v14 | partial | 7 | 146,399 | 1 material medium + 3 low | 1 material medium + 4 low |
| BV1yb v3 | pending | — | — | — | — |

- BV17：VLM 抓到“图注指向错半边”，repair 以 3.8% 改动修正；post-audit 剩 1 medium + 2 low。
- BV1AC：video id 检查触发 repair；caption restore 阻止了 v12 的 visual high 漂移；post-audit 剩 1 material medium（claim_scope “界面几乎一样”）+ 4 low；source line 现在含 `BV1ACbi6DEvC`。
- BV1AC v13 曾在没有 video id 检查时 status complete，但 source line 丢了 BV id；v14 修复后 partial（1 medium）。这说明“complete”不等于“source line 完整”，需要 contract 检查。

### 8.5 仍待处理

- BV1yb v3 的 post-audit（speaker attribution high 是否被修复）。
- polish 在 BV17 v7 因新增 `0.02` 被 binding 丢弃；已加“不得计算新数字”，待下一轮确认。
- post-repair audit 成本 17–25k；是否只在 pre-repair 有 critical/high 或 material medium ≥2 时运行，待数据决定。
- judge v5 pack 仍是旧 runs；等 3 个 dev case 稳定后重建。
