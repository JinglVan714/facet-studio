"""LLM provider boundary.

The rest of the system knows only ``complete(stage, key, system, user, ...)``.
Keeping provider details here means domain objects never import an SDK type,
and replay can substitute recorded responses without touching the pipeline.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..core.config import Settings
from ..core.hashing import semantic_hash, utc_now_iso


class ProviderError(RuntimeError):
    kind = "provider_error"

    def __init__(self, kind: str, message: str, *, raw: str = ""):
        super().__init__(message)
        self.kind = kind
        self.raw = raw


class ProviderUnavailable(ProviderError):
    def __init__(self, message: str):
        super().__init__("provider_unavailable", message)


class ProviderOutcomeUnknown(ProviderError):
    def __init__(self, message: str):
        super().__init__("provider_outcome_unknown", message)


class ReplayMiss(ProviderError):
    def __init__(self, message: str):
        super().__init__("replay_missing_call", message)


class BudgetExceeded(ProviderError):
    def __init__(self, message: str):
        super().__init__("budget_exceeded", message)


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    cached_tokens: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cached_tokens": self.cached_tokens,
        }


@dataclass(frozen=True)
class ImageInput:
    """One image content part for a VLM call.

    ``data`` stays out of artifacts; only its SHA-256 and name are recorded.
    """

    data: bytes
    media_type: str = "image/jpeg"
    name: str = ""

    def hash(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.media_type.encode("utf-8"))
        digest.update(b"\0")
        digest.update(self.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(self.data)
        return digest.hexdigest()


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    usage: LLMUsage
    latency_ms: int
    finish_reason: str | None = None
    provider_response_id: str | None = None
    replayed: bool = False
    cached: bool = False


@dataclass
class LLMCallRecord:
    call_id: str
    stage: str
    key: str
    input_hash: str
    model: str
    provider: str
    system_hash: str
    user_hash: str
    max_tokens: int
    temperature: float
    status: str
    raw_response: str
    finish_reason: str | None
    usage: dict[str, int]
    latency_ms: int
    image_hashes: list[str] = field(default_factory=list)
    error: str | None = None
    error_kind: str | None = None
    replayed: bool = False
    created_at: str = field(default_factory=utc_now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "stage": self.stage,
            "key": self.key,
            "input_hash": self.input_hash,
            "model": self.model,
            "provider": self.provider,
            "system_hash": self.system_hash,
            "user_hash": self.user_hash,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "status": self.status,
            "raw_response": self.raw_response,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
            "image_hashes": self.image_hashes,
            "error": self.error,
            "error_kind": self.error_kind,
            "replayed": self.replayed,
            "created_at": self.created_at,
        }


class LLMClient(Protocol):
    model: str
    provider: str

    def complete(
        self,
        *,
        stage: str,
        key: str,
        system: str,
        user: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
        images: list[ImageInput] | None = None,
    ) -> LLMResponse: ...


def request_identity(
    *,
    model: str,
    system: str,
    user: str,
    max_tokens: int,
    temperature: float,
    images: list[ImageInput] | None = None,
) -> tuple[str, str, str]:
    system_hash = semantic_hash({"text": system}, drop_volatile=False)
    user_hash = semantic_hash({"text": user}, drop_volatile=False)
    image_hashes = [image.hash() for image in (images or [])]
    input_hash = semantic_hash(
        {
            "model": model,
            "system_hash": system_hash,
            "user_hash": user_hash,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "image_hashes": image_hashes,
        },
        drop_volatile=False,
    )
    return input_hash, system_hash, user_hash


class _BudgetMixin:
    def __init__(self, budget: Any | None = None):
        self.budget = budget

    def _before_call(self) -> None:
        if self.budget is not None:
            self.budget.before_call()

    def _after_call(self, usage: LLMUsage) -> None:
        if self.budget is not None:
            self.budget.add_usage(usage.as_dict())


class DeepSeekLLM(_BudgetMixin):
    """OpenAI-compatible DeepSeek client with explicit failure semantics."""

    provider = "deepseek"

    def __init__(
        self,
        settings: Settings,
        *,
        budget: Any | None = None,
        call_sink: Any | None = None,
    ):
        super().__init__(budget)
        self.settings = settings
        self.model = settings.model or "unknown"
        self.call_sink = call_sink
        self._client = None
        if settings.provider_configured:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=settings.api_key,
                base_url=settings.base_url or None,
                timeout=settings.timeout_s,
                max_retries=0,
            )

    def complete(
        self,
        *,
        stage: str,
        key: str,
        system: str,
        user: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
        images: list[ImageInput] | None = None,
    ) -> LLMResponse:
        if self._client is None:
            raise ProviderUnavailable("未配置 DEEPSEEK_API_KEY / DEEPSEEK_MODEL")
        max_tokens = max_tokens or self.settings.max_output_tokens
        input_hash, system_hash, user_hash = request_identity(
            model=self.model,
            system=system,
            user=user,
            max_tokens=max_tokens,
            temperature=temperature,
            images=images,
        )
        image_hashes = [image.hash() for image in (images or [])]
        self._before_call()
        started = time.perf_counter()
        response_id: str | None = None
        raw = ""
        finish_reason: str | None = None
        usage = LLMUsage()
        try:
            user_content: Any = user
            if images:
                user_content = [{"type": "text", "text": user}]
                for image in images:
                    encoded = base64.b64encode(image.data).decode("ascii")
                    user_content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": (
                                    f"data:{image.media_type};base64,{encoded}"
                                )
                            },
                        }
                    )
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            response_id = getattr(response, "id", None)
            choice = response.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)
            raw = choice.message.content or ""
            usage = _usage_from_response(response)
            latency_ms = int((time.perf_counter() - started) * 1000)
            if not raw.strip():
                kind = "provider_output_empty"
                detail = (
                    f"模型返回空内容（finish_reason={finish_reason}）。"
                    "如果 finish_reason=length，说明 token 预算被 reasoning 消耗；"
                    "请提高 FACET_STUDIO_MAX_OUTPUT_TOKENS。"
                )
                self._after_call(usage)
                self._record(
                    stage, key, input_hash, system_hash, user_hash, max_tokens,
                    temperature, "failed", raw, finish_reason, usage, latency_ms,
                    detail, kind, False, image_hashes,
                )
                raise ProviderError(kind, detail, raw=raw)
            self._after_call(usage)
            self._record(
                stage, key, input_hash, system_hash, user_hash, max_tokens,
                temperature, "succeeded", raw, finish_reason, usage, latency_ms,
                None, None, False, image_hashes,
            )
            return LLMResponse(
                text=raw,
                model=self.model,
                provider=self.provider,
                usage=usage,
                latency_ms=latency_ms,
                finish_reason=finish_reason,
                provider_response_id=response_id,
            )
        except ProviderError:
            raise
        except Exception as exc:  # network / HTTP / SDK failure
            latency_ms = int((time.perf_counter() - started) * 1000)
            message = f"{type(exc).__name__}: {exc}"
            self._record(
                stage, key, input_hash, system_hash, user_hash, max_tokens,
                temperature, "failed", raw, finish_reason, usage, latency_ms,
                message, "provider_outcome_unknown", False, image_hashes,
            )
            # 不自动重放未知结果；交由调用方决定是否新 run。
            raise ProviderOutcomeUnknown(
                f"模型调用结果未知（不自动重试）：{message}"
            ) from exc

    def _record(
        self,
        stage: str,
        key: str,
        input_hash: str,
        system_hash: str,
        user_hash: str,
        max_tokens: int,
        temperature: float,
        status: str,
        raw: str,
        finish_reason: str | None,
        usage: LLMUsage,
        latency_ms: int,
        error: str | None,
        error_kind: str | None,
        replayed: bool,
        image_hashes: list[str] | None = None,
    ) -> None:
        record = LLMCallRecord(
            call_id=f"call_{semantic_hash({'stage': stage, 'key': key, 'h': input_hash, 't': utc_now_iso()}, drop_volatile=False)[:16]}",
            stage=stage,
            key=key,
            input_hash=input_hash,
            model=self.model,
            provider=self.provider,
            system_hash=system_hash,
            user_hash=user_hash,
            max_tokens=max_tokens,
            temperature=temperature,
            status=status,
            raw_response=raw,
            finish_reason=finish_reason,
            usage=usage.as_dict(),
            latency_ms=latency_ms,
            image_hashes=list(image_hashes or []),
            error=error,
            error_kind=error_kind,
            replayed=replayed,
        )
        if self.call_sink is not None:
            self.call_sink(record.as_dict())


class ReplayLLM(_BudgetMixin):
    """Replay recorded successful responses by exact request identity."""

    provider = "replay"

    def __init__(
        self,
        records: list[dict[str, Any]],
        *,
        model: str | None = None,
        default_max_tokens: int | None = None,
        budget: Any | None = None,
        call_sink: Any | None = None,
    ):
        super().__init__(budget)
        self.model = model or (records[0].get("model") if records else "replay")
        self.default_max_tokens = default_max_tokens or 65536
        self.call_sink = call_sink
        self._index: dict[tuple[str, str, str], dict[str, Any]] = {}
        for record in records:
            if record.get("status") == "succeeded":
                self._index[
                    (record["stage"], record["key"], record["input_hash"])
                ] = record

    def complete(
        self,
        *,
        stage: str,
        key: str,
        system: str,
        user: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
        images: list[ImageInput] | None = None,
    ) -> LLMResponse:
        max_tokens = max_tokens or self.default_max_tokens
        self._before_call()
        input_hash, system_hash, user_hash = request_identity(
            model=self.model,
            system=system,
            user=user,
            max_tokens=max_tokens,
            temperature=temperature,
            images=images,
        )
        record = self._index.get((stage, key, input_hash))
        if record is None:
            raise ReplayMiss(
                f"replay 缺少匹配调用: stage={stage} key={key} input_hash={input_hash[:12]}"
            )
        usage = LLMUsage(**{k: int(v or 0) for k, v in record.get("usage", {}).items()})
        self._after_call(usage)
        replayed = LLMCallRecord(
            call_id=f"replay_{semantic_hash({'s': stage, 'k': key, 'h': input_hash}, drop_volatile=False)[:16]}",
            stage=stage,
            key=key,
            input_hash=input_hash,
            model=self.model,
            provider=self.provider,
            system_hash=system_hash,
            user_hash=user_hash,
            max_tokens=max_tokens,
            temperature=temperature,
            status="succeeded",
            raw_response=record.get("raw_response", ""),
            finish_reason=record.get("finish_reason"),
            usage=usage.as_dict(),
            latency_ms=0,
            image_hashes=[image.hash() for image in (images or [])],
            replayed=True,
        )
        if self.call_sink is not None:
            self.call_sink(replayed.as_dict())
        return LLMResponse(
            text=record.get("raw_response", ""),
            model=self.model,
            provider=self.provider,
            usage=usage,
            latency_ms=0,
            finish_reason=record.get("finish_reason"),
            provider_response_id=record.get("call_id"),
            replayed=True,
        )


class CachedLLM:
    """Content-addressed cache around another LLM client.

    The key is the exact provider request identity (model + system + user +
    max_tokens + temperature).  A hit does not call the inner provider; it
    records a replay-style call row and returns the cached response.  Corrupt
    cache entries fall back to a real call.
    """

    provider = "cache"

    def __init__(self, inner: Any, cache_dir: Path, *, call_sink: Any | None = None):
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.model = getattr(inner, "model", "unknown")
        self.call_sink = call_sink

    def complete(
        self,
        *,
        stage: str,
        key: str,
        system: str,
        user: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
        images: list[ImageInput] | None = None,
    ) -> LLMResponse:
        settings = getattr(self.inner, "settings", None)
        resolved_max_tokens = max_tokens or getattr(
            settings, "max_output_tokens", 65536
        )
        image_hashes = [image.hash() for image in (images or [])]
        input_hash, system_hash, user_hash = request_identity(
            model=self.model,
            system=system,
            user=user,
            max_tokens=resolved_max_tokens,
            temperature=temperature,
            images=images,
        )
        cache_path = self.cache_dir / f"{input_hash}.json"
        if cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding="utf-8"))
                usage = LLMUsage(
                    **{
                        k: int(v or 0)
                        for k, v in payload.get("usage", {}).items()
                    }
                )
                record = LLMCallRecord(
                    call_id=(
                        "cache_"
                        + semantic_hash(
                            {
                                "stage": stage,
                                "key": key,
                                "h": input_hash,
                                "t": utc_now_iso(),
                            },
                            drop_volatile=False,
                        )[:16]
                    ),
                    stage=stage,
                    key=key,
                    input_hash=input_hash,
                    model=payload.get("model", self.model),
                    provider="cache",
                    system_hash=system_hash,
                    user_hash=user_hash,
                    max_tokens=resolved_max_tokens,
                    temperature=temperature,
                    status="succeeded",
                    raw_response=payload.get("text", ""),
                    finish_reason=payload.get("finish_reason"),
                    usage=usage.as_dict(),
                    latency_ms=0,
                    image_hashes=image_hashes,
                    replayed=True,
                )
                if self.call_sink is not None:
                    self.call_sink(record.as_dict())
                return LLMResponse(
                    text=payload.get("text", ""),
                    model=payload.get("model", self.model),
                    provider="cache",
                    usage=usage,
                    latency_ms=0,
                    finish_reason=payload.get("finish_reason"),
                    provider_response_id=payload.get("provider_response_id"),
                    replayed=True,
                    cached=True,
                )
            except (OSError, ValueError, TypeError):
                # Corrupt cache entry: fall through to a real call.
                pass

        inner_kwargs: dict[str, Any] = {
            "stage": stage,
            "key": key,
            "system": system,
            "user": user,
            "max_tokens": resolved_max_tokens,
            "temperature": temperature,
        }
        if images:
            inner_kwargs["images"] = images
        response = self.inner.complete(**inner_kwargs)
        if response.text.strip():
            payload = {
                "text": response.text,
                "model": response.model,
                "provider": response.provider,
                "usage": response.usage.as_dict(),
                "finish_reason": response.finish_reason,
                "provider_response_id": response.provider_response_id,
                "image_hashes": image_hashes,
                "created_at": utc_now_iso(),
            }
            tmp_path = cache_path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            tmp_path.replace(cache_path)
        return response


def _usage_from_response(response: Any) -> LLMUsage:
    usage = getattr(response, "usage", None)
    if usage is None:
        return LLMUsage()
    completion_details = getattr(usage, "completion_tokens_details", None)
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    return LLMUsage(
        prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
        completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        total_tokens=int(getattr(usage, "total_tokens", 0) or 0),
        reasoning_tokens=int(getattr(completion_details, "reasoning_tokens", 0) or 0)
        if completion_details
        else 0,
        cached_tokens=int(getattr(prompt_details, "cached_tokens", 0) or 0)
        if prompt_details
        else 0,
    )
