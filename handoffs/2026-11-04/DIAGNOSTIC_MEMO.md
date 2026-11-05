# Diagnostic Memo — writing 层现状（2026-11-04，新 session 独立诊断）

> **历史诊断，已废弃，不要读。** 它基于旧的 `writing/` brief/verifier/repair 链，不是当前 `writing_v4`；当前入口是 [NEXT_SESSION_PROMPT.md](../2026-11-03/NEXT_SESSION_PROMPT.md)。不要把本文结论当当前基线。

> 性质：诊断，不是方案冻结；**没有改代码、没有加字段/agent/validator、没有 commit、没有跑模型、没有跑 judge/reader test**。
> 方法：按 `NEXT_SESSION_PROMPT.md` 顺序读 AGENTS / operating model / architecture / substrate freeze / HANDOFF / STATE / evals / 两份只读标准 / skill / 代码 / 最新 runs / 旧 judge / 上一轮 memo；跑全量测试；用当前代码离线复算 request hash、skill hash、quote binding、polish validation、repair diff。
> 证据：`runs/_diag/{BV17_workflow_v7,BV1AC_workflow_v14,BV1yb_workflow_v3}` 的 `reader.md`、`brief.json`、`visual/plan.json`、`visual/render.json`、`verifier_final_report.json`、`verifier_final_after_report.json`、`writer/`、`writer_repair/`、`validation.json`、`output/validation.json`；`runs/_brief_final3/`（旧 current）；`runs/_reader_test_2026-11-03/llm_judge/`（旧 judge）。
> 限制：最新 3 个 run **早于当前 skill/code cleanup**（run skill hash `4776af...`，当前 `08ca35...`；run 时间 22:29–22:59，`pipeline.py`/`render.py` 23:07–23:11 仍在改），不是当前代码的最终证据；但本文引用的 **机制在今天的代码里仍然存在**（见每条的 code 行号）。没有真人 reader test；没有当前代码的新 run；没有 judge v5 结果。我的阅读是 developer read，不是读者验收。
> 诊断 scratch（非 run artifact）：`runs/_diag/_tmp_validate_bv1yb.json`、`_tmp_bv1yb_repair.diff`、`_tmp_BV17_repair.diff`、`_tmp_BV1AC_repair.diff`、`_tmp_quote_scope.json`。

---

## 0. 结论先行

1. **内容层没有坏，last-mile 控制环坏了。** 三篇交付的 prose、结构、证据链、边界都在；没有 red line、没有 critical/high；每篇只差 1 个 blocking 的 material medium（BV1AC 另有 1 个非 blocking 的 consistency medium）。真正反复失败的是“检测→修复→验收→交付”这一段：**repair 会删掉合法的引语和归属，会改标题，会把一个 finding 换成另一个 finding；post-audit 只比数量，不比 identity；默认状态在结构上永远是 partial。**
2. **最具体、最可复现的 bug 是 quote binding 的 pack/sentence 作用域。** BV1yb writer 有 29 条引语，22 条 bound、7 条 `unbound_long`；这 7 条全部 `in_input`（在 writer 看到的 edited text 里），其中至少 3 条精确出现在 edited text 但不在任何单条 pack sentence 里（另 2 条是标点归一化变体），`bind_article` 逐句查，所以判 unbound。validation 因此 partial；repair 按“unbound → 去引号改写”处理，最后把 **63 个引号对删到 3 个（正文 0 个）**，同时把于谦从 12 次降到 4 次、把“对话里”从 2 次升到 9 次。**22 条合法引语被牺牲，只为修 7 条 false negative。** 这不是“写作不好”，是 deterministic binding 和 repair 合同一起把文章变平。
3. **repair 没有“最小修改”合同。** `REPAIR_INSTRUCTION`（`src/lunograph/writing/prompt.py:34-68`）只说“只修 listed problems”，但没有任何 protected span 概念；`_repair_diff_guard`（`pipeline.py:186-207`）只查 H2 数量和图片数量，不查 H1/title、不查引语、不查 source line。BV1AC 的 repair 在没有 title finding 的情况下把 H1 从 brief 的问题句改成陈述句（`BV1AC_workflow_v14/writer/article.md:1` vs `output/reader.md:1`；brief 的 chosen title 是“DeepSeek Harness 的四种模式，为什么是四份插件清单？”）。这是可见的 P4 回归，但 final verifier 的 `title_cta` 没抓到。
4. **repair 的验收是 count-based，不是 finding-based。** `pipeline.py:613-627` 只比较 critical/high/material_medium 的数量；BV1AC 修前 4 findings（1 material medium），修后 5 findings（1 material medium），数量不变就 accepted；但修后多了一个新的 medium claim_scope（“差别集中在两处”），还多了一个 source low（“成熟”）。**修好一个 source medium，换来一个新的 claim_scope medium，系统认为“没变差”。**
5. **来源行仍然会错，而且 contract 和 verifier 都不拦。** BV1AC 的 source line 说“标题、发布日期与链接未提供、未核实”（`BV1AC_workflow_v14/output/reader.md:113`），但 brief/source_map 明明有标题 `Agent和Harness到底是什么？一个动画彻底搞懂！` 和日期 `2026-05-15`（frame OCR，未核实；`brief/brief.json:234-263`）。`contract._undisclosed_missing`（`contract.py:47-63`）只检查“missing 字段有没有披露”，不检查“known 字段有没有被说成 missing”；final verifier 也拿到了 source_block，却没抓。BV17 的 source line 为了修一个 finding，把 `EmbeddingGemma 2` 从全文删掉（`BV17_workflow_v7/output/reader.md:97`），现在读者不知道要用什么工具；post-audit 反而来要这个名字。
6. **派生视觉（SVG diagram）没有语义审计，会和正文打架。** BV1yb 的 `diagram_01.svg` 节点写“五周年新装：魔法杖”，正文说“这套设计和五周年的关系并没有被确认”（`reader.md:17`）；`diagram_04.svg` 节点写“真去问恩西马”，正文说“她说去问问他们”（`reader.md:81`、`:107`）。final verifier 对 BV1yb 的 `visual_status` 是 `not_provided`（没有 real frame），`visual_manifest` 虽然在 payload 里，但 prompt 的 visual axis 是“if images are provided”，所以 diagram spec 实际没被检查。同时 BV17 正文说“视频给了一张真实结果做的图”（`reader.md:25`），文章里放的却是派生示意图，真正的 2D 结果帧没进来。
7. **成本/状态/评测完整性是“项目看起来坏了”的直接原因。** 新 workflow 7 calls / 137,564、146,399、211,923 tokens（含 opt-in post-audit）；旧 current（`runs/_brief_final3`，brief+writer+visual，BV1yb 另一次 repair）是 38,586、79,154、64,596。polish 2/3 被丢弃（BV17 18,934、BV1yb 35,456 tokens 白花）；三篇最终都是 `partial`，原因是各剩 1 个 material medium。默认 `verify_after_repair=False` 时，`delivered_verifier_report` 用的是 **pre-repair** report（`pipeline.py:643-647`），所以任何 repair 过的稿子都会被标 `partial` + `repair_not_reaudited`，结构上不可能 `complete`。judge v5 pack 的 new 侧是 v5/v10/v1（`runs/_diag/build_judge_pack_v5.py:29-45`），当前 runs 是 v7/v14/v3；pack 15:46 构建（build script 15:36），当前代码 23:11 还在改；**现在没有任何“当前代码”的 run 或 judge 证据**。
8. **架构判断：不需要大重写，需要重写 last-mile 的控制合同 + 修一个 deterministic binding bug；或者做一次“简化”而不是“大改”。** substrate→edited text→skill writer→deterministic binding→semantic audit 这条主干是成立的；writer 的 prose 是三篇里最强的部分。把整条链推倒重来会丢掉来源行、semantic detector、visual provenance 这些真实收益。要做的是：**让 repair 变成最小、可审计、保护事实/引语/标题的编辑；让 binding 不再把 edited text 里的合法引语判死；让 post-audit 和 status 对“修好了”给出可信的结论。** 如果用户更在意“这周能有可发布稿”，更稳的是 **B：把 verifier 当报告，删掉 polish/repair 的自动 last mile，人来做最后 1 个 medium 的编辑**（见 §6）。

