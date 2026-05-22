from __future__ import annotations

import json

from nexus.learning.zero_trust_v2_receipts import build_runtime_signed_receipt
from scripts.ops.build_zero_trust_v2_m45_m52_completion import build_zero_trust_v2_m45_m52_completion


def _m36(bundle: str) -> dict:
    return {
        "summary": {
            "m42_p0_ready_for_execution_count": 5,
            "m43_p1_p2_ready_for_execution_count": 14,
        },
        "selected_canary_candidate": {"capability_id": "policy_capability_gate", "skill_id": "browse"},
        "m38_signed_behavior_execution_gate": {
            "run_plan": [
                {"run_index": 1, "run_id": "run-01", "expected_evidence_bundle": bundle},
                {"run_index": 2, "run_id": "run-02", "expected_evidence_bundle": ".missing/run-02/evidence_bundle.json"},
                {"run_index": 3, "run_id": "run-03", "expected_evidence_bundle": ".missing/run-03/evidence_bundle.json"},
            ]
        },
    }


def test_m45_m52_blocks_executed_but_unclean_behavior_bundle(tmp_path) -> None:
    bundle = tmp_path / "evidence_bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "benchmark_summary": {"with_nexus": {"infra_invalid_reasons": ["receipt_data_contract_violation"]}},
                "row_counts": {"eligible_with_nexus": 0},
                "rubric_contract": {"with_nexus": {"hard_fail_reasons": ["missing_required_capability_receipts"]}},
            }
        ),
        encoding="utf-8",
    )

    result = build_zero_trust_v2_m45_m52_completion(m36_m44=_m36(str(bundle)))

    assert result["status"] == "BLOCKED"
    assert result["summary"]["m45_behavior_run_executed_count"] == 1
    assert result["summary"]["m45_clean_v2_receipt_count"] == 0
    assert result["summary"]["m46_receipt_import_ready"] is False
    assert result["m45_behavior_run_results"][0]["status"] == "EXECUTED_BUT_BLOCKED"
    assert "receipt_data_contract_violation" in result["m45_behavior_run_results"][0]["blockers"]
    assert "missing_runtime_signed_v2_receipt" in result["m45_behavior_run_results"][0]["blockers"]
    assert result["m52_v1_path_closure_gate"]["status"] == "BLOCKED"


def test_m45_m52_blocks_when_behavior_bundles_are_missing() -> None:
    result = build_zero_trust_v2_m45_m52_completion(m36_m44=_m36(".missing/run-01/evidence_bundle.json"))

    assert result["summary"]["m45_behavior_run_executed_count"] == 0
    assert result["m45_behavior_run_results"][0]["status"] == "NOT_EXECUTED"
    assert result["m46_receipt_import_gate"]["status"] == "BLOCKED"


