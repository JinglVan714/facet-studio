"""Content-addressed LLM cache behavior, without a real provider."""

from __future__ import annotations

from types import SimpleNamespace

from lunograph.providers.llm import CachedLLM, LLMResponse, LLMUsage


class FakeLLM:
    model = "fake-model"
    provider = "fake"
    settings = SimpleNamespace(max_output_tokens=1024)

    def __init__(self) -> None:
        self.calls = 0

    def complete(
        self,
        *,
        stage: str,
        key: str,
        system: str,
        user: str,
        max_tokens: int | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            text=f"response {self.calls}",
            model=self.model,
            provider=self.provider,
            usage=LLMUsage(prompt_tokens=1, completion_tokens=2, total_tokens=3),
            latency_ms=7,
            finish_reason="stop",
        )


def _call(client, *, user: str = "same user") -> LLMResponse:
    return client.complete(
        stage="test_stage",
        key="test_key",
        system="system prompt",
        user=user,
        max_tokens=100,
        temperature=0.0,
    )


def test_cache_hit_does_not_call_inner(tmp_path) -> None:
    inner = FakeLLM()
    records: list[dict] = []
    client = CachedLLM(inner, tmp_path, call_sink=records.append)

    first = _call(client)
    second = _call(client)

    assert inner.calls == 1
    assert first.cached is False
    assert second.cached is True
    assert second.replayed is True
    assert second.text == first.text
    assert second.latency_ms == 0
    assert len(records) == 1
    assert records[0]["provider"] == "cache"
    assert records[0]["status"] == "succeeded"
    assert records[0]["replayed"] is True


def test_cache_miss_on_different_request(tmp_path) -> None:
    inner = FakeLLM()
    client = CachedLLM(inner, tmp_path)

    _call(client, user="user one")
    _call(client, user="user two")

    assert inner.calls == 2


def test_corrupt_cache_entry_falls_back_to_inner(tmp_path) -> None:
    inner = FakeLLM()
    client = CachedLLM(inner, tmp_path)

    _call(client)
    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1
    cache_files[0].write_text("not json", encoding="utf-8")

    response = _call(client)

    assert inner.calls == 2
    assert response.cached is False