---

## 1. 这个系统现在实际是什么（不是文档说它是什么）

### 1.1 实际数据流（代码事实）

`src/lunograph/writing/pipeline.py` 的实际顺序：

1. `load_request` + `load_skill` + index/edited_text/pack/sentences/source_map（`:273-279`）。
2. `build_working_context`（`:281-284`）：profile 由 request/长度决定；`full_text` 是默认；`sectioned`/`multi_source` 返回 `unsupported_profile`（`context.py:335-353`），但 pipeline **不检查 status**，继续调 writer；`prompt.build_user_prompt` 对 `index_parts` 直接 `raise ValueError`（`prompt.py:172-175`）。这是长视频边界上的硬失败，不是 graceful status。
3. `build_source_map`（`:285-291`）：sections/anchors/numbers/frames/source_metadata/gaps；channel 用“最高频/最长、排除 suffix”的启发式（`source_map.py:31-74`）；title/date/official 从 frame OCR 提取（`:77-161`），全部标 `frame_ocr/unverified`。
4. `_resolve_brief_mode`（`:70-89`）：显式 none/mini/full；`risk_level=high` 或 `audit_level != none` → full；`chars <= 6000 and segments <= 8` → mini；否则 full。mini **不含全文**（`include_full_text=False`，`:295-299`），只给 source_map；full 含全文。
5. `write_brief`（`:300-311`）：模型 1 次；输出 `editorial-brief-v1`（core/spine/titles/stance/cut/challenge + concept/mechanism/number ledger + source_block + texture_policy + next_step）；缺 core/spine/title → `invalid_output`；`title_check` 只查绝对词和标题引语是否在 source_map（`brief.py:301-327`），不查“具体主体+冲突”。
6. `run_writer`（`:313-324`）：模型 1 次；system = SKILL.md + examples + input note + final line（`prompt.py:137-146`）；user = request + reader_profile + evidence_text + writing_brief（`_brief_payload` 只带 shape/reader/core/source_question/payoff/throughline/spine/chosen titles/stance/cut/title_check/concept/mechanism/number/source/texture/next_step；`:71-101`）；输出 Markdown，`self_review` 是空 `{}`（`writer.py:248-266`），没有结构化 claim map。
7. `validate_article`（`:379-385`）：`clean_article`（quote hygiene，基于 **edited text** 去非精确引号）→ `bind_article`（基于 **pack/sentences**）→ `_demote_editorial_latin`（拉丁术语降为 advisory）→ structure/reader hygiene。binding partial → failures `binding`。
8. `audit_contract`（`:386`）：source line 存在、title quote/number 在正文、每张图有 caption、missing 字段有披露、绝对词 advisory；blocking → contract partial。
9. `run_polish`（`:389-426`）：模型 1 次；preserve facts/numbers/quotes/source line；输出重新 validation，**不 complete 就整次丢弃**（`:417-421`）。
10. `plan_visuals`（`:438-452`）：模型 1 次；frames/claims/evidence + article sections + max_assets；narrative/mixed 最多 2 个（`:435-436`）；`status` 是 measured/hypothesis/demo/illustration/unknown；caption “看哪里”。注意 `plan_visuals` 的默认 `max_tokens=16384`（`media/planner.py:368`），与“不设 per-call max_tokens”的纪律不一致；`finish_reason=length` 没有专门状态，JSON 解析失败 → `invalid_output` → 无视觉，但 final status 不因此失败。
11. `render_visual_plan`（`:453-465`）：table/SVG chart/SVG diagram/real frame；real frame 过 `_frame_readability`（`media/render.py:974-1018`），暗帧可以用 caption 长度 override；caption 后缀按 status 写“根据视频中的假设/示意/单次演示/视频内容绘制”（`:1026-1039`）。
12. final validation + contract（`:467-478`）。
13. `run_verifier`（`:485-508`）：模型 1 次；article + source_text + source_block + number_ledger + concept_ledger + mechanism_chain + real frame images + visual_manifest；9 axes；max 12 findings；red_line。`visual_status` 在有 real frame 时 `checked`，否则 `not_provided`（`verifier.py:315-337`）。
14. 如果 validation partial / contract partial / verifier blocking → `run_writer` repair（`:522-581`）：draft + findings + evidence + brief；`REPAIR_INSTRUCTION`；re-validate；`_restore_unrequested_captions`；`_repair_diff_guard`（H2 数量、图片数量）。
15. 如果 `verify_after_repair=True` → 第二次 verifier（post-audit，`:584-633`）；accepted 的条件是 post-audit complete 且 critical/high/material_medium 数量 **不大于** before；否则 rejected（`post_audit_worse`/`post_audit_unverified`）。
16. 默认 `verify_after_repair=False` → 直接 accepted，但 `delivered_verifier_report = verifier_final_report`（pre-repair），所以 `delivered_blocking=True`、final status `partial` + `repair_not_reaudited`（`:643-675`）。
17. `render_bundle`（`:676-684`）：reader.md + assets + binding/citations/audit/validation/manifest。

**实际调用数**：brief + writer + polish + visual + verifier + repair = 6；`--verify-after-repair` +1 = 7。没有 initial verifier；没有第二次 repair；final verifier 不是“只读审计”，它是 **唯一能驱动 repair 的 semantic gate**（`pipeline.py:480-521`）。

### 1.2 实际成本 / 状态（每篇）

| run | calls | tokens | polish | repair | post-audit | final status | final verifier（after） |
|---|---:|---:|---|---|---|---|---|
| BV17_workflow_v7 | 7 | 137,564 | discarded（18,934） | 24,732 | 25,457 | partial | 3 findings：1 medium source + 2 low |
| BV1AC_workflow_v14 | 7 | 146,399 | accepted（19,552） | 24,539 | 16,832 | partial | 5 findings：1 medium consistency + 1 medium claim_scope + 3 low |
| BV1yb_workflow_v3 | 7 | 211,923 | discarded（35,456） | 50,996 | 24,589 | partial | 5 findings：1 medium source + 4 low |
| 旧 current BV17 | 3 | 38,586 | — | — | — | complete（无 semantic verifier） | — |
| 旧 current BV1AC | 3 | 79,154 | — | — | — | complete（无 semantic verifier） | — |
| 旧 current BV1yb | 3+1 | 64,596（不含 repair 47,444） | — | 17,152 | — | complete（无 semantic verifier） | — |

**事实**：三篇最新稿 **没有 red line、没有 critical/high**；三篇 final validation 都是 complete（`output/validation.json`）；三篇 final status 都是 partial，失败原因只有 `verifier`（manifest `failures: ["verifier"]`）。也就是说，**不是技术门失败，而是各剩 1 个 material medium**：BV17 模型名缺失、BV1AC “差别集中在两处”、BV1yb 恩西马写成已完成。

### 1.3 文档 vs 代码/artifacts 的冲突

