"""ASGI entrypoint. `create_app` builds the FastAPI app, the AiCore pipeline
(shared on app.state), CORS, and the error handlers.

Run with the factory (no import-time side effects, so importing this module in
tests does not open a DB or build an LLM client):

    uvicorn app.main:create_app --factory --app-dir backend
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.error_handlers import register_error_handlers
from app.api.routes_analyze import router as analyze_router
from app.api.routes_chats import router as chats_router
from app.api.routes_health import router as health_router
from app.config import Settings
from app.runtime.analyze import AiCore


def create_app(settings: Settings | None = None, core: AiCore | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="VietLaw-Chat Backend", version="1.0.0")
    app.state.settings = settings
    # `core` is injectable so tests can supply a pipeline with a fake LLM.
    app.state.core = core or AiCore(settings)

    origins = [o.strip() for o in settings.frontend_origin.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    register_error_handlers(app)
    app.include_router(health_router)
    app.include_router(analyze_router)
    app.include_router(chats_router)
    return app
