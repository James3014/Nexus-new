"""#2824 review: an expected effect identity never matches a missing or empty stored attempt id."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from nexus.orchestrator.managed_local_agent import ManagedLocalAgentLauncher, ReconcileAction


def _launcher(state: dict) -> ManagedLocalAgentLauncher:
    service = SimpleNamespace(_read_state=lambda task_id: state)
    return ManagedLocalAgentLauncher(service=service)


@pytest.mark.parametrize(
    "stored", [{}, {"attempt_id": None}, {"attempt_id": ""}, {"attempt_id": 7}]
)
@pytest.mark.parametrize("expected", ["", "attempt-1"])
def test_expected_identity_never_matches_a_missing_or_empty_stored_id(stored, expected) -> None:
    res = _launcher({"status": "RUNNING", **stored}).reconcile_attempt(
        "t", expected_effect_identity=expected
    )
    assert res["action"] == ReconcileAction.BLOCK.value


def test_matching_non_empty_identity_still_reconciles() -> None:
    res = _launcher({"status": "RUNNING", "attempt_id": "attempt-1"}).reconcile_attempt(
        "t", expected_effect_identity="attempt-1"
    )
    assert res["action"] == ReconcileAction.RECONCILE_EXISTING.value
    assert res["attempt_id"] == "attempt-1"
