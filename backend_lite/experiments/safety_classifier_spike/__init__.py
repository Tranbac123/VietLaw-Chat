"""Gate A3a2c model-assisted safety-classifier strategy spike.

This package is intentionally outside ``backend_lite.app``.  Production code
must not import it; the spike may import the frozen deterministic kernel only to
measure the existing baseline.
"""

from .contract import (
    ClassifierRequest,
    ProviderResponse,
    SafetyClassificationCandidate,
    SupportingSpan,
)
from .strategy import BackendSafetyDecision, StrategyOutcome
from .validator import ClassifierValidationError, validate_candidate

__all__ = [
    "BackendSafetyDecision",
    "ClassifierRequest",
    "ClassifierValidationError",
    "ProviderResponse",
    "SafetyClassificationCandidate",
    "StrategyOutcome",
    "SupportingSpan",
    "validate_candidate",
]

