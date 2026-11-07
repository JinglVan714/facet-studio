# 2026-11-05 session 2：当前方向与接手点

> 当前快照（2026-11-06）。当前架构：[docs/writing-v5-architecture.md](../../docs/writing-v5-architecture.md)；JD 映射：[docs/jd-mapping-2026-11.md](../../docs/jd-mapping-2026-11.md)。
> 历史入口见 [NEXT_SESSION_PROMPT.md](NEXT_SESSION_PROMPT.md)（旧 session 快照，不是方向指令）。

## 当前形态

**三种：深度总结（long_article）/ 公众号（wechat_article）/ 小红书（xiaohongshu_note）。**
**短视频脚本暂不做**，后续有需要再加。

## 当前状态

- 公众号 v5、小红书 v3 用户“大致验收”。
- Lead Planner + orchestrator + bundle 已跑通：
  - [BV17 social_05](../../runs/writing_v5/bundle_BV17_social_05/bundle.md)：公众号 2,637 字 + 小红书 944 字，complete。
  - [BV1ix social_04](../../runs/writing_v5/bundle_BV1ix_social_04/bundle.md)：公众号 2,514 字 + 小红书 773 字，complete。
- Orchestrator：`skills/writing/bundle-planner/` + `planner.py` + `tools.py` + `orchestrator.py` + `run_bundle.py`；接 RunStore/TaskPlan/ToolExecutor/WorkingMemory/ArtifactBoard/Decision/Trace。
- form-scoped request：writer 只写自己的 form，不看 bundle request；每个产物一次 writer，无 editor/checker。
- 开发纪律修复：active skill 里的具体视频内容已清理；例子改为匿名场景（收纳/手冲咖啡/写作/健身）；不再按单例调参。
- 读者通读后收过一轮：BV17 公众号开头/H2 的概念顺序已修；小红书干净；BV1ix 两篇稳。BV17 公众号仍残留 `query / 4 字节 / 0.709`（模型判断问题，不是 skill 规则）。
- 最新 bundle 的 JD 证据：`lead_plan.json`、`task_plan.json`、`llm_calls.jsonl`、`tool_calls.jsonl`、`decision_records.jsonl`、`working_memory.json`、`artifact_board.json`、`semantic_memory.json`、`bundle_manifest.json`。

## 当前边界（用户明确）

- 一个产物一次 writer；没有草稿阶段、editor、checker。
- Writer 不知道来源；只拿到「这件事的完整内容」；不核验内容本身、不挑错、不做百科。
- 不写死字数、H2 数、段落数；request 优先，没 request 用默认。
- 前端 prompt 驱动 request；链路干净、低成本、不冗余；展示页要美观。
- 用户人工验收是唯一发布门；不按单篇调参；active skill 不出现具体视频/产品/人物。
- 不恢复旧 supervisor/demo/词表/P1 两段式；不跑 30 judge；不自动发布；不 commit/push。

## 未做 / 可能方向（仅参考，不是方向指令）

- **接手 session 自己看代码、runs、产出和用户反馈，自己判断下一步；用户裁决。** 不要照抄本文件的方向。
- 事实上的未做项：per-form eval case、replay 实测、MCP 薄 adapter、Human-in-the-loop 发布门、FastAPI/前后端 demo、展示页；`long_article` 未接进 bundle。
- 可能方向（不排序、不推荐）：展示页；3-form bundle；JD eval/前后端；更多视频；进一步质量收口；其他。

## 接手先读

1. `docs/writing-rebuild-brief.md` §2（好 writing）+ §3（开发纪律）。
2. `AGENTS.md`（护栏；§5 不要改）。
3. `docs/writing-v5-architecture.md`。
4. `architecture.md` §0.1（机会地图；旧实现是历史）。
5. `STATE.md` + `HANDOFF.md`。
6. `docs/jd-mapping-2026-11.md`（JD/面试）。