| 文档说法 | 实际 |
|---|---|
| `STATE.md` / `HANDOFF.md`：526 passed | 复算 **526 passed in 5.74s**；`docs/writing-operating-model.md` §6 仍写 508，是旧快照。 |
| 最新 runs 是 v7/v14/v3 | `skills/writing/reader_first_explainer/STATUS.md:3` 仍指向 v5/v10/v1；skill 的 `STATUS.md` 不是当前快照。 |
| run 是当前代码证据 | run skill hash `4776af...`，当前 `08ca35...`（`load_skill` 复算）；run 22:29–22:59，`pipeline.py`/`render.py` 23:07–23:11 仍在改。**runs 是旧 skill/旧 code 的快照。** |
| request 已冻结（`request_hash` 不得改） | 三个 request 文件里的 `request_hash` 与 `load_request` 复算值 **全部不一致**：BV17 `9bcf8b...` vs `a885db...`；BV1AC `fde81f...` vs `9ab94b...`；BV1yb `29562f...` vs `da48c3...`。`validate_request` 会剥掉并重算（`request.py:127-131`），从不校验文件里存的值；所以“冻结”是名义上的，改了 request 也不会被发现。 |
| judge v5 pack 是当前 pack | new 侧是 `BV17_workflow_v5`、`BV1AC_workflow_v10`、`BV1yb_workflow_v1`（`runs/_diag/build_judge_pack_v5.py:29-45`）；当前 runs 是 v7/v14/v3；pack 15:46 构建（build script 15:36），当前代码 23:11 仍在改。**pack stale，不能跑。** |
| `validation.json` 是交付稿状态 | 根目录 `validation.json` 是 **repair 前**写的（`pipeline.py:474`），repair accepted 后没有重写；`output/validation.json` 是交付稿。BV17 根 `partial`（1 unsupported fact）vs `output` `complete`；BV1yb 根 `partial`（7 unbound quotes）vs `output` `complete`（0 quotes）。同一条 run 里两个 validation 状态不同，读哪个决定你看到什么。 |
| polish 值得保留（上一轮 `PIPELINE_IO_AUDIT.md`） | 最新 3 篇 2/3 被丢弃（BV17 因 `0.02` 新数字；BV1yb 因 6 条 unbound quote）；BV1AC 的 polish 虽然 accepted，但最终稿仍有 5 个 after findings。polish 的净收益没有被证明；成本 18.9k/19.6k/35.5k 是确定的。 |
| “skill/reference 已无 dev case 专名”（`DISCIPLINE_AUDIT.md`） | `source_map.py:36` 的 docstring 仍有 `轩辕的编程宇宙 bilibili`；`brief.py:588` 注释仍有 `e.g. BV1AC`；`cli.py:8-15` 示例仍是 BV17 路径。不是 hardcode，但 cleanup 不彻底。 |

---

## 2. 三篇最新交付实际做到了什么、没做到什么

### 2.1 BV17（`runs/_diag/BV17_workflow_v7/output/reader.md`）

**做到了**

- 标题有具体主体 + 数字 + 冲突：`文字搜照片：0.756 的蝙蝠，为什么能排在第一？`（`:1`）；第一段兑现“0.756 < 0.8”的矛盾（`:3-7`）。
- 数字链完整：0.756、0.8、0.951、0.781、0.921、0.624、0.733–0.718、0.709、256/128；表格 `:41-47`；边界 `:65`。
- 机制链是文章自己的判断，并且标了“本文”：`能比较 ≠ 共用一把绝对刻度`（`:87-89`）；“视频没有讲训练或校准机制”（`:51`）；“这是一次演示的观察”（`:51`）。
- 来源行存在（`:97`）：BV id + 画面水印 channel + 标题/日期/链接 missing + 频道未核实；这是旧 current 没有的净改进。
- 两帧 real frame 可读（`visual/render.json:10-18,32-40`，non_dark 0.204/0.19）；两个 diagram 的 spec 在 plan 里可回查（`visual/plan.json:14-75,95-148`）。
- 确定性 binding 干净：final `output/validation.json` facts 63/63 hard + 1 editorial（coverage 1.0）、quotes 9/9；`contract` complete；526 tests 通过。

**没做到**

- **全文没有出现模型名。** `EmbeddingGemma` 0 次；`Google` 2 次都是“Google 的说法”（`:69`、`:97`）。after-verifier 的 medium source 就是这条（`verifier_final_after_report.json:5-13`）：读者不知道要用哪个模型，末尾“找一批自己的照片，把向量提前算好”没有落点。这不是“视频没说”——source text 第一句就是“今天的主角是Google昨晚刚刚开源的EmbeddingGemmaTwo”（`runs/m1_light/BV17/light_text.txt:6`），brief 的 cut/challenge 也点了名（`brief/brief.json:80,88`）。**writer 选择了省略，repair 又把 source line 里的名字删掉，post-audit 再来要。**
- **H2 “切到 256 维省三倍空间”是数学/方向错误。** 768→256 是降到 1/3，省 2/3；source 说的是“缩小3倍/小了三倍”（`light_text.txt:6,22`），正文 `:69` 又写“从约 3 GB 降到约 1 GB”（正确）。after-verifier 的 low number finding 就是这条（`verifier_final_after_report.json:15-21`）。因为它是 low，不驱动 repair，所以留在交付稿里；H2 是目录，扫读的人会先看到它。
- **正文说“视频给了一张真实结果做的图”（`:25`），文章里放的却是派生 diagram（`:29-31`）。** 真正的 2D 聚类帧没有进文章；读者看到的是“这是对文章描述的示意，不是模型结构图”。这不是伪造，但**证据强度下降了**：old judge 的 P2/P3 是看重“真实结果”的；current visual planner 选了更安全的示意图，却没在正文里改口说“这里用示意图代替”。
- **`:57` 的“排名只要求同一句话内部的候选之间可比”仍是未标“本文推断”的机制句。** after-verifier 的 low mechanism finding 就是这条（`verifier_final_after_report.json:23-29`）；文章下一句已经承认“这种偏移是否对所有候选都一样，视频没有解释”，但上一句仍像在讲原理。low，不驱动 repair。
- **`:3` 的“先看不设门槛的版本”是 repair 痕迹。** 它修了“开头先成功后来零张”的 consistency finding，但把一个具体场景开头换成了流程说明；不算错，但对 P1/P3 是轻微损失。
- **最后一个 diagram 是 section-summary**（`:93-95`），把第 6 节的论证又画了一遍；visual-first 的“图要加信息，不要复述 prose”没有做到。它不是错，只是 redundant。

**判断**：BV17 是一篇可发布草稿；差一句“视频演示的是 EmbeddingGemma 2（视频称，未核实）”和一个 H2 措辞。它的 residual 是 **1 medium + 2 low**，全部可定点修；不是重写。

### 2.2 BV1AC（`runs/_diag/BV1AC_workflow_v14/output/reader.md`）

**做到了**

- 主线清楚：Harness 是什么 → 定位 → Cordis → 四份清单/三条轴 → PTC → 创造 → “技术人自嗨”批评（`:7-111`）；H2 是可读的 TOC。
- 四模式表（`:51-56`）和 PTC 5→3 表（`:74-79`）是有效结构；PTC 明确写“5 次变 3 次是算出来的，不是测出来的”（H2 `:68`）、正文“示意算术”（`:83`）、表里“3 次（示意）”（`:78`）。这是 claim status 做得最好的地方。
- 创造模式“两轮才成功”“两次 vs 几十次”都标了单次/作者自报/无基准（`:89-97`）；边界清楚。
- 来源行有 BV id + 作者 + 画面水印 channel + 未核实（`:113`）；四帧 real frame 可读（`visual/render.json:5-84`，都靠 `caption_dark_slide` override，但 captions 有内容）。
- 确定性 binding 干净：final facts 70/70 hard + 2 editorial、quotes 16/16；contract complete。
- 作者观点的归属比之前好：`“这个我就不太同意了”`（`:105`）、“这是他的判断，不是本文核实过的结论”（`:105`）；`“成熟”` 仍有一处小 inflation（`:109`，after-verifier low）。

**没做到**

