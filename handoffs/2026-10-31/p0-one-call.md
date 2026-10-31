# v3 P0：一次 Writer 实测

> 日期：2026-10-31
> 对象：BV1ACbi6DEvC（656 秒，约 11 分钟）
> 结论：385 units → 116 sentences → 32 passages → 43 claims → 40-claim pack → **写作链 1 次 Writer**，reader 1,865 字，绑定/quote/hygiene 校验通过。质量主观上成立，但尚未做 reader test/A-B。
> 注意：标题的“one-call”指写作链；上游 claim extraction 是 1 次/视频（31k tokens），总调用 2 次、总 69k tokens。

## 1. 链路

| 阶段 | 输入 | 输出 | 模型调用 |
|---|---|---|---:|
| transcript_merge | units 385 | sentences 116 / passages 32 | 0 |
| claim_extract | passages 32 | claims 43 | **1** |
| pack_from_claims | claims 43 + sentences + frames | pack 40 claims / 53 sentences / 20 frames | 0 |
| v3_writer | pack + skill + request | reader 1,865 字 | **1** |

总模型调用：**2 次**（claim extraction + writer）；写作链 1 次。

## 2. 成本

| 阶段 | prompt | completion | reasoning | total | latency |
|---|---:|---:|---:|---:|---:|
| claim_extract | 5,387 | 25,890 | 21,647 | **31,277** | 115.8s |
| v3_writer | 17,508 | 20,563 | 15,444 | **38,071** | 110.0s |
| 合计 | 22,895 | 46,453 | 37,091 | **69,348** | ~226s |

- claim extraction 是一次/视频，可缓存；后续同视频换文体只重跑 pack + writer。
- 对比 v2 一条链 267k tokens、7 calls；v3 一次写作 38k、1 call。
- 仍有优化空间：claim extraction 的 21.6k reasoning 偏高；可换更便宜的 extraction 模型/降 reasoning，不加阶段。

## 3. Writer 输出

- reader 1,865 字，5 个 H2。
- 25 grounded spans / 9 editorial spans。
- 1 张图（`00000_000015000`，Cordis/一切皆插件画面），caption 是“看这里”。
- plan_header：title/controlling_idea/reader_path/5 sections/3 mechanism steps/demo choice。
- self_review：central question answered、mechanism retellable、conclusion synthesis、source attribution natural、boundary reader-facing；risks/uncertain/coverage gaps 都有。
- 校验：`status=complete`，0 issues。

### 内容结构

1. 四种模式不是四套程序（定位 + 问题）
2. 模型只负责想，Harness 负责让它能干活（Harness/Agent 机制）
3. Cordis 把“一切皆插件”变成可换的清单（插件化机制）
4. 四种模式改的是装配方式（标准/PTC/极简/创造）
5. 选模式，就是选让框架管到哪一步（synthesis + 边界）

**优点**：
- 没有按视频时间顺序写，也没有被安装/UI 带偏；40 条 claim 里选的是核心 25 条。
- 结论是 synthesis（责任分配/自动化/可控性），不是逐节 recap。
- 边界是读者向的：两次 vs 几十次只是作者一次测试；插件清单具体组成、PTC 重试成本、插件安全/生态未验证。
- 来源归属自然：“视频给极简模式的定位是减少干预”“作者也同意……”只在需要时出现，没有每段“视频作者认为”。

**仍需注意**：
- 个别 ASR 误识别/quote 截断仍在 audit 层（`harmonyos`/`Share`/`cortis`/“时间的验”）；正文用 claim text，没有抄错。
- 图片是候选帧，只保证时间窗/画面相关，不保证 claim-level 匹配；后续图表/生成图方案再补。
- 尚未做真实 reader test/A-B；不能把“我读着好”当发布通过。

## 4. Schema 修复

第一轮 Writer 出现 25 个 `quote not in text`。原因不是内容错，是 `quote` 语义没写清：它是**证据绑定/审计 quote**，正文可以改写；只有正文直接引用时才要求逐字一致。已修：

- `SKILL.md`：quote 是 audit binding，可在正文改写；直接引用才需逐字。
- `src/lunograph/writing_v3/one_call_writer.py`：只校验 quote 是 bound evidence 子串，不再要求出现在 text。
- 重跑 validate-only：`status=complete`，0 issues。
- 没有重跑 Writer；同一输出直接重新校验。

## 5. 结论

- **一次 Writer + 40-claim pack 能产出连续、可读、按读者路径组织的文章**；比直接读 ASR 好：有 claim/evidence/时间码/上下文/帧候选，不需要从 385 个碎片里抽 claim。
- **substrate 成本可接受**：1 次 claim extraction（31k）+ 1 次 writer（38k）；claim extraction 一次/视频、可缓存、跨文体复用。
- **下一步**：对这篇做真实 reader test/轻量 A-B；再跑第二个视频验证通用性（不按本篇调参）。如果第二篇也成立，再把 transcript/claim/pack/writer 固化为 v3 P1 默认短文体链路。

## 6. 文件

- [reader.md](examples/BV1AC_reader.md)
- [writer_output.json](examples/BV1AC_writer_output.json)
- [metrics.json](examples/BV1AC_metrics.json)
- [pack](examples/BV1AC_pack.json)
- [claims](examples/BV1AC_claims.json)
- [transcript passages](examples/BV1AC_passages.json)
- [substrate audit](substrate-audit.md)
