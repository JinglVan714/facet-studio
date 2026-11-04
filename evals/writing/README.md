# Writing Evals（当前协议 2026-11-03）

> 状态：当前评测协议；不是已验收基线结果。LLM-as-Judge 是当前主评测；真人 reader test 未做、未来可选。
> 上位：[docs/writing-operating-model.md](../../docs/writing-operating-model.md)、[AGENTS.md](../../AGENTS.md)、[architecture.md](../../architecture.md)。
> 原则：先冻结 request，再看文章；不按单篇调参；不伪造 reader test/A-B；技术 complete ≠ reader pass。

## 0. 当前评测栈（2026-11-03）

| 层 | 工具 | 当前状态 | 说明 |
|---|---|---|---|
| L1 确定性 | `lunograph.writing.validate` + `contract` | 每次 run | structure/reader hygiene/quote hygiene/binding/source line/title/caption/gaps/absolutes |
| L2 语义审计 | `lunograph.writing.verifier` | 每次 run | initial 驱动至多 1 次 repair；final 只读审计交付稿，不再 repair；residual → partial |
| L3 LLM-as-Judge | 5 persona × 6 篇；两份只读标准 | 第一轮 30 报告已完成；v5 pack 待跑 | 匿名 A/B；团队权重 0.20/0.25/0.20/0.15/0.20；P5 红线；用户 manual acceptance |
| L4 真人 reader test | 5+ 真人、盲读、attestation | **未做** | 未来可选；不得用模型/模拟盲读冒充 |

### L3 标准与 pack

- 只读标准：`runs/_reader_test_2026-11-03/reader_pack/5个persona.md`、`评价方法.md`（不要修改）。
- 当前 pack：`runs/_reader_test_2026-11-03/judge_v5/`；启动 Prompt：`STARTUP_PROMPT.md`；`reader_pack/` 给 subagent；`_hidden_mapping.json` 在 30 份报告完成后才读。
- 5 persona：Human Reader / Knowledge Translator / Content Strategist / Growth Expert / Critical Reviewer。
- 每个 subagent 只看两份标准 + 自己的 persona + 自己那篇；互不可见；不联网；不改文章。
- P5 红线优先：重大事实错误/严重误导/未证实关键产品能力写成已证实 → risk hold；团队分不是发布许可。
- 标准受众是 AI 初学者/普通互联网用户；当前 writer 可能按 technical baseline 写作；按标准评分，同时单列 `profile_mismatch`，不静默放宽准确性/红线。

### 第一轮结果（旧 pack，事实）

- 30 份独立报告；current 赢 2/3；candidate P2 −8.0；3/6 红线。
- 详细：`runs/_reader_test_2026-11-03/llm_judge/summary.md`、`problems.md`、`method_conflicts.md`、`manual_acceptance.md`。
- 这些分数是旧 pack 的 LLM-as-Judge，不是真人 reader test，也不是当前 v5 的结果。

---

## 1. Case 集

### Dev（允许调 skill/参数）

| case | video | 时长 | 用途 |
|---|---|---:|---|
| BV17 | `BV17DHC6CELr` | 7.4min | 短视频；多模态 embedding |
| BV1AC | `BV1ACbi6DEvC` | 10.9min | 短视频；DeepSeek Harness |
| BV1yb | `BV1ybHXzfEEu` | 28.16min | 长视频；ASR 325 句/85 passages |

### Holdout（只看结果，不参与调参）

| case | video | 时长 | 用途 |
|---|---|---:|---|
| BV13 | `BV13EHX64EaY` | 11.2min | 跨视频泛化 |
| BV1ix | `BV1ixpd6GENc` | 5.2min | 跨视频泛化 |

其余 `BV1B5`/`BV1eU`/`BV1qo`/`BV1zn` 后置；不要先扫全量 data。

### 请求编写规则

- 按视频实际内容写 `central_question`、`job_to_be_done`、`reader_before_state`、`desired_reader_outcome`、`required_information`、`forbidden_information`。
- request 不是大纲：`central_question`/`job_to_be_done` 描述读者问题/任务，不要列“形象/定位/互动/原则”这种节序；`required_information` 是覆盖约束，不是顺序。Planner 可以提出与 request 不同的角度，并记录 conflict。
- 先读 transcript/claims（或让 claim extract 先跑一次），再写 request；不要凭标题猜。
- 写完后冻结 `request_hash`；看到文章后不得改 request。
- 每个 case 一个 request 文件：`evals/writing/requests/<video_id>.json`。
- 模板：[request-template.json](request-template.json)。
- 已冻结 dev：`requests/BV17.json`、`requests/BV1AC.json`、`requests/BV1yb.json`；holdout BV13/BV1ix 待按实际内容补。
- 3 dev real run 已完成（`runs/_final/`，local）；brief 盲审实验见 `runs/_planner_experiment/`；**真人 reader test/A-B 未做**。

---

## 2. Profile 选择