- **标题被 repair 改掉了，而且没有 title finding。** brief 的 chosen title 是 `DeepSeek Harness 的四种模式，为什么是四份插件清单？`（`brief/brief.json:86-93`）；writer 稿 `writer/article.md:1` 用的就是这个问句；repair 把它改成 `同一套 Harness，四份插件清单：DeepSeek Harness 的四种模式`（`output/reader.md:1`）。repair 没有收到任何 title finding（pre-repair findings 是 tool names / diagram caption / “无需改源码” / “技术人自嗨”），`_repair_diff_guard` 只查 H2 数量，不查 H1。**这是 P4 的可见回归：问句有冲突，陈述句只是分类。** final verifier 的 `title_cta` 没抓，因为它只查匿名/术语前置/来源/URL，不查“有没有冲突”。
- **“差别集中在两处”是对四种模式的过度概括。** `:49` 说“从演示看，界面几乎一样，差别集中在两处：系统提示词 + 工具列表”；但创造模式的差别是“能查看/组合插件、创建新运行模式”，PTC 的差别是调用方式，不是这两处能覆盖的。after-verifier 的 medium claim_scope 就是这条（`verifier_final_after_report.json:14-20`），它是三篇里 BV1AC 剩下的 blocking finding。
- **正文和图注对“两个工具”说法不一致。** 正文 `:58` 说“口播把这两个工具读作‘半型’和‘字符串操作’，前者转写不清、视频里也没解释它到底是什么”；图注 `:64` 说“工具列表只剩 Bash 和 str_replace_editor”。after-verifier 的 medium consistency 是这条（`verifier_final_after_report.json:5-12`）。这里 verifier 有一处 **false positive**：它说 source_text 没有“字符串操作”这一读法，但 source 第 24 行确实有“只保留了半型和字符串操作的两个工具”。不过 **正文/图注的读者困惑是真的**：读者不知道“半型”就是 Bash，也不知道“字符串操作”就是 str_replace_editor。repair 把原来的“一个文件操作类”改成了这句，反而让正文更绕；caption restore 把 Bash/str_replace_editor 的图注恢复了，但正文没有同步。
- **source line 说“标题、发布日期与链接未提供”，但 brief/source_map 有标题和日期。** `:113`；`brief/brief.json:234-263` 的 source_block title = `Agent和Harness到底是什么？一个动画彻底搞懂！`、date = `2026-05-15（画面 OCR，未核实；与另一画面 OCR 的 2026年8月13日公告冲突）`。这不是“没有”，是“没有用”。contract 只查 missing 披露，不查 known 被误报 missing；final verifier 有 source_block 也没抓。
- **Cordis 的“内核只负责加载、卸载和依赖”在 brief 里是错的；writer 把它画成了 diagram，repair 删了 diagram。** 最终正文 `:45` 已经没有“不需要改源码”；repair 把它改成了“这个底板类比是本文为了方便理解做的……视频没有讲”。这是 repair 做对的一处。但 **brief 本身的 mechanism_chain 仍写“内核只负责加载、卸载和依赖”（`brief/brief.json:166-169`）**，下一轮 writer 还会再犯；这是“brief 是错误上游”的残留，不是当前稿的错误。
- **`:97` 有“它演示的是Agent”缺少空格**；`:105-109` 的“成熟”是 source 没有的词。都是 low，但说明 copyedit 层没有兜住。

**判断**：BV1AC 也是一篇可发布草稿；差一句“把‘差别集中在两处’限定为极简模式”、一句“正文写明 Bash / str_replace_editor 与口播读法的关系”、以及把 title 恢复成 brief 的问句。它的 residual 是 **2 medium + 3 low**；其中 claim_scope medium 是 blocking，consistency medium（工具名）不 block 但仍然可见；不是重写。

### 2.3 BV1yb（`runs/_diag/BV1yb_workflow_v3/output/reader.md`）

**做到了**

- 具体场景/对话链是三篇里最强的：1805 岁、丸子头/大头菜、魔法杖、斗地主被扔西红柿、分手厨房一个碗、看脑门、满屏抱抱、恩西马（`:11-85`）。读者能“看见”视频。
- 机制清楚：形象是容器（承诺 + 距离感），角色是幼儿园园长（不用毕业），玩得差降低参与门槛，真诚/守信接住倾诉（`:103-109`）；边界表（`:89-95`）和“个案、无效果数据、无对照、半个心理医生是比喻”（`:97-101`）是全文最诚实的地方。
- 来源行有节目名 + BV id + 画面水印 + missing 披露（`:117`）；这是旧 current 没有的。
- repair 修掉了 pre-repair 的 8 个 findings 里的大部分：一个孩子 vs 两个孩子（`:9`）、“定位来自一条弹幕”→“来自孩子的一句话”（`:31`）、“五周年新装”→“关系未确认”（`:17`）、“粉丝不会当真”→“本文的推测”（`:19`）、“最省力”→“对某些人，可能”（`:55`）、“菜菜子的版本”→“对话里的说法”（`:79`）、恩西马的“托”→“她说去问问他们”（`:81`）、魔法杖的指代（`:17`）。
- 确定性 binding 干净：final facts 14/14、quotes 0/0；contract complete。

**没做到**

- **引语被 repair 基本删光：writer 63 个引号对 → final 3 个（正文 0 个）。** writer 有 29 条 binding 引语（22 bound、7 unbound），final validation 的 `quotes.total=0`；`reader.md` 正文没有一处直接引语，只有两个 diagram caption 里还有引号。old judge 给旧 current BV1yb 的 P3 是 **90**（六篇最高），旧 current 有 36 个引号对；新稿的 P3/P4 很可能下降。这不是“文风选择”，是 repair 对 unbound quotes 的全局反应。
- **7 条 unbound 全是 `in_input`；其中至少 3 条精确出现在 edited text 但不在任何单条 pack sentence 里，另外 2 条是标点归一化变体。** 例：`我按哪个键扔回去呀？不会呀。`、`什么叫看我的面子？我又不吃。`、`只有虚拟主播。你想怎么让他好，他就能怎么好` 都在 edited text 里，但不在任何单条 pack sentence 里；`bind_article._quote_matches` 逐句查（`bind_article.py:376-405`），所以判 unbound。`quote_hygiene` 用的是 edited text，所以保留引号；两个 deterministic pass 对“引语是否合法”给出相反结论。**这是 code bug，不是 writer 伪造引语。**
- **repair 把于谦的归属也删了：writer 12 次 → final 4 次；“对话里”2 次 → 9 次。** 例：`于谦在旁边接了一句感慨` → `旁边接了一句感慨`（diff `_tmp_bv1yb_repair.diff`）；`于谦给了自己的判断：她有“半个心理医生”的作用` → `对话里给了一个判断`（`:69`）。source 里这些是于谦的明确发言（“咱都是打小过来的”“我说那句话没错，真有半个心理医生的这么一个”），不是“speaker unknown”。repair 把“speaker 可能错”的 finding 泛化成“所有归属都改成对话里”，读者失去了主持人和嘉宾的互动，P3/P4 的语气被抹平。
- **恩西马仍写成“已完成”。** `:81`：“她说去问问他们，后来通过朋友问到答案，回来在直播里告诉孩子这是什么，孩子特别高兴。” source 是“下次直播的时候告诉孩子们，我给你们问了啊”（`light_text.txt:18`，未来计划），后一句“他托你办的事，你给他办到了，他们就特别高兴”是通则，不是这次的结果。after-verifier 的 medium source 就是这条（`verifier_final_after_report.json:5-13`）。repair 改了“托”，但没改“已完成”；这是 **repair 没有完全执行 finding**。
- **diagram 节点和正文打架。** `diagram_01.svg` 节点 `五周年新装：魔法杖` vs 正文 `:17` “五周年关系未确认”；`diagram_04.svg` 节点 `真去问恩西马` vs 正文 `:81` “她说去问问他们”、`:107` “真去问恩西马”（`:107` 本身也还没改）。diagram 是 4 个 SVG，final verifier 的 `visual_status=not_provided`（没有 real frame），`visual_manifest` 没有被实际检查；所以这些矛盾留在交付稿里。
- **diagram caption 的 provenance 也不准。** `:23`/`:53`/`:73`/`:115` 都写“根据视频中的假设/示意绘制”，但这些 diagram 是 **文章自己的分析**（承诺/距离感、容器/稳定回应），不是“视频中的假设/示意”。BV17 的 diagram 至少写了“这是对文章描述的示意”；BV1yb 没有。这是 source attribution 的小但真实的错。
- **`:75` “它不治病，但它让一个人确认自己说出口的话被接住了”** 是从少数个案推出的效果判断；after-verifier 的 low claim_scope 就是这条。`:63` “跟父母说不通的孩子更多” 是文章自加的比较级；low。`:107` “真去问恩西马” 重复了未完成的事实；low。
- **最终综合 `:109` “虚拟形象提供的只是一个可以承载承诺的容器……”** 是本文的判断，但没有标“本文判断”；整篇的“本文”只出现 2 次。skill 要求三种句子分开；这里混了。

