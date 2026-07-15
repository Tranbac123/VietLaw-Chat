"""Deterministic content templates."""
from pathlib import Path

import pytest

from app import content_templates as ct
from app.patterns import PatternBank
from app.schemas import Decision, Domain
from app.unsafe_intent_detector import detect
from app.input_normalizer import normalize

_DATA = Path(__file__).resolve().parents[2] / "data" / "unsafe_patterns.json"


@pytest.fixture(scope="module")
def bank():
    return PatternBank.load(str(_DATA))


@pytest.mark.parametrize("domain", list(Domain))
def test_template_questions_and_checklist_nonempty(domain):
    assert ct.template_questions(domain)
    assert ct.template_checklist(domain)


def test_refusal_content_is_safe(bank):
    u = detect(normalize("Làm sao để giấu chứng cứ?").accent_insensitive, bank)
    c = ct.refusal_content(u, bank)
    assert "không thể" in c.summary.lower()
    assert c.used_source_ids == []
    # Negated prohibitions ("không ... làm giả") are safe; only enabling/tactical
    # phrasing is forbidden.
    joined = " ".join(c.next_steps + c.checklist).lower()
    for tactical in ("cách làm giả", "cách giấu chứng cứ", "mẹo né phạt", "cách né phạt"):
        assert tactical not in joined


def test_escalation_content_recommends_professional(bank):
    c = ct.escalation_content(Domain.high_risk, bank)
    joined = " ".join(c.next_steps).lower()
    assert "luật sư" in joined or "cơ quan" in joined


def test_unsupported_language_mentions_vietnamese(bank):
    c = ct.unsupported_content(bank, reason="language")
    assert "tiếng việt" in c.summary.lower()
    assert c.checklist == []
    assert c.used_source_ids == []


def test_unsupported_non_legal(bank):
    c = ct.unsupported_content(bank, reason="non_legal")
    assert c.summary
    assert c.used_source_ids == []


def test_fallback_content_is_cautious(bank):
    c = ct.fallback_content(Domain.civil_dispute, bank)
    assert c.clarifying_questions
    assert c.used_source_ids == []
