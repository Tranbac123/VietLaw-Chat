"""Citation guard."""
from app.guards.citation_guard import apply
from app.schemas import LLMContent


def _content(ids):
    return LLMContent(summary="x", clarifying_questions=[], checklist=[],
                      next_steps=[], used_source_ids=ids)


def test_valid_subset_unchanged():
    c, notes = apply(_content(["civil_deposit_001"]), ["civil_deposit_001", "civil_rental_001"])
    assert c.used_source_ids == ["civil_deposit_001"]
    assert notes is None


def test_invented_ids_removed_with_note():
    c, notes = apply(_content(["civil_deposit_001", "FAKE_999"]), ["civil_deposit_001"])
    assert c.used_source_ids == ["civil_deposit_001"]
    assert notes and "FAKE_999" in notes


def test_all_ids_cleared_when_nothing_retrieved():
    c, notes = apply(_content(["civil_deposit_001"]), [])
    assert c.used_source_ids == []
    assert notes is not None
