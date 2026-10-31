# REFERENCES.md — 本地参考与证据索引

> 本文件是 git 可见的索引。完整素材保留在本地只读目录，默认不入 git（体积、许可证、cookies）。
> 新 session 看到本文件即可知道路径；需要具体内容时按路径读取，不要改动源目录。

## 1. 写作 Skill 参考

路径：`参考素材/skills/`（约 73MB，17 个下载仓库）

- `aislinn-yang__rednote-writing-skill`
- `blader__humanizer`
- `conorbronsdon__avoid-ai-writing`
- `crewAIInc__crewAI-examples`
- `d-wwei__great-writer`
- `dexhunter__seedance2-skill`
- `imraywang__wewrite`
- `LearnPrompt__awesome-seedance`
- `Mouriya-Emma__writing-pipeline-zh`
- `NEKOINEKOI__tomoai-longform-skill`
- `Norman-bury__research-writing-skill`
- `THUDM__LongWriter`
- `VincentOld__stop-slop-zh`
- `wordflowlab__article-writer`
- `yaoleifly__wechat-writing-style`
- `zenstory-ai__drama-skills`
- `zwzhangyu__ai-agent-lab`

本地 `bilibili-render-pdf`：

`C:/Users/30279/.claude/skills/bilibili-render-pdf`（约 33KB，含 `SKILL.md` / `assets` / `agents`；本地未见 LICENSE）

使用规则：

- 全部只读；复用/二开前先审 license、安全、维护状态。
- 当前 [reader_first_explainer](skills/writing/reader_first_explainer/) 是 **v0.1 provisional**；不要把它当最终 skill，也不要因为它存在就停止调研。
- 下一轮 skill 工作先重新大量调研这些参考 skill + 本地 `bilibili-render-pdf`，再决定重写、二开或保留。
- 不把第三方仓库整目录复制进 v3；不照搬与证据优先冲突的整条 pipeline。
- 初步来源/复用记录见 [handoffs/2026-10-31/skill-reuse-map.md](handoffs/2026-10-31/skill-reuse-map.md)，那是历史快照，不是最终结论。

## 2. 视频证据

路径：`data/`（约 283MB，9 个视频）

- `BV13EHX64EaY`
- `BV17DHC6CELr`
- `BV1ACbi6DEvC`
- `BV1B5411A7ax`
- `BV1eUhM6hEdn`
- `BV1ixpd6GENc`
- `BV1qoHe6mEx6`
- `BV1ybHXzfEEu`
- `BV1znXSBqEUP`

目录可能包含 `raw/`、`transcript/`、`frames/`、`frames_scene/`、`frames_vlm/`、`substrate/`；不同视频不完全一致，**具体结构/字段以用户后续提供的结构为准，不要猜**。

- `data/cookies/` 含登录凭据：不读、不复制、不入库、不外传。
- `raw/*.mp4`、`transcript/*.wav`、`frames*/` 等媒体默认本地只读，不入 git。
- 后续需要某个视频时，由用户给出对应结构，再按结构读取；不要先扫描/改写全量 data。

## 3. Git 可见范围

- **已跟踪**：代码、`architecture.md` / `AGENTS.md` / `HANDOFF.md` / `STATE.md`、`skills/writing/`、`handoffs/`、本文件。
- **本地只读、不入库**：`data/`、`参考素材/skills/`、`_archive/`、`runs/`、`docs/_frozen/`、第三方大仓库。
- **原因**：data 约 283MB 且含 cookies/原始媒体；参考 skills 约 73MB、许可证各异；全量入库会泄露凭据、膨胀仓库并带来再分发风险。
- 若确实要全量版本化：先清 cookies、逐一审 license，再用独立仓库或 Git LFS；不要直接 `git add -f data/`。
