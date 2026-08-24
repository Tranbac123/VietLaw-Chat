"""VietLaw Limited Demo Deployment Readiness V1.

Deployment-specific tests only: exact-origin CORS behavior, the in-process
rate limiter (unit-level, with an injected fake clock -- never a real sleep
or wall-clock dependency) and its HTTP wiring, the health endpoint's status
code, and `Settings`' path resolution for a Railway-style absolute `/data`
path. None of this touches traffic legal rules, selectors, citations, or
MODE_2D.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend_lite.app.config import Settings
from backend_lite.app.guards.rate_limiter import ConcurrencyLimiter, FixedWindowRateLimiter
from backend_lite.app.main import CorsConfigError, create_app, validate_production_cors_origins


# =============================================================================
# CORS: exact-origin allowlist (task §8)
# =============================================================================


def test_configured_production_origin_is_allowed(settings: Settings, analyze_payload):
    configured = settings.model_copy(update={"cors_origins": "https://vietlaw-demo.pages.dev"})
    with TestClient(create_app(configured)) as client:
        response = client.get(
            "/api/health", headers={"Origin": "https://vietlaw-demo.pages.dev"}
        )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://vietlaw-demo.pages.dev"


def test_unconfigured_origin_is_rejected(settings: Settings):
    configured = settings.model_copy(update={"cors_origins": "https://vietlaw-demo.pages.dev"})
    with TestClient(create_app(configured)) as client:
        response = client.get("/api/health", headers={"Origin": "https://evil.example.com"})
    # The server still answers (CORS is enforced by the BROWSER reading
    # this header, not by the server refusing the request) -- the absence
    # of the allow-origin header is what makes the browser block the read.
    assert response.status_code == 200
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_localhost_allowed_only_when_explicitly_configured(settings: Settings):
    dev = settings.model_copy(update={"cors_origins": "http://127.0.0.1:5173,http://localhost:5173"})
    with TestClient(create_app(dev)) as client:
        allowed = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        rejected = client.get("/api/health", headers={"Origin": "https://vietlaw-demo.pages.dev"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in {k.lower() for k in rejected.headers}


def test_credentials_allowed_for_a_configured_origin(settings: Settings):
    configured = settings.model_copy(update={"cors_origins": "https://vietlaw-demo.pages.dev"})
    with TestClient(create_app(configured)) as client:
        response = client.get(
            "/api/health", headers={"Origin": "https://vietlaw-demo.pages.dev"}
        )
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_preflight_request_for_configured_origin_succeeds(settings: Settings):
    configured = settings.model_copy(update={"cors_origins": "https://vietlaw-demo.pages.dev"})
    with TestClient(create_app(configured)) as client:
        response = client.options(
            "/api/analyze",
            headers={
                "Origin": "https://vietlaw-demo.pages.dev",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://vietlaw-demo.pages.dev"


def test_preflight_request_for_unconfigured_origin_is_not_authorized(settings: Settings):
    configured = settings.model_copy(update={"cors_origins": "https://vietlaw-demo.pages.dev"})
    with TestClient(create_app(configured)) as client:
        response = client.options(
            "/api/analyze",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert "access-control-allow-origin" not in {k.lower() for k in response.headers}


def test_wildcard_origin_is_never_configured_in_source() -> None:
    # A static-source check, not a runtime one: confirms `allow_origins=["*"]`
    # was never (re)introduced into the actual CORSMiddleware wiring. (Bounded
    # pre-deploy hardening: `main.py` now also validates an OPERATOR-supplied
    # `CORS_ORIGINS=*` at runtime -- see the tests below -- which necessarily
    # references the "*" literal itself; this assertion is narrowed to the
    # specific hardcoded-into-CORSMiddleware pattern it originally existed to
    # catch, not every occurrence of the character in the file.)
    main_source = (Path(__file__).resolve().parents[2] / "backend_lite" / "app" / "main.py").read_text(
        encoding="utf-8"
    )
    assert 'allow_origins=["*"]' not in main_source
    assert "allow_origins=['*']" not in main_source


# =============================================================================
# CORS: wildcard origin rejected in production (bounded pre-deploy hardening)
# =============================================================================


def test_production_rejects_wildcard_cors_origin() -> None:
    with pytest.raises(CorsConfigError):
        validate_production_cors_origins("production", ["*"])


def test_production_accepts_exact_configured_cors_origin() -> None:
    # Must not raise.
    validate_production_cors_origins("production", ["https://vietlaw-demo.pages.dev"])


def test_non_production_allows_wildcard_cors_origin() -> None:
    # Not a blocker outside production -- the checklist forbids it there,
    # but this guard is specifically the production deployment safety net.
    validate_production_cors_origins("development", ["*"])


def test_production_app_refuses_to_boot_with_wildcard_cors_origin(settings: Settings) -> None:
    configured = settings.model_copy(update={"app_env": "production", "cors_origins": "*"})
    with pytest.raises(CorsConfigError):
        create_app(configured)


# =============================================================================
# APP_ENV: unrecognized values are rejected, not silently bypassed (bounded
# pre-deploy hardening)
# =============================================================================


@pytest.mark.parametrize("invalid_value", ["prod", "staginggg", "foo", "unknown", "Production2"])
def test_invalid_app_env_value_is_rejected(invalid_value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(app_env=invalid_value)


@pytest.mark.parametrize(
    ("configured_value", "expected"),
    [
        ("development", "development"),
        ("test", "test"),
        ("production", "production"),
        ("  PRODUCTION  ", "production"),
        ("Development", "development"),
    ],
)
def test_canonical_app_env_values_are_accepted_case_and_whitespace_insensitively(
    configured_value: str, expected: str
) -> None:
    configured = Settings(app_env=configured_value)
    assert configured.app_env == expected


# =============================================================================
# Health endpoint status code (task §10)
# =============================================================================


def test_healthy_response_is_200(client) -> None:
    assert client.get("/api/health").status_code == 200


def test_degraded_response_is_503(settings: Settings, tmp_path: Path) -> None:
    degraded = settings.model_copy(update={"legal_snippets_path": tmp_path / "missing.json"})
    with TestClient(create_app(degraded)) as client:
        response = client.get("/api/health")
    assert response.status_code == 503


# =============================================================================
# Settings path resolution for a Railway-style absolute /data path (task §6)
# =============================================================================


def test_absolute_data_volume_path_is_used_verbatim() -> None:
    # No code change was needed for this (the existing `chat_db_path`
    # env var already accepts any absolute path) -- this test exists only
    # to prove it, against the exact path a Railway deployment would set.
    configured = Settings(chat_db_path="/data/vietlaw_chat.sqlite3")
    assert configured.chat_db_path == Path("/data/vietlaw_chat.sqlite3")


def test_relative_path_resolves_against_cwd_not_silently_elsewhere(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    configured = Settings(chat_db_path="data/vietlaw_chat.sqlite3")
    assert configured.chat_db_path == (tmp_path / "data" / "vietlaw_chat.sqlite3").resolve()


def test_local_development_default_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    # Local dev must keep working with zero configuration. `CHAT_DB_PATH` is
    # cleared here because a real repository `.env` file may itself set it
    # for a developer's own local live-testing convenience -- this test is
    # specifically about the code's OWN default, not whatever a `.env` says.
    monkeypatch.delenv("CHAT_DB_PATH", raising=False)
    default = Settings()
    assert default.chat_db_path.name == "vietlaw_chat.sqlite3"
    assert default.chat_db_path.is_absolute()


# =============================================================================
# Rate limiter primitives (task §9) -- deterministic fake clock, no real sleep
# =============================================================================


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_fixed_window_limiter_allows_up_to_the_limit_then_rejects() -> None:
    clock = _FakeClock()
    limiter = FixedWindowRateLimiter(limit=3, window_seconds=60.0, now_fn=clock)
    assert [limiter.check("ip-1").allowed for _ in range(3)] == [True, True, True]
    fourth = limiter.check("ip-1")
    assert fourth.allowed is False
    assert fourth.retry_after_seconds == pytest.approx(60.0, abs=0.01)


def test_fixed_window_limiter_resets_after_the_window_elapses() -> None:
    clock = _FakeClock()
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60.0, now_fn=clock)
    assert limiter.check("ip-1").allowed is True
    assert limiter.check("ip-1").allowed is False
    clock.advance(60.1)
    assert limiter.check("ip-1").allowed is True


def test_fixed_window_limiter_tracks_keys_independently() -> None:
    clock = _FakeClock()
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=60.0, now_fn=clock)
    assert limiter.check("ip-1").allowed is True
    assert limiter.check("ip-2").allowed is True
    assert limiter.check("ip-1").allowed is False


def test_fixed_window_limiter_sweeps_stale_keys_to_bound_memory() -> None:
    clock = _FakeClock()
    limiter = FixedWindowRateLimiter(
        limit=1, window_seconds=60.0, now_fn=clock, sweep_interval_seconds=100.0
    )
    for i in range(50):
        limiter.check(f"ip-{i}")
    assert len(limiter) == 50
    # Advance past both the window (60s) and the sweep interval (100s); the
    # next check (a new key) triggers a sweep of all the now-stale entries.
    clock.advance(250.0)
    limiter.check("ip-new")
    assert len(limiter) == 1  # only the just-inserted key survives


def test_fixed_window_limiter_rejects_nonpositive_configuration() -> None:
    with pytest.raises(ValueError):
        FixedWindowRateLimiter(limit=0, window_seconds=60.0, now_fn=lambda: 0.0)
    with pytest.raises(ValueError):
        FixedWindowRateLimiter(limit=1, window_seconds=0.0, now_fn=lambda: 0.0)


def test_concurrency_limiter_rejects_once_full_and_recovers_on_release() -> None:
    limiter = ConcurrencyLimiter(limit=2)
    assert limiter.try_acquire() is True
    assert limiter.try_acquire() is True
    assert limiter.try_acquire() is False
    assert limiter.in_flight == 2
    limiter.release()
    assert limiter.in_flight == 1
    assert limiter.try_acquire() is True


def test_concurrency_limiter_release_never_goes_negative() -> None:
    limiter = ConcurrencyLimiter(limit=1)
    limiter.release()
    limiter.release()
    assert limiter.in_flight == 0


# =============================================================================
# Rate limiter HTTP wiring (task §9) -- feature-flagged, scoped to /api/analyze
# =============================================================================


def _rate_limited_app(settings: Settings, **overrides):
    from backend_lite.app.api.rate_limit_middleware import RateLimitMiddleware
    from backend_lite.app.dependencies import build_container
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from backend_lite.app.api.error_handlers import register_error_handlers
    from backend_lite.app.api.routes_analyze import router as analyze_router
    from backend_lite.app.api.routes_chats import router as chats_router
    from backend_lite.app.api.routes_health import router as health_router

    clock = _FakeClock()
    kwargs = {
        "enabled": True,
        "max_message_chars": 3000,
        "per_ip_limiter": FixedWindowRateLimiter(limit=2, window_seconds=60.0, now_fn=clock),
        "per_conversation_limiter": FixedWindowRateLimiter(limit=2, window_seconds=60.0, now_fn=clock),
        "concurrency_limiter": ConcurrencyLimiter(limit=5),
    }
    kwargs.update(overrides)

    app = FastAPI(title="test")
    app.state.container = build_container(settings)
    app.add_middleware(RateLimitMiddleware, **kwargs)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(analyze_router)
    app.include_router(chats_router)
    return app, clock


def test_rate_limit_disabled_by_default_allows_unlimited_requests(client, analyze_payload) -> None:
    for _ in range(10):
        response = client.post("/api/analyze", json=analyze_payload("cảm ơn nhé"))
        assert response.status_code == 200


def test_rate_limit_per_ip_returns_429_with_retry_after(settings: Settings, analyze_payload) -> None:
    app, _clock = _rate_limited_app(settings)
    with TestClient(app) as client:
        first = client.post("/api/analyze", json=analyze_payload("cảm ơn nhé"))
        second = client.post("/api/analyze", json=analyze_payload("cảm ơn nhé"))
        third = client.post("/api/analyze", json=analyze_payload("cảm ơn nhé"))
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "rate_limited"
    assert int(third.headers["retry-after"]) >= 1


def test_rate_limit_health_endpoint_is_never_limited(settings: Settings) -> None:
    app, _clock = _rate_limited_app(
        settings,
        per_ip_limiter=FixedWindowRateLimiter(limit=1, window_seconds=60.0, now_fn=_FakeClock()),
    )
    with TestClient(app) as client:
        responses = [client.get("/api/health") for _ in range(5)]
    assert all(response.status_code == 200 for response in responses)


def test_rate_limit_chat_list_endpoint_is_never_limited(settings: Settings) -> None:
    app, _clock = _rate_limited_app(
        settings,
        per_ip_limiter=FixedWindowRateLimiter(limit=1, window_seconds=60.0, now_fn=_FakeClock()),
    )
    with TestClient(app) as client:
        responses = [
            client.get("/api/chats", params={"session_id": "session_test"}) for _ in range(5)
        ]
    assert all(response.status_code == 200 for response in responses)


def test_oversized_message_is_rejected_with_413(settings: Settings, analyze_payload) -> None:
    app, _clock = _rate_limited_app(settings, max_message_chars=50)
    with TestClient(app) as client:
        response = client.post("/api/analyze", json=analyze_payload("x" * 100))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "message_too_long"


def test_concurrency_limit_returns_429_once_exhausted(settings: Settings, analyze_payload) -> None:
    # Pre-acquire the exact limiter instance the middleware will consult,
    # simulating one already-in-flight request, then confirm a genuine HTTP
    # request through the middleware is rejected while that slot is held.
    shared_limiter = ConcurrencyLimiter(limit=1)
    assert shared_limiter.try_acquire() is True

    app, _clock = _rate_limited_app(settings, concurrency_limiter=shared_limiter)
    with TestClient(app) as client:
        response = client.post("/api/analyze", json=analyze_payload("cảm ơn nhé"))
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


def test_per_conversation_limit_is_independent_of_per_ip_limit(settings: Settings, analyze_payload) -> None:
    app, _clock = _rate_limited_app(
        settings,
        per_ip_limiter=FixedWindowRateLimiter(limit=100, window_seconds=60.0, now_fn=_FakeClock()),
        per_conversation_limiter=FixedWindowRateLimiter(limit=2, window_seconds=60.0, now_fn=_FakeClock()),
    )
    with TestClient(app) as client:
        # A chat is created server-side on the first turn (no chat_id yet,
        # so the per-conversation limiter has nothing to key on for it);
        # its id is then reused for subsequent turns in the SAME
        # conversation, which the per-conversation limiter (limit=2) DOES
        # count -- the 3rd such turn is the one that is rejected.
        first = client.post("/api/analyze", json=analyze_payload("cảm ơn nhé"))
        chat_id = first.json()["chat_id"]
        second = client.post("/api/analyze", json=analyze_payload("cảm ơn nhé", chat_id=chat_id))
        third = client.post("/api/analyze", json=analyze_payload("cảm ơn nhé", chat_id=chat_id))
        fourth = client.post("/api/analyze", json=analyze_payload("cảm ơn nhé", chat_id=chat_id))
        other_chat = client.post("/api/analyze", json=analyze_payload("cảm ơn nhé"))
    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert fourth.status_code == 429
    assert other_chat.status_code == 200
