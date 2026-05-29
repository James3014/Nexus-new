from __future__ import annotations

import pytest
from nexus.core.cost_evidence_contracts import CostEvidenceClass, derive_cost_evidence_class


@pytest.mark.parametrize(
    "fixture_name, inputs, expected_class",
    [
        # Fixture 1: clean model cost
        (
            "clean_model_cost",
            {
                "model_calls": 1,
                "provider_token_measured": True,
                "token_reliable": True,
                "runner_overhead_polluted": False,
                "local_success": False,
            },
            CostEvidenceClass.CLEAN_MODEL_COST,
        ),
        # Fixture 2: local winner + measured model call
        (
            "local_winner_with_measured_model_call",
            {
                "model_calls": 1,
                "provider_token_measured": True,
                "token_reliable": True,
                "runner_overhead_polluted": False,
                "local_success": True,
            },
            CostEvidenceClass.RESCUE_WITH_MODEL_FALLBACK_MEASURED,
        ),
        # Fixture 3: local winner + unmeasured model call
        (
            "local_winner_with_unmeasured_model_call",
            {
                "model_calls": 1,
                "provider_token_measured": False,
                "token_reliable": True,
                "runner_overhead_polluted": False,
                "local_success": True,
            },
            CostEvidenceClass.RESCUE_WITH_MODEL_FALLBACK,
        ),
        # Extra Boundary Cases for completeness
        (
            "no_model_call",
            {
                "model_calls": 0,
                "provider_token_measured": False,
                "token_reliable": True,
                "runner_overhead_polluted": False,
                "local_success": False,
            },
            CostEvidenceClass.NO_MODEL_CALL,
        ),
        (
            "rescue_only_no_model_call",
            {
                "model_calls": 0,
                "provider_token_measured": False,
                "token_reliable": True,
                "runner_overhead_polluted": False,
                "local_success": True,
            },
            CostEvidenceClass.RESCUE_ONLY_NO_MODEL_CALL,
        ),
        (
            "runner_overhead_polluted",
            {
                "model_calls": 1,
                "provider_token_measured": True,
                "token_reliable": True,
                "runner_overhead_polluted": True,
                "local_success": False,
            },
            CostEvidenceClass.RUNNER_OVERHEAD_POLLUTED,
        ),
        (
            "token_unreliable",
            {
                "model_calls": 1,
                "provider_token_measured": False,
                "token_reliable": True,
                "runner_overhead_polluted": False,
                "local_success": False,
            },
            CostEvidenceClass.TOKEN_UNRELIABLE,
        ),
    ],
)
def test_cost_evidence_class_characterization_fixtures(fixture_name, inputs, expected_class):
    """M2 Boundary: Verify that all standard cost characterization fixtures map correctly

    according to the centralized SSOT cost evidence contract.
    """
    result = derive_cost_evidence_class(**inputs)
    assert result == expected_class, f"Fixture {fixture_name} failed: expected {expected_class}, got {result}"
