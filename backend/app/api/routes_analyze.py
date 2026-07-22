"""POST /api/analyze. Thin HTTP wrapper over the AiCore pipeline. AiCore owns
all business logic and raises typed errors that the error handlers map.

Defined as a sync def so FastAPI runs it in a worker thread: the pipeline does
blocking SQLite and LLM network calls that must not block the event loop.
"""
from fastapi import APIRouter, Depends

from app.api.deps import get_core
from app.runtime.analyze import AiCore
from app.schemas import AnalyzeRequest, AnalyzeResponse

router = APIRouter(prefix="/api", tags=["analyze"])


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(payload: AnalyzeRequest, core: AiCore = Depends(get_core)) -> AnalyzeResponse:
    return core.analyze(payload)
