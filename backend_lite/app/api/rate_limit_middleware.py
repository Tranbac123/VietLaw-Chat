"""VietLaw Limited Demo: bounded, feature-flagged request protection for the
one expensive, unauthenticated endpoint (`POST /api/analyze`).

Scope is deliberately narrow: `/api/health` (a Railway health-check target)
and every GET/read-only endpoint (`/api/chats*`) are never touched, per the
task's explicit "health endpoint excluded" / "static/read-only endpoints
excluded" requirement -- a health check or chat-history read must never be
rejected because a user is chatting quickly.

This is a single-process, in-memory guard (see
`guards/rate_limiter.py`'s own docstring for why): it requires exactly one
Railway replica to produce correct aggregate limits, resets on restart, and
is not a substitute for a real edge/production rate limiter.
"""

from __future__ import annotations

import ipaddress
import json
import os
import time
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ..constants import CONTRACT_VERSION, SAFETY_NOTICE
from ..guards.rate_limiter import ConcurrencyLimiter, FixedWindowRateLimiter
from ..schemas.api import ApiErrorResponse, ErrorBody

_LIMITED_PATH = "/api/analyze"


def _flag(name: str, *, default: bool) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name) or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def rate_limiting_enabled() -> bool:
    return _flag("VIETLAW_RATE_LIMIT_ENABLED", default=False)


def trust_proxy_headers_enabled() -> bool:
    """Deployment Correction Round 1 (MEDIUM-02): whether this process sits
    behind a proxy (Railway) that can be trusted to set `X-Real-IP` itself,
    as opposed to a client reaching this backend directly, who could set
    that header to anything. Off by default -- a deployment must opt in
    explicitly, exactly like `VIETLAW_RATE_LIMIT_ENABLED`."""

    return _flag("VIETLAW_TRUST_PROXY_HEADERS", default=False)


def _valid_ip_or_none(value: str | None) -> str | None:
    candidate = (value or "").strip()
    if not candidate:
        return None
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate


