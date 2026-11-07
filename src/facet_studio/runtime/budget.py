"""Run budget: calls and tokens, checked before/after every provider call."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


class BudgetExceeded(RuntimeError):
    def __init__(self, message: str):
        super().__init__(message)
        self.kind = "budget_exceeded"


@dataclass
class BudgetPolicy:
    max_calls: int = 32
    max_tokens: int = 400_000
    max_cost_usd: float | None = None


@dataclass
class BudgetState:
    policy: BudgetPolicy
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    _lock: threading.RLock = field(
        default_factory=threading.RLock, repr=False, compare=False
    )

    def before_call(self) -> None:
        # Reserve the attempt under the lock.  Parallel section drafts must not
        # all pass the check before any usage is recorded.
        with self._lock:
            if self.calls >= self.policy.max_calls:
                raise BudgetExceeded(
                    f"budget 用尽：calls={self.calls} >= {self.policy.max_calls}"
                )
            self.calls += 1

    def add_usage(self, usage: dict[str, Any]) -> None:
        # ``calls`` was reserved in before_call; this method only accumulates
        # tokens.  A failed call still counts as an attempt.
        with self._lock:
            self.prompt_tokens += int(usage.get("prompt_tokens", 0) or 0)
            self.completion_tokens += int(usage.get("completion_tokens", 0) or 0)
            self.total_tokens += int(usage.get("total_tokens", 0) or 0)
            self.reasoning_tokens += int(usage.get("reasoning_tokens", 0) or 0)
            if self.total_tokens > self.policy.max_tokens:
                raise BudgetExceeded(
                    f"budget 用尽：tokens={self.total_tokens} > {self.policy.max_tokens}"
                )

    def snapshot(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "policy": {
                "max_calls": self.policy.max_calls,
                "max_tokens": self.policy.max_tokens,
                "max_cost_usd": self.policy.max_cost_usd,
            },
        }
