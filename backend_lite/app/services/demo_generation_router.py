"""DEMO scripted router: safety defer + scenario -> route mapping (pure).

The bounded safety-defer predicate runs (in the orchestrator) BEFORE scenario
classification. This module maps an already-classified :class:`DemoScenario`
(plus greeting/capability/source cues) to a route. Only deposit legal-guidance
and drafting spend a provider call; everything else is direct or POLICY_DIRECT.
This is NOT a production safety classifier.
"""

from __future__ import annotations

import re

from ..application.social_intent_detector import detect_social_intent
from ..contracts.conversation_intent import ConversationIntent
from ..contracts.demo_llm import DemoGenerationRoute, DemoRoute, DemoScenario, LLM_ROUTES
from .demo_deposit_extractor import normalize_for_eligibility

# Bounded, fail-closed demo safety-eligibility signals. A match only prevents the
# demo from OWNING the turn; the baseline pipeline still receives it. Matched on
# the eligibility-normalized text (separators collapsed), on word boundaries.
_RISK_SIGNALS = (
    "dao", "sung", "vu khi", "ma tau", "bom", "axit", "gay",
    "de doa", "doa danh", "doa giet", "hanh hung", "danh toi", "tan cong",
    "giet", "dam", "chem",
    "tu xu", "tra thu", "danh lai", "xu chu nha", "xu ly chu nha",
    "cong an", "canh sat", "bi bat", "bat giu", "dieu tra", "hinh su",
    "trieu tap", "moi lam viec", "khoi to",
)
_RISK_RE = re.compile(r"\b(?:" + "|".join(re.escape(s) for s in _RISK_SIGNALS) + r")\b")

_SOURCE_LOOKUP = ("nguon nao", "dung nguon", "su dung nguon", "vua dung nguon", "nguon gi", "trich dan nao")


def should_defer_demo_for_risk(text: str) -> bool:
    """True => the demo must NOT own this turn (defer to baseline). Overblocks by design."""

    return _RISK_RE.search(normalize_for_eligibility(text)) is not None


def _contains_any(text: str, cues: tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)


def route_demo(normalized_text: str, accentless_text: str, scenario: DemoScenario) -> DemoGenerationRoute:
    """Map social cues + an approved scenario to a route."""

    social = detect_social_intent(normalized_text)
    if social is ConversationIntent.GREETING:
        return _route(DemoRoute.SOCIAL_DIRECT, False, "demo.route.greeting.v1", DemoScenario.GREETING_DIRECT)
    if social in (ConversationIntent.IDENTITY_QUERY, ConversationIntent.CAPABILITY_QUERY):
        return _route(DemoRoute.CAPABILITY_DIRECT, False, "demo.route.capability.v1", DemoScenario.GREETING_DIRECT)
    if _contains_any(accentless_text, _SOURCE_LOOKUP):
        return _route(DemoRoute.SOURCE_LOOKUP_DIRECT, False, "demo.route.source_lookup.v1", DemoScenario.GREETING_DIRECT)

    if scenario is DemoScenario.DEPOSIT_FACT_UPDATE:
        return _route(DemoRoute.FACT_UPDATE_DIRECT, False, "demo.route.fact_update.v1", scenario)
    if scenario is DemoScenario.DEPOSIT_LEGAL_GUIDANCE:
        return _route(DemoRoute.LEGAL_GENERATION, True, "demo.route.legal_guidance.v1", scenario)
    if scenario is DemoScenario.DEPOSIT_DRAFT_REQUEST:
        return _route(DemoRoute.DOCUMENT_DRAFTING, True, "demo.route.drafting.v1", scenario)

    return _route(DemoRoute.POLICY_DIRECT, False, "demo.route.unsupported.v1", DemoScenario.UNSUPPORTED)


def _route(route: DemoRoute, llm: bool, reason: str, scenario: DemoScenario) -> DemoGenerationRoute:
    if llm:
        assert route in LLM_ROUTES
    return DemoGenerationRoute(route=route, llm_required=llm, reason_code=reason, scenario=scenario)


__all__ = ["route_demo", "should_defer_demo_for_risk"]
