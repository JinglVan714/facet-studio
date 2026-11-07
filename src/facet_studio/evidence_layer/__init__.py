"""LectureMind —— 视频 → 可回链的知识底稿（证据层）。

当前可见实现范围：层 0/1/1.5（取流/抽帧/转录/单元化/断言/关系/冲突/Evidence MCP）。
writing 层已归档，按 `docs/REFACTOR-PLAN.md` 重建；不在这里导入。
"""

__all__ = ["constants", "acquire", "audio", "frames", "manifest", "pipeline"]
