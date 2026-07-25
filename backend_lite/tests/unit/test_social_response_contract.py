from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend_lite.app.schemas.api import AnalyzeResponse
from backend_lite.app.schemas.content import AnalyzeContent, Confidence

_LEGAL_IDS = dict(
    contract_version="v1",
    request_id="req_1",
    chat_id="chat_1",
    user_message_id="msg_user_1",
    assistant_message_id="msg_asst_1",
)


def _legal_response(**overrides: object) -> AnalyzeResponse:
    fields: dict[str, object] = {
        **_LEGAL_IDS,
        "domain": "civil_dispute",
        "risk_level": "low",
        "decision": "answer_with_guidance",
        "summary": "Tóm tắt.",
        "clarifying_questions": [],
        "checklist": ["Chuẩn bị hợp đồng thuê nhà."],
        "next_steps": ["Liên hệ chủ nhà bằng văn bản."],
        "sources": [],
        "safety_notice": "Thông tin tham khảo.",
        "confidence": Confidence(domain=0.8, risk=0.7, answer=0.6),
        "metadata": {},
    }
    fields.update(overrides)
    return AnalyzeResponse(**fields)


def _social_response(**overrides: object) -> AnalyzeResponse:
    fields: dict[str, object] = {
        **_LEGAL_IDS,
        "response_kind": "social",
        "domain": None,
        "risk_level": None,
        "decision": None,
        "summary": "Chào bạn, hôm nay tôi có thể hỗ trợ gì cho bạn?",
        "clarifying_questions": [],
        "checklist": [],
        "next_steps": [],
        "sources": [],
        "safety_notice": "",
        "confidence": None,
        "metadata": {"conversational_intent": "GREETING", "conversation_route": "DIRECT_RESPONSE"},
    }
    fields.update(overrides)
    return AnalyzeResponse(**fields)


# 1. Existing legal response defaults to legal.
def test_existing_legal_response_defaults_to_legal() -> None:
    # _legal_response() never sets response_kind explicitly, matching every
    # pre-existing LiteResponseBuilder.build() construction site.
    response = _legal_response()
    assert response.response_kind == "legal"


# 2. Valid legal response accepted.
def test_valid_legal_response_is_accepted() -> None:
    response = _legal_response(response_kind="legal")
    assert response.response_kind == "legal"
    assert response.domain == "civil_dispute"
    assert response.decision == "answer_with_guidance"


# 3. Valid social response accepted.
def test_valid_social_response_is_accepted() -> None:
    response = _social_response()
    assert response.response_kind == "social"
    assert response.domain is None
    assert response.risk_level is None
    assert response.decision is None
    assert response.confidence is None
    assert response.sources == []


# 4. Social + legal domain rejected.
def test_social_with_legal_domain_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _social_response(domain="civil_dispute")


# 5. Social + legal risk rejected.
def test_social_with_legal_risk_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _social_response(risk_level="low")


# 6. Social + legal Decision rejected.
def test_social_with_legal_decision_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _social_response(decision="answer_with_guidance")


def test_social_with_confidence_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _social_response(confidence=Confidence(domain=0.8, risk=0.7, answer=0.6))


# 7. Social + non-empty sources rejected.
def test_social_with_non_empty_sources_is_rejected() -> None:
    source = {
        "id": "s1",
        "title": "t",
        "source_name": "n",
        "snippet": "sn",
        "source_type": "legal_snippet",
        "last_checked": "2026-01-01",
    }
    with pytest.raises(ValidationError):
        _social_response(sources=[source])


# 8. Social + checklist/clarification rejected.
def test_social_with_checklist_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _social_response(checklist=["Something"])


def test_social_with_clarifying_questions_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _social_response(clarifying_questions=["Bạn có giấy tờ không?"])


def test_social_with_next_steps_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _social_response(next_steps=["Something"])


# 9. Legal + null legal fields rejected.
@pytest.mark.parametrize("field", ["domain", "risk_level", "decision", "confidence"])
def test_legal_with_null_legal_field_is_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        _legal_response(**{field: None})


# 10. Existing deposit metadata still validates.
def test_existing_deposit_metadata_still_validates() -> None:
    response = _legal_response(
        metadata={
            "retrieval_count": 2,
            "has_sources": True,
            "asked_question_ids": ["q_deposit_amount", "q_deposit_contract_date"],
            "guards_applied": {"citation_guard": True, "safety_guard": True, "fallback_used": False},
        }
    )
    assert response.metadata["asked_question_ids"] == ["q_deposit_amount", "q_deposit_contract_date"]


# --- AnalyzeContent (persisted projection) carries the same invariants ---


def test_analyze_content_social_defaults_and_validates() -> None:
    content = AnalyzeContent(
        response_kind="social",
        domain=None,
        risk_level=None,
        decision=None,
        summary="Chào bạn.",
        clarifying_questions=[],
        checklist=[],
        next_steps=[],
        sources=[],
        safety_notice="",
        confidence=None,
        metadata={},
    )
    assert content.response_kind == "social"


def test_analyze_content_legal_default_response_kind() -> None:
    content = AnalyzeContent(
        domain="civil_dispute",
        risk_level="low",
        decision="answer_with_guidance",
        summary="s",
        clarifying_questions=[],
        checklist=[],
        next_steps=[],
        sources=[],
        safety_notice="n",
        confidence=Confidence(domain=0.5, risk=0.5, answer=0.5),
        metadata={},
    )
    assert content.response_kind == "legal"


def test_analyze_content_social_with_legal_domain_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalyzeContent(
            response_kind="social",
            domain="civil_dispute",
            risk_level=None,
            decision=None,
            summary="s",
            clarifying_questions=[],
            checklist=[],
            next_steps=[],
            sources=[],
            safety_notice="",
            confidence=None,
            metadata={},
        )


def test_analyze_content_social_with_confidence_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalyzeContent(
            response_kind="social",
            domain=None,
            risk_level=None,
            decision=None,
            summary="s",
            clarifying_questions=[],
            checklist=[],
            next_steps=[],
            sources=[],
            safety_notice="",
            confidence=Confidence(domain=0.5, risk=0.5, answer=0.5),
            metadata={},
        )
