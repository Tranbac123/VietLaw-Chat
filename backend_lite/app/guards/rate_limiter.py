"""VietLaw Limited Demo: bounded, in-process rate limiting primitives.

This is deliberately a ONE-PROCESS limiter, not a distributed production rate
limiter (see `DEPLOY_RAILWAY_CLOUDFLARE.md`'s "Known limitations"): state is
held in plain Python dicts guarded by a `threading.Lock`, resets on process
restart, and only produces correct aggregate limits when the backend runs as
exactly one replica -- which the limited-demo Railway configuration requires
for its SQLite volume anyway (see `railway.toml`).

Two independent primitives are provided:

  `FixedWindowRateLimiter` -- a per-key (client IP or conversation id)
  fixed-window counter (e.g. "at most N requests per rolling minute-window
  boundary"). Deterministic and side-effect-free apart from its own
  dict/lock: the caller supplies `now_fn`, so tests never need a real clock
  or a real sleep.

  `ConcurrencyLimiter` -- a bounded in-flight-request counter (a manual
  semaphore), so a caller can reject a request outright rather than queueing
  it indefinitely.

Both remove their own expired/idle entries so memory stays bounded even
under many distinct short-lived keys (e.g. many different client IPs that
each make only one request ever).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class RateLimitDecision:
    """Result of `FixedWindowRateLimiter.check`. `retry_after_seconds` is
    only meaningful when `allowed` is `False`."""

    allowed: bool
    retry_after_seconds: float = 0.0


@dataclass
class _Bucket:
    window_start: float
    count: int


class FixedWindowRateLimiter:
    """Deterministic per-key fixed-window counter.

    A key's window resets the first time it is checked after
    `window_seconds` have elapsed since that key's own window started --
    this is a fixed window, not a sliding one (a bounded, simple choice
    appropriate for a limited demo, not a production-grade token bucket).
    """

    def __init__(
        self,
        *,
        limit: int,
        window_seconds: float,
        now_fn,
        sweep_interval_seconds: float = 300.0,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self._limit = limit
        self._window_seconds = window_seconds
        self._now_fn = now_fn
        self._sweep_interval = sweep_interval_seconds
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._last_sweep = now_fn()

    def check(self, key: str) -> RateLimitDecision:
        """Record one attempt for `key` and report whether it is allowed.
        Every call (allowed or not) counts as an attempt against the
        window -- a caller that is being rejected must not be able to probe
        for free by retrying instantly."""

        now = self._now_fn()
        with self._lock:
            self._maybe_sweep(now)
            bucket = self._buckets.get(key)
            if bucket is None or (now - bucket.window_start) >= self._window_seconds:
                self._buckets[key] = _Bucket(window_start=now, count=1)
                return RateLimitDecision(allowed=True)
            if bucket.count < self._limit:
                bucket.count += 1
                return RateLimitDecision(allowed=True)
            retry_after = max(self._window_seconds - (now - bucket.window_start), 0.0)
            return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)

    def _maybe_sweep(self, now: float) -> None:
        if (now - self._last_sweep) < self._sweep_interval:
            return
        stale_before = now - (self._window_seconds * 2)
        stale_keys = [key for key, bucket in self._buckets.items() if bucket.window_start < stale_before]
        for key in stale_keys:
            del self._buckets[key]
        self._last_sweep = now

    def __len__(self) -> int:
        """Current tracked-key count -- exposed only for tests proving
        sweeping actually bounds memory."""

        with self._lock:
            return len(self._buckets)


class ConcurrencyLimiter:
    """A manual counting semaphore: `try_acquire()` never blocks -- it
    either reserves a slot and returns `True`, or reports the limit is
    already full and returns `False`. The caller MUST call `release()`
    exactly once for every successful `try_acquire()` (typically in a
    `try`/`finally`), or the slot leaks for the life of the process."""

    def __init__(self, *, limit: int) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        self._limit = limit
        self._count = 0
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        with self._lock:
            if self._count >= self._limit:
                return False
            self._count += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._count = max(0, self._count - 1)

    @property
    def in_flight(self) -> int:
        with self._lock:
            return self._count


__all__ = ["ConcurrencyLimiter", "FixedWindowRateLimiter", "RateLimitDecision"]
