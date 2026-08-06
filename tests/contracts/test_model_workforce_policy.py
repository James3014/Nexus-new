from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "docs/arch/MODEL_WORKFORCE_POLICY.md"
MANIFEST_PATH = REPO_ROOT / "nexus/config/model_workforce.yaml"
MATRIX_PATH = REPO_ROOT / "nexus/config/model_three_arm_matrix.yaml"
AGENTS_PATH = REPO_ROOT / "AGENTS.md"
SUMMARY_REPORT_PATH = REPO_ROOT / "docs/reports/model_workforce_three_arm_calibration_20260729.md"
SUMMARY_JSON_PATH = REPO_ROOT / "docs/reports/model_workforce_three_arm_calibration_20260729.json"


def _yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _manifest() -> dict:
    return _yaml(MANIFEST_PATH)


def test_model_workforce_authority_files_exist_and_are_current() -> None:
    assert POLICY_PATH.is_file()
    assert MANIFEST_PATH.is_file()
    assert MATRIX_PATH.is_file()

    data = _manifest()
    assert data["schema"] == "nexus.model_workforce.v1"
    assert data["status"] == "current"
    assert data["authority_document"] == "docs/arch/MODEL_WORKFORCE_POLICY.md"
    assert data["benchmark_matrix"] == "nexus/config/model_three_arm_matrix.yaml"
    assert data["route_authority"] == "CapabilityPlanner"


def test_initial_uniform_matrix_covers_all_enrolled_models() -> None:
    manifest = _manifest()
    snapshot = manifest["benchmark_snapshot"]
    matrix = _yaml(MATRIX_PATH)

    assert snapshot["attempted_model_count"] == 25
    assert snapshot["semantically_scored_model_count"] == 21
    assert snapshot["provider_blocked_model_count"] == 4
    assert snapshot["all_enrolled_models_attempted"] is True
    assert snapshot["full_receipt_closure_proven"] is False
    assert len(snapshot["models"]) == 25

    assert matrix["status"] == "completed_initial_matrix"
    assert matrix["latest_snapshot"]["attempted_model_count"] == 25
    assert matrix["latest_snapshot"]["all_enrolled_models_attempted"] is True
    assert matrix["result_authority"] == "nexus/config/model_workforce.yaml"
    assert matrix["composite_task"]["verifier_assertions"] == 11
    assert matrix["latest_snapshot"]["summary_report"] == str(SUMMARY_REPORT_PATH.relative_to(REPO_ROOT))
    assert matrix["latest_snapshot"]["machine_summary"] == str(SUMMARY_JSON_PATH.relative_to(REPO_ROOT))
    assert SUMMARY_REPORT_PATH.is_file()
    assert SUMMARY_JSON_PATH.is_file()


def test_mainchain_capability_and_current_availability_are_separate() -> None:
    workers = _manifest()["workers"]

    codex = workers["codex_luna"]
    assert codex["state"] == "PROVEN_MAINCHAIN"
    assert codex["capability_grade"] == "L3_HISTORICAL"
    assert codex["autonomy"] == "L3_HISTORICAL"
    assert codex["availability"] == "AVAILABLE"
    assert codex["current_assignment"] == "available_for_governed_mainchain_assignment"
    assert codex["requires"] == ["governed_adapter", "independent_verification", "receipt"]
    assert set(codex["forbidden_claims"]) == {
        "product_authority",
        "protected_main_merge",
        "remote_push",
    }
    assert codex["runtime_verification"] == {
        "date": "2026-07-29",
        "cli_version": "0.146.0",
        "model": "gpt-5.6-luna",
        "mode": "read_only_smoke",
        "stdout": "OK",
    }

    agy = workers["agy_flash"]
    assert agy["state"] == "PROVEN_MAINCHAIN"
    assert agy["availability"] == "AVAILABLE"
    assert agy["preferred_context"] == "nexus_bounded"

    grok = workers["grok_review"]
    assert grok["state"] == "PROVEN_MAINCHAIN"
    assert grok["availability"] == "AVAILABLE"
    assert grok["benchmark_ref"] == "grok_45"


