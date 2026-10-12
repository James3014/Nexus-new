"""Hermetic research provider for services tests.

The research executor now passes the real task to ResearchPhaseHandler, which would call the
external chub/felo providers (network, ``~/.openclaw`` cache).  Canary and closure tests must not
depend on either, so the provider and cache are replaced by a deterministic offline stub.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _hermetic_research_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from nexus.engine.phases.research import ResearchPhaseHandler

    def offline_provider(self: Any, query: str) -> dict[str, Any]:
        return {
            "findings": [f"offline research stub: {query[:120]}"],
            "source": "offline_test_stub",
            "status": "SUCCESS",
            "tokens_used": 0,
        }

    # keep the real egress path reachable for tests that exercise the authorization gate
    monkeypatch.setattr(
        ResearchPhaseHandler,
        "_real_run_external_research",
        ResearchPhaseHandler._run_external_research,
        raising=False,
    )
    monkeypatch.setattr(ResearchPhaseHandler, "_run_external_research", offline_provider)
    monkeypatch.setattr(ResearchPhaseHandler, "_get_lancedb", lambda self: None)