**判断**：BV1yb 的素材最好，但 repair 把它从“有现场感”改成了“正确但平”。它的 residual 是 **1 medium source + 4 low + 3 个 diagram 矛盾**；其中 medium 可一句修，diagram 矛盾需要 deterministic/visual 检查。它不是“写作失败”，是“repair 过度”。

---

## 3. Top 5 问题（按影响读者 / 影响成本 / 影响可迭代性排序）

### 问题 1：quote binding 的 pack/sentence 作用域 + repair 的全局去引号，导致合法引语和说话人归属被删（实现 + 设计 + 证据/数据）

**事实**

- BV1yb writer：29 条 binding 引语，22 bound、7 unbound_long；7 条全部 `in_input`（`validation.json` 的 binding counts；`quote_unbound` 7 条）；其中至少 3 条精确出现在 edited text 但不在任何单条 pack sentence 里（`_tmp_quote_scope.json`：`我按哪个键扔回去呀？不会呀。`、`什么叫看我的面子？我又不吃。`、`只有虚拟主播。你想怎么让他好，他就能怎么好`），另外 2 条是标点归一化变体（`上面长痱子，底下长冻疮`、`快点啊，把降压药、心脏病药都准备好啊，蔡蔡子要玩斗地主。`）。
- `quote_hygiene.clean_article` 用 edited text 判断，保留这些引号（`writing_v3/quote_hygiene.py:25-31`）；`bind_article` 用 pack sentences 判断，判 unbound（`writing_v3/bind_article.py:376-405,560-610`）。两个 deterministic pass 的 source-scope 不一致。
- pipeline 把 `quote_unbound_long` 当 binding failure（`validate.py:190-192`），于是 validation partial；repair 的 `REPAIR_INSTRUCTION` 说 unbound quote 要“remove the quotation marks and paraphrase it”（`prompt.py:40-44`）；repair 对整个 article 执行，结果 63→3 个引号对、正文 0 引语。
- 同一个 repair 把于谦 12→4、对话里 2→9（`_tmp_bv1yb_repair.diff`）。source 里这些句子有明确的于谦上下文（“咱都是打小过来的”“明儿我也得上你直播间”“我说那句话没错”），不是 speaker unknown。

**影响**

- 读者：失去现场引语和主持人/嘉宾的互动；P3（叙事/表达）和 P4（传播）最直接的损失。old judge 给旧 current BV1yb P3=90，新稿很可能下降。
- 成本：BV1yb repair 50,996 tokens / 160s，其中相当一部分是在修 false negative，并把 22 条合法引语一起删掉。
- 可迭代性：系统学到“删引号最安全”，下一轮 writer 还会写引语，下一轮 repair 还会删；这是一个自我强化的坏循环。

**分类**：主因 **实现**（bind_article 的 source scope；quote_hygiene vs binding 不一致），次因 **设计**（repair 没有“only listed spans / protect other quotes”合同），**证据/数据** 是 sentence 边界与 edited text 的拼接差异。

**为什么排第一**：它同时影响读者（voice）、成本（一次 repair 大半白费）和可迭代性（每次都会重演）；而且它是 deterministic、可复现、可修的一个点，不需要新 stage/agent。

---

### 问题 2：repair 没有最小范围 / protected span；验收是 count-based，不是 finding-based（设计 + 实现）

**事实**

- `_repair_diff_guard`（`pipeline.py:186-207`）只查 H2 数量变化、图片数量增加；`changed_ratio` 只作诊断，不阻断。H1/title、source line、引语、数字都没有保护。
- BV1AC repair 在没有 title finding 的情况下改了 H1（`writer/article.md:1` → `output/reader.md:1`；brief 的 chosen title 是问句，`brief/brief.json:86-93`）；`_restore_unrequested_captions` 只恢复 caption，不恢复 title。
- BV1AC 修前 4 findings（1 material medium），修后 5 findings（1 material medium）→ `post_audit_worse` 不触发，accepted；但 after 多了一个新的 medium claim_scope（“差别集中在两处”）和一个新的 source low（“成熟”）。`audit_comparison` 只比 critical/high/material_medium 数量（`pipeline.py:613-627`），不比 finding 的 identity/quote。
- BV1yb repair 的 changed_ratio 0.1417，删了 60 个引号对；`diff_guard.ok=true`，因为 H2 数量没变、图片没新增。
- repair prompt 说“Keep the article's headings and structure unless the finding is about a heading”（`prompt.py:66-68`），但 H1 被改；说明模型没有遵守，或把“heading”理解成 H2。没有确定性 guard 兜底。

**影响**

- 读者：最可见的 title 可能被降级；合法的 quote/source line 可能被删；repair 可能引入新错误，而系统认为“没变差”。
- 成本：一次 repair 可能只修好 1 个 finding，同时制造 1 个新的同等 finding；post-audit 再花 17–25k 才发现“数量没变”，但不能修。
- 可迭代性：无法判断“repair 是否真的变好”，只能看一个粗粒度计数；下一轮无法复用 finding history。

**分类**：主因 **设计**（repair 合同/acceptance policy），次因 **实现**（guard 不保护 H1/quote/source line；comparison 不比 identity）。

**为什么排第二**：它解释了“为什么修了还是 partial、为什么标题/引语会变差”；它是问题 1 的上位机制。修它比修单个 finding 更有杠杆。

---

### 问题 3：source metadata 已经提取，但 source line/contract/verifier 没有一致地使用和审计（证据/数据 + 实现 + 评测）

**事实**

- BV1AC source line `:113` 说“标题、发布日期与链接未提供、未核实”；brief/source_map 的 source_block 有标题 `Agent和Harness到底是什么？一个动画彻底搞懂！`、日期 `2026-05-15`（frame OCR，未核实；`brief/brief.json:234-263`）。`contract._source_missing` 取 brief 的 `missing`，其中 title/date 因为 source_block 有值而不在 missing 里；`_undisclosed_missing` 只查 missing 字段有没有被披露（`contract.py:47-63`），不查 known 字段被说成 missing。final verifier 也拿到了 source_block，没抓。
- BV17 source line `:97` 把 `EmbeddingGemma 2` 删了；after-verifier 的 medium source 说 source_text/frame 1 明确给了模型名，读者不知道用什么工具。repair 的 source 修复是“删掉 source line 里的产品信息”，不是“把产品名写进正文并标视频称/未核实”。
- BV1yb source_block 的 channel 是“于谦”（host/watermark），不是频道/节目名；source line 自己写了节目名《多新鲜呐》，所以读者没被误导，但 brief/verifier 的 channel 字段是错的。source_map 的 channel 启发式对访谈类视频仍会把 host 当 channel。
- 三篇的 source line 都写了“未核实/未提供”，但 **“未提供”与“有 OCR hint 但未核实”是两种不同状态**；当前 contract 把两者都当中性披露，读者无法区分“真的没有”与“有画面线索但没核实”。

**影响**

- 读者：P5 可信度的核心；“标题/日期未提供”是一句可以被读者用画面/视频页直接反驳的错话；BV17 的“Google 的说法”没有指向，建议不可执行。
- 成本：这是确定性/便宜的修复；现在却要靠 verifier 的 medium 来发现，且 verifier 有时漏。
- 可迭代性：source line 是旧 current 最大的净改进；如果它继续错，judge 的 P5 会重新红线。

**分类**：主因 **实现**（contract 单向、writer 不合并 brief 的 known fields、verifier 不比较 source line 与 source_block），**证据/数据** 是 frame OCR 只是 hint，不是结构化 metadata；**评测** 是 judge 的 P5 对 source line 的检查没有进入确定性层。

**为什么排第三**：它直接决定“能不能发”；但它的影响面比 1/2 窄，修起来也最便宜（contract + writer prompt），所以排在 1/2 之后。

