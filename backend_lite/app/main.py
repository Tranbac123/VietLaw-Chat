from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.error_handlers import register_error_handlers
from .api.rate_limit_middleware import RateLimitMiddleware, build_rate_limit_middleware_kwargs
from .api.routes_analyze import router as analyze_router
from .api.routes_chats import router as chats_router
from .api.routes_health import router as health_router
from .config import Settings
from .dependencies import build_container


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings()
    app = FastAPI(title="VietLaw-Chat Backend", version="1.0.0")
    app.state.container = build_container(resolved_settings)
    # Limited-demo protection (task: "basic rate limiting"). Always added;
    # a no-op pass-through when VIETLAW_RATE_LIMIT_ENABLED is unset/false,
    # so existing behavior is unchanged unless a deployment opts in.
    app.add_middleware(RateLimitMiddleware, **build_rate_limit_middleware_kwargs())
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )
    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(analyze_router)
    app.include_router(chats_router)
    return app


app = create_app()