def _client_ip(request: Request, *, trust_proxy_headers: bool) -> str:
    """Rate-limit identity extraction.

    `X-Forwarded-For` is NEVER used for this: it is attacker-controlled
    end-to-end (any client can set it directly against this backend,
    bypassing the real Railway edge entirely -- see MEDIUM-02, HIGH-lettered
    finding in the independent deployment review, which demonstrated a
    spoofed-address bypass of the per-IP limit via rotating that header).

    In trusted-proxy mode (`VIETLAW_TRUST_PROXY_HEADERS=1`, Railway's actual
    deployment configuration), `X-Real-IP` is Railway's own edge-assigned
    header -- not attacker-settable the same way, since it is Railway's
    proxy, not the origin client, that sets it on the request this process
    receives. It is still validated with `ipaddress.ip_address()` before
    use, and any malformed value falls back to the raw ASGI socket peer
    rather than being trusted blindly.

    Outside trusted-proxy mode (local development, or any deployment that
    has not explicitly opted in), both proxy headers are ignored entirely
    and only the direct socket peer is used -- this is still only a
    limited-demo protection (a single-process, single-replica limiter), not
    a hardened anti-spoofing mechanism; see the module docstring."""

    if trust_proxy_headers:
        real_ip = _valid_ip_or_none(request.headers.get("x-real-ip"))
        if real_ip is not None:
            return real_ip
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _error_response(
    *, status_code: int, code: str, message: str, retry_after_seconds: float | None
) -> JSONResponse:
    body = ApiErrorResponse(
        contract_version=CONTRACT_VERSION,
        request_id=f"req_{uuid4().hex}",
        error=ErrorBody(code=code, message=message),
        safety_notice=SAFETY_NOTICE,
    )
    headers = {}
    if retry_after_seconds is not None:
        headers["Retry-After"] = str(max(1, int(retry_after_seconds + 0.999)))
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", exclude_none=True),
        headers=headers,
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Applies, in order, to `POST /api/analyze` only:

      1. maximum message length (`question` field, chars)
      2. maximum concurrent in-flight analyze requests
      3. per-client-IP requests-per-minute
      4. per-conversation (`chat_id`) requests-per-minute

    Every check is independently feature-flagged off by default via
    `enabled=False` (wired from `VIETLAW_RATE_LIMIT_ENABLED`) so existing
    behavior is unchanged unless a deployment opts in.
    """

    def __init__(
        self,
        app,
        *,
        enabled: bool,
        max_message_chars: int,
        per_ip_limiter: FixedWindowRateLimiter,
        per_conversation_limiter: FixedWindowRateLimiter,
        concurrency_limiter: ConcurrencyLimiter,
        trust_proxy_headers: bool = False,
    ) -> None:
        super().__init__(app)
        self._enabled = enabled
        self._max_message_chars = max_message_chars
        self._per_ip_limiter = per_ip_limiter
        self._per_conversation_limiter = per_conversation_limiter
        self._concurrency_limiter = concurrency_limiter
        self._trust_proxy_headers = trust_proxy_headers

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self._enabled or request.method != "POST" or request.url.path != _LIMITED_PATH:
            return await call_next(request)

        raw_body = await request.body()
        question_length: int | None = None
        chat_id: str | None = None
        try:
            parsed = json.loads(raw_body) if raw_body else {}
            if isinstance(parsed, dict):
                question = parsed.get("question")
                if isinstance(question, str):
                    question_length = len(question)
                candidate_chat_id = parsed.get("chat_id")
                if isinstance(candidate_chat_id, str) and candidate_chat_id:
                    chat_id = candidate_chat_id
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Malformed JSON is not this middleware's concern -- let the
            # normal FastAPI validation error handler produce the usual 400.
            pass

        if question_length is not None and question_length > self._max_message_chars:
            return _error_response(
                status_code=413,
                code="message_too_long",
                message="Tin nhắn quá dài. Vui lòng rút gọn nội dung và gửi lại.",
                retry_after_seconds=None,
            )

        client_ip = _client_ip(request, trust_proxy_headers=self._trust_proxy_headers)
        ip_decision = self._per_ip_limiter.check(client_ip)
        if not ip_decision.allowed:
            return _error_response(
                status_code=429,
                code="rate_limited",
                message="Bạn đã gửi quá nhiều yêu cầu trong thời gian ngắn. Vui lòng thử lại sau.",
                retry_after_seconds=ip_decision.retry_after_seconds,
            )

        if chat_id is not None:
            conversation_decision = self._per_conversation_limiter.check(chat_id)
            if not conversation_decision.allowed:
                return _error_response(
                    status_code=429,
                    code="rate_limited",
                    message="Cuộc trò chuyện này đang gửi tin nhắn quá nhanh. Vui lòng thử lại sau.",
                    retry_after_seconds=conversation_decision.retry_after_seconds,
                )

        if not self._concurrency_limiter.try_acquire():
            return _error_response(
                status_code=429,
                code="rate_limited",
                message="Hệ thống đang xử lý nhiều yêu cầu. Vui lòng thử lại sau ít giây.",
                retry_after_seconds=1.0,
            )
        try:
            # `request.body()` caches its result on the ASGI receive channel,
            # so downstream FastAPI parsing re-reads the same bytes rather
            # than hanging waiting for a second (already-consumed) body.
            return await call_next(request)
        finally:
            self._concurrency_limiter.release()


def build_rate_limit_middleware_kwargs() -> dict:
    """Reads `VIETLAW_RATE_LIMIT_*` env vars into the exact kwargs
    `RateLimitMiddleware` needs, using `time.monotonic` as the real clock.
    Kept separate from the class so tests can construct the middleware
    directly with an injected `now_fn` instead of real time."""

    return {
        "enabled": rate_limiting_enabled(),
        "trust_proxy_headers": trust_proxy_headers_enabled(),
        "max_message_chars": _int_env("VIETLAW_MAX_MESSAGE_CHARS", 3000),
        "per_ip_limiter": FixedWindowRateLimiter(
            limit=_int_env("VIETLAW_RATE_LIMIT_PER_IP_PER_MINUTE", 20),
            window_seconds=60.0,
            now_fn=time.monotonic,
        ),
        "per_conversation_limiter": FixedWindowRateLimiter(
            limit=_int_env("VIETLAW_RATE_LIMIT_PER_CONVERSATION_PER_MINUTE", 12),
            window_seconds=60.0,
            now_fn=time.monotonic,
        ),
        "concurrency_limiter": ConcurrencyLimiter(
            limit=_int_env("VIETLAW_MAX_CONCURRENT_REQUESTS", 4),
        ),
    }


__all__ = [
    "RateLimitMiddleware",
    "build_rate_limit_middleware_kwargs",
    "rate_limiting_enabled",
    "trust_proxy_headers_enabled",
]
