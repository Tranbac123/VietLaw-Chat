"""Deployment Correction Round 1 (MEDIUM-02): trusted client-IP extraction
for rate-limit identity.

Unit-level tests for `_client_ip` plus an HTTP-level regression proving
`X-Forwarded-For` rotation cannot bypass the per-IP rate limit, and that
`X-Real-IP` is honored (with a safe fallback) only in trusted-proxy mode.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend_lite.app.api.rate_limit_middleware import RateLimitMiddleware, _client_ip
from backend_lite.app.config import Settings
from backend_lite.app.dependencies import build_container
from backend_lite.app.guards.rate_limiter import ConcurrencyLimiter, FixedWindowRateLimiter


def _make_request(*, headers: dict[str, str], client_host: str | None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (client_host, 12345) if client_host else None,
    }
    return Request(scope)


def test_untrusted_mode_ignores_both_proxy_headers_uses_socket_peer():
    request = _make_request(
        headers={"x-forwarded-for": "1.2.3.4", "x-real-ip": "5.6.7.8"},
        client_host="9.9.9.9",
    )
    assert _client_ip(request, trust_proxy_headers=False) == "9.9.9.9"


def test_trusted_mode_uses_valid_x_real_ip():
    request = _make_request(
        headers={"x-forwarded-for": "1.2.3.4", "x-real-ip": "5.6.7.8"},
        client_host="9.9.9.9",
    )
    assert _client_ip(request, trust_proxy_headers=True) == "5.6.7.8"


def test_trusted_mode_falls_back_safely_on_malformed_x_real_ip():
    request = _make_request(
        headers={"x-real-ip": "not-an-ip"},
        client_host="9.9.9.9",
    )
    assert _client_ip(request, trust_proxy_headers=True) == "9.9.9.9"


def test_trusted_mode_ignores_x_forwarded_for_entirely_even_when_x_real_ip_absent():
    request = _make_request(
        headers={"x-forwarded-for": "1.2.3.4"},
        client_host="9.9.9.9",
    )
    assert _client_ip(request, trust_proxy_headers=True) == "9.9.9.9"


def test_no_discoverable_origin_returns_constant():
    request = _make_request(headers={}, client_host=None)
    assert _client_ip(request, trust_proxy_headers=True) == "unknown"


class _FakeClock:
    def __init__(self) -> None:
        self._now = 0.0

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def _rate_limited_app(settings: Settings, *, trust_proxy_headers: bool):
    from backend_lite.app.api.error_handlers import register_error_handlers
    from backend_lite.app.api.routes_analyze import router as analyze_router
    from backend_lite.app.api.routes_chats import router as chats_router
    from backend_lite.app.api.routes_health import router as health_router

    clock = _FakeClock()
    app = FastAPI(title="test")
    app.state.container = build_container(settings)
    app.add_middleware(
        RateLimitMiddleware,
        enabled=True,
        trust_proxy_headers=trust_proxy_headers,
        max_message_chars=3000,
        per_ip_limiter=FixedWindowRateLimiter(limit=1, window_seconds=60.0, now_fn=clock),
        per_conversation_limiter=FixedWindowRateLimiter(limit=100, window_seconds=60.0, now_fn=clock),
        concurrency_limiter=ConcurrencyLimiter(limit=5),
    )
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(analyze_router)
    app.include_router(chats_router)
    return app


def test_rotating_x_forwarded_for_cannot_bypass_per_ip_limit(settings: Settings, analyze_payload):
    """Untrusted mode (the default): the ASGI test client always presents the
    same socket peer regardless of header content, so rotating
    `X-Forwarded-For` must not grant a second allowance."""

    app = _rate_limited_app(settings, trust_proxy_headers=False)
    with TestClient(app) as client:
        first = client.post(
            "/api/analyze",
            json=analyze_payload("cảm ơn nhé"),
            headers={"X-Forwarded-For": "1.1.1.1"},
        )
        second = client.post(
            "/api/analyze",
            json=analyze_payload("cảm ơn nhé"),
            headers={"X-Forwarded-For": "2.2.2.2"},
        )
    assert first.status_code == 200
    assert second.status_code == 429


def test_trusted_mode_x_real_ip_gives_independent_buckets_per_real_client(
    settings: Settings, analyze_payload
):
    """Trusted-proxy mode still keys on the real client identity
    (`X-Real-IP`) -- two genuinely different clients (as Railway's edge
    would report them) each get their own bucket, proving this is normal
    per-IP behavior, not a blanket bypass."""

    app = _rate_limited_app(settings, trust_proxy_headers=True)
    with TestClient(app) as client:
        client_a_first = client.post(
            "/api/analyze",
            json=analyze_payload("cảm ơn nhé"),
            headers={"X-Real-IP": "10.0.0.1"},
        )
        client_a_second = client.post(
            "/api/analyze",
            json=analyze_payload("cảm ơn nhé"),
            headers={"X-Real-IP": "10.0.0.1"},
        )
        client_b_first = client.post(
            "/api/analyze",
            json=analyze_payload("cảm ơn nhé"),
            headers={"X-Real-IP": "10.0.0.2"},
        )
    assert client_a_first.status_code == 200
    assert client_a_second.status_code == 429
    assert client_b_first.status_code == 200


def test_trusted_mode_x_forwarded_for_alone_cannot_bypass_limit(settings: Settings, analyze_payload):
    """Even in trusted-proxy mode, `X-Forwarded-For` (never consulted) gives
    an attacker nothing -- only a genuine change in the socket peer (which a
    test client cannot forge per-request) or a valid `X-Real-IP` changes the
    bucket."""

    app = _rate_limited_app(settings, trust_proxy_headers=True)
    with TestClient(app) as client:
        first = client.post(
            "/api/analyze",
            json=analyze_payload("cảm ơn nhé"),
            headers={"X-Forwarded-For": "1.1.1.1"},
        )
        second = client.post(
            "/api/analyze",
            json=analyze_payload("cảm ơn nhé"),
            headers={"X-Forwarded-For": "2.2.2.2"},
        )
    assert first.status_code == 200
    assert second.status_code == 429
