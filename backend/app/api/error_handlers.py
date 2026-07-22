"""Maps typed AiCore errors and request-validation failures to the frozen
error contract. Never leaks stack traces, provider errors, or secrets: each
error code returns a fixed, safe Vietnamese message and the safety notice.
"""
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import SAFETY_NOTICE
from app.errors import AiCoreError
from app.schemas import ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)

# Fixed, user-safe messages per error code. Raw exception text is never
# forwarded to the client (it may carry provider or internal detail).
_SAFE_MESSAGES = {
    "invalid_request": "Dữ liệu yêu cầu không hợp lệ.",
    "chat_not_found": "Không tìm thấy cuộc trò chuyện.",
    "retrieval_error": "Nguồn tham khảo tạm thời không khả dụng.",
    "llm_error": "Dịch vụ AI tạm thời không khả dụng.",
    "internal_error": "Backend gặp lỗi không mong đợi.",
}


def _payload(code: str, request_id: str | None = None) -> dict:
    return ErrorResponse(
        request_id=request_id or ("req_err_" + uuid.uuid4().hex[:12]),
        error=ErrorDetail(code=code, message=_SAFE_MESSAGES.get(code, _SAFE_MESSAGES["internal_error"])),
        safety_notice=SAFETY_NOTICE,
    ).model_dump()


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AiCoreError)
    async def _aicore_error(_request: Request, exc: AiCoreError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=_payload(exc.code))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content=_payload("invalid_request"))

    @app.exception_handler(Exception)
    async def _unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled backend error", exc_info=exc)
        return JSONResponse(status_code=500, content=_payload("internal_error"))
