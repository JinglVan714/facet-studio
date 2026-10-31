# v3 Skill 复用映射

> 日期：2026-10-31
> 目的：P0 Skill 原型优先复用已有 skill/开源项目，不自己从零搓。
> 状态：设计/素材评估；对外发布前必须再过一遍 license。
> 有效输入（只读、不在 git）：`data/`（视频数据）、`参考素材/skills/`（skill 参考）。
> 已屏蔽：`_archive/_blocked/video-writing-product-architecture/`、`_archive/_blocked/AB/`；不要读/引用。

## 1. 已提供的素材

| 来源 | 许可证 | 可复用什么 | 不复用什么 |
|---|---|---|---|
| `C:/Users/30279/.claude/skills/bilibili-render-pdf` | 本地 skill，未见 LICENSE 文件 | 视频→讲义的教学流程、长视频分段、关键帧选择清单、帧时间 provenance、最终 synthesis、图注“看哪里” | 整条 LaTeX/PDF 交付链；未确认 license 前不逐字复制 |
| `参考素材/skills/aislinn-yang__rednote-writing-skill` | MIT | 小红书 voice 来自 examples；写/检分离；机械扫描+活人感冷读；标题/封面流程 | 账号定位、Notion 保存、具体违禁词表（不进入 core） |
| `参考素材/skills/d-wwei__great-writer` | MIT | 读者立场、core tension、结构先行、humanizer/polish、modular modes | 6-phase pipeline、red lines、字数/句长硬规则 |
| `参考素材/skills/Norman-bury__research-writing-skill` | MIT | 证据优于声称、引用可追溯、不编文献、两阶段 review 的思想 | 论文编排/章节确认/LaTeX 流程 |
| `参考素材/skills/yaoleifly__wechat-writing-style` | MIT | 公众号结论先行、口语化高密度、短段留白、平台敏感性检查 | 破折号/emoji/敏感词等硬规则不进入通用层 |
| `参考素材/skills/NEKOINEKOI__tomoai-longform-skill` | CC BY-NC 4.0 | 只作长文/自媒体结构参考（APAG、问题→观点→优势→行动） | **不能用于商业交付/直接复制**；如要商用，重写或换 MIT 来源 |
| `参考素材/skills/dexhunter__seedance2-skill` | MIT | 生图/视频 prompt 的结构：主体+场景+动作+镜头+时间分段+音频+风格；@ 引用语法 | 平台限制/模型参数硬编码；生图/视频 prompt 是另一个 skill |
| `参考素材/skills/blader__humanizer` | MIT | 去 AI 味的评估维度/示例 | 词表式 blacklist 不进入 core |
| `参考素材/skills/conorbronsdon__avoid-ai-writing` | MIT | 反 AI 写作模式的评测/示例 | 规则清单/词表不进入 core |
| `参考素材/skills/VincentOld__stop-slop-zh` | MIT | 中文 AI 味评估/示例 | 词表式规则不进入 core |
| `参考素材/skills/THUDM__LongWriter` | 需查 LICENSE | 长文生成研究参考 | 不直接接 pipeline；长文后置 |

## 2. 开源项目

| 来源 | 复用方式 | 阶段 |
|---|---|---|
| Anthropic Agent Skills / `anthropics/skills` | SKILL.md 格式、progressive disclosure、scripts 做确定性工作 | P0 |
| WriteHERE | 递归/图规划思想；长文再借，不做短文章默认 | P2 |
| STORM | research→outline→write→polish；多源/长文再借 | P3 |
| InkOS / OmniWriter | 长文/多 Agent/记忆；后置 | P3 |
| ffmpeg / faster-whisper / PaddleOCR / Qwen2.5-VL / InternVL | 视频/ASR/OCR/VLM 工具链 | P0 |

## 3. 按 v3 层的复用决策

### 3.1 视频证据编译器

直接借 `bilibili-render-pdf` 的：

- 字幕优先→Whisper 兜底→视觉模式的 source acquisition；
- 长视频按章节/分P/时间窗分段，相邻段留 overlap；
- 关键帧选择清单：相关性、所需内容可见、最终完整状态、附近最佳候选、可读性；
- 帧时间 provenance：帧必须能回到字幕/时间段；
- 最终 synthesis：保留作者有教学价值的收尾。

不借：LaTeX/PDF 交付、图注规则中的排版部分、逐字复制（license 待确认）。

### 3.2 Reader-first explainer skill

组合：

- `great-writer`：读者立场、core tension、证据密度、结构先行、humanizer 的“像人写”；
- `bilibili-render-pdf`：动机→主 idea→机制→例子/证据→takeaway 的教学 flow；最终 synthesis；
- `research-writing`：证据优先、不编事实/引用；
- `humanizer`/`avoid-ai-writing`/`stop-slop-zh`：只作为 examples/eval，不做词表规则。

不借：6-phase pipeline、每阶段 gate、字数/句长/黑名单硬规则。

### 3.3 社媒 skill（后续）

- `rednote-writing-skill`：voice 来自 examples、写/检分离、标题/封面；
- `wechat-writing-style`：公众号结论先行、口语化高密度；
- `tomoai-longform-skill`：只作结构参考（NC，不直接复制）。

### 3.4 生图/视频 prompt skill（后续）

- `seedance2-skill`：主体+场景+动作+镜头+时间分段+音频+风格；@ 引用资产角色；
- `bilibili-render-pdf`：关键帧候选/时间 provenance；
- 生成图只 editorial，不作为视频证据。

### 3.5 长文/讲义（后续）

- `bilibili-render-pdf` 的教学结构/帧 provenance；
- `tomoai`/`LongWriter` 只作参考；
- 长文分节 Writer，不先做多阶段瀑布。

## 4. 不进入 v3 core 的东西

- 词表/违禁词/句长/字数/emoji/破折号等硬规则；
- 6-phase/多阶段 gate；
- 每文体一套 validator/gate；
- CC BY-NC 内容直接进入商业交付；
- 未确认 license 的 bilibili skill 大段逐字复制。

## 5. 落地方式

- 每个 v3 skill 目录带 `SOURCES.md`，列出借用的来源、license、改动点；
- 可直接复用的 MIT 内容保留版权声明；不确定/NC 的只借方法/结构，重写文本；
- 对外发布前跑 license 清单；不能确认的替换或删除。

## 6. 下一步

1. 用 `great-writer` + `bilibili-render-pdf` + `research-writing` 组合出 `reader_first_explainer` 的 `SKILL.md`；
2. `examples.md` 用原创好/坏对照（不复制 NC/未确认 license 文本）；
3. EvidencePack builder + 一次 Writer PoC；
4. 后续社媒/生图/讲义 skill 再按上表接。