def test_m45_m52_requires_verified_runtime_signature(tmp_path, monkeypatch) -> None:
    bundle = tmp_path / "evidence_bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "row_counts": {"eligible_with_nexus": 1, "infra_invalid_with_nexus": 0},
                "rubric_contract": {"with_nexus": {"hard_fail_reasons": []}},
                "zero_trust_v2_runtime_receipt": {
                    "receipt_provenance": "runtime_signed",
                    "receipt_signature": "bad",
                    "receipt_signature_algorithm": "hmac-sha256",
                    "receipt_signature_inputs": {"receipt_hash": "bad"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", "test-secret")

    result = build_zero_trust_v2_m45_m52_completion(m36_m44=_m36(str(bundle)))

    assert result["m45_behavior_run_results"][0]["runtime_signed_receipt_present"] is True
    assert result["m45_behavior_run_results"][0]["runtime_signed_receipt_verified"] is False
    assert "runtime_signed_v2_receipt_signature_unverified" in result["m45_behavior_run_results"][0]["blockers"]


def test_m45_m52_passes_receipt_import_after_three_verified_clean_runs(tmp_path, monkeypatch) -> None:
    run_plan = []
    for index in range(1, 4):
        bundle = tmp_path / f"run-{index}" / "evidence_bundle.json"
        bundle.parent.mkdir()
        receipt = build_runtime_signed_receipt(
            run_id=f"run-{index}",
            row_id=f"run-{index}:with_nexus",
            arm_id="candidate_skill_v2",
            capability_id="policy_capability_gate",
            skill_id="browse",
            artifact_hash=f"artifact-{index}",
            raw_observation={"row_counts": {"eligible_with_nexus": 1}},
            secret="test-secret",
        )
        bundle.write_text(
            json.dumps(
                {
                    "row_counts": {"eligible_with_nexus": 1, "infra_invalid_with_nexus": 0},
                    "rubric_contract": {"with_nexus": {"hard_fail_reasons": []}},
                    "zero_trust_v2_runtime_receipt": receipt,
                }
            ),
            encoding="utf-8",
        )
        run_plan.append({"run_index": index, "run_id": f"run-{index}", "expected_evidence_bundle": str(bundle)})
    monkeypatch.setenv("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", "test-secret")

    result = build_zero_trust_v2_m45_m52_completion(
        m36_m44={
            "summary": {"m42_p0_ready_for_execution_count": 5, "m43_p1_p2_ready_for_execution_count": 14},
            "selected_canary_candidate": {"capability_id": "policy_capability_gate", "skill_id": "browse"},
            "m38_signed_behavior_execution_gate": {"run_plan": run_plan},
        }
    )

    assert result["status"] == "PASS"
    assert result["summary"]["m45_clean_v2_receipt_count"] == 3
    assert result["summary"]["m46_receipt_import_ready"] is True
    assert result["m46_receipt_import_gate"]["status"] == "PASS"


def test_m45_m52_matrix_mode_requires_three_clean_runs_per_ready_capability(tmp_path, monkeypatch) -> None:
    matrix = {
        "adapters": [
            {
                "capability_id": "policy_capability_gate",
                "skill_id": "browse",
                "priority": "P0",
                "status": "READY_FOR_PHYSICAL_BEHAVIOR_RUN",
            },
            {
                "capability_id": "codeintel",
                "skill_id": "codeintel-skill",
                "priority": "P1",
                "status": "READY_FOR_PHYSICAL_BEHAVIOR_RUN",
            },
        ]
    }
    for index in range(1, 4):
        bundle = (
            tmp_path
            / ".nexus"
            / "reports"
            / "zero_trust_v2_behavior"
            / "policy_capability_gate"
            / "browse"
            / f"run-{index:02d}"
            / "evidence_bundle.json"
        )
        bundle.parent.mkdir(parents=True)
        receipt = build_runtime_signed_receipt(
            run_id=f"ztv2-matrix-policy_capability_gate-browse-{index:02d}",
            row_id=f"run-{index}:with_nexus",
            arm_id="candidate_skill_v2",
            capability_id="policy_capability_gate",
            skill_id="browse",
            artifact_hash=f"artifact-{index}",
            raw_observation={"row_counts": {"eligible_with_nexus": 1}},
            secret="test-secret",
        )
        bundle.write_text(
            json.dumps(
                {
                    "row_counts": {"eligible_with_nexus": 1, "infra_invalid_with_nexus": 0},
                    "rubric_contract": {"with_nexus": {"hard_fail_reasons": []}},
                    "zero_trust_v2_runtime_receipt": receipt,
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NEXUS_ZERO_TRUST_V2_RECEIPT_SIGNING_SECRET", "test-secret")

    result = build_zero_trust_v2_m45_m52_completion(m36_m44=_m36("unused"), runner_matrix=matrix)

    assert result["status"] == "BLOCKED"
    assert result["summary"]["m45_status"] == "PARTIAL_MATRIX_BLOCKED"
    assert result["summary"]["m45_behavior_run_plan_count"] == 6
    assert result["summary"]["m45_clean_v2_receipt_count"] == 3
    assert result["m46_receipt_import_gate"]["required_clean_v2_receipt_count"] == 6
    assert result["m51_34_capability_gap"]["v2_ready_capability_count"] == 1
    assert result["m51_34_capability_gap"]["remaining_capability_count"] == 33
