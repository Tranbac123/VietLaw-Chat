"""Typed AI Core errors. The HTTP layer (not in this scope) maps these to the
error schema. analyze() raises these; it never returns the error schema itself.
"""


class AiCoreError(Exception):
    """Base for all AI Core errors. Carries an API error code + HTTP status."""

    code: str = "internal_error"
    http_status: int = 500


class InvalidRequest(AiCoreError):
    code = "invalid_request"
    http_status = 400


class ChatNotFound(AiCoreError):
    code = "chat_not_found"
    http_status = 404


class RetrievalError(AiCoreError):
    code = "retrieval_error"
    http_status = 503


class LlmError(AiCoreError):
    code = "llm_error"
    http_status = 503


class InternalError(AiCoreError):
    code = "internal_error"
    http_status = 500
