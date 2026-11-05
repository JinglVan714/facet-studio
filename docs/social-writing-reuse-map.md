# 社媒写作 reuse map（2026-11-05）

> P0 调研：本地 + GitHub，只读，不写代码。范围：小红书 + 公众号。
> 目的：在开写前决定“借什么、不借什么”，让社媒是现有 video-article 核心的**平台层**，不是另一套方法论。
> 结论：社媒 = 现有“理解 → 组织 → 表达 → 自审”核心 + 平台 shape/reader/format；优先借结构、rubric、beats/grounding、多平台改写原则；不借账号 voice、强制 emoji/网络梗、engagement bait、发布管线。

## 0. 结论先行

1. **小红书/公众号不是新方法**：它们和现有 article skill 共用同一个内容稿、同一套证据纪律、同一个“一个控制性 idea + 机制 + 例子 + 边界”的写作逻辑；差异在读者、长度、开头、段落节奏、标题/标签、平台语气。
2. **最值得借的四类**：
   - 平台 shape：一篇只讲一件事、hook、短段、标题、标签/CTA（rednote、cool111111、great-writer、wechat-style）。
   - 质量 rubric：准确/观点/有用/合声/好读 + 阻断项（wewrite）。
   - 多平台改写：内容级重写，不是近义词替换；同源多版本要拉开差异、保持同一 persona（wewrite）。
   - beats/grounding：每个 beat 只做一件事；概念先 grounding；format 选择要有理由（mattpocock、bilibili-render-pdf）。
3. **不借**：账号特定 voice/examples（rednote 的 AI 出海账号）、强制 emoji/“姐妹们”/网络梗（great-writer 小红书模板）、CES/涨粉优化、Notion/公众号发布管线、与内容无关的合规/敏感词库、30 judge。
4. **License 纪律**：rednote / wechat-style / wewrite / great-writer / mattpocock 是 MIT；anthropics internal-comms 是 Apache-2.0；bilibili-render-pdf 本地无 LICENSE（只在本地借逻辑）；cool111111、gainubi 未见 LICENSE（不抄文本，只借思路）；JuneYaooo/xhs-writer-skill 是 Apache-2.0。**即使 license 允许，也借逻辑不抄文本；例子不搬。**
5. **对当前 skill 的落法**：保留 video-article 作为“内容理解 + 证据纪律”核心；新增平台层 `references/platforms/xiaohongshu.md` / `wechat.md`，由平台编辑 specialist 使用；不复制 pipeline。

## 1. 平台矩阵

| 维度 | 小红书 | 公众号 |
|---|---|---|
| 读者 | 刷信息流；0.5 秒决定划不划走；想快速拿到一个点 | 已点开/订阅；愿意读长文；想理解一件事 |
| 长度 | 不设硬长度；短、精简优先；内容多可到 1000+，不硬凑 | 不设硬长度；1500–3000 优先；短视频不硬凑几千字 |
| 结构 | 一个点；hook → 解释/场景 → 核心细节 → 可选行动；短段 | 结论先行；一个控制性 idea；2–4 个 H2；机制/例子/边界；短段 |
| 开头 | 第一句给结果/反差/问题；不铺垫 | 前 3 句给结论或判断；不铺垫 |
| 标题 | ≤20 字；具体、有信息量；不极限词/标题党 | 具体、有点击理由；含核心关键词；3–5 个候选 |
| 段落 | 2–4 句；留白；可扫读 | 1–3 句；留白；单句成段可强调 |
| 语气 | 第一人称、像朋友；但**不强制** emoji/网络梗 | 口语化、高信息密度；不书面腔 |
| 标签/CTA | 3–10 个标签（请求要求才写）；结尾自然收，不空泛求赞 | 结尾一句互动/行动；不喊口号 |
| 图 | 封面 + 1–3 张内容图；有真实帧就用，没有不硬编 | 可有可无；图服务机制/例子，不堆图 |
| 证据 | 事实/数字/引语只来自内容稿；不编亲历；一个案例保持一个 | 同左；结论不超出证据；第三方数字保留“据内容/Google 说” |
| 我们额外守 | 不用“作者说/视频里/内容稿/素材”；不把演示写成普遍规律 | 同左；不写“未证实/待核”体检报告 |

## 2. Reuse map（来源 → 借什么 → 不借什么 → license）

