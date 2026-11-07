"""步骤注册表 —— **现在只是 `executor.py` 的薄转发，不再自己实现。**

## 为什么这里从"实现"变成了"转发"

本文件曾经有一份**完整独立的** 10 个步骤实现，与 `executor.py` 里的那份**逐一对不上**
（实测：`HANDLERS` 的 10 个 kind 全在，但**没有一个是同一个函数对象**）。
文件头还写着"这是两个执行器共用的唯一入口"——**注释在说谎**。

代价是实测出来的：

- 2026-10-16 把 `lmind l1` 与 `executor.py` 合并成同一份实现（`prepare_l1` + `extract_one_chunk`），
  并把计划的分片从时间窗改成契约分段（`c000…` → `seg1…seg8`）。
- **`lg_runner` 用的是本文件**，所以它的 `extract` 仍在查 `make_chunks` 的旧分片 id，
  于是 LangGraph 执行器上**每一步都失败**：`计划里的分片不存在：seg1`。
- 而手写执行器（走 `executor.py`）**全部成功**。**同一条命令，看你敲的是 `exec` 还是 `lg-run`。**

> **教训（已写进 spec §8.0d）：修一条分叉之前，先数清有几条。**
> 那次我以为只有"`lmind l1` vs 执行器"两条，实际是三条——`steps.py` 是暗的那一条，
> 因为它**不叫自己执行器**，而且**没人 import 它除了 lg_runner**。

保留本文件（而不是删掉、让 `lg_runner` 直接 import `executor`）的理由：外部可能有引用，
且 `execute_one` / `needs_approval` 是 LangGraph 侧的稳定接口名。**但实现只有一个。**
"""
from __future__ import annotations

from typing import Callable

from .executor import HANDLERS, needs_approval  # noqa: F401  —— 单一实现

StepResult = tuple[bool, str]

__all__ = ["StepResult", "HANDLERS", "needs_approval", "execute_one"]


def execute_one(step: dict, plan: dict) -> StepResult:
    """执行一步（幂等）。**两个执行器共用的唯一入口**——这次是真的。"""
    h: Callable[[dict, dict], StepResult] | None = HANDLERS.get(step["kind"])
    if h is None:
        return False, f"没有实现 {step['kind']} 的处理器"
    return h(step, plan)
