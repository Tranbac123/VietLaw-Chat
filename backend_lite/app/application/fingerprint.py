"""Canonical accepted-request and opaque retry-carrier digests.

The helpers are intentionally standalone.  A1 does not connect them to the
public route or to persistence, and it never logs or stores the raw carrier.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

FINGERPRINT_VERSION = "fingerprint-v1"
IDEMPOTENCY_KEY_DIGEST_VERSION = "idempotency-key-digest-v1"
_CARRIER_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{8,128}$")


class CanonicalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chat_id: str | None = Field(default=None, min_length=1, max_length=128)
    contract_version: str = "v1"
    language: str = Field(default="vi", min_length=2, max_length=16)
    question: str = Field(min_length=1, max_length=3000)
    session_id: str = Field(min_length=1, max_length=128)
    user_type: Literal["citizen", "household_business", "foreign_visitor", "unknown"] = "unknown"

    @field_validator("question")
    @classmethod
    def contract_trim_question(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("question must contain non-whitespace text")
        return value


def canonical_request_payload(request: CanonicalRequest | Mapping[str, object] | BaseModel) -> dict[str, object]:
    """Materialize contract defaults and return the fixed six-key payload."""

    if isinstance(request, CanonicalRequest):
        value = request
    else:
        if isinstance(request, BaseModel):
            request = request.model_dump(mode="python")
        allowed_keys = {"chat_id", "contract_version", "language", "question", "session_id", "user_type"}
        carrier_keys = {"idempotency_key", "Idempotency-Key", "idempotency_key_digest", "idempotency_key_version"}
        unknown_keys = set(request) - allowed_keys - carrier_keys
        if unknown_keys:
            raise ValueError(f"unknown request fields: {sorted(unknown_keys)}")
        value = CanonicalRequest.model_validate(
            {
                "chat_id": request.get("chat_id"),
                "contract_version": request.get("contract_version", "v1"),
                "language": request.get("language", "vi"),
                "question": request.get("question"),
                "session_id": request.get("session_id"),
                "user_type": request.get("user_type", "unknown"),
            }
        )
    return value.model_dump(mode="python")


def canonical_request_json(request: CanonicalRequest | Mapping[str, object] | BaseModel) -> bytes:
    payload = canonical_request_payload(request)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def fingerprint_request(request: CanonicalRequest | Mapping[str, object] | BaseModel) -> str:
    """Return the lower-case SHA-256 digest for the accepted payload."""

    return hashlib.sha256(canonical_request_json(request)).hexdigest()


def compute_request_fingerprint(request: CanonicalRequest | Mapping[str, object] | BaseModel) -> str:
    """Descriptive alias for callers that prefer an explicit operation name."""

    return fingerprint_request(request)


def validate_idempotency_key(value: str) -> str:
    """Validate only the safe opaque-header shape; do not interpret semantics."""

    if not isinstance(value, str) or not _CARRIER_PATTERN.fullmatch(value):
        raise ValueError("idempotency key must be 8-128 ASCII token characters")
    return value


def digest_idempotency_key(value: str) -> str:
    """Return the digest only; the raw header is never retained or logged."""

    return hashlib.sha256(validate_idempotency_key(value).encode("utf-8")).hexdigest()


def idempotency_key_digest(value: str) -> str:
    return digest_idempotency_key(value)


__all__ = [
    "CanonicalRequest",
    "FINGERPRINT_VERSION",
    "IDEMPOTENCY_KEY_DIGEST_VERSION",
    "canonical_request_json",
    "canonical_request_payload",
    "compute_request_fingerprint",
    "digest_idempotency_key",
    "fingerprint_request",
    "idempotency_key_digest",
    "validate_idempotency_key",
]
