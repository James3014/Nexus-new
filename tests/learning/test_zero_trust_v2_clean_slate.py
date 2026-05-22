from __future__ import annotations

from nexus.learning.zero_trust_v2_clean_slate import build_baseline_sandwich, validate_clean_slate_contract


def test_clean_baseline_sandwich_passes() -> None:
    contract = build_baseline_sandwich(
        baseline_before_hash="same",
        skill_arm_hash="skill",
        baseline_after_hash="same",
    )

    verdict = validate_clean_slate_contract(contract)

    assert contract["baseline_sandwich"]["baseline_delta_status"] == "CLEAN"
    assert verdict == {"status": "PASS", "reasons": [], "runner_quarantine_status": "NONE"}


def test_polluted_baseline_blocks_promotion() -> None:
    contract = build_baseline_sandwich(
        baseline_before_hash="before",
        skill_arm_hash="skill",
        baseline_after_hash="after",
    )

    verdict = validate_clean_slate_contract(contract)

    assert contract["baseline_sandwich"]["baseline_delta_status"] == "POLLUTED"
    assert verdict["status"] == "BLOCKED"
    assert verdict["reasons"] == ["baseline_not_clean"]


def test_cleanup_failure_quarantines_runner() -> None:
    contract = build_baseline_sandwich(
        baseline_before_hash="same",
        skill_arm_hash="skill",
        baseline_after_hash="same",
        teardown_status="FAIL",
    )

    verdict = validate_clean_slate_contract(contract)

    assert verdict["status"] == "BLOCKED"
    assert verdict["runner_quarantine_status"] == "QUARANTINED"
    assert "cleanup_not_pass" in verdict["reasons"]
