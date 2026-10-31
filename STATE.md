# STATE.md — 当前代码 / 分支 / 测试状态

> 2026-10-31。架构见 [architecture.md](architecture.md)，规则见 [AGENTS.md](AGENTS.md)，任务见 [HANDOFF.md](HANDOFF.md)。

## 1. Git / 仓库

- 当前分支：`v3`（orphan branch，只含 v3 文档/代码/skill）。
- 工作树：应保持 clean；不 push。
- 旧分支：`rebuild-v2`、`main` 等仍存在，只作历史；不从中恢复写作链。
- 旧架构/旧 AB：`_archive/_blocked/video-writing-product-architecture/`、`_archive/_blocked/AB/`；被 `.gitignore` 屏蔽。
- v2 冻结素材：`docs/_frozen/v2-2026-10-31/`；本地只读，不在 v3 git。

## 2. 代码结构

| 模块 | 作用 |
|---|---|
| `src/lunograph/core`、`evidence`、`knowledge`、`providers`、`runtime` | substrate（ASR units、snapshot、证据、provider、runtime） |
| `src/lunograph/writing_v3/transcript.py` | ASR units → sentences → passages；确定性；写 receipt |
| `src/lunograph/writing_v3/claim_extract.py` | passages → 写作级 claims（1 次模型调用）；校验 quote/IDs、去重 |
| `src/lunograph/writing_v3/evidence_pack.py` | snapshot → 原始 EvidencePack（早期路径） |
| `src/lunograph/writing_v3/pack_from_claims.py` | claims + passages → coverage-aware EvidencePack |
| `src/lunograph/writing_v3/one_call_writer.py` | pack + skill + request → reader；校验 span/quote/数字/审计语言；渲染与拷贝素材 |
| `src/lunograph/writing_v3/trace.py` | `trace.jsonl` + `stage_receipts/*.json`（路径、sha256、字节数、counts、decisions） |
| `skills/writing/reader_first_explainer/` | 当前唯一写作 skill（SKILL.md / examples.md / manifest.json / SOURCES.md） |

## 3. 测试

- 命令：`PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m pytest -q`
- 最近结果：**304 passed**；全部属于 `tests/writing_v2/`（旧链路测试）。
- **v3 没有自动化测试**；`writing_v3/` 目前靠 P0 运行 + `trace`/`stage_receipts` + `--validate-only` 验证。
- `pyproject.toml` 的 `testpaths = ["tests"]`，因此 v3 改动不会被现有测试覆盖。

## 4. P0 样本

| 样本 | 时长 | units → sentences → passages | claims → pack | pack chars | Writer tokens | reader | 校验 |
|---|---:|---|---|---|---:|---:|---|
| BV1AC | 656s | 385 → 116 → 32 | 43 → 40 | 47,850 | 38,071 | 1,865 字 | complete |
| BV17 | 未记录 | 185 → 53 → 16 | 31 → 28 | 30,556 | 33,583 | 1,497 字 | complete |

- claim extraction：BV1AC 31,277 tokens；BV17 20,239 tokens。
- 两样本总调用均为 2 次（claim extraction + Writer）。
- 样例与 trace：`handoffs/2026-10-31/examples/`。
- `BV1AC_BV17_advisory_blind_read.json` 是模型冷读，**不是真实 reader test/A-B**，不能当验收。

## 5. 能力边界

已具备：单视频 → 证据 → reader-first 文章的端到端原型；失败/partial 状态可见；quote/span/ID 可审计。`reader_first_explainer` 仅为 v0.1 provisional。

未具备：真实读者测试/A-B；第二文体 skill；Verifier；v3 自动化测试；多视频/多源；publish 工作流；图表/生成图方案。

## 6. 输入与屏蔽

- 有效只读：`data/`（9 个视频，约 283MB；结构待用户提供；`data/cookies/` 不读）、`参考素材/skills/`（17 个参考仓库，约 73MB）、`C:/Users/30279/.claude/skills/bilibili-render-pdf`（约 33KB）。
- git 可见索引：[REFERENCES.md](REFERENCES.md)；完整 `data/`、`参考素材/skills/` 本地只读、不入库。
- 不读：`_archive/`、旧 run、旧 audit/reader.md，除非用户明确要求。
- 环境：Python `D:/anaconda/envs/myagent/python.exe`（3.11.14）；`PYTHONPATH=src`。