---

### 问题 4：派生视觉（SVG diagram/chart/table）能生成，但没有 semantic audit；会和正文打架（设计 + 评测）

**事实**

- BV1yb `diagram_01.svg` 节点 `五周年新装：魔法杖` vs 正文 `:17` “五周年关系未确认”；`diagram_04.svg` 节点 `真去问恩西马` vs 正文 `:81` “她说去问问他们”。这两处都是交付稿，final verifier 的 `visual_status=not_provided`（没有 real frame），`visual_manifest` 在 payload 里但 prompt 的 visual axis 是“if images are provided”（`verifier.py:60`），所以 SVG spec 实际没被检查。
- BV17 正文 `:25` 说“视频给了一张真实结果做的图”，文章里放的是派生 diagram（`:29-31`）；真正的 2D 聚类帧没有进文章。visual planner 选了更安全的示意图，但没有在正文改口。
- `media/planner._validate` 只查 frame ID、chart 数字、table 数字/identifier、diagram node label 的 identifier（`media/planner.py:149-326`）；不检查 edge 关系是否被 source 支持，不检查 diagram 节点是否与正文/其他图矛盾。
- `media/render._caption` 对 `illustration` 一律加“（根据视频中的假设/示意绘制）”（`render.py:1026-1039`）；BV1yb 的 diagram 是文章自己的分析，不是“视频中的假设/示意”。BV17 的 diagram 至少还有“这是对文章描述的示意”。
- BV17 的最后一个 diagram 是 section-summary（`:93-95`），复述第 6 节；visual-first 的“图要加信息”没有做到。

**影响**

- 读者：图是“证据/结构”；图里写“五周年新装”而正文说“未确认”，读者不知道信哪个；这是 P5/consistency 的直接风险。
- 成本：VLM 已经接进 final verifier，但只覆盖 real frame；SVG 的语义审计缺口没有被覆盖。
- 可迭代性：visual planner 的 `status=illustration` 同时表示“视频假设”和“本文示意”，caption 后缀无法区分；下一轮还会错。

**分类**：主因 **设计**（visual audit 只覆盖 real frame；status enum 混淆 video hypothesis vs article illustration），次因 **评测**（没有 SVG→VLM rasterize/check；verifier 的 visual_manifest 没有独立 status）。

**为什么排第四**：它影响可信度和 visual-first，但只出现在有派生图的稿子（BV17/BV1yb），且不是每篇都致命；修起来是 prompt/manifest 的事，不需要新 stage。

---

### 问题 5：成本/状态/评测完整性：6–7 calls、138–212k tokens、三篇全 partial、polish 2/3 白花、runs/pack/request hash 全部 stale（评测 + 设计 + 实现）

**事实**

- 新 workflow 7 calls / 137,564、146,399、211,923 tokens；旧 current 3 calls / 38,586、79,154、64,596（BV1yb 含 repair；不含 repair 47,444）。新/旧 = 3.6x / 1.8x / 3.3x（BV1yb 不含 repair 是 4.5x）。
- polish 2/3 discarded（BV17 18,934、BV1yb 35,456）；BV1AC accepted 但最终仍 5 个 after findings。polish 的 cost 是确定的，收益没有被证明。
- 三篇 final status 都 partial，失败原因都只有 `verifier`；各剩 1 个 material medium。默认 `verify_after_repair=False` 时，repair accepted 后 `delivered_verifier_report` 仍是 pre-repair report（`pipeline.py:643-647`），final status 永远 partial + `repair_not_reaudited`（`:670-675`）。**默认 pipeline 在“需要 repair”时结构上不可能 complete。**
- 最新 runs 是旧 skill/旧 code（skill hash 4776af vs 当前 08ca35；run 22:29–22:59，code 23:07–23:11 仍在改）；judge v5 pack 的 new 侧是 v5/v10/v1（build script `:29-45`），当前 runs 是 v7/v14/v3；pack 15:46 构建（build script 15:36），当前代码 23:11 仍在改。**没有当前代码的 run，也没有当前代码的 judge。**
- 三个 request 的 stored `request_hash` 与复算值全部不一致（§1.3）；`validate_request` 不校验 stored hash。所谓“冻结 request”没有代码保障。
- 根 `validation.json` 是 repair 前，`output/validation.json` 是 repair 后；同一 run 两个状态（BV17 partial vs complete；BV1yb partial vs complete）。
- `media/planner.plan_visuals` 默认 `max_tokens=16384`（`media/planner.py:368`），与“不设 per-call max_tokens”的纪律不一致；`finish_reason=length` 没有专门状态，JSON 失败 → `invalid_output` → 无视觉，但 final status 不失败。
- `index_parts` profile 可以由 `select_profile` 选出（`context.py:140-155`），但 `build_user_prompt` 对 `index_parts` 直接 raise（`prompt.py:172-175`）；`sectioned` 返回 `unsupported_profile` 但 pipeline 不检查，继续调 writer 也会 raise。>30min 的视频会在 writer 阶段硬崩。

**影响**

- 读者：三篇都是“差一个 medium 的 partial”，不是“可发布”；用户看到的是“修了这么多轮还是 partial”。
- 成本：最贵的两个 stage（repair 25–51k、post-audit 17–25k）没有被证明值得；polish 2/3 白花。
- 可迭代性：stale runs/pack/request hash 意味着“当前代码到底怎样”不可知；下一轮 judge 如果直接用旧 pack，会测到不存在的代码。

**分类**：主因 **评测**（stale pack/runs/request hash；没有当前代码的 evidence），次因 **设计**（status policy、stage set、polish 的位置），**实现**（validation.json 不同步、manifest 不记 input paths、index_parts 边界）。

**为什么排第五**：它不直接让某一句变差，但它让“项目看起来坏了”成为事实：贵、慢、永远 partial、证据不可信。它是用户判断“架构级大改”的主要来源；但它是 control/measurement 问题，不是 content 问题。

---

## 4. 分类汇总

| 问题 | 设计 | 实现 | 证据/数据 | 评测 |
|---|---|---|---|---|
| 1. quote binding + 去引号 | repair 合同（次） | bind_article scope / quote_hygiene 不一致（主） | sentence 边界 vs edited text 拼接（主） | — |
| 2. repair 最小范围 / 验收 | repair 合同 + acceptance policy（主） | diff guard 不保护 H1/quote/source line；comparison 不比 identity（主） | — | — |
| 3. source line / metadata | source_block 合并策略（次） | contract 单向；writer 不用 known fields；verifier 不比较（主） | frame OCR 只是 hint，无结构化 metadata（主） | P5 没有进入确定性层（次） |
| 4. 派生视觉审计 | visual audit 只覆盖 real frame；status enum 混淆（主） | planner 只查结构；caption 后缀不区分（次） | — | 没有 SVG semantic audit（主） |
| 5. 成本/状态/评测完整性 | status policy / stage set / polish 位置（主） | validation.json 不同步；manifest 不记 input paths；index_parts 崩溃（次） | — | stale pack/runs/request hash（主） |

---

## 5. 保留 / 改 / 删（为什么）

### 保留（有证据支持）

- **substrate v1 light path + edited text**：三篇 final binding 都是 facts 63/63 hard + 1 editorial、70/70 hard + 2 editorial、14/14，quotes 9/9、16/16、0/0；source text 足够支撑 central question。不要动 substrate 的采集/句子/帧。
- **一次 Writer + skill**：三篇的 prose、结构、具体例子是三篇里最强的部分；old judge 的 P3 在旧 current 上能到 90；writer 不是瓶颈。不要为了“更可控”把它拆成多阶段。
- **source_map + editorial brief**：brief 的 core/spine/title/ledger 在 BV17/BV1yb 上明显有用于 claim status 和边界；BV1AC 的 brief 只有一处“内核职责”过度推断（被 repair 删了 diagram）。保留 brief，但修 title 合同和 source_block 合并。
- **deterministic validation + contract**：binding/quote/structure/hygiene 是干净的；contract 的 source line/title quote/number/image caption 检查方向对。保留，补三个洞：known field vs missing、H1 vs brief title、quote protection。
- **final verifier 作为 detector**：它抓到的多数 residual 是真的（BV17 模型名、BV1yb 恩西马、BV1AC “两处”）；不要因为它是 model 就否定。保留，但把它从“truth”降为“finding”，允许 repair 质疑/记录 false positive。
- **visual planner/renderer 的 provenance/readability/status 结构**：有 frame ID/数字校验、像素门、caption 后缀；问题在语义层，不在“有没有做”。
- **artifacts/trace**：manifest/prompt/raw/usage/latency/verifier 都可查；526 tests 通过。保留，补 input paths/hashes 和 validation.json 同步。