| 来源 | 借什么 | 不借什么 | License |
|---|---|---|---|
| [rednote-writing-skill](https://github.com/aislinn-yang/rednote-writing-skill)（本地） | “voice 由 examples 决定，不套模板”；写完再检查（写/检分离）；标题/封面规则（核心词前 10 字、≤25 字、不极限词）；一篇只讲一个点；不编事实但可延伸思考；封面比标题重要 | 账号定位/8 篇真实帖子（AI 出海 voice，不适用）；Notion 保存；强制 emoji/网络梗；CES/涨粉权重；违禁标点死规则（会与内容冲突） | MIT |
| [wechat-writing-style](https://github.com/yaoleifly/wechat-writing-style)（本地） | 结论先行；口语化但高信息密度；短段/留白；中英文/数字空格；不用破折号；H2 用口语问句；标题 5–10 候选；结尾自然互动；具体工具/场景/数据 | 投资免责声明/VPN 敏感词（内容特定）；4000–8000 字硬长度；具体主题领域；模板化过渡词 | MIT |
| [wewrite](https://github.com/imraywang/wewrite)（本地） | 七种框架（痛点/故事/清单/对比/热点/观点/复盘）；五项编辑质量 + 阻断项；多平台改写=内容级重写，不是洗稿；同源多版本要拉开差异、保持 persona；标题/风格分离 | brief/claims/review-report 多阶段管线（旧链味）；CLI/公众号发布；2 轮 repair；quality_score ≥60 硬门 | MIT |
| [great-writer](https://github.com/d-wwei/great-writer)（本地） | 小红书三个子类型（种草/干货/经验）、长度区间、标题公式、anti-pattern、诚实边界、配图建议 | 强制 emoji（1–2/段）、“姐妹们”开头、网络梗、涨粉公式、温度/人格参数 | MIT |
| [mattpocock writing-beats / writing-shape](https://github.com/mattpocock/skills)（本地） | beat 定义（一个 move/一件事）；grounding（prerequisite vs introduced）；format 选择（prose/list/table/quote）；“文章在 journey 完整时结束，不是 pile 用完” | 交互式 choose-your-own-adventure；逐 beat 追加文件的工作流 | MIT |
| [anthropics internal-comms](https://github.com/anthropics/skills)（本地） | 按 communication type 选格式；guideline/examples 的结构 | 3P/newsletter/FAQ 内部通讯格式（除非内容匹配） | Apache-2.0 |
| [bilibili-render-pdf](C:/Users/30279/.claude/skills/bilibili-render-pdf)（本地） | 教学 flow：motivation → idea → mechanism → example/evidence → takeaway；不要按字幕时间顺序 dump；概念先落地；具体机制/例子/数字 | LaTeX/PDF 管线（PDF 暂不做）；图越多越好；封面/模板 | 本地无 LICENSE |
| [cool111111/xhs-content-skill](https://github.com/cool111111/xhs-content-skill)（GitHub） | 一篇只讲一个点；0.5 秒 hook；HKR 选题检查（可作参考）；3–5 标签；Q1–Q5 检查（hook/density/prohibitions/platform fit/sources）；不教科书腔；结尾不 engagement bait | HKR 作为硬框架；具体 prompt 文本（未见 LICENSE）；平台违禁词库 | 未见 LICENSE |
| [UnderleveledBuilder/awesome-social-media-skills](https://github.com/UnderleveledBuilder/awesome-social-media-skills)（GitHub 目录） | 找到更多可借项目：`xhs-writer-skill`（Apache-2.0）、`writing-agent`（MIT；director/lead writer/reader-reviewer/de-AI editor，可参考多 Agent 编排）、`content-skills`（MIT；hook/script patterns）、`video-spec-builder`（MIT；storyboard）、`wechat-article-skills`（Apache-2.0） | 整包照搬；未标 license 的项目；发布/自动化管线 | 各项目不同 |
| [gainubi/wechat-skills](https://github.com/gainubi/wechat-skills)（GitHub） | 阶段拆分（topic/outline → draft → title → style profile）；style 作为持久 artifact；title 生成与评分分离；短段/清晰结构 | 具体文本（未见 LICENSE）；交互式多阶段流程；发布 | 未见 LICENSE |

## 3. 对当前 skill 的落法

- **核心不换**：`skills/writing/video-article/SKILL.md` 的内容理解、证据边界、直接陈述、scope、自审继续用；社媒只加平台层。
- **平台层**：
  - `skills/writing/social-note/references/platforms/xiaohongshu.md`：读者/长度/结构/hook/标题/标签/段落/图/CTA + 反例。
  - `skills/writing/social-note/references/platforms/wechat.md`：结论先行/短段/H2/标题候选/结尾/长度 + 反例。
  - 两个平台共用同一个 writer 调用；平台差异在 prompt/reference，不在 pipeline。
- **多平台一致性**：同一视频的小红书/公众号版本必须 **内容级重写**，不能近义词替换；事实、数字、范围、结论要一致；平台版本之间要拉开表达差异（wewrite 的原创铁律）。
- **质量 rubric**（每个平台都过）：
  1. 准确：核心事实有内容稿依据；事实/推断/意见分开；结论不超出证据。
  2. 观点：一个控制性 idea；说明新增价值/适用范围/最强反方（有就写）。
  3. 有用：给行动、判断方法或可迁移理解。
  4. 合声：像一个人在讲，不是 AI/营销腔；不用账号特定 voice。
  5. 好读：开头进入问题；每段有任务；标题准确；短段/留白。
  - **阻断项**：编造亲历/朋友/采访/场景；核心事实无来源；结论超出证据；没有明确读者交付；正文出现工作痕迹。
- **不做**：强制 emoji/网络梗；engagement bait；平台违禁词硬 validator；30 judge；brief/claims/verifier/repair 链；PDF。

## 4. 社媒 prompt 结构（草案，不是最终 skill）

### 小红书
- 角色/读者：刷信息流的普通人；0.5 秒决定是否继续。
- 输入：content.md + figures；事实只来自内容稿。
- 规则：一篇只讲一个点；标题 ≤20 字；第一句给结果/反差/问题；2–4 段短段；至少一个具体数字/动作/条件；结尾一个动作/判断；标签请求要求才写；不编亲历/品牌/价格；一个案例保持一个。
- 自审：一个点？hook？具体细节？标题兑现？范围？工作痕迹？AI 味？
- 输出：`# 标题` + 正文（+ 可选标签）；出处由 runner 补。

### 公众号
- 角色/读者：已点开、愿意读长文的读者；想理解一件事。
- 输入：content.md + figures。
- 规则：前 3 句给结论/判断；一个控制性 idea；2–4 个 H2（口语问句/具体判断）；机制优先；一个具体例子/数字；诚实边界；短段；不用破折号；标题 3–5 候选（或 1 主标题 + 2 备选，按请求）；结尾自然互动/行动。
- 自审：结论先行？一个 idea？机制/例子？边界？标题兑现？工作痕迹？AI 味？
- 输出：`# 标题` + 正文；出处由 runner 补。

## 5. 已确认的取舍（2026-11-05）

1. **小红书 emoji**：**可用，不强制，不设 1–2 个上限**；按平台自然使用，但不为 emoji 牺牲信息密度。标题 emoji 可选。
2. **公众号长度**：**不设硬长度，按内容**；1500–3000 优先，短视频不硬凑几千字；一句话能说清就不扩。
3. **标题候选**：正文一个主标题；平台编辑另出 2–3 个备选（sidecar），不污染正文。
4. **平台编辑：直接 B（多 Agent 编排）**。P1 就做 LeadPlan + Platform Editor，不再先做单 writer A 再重构；writer 出平台稿 → platform editor 做平台适配 → lead 合成。成本 +1 call/版本，换来 JD 第 1 行真实落点。
5. **图**：先用 content.md 里的真实帧（1 张封面 + 1–3 张内容图）；效果不好后续再生成图表/模板图；不伪造画面。小红书是“顶部图片（模板/真实帧/总结）+ 标题 + 正文纯文字 + tag”，所以交付包要含 card_copy/images/publish，不只正文。
6. **HTML/PDF**：P1 只做 md；HTML 后置；**PDF 暂不做**。
7. **小红书内容类型**：用**干货/教程**，不用“种草”框架；emoji 可用但不走营销号套路。

## 6. 下一步

- 已确认目标架构：LeadPlan + Platform Editor + specialists + 共享 RunState + trace；P1 直接做。
- P1：写 `social-note` 的平台 references（小红书/公众号）+ orchestrator/platform editor，再生成 BV1ix/BV17 × 2 平台 = 4 个发布包；floor + 5 维 rubric + 人工 acceptance + 跨平台一致性。
- 不写 HTML/PDF；视频脚本 P2；HTML P3；demo P4。

## 7. 来源

- [rednote-writing-skill](https://github.com/aislinn-yang/rednote-writing-skill) — MIT
- [wechat-writing-style](https://github.com/yaoleifly/wechat-writing-style) — MIT
- [wewrite](https://github.com/imraywang/wewrite) — MIT
- [great-writer](https://github.com/d-wwei/great-writer) — MIT
- [mattpocock/skills](https://github.com/mattpocock/skills) — MIT
- [anthropics/skills](https://github.com/anthropics/skills) — Apache-2.0
- [bilibili-render-pdf](C:/Users/30279/.claude/skills/bilibili-render-pdf) — 本地无 LICENSE
- [cool111111/xhs-content-skill](https://github.com/cool111111/xhs-content-skill) — 未见 LICENSE
- [UnderleveledBuilder/awesome-social-media-skills](https://github.com/UnderleveledBuilder/awesome-social-media-skills) — 目录；各项目 license 不同
- [gainubi/wechat-skills](https://github.com/gainubi/wechat-skills) — 未见 LICENSE
- [JuneYaooo/xhs-writer-skill](https://github.com/JuneYaooo/xhs-writer-skill) — Apache-2.0
