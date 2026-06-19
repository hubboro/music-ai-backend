import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse


def positive_int_env(name, default):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class LimitRule:
    key: str
    limit: int
    window_seconds: int


@dataclass(frozen=True)
class LimitDecision:
    allowed: bool
    retry_after: int = 0


class SlidingWindowRateLimiter:
    """Small in-memory limiter for the app's single-process Render service."""

    def __init__(self, clock=None):
        self._clock = clock or time.monotonic
        self._events = defaultdict(deque)
        self._lock = Lock()

    def check(self, rules):
        now = self._clock()
        with self._lock:
            retry_after = 0
            prepared = []

            for rule in rules:
                events = self._events[rule.key]
                cutoff = now - rule.window_seconds
                while events and events[0] <= cutoff:
                    events.popleft()

                prepared.append((rule, events))
                if len(events) >= rule.limit:
                    retry_after = max(
                        retry_after,
                        max(1, int(events[0] + rule.window_seconds - now) + 1),
                    )

            if retry_after:
                return LimitDecision(allowed=False, retry_after=retry_after)

            for _, events in prepared:
                events.append(now)

            return LimitDecision(allowed=True)


limiter = SlidingWindowRateLimiter()


def client_identifier(request: Request):
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def enforce_rate_limit(
    request,
    scope,
    per_ip_limit,
    per_ip_window_seconds=3600,
    global_limit=None,
    global_window_seconds=86400,
):
    client_id = client_identifier(request)
    rules = [
        LimitRule(
            key=f"{scope}:client:{client_id}",
            limit=per_ip_limit,
            window_seconds=per_ip_window_seconds,
        )
    ]
    if global_limit:
        rules.append(
            LimitRule(
                key=f"{scope}:global",
                limit=global_limit,
                window_seconds=global_window_seconds,
            )
        )

    decision = limiter.check(rules)
    if decision.allowed:
        return None

    return JSONResponse(
        {"error": "rate_limited", "retry_after": decision.retry_after},
        status_code=429,
        headers={
            "Retry-After": str(decision.retry_after),
            "Cache-Control": "no-store",
        },
    )
