"""Minimal async OpenAI-compatible chat-completions client.

Why hand-rolled instead of the openai SDK: the SDK pulls in a lot of features we
don't use, and we want a hard dependency only on httpx. This client is small,
typed, retried, and trivially mockable in tests via `respx`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

# Cost estimates ($/1M tokens) — updated from public OpenAI pricing as of 2024-09.
# Off-list models fall back to a conservative default rather than zero, so cost
# tracking always emits a number callers can sanity-check.
_PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "o1-mini": (3.00, 12.00),
}
_DEFAULT_PRICE: tuple[float, float] = (1.00, 2.00)


@dataclass(slots=True, frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(slots=True, frozen=True)
class LLMResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    latency_ms: int
    model: str


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_p, out_p = _PRICES_USD_PER_MTOK.get(model, _DEFAULT_PRICE)
    return (prompt_tokens * in_p + completion_tokens * out_p) / 1_000_000


class LLMClient:
    """Thin async wrapper around POST /chat/completions, with retry + cost tracking."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_s: float = 60.0,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._client = client
        self._owns_client = client is None

    async def __aenter__(self) -> LLMClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout_s)
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int = 512,
        response_format: dict[str, str] | None = None,
    ) -> LLMResponse:
        if self._client is None:
            raise RuntimeError("LLMClient must be used as an async context manager")

        payload: dict[str, object] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._max_retries + 1),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
            retry=retry_if_exception_type(
                (httpx.TimeoutException, httpx.NetworkError, _RetryableHTTPError)
            ),
            reraise=True,
        ):
            with attempt:
                return await self._do_request(model, payload)
        raise RuntimeError("unreachable")  # pragma: no cover

    async def _do_request(self, model: str, payload: dict[str, object]) -> LLMResponse:
        assert self._client is not None
        timer = _Stopwatch.start()
        resp = await self._client.post(
            f"{self._base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if resp.status_code in (429, 500, 502, 503, 504):
            raise _RetryableHTTPError(resp.status_code, resp.text)
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        prompt_toks = int(usage.get("prompt_tokens", 0))
        completion_toks = int(usage.get("completion_tokens", 0))
        return LLMResponse(
            content=data["choices"][0]["message"]["content"],
            prompt_tokens=prompt_toks,
            completion_tokens=completion_toks,
            cost_usd=estimate_cost(model, prompt_toks, completion_toks),
            latency_ms=timer.elapsed_ms(),
            model=model,
        )


class _RetryableHTTPError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status = status


class _Stopwatch:
    __slots__ = ("_start",)

    def __init__(self, start: float):
        self._start = start

    @classmethod
    def start(cls) -> _Stopwatch:
        import time

        return cls(time.perf_counter())

    def elapsed_ms(self) -> int:
        import time

        return int((time.perf_counter() - self._start) * 1000)