def test_required_remote_workers_have_current_fail_closed_states() -> None:
    workers = _manifest()["workers"]

    for worker_id in ("opencode_mimo_free", "opencode_ling_free"):
        worker = workers[worker_id]
        assert worker["state"] == "REGISTERED_CONDITIONAL"
        assert worker["autonomy"] == "L1"
        assert "direct_workspace_mutation" in worker["forbidden_actions"]
        assert "verifier" in worker["requires"]

    assert workers["direct_gemini"]["state"] == "REGISTERED_BLOCKED"
    assert workers["mimo_cli"]["state"] == "REGISTERED_BLOCKED"


def test_local_workers_have_evidence_specific_context_and_autonomy_boundaries() -> None:
    workers = _manifest()["workers"]

    advisor = workers["local_advisor_3b"]
    assert advisor["state"] == "LOCAL_CONDITIONAL"
    assert advisor["preferred_context"] == "nexus_bounded"
    assert {"code_mutation", "full_context_assignment", "claim_authority"} <= set(
        advisor["forbidden_actions"]
    )

    coder = workers["local_coder_7b"]
    assert coder["state"] == "LOCAL_CONDITIONAL"
    assert {"parser", "compile", "focused_tests"} <= set(coder["requires"])
    assert "self_verification" in coder["forbidden_actions"]

    qwen3 = workers["local_qwen3_8b"]
    assert qwen3["state"] == "LOCAL_CONDITIONAL"
    assert qwen3["preferred_context"] == "nexus_bounded"
    assert "full_context_default" in qwen3["forbidden_actions"]

    qwen35 = workers["local_qwen35_9b"]
    assert qwen35["state"] == "LOCAL_CONDITIONAL"
    assert qwen35["model"] == "qwen3.5:9b"
    assert qwen35["preferred_context"] == "nexus_bounded"
    assert qwen35["roles"] == ["bounded_reasoning_candidate", "counterexample_search"]
    assert qwen35["requires"] == [
        "bounded_context",
        "parser",
        "external_verifier",
        "counterexample_suite",
        "role_specific_suite",
    ]
    assert "full_context_default" in qwen35["forbidden_actions"]
    assert "claim_authority" in qwen35["forbidden_actions"]
    assert "direct_apply" in qwen35["forbidden_actions"]
    evidence = qwen35["requalification_evidence"]
    assert evidence["date"] == "2026-08-06"
    assert evidence["repetitions"] == 2
    assert evidence["mutation_free_real_provider"] is True
    assert evidence["arm_results"] == {
        "bare": "10/11",
        "nexus_bounded": "10/11",
        "nexus_full": "10/11",
    }
    assert evidence["role_recommendation"] == "BOUNDED_REVIEW_AND_AUDIT"
    assert evidence["autonomy_ceiling"] == "L1"
    assert evidence["implementation_edge_failure"] == "normalize_status_success_label"
    assert evidence["public_claim"] is False

    matrix_models = _yaml(MATRIX_PATH)["models"]
    assert matrix_models["local_qwen35_9b"]["thinking_control"] == "api"
    matrix_excluded = _yaml(MATRIX_PATH)["excluded"]
    assert "local_qwythos_v2_9b" in matrix_excluded
    assert "local_gemma12b" in matrix_excluded
    assert "local_ornith9b" in matrix_excluded


def test_resource_risk_and_tool_discipline_models_are_not_default_workers() -> None:
    workers = _manifest()["workers"]

    for worker_id in ("local_qwen14b", "local_deepseek14b"):
        worker = workers[worker_id]
        assert worker["state"] == "DISABLED_RESOURCE_RISK"
        assert worker["autonomy"] == "L0"

    laguna = workers["opencode_laguna"]
    assert laguna["state"] == "QUARANTINED"
    assert "tool_denial_verification" in laguna["reenable_requires"]


