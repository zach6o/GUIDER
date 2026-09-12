"""Compatibility shim. The implementation moved to `app.providers` in PR-1.

Kept so existing imports and tests continue to resolve unchanged. Remove once
callers import from `app.providers` directly.
"""

from app.providers.base import AnalysisProvider
from app.providers.fixture import FixtureProvider, python_fixture

__all__ = ["AnalysisProvider", "FixtureProvider", "python_fixture"]
