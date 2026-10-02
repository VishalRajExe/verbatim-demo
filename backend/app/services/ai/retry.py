"""LLM call retry policy (Rules §4.6).

Retry only on 429 / 500 / 503 and network-type errors, with exponential backoff
and jitter, honouring a ``Retry-After`` hint when present. Non-retryable errors
bubble up immediately. Time is injected so tests run instantly.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable, Iterable

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass
class LLMError(Exception):
    status: int | None = None
    message: str = "LLM request failed."
    retry_after: float | None = None

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"LLMError(status={self.status}): {self.message}"


def is_retryable(err: Exception) -> bool:
    if isinstance(err, LLMError):
        return err.status in RETRYABLE_STATUS or err.status is None
    return isinstance(err, (ConnectionError, TimeoutError))


def retry_call(
    fn: Callable[[], object],
    *,
    max_attempts: int = 4,
    base_delay: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
    rng: Callable[[], float] = random.random,
    retryable_statuses: Iterable[int] = RETRYABLE_STATUS,
) -> object:
    last: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - classified below
            last = exc
            retryable = (
                isinstance(exc, LLMError) and exc.status in set(retryable_statuses)
            ) or (not isinstance(exc, LLMError) and is_retryable(exc))
            if not retryable or attempt == max_attempts:
                raise
            delay = _backoff(attempt, base_delay, exc, rng)
            sleep(delay)
    if last:  # pragma: no cover - loop always returns or raises
        raise last
    raise LLMError(message="retry_call exhausted without a call")


def _backoff(attempt: int, base: float, exc: Exception, rng) -> float:
    if isinstance(exc, LLMError) and exc.retry_after:
        return float(exc.retry_after)
    exp = base * (2 ** (attempt - 1))
    jitter = rng() * base
    return exp + jitter
