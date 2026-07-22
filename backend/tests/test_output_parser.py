"""Output parser. Whitelist-only, subset ids, safe fallback."""
from pathlib import Path

import pytest

from app.llm.output_parser import parse_content_or_fallback
from app.nlp.patterns import PatternBank
from app.schemas import Domain

_DATA = Path(__file__).resolve().parents[2] / "data" / "unsafe_patterns.json"


@pytest.fixture(scope="module")
def bank():
    return PatternBank.load(str(_DATA))


def test_parses_valid_json_and_drops_extra_fields(bank):
    raw = """{"summary":"tóm tắt","clarifying_questions":["a?"],"checklist":["b"],
    "next_steps":["c"],"used_source_ids":["civil_deposit_001"],
    "domain":"HACK","sources":[{"id":"x"}],"safety_notice":"evil"}"""
    c, err = parse_content_or_fallback(raw, ["civil_deposit_001"], Domain.civil_dispute, bank)
    assert err is False
    assert c.summary == "tóm tắt"
    assert c.used_source_ids == ["civil_deposit_001"]
    # extra fields are not on LLMContent at all
    assert not hasattr(c, "domain") or c.__class__.__name__ == "LLMContent"


def test_parses_markdown_fenced_json(bank):
    raw = "```json\n{\"summary\":\"x\",\"clarifying_questions\":[],\"checklist\":[],\"next_steps\":[],\"used_source_ids\":[]}\n```"
    c, err = parse_content_or_fallback(raw, [], Domain.traffic, bank)
    assert err is False
    assert c.summary == "x"


def test_invalid_json_falls_back(bank):
    c, err = parse_content_or_fallback("not json at all", [], Domain.civil_dispute, bank)
    assert err is True
    assert c.clarifying_questions  # fallback provides cautious content


def test_missing_summary_falls_back(bank):
    raw = '{"clarifying_questions":["a"],"checklist":[],"next_steps":[],"used_source_ids":[]}'
    c, err = parse_content_or_fallback(raw, [], Domain.civil_dispute, bank)
    assert err is True


def test_used_source_ids_filtered_to_retrieved(bank):
    raw = '{"summary":"x","clarifying_questions":[],"checklist":[],"next_steps":[],"used_source_ids":["civil_deposit_001","INVENTED_999"]}'
    c, err = parse_content_or_fallback(raw, ["civil_deposit_001"], Domain.civil_dispute, bank)
    assert c.used_source_ids == ["civil_deposit_001"]


def test_nonlist_fields_are_coerced(bank):
    raw = '{"summary":"x","clarifying_questions":"oops","checklist":null,"next_steps":["c"],"used_source_ids":[]}'
    c, err = parse_content_or_fallback(raw, [], Domain.civil_dispute, bank)
    assert err is False
    assert c.clarifying_questions == []
    assert c.checklist == []
    assert c.next_steps == ["c"]
