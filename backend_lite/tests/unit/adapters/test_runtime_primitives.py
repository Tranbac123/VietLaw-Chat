from __future__ import annotations

from datetime import timezone

import pytest

import backend_lite.app.adapters.runtime_primitives as runtime_primitives
from backend_lite.app.adapters.runtime_primitives import PrefixedUuidIdGenerator, SystemClock
from backend_lite.app.contracts.internal import IdKind


def test_system_clock_is_utc_aware_and_monotonic_source_is_non_decreasing() -> None:
    clock = SystemClock()
    first = clock.now_utc()
    second = clock.now_utc()
    assert first.tzinfo is not None
    assert first.utcoffset() == timezone.utc.utcoffset(first)
    assert clock.monotonic() <= clock.monotonic()
    assert second.tzinfo is not None


@pytest.mark.parametrize(
    ("kind", "prefix"),
    [
        (IdKind.REQUEST, "req_"),
        (IdKind.CHAT, "chat_"),
        (IdKind.USER_MESSAGE, "msg_user_"),
        (IdKind.ASSISTANT_MESSAGE, "msg_asst_"),
    ],
)
def test_id_prefixes_and_uniqueness(kind: IdKind, prefix: str) -> None:
    generator = PrefixedUuidIdGenerator()
    values = {generator.new_id(kind) for _ in range(20)}
    assert len(values) == 20
    assert all(value.startswith(prefix) for value in values)


def test_prefix_mapping_cannot_be_mutated() -> None:
    assert not isinstance(vars(PrefixedUuidIdGenerator).get("_prefixes"), dict)
    with pytest.raises(TypeError):
        runtime_primitives._PREFIXES[IdKind.REQUEST] = "bad"  # type: ignore[index]


def test_request_prefix_unchanged() -> None:
    assert PrefixedUuidIdGenerator().new_id(IdKind.REQUEST).startswith("req_")


def test_chat_prefix_unchanged() -> None:
    assert PrefixedUuidIdGenerator().new_id(IdKind.CHAT).startswith("chat_")


def test_user_message_prefix_unchanged() -> None:
    assert PrefixedUuidIdGenerator().new_id(IdKind.USER_MESSAGE).startswith("msg_user_")


def test_assistant_message_prefix_unchanged() -> None:
    assert PrefixedUuidIdGenerator().new_id(IdKind.ASSISTANT_MESSAGE).startswith("msg_asst_")


def test_unknown_id_kind_fails_loud() -> None:
    with pytest.raises(ValueError, match="unknown ID kind"):
        PrefixedUuidIdGenerator().new_id("unknown")  # type: ignore[arg-type]