默认 `full_text`（compiled edited text）；条件启用：

- `claim_lean`：`audit_level=claim|boundary|reuse` 或 `risk_level=high`，且 claims 可用；否则先 claim extract 或显式回退。
- `index_parts`：edited text 超 `context_budget_tokens` 或 segment 过多。
- `sectioned`：>30min/长文/多节，或 index_parts 仍超预算。
- `multi_source`/`tool_agent`：后置。

触发看实测 token/segment，不看固定分钟；记录 `plan.json`/`decisions.jsonl`；允许 `--profile` 覆盖。

---

## 3. Brief 盲审协议（模型/代理读者，不是真人 test；内部前置检查）

> 2026-11-03：这是内部前置检查，不是当前主评测；当前主评测是 §0 的 L3 LLM-as-Judge。

目的：在花 Writer/Visual 的钱之前，先检查 brief 的标题/主线/取重是否站得住。

- 1–2 个**干净上下文**读者；不看 skill/plan/current article/其他 case。
- Phase 1：只读 `editorial-brief-v1`（或实验 brief），回答：
  - 标题承诺什么？想不想读？哪个标题最 grounded/最 clickable？
  - spine 是调查/决策路径还是 topic list？core 有没有被某个 move 兑现？
  - 哪个 beat 像 filler/重叠？哪些锚点还不够具体？
- Phase 2：再读 source（`light_text` 或 source map + source），复评：
  - 最强素材是否用上？有没有 underuse/overweight？
  - title 是否兑现？speaker/claim type/relation 是否对？
  - 有没有事实错位（假设写成实测、同模态写成跨模态、把 A 的话给 B）？
- 记录 `brief_review.status`、reader 原始回答、chosen title、top risks；不把模型盲审写成真人 reader test。
- 通过标准不是“读者喜欢”，而是：title 有 payoff、core 被兑现、锚点正确、spine 顺序成立、边界清楚。

## 4. Reader test 协议（未来/可选；当前未做）

> 2026-11-03：这是未来真人 reader test 的协议，不是当前质量门；当前没有真人数据，不得写成 pass。

- **5+ 真实读者**；不允许模型/模拟读者冒充。
- 5 题：
  1. 这篇文章在回答什么问题？
  2. 用自己的话复述机制/步骤。
  3. 文章说证据覆盖/没覆盖什么？
  4. 一个具体事实/数字是什么？
  5. 与另一篇相比更喜欢哪篇，为什么？
- 盲读：不告知作者/skill/来源；A/B 随机顺序；记录原始回答。
- 个人数据只放 `runs/`；`evals/` 放匿名汇总/attestation。
- 结果标 `reader_test.status=pass|partial|fail|not_run`；`not_run` 不得写成 pass。

## 5. A/B 协议（未来/可选；当前用 L3 匿名 A/B）

> 2026-11-03：真人 A/B 未做；当前 A/B 是 LLM-as-Judge 的匿名 pair（同一视频两版），used for direction, not human evidence.

- baseline：同模型、同 evidence、通用 explainer prompt；或上一版 skill。
- 6 维：comprehension/accuracy/expression/structure/memory/willingness；1–5。
- 同读者、随机顺序、盲评；记录原始评分/偏好/理由。
- 至少 2 视频 × 2 文体再做通用结论；单 case 只作 case 结果。

---

## 6. 指标

| 维度 | 指标 |
|---|---|
| 质量 | central question/mechanism/boundary；title payoff；brief core cash；reader test；A/B |
| Brief | title promise/fulfilled_by；core cash；anchor correctness；spine sequence；cut/limits |
| 证据 | fact binding coverage/unsupported/outside_input；quote precision；timecode accuracy |
| 成本 | prompt/completion/reasoning/cached tokens；latency；calls；cache hit |
| 复用 | 第二文体 marginal tokens/latency；reused layers |
| 失败 | partial/failed/unknown；over_budget；coverage unreported |

---

## 7. 文件

```text
evals/writing/
  README.md
  request-template.json
  requests/
    BV17.json
    BV1AC.json
    BV1yb.json
    BV13.json        # holdout
    BV1ix.json       # holdout
  cases/
    <case_id>.json   # EvalCase
  protocols/
    reader_test.md
    ab_test.md
```

当前 LLM-as-Judge 产物：

```text
runs/_reader_test_2026-11-03/
  reader_pack/
    5个persona.md        # 用户标准，只读
    评价方法.md          # 用户标准，只读
  llm_judge/             # 第一轮 30 报告 + summary/problems/method_conflicts/manual_acceptance
  judge_v5/
    reader_pack/         # 匿名 A/B + 标准 copies，给 subagent
    _hidden_mapping.json # 30 报告完成后再读
    STARTUP_PROMPT.md    # 给新 session
```

运行产物（文章/审计/原始读者回答）放 `runs/<run_id>/`，不进 git。不要修改用户的两份标准文档；不要提前读 `_hidden_mapping.json`。
