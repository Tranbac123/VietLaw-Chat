from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int, details: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class InvalidRequestError(AppError):
    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__("invalid_request", message, 400, details)


class ChatNotFoundError(AppError):
    def __init__(self, message: str = "Không tìm thấy cuộc trò chuyện.") -> None:
        super().__init__("chat_not_found", message, 404)


class IdempotencyConflictError(AppError):
    """The same owner reused a client_request_id for a materially different
    request. Replaying the stored answer would be wrong, and running the new one
    under an already-used key would break exactly-once, so the turn is refused
    with no provider call and no database write."""

    def __init__(
        self,
        message: str = "Yêu cầu này đã được gửi trước đó với nội dung khác. Bạn gửi lại tin nhắn mới giúp tôi nhé.",
    ) -> None:
        super().__init__("idempotency_conflict", message, 409)


class RequestInProgressError(AppError):
    """A reservation for this owner/request is still pending. A controlled
    retry-safe result is the only safe answer: starting a second provider
    attempt could duplicate the turn's effects."""

    def __init__(
        self,
        message: str = "Yêu cầu trước của bạn đang được xử lý. Bạn đợi một chút rồi thử lại nhé.",
    ) -> None:
        super().__init__("request_in_progress", message, 409)


class IdempotencyUnavailableError(AppError):
    """A request carrying a ``client_request_id`` asked for exactly-once
    handling that cannot currently be guaranteed.

    Falling back to the legacy path here would silently execute a keyed request
    non-idempotently -- the caller believes a retry is safe when it is not. The
    turn is refused instead, before any chat, message, provider call or fact
    write, so an explicit retry stays safe.
    """

    def __init__(
        self,
        message: str = "Hệ thống tạm thời chưa xử lý được yêu cầu này một cách an toàn. Bạn thử lại sau giây lát nhé.",
    ) -> None:
        super().__init__("idempotency_unavailable", message, 503)


class RetrievalError(AppError):
    def __init__(self, message: str = "Nguồn tham khảo tạm thời không khả dụng.") -> None:
        super().__init__("retrieval_error", message, 503)
