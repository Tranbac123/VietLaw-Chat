"""Strict, non-public contracts for the Gate A1 application boundary."""

from .internal import *  # noqa: F403 - this package is the internal contract surface
from .internal import __all__ as _internal_all
from .state import AnalysisState

__all__ = [*_internal_all, "AnalysisState"]
