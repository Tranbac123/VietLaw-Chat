"""Meaning-preserving deterministic question normalization."""

from __future__ import annotations

import re
import unicodedata

from .analysis_state import AnalysisInvariantError

_WHITESPACE = re.compile(r"\s+")


def normalize_question(raw_question: str) -> str:
    if not isinstance(raw_question, str):
        raise AnalysisInvariantError("current question must be text")
    normalized = _WHITESPACE.sub(" ", unicodedata.normalize("NFC", raw_question)).strip()
    if not normalized:
        raise AnalysisInvariantError("current question must not be blank")
    return normalized


__all__ = ["normalize_question"]
