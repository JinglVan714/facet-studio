# Product v1 eval (P4)

> 独立开发评测，不进产品 UI；只读 run artifacts，不改文章、不改 run。
> 当前是 deterministic contract harness；LLM judge / 真人 reader test 未跑，`pass@1/pass^k` 不伪造。

## 数据

- `cases.json`：capability 6 cases（2 视频 × 3 形态；BV1ix 的 long/wechat 尚未生成，明确标 `not_run`）+ regression 3 cases。
- 每个 case 指向一个真实 `runs/product_v1/<run_id>`，检查：
  - run 状态 / 人工验收；
  - reader + 形态产物（WeChat 复制页、XHS 3:4 卡、PDF）；
  - 图数、缺图、正文长度、事实关键词；
  - 轨迹（P3 workflow stages；旧 run 的 planner trace 单独报告，不当作单 writer 失败）；
  - tokens / latency。

## 运行

```bash
PYTHONPATH=src PYTHONUTF8=1 python -m facet_studio.evals.product \
  --cases evals/product_v1/cases.json \
  --out evals/product_v1/reports
```

输出 `report-<timestamp>.json` + `.md`。报告里的 `deterministic_pass_rate` 只是产品合同通过率，不是 task success；`pass_at_1` / `pass_at_k` 为 null，直到有 judged trials。

## 当前基线（2026-11-07）

- 7/9 cases 有 artifact；2 个 capability missing（BV1ix long/wechat）。
- deterministic pass: 7/7 run cases；manual acceptance: 7/7。
- planner trace: 4/7（旧 P1 产物缺 planner usage，新 P3 workflow 有完整 stages）。
- p50/p95 latency：50,970 / 58,757 ms；tokens total 138,609。

## 后续（P4 收口）

- 生成 BV1ix long/wechat，补满 6 capability cases。
- 窄 rubric judge（每形态一套）+ 用户标注 6–12 个产物做 judge-human 校准；2 次聚合，不做 30 judge。协议见 [judge-protocol.md](judge-protocol.md)。
- trajectory 扩展：required tools、loop、step budget、失败恢复、审批门。
- regression gate：固定 cases + snapshot/replay；失败样本进 regression set。
- 不把 deterministic pass 当 reader quality；人工验收仍是唯一发布门。
