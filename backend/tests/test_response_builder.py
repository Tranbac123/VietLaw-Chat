"""Response builder."""
from pathlib import Path

import pytest

from app.config import SAFETY_NOTICE, Settings
from app.services.context_builder import Context
from app.rag.rag_retriever import Retriever, load_snippets
from app.nlp.input_normalizer import normalize
from app.services.response_builder import build
from app.schemas import AnalyzeResponse, Decision, Domain, LLMContent, RiskLevel

_PACK = Path(__file__).resolve().parents[2] / "data" / "legal_snippets.json"


@pytest.fixture(scope="module")
def retrieved():
    return Retriever(load_snippets(str(_PACK))).retrieve(
        normalize("Tôi thuê nhà giữ tiền cọc"),
        domain=Domain.civil_dispute, decision=Decision.ask_clarifying_questions)


def _build(content, retrieved, decision=Decision.ask_clarifying_questions, domain=Domain.civil_dispute):
    return build(
        request_id="req_1", chat_id="chat_1", user_message_id="mu_1",
        assistant_message_id="ma_1", domain=domain, risk_level=RiskLevel.medium,
        decision=decision, content=content, retrieved=retrieved,
        settings=Settings(_env_file=None), context=Context(),
        used_llm=True, unsafe_detected=False, detected_topic=None,
    )


def test_full_shape_and_constants(retrieved):
    c = LLMContent(summary="s", clarifying_questions=["q"], checklist=["k"],
                   next_steps=["n"], used_source_ids=[retrieved.sources[0].id])
    r = _build(c, retrieved)
    assert isinstance(r, AnalyzeResponse)
    assert r.contract_version == "v1"
    assert r.chat_id and r.user_message_id and r.assistant_message_id
    assert r.safety_notice == SAFETY_NOTICE


def test_sources_mapped_from_used_source_ids(retrieved):
    used = retrieved.sources[0].id
    c = LLMContent(summary="s", used_source_ids=[used])
    r = _build(c, retrieved)
    assert [s.id for s in r.sources] == [used]
    assert r.metadata.has_sources is True


def test_unsupported_path_has_no_sources(retrieved):
    c = LLMContent(summary="Ngoài phạm vi.", used_source_ids=[])
    r = _build(c, retrieved, decision=Decision.unsupported, domain=Domain.unknown)
    assert r.sources == []


def test_refuse_path_may_surface_retrieved_sources(retrieved):
    # refusal can show safety sources; it must not be forced empty.
    c = LLMContent(summary="Tôi không thể hỗ trợ.", used_source_ids=[])
    r = _build(c, retrieved, decision=Decision.refuse_unsafe_request, domain=Domain.high_risk)
    assert [s.id for s in r.sources] == [s.id for s in retrieved.sources]


def test_metadata_has_required_keys(retrieved):
    c = LLMContent(summary="s", used_source_ids=[])
    r = _build(c, retrieved)
    md = r.metadata
    for attr in ("retrieval_count", "has_sources", "retrieval_strategy", "used_llm",
                 "model_name", "used_current_chat_history", "history_message_count",
                 "unsafe_intent_detected", "high_risk_detected", "safety_flags",
                 "guards_applied"):
        assert hasattr(md, attr)
