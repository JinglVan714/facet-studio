"""Minimal ToolSpec / Registry / Executor.

The harness does not own domain facts.  Tools expose deterministic services
(evidence lookup, binding checks, rendering) with an explicit schema, a role
whitelist, a timeout and a real receipt.  Model calls remain provider calls;
they are not disguised as tools.

This module is intentionally small: it is the first real consumer of the
Harness contract, not a general plugin system.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any, Callable

from pydantic import BaseModel, Field

from ..core.hashing import canonical_json
from .trace import make_tool_call

Handler = Callable[[dict[str, Any]], dict[str, Any]]


class ToolError(RuntimeError):
    kind = "tool_error"


class ToolNotFound(ToolError):
    kind = "tool_not_found"


class ToolPermissionError(ToolError):
    kind = "tool_permission_denied"


class ToolValidationError(ToolError):
    kind = "tool_validation_error"


class ToolTimeout(ToolError):
    kind = "tool_timeout"


class ToolExecutionError(ToolError):
    kind = "tool_execution_error"


class ToolSpec(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    allowed_roles: list[str] = Field(default_factory=lambda: ["*"])
    source_policy: str = "video_native"
    side_effect: str = "read"  # read / write / external
    idempotency: str = "key"  # key / none
    timeout_s: float = 5.0
    cost_model: dict[str, Any] = Field(default_factory=dict)


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, Handler] = {}

    def register(self, spec: ToolSpec, handler: Handler) -> None:
        if spec.name in self._specs:
            raise ValueError(f"工具已注册: {spec.name}")
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def get(self, name: str) -> tuple[ToolSpec, Handler]:
        spec = self._specs.get(name)
        handler = self._handlers.get(name)
        if spec is None or handler is None:
            raise ToolNotFound(f"未知工具: {name}")
        return spec, handler

    def specs(self) -> list[ToolSpec]:
        return [self._specs[name] for name in sorted(self._specs)]

    def names(self) -> list[str]:
        return sorted(self._specs)


def _validate_type(name: str, value: Any, expected: str) -> None:
    checks = {
        "string": lambda item: isinstance(item, str),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
        "number": lambda item: isinstance(item, (int, float)),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
    }
    check = checks.get(expected)
    if check is not None and not check(value):
        raise ToolValidationError(
            f"工具参数 {name} 期望 {expected}，实际 {type(value).__name__}"
        )


def validate_arguments(spec: ToolSpec, arguments: dict[str, Any]) -> None:
    schema = spec.input_schema or {}
    for key in schema.get("required") or []:
        if key not in arguments:
            raise ToolValidationError(f"工具 {spec.name} 缺少参数: {key}")
    properties = schema.get("properties") or {}
    for key, value in arguments.items():
        prop = properties.get(key)
        if not isinstance(prop, dict):
            continue
        expected = prop.get("type")
        if expected:
            _validate_type(key, value, str(expected))


class ToolExecutor:
    """Execute registered tools with a real receipt.

    ``call_sink`` receives ToolCallRecord dicts; the pipeline wires it to
    ``tool_calls.jsonl``.  Results are cached per executor when the tool is
    idempotent.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        call_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.registry = registry
        self.call_sink = call_sink
        self._cache: dict[str, dict[str, Any]] = {}

    def execute(
        self,
        *,
        run_id: str,
        task_id: str,
        actor: str,
        tool_name: str,
        arguments: dict[str, Any],
        attempt: int = 1,
    ) -> dict[str, Any]:
        spec, handler = self.registry.get(tool_name)
        if "*" not in spec.allowed_roles and actor not in spec.allowed_roles:
            raise ToolPermissionError(
                f"角色 {actor} 无权调用工具 {tool_name}；允许 {spec.allowed_roles}"
            )
        validate_arguments(spec, arguments)
        cache_key = f"{tool_name}:{canonical_json(arguments)}"
        if spec.idempotency == "key" and cache_key in self._cache:
            cached = dict(self._cache[cache_key])
            cached["cached"] = True
            self._record(
                run_id=run_id,
                task_id=task_id,
                actor=actor,
                tool_name=tool_name,
                arguments=arguments,
                attempt=attempt,
                result=cached,
                latency_ms=0,
            )
            return cached

        started = time.perf_counter()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(handler, arguments)
                result = future.result(timeout=spec.timeout_s)
        except FutureTimeout as exc:
            latency = int((time.perf_counter() - started) * 1000)
            self._record(
                run_id=run_id,
                task_id=task_id,
                actor=actor,
                tool_name=tool_name,
                arguments=arguments,
                attempt=attempt,
                error="timeout",
                latency_ms=latency,
            )
            raise ToolTimeout(f"工具 {tool_name} 超时 ({spec.timeout_s}s)") from exc
        except Exception as exc:
            latency = int((time.perf_counter() - started) * 1000)
            self._record(
                run_id=run_id,
                task_id=task_id,
                actor=actor,
                tool_name=tool_name,
                arguments=arguments,
                attempt=attempt,
                error=f"{type(exc).__name__}: {exc}",
                latency_ms=latency,
            )
            if isinstance(exc, ToolError):
                raise
            raise ToolExecutionError(
                f"工具 {tool_name} 执行失败: {type(exc).__name__}: {exc}"
            ) from exc
        latency = int((time.perf_counter() - started) * 1000)
        if not isinstance(result, dict):
            raise ToolExecutionError(f"工具 {tool_name} 必须返回 dict")
        if spec.idempotency == "key":
            self._cache[cache_key] = dict(result)
        self._record(
            run_id=run_id,
            task_id=task_id,
            actor=actor,
            tool_name=tool_name,
            arguments=arguments,
            attempt=attempt,
            result=result,
            latency_ms=latency,
        )
        return result

    def _record(self, **kwargs: Any) -> None:
        if self.call_sink is None:
            return
        self.call_sink(make_tool_call(**kwargs))


def json_size(value: Any) -> int:
    """Small helper for tests and receipts."""
    return len(json.dumps(value, ensure_ascii=False))
