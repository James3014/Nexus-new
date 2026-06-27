import pytest
from nexus.services.local_heal.role_contract import (
    ModelRole,
    PHASE_ROLE_CONTRACT,
    ROLE_CONTRACT,
    RoleReceipt,
    build_role_receipt,
    check_role_drift,
)


def test_3b_cannot_enter_patch_phase():
    drift = check_role_drift("patch", "qwen2.5:3b")
    assert drift is not None
    assert "ROLE_DRIFT" in drift
    assert "expected=patcher" in drift
    assert "got=selector" in drift


def test_3b_can_enter_planning_as_selector():
    drift = check_role_drift("planning", "qwen2.5:3b")
    assert drift is not None
    assert "expected=searcher" in drift
    assert "got=selector" in drift


def test_7b_can_do_reproduction():
    drift = check_role_drift("reproduction", "qwen2.5-coder:7b")
    assert drift is None


def test_7b_can_do_planning():
    drift = check_role_drift("planning", "qwen2.5-coder:7b")
    assert drift is None


def test_7b_can_do_localization():
    drift = check_role_drift("localization", "qwen2.5-coder:7b")
    assert drift is None


def test_7b_cannot_enter_patch_phase():
    drift = check_role_drift("patch", "qwen2.5-coder:7b")
    assert drift is not None
    assert "expected=patcher" in drift
    assert "got=searcher" in drift


def test_14b_has_patch_authority():
    drift = check_role_drift("patch", "qwen2.5-coder:14b-instruct-q3_K_M")
    assert drift is None


def test_14b_cannot_enter_reproduction_as_searcher():
    drift = check_role_drift("reproduction", "qwen2.5-coder:14b-instruct-q3_K_M")
    assert drift is not None
    assert "expected=searcher" in drift
    assert "got=patcher" in drift


def test_unknown_phase_has_no_contract():
    drift = check_role_drift("unknown_phase", "qwen2.5:3b")
    assert drift is None


def test_manual_route_roles_are_contracted():
    assert ROLE_CONTRACT["judge"] == ModelRole.JUDGE
    assert ROLE_CONTRACT["proposer"] == ModelRole.PROPOSER
    assert ROLE_CONTRACT["secondary_proposer"] == ModelRole.SECONDARY_PROPOSER


def test_manual_route_roles_match_legacy_models():
    assert check_role_drift("judge", "qwen2.5:3b") is None
    assert check_role_drift("proposer", "qwen2.5-coder:7b") is None
    assert check_role_drift("secondary_proposer", "deepseek-coder:6.7b-instruct") is None


def test_unknown_model_skips_drift_check():
    drift = check_role_drift("patch", "some-unknown-model")
    assert drift is None


def test_phase_role_contract_completeness():
    expected_phases = {"reproduction", "planning", "localization", "patch", "verification"}
    assert set(PHASE_ROLE_CONTRACT.keys()) == expected_phases


def test_phase_role_contract_correct_mapping():
    assert PHASE_ROLE_CONTRACT["reproduction"] == ModelRole.SEARCHER
    assert PHASE_ROLE_CONTRACT["planning"] == ModelRole.SEARCHER
    assert PHASE_ROLE_CONTRACT["localization"] == ModelRole.SEARCHER
    assert PHASE_ROLE_CONTRACT["patch"] == ModelRole.PATCHER
    assert PHASE_ROLE_CONTRACT["verification"] == ModelRole.GOVERNANCE


def test_build_role_receipt_has_all_fields():
    receipt = build_role_receipt(
        phase="patch",
        model_name="qwen2.5-coder:14b-instruct-q3_K_M",
        reason_code="algebraic_precision_requirement_ollama",
    )
    assert isinstance(receipt, RoleReceipt)
    assert receipt.phase == "patch"
    assert receipt.selected_model_role == "patcher"
    assert receipt.invoked_model_role == "patcher"
    assert receipt.reason_code == "algebraic_precision_requirement_ollama"
    assert receipt.fallback_reason == ""
    assert receipt.role_drift_detected is False


def test_build_role_receipt_detects_drift():
    receipt = build_role_receipt(
        phase="patch",
        model_name="qwen2.5:3b",
        reason_code="wrong_choice",
    )
    assert receipt.role_drift_detected is True
    assert receipt.selected_model_role == "patcher"
    assert receipt.invoked_model_role == "selector"


def test_build_role_receipt_supports_manual_route_roles():
    judge_receipt = build_role_receipt(
        phase="judge",
        model_name="qwen2.5:3b",
        reason_code="manual_route_judge",
    )
    proposer_receipt = build_role_receipt(
        phase="proposer",
        model_name="qwen2.5-coder:7b",
        reason_code="manual_route_proposer",
    )
    secondary_receipt = build_role_receipt(
        phase="secondary_proposer",
        model_name="deepseek-coder:6.7b-instruct",
        reason_code="manual_route_secondary_proposer",
    )

    assert judge_receipt.role_drift_detected is False
    assert judge_receipt.selected_model_role == "judge"
    assert judge_receipt.invoked_model_role == "judge"
    assert proposer_receipt.role_drift_detected is False
    assert proposer_receipt.selected_model_role == "proposer"
    assert proposer_receipt.invoked_model_role == "proposer"
    assert secondary_receipt.role_drift_detected is False
    assert secondary_receipt.selected_model_role == "secondary_proposer"
    assert secondary_receipt.invoked_model_role == "secondary_proposer"


def test_3b_output_cannot_be_patch_success():
    receipt = build_role_receipt(
        phase="patch",
        model_name="qwen2.5:3b",
        reason_code="3b_cannot_patch",
    )
    assert receipt.role_drift_detected is True
    assert receipt.invoked_model_role == "selector"
