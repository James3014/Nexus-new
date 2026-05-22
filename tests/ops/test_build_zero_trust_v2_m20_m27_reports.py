from __future__ import annotations

import json

from scripts.ops.build_zero_trust_v2_behavior_runner_matrix import build_zero_trust_v2_behavior_runner_matrix
from scripts.ops.build_zero_trust_v2_fresh_task_refs import build_zero_trust_v2_fresh_task_refs
from scripts.ops.build_zero_trust_v2_m20_m27_completion import build_zero_trust_v2_m20_m27_completion
from scripts.bench.capability_ab_runner import _ensure_expected_capability_receipts


def test_fresh_task_refs_generate_runner_ready_matrix(tmp_path) -> None:
    backlog = {
        "items": [
            {"capability_id": "policy_capability_gate", "skill_id": "skill-a", "priority": "P0"},
            {"capability_id": "codeintel", "skill_id": "skill-b", "priority": "P1"},
            {"capability_id": "hyper_sprint", "skill_id": "skill-c", "priority": "P2"},
            {"capability_id": "swarm_multi_agent", "skill_id": "skill-d", "priority": "P2"},
            {"capability_id": "research_and_source_discipline", "skill_id": "skill-e", "priority": "P2"},
            {"capability_id": "repair_loop", "skill_id": "skill-f", "priority": "P1"},
            {"capability_id": "autonomic_router", "skill_id": "skill-g", "priority": "P2"},
            {"capability_id": "learn_ask", "skill_id": "skill-h", "priority": "P2"},
            {"capability_id": "benchmark_meta_opt", "skill_id": "skill-i", "priority": "P2"},
            {"capability_id": "direct_master_loop", "skill_id": "skill-j", "priority": "P2"},
            {"capability_id": "governance_and_trust", "skill_id": "skill-k", "priority": "P0"},
        ]
    }
    manifest = tmp_path / "fresh_tasks.json"
    refs = build_zero_trust_v2_fresh_task_refs(backlog=backlog, manifest_path=str(manifest))
    matrix = build_zero_trust_v2_behavior_runner_matrix(backlog=backlog, fresh_task_refs=refs)

    assert refs["summary"]["fresh_task_ref_count"] == 11
    assert manifest.exists()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert "zero_trust_v2" not in payload["tasks"][0]
    assert payload["tasks"][0]["expected_capabilities"] == ["mempalace_gate"]
    assert payload["tasks"][2]["expected_capabilities"] == ["hyper"]
    assert payload["tasks"][3]["expected_capabilities"] == ["swarm"]
    assert payload["tasks"][4]["expected_capabilities"] == ["research"]
    assert payload["tasks"][5]["expected_capabilities"] == ["hyper"]
    assert payload["tasks"][6]["expected_capabilities"] == ["autoreason"]
    assert payload["tasks"][7]["expected_capabilities"] == ["semantic_searcher"]
    assert payload["tasks"][8]["expected_capabilities"] == ["judge_panel"]
    assert payload["tasks"][9]["expected_capabilities"] == ["hyper"]
    assert payload["tasks"][10]["expected_capabilities"] == ["mempalace_gate"]
    assert payload["tasks"][0]["fixture_kind"] == "pytest_async_repair"
    assert payload["tasks"][0]["target_file"] == "target.py"
    assert payload["tasks"][0]["test_file"] == "test_visible.py"
    assert payload["tasks"][0]["mutation_required"] is True
    assert payload["tasks"][0]["allowed_files"] == ["target.py"]
    assert "compute_backoff" in payload["tasks"][0]["task_desc"]
    assert payload["tasks"][0]["verification_command"] == "python -m pytest -q test_visible.py"
    assert refs["zero_trust_v2_task_metadata"][0]["runner_capability"] == "mempalace_gate"
    assert refs["fresh_task_manifest"] == str(manifest)
    assert matrix["summary"]["ready_for_physical_behavior_run_count"] == 11
    assert all(item["command"] for item in matrix["adapters"])
    assert all(item["promotion_credit_allowed"] is False for item in matrix["adapters"])


def test_m20_m27_completion_keeps_runtime_locked_without_receipts() -> None:
    result = build_zero_trust_v2_m20_m27_completion(
        fresh_task_refs={"summary": {"fresh_task_ref_count": 2}},
        runner_matrix={"summary": {"ready_for_physical_behavior_run_count": 2, "p0_count": 1, "p1_count": 1, "p2_count": 0}},
        m12_verdict={"summary": {"capability_count": 34}},
    )

    assert result["summary"]["m20_fresh_task_ref_count"] == 2
    assert result["summary"]["m21_ready_for_physical_behavior_run_count"] == 2
    assert result["summary"]["m22_clean_v2_receipt_count"] == 0
    assert result["summary"]["m27_v1_promotion_path_closed"] is False
    assert result["summary"]["runtime_mutation_allowed"] is False
    assert result["rollback_gate"]["requires_previous_skill_id"] is True


def test_fresh_behavior_can_emit_deterministic_judge_panel_receipt() -> None:
    receipts = _ensure_expected_capability_receipts(
        task_id="ztv2-fresh-benchmark-meta-opt",
        expected_capabilities=("judge_panel",),
        capability_receipts=[],
        codeintel={},
        tests_passed=True,
        delivery_evidence_refs=["hidden_verifier:ztv2-fresh-benchmark-meta-opt"],
    )

    judge = {item["name"]: item for item in receipts}["judge_panel"]
    assert judge["invoked"] is True
    assert judge["public_claim_safe"] is True
    assert judge["selection_source"] == "deterministic_receipt_lite"
