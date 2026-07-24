from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend_lite.app.schemas.api import AnalyzeResponse
from backend_lite.app.schemas.content import AnalyzeContent, Confidence, SourceObject


def _source() -> SourceObject:
    return SourceObject(
        id="s1", title="t", source_name="n", url=None, snippet="text",
        source_type="official_source", last_checked="2026-01-01",
    )


def _confidence() -> Confidence:
    return Confidence(domain=0.9, risk=0.1, answer=0.8)


def _legal_kwargs(**ov) -> dict:
    base = dict(
        domain="civil_dispute", risk_level="low", decision="answer_with_guidance",
        summary="s", clarifying_questions=[], checklist=[], next_steps=[],
        sources=[], safety_notice="n", confidence=_confidence(), metadata={},
    )
    base.update(ov)
    return base


def _social_kwargs(**ov) -> dict:
    base = dict(
        domain=None, risk_level=None, decision=None,
        summary="s", clarifying_questions=[], checklist=[], next_steps=[],
        sources=[], safety_notice="n", confidence=None, metadata={},
    )
    base.update(ov)
    return base


def _response_extra() -> dict:
    return dict(contract_version="v1", request_id="r", chat_id="c",
                user_message_id="u", assistant_message_id="a")


def _build_response(**kwargs) -> AnalyzeResponse:
    return AnalyzeResponse(**_response_extra(), **kwargs)


def _build_content(**kwargs) -> AnalyzeContent:
    return AnalyzeContent(**kwargs)


BUILDERS = {"AnalyzeResponse": _build_response, "AnalyzeContent": _build_content}


# --- (13)-(14) valid social / legal states pass, for both models -----------

@pytest.mark.parametrize("name,build", BUILDERS.items())
def test_valid_social_state_passes(name, build):
    obj = build(response_kind="social", **_social_kwargs())
    assert obj.response_kind == "social"


@pytest.mark.parametrize("name,build", BUILDERS.items())
def test_valid_legal_state_passes(name, build):
    obj = build(response_kind="legal", **_legal_kwargs())
    assert obj.response_kind == "legal"


# --- (15)-(16) legacy: response_kind omitted passes, serialization omits it -

@pytest.mark.parametrize("name,build", BUILDERS.items())
def test_legacy_omitted_response_kind_passes(name, build):
    obj = build(**_legal_kwargs())
    assert obj.response_kind == "legal"
    assert "response_kind" not in obj.model_dump()
    assert "response_kind" not in obj.model_dump_json()


# --- (17)-(18) explicit social/legal serialize response_kind ---------------

@pytest.mark.parametrize("name,build", BUILDERS.items())
def test_explicit_social_serializes_response_kind(name, build):
    obj = build(response_kind="social", **_social_kwargs())
    assert obj.model_dump()["response_kind"] == "social"


@pytest.mark.parametrize("name,build", BUILDERS.items())
def test_explicit_legal_serializes_response_kind(name, build):
    obj = build(response_kind="legal", **_legal_kwargs())
    assert obj.model_dump()["response_kind"] == "legal"


# --- (19) unrelated metadata remains serialized -----------------------------

@pytest.mark.parametrize("name,build", BUILDERS.items())
def test_unrelated_metadata_remains_serialized(name, build):
    obj = build(**_legal_kwargs(metadata={"marker": "keep-me"}))
    assert obj.model_dump()["metadata"] == {"marker": "keep-me"}


# --- (20) explicit response_kind survives API-to-content persistence -------

def test_explicit_response_kind_survives_persistence_round_trip():
    response = _build_response(response_kind="social", **_social_kwargs())
    dumped = response.model_dump(mode="json")
    content_fields = set(AnalyzeContent.model_fields)
    projected = {k: v for k, v in dumped.items() if k in content_fields}
    content = AnalyzeContent.model_validate(projected)
    assert content.response_kind == "social"
    assert "response_kind" in content.model_dump()


# --- (1)-(8) reject all eight invalid social states, per model -------------

_SOCIAL_VIOLATIONS = {
    "domain": _social_kwargs(domain="civil_dispute"),
    "risk_level": _social_kwargs(risk_level="low"),
    "decision": _social_kwargs(decision="answer_with_guidance"),
    "confidence": _social_kwargs(confidence=_confidence()),
    "sources": _social_kwargs(sources=[_source()]),
    "clarifying_questions": _social_kwargs(clarifying_questions=["q"]),
    "checklist": _social_kwargs(checklist=["c"]),
    "next_steps": _social_kwargs(next_steps=["n"]),
}


@pytest.mark.parametrize("name,build", BUILDERS.items())
@pytest.mark.parametrize("field,kwargs", _SOCIAL_VIOLATIONS.items())
def test_invalid_social_state_rejected(name, build, field, kwargs):
    with pytest.raises(ValidationError) as exc_info:
        build(response_kind="social", **kwargs)
    errors = exc_info.value.errors()
    assert len(errors) == 1
    assert errors[0]["type"] == "value_error"
    assert errors[0]["loc"] == ()


# --- (9)-(12) reject all four invalid legal states, per model --------------

_LEGAL_VIOLATIONS = {
    "domain": _legal_kwargs(domain=None),
    "risk_level": _legal_kwargs(risk_level=None),
    "decision": _legal_kwargs(decision=None),
    "confidence": _legal_kwargs(confidence=None),
}


@pytest.mark.parametrize("name,build", BUILDERS.items())
@pytest.mark.parametrize("field,kwargs", _LEGAL_VIOLATIONS.items())
def test_invalid_legal_state_rejected(name, build, field, kwargs):
    with pytest.raises(ValidationError) as exc_info:
        build(response_kind="legal", **kwargs)
    errors = exc_info.value.errors()
    assert len(errors) == 1
    assert errors[0]["type"] == "value_error"
    assert errors[0]["loc"] == ()
