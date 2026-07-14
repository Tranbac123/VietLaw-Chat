from __future__ import annotations

import pytest

from backend_lite.app.application.fingerprint import (
    FINGERPRINT_VERSION,
    IDEMPOTENCY_KEY_DIGEST_VERSION,
    canonical_request_json,
    digest_idempotency_key,
    fingerprint_request,
    validate_idempotency_key,
)


BASE = {
    "session_id": "session_001",
    "question": "Tôi thuê nhà, chủ nhà giữ tiền cọc.",
}


def test_fixed_unicode_vector_and_version() -> None:
    assert FINGERPRINT_VERSION == "fingerprint-v1"
    assert fingerprint_request(BASE) == "22bdd4b5389d6e72ba9421b04127fb85d2f2a8e8d68527f116265fca7a163e1b"
    assert canonical_request_json(BASE).decode().startswith('{"chat_id":null')


def test_json_order_and_absent_defaults_are_equivalent() -> None:
    first = {**BASE, "user_type": "unknown", "language": "vi", "chat_id": None}
    second = {
        "language": "vi",
        "question": BASE["question"],
        "chat_id": None,
        "session_id": BASE["session_id"],
        "user_type": "unknown",
    }
    assert fingerprint_request(first) == fingerprint_request(second) == fingerprint_request(BASE)


def test_only_boundary_trim_is_equivalent() -> None:
    assert fingerprint_request({**BASE, "question": f"  {BASE['question']}  "}) == fingerprint_request(BASE)
    assert fingerprint_request({**BASE, "question": "Tôi thuê  nhà, chủ nhà giữ tiền cọc."}) != fingerprint_request(BASE)
    assert fingerprint_request({**BASE, "question": BASE["question"].upper()}) != fingerprint_request(BASE)


def test_identity_fields_and_carrier_do_not_collide() -> None:
    assert fingerprint_request({**BASE, "session_id": "other"}) != fingerprint_request(BASE)
    assert fingerprint_request({**BASE, "chat_id": "chat_1"}) != fingerprint_request(BASE)
    assert fingerprint_request(BASE) == fingerprint_request({**BASE, "idempotency_key": "opaque-a"})


def test_unknown_fields_are_rejected_by_fingerprint_helper() -> None:
    with pytest.raises(ValueError, match="unknown request fields"):
        fingerprint_request({**BASE, "unexpected": True})


def test_carrier_digest_has_fixed_vector_and_never_returns_raw_key() -> None:
    key = "opaque-key-01"
    assert IDEMPOTENCY_KEY_DIGEST_VERSION == "idempotency-key-digest-v1"
    digest = digest_idempotency_key(key)
    assert digest == "ada033b6ec3b7d2c095f8cc05bee68c1157cd11cf60a19ea48cf2b68baf751a6"
    assert key not in digest
    assert len(digest) == 64
    assert digest == digest.lower()


def test_carrier_digest_fixed_vector_unchanged() -> None:
    assert IDEMPOTENCY_KEY_DIGEST_VERSION == "idempotency-key-digest-v1"
    assert digest_idempotency_key("opaque-key-01") == (
        "ada033b6ec3b7d2c095f8cc05bee68c1157cd11cf60a19ea48cf2b68baf751a6"
    )


def test_carrier_rejects_7_characters() -> None:
    with pytest.raises(ValueError):
        validate_idempotency_key("a" * 7)


def test_carrier_accepts_8_characters() -> None:
    value = "A._~-z09"
    assert len(value) == 8
    assert validate_idempotency_key(value) == value


def test_carrier_accepts_128_characters() -> None:
    value = "a" * 128
    assert validate_idempotency_key(value) == value


def test_carrier_rejects_129_characters() -> None:
    with pytest.raises(ValueError):
        validate_idempotency_key("a" * 129)


def test_carrier_rejects_unsafe_ascii() -> None:
    for value in ("a b123456", "a/b123456", "a:b123456", "a\\tb12345"):
        with pytest.raises(ValueError):
            validate_idempotency_key(value)


def test_carrier_rejects_non_ascii() -> None:
    for value in ("é" * 8, "ключ1234", "你好123456"):
        with pytest.raises(ValueError):
            validate_idempotency_key(value)


@pytest.mark.parametrize("value", ["", "a b", "a\nb", "a\tb", "x" * 256])
def test_carrier_shape_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError):
        validate_idempotency_key(value)
