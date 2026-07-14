"""Injected runtime effects for the future Gate A composition root."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from types import MappingProxyType
from uuid import uuid4

from ..contracts.internal import IdKind


_PREFIXES = MappingProxyType(
    {
        IdKind.REQUEST: "req_",
        IdKind.CHAT: "chat_",
        IdKind.USER_MESSAGE: "msg_user_",
        IdKind.ASSISTANT_MESSAGE: "msg_asst_",
    }
)


class SystemClock:
    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def monotonic(self) -> float:
        return time.monotonic()


class PrefixedUuidIdGenerator:
    def new_id(self, kind: IdKind) -> str:
        try:
            normalized_kind = kind if isinstance(kind, IdKind) else IdKind(kind)
            prefix = _PREFIXES[normalized_kind]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"unknown ID kind: {kind!r}") from exc
        return f"{prefix}{uuid4().hex}"


__all__ = ["PrefixedUuidIdGenerator", "SystemClock"]
