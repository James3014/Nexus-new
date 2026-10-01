import json
from pathlib import Path


def test_automation_contract_does_not_activate_primary_cohort_in_wave1() -> None:
    payload = json.loads(
        Path("docs/research/hybrid_replication_v2/AUTOMATION_CONTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["status"] == "SOURCE_READY_PENDING_LIVE_ACTIVATION"
    assert payload["activation"]["t_auto"] is None
    assert payload["activation"]["wave1_must_not_create_primary_scoring_boundary"] is True
    assert (
        payload["superseded_provisional_boundary"]["status"]
        == "PRE_AUTOMATION_PROVISIONAL_GENERATION"
    )
    assert payload["superseded_provisional_boundary"]["primary_scoring_allowed"] is False
    assert len(payload["candidate_repositories"]) == 8
    assert payload["frozen_incumbent"]["dm1_top_probability_min"] == 0.7
    assert payload["frozen_incumbent"]["dm1_margin_min"] == 0.3


def test_daemon_is_fail_closed_on_capture_and_admission_gaps() -> None:
    text = Path("scripts/ops/hybrid_replication_daemon.py").read_text(encoding="utf-8")
    assert 'return 3' in text
    assert 'return 4' in text
    assert '"missing_capture"' in text
    assert '"missing_admission"' in text
    assert "ExternalFrozenStackRunner" in text
    assert "ExternalGroundTruthResolver" in text
