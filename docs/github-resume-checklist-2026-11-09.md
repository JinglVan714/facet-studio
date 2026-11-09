# GitHub / 简历发布清单（2026-11-09）

> 目标不是“把仓库推上去”，而是让陌生人 clone 后能看懂、跑测试、看到一份可验证的产物，并且简历上的每句话都能在仓库/报告里找到证据。
> 状态：`done` / `missing` / `risky` / `decision`。`decision` 需要用户拍板，不要替他选。

## 1. 公开仓库前必须做（P0）

| 项 | 状态 | 事实 | 动作 |
|---|---|---|---|
| LICENSE | missing | 根目录没有 `LICENSE`；LibreChat 是外部 clone（MIT），Pandoc/Tectonic/卡片库各有 license | 用户选 own-code license（MIT/Apache-2.0/AGPL）；补 `THIRD_PARTY_NOTICES.md`；不要把外部 clone 当自己的代码 |
| git remote / 默认分支 | missing | `git remote -v` 为空；产品代码在未推送的 `writing-rebuild`，`main` 还停在旧 P2；`legacy-broken-baseline` 等历史分支/tag 会一起公开 | 建远端后 push 当前分支、设默认分支；归档/改名 legacy refs；确认公开范围 |
| 工作树/证据提交 | risky | 本轮 docs/runtime evidence/checklist、最新 P4 reports 和代码修复需要提交；README 已链接这些文件 | 提交前逐项 review；保证 GitHub 上无 404；不要把内部 checklist 当公开首页 |
| 可公开的 demo 产物 | missing | `runs/` 全被 gitignore；README 里的 run 链接只在本机存在 | 加 `examples/demo/`：一份不含第三方视频画面的合成内容稿 + reader 截图/HTML + run_meta 摘要；或明确“demo 仅本地” |
| P4 复现数据 | risky | P4 依赖本地 `runs/`；公开仓库没有 run artifacts，clone 后跑不了 10 cases | 加一个最小 fixture case（合成内容稿 + reader + run_meta），让 `--gate` 可复现；其余真实 run 只作本地证据 |
| 干净 clone 测试 | done（2026-11-09 修复后） | `git archive HEAD` 解压后 `315 passed`；本地全量 `619 passed`，差额是 gitignored 的 `tests/writing_v2/` 旧测试 | README/STATE 只写“clean clone 315”；本地 619 要注明含未发布 legacy tests |
| 行尾可移植性 | done | skill manifest hash 原来对 CRLF 敏感，Windows clean clone 会挂；已改为 hash 前 CRLF→LF，并加测试 | 保持；可再加 `.gitattributes` 防回归 |
| secrets / cookies | done | `.env`、`data/`、`runs/`、`vendor/` 均 gitignore；`git rev-list --all` 的 sk-/API key/cookie 扫描无命中 | 发布前再跑 gitleaks/trufflehog；绝不提交 `.env`/cookies/data/runs/vendor |
| 第三方图片/视频权利 | risky | `deliverables/writing-skill/` 含 B 站视频截帧（58 files / 5.8MB）；README 已声明不是当前默认输出，但仍在仓库 | 公开前删掉/替换成可公开素材，或在 `deliverables/README` 明确版权与不授权；更稳妥是不把视频帧放进公开 repo |
| LibreChat 外部依赖 | risky | 产品壳不 vendored；需要外部 clone + `client-ui.patch` + `librechat.yaml.example` + Mongo 内存版 | 提供 `scripts/bootstrap_librechat` 或一份“10 分钟跑起来”文档；在 clean clone 上实测一次 |
| 根 README 定位 | risky | README 信息量很大，但“30 秒看懂做什么 / 证据在哪 / 怎么跑”不够前置 | 重排顶部：一句话、3 个能力、1 张架构图、1 个 demo 链接、测试/P4 命令、Known limitations |

## 2. 简历投递前应该做（P1）

