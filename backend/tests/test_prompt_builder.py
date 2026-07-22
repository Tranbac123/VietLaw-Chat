"""Prompt builder."""
from app.llm.prompt_builder import build_prompt
from app.rag.rag_retriever import Retriever, load_snippets
from app.schemas import Decision, Domain, RiskLevel
from app.nlp.input_normalizer import normalize
from pathlib import Path

_PACK = Path(__file__).resolve().parents[2] / "data" / "legal_snippets.json"


def _sources():
    r = Retriever(load_snippets(str(_PACK)))
    return r.retrieve(normalize("Tôi thuê nhà giữ tiền cọc"),
                      domain=Domain.civil_dispute, decision=Decision.ask_clarifying_questions)


def test_prompt_contains_question_classification_sources_and_constraints():
    src = _sources()
    p = build_prompt("Tôi thuê nhà giữ tiền cọc?", context_summary="", domain=Domain.civil_dispute,
                     risk_level=RiskLevel.medium, decision=Decision.ask_clarifying_questions,
                     sources=src.sources, allowed_source_ids=src.allowed_source_ids)
    assert "Tôi thuê nhà giữ tiền cọc?" in p
    assert "civil_dispute" in p
    assert "JSON" in p
    assert "used_source_ids" in p
    assert src.allowed_source_ids[0] in p
    # must not instruct the LLM to emit backend-owned fields
    assert "tiếng việt" in p.lower() or "vietnamese" in p.lower()


def test_prompt_without_sources_asks_for_caution():
    p = build_prompt("Câu hỏi lạ?", context_summary="", domain=Domain.unknown,
                     risk_level=RiskLevel.low, decision=Decision.ask_clarifying_questions,
                     sources=[], allowed_source_ids=[])
    assert "nguồn" in p.lower()
