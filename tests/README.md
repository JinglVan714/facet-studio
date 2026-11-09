# tests

公开仓库的测试覆盖：MCP server / workflow / typesetting / PDF / XHS cards /
product eval / grounding / ingest / visual audit 等。运行：

```bash
PYTHONPATH=src PYTHONUTF8=1 python -m pytest tests -q
```

测试不依赖 `data/`、`runs/` 或 API key；P4 的合成 fixture 在
`evals/product_v1/fixtures/`。

本地全量测试可能包含 gitignored 的 `tests/writing_v2/` 旧测试；它不属于公开
仓库的测试面，也不代表当前实现。
