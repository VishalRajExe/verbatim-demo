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


# Substrings that mark a provider "too many requests / out of quota" failure
# across the phrasings Google (and other vendors) use. Matched case-insensitively.
_QUOTA_HINTS = (
    "resource_exhausted",
    "resource exhausted",
    "quota",
    "rate limit",
    "ratelimit",
    "too many requests",
)


def friendly_message(exc: LLMError) -> str:
    """A short, user-safe description of an LLM failure.

    The raw provider payload (``exc.message``) is deliberately NOT returned: it
    is unreadable to end users and can leak internal request/limit details. The
    full error is still logged server-side where it belongs. This keeps the
    honest-status principle (tell the user it failed and why, in plain terms)
    without fabricating a result or exposing internals."""
    low = (exc.message or "").lower()
    if exc.status == 429 or any(h in low for h in _QUOTA_HINTS):
        return (
            "The AI service is rate-limited right now — its daily request quota "
            "has been reached. Please try again in a little while."
        )
    if exc.status in (401, 403):
        return "The AI service is unavailable right now. Please try again later."
    if exc.status in (500, 502, 503, 504) or exc.status is None:
        return "The AI service is temporarily unavailable. Please try again."
    return "The AI service could not complete this request. Please try again."


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
