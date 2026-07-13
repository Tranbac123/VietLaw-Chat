"""Schema/contract tests."""
import pytest
from pydantic import ValidationError

from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    Source,
    Confidence,
    GuardsApplied,
    Metadata,
    LLMContent,
    ErrorResponse,
    Domain,
    RiskLevel,
    Decision,
    UserType,
)


# ---- enums (exact contract values) ----

def test_domain_values():
    assert {d.value for d in Domain} == {
        "civil_dispute", "traffic", "household_business",
        "administrative", "high_risk", "unknown",
    }


def test_risk_values():
    assert {r.value for r in RiskLevel} == {"low", "medium", "high"}


def test_decision_values():
    assert {d.value for d in Decision} == {
        "answer_with_guidance", "ask_clarifying_questions",
        "recommend_professional_help", "refuse_unsafe_request", "unsupported",
    }


# ---- AnalyzeRequest ----

def test_request_defaults():
    r = AnalyzeRequest(question="Tôi thuê nhà bị giữ cọc", session_id="s1")
    assert r.user_type == UserType.unknown
    assert r.language == "vi"
    assert r.chat_id is None


def test_request_strips_question_whitespace():
    r = AnalyzeRequest(question="   xin chào luật   ", session_id="s1")
    assert r.question == "xin chào luật"


def test_request_rejects_too_short_after_strip():
    with pytest.raises(ValidationError):
        AnalyzeRequest(question="  a ", session_id="s1")


def test_request_rejects_too_long():
    with pytest.raises(ValidationError):
        AnalyzeRequest(question="x" * 3001, session_id="s1")


# ---- Source ----

def test_source_url_optional():
    s = Source(
        id="civil_deposit_001",
        title="Đặt cọc",
        source_name="BLDS 2015 - Điều 328",
        snippet="Đặt cọc là...",
        source_type="official_source",
        last_checked="2026-07-10",
    )
    assert s.url is None


def test_source_requires_id():
    with pytest.raises(ValidationError):
        Source(
            title="x", source_name="y", snippet="z",
            source_type="official_source", last_checked="2026-07-10",
        )


# ---- LLMContent (whitelist the parser produces) ----

def test_llm_content_shape():
    c = LLMContent(
        summary="tóm tắt",
        clarifying_questions=["a?"],
        checklist=["b"],
        next_steps=["c"],
        used_source_ids=["civil_deposit_001"],
    )
    assert c.used_source_ids == ["civil_deposit_001"]


# ---- Confidence bounds ----

def test_confidence_rejects_out_of_range():
    with pytest.raises(ValidationError):
        Confidence(domain=1.5, risk=0.5, answer=0.5)


# ---- AnalyzeResponse (full successful shape) ----

def _valid_response_kwargs():
    return dict(
        request_id="req_1",
        chat_id="chat_1",
        user_message_id="msg_user_1",
        assistant_message_id="msg_asst_1",
        domain=Domain.civil_dispute,
        risk_level=RiskLevel.medium,
        decision=Decision.ask_clarifying_questions,
        summary="tóm tắt",
        clarifying_questions=[],
        checklist=[],
        next_steps=[],
        sources=[],
        safety_notice="notice",
        confidence=Confidence(domain=0.8, risk=0.7, answer=0.6),
        metadata=Metadata(
            retrieval_count=0, has_sources=False, retrieval_strategy="none",
            used_llm=True, model_name="api-model", used_current_chat_history=False,
            history_message_count=0, unsafe_intent_detected=False,
            high_risk_detected=False, detected_topic=None, safety_flags=[],
            guards_applied=GuardsApplied(),
        ),
    )


def test_response_contract_version_is_v1():
    r = AnalyzeResponse(**_valid_response_kwargs())
    assert r.contract_version == "v1"


def test_response_arrays_are_lists():
    r = AnalyzeResponse(**_valid_response_kwargs())
    assert isinstance(r.sources, list)
    assert isinstance(r.clarifying_questions, list)


def test_response_rejects_missing_safety_notice():
    kw = _valid_response_kwargs()
    del kw["safety_notice"]
    with pytest.raises(ValidationError):
        AnalyzeResponse(**kw)


def test_guards_applied_defaults():
    g = GuardsApplied()
    assert g.citation_guard is True
    assert g.safety_guard is True
    assert g.fallback_used is False


# ---- ErrorResponse ----

def test_error_response_shape():
    e = ErrorResponse(
        request_id="req_e1",
        error={"code": "invalid_request", "message": "Question must not be empty."},
        safety_notice="notice",
    )
    assert e.contract_version == "v1"
    assert e.error.code == "invalid_request"
