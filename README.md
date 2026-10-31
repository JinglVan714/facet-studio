# LunoGraph v3 — 证据驱动的视频理解与多形态写作

以不可变视频资料和可追溯证据为底座，把视频编译成**可复用、带上下文的证据**，再用**写作 Skill + 一次 Writer** 生成多种文体；引用/时间码/citation 由代码派生，人工发布门保留。

## v3 入口

1. [docs/v3/00-architecture.md](docs/v3/00-architecture.md)：v3 完整架构书（证据编译器、View、Skill、Writer、可选 Verifier、确定性校验/渲染、多文体、关键帧、JD、小号 Harness、开源复用）。
2. [docs/v3/00-architecture-self-check.md](docs/v3/00-architecture-self-check.md)：架构书自检清单与残余风险。
3. [docs/v3/README.md](docs/v3/README.md)：v3 文档索引。
4. [agent.md](agent.md)：新 session 入口与 v3 硬规则。

## 当前状态

- v3 架构书 + v2 冻结已完成；P0 原型（Skill / EvidencePack / one-call Writer）已跑通一次。
- BV1AC：385 units → 116 sentences → 32 passages → 43 claims → 40-claim pack → 1 次 Writer；claim extraction 31k + writer 38k = 69k tokens；reader 1,865 字、校验 complete。
- 尚未做真实 reader test/A-B，未跑第二视频；不按单篇调参。
- v2 已冻结为素材：本地磁盘 `docs/_frozen/v2-2026-10-31/`（不入 v3 git 分支）；只作参考，不是基线。
- v2 的 approved 案例/AB 结果仍是历史素材，不代表 v3 已实现或已验收。
- 下一步：第二视频验证 + reader test/轻量 A-B，再决定固化 P1。

## 设计要点

- **默认 1 次 Writer**；高风险才加 1 次可选 Verifier；不恢复多阶段 waterfall。
- **EvidencePack**：按请求/文体对证据做确定性投影；带上下文/反证/gap/帧候选；不拍平、不模型摘要。
- **多文体 = 多 Skill/View**：深度解析、讲义、社媒、企业知识、视频脚本、二创、生图提示词；不为每个文体加 body/validator/gate。
- **ASR 为主，关键帧为证**：在 ASR 关键节点附近挑帧；真实帧/文本实验/无演示明确；生成图只 editorial。
- **容量 advisory**：不做固定 length/focus 硬门；质量由 reader/专家/A-B 判断。

## 环境

```bash
cd "D:/秋招/个人作品/1023视频写作"
PYTHONPATH=src "D:/anaconda/envs/myagent/python.exe" -m pytest -q
```

- 解释器固定：`D:/anaconda/envs/myagent/python.exe`（Python 3.11.14）。
- `data/`、`参考素材/` 只读；`.env`、`data/`、`runs/`、`写作模板/`、封存目录不入 git。
- 当前阶段不写代码；代码/测试属于 v2 legacy material，v3 尚未开始实现。
