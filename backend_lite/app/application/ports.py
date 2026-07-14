"""Typed effect boundaries for the future Gate A analyze use case."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from ..contracts.internal import (
    AnswerDraft,
    AnswerPlan,
    BeginRequest,
    BeginRequestResult,
    BoundedContextQuery,
    CompleteRequest,
    FailRequest,
    IdKind,
    MinimalConversationContext,
    RetrievalQuery,
    RetrievalResult,
    StageTrace,
    StoredResponse,
)


@runtime_checkable
class ChatStore(Protocol):
    """Durable request/message boundary; no SQLite type leaks through it."""

    def begin_request(self, command: BeginRequest) -> BeginRequestResult: ...

    def complete_request(self, command: CompleteRequest) -> StoredResponse: ...

    def fail_request(self, command: FailRequest) -> None: ...

    def load_bounded_context(self, query: BoundedContextQuery) -> MinimalConversationContext: ...


@runtime_checkable
class Retriever(Protocol):
    def retrieve(self, query: RetrievalQuery) -> RetrievalResult: ...


@runtime_checkable
class AnswerGenerator(Protocol):
    def generate(self, plan: AnswerPlan) -> AnswerDraft: ...


@runtime_checkable
class TraceSink(Protocol):
    def record_transition(self, event: StageTrace) -> None: ...


@runtime_checkable
class Clock(Protocol):
    def now_utc(self) -> datetime: ...

    def monotonic(self) -> float: ...


@runtime_checkable
class IdGenerator(Protocol):
    def new_id(self, kind: IdKind) -> str: ...


__all__ = [
    "AnswerGenerator",
    "ChatStore",
    "Clock",
    "IdGenerator",
    "Retriever",
    "TraceSink",
]
