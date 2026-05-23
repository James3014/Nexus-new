from __future__ import annotations

from nexus.learning.skill_fit_status import build_skill_fit_data_shape_pregate


def _catalog() -> dict[str, object]:
    return {
        "schema": "nexus.skill_fit_catalog.v1",
        "status": "PASS",
        "summary": {"matrix_complete": True},
        "skill_verdicts": [
            {
                "capability": "repair_and_coding",
                "skill_id": "tdd",
                "verdict": "keep",
                "tested_rows": 30,
                "effective_rows": 30,
                "evidence_refs": ["evidence:tdd"],
                "receipt_refs": ["receipt:tdd"],
            }
        ],
    }


def _policy() -> dict[str, object]:
    return {
        "schema": "nexus.capability_skill_promotion_policy_draft.v1",
        "status": "PASS",
        "runtime_update_allowed": False,
        "defaults": {"repair_and_coding": "tdd"},
        "alternates": {},
        "needs_more_data": {},
        "rejected": {},
    }


def _threshold() -> dict[str, object]:
    return {
        "schema": "nexus.skill_promotion_threshold_contract.v1",
        "status": "PASS",
        "runtime_update_allowed": False,
        "summary": {"matrix_complete": True},
        "capability_skill_thresholds": [
            {
                "capability": "repair_and_coding",
                "skill_id": "tdd",
                "observed_rows_ok": True,
                "threshold_recommendation": "default_candidate",
            }
        ],
        "failures": [],
    }


def test_skill_fit_data_shape_pregate_passes_minimal_complete_chain():
    pregate = build_skill_fit_data_shape_pregate(
        catalog=_catalog(),
        promotion_policy=_policy(),
        threshold_contract=_threshold(),
    )

    assert pregate["schema"] == "nexus.skill_fit_data_shape_pregate.v1"
    assert pregate["status"] == "PASS"
    assert pregate["failures"] == []
    assert pregate["runtime_update_allowed"] is False
    assert pregate["public_benchmark_allowed"] is False
    assert pregate["summary"]["positive_pair_count"] == 1


def test_skill_fit_data_shape_pregate_returns_on_positive_policy_without_receipts():
    catalog = _catalog()
    catalog["skill_verdicts"][0]["receipt_refs"] = []

    pregate = build_skill_fit_data_shape_pregate(
        catalog=catalog,
        promotion_policy=_policy(),
        threshold_contract=_threshold(),
    )

    assert pregate["status"] == "RETURN"
    assert pregate["runtime_update_allowed"] is False
    assert pregate["public_benchmark_allowed"] is False
    assert "repair_and_coding:tdd:catalog_positive_missing_evidence_or_receipt" in pregate["failures"]


def test_skill_fit_data_shape_pregate_returns_on_threshold_pair_missing_from_catalog():
    threshold = _threshold()
    threshold["capability_skill_thresholds"][0]["skill_id"] = "ghost-skill"

    pregate = build_skill_fit_data_shape_pregate(
        catalog=_catalog(),
        promotion_policy=_policy(),
        threshold_contract=threshold,
    )

    assert pregate["status"] == "RETURN"
    assert "repair_and_coding:ghost-skill:threshold_pair_missing_catalog_verdict" in pregate["failures"]
    assert "repair_and_coding:tdd:missing_threshold_contract" in pregate["failures"]


def test_skill_fit_data_shape_pregate_never_allows_runtime_or_public_benchmark():
    catalog = _catalog()
    catalog["public_benchmark_allowed"] = True
    policy = _policy()
    policy["runtime_update_allowed"] = True

    pregate = build_skill_fit_data_shape_pregate(
        catalog=catalog,
        promotion_policy=policy,
        threshold_contract=_threshold(),
    )

    assert pregate["status"] == "RETURN"
    assert pregate["runtime_update_allowed"] is False
    assert pregate["public_benchmark_allowed"] is False
    assert "promotion_policy_runtime_update_must_remain_false" in pregate["failures"]
