from backend_lite.app.application.analysis_state import BoundedPriorContext, ContextFact
from backend_lite.app.application.context_resolution import resolve_context


def test_current_explicit_fact_wins_and_conflict_is_recorded() -> None:
    current = (ContextFact("domain", "civil_dispute", "current_turn"),)
    prior = BoundedPriorContext((ContextFact("domain", "traffic", "prior_assistant", 3), ContextFact("document", "contract", "prior_assistant", 2)))
    result = resolve_context(current, prior)
    assert result.current_facts == current
    assert result.supporting_facts == (ContextFact("document", "contract", "prior_assistant", 2),)
    assert result.conflicts == ("domain",)


def test_prior_context_permutation_uses_newest_qualifying_fact() -> None:
    old, new = ContextFact("topic", "old", "prior_assistant", 1), ContextFact("topic", "new", "prior_assistant", 2)
    left = resolve_context((), BoundedPriorContext((old, new)))
    right = resolve_context((), BoundedPriorContext((new, old)))
    assert left == right
    assert left.supporting_facts == (new,)
