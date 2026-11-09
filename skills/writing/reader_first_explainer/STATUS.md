# STATUS：v2.0.0 draft，judge/reader test pending

> 2026-11-04：skill 重写为 v2.0.0。上一版 v1.1.0 的 runs **不是 v2 的证据**；v2 还没跑过模型。
> 质量门是 LLM-as-Judge（5 persona）× 真人 reader test（未来）；确定性测试只是地板。

## 这一版改了什么

- **去掉“核实官僚”**：不再要求每句“视频称/未核实”、不再把“三种句子”当标签。写作层只保证“视频有就写，没有就不写”；source line 只做出处。
- **Skill 从 15 条 self-review / 61 条 bullet 压到 8 问 + 五个写作决策**；把规则重量搬回标题/结构/视频等价/术语/边界/视觉/声音。
- **Voice** 明确借 stop-slop 的 8 条中文 AI 味规则和 avoid-ai-writing 的 source fidelity/protected content/one corrective pass；不抄词表。
- **Examples 重写**：19 组通用好/坏对照，新增“不要每句未核实”“不要升级官方”“说话人不猜”的例子。
- **References**：planning 变成五个决定；structure 强调 TOC/teaching flow；visuals 强调“图要和正文一致、不要 section-summary”；evidence 改成“对视频忠实，不核实世界”。
- **Rubric**：10 维诊断，judge/reader 是质量门；quote/数字/ID 是地板。
- **Manifest**：v2.0.0，`required_evidence` 只要 `edited_text`；frames/claims 可选；`quality_rubric=reader-first-v2`。

## 未完成

- v2 还没在 3 个旧 dev + 2 个新 dev 上跑。
- 还没做粗评（对照 `runs/_reader_test_2026-11-03/llm_judge/problems.md` 的 30 条典型问题）。
- 还没跑 30 份 LLM-as-Judge；没有真人 reader test。
- 下一轮要把 writer prompt/brief/verifier/repair 也按 v2 的“写作优先、编辑最小”哲学改；当前 pipeline 仍是 v1 的 9 轴 verifier + full rewrite repair。

## 下一步

1. 用 v2 skill 跑 5 个 dev（3 旧 + 2 新），先不跑 judge。
2. 粗评：对照 `problems.md` 的 top 10 + 版本特异问题，标出“同类/新问题”。
3. 若粗评显示 v2 在 title/voice/source/visual 上有改善，再重建 judge pack（旧 current vs v2）跑 30 份。
4. 然后改 pipeline：brief 缩短；verifier 只查 fidelity/attribution/consistency；repair 只做最小 patch 或交给人；去掉“未证实”blocking。
