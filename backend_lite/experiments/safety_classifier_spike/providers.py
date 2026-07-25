"""Experiment adapters and redacted provider failure taxonomy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .contract import ClassifierRequest, ProviderResponse


class ClassifierProviderError(RuntimeError):
    """Base provider error with no raw provider message in its public value."""

    code = "CLASSIFIER_PROVIDER_ERROR"

    def __init__(self) -> None:
        super().__init__(self.code)


class ClassifierTimeoutError(ClassifierProviderError):
    code = "CLASSIFIER_PROVIDER_TIMEOUT"


class ClassifierUnavailableError(ClassifierProviderError):
    code = "CLASSIFIER_PROVIDER_UNAVAILABLE"


class ClassifierRateLimitError(ClassifierProviderError):
    code = "CLASSIFIER_PROVIDER_RATE_LIMIT"


@dataclass(slots=True)
class ScriptedProvider:
    """In-memory adapter for contract replay; it is not a quality oracle."""

    responder: Callable[[ClassifierRequest], ProviderResponse]
    provider_name: str = "scripted-contract-replay"
    call_count: int = 0

    def classify(self, request: ClassifierRequest) -> ProviderResponse:
        self.call_count += 1
        return self.responder(request)


@dataclass(slots=True)
class FailureProvider:
    """Deterministically inject one typed provider failure."""

    failure: type[ClassifierProviderError]
    provider_name: str = "failure-injection"
    call_count: int = 0

    def classify(self, request: ClassifierRequest) -> ProviderResponse:
        del request
        self.call_count += 1
        raise self.failure()


__all__ = [
    "ClassifierProviderError",
    "ClassifierRateLimitError",
    "ClassifierTimeoutError",
    "ClassifierUnavailableError",
    "FailureProvider",
    "ScriptedProvider",
]

