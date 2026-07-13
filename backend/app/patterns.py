"""Loader for data/unsafe_patterns.json — the deterministic classifier data.

Each pattern group carries expected_domain/risk/decision + a safe_response_hint,
tuned to the golden/demo cases. Patterns are folded to accent-insensitive form at
load time so no-diacritics input matches for free.
"""
import json
from dataclasses import dataclass, field
from typing import Optional

from app.errors import RetrievalError
from app.input_normalizer import strip_accents


def _fold(s: str) -> str:
    return strip_accents(s.lower())


@dataclass(frozen=True)
class PatternGroup:
    id: str
    category: str
    kind: str  # unsafe | high_risk | medium | low | unsupported
    folded_patterns: tuple[str, ...]
    expected_domain: Optional[str] = None
    expected_risk: Optional[str] = None
    expected_decision: Optional[str] = None
    safe_response_hint: Optional[str] = None

    def match(self, ai_text: str) -> bool:
        return any(p in ai_text for p in self.folded_patterns)


def _group(d: dict, kind: str) -> PatternGroup:
    return PatternGroup(
        id=d["id"],
        category=d.get("category", ""),
        kind=kind,
        folded_patterns=tuple(_fold(p) for p in d["patterns"]),
        expected_domain=d.get("expected_domain"),
        expected_risk=d.get("expected_risk"),
        expected_decision=d.get("expected_decision"),
        safe_response_hint=d.get("safe_response_hint"),
    )


@dataclass
class PatternBank:
    unsafe: list[PatternGroup] = field(default_factory=list)
    high_risk: list[PatternGroup] = field(default_factory=list)
    medium: list[PatternGroup] = field(default_factory=list)
    low: list[PatternGroup] = field(default_factory=list)
    unsupported: list[PatternGroup] = field(default_factory=list)
    forbidden_output_phrases: tuple[str, ...] = ()
    safe_replacement_phrases: dict = field(default_factory=dict)
    matching_rules: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str) -> "PatternBank":
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, json.JSONDecodeError) as e:
            raise RetrievalError(f"cannot load unsafe patterns: {e}") from e
        return cls(
            unsafe=[_group(g, "unsafe") for g in d.get("unsafe_intent_patterns", [])],
            high_risk=[_group(g, "high_risk") for g in d.get("high_risk_patterns", [])],
            medium=[_group(g, "medium") for g in d.get("medium_risk_patterns", [])],
            low=[_group(g, "low") for g in d.get("low_risk_patterns", [])],
            unsupported=[_group(g, "unsupported") for g in d.get("unsupported_patterns", [])],
            forbidden_output_phrases=tuple(d.get("forbidden_output_phrases", [])),
            safe_replacement_phrases=d.get("safe_replacement_phrases", {}),
            matching_rules=d.get("matching_rules", {}),
        )