def test_routing_is_deterministic_first_bounded_first_and_fail_closed() -> None:
    routing = _manifest()["routing"]

    assert routing["deterministic_first"] is True
    assert routing["no_default_full_context_local_worker"] is True
    assert routing["blocked_or_disabled_models_must_not_be_selected"] is True
    assert routing["experiment_only_models_require_explicit_authorization"] is True

    assert routing["local_first"] == {
        "classification": "local_advisor_3b",
        "extraction": "local_advisor_3b",
        "compression": "local_advisor_3b",
        "compact_diagnosis": "local_advisor_3b",
        "bounded_code_candidate": "local_coder_7b",
        "bounded_reasoning_shadow": "local_qwen3_8b",
    }
    assert routing["online"]["fast_bounded_implementation"] == "agy_flash"
    assert routing["online"]["independent_review"] == "grok_review"
    assert routing["online"]["complex_milestone"] == "codex_luna_when_available"

    mandatory = set(routing["mandatory_escalation_conditions"])
    assert "architecture_or_authority_choice" in mandatory
    assert "production_or_claim_adjudication" in mandatory
    assert "local_disagreement_or_verifier_failure" in mandatory


def test_full_context_is_not_assumed_to_improve_models() -> None:
    policy = _manifest()["context_policy"]
    regressions = set(policy["observed_full_context_regressions"])

    assert policy["prefer_nexus_bounded_for_small_and_medium_models"] is True
    assert policy["nexus_full_is_not_assumed_better"] is True
    assert policy["structured_output_requires_thinking_suppression_when_supported"] is True
    assert {
        "local_advisor_3b",
        "local_deepseek67b",
        "local_qwen35_9b",
        "local_qwen3_8b",
        "local_qwythos_v2_9b",
    } <= regressions


def test_model_output_cannot_become_receipt_or_completion_claim() -> None:
    claim_rules = _manifest()["claim_rules"]
    assert claim_rules["local_output_is_candidate_only"] is True
    assert claim_rules["plain_text_is_not_receipt"] is True
    assert claim_rules["focused_tests_do_not_prove_production_ready"] is True
    assert claim_rules["provider_failure_separate_from_model_failure"] is True
    assert claim_rules["semantic_pass_does_not_prove_receipt_complete"] is True
    assert claim_rules["no_model_self_assesses_production_ready"] is True

    policy = POLICY_PATH.read_text(encoding="utf-8")
    assert "Local output is always a candidate" in policy
    assert "semantic Full-arm pass does not imply" in policy


def test_bare_results_cannot_be_used_as_final_worker_grade() -> None:
    layers = _manifest()["evidence_layers"]
    assert layers["bare_model"]["sufficient_for_final_worker_grade"] is False
    assert layers["nexus_bounded"]["required_for_role_grade"] is True
    assert layers["nexus_full"]["required_for_autonomy_promotion"] is True
    assert layers["nexus_full"]["semantic_pass_is_not_receipt_closure"] is True
    assert layers["stable_promotion"]["requires_second_repetition"] is True
    assert layers["stable_promotion"]["requires_role_specific_suite"] is True

    policy = POLICY_PATH.read_text(encoding="utf-8")
    assert "Bare" in policy
    assert "Nexus-bounded" in policy
    assert "Nexus-full" in policy


def test_agents_must_read_both_model_workforce_authorities() -> None:
    agents = AGENTS_PATH.read_text(encoding="utf-8")
    overlay_ref = "docs/agents/WORKFORCE_EXECUTION_OVERLAY.md"
    assert overlay_ref in agents
    overlay = (REPO_ROOT / overlay_ref).read_text(encoding="utf-8")
    assert "docs/arch/MODEL_WORKFORCE_POLICY.md" in overlay
    assert "nexus/config/model_workforce.yaml" in overlay
    assert "Local output and delegated output are candidates" in overlay