### 改（通用、跨 ≥2 case）

1. **quote binding 的 source scope**：在 writing 层把 `input_status == in_input` 的 quote 视为 bound（或把 edited text 作为 `bind_article` 的 source，而不是只做 input-scope check）；把 `quote_unbound_long` 中 `in_input` 的项降为 `quote_pack_miss` advisory，不驱动 repair。这是 writing 层的 workaround，不必改冻结的 substrate；如果要改 substrate，先按 §7 报告。
2. **repair 合同**：只改 findings 里明确 quote 的 span；保护 H1/title、source line、所有未被 findings 点名的 quotes；如果 quote 在 input 里但不在 pack 里，保留引号并记 `pack_miss`，不要 paraphrase。把 `REPAIR_INSTRUCTION` 从“unbound → 去引号”改成“unbound → 先查 input；input 有就保留；只有 input 没有才去引号/改写”。
3. **repair diff guard**：在现有 H2/图片检查之外，加 H1/title 不变（除非 title finding）、quote spans 不被非 finding 删除、source line 不变（除非 source finding）；`changed_ratio` 仍只作诊断，不设硬阈值。
4. **repair acceptance**：从 count-based 改为 finding-based：after 不能有新的 critical/high/material_medium（按 quote/axis 归一化比较），不能有 before 没出现的 material finding；如果 after 的 finding 只是 before 的同一 finding 的改写，算 resolved；如果是新的，算 worse。`audit_comparison` 记录 before/after 的 finding quote/axis 集合，不只数量。
5. **source line 合同**：contract 增加“known field 不能被说成 missing”：如果 brief.source_block.title/channel/date 有值（哪怕 unverified），source line 不能写“未提供”；只能写“画面显示/未核实”或“视频称/未核实”。这是确定性检查，不是新 validator；它补的是现有 contract 的单向漏洞。
6. **visual audit**：把 `visual_manifest` 从“有图才查”改成“始终查 spec”；对 diagram/chart/table 检查 caption/节点是否与正文、source_block、number_ledger 一致；对 `illustration` 区分“视频假设”与“本文示意”，caption 后缀分别写“根据视频中的假设/示意” vs “本文的示意整理”。如果 SVG 需要像素审计，再把 SVG rasterize 后送 VLM；先做 spec 交叉检查，不加新 stage。
7. **polish**：先做 A/B（polish on/off，3 dev cases）；如果 2/3 仍被丢弃且无 voice 增益，删掉 polish；如果要保留，改成“只改不触碰 facts/numbers/quotes/source line 的 span”，并在 polish 前把 protected spans 明确给模型。不是“再加一条规则”，是改 I/O。
8. **长视频边界**：pipeline 检查 `context.status == unsupported_profile`，返回明确 `unsupported_profile` 而不是继续调 writer；`index_parts` 要么实现 part 注入，要么在 select_profile 里不选它。graceful failure，不是新 gate。
9. **request hash**：`load_request` 校验 stored `request_hash` 与复算值；不一致就报 `request_hash_mismatch`，不静默重算。或者删掉文件里的 `request_hash`，只信 manifest；但“冻结”需要可验证。
10. **manifest/trace**：记录 request/skill/index/edited_text/pack/sentences/source_map 的路径 + hash；repair 后同步根 `validation.json`（或删掉根副本，只留 `output/validation.json`）；记录 brief chosen title vs final H1，以及 title 是否被改/为什么。
11. **visual planner max_tokens**：去掉 `max_tokens=16384` 的默认（或把 `finish_reason=length` 显式记为 `truncated` 并让 pipeline 失败/partial），遵守“不设 per-call max_tokens”。

### 删 / 退（不做）

- **不做第二次无限 repair loop**。只保留一次 bounded repair；如果要修 residual，用“人类 final edit”或“一次 verifier-report + human edit”，不是“再修一轮看看”。
- **不按单篇/单 finding 加 validator/词表/gate**。不硬编码“EmbeddingGemma”“恩西马”“差别集中在两处”；上面所有改动都是通用 scope/contract。
- **不恢复 v2 多阶段 waterfall**；不新增 agent/validator 数量。
- **不因为 judge 的 AI 初学者标准就把所有术语删掉**；默认读者是 technical baseline，先按标准评分并单列 `profile_mismatch`。
- **不在 pack 未重建前跑 judge v5**；不把旧 run 的分数当当前代码的结果。
- **删死代码/legacy**：`writing/planner.py`（writing-plan-v1）、`prompt.py` 的 `writing_plan` fallback、`media/planner._planned_visuals`（pipeline 从不传 `writing_plan`）。它们不影响输出，但增加下一轮的阅读成本。
- **polish 如果不能证明收益就删**；不要为了“流程完整”保留一个 2/3 被丢弃的 stage。

---

## 6. 下一步最小、最有杠杆的实验

### 假设

三篇的 reader-visible 损失，主要不是 writer 不会写，而是 **last-mile 的 quote binding/repair 合同把合法引语和归属删掉、把 title 改掉**；修这两个通用点，能在不增加调用、不改 substrate 的前提下，让交付稿更接近 writer 的第一稿，并让 repair 的 cost 更有意义。

### 方案 A（推荐，若用户要保留自动化）：最小修复 + 3 dev 复跑

**改动（只改 writing 层，不动 substrate）**

1. `validate_article`/`bind_article` 调用：把 `input_status == "in_input"` 的 unbound quote 视为 bound（或把 edited text 作为 source）；`quote_unbound_long` 只保留 input 也没有的项。
2. `REPAIR_INSTRUCTION`：unbound quote 先查 input；input 有 → 保留；只有 input 没有 → 去引号/改写；只改 findings 点名的 quote；保护 H1/title、source line、其他 quotes。
3. `_repair_diff_guard`：加 H1/title 不变（除非 title finding）、quote spans 不被非 finding 删除、source line 不变（除非 source finding）。
4. `audit_comparison`：before/after finding 的 axis+quote 集合比较，不只数量。
5. `contract`：known field 不能被说成 missing；`manifest` 记录 brief chosen title vs final H1。
6. （可选）post-audit 只在 pre-repair 有 critical/high 或 material_medium ≥2 时跑；或默认关，接受 `repair_not_reaudited` partial，但 manifest 给出 exact fix list。

**验收标准（3 dev cases）**

1. final H1 = brief chosen title，除非有 title finding；3/3。
2. BV1yb final 正文引语数 ≥15 条（writer 29 条 binding 引语的 50%；至少不要 63→3）；22 条 bound quotes 至少保留 20 条；不新增 quote_unbound。
3. 三篇 final verifier 的 critical/high = 0；material medium ≤1/篇，且每条要么是 before 就有的同一 finding，要么在 manifest 标为 accepted known risk。
4. 不引入新的 binding/contract failure；final `output/validation.json` 仍 complete。
5. repair 的 changed_ratio 不高于当前（BV17 0.0723、BV1AC 0.0559、BV1yb 0.1417）；repair tokens 不高于当前。
6. 总成本不高于当前（理想：少一次 post-audit 或 polish）。
7. 人读：3 篇的 voice/title/source line 至少不比当前差；BV1yb 的于谦归属至少保持 4 次，且只在 source 支持的地方保留。

