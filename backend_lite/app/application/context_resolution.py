"""Current-turn-first bounded context resolution."""

from __future__ import annotations

from .analysis_state import AnalysisInvariantError, BoundedPriorContext, ContextFact, ResolvedContext


def resolve_context(
    current_facts: tuple[ContextFact, ...], prior: BoundedPriorContext
) -> ResolvedContext:
    if any(fact.provenance != "current_turn" for fact in current_facts):
        raise AnalysisInvariantError("current facts require current-turn provenance")
    current_by_key = {fact.key: fact for fact in current_facts}
    if len(current_by_key) != len(current_facts):
        raise AnalysisInvariantError("current fact keys must be unique")
    supporting: list[ContextFact] = []
    conflicts: list[str] = []
    seen: set[str] = set()
    ordered_prior = sorted(prior.facts, key=lambda fact: (-fact.recency, fact.key, fact.value))
    for fact in ordered_prior:
        if fact.provenance != "prior_assistant":
            raise AnalysisInvariantError("prior facts require prior-assistant provenance")
        current = current_by_key.get(fact.key)
        if current is not None:
            if current.value != fact.value:
                conflicts.append(fact.key)
            continue
        if fact.key not in seen:
            supporting.append(fact)
            seen.add(fact.key)
    return ResolvedContext(
        current_facts=tuple(sorted(current_facts, key=lambda fact: fact.key)),
        supporting_facts=tuple(supporting),
        unresolved_ambiguities=tuple(sorted(set(prior.unresolved_ambiguities))),
        conflicts=tuple(sorted(set(conflicts))),
    )


__all__ = ["resolve_context"]