| 项 | 状态 | 动作 |
|---|---|---|
| 一页项目卡 | missing | 3–5 条 bullet：问题、架构、可观测/harness、结果数字、边界；只引用 `docs/runtime-evidence-2026-11-09.md` 的数字，不写 44.6s 当端到端 |
| 3 分钟 demo | risky | 聊天 → 视频 → 后台 run → 消息级运行卡 → 右侧预览 → 运行数据 → 人工验收；需要录屏/GIF，不能只给本地 URL |
| 架构图/截图 | missing | 一张 Mermaid/PNG：LibreChat → MCP → LangGraph → writing_v4 → reader/XHS/PDF；加单卡、右侧抽屉、/runs、Trace 截图 |
| CI | missing | `.github/workflows/ci.yml`：clean clone 上 `pytest` + `ruff`/typecheck（如可）；P4 需要 fixture 后再接；不要要求 API key |
| 依赖可复现 | risky | `pyproject.toml` 的 langgraph 1.2/checkpoint 3.1 与 `requirements.txt` 的 1.0.5/3.0.3 冲突；pyproject 缺 av/dashscope/yt-dlp 等证据层依赖；requirements 提示 Python 3.13 不可装 | 统一依赖来源；钉 Python 3.11/3.12；在干净 venv 跑 `pip install -e .` + 证据层 extras |
| 发布检查 | missing | 新 tag + release notes + 截图；确认 `git status` 干净、无个人绝对路径（D:/秋招、C:/Users/...）/API key |
| .gitattributes / .claude | done | 已加 `* text=auto` + `skills/** eol=lf`；`.claude/` 已 gitignore | 保持；发布前确认没有 `git status` 噪音 |
| 作品与评测分开 | done | `runs/` 不入库；P4 报告入库；不要在 README 把 P4 当 writing quality |

## 3. 简历上可以写 / 不要写

### 可以写（有仓库或报告证据）

- LangGraph 工作流：`intake → plan → approval → write → typeset → review`，SQLite checkpoint + interrupt；端到端默认直写，最终人工验收。
- MCP 工具层 13 tools；LibreChat 聊天壳；消息级运行卡 + 右侧预览；不把原始工具 JSON 暴露给用户。
- Run-level trace：stage / LLM call / tool span / decision / tokens / latency；看板 p50/p95、error、checks、grounding candidates。
- P4 harness：10 cases / 9 unique runs，contract 10/10、trajectory 30/30、error 0；人工验收单独统计，不伪造 pass@k。
- 视觉审计：关键帧逐帧判定；0 通过时降级为文字封面/不用截图；SVG 只保留 flow/tree/timeline。

### 不要写

- 真实用户数、生产 QPS、线上 A/B、留存/转化。
- “幻觉率 X%”或 “writing quality 分数”；grounding 只是 candidate，不是 adjudicated rate。
- pass@1 / pass@k；没有 judged trials。
- Langfuse/OTel 生产部署；本地只有 JSONL + 自建看板。
- multi-tenant 鉴权、RBAC、K8s、真实 Mongo 生产集群。
- “多 Agent 协作”说成 supervisor/worker 全形态；实际是 planner + 单 writer，故意没有 editor/checker。
- 2026 “Harness engineering（ETCLOVG）”全层实现；这里只有 deterministic eval harness + trace，不覆盖 Execution/Governance 等完整七层。

## 4. 发布前最后一次验证

```bash
# 1) clean clone / archive
git archive HEAD | tar -x -C /tmp/facet_clean
cd /tmp/facet_clean
PYTHONPATH=src PYTHONUTF8=1 python -m pytest tests

# 2) 本地全量（含 gitignored legacy tests，数字要注明）
cd <project>
PYTHONPATH=src PYTHONUTF8=1 python -m pytest tests

# 3) harness（需要本地 runs/；公开仓库需 fixture 后才能复现）
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.product \
  --cases evals/product_v1/cases.json --out evals/product_v1/reports --gate
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.grounding \
  --cases evals/product_v1/cases.json --out evals/product_v1/reports

# 4) secret scan
git grep -nE 'sk-[A-Za-z0-9]{16,}|DASHSCOPE_API_KEY=[^ ]+|DEEPSEEK_API_KEY=[^ ]+' $(git rev-list --all) -- . ':!*.example' | head
```

## 5. 建议的收尾顺序

1. 用户拍板 LICENSE 和是否公开 `deliverables/` 视频帧。
2. 做 `examples/demo` + README 顶部重排 + 架构图。
3. clean clone 跑 315 tests；补 CI（只跑不依赖 API 的部分）。
4. 录 3 分钟 demo；截图/报告链接放进 README。
5. 最后再写简历 bullet；每个数字引用 [runtime-evidence-2026-11-09.md](runtime-evidence-2026-11-09.md)。
