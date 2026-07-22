"""RAG retrieval (rag_001..rag_013)."""
from pathlib import Path

import pytest

from app.errors import RetrievalError
from app.nlp.input_normalizer import normalize
from app.rag.rag_retriever import Retriever, load_snippets
from app.schemas import Decision, Domain

_PACK = Path(__file__).resolve().parents[2] / "data" / "legal_snippets.json"


@pytest.fixture(scope="module")
def retriever():
    return Retriever(load_snippets(str(_PACK)))


def _ids(result):
    return [s.id for s in result.sources]


def _r(retriever, q, domain, decision, detected_topic=None, context_terms=""):
    return retriever.retrieve(
        normalize(q), domain=domain, decision=decision,
        detected_topic=detected_topic, context_terms=context_terms,
    )


# ---- load / validate ----

def test_load_missing_file_raises_retrieval_error():
    with pytest.raises(RetrievalError):
        load_snippets(str(_PACK.parent / "nope.json"))


def test_load_returns_all_snippets(retriever):
    assert len(retriever.snippets) == 26


# ---- demo-domain retrieval (rag_001..004) ----

def test_rag_001_deposit_returns_civil_source(retriever):
    r = _r(retriever, "Tôi thuê nhà, chủ nhà giữ tiền cọc không trả.",
           Domain.civil_dispute, Decision.ask_clarifying_questions)
    assert r.has_sources
    assert any(i.startswith("civil_") for i in _ids(r))


def test_rag_003_traffic_returns_traffic_source(retriever):
    r = _r(retriever, "Tôi bị phạt giao thông nhưng không hiểu lỗi.",
           Domain.traffic, Decision.ask_clarifying_questions)
    assert any(i.startswith("traffic_") for i in _ids(r))


def test_rag_004_food_returns_business_source(retriever):
    r = _r(retriever, "Tôi muốn bán đồ ăn online ở quê cần giấy tờ gì?",
           Domain.household_business, Decision.answer_with_guidance)
    assert any(i.startswith("business_") for i in _ids(r))


# ---- top_k cap ----

def test_returns_at_most_three(retriever):
    r = _r(retriever, "Tôi thuê nhà, chủ nhà giữ tiền cọc không trả.",
           Domain.civil_dispute, Decision.ask_clarifying_questions)
    assert r.retrieval_count <= 3
    assert r.allowed_source_ids == [s.id for s in r.sources]


# ---- unsafe / high-risk (rag_005..007) ----

def test_rag_005_ne_phat_no_harmful_source(retriever):
    r = _r(retriever, "Làm sao để né phạt giao thông?",
           Domain.high_risk, Decision.refuse_unsafe_request, detected_topic="traffic")
    # Only safety/high-risk sources allowed; never a how-to.
    for s in r.sources:
        assert s.domain == "high_risk"
        assert s.source_type in ("safety_policy", "official_source", "procedure", "curated_note")


def test_rag_007_police_returns_high_risk_source(retriever):
    r = _r(retriever, "Tôi bị công an mời làm việc.",
           Domain.high_risk, Decision.recommend_professional_help)
    assert any(i.startswith("high_risk_") for i in _ids(r))


# ---- no-source (rag_008, rag_009) ----

def test_rag_008_poem_returns_no_source(retriever):
    r = _r(retriever, "Viết cho tôi bài thơ tình.", Domain.unknown, Decision.unsupported)
    assert not r.has_sources
    assert r.sources == []


def test_rag_009_unrelated_returns_empty(retriever):
    r = _r(retriever, "Hôm nay trời đẹp tôi muốn đi dạo công viên.",
           Domain.unknown, Decision.unsupported)
    assert r.retrieval_count == 0
    assert r.has_sources is False


# ---- no-diacritics (rag_012, rag_013) ----

def test_rag_012_no_diacritics_deposit(retriever):
    r = _r(retriever, "toi thue nha chu nha giu tien coc khong tra",
           Domain.civil_dispute, Decision.ask_clarifying_questions)
    assert any(i.startswith("civil_") for i in _ids(r))


def test_rag_013_no_diacritics_food(retriever):
    r = _r(retriever, "toi muon ban do an online o que can giay to gi",
           Domain.household_business, Decision.answer_with_guidance)
    assert any(i.startswith("business_") for i in _ids(r))


# ---- follow-up with/without context (rag_011, rag_011b) ----

def test_rag_011_followup_with_context_retrieves(retriever):
    r = _r(retriever, "Vậy tôi cần chuẩn bị giấy tờ gì?",
           Domain.civil_dispute, Decision.ask_clarifying_questions,
           context_terms="thuê nhà tiền cọc hợp đồng chủ nhà giữ cọc")
    assert r.has_sources
    assert any(i.startswith("civil_") for i in _ids(r))


def test_rag_011b_followup_without_context_empty(retriever):
    r = _r(retriever, "Vậy tôi cần chuẩn bị giấy tờ gì?",
           Domain.civil_dispute, Decision.ask_clarifying_questions)
    assert r.retrieval_count == 0


# ---- deprecated exclusion (rag_010, synthetic) ----

def test_deprecated_snippet_never_returned():
    raw = [
        {"id": "dep_1", "domain": "civil_dispute", "title": "Đặt cọc",
         "source_name": "X", "source_url": "", "source_type": "official_source",
         "status": "deprecated", "text": "đặt cọc tiền cọc thuê nhà hợp đồng",
         "plain_language_summary": "", "tags": ["dat_coc", "tien_coc", "thue_nha"],
         "risk_notes": [], "last_checked": "2026-07-10"},
    ]
    r = Retriever(raw).retrieve(
        normalize("Tôi thuê nhà giữ tiền cọc"), domain=Domain.civil_dispute,
        decision=Decision.ask_clarifying_questions,
    )
    assert r.retrieval_count == 0
