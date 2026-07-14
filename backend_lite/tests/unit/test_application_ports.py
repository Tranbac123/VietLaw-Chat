from __future__ import annotations

import inspect

from backend_lite.app.application.ports import (
    AnswerGenerator,
    ChatStore,
    Clock,
    IdGenerator,
    Retriever,
    TraceSink,
)
from backend_lite.app.contracts.internal import IdKind


def test_ports_have_required_typed_use_case_methods() -> None:
    assert set(ChatStore.__dict__) >= {
        "begin_request",
        "complete_request",
        "fail_request",
        "load_bounded_context",
    }
    assert "retrieve" in Retriever.__dict__
    assert "generate" in AnswerGenerator.__dict__
    assert "record_transition" in TraceSink.__dict__
    assert set(Clock.__dict__) >= {"now_utc", "monotonic"}
    assert "new_id" in IdGenerator.__dict__
    assert "Any" not in inspect.getsource(__import__("backend_lite.app.application.ports", fromlist=["ports"]))


def test_fake_ports_satisfy_protocol_shape_without_concrete_adapters() -> None:
    class FakeStore:
        def begin_request(self, command): ...
        def complete_request(self, command): ...
        def fail_request(self, command): ...
        def load_bounded_context(self, query): ...

    class FakeRetriever:
        def retrieve(self, query): ...

    class FakeGenerator:
        def generate(self, plan): ...

    class FakeTrace:
        def record_transition(self, event): ...

    class FakeClock:
        def now_utc(self): ...
        def monotonic(self): ...

    class FakeIds:
        def new_id(self, kind: IdKind): ...

    assert isinstance(FakeStore(), ChatStore)
    assert isinstance(FakeRetriever(), Retriever)
    assert isinstance(FakeGenerator(), AnswerGenerator)
    assert isinstance(FakeTrace(), TraceSink)
    assert isinstance(FakeClock(), Clock)
    assert isinstance(FakeIds(), IdGenerator)