**Case 数**：3 个 dev（BV17 短/analytical、BV1AC 中/product、BV1yb 长/interview）。这覆盖 3 种长度、3 种 claim 类型；满足 AGENTS 的 ≥2 视频/文体，不是单例。holdout BV13/BV1ix 仍不跑，不能据此说泛化。

### 方案 B（如果用户更在意“这周有可发布稿”）：简化 last mile，人做最后 edit

- 保留 brief + writer + visual + verifier（report only）；**删掉 polish 和 repair 的默认调用**；pipeline 输出 `draft.md` + `verifier_findings.md` + `source line` + `assets`，status 标 `draft_with_findings`。
- 人按 findings 做最后 edit（每篇 1 个 medium + 2–4 low，通常 10–20 分钟）；系统不再假装自动修。
- 成本：brief+writer+visual+verifier ≈ 80–100k；没有 repair 25–51k、post-audit 17–25k、polish 19–36k；没有 quote stripping/title change 的风险。
- 验收：3/3 有 draft + 可执行 finding list；无 red line；人能在 20 分钟内把 1 个 medium 修掉；judge A/B 对旧 current 的 P3/P4 不下降。
- 这不是“放弃自动化”，是把“编辑判断”留给最会做编辑判断的人；系统的价值是证据 + 第一稿 + audit，不是自动修复。

### 方案 C（不推荐）：架构级大重写

- 不推荐。主干（substrate→edited text→skill writer→deterministic binding→semantic audit）是成立的；重写会丢掉 source line、semantic detector、visual provenance 的真实收益，并重新引入 v2 的 waterfall 风险。
- 如果用户坚持大改，最小的大改是 **B**（删 last mile 自动化），不是重写 substrate/writer。

### 然后才跑 judge

- 用当前代码重跑 3 dev；重建 judge pack（不要复用 v5/v10/v1）；new 侧用修后的 run，baseline 用旧 current `runs/_brief_final3`（同一 request/视频）。
- 跑 30 份 subagent（5 persona × 6 篇，A/B 匿名）；按 `profile_mismatch` 单列受众差异；P5 红线优先；manual acceptance 由用户做。
- 不要提前读 `_hidden_mapping.json`；不要在 pack stale 时跑。

### 如果只能做一件事

**做 A 的第 1+2+3 项（quote binding + repair 保护 + title 保护）**：它是 deterministic、可测、跨 3 case、直接影响读者 voice/title 的一刀；不增加 stage/agent；如果做完发现 residual 还是 1 medium/篇，再决定 B（人 edit）或 second repair。**不要先做 judge**：当前 runs 是旧代码，judge 会测到不存在的状态；**也不要先做加 validator/agent**：问题在 I/O 和合同，不在检测能力。

---

## 7. 需要用户裁决什么

1. **目标是什么：可发布稿，还是诚实 partial + audit？** 当前 strict policy（material medium 即 blocking + 默认不 post-audit）让“修过的稿子”结构上永远 partial。若要可发布，要么默认 post-audit（+17–25k），要么允许人 final edit，要么放宽“单个 medium 不 block”。这是 policy，不是 bug。
2. **repair 能不能动 title/source line/引语？** 我建议：除非 finding 明确指向，禁止改 H1/title、source line、未被点名的 quotes。你同意吗？
3. **模型名怎么写？** BV17 的 `EmbeddingGemma 2`：写成“视频称 Google 昨晚开源了 EmbeddingGemma 2（未核实）”并放进正文，还是继续不点名？我建议前者：它是视频里的 claim，不是本文的官方断言，不触发 P5 红线；不点名会让建议不可执行。
4. **quote binding 的修法：writing 层 workaround 还是改 substrate？** 我建议先在 writing 层把 `in_input` 的 quote 视为 bound（不改冻结的 substrate），同时把 substrate 的“逐句查 vs edited text 拼接”问题记录为已知限制。你同意吗？
5. **polish 留不留？** 2/3 被丢弃，cost 19–36k；我建议先 A/B（on/off，3 case），没有 voice 增益就删。
6. **post-audit 默认开还是关？** 开：+17–25k，能确认 repair 是否变好；关：省成本，但 repaired 稿永远 `repair_not_reaudited` partial。你更在意哪一个？
7. **要不要把“current code”的 3 dev run + judge 作为下一轮的验收？** 我建议要：没有当前代码的 run/judge，下一轮无法判断任何改动是否有效。
8. **方案 A 还是 B？** A 保留自动化，修 last mile；B 删 last mile 自动化，人做 final edit。A 适合继续做产品；B 适合这周要可发布稿/作品集。我的推荐：先 A 的最小三项；如果 A 的 3 case 仍 1 medium/篇，转 B 的人 edit，不要 second repair。

---

## 8. 与上一轮 memo/文档的冲突（挑战，不是继承）

1. **上一轮 `DIAGNOSTIC_MEMO.md` 问题 1“final verifier 只读、不修”已经过时。** 当前代码是 final verifier 驱动 repair（`pipeline.py:480-581`）；问题变成了“repair 过度/不最小”，不是“不修”。不要按旧 memo 再提“把 final verifier 变成可驱动 repair”——已经做了。
2. **上一轮问题 2“source_map 不提取 channel/title/date、channel 截断”已部分修复。** 当前 source_map 提取 channel/title/date/official hints；BV1AC channel 从“的编程宇宙”修成“轩辕的编程宇宙”。但 **使用/审计层仍错**：BV1AC source line 仍说 title/date 未提供；contract 单向；verifier 漏。瓶颈从“提取”移到了“使用 + 审计”。
3. **上一轮问题 3“brief 是错误上游”已明显改善。** 当前 BV17/BV1AC/BV1yb brief 的 core/spine/ledger 多数准确；BV1AC 只剩“内核只负责加载、卸载和依赖”这一处过度推断（被 repair 删了 diagram）。不要把 brief 再当主因；主因是 repair。
4. **上一轮问题 4“视觉无语义审计”只修了一半。** real frame 已走 VLM（`verifier.py` images）；但 **derived diagram 仍无 audit**，BV1yb 的节点矛盾就是证据。不要因为“VLM 已接”就认为视觉审计完成。
5. **上一轮问题 5“标题/传播/受众”有改善也有回归。** BV17/BV1yb 标题更好；BV1AC 的 brief 问句被 repair 改成陈述句；judge 受众（AI 初学者）vs writer 默认（technical baseline）仍未解决。标题质量不稳定，不是已修。
6. **`PIPELINE_IO_AUDIT.md` 说“polish 值得保留”不被当前 runs 支持。** 最新 2/3 polish 被丢弃；需要 A/B，不要默认保留。
7. **`DISCIPLINE_AUDIT.md` 说“production 已无 dev case 专名”不准确。** `source_map.py:36`、`brief.py:588`、`cli.py:8-15` 仍有 BV1AC/轩辕/BV17；不是 hardcode，但 cleanup 不彻底。
8. **`STATE.md`/`HANDOFF.md` 的 526 对，`operating model` 的 508 是旧快照；`STATUS.md` 指向 v5/v10/v1，不是 v7/v14/v3。** 文档快照需要更新；但先不要改，等 memo 确认后一起改。
9. **judge v5 pack 不能跑。** new 侧是 v5/v10/v1；当前 runs 是 v7/v14/v3；当前代码 23:11 还在改。先重跑当前代码，再重建 pack。
10. **“三篇都 partial”不等于“三篇都坏”。** 三篇都没有 red line/critical/high；每篇只差 1 个 blocking 的 material medium（BV1AC 另有 1 个非 blocking 的 consistency medium）。上一轮 memo 的“partial 是诚实记录”成立；但“partial 可以交付”不成立——需要人 final edit 或 second repair，用户决定。

---

## 9. 一句话

**这套系统已经会写、会查、会修一部分；它还没学会“最小地修、保护不该动的东西、并诚实地结束”。先修 quote binding 和 repair 合同，再谈 judge 分数和第二轮优化；不要用架构大重写来掩盖一个 deterministic scope bug 和一个过宽的 repair 合同。**
