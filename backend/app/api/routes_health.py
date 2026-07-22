"""GET /api/health. Reports readiness of RAG data, safety patterns, and the
chat store. Must not call the LLM or expose secrets.
"""
from fastapi import APIRouter, Depends

from app.api.deps import get_core
from app.runtime.analyze import AiCore
from app.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])

SERVICE_NAME = "vietlaw-chat-backend"


@router.get("/health", response_model=HealthResponse)
def health(core: AiCore = Depends(get_core)) -> HealthResponse:
    rag_loaded = len(core.retriever.snippets) > 0
    safety_loaded = bool(core.bank.unsafe or core.bank.high_risk)
    chat_store_ready = core.store.healthcheck()
    return HealthResponse(
        status="ok" if (rag_loaded and safety_loaded and chat_store_ready) else "degraded",
        service=SERVICE_NAME,
        rag_loaded=rag_loaded,
        safety_loaded=safety_loaded,
        chat_store_ready=chat_store_ready,
    )
