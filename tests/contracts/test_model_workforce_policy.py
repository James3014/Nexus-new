from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from nexus.services.model_workforce_policy import WorkforcePolicyLoader

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
    assert matrix["latest_snapshot"]["summary_report"] == str(
        SUMMARY_REPORT_PATH.relative_to(REPO_ROOT)
    )
    assert matrix["latest_snapshot"]["machine_summary"] == str(
        SUMMARY_JSON_PATH.relative_to(REPO_ROOT)
    )
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
    # Agy 1.3.4 no longer serves Gemini 3.6 (Owner decision 2026-10-13, #1932).
    assert agy["availability"] == "UNAVAILABLE"
    assert agy["reason"] == "provider_no_longer_serves_model_agy_1.3.4_2026-10-13"
    assert agy["preferred_context"] == "nexus_bounded"

    medium_36 = workers["agy_flash_medium"]
    assert medium_36["model"] == "gemini-3.6-flash-medium"
    assert medium_36["autonomy"] == "L1"
    assert medium_36["default_route"] is False
    assert medium_36["calibration_evidence"]["inherits_high_evidence"] is False
    assert medium_36["availability"] == "UNAVAILABLE"

    medium_37 = workers["agy_flash_37_medium"]
    assert medium_37["provider"] == "agy"
    assert medium_37["model"] == "gemini-3.7-flash-medium"
    assert medium_37["state"] == "REGISTERED_CONDITIONAL"
    # Agy 1.3.4 rejects gemini-3.7-flash-medium; agy_flash_38 replaced it as default.
    assert medium_37["availability"] == "UNAVAILABLE"
    assert medium_37["reason"] == "provider_no_longer_serves_model_agy_1.3.4_2026-10-13"
    assert medium_37["autonomy"] == "L3"
    assert medium_37["default_route"] is False
    assert medium_37["calibration_evidence"] == {
        "status": "OWNER_APPROVED_CEILING",
        "lineage": "gemini-3.7-flash-medium",
        "stable_floor": "L3",
        "current_frontier": "L4",
        "conditional_ceiling": "L3",
        "experimental_ceiling": "L4",
        "experimental_l4_admitted": False,
    }

    grok = workers["grok_review"]
    assert grok["state"] == "PROVEN_MAINCHAIN"
    assert grok["availability"] == "UNAVAILABLE"
    assert grok["reason"] == "retired_from_frontier_priority_2026-10-15"
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


def test_owner_approved_deepseek_l1_role_writeback_is_bounded_and_evidence_bound() -> None:
    # Preserve the historical logical node for exact-base comparison.
    # The assertions below bind the current L2 policy.
    worker = _manifest()["workers"]["opencode_deepseek_v4_flash"]
    assert worker["provider"] == "opencode"
    assert worker["model"] == "opencode/deepseek-v4-flash-free"
    assert worker["state"] == "REGISTERED_CONDITIONAL"
    assert worker["availability"] == "AVAILABLE"
    assert worker["autonomy"] == "L2"
    assert worker["default_route"] is False
    assert worker["roles"] == ["bounded_candidate_generation", "compact_code_candidate"]
    assert {"parser", "focused_tests", "verifier"} <= set(worker["requires"])
    assert "second_repetition" not in worker["requires"]
    assert "physical_patch_suite" not in worker["requires"]
    assert {
        "route_authority",
        "direct_workspace_mutation",
        "production_ready_judgment",
        "approval",
        "integration",
        "push",
    } <= set(worker["forbidden_actions"])
    evidence = worker["requalification_evidence"]
    assert evidence["date"] == "2026-08-15"
    assert evidence["repetitions"] == 2
    assert evidence["provider"] == "opencode"
    assert evidence["model"] == "opencode/deepseek-v4-flash-free"
    assert evidence["opencode_version"] == "1.17.20"
    assert evidence["provider_model_revision"] == "UNRESOLVED"
    assert evidence["lineage"] == "deepseek-v4-flash"
    assert evidence["arm_results"] == {
        "R2": {"bare": "11/11", "nexus_bounded": "11/11", "nexus_full": "11/11"},
        "R3": {"bare": "11/11", "nexus_bounded": "11/11", "nexus_full": "11/11"},
    }
    assert evidence["result_json_sha256"] == {
        "R2": "2493c49e2e9caa1b5a39f3839807d655cd78f8f12c8854058032b3e0d602471a",
        "R3": "b52e4ee5cc6e15a4cf452d8373bbe16fa6ce8837386dca8a9c70bf94c05065e8",
    }
    assert evidence["physical_patch_evidence"] == {
        "PR_84_merge_sha": "c304e7d98f62f615f7ca44c2ab4451dff9e780e3",
        "PR_85_merge_sha": "8f7c75ca08a6c88fad9b791f254d38d79ad8bf29",
    }
    assert evidence["role_recommendation"] == "bounded_code_candidate"
    assert evidence["autonomy_ceiling"] == "L2"
    assert evidence["experimental_l4_admitted"] is False
    assert evidence["public_claim"] is False
    policy = POLICY_PATH.read_text(encoding="utf-8")
    assert "Dated Owner-approved amendment — 2026-08-15" in policy
    assert "DeepSeek V4 Flash (`opencode_deepseek_v4_flash`)" in policy


def test_local_workers_have_evidence_specific_context_and_autonomy_boundaries() -> None:
    workers = _manifest()["workers"]

    advisor = workers["local_advisor_3b"]
    # Retired 2026-10-13 (nexus-runtime #184): weights absent, no roles admitted.
    assert advisor["state"] == "REGISTERED_BLOCKED"
    assert advisor["availability"] == "UNAVAILABLE"
    assert advisor["roles"] == []
    assert advisor["preferred_context"] == "nexus_bounded"
    assert {"code_mutation", "full_context_assignment", "claim_authority"} <= set(
        advisor["forbidden_actions"]
    )

    coder = workers["local_coder_7b"]
    assert coder["state"] == "LOCAL_CONDITIONAL"
    assert {"parser", "compile", "focused_tests"} <= set(coder["requires"])
    assert "self_verification" in coder["forbidden_actions"]

    qwen3 = workers["local_qwen3_8b"]
    # Not present on the M5 Ollama host (nexus-runtime#173); roles kept for history.
    assert qwen3["state"] == "INSTALLED_NOT_CONNECTED"
    assert qwen3["reason"] == "not_present_on_m5_ollama_2026-10-12"
    assert qwen3["preferred_context"] == "nexus_bounded"
    assert "full_context_default" in qwen3["forbidden_actions"]

    qwen35 = workers["local_qwen35_9b"]
    assert qwen35["state"] == "LOCAL_CONDITIONAL"
    assert qwen35["model"] == "qwen3.5:9b"
    assert qwen35["preferred_context"] == "nexus_bounded"
    assert qwen35["roles"] == [
        "bounded_reasoning_candidate",
        "counterexample_search",
        "classification",
        "extraction",
        "compression",
        "compact_diagnosis",
        "committee_judge",
    ]
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
        assert worker["autonomy"] == "L0"
    assert workers["local_qwen14b"]["state"] == "DISABLED_RESOURCE_RISK"
    # nexus-runtime#173: not present on M5; the resource-risk verdict is kept as prior state.
    deepseek14b = workers["local_deepseek14b"]
    assert deepseek14b["state"] == "INSTALLED_NOT_CONNECTED"
    assert deepseek14b["prior_state"] == "DISABLED_RESOURCE_RISK"

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
        "classification": "local_qwen35_9b",
        "extraction": "local_qwen35_9b",
        "compression": "local_qwen35_9b",
        "compact_diagnosis": "local_qwen35_9b",
        "bounded_code_candidate": "local_coder_7b",
        "bounded_reasoning_shadow": "local_qwen35_9b",
        "committee_judge": "local_qwen35_9b",
    }
    assert routing["online"]["fast_bounded_implementation"] == "agy_flash_38"
    assert routing["online"]["fast_bounded_implementation_fallback"] is None
    route_defaults = routing["online"]["route_defaults"]["fast_bounded_implementation"]
    assert route_defaults["current_default"] == "agy_flash_38"
    assert route_defaults["fallback"] is None
    campaign = routing["online"]["campaign_routing"]["CAMPAIGN-NEXUS-LEARNING-CANONICAL-WIRING-01"]
    assert campaign["fast_bounded_implementation"] == "agy_flash_38"
    assert routing["online"]["independent_review"] == "agy_flash_38_high"
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


def test_owner_approved_mimo_cumulative_calibration_stays_l1_and_not_promoted() -> None:
    workers = _manifest()["workers"]

    mimo = workers["opencode_mimo_free"]
    assert mimo["provider"] == "opencode"
    assert mimo["model"] == "opencode/mimo-v2.5-free"
    assert mimo["state"] == "REGISTERED_CONDITIONAL"
    assert mimo["availability"] == "AVAILABLE"
    assert mimo["autonomy"] == "L1"
    assert mimo["roles"] == ["bounded_candidate_generation", "compact_code_candidate"]

    assert mimo["autonomy"] not in ("L2", "L3")

    evidence = mimo["requalification_evidence"]
    assert evidence["date"] == "2026-08-17"
    assert evidence["semantic_stable_floor"] == "L1.5"
    assert evidence["semantic_frontier"] == "L3"
    assert evidence["trial_count"] == 53
    assert evidence["semantic_score"] == "51/53"
    assert evidence["frontier_stress"] == "15/15"
    assert evidence["verifier_guided_repair"] == "4/5"
    assert evidence["strict_schema_discipline"] == "CONDITIONAL"
    assert evidence["tool_scope_discipline"] == "HARD_FAIL"
    assert evidence["trusted_execution_ceiling"] == "L1"
    assert evidence["autonomy_ceiling"] == "L1"
    assert evidence["promotion_status"] == "NOT_PROMOTED"
    assert evidence["public_claim"] is False
    assert evidence["evidence_status"] == "OWNER_APPROVED_CUMULATIVE_SUMMARY"
    assert evidence["raw_trial_receipt_status"] == "NOT_REPOSITORY_BOUND"
    assert evidence["raw_trial_evidence"] == "NOT_IN_REPOSITORY_AUTHORITY"
    assert evidence["claim_ceiling"] == "OWNER_APPROVED_CUMULATIVE_SUMMARY_ONLY"
    assert evidence["baseline_main"] == "9296d68fe19d933cb78b9a0470a054ea5efd4c2f"
    assert {a["name"] for a in evidence["source_artifacts"]} == {
        "MODEL_WORKFORCE_POLICY_20260817.md",
        "NEXUS_MULTI_MODEL_V2.9.md",
        "opencode-1.18.18",
    }
    assert [a["sha256"] for a in evidence["source_artifacts"]] == [
        "6cefe1aabb58a43b2fea39c1e6365e03efd1191034310634352ee997604edfc3",
        "67bd054cfd2b5eb636524c552837f6cb692f2c5a88436f3de67be8f38e38185a",
        "4f5979c2dadb06fbff1335335afaaea274e58f92e79aa43cf2ed98618d555422",
    ]
    assert {a["digest_status"] for a in evidence["source_artifacts"]} == {"FULL_SHA256_VERIFIED"}

    registered_models = {w["model"] for w in workers.values()}
    assert "opencode/mimo-v2.5-free" in registered_models
    assert "opencode-go/mimo-v2.5" not in registered_models
    assert "opencode-go/mimo-v2.5" not in {w["model"] for w in workers.values()}

    policy = POLICY_PATH.read_text(encoding="utf-8")
    assert "Dated Owner-approved MiMo calibration amendment — 2026-08-17" in policy
    assert "NOT_PROMOTED" in policy
    assert "semantic frontier" in policy
    assert "HARD FAIL" in policy
    assert "tool-discipline requalification" in policy
    assert "FREE_FIRST" in policy
    assert "opencode-go/mimo-v2.5" in policy


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("strategy", "FREE_FIRST"),
        ("free_identity", {"provider": "opencode", "model": "opencode/mimo-v2.5-free", "order": 1}),
        (
            "paid_go_identity",
            {
                "provider": "opencode-go",
                "model": "opencode-go/mimo-v2.5",
                "order": 2,
                "workforce_admission": "NOT_ADMITTED",
            },
        ),
        (
            "allowed_pre_mutation_blocker_classes",
            ["PROVIDER", "TRANSPORT", "CAPACITY", "QUOTA", "EXACT_MODEL_AVAILABILITY"],
        ),
        ("forbidden_fallback_classes", ["UNKNOWN", "POST_MUTATION", "SEMANTIC", "VERIFIER"]),
        ("lineage_equivalence", "UNRESOLVED"),
    ],
)
def test_mimo_transport_policy_is_free_first_and_fail_closed(field: str, expected: object) -> None:
    transport = _manifest()["workers"]["opencode_mimo_free"]["transport_policy"]
    assert transport[field] == expected


def test_mimo_transport_policy_requires_clean_pre_mutation_go_and_devspace_enforcement() -> None:
    transport = _manifest()["workers"]["opencode_mimo_free"]["transport_policy"]
    assert transport["require_clean_no_mutation"] is True
    assert transport["fresh_go_preflight_required"] is True
    assert set(transport["allowed_pre_mutation_blocker_classes"]).isdisjoint(
        transport["forbidden_fallback_classes"]
    )
    enforcement = transport["enforcement"]
    assert enforcement["authority"] == "DevSpace"
    assert enforcement["not_capability_planner"] is True
    assert enforcement["issue"] == 400
    assert enforcement["candidate_commit"] == "65103307a014d5e51534828ab5e3c8469b60b732"
    assert enforcement["durable_receipt_url"] == (
        "https://github.com/James3014/Nexus-new/issues/400#issuecomment-5320083668"
    )


@pytest.mark.parametrize("forbidden", ["UNKNOWN", "POST_MUTATION", "SEMANTIC", "VERIFIER"])
def test_mimo_transport_policy_rejects_non_pre_mutation_go_fallbacks(forbidden: str) -> None:
    transport = _manifest()["workers"]["opencode_mimo_free"]["transport_policy"]
    assert forbidden in transport["forbidden_fallback_classes"]
    assert forbidden not in transport["allowed_pre_mutation_blocker_classes"]


def test_three_layers_lineage_and_ceiling_constraints() -> None:
    manifest = _manifest()
    workers = manifest["workers"]

    # Layer distinction
    semantic_layers = manifest["evidence_layers"]["semantic_layers"]
    assert (
        "semantic_capability_lineage != exact_execution_identity != admitted_authority"
        in semantic_layers["distinction"]
    )
    assert semantic_layers["exact_identity_matching"] == "strict_fail_closed"
    assert semantic_layers["route_authority"] == "CapabilityPlanner_sole_authority"

    # CapabilityPlanner sole route authority
    assert manifest["route_authority"] == "CapabilityPlanner"

    # Preserve the existing Gemini 3.6 Medium identity and register 3.7 separately.
    gemini_36_medium = workers["agy_flash_medium"]
    assert gemini_36_medium["model"] == "gemini-3.6-flash-medium"
    assert gemini_36_medium["autonomy"] == "L1"
    assert gemini_36_medium["default_route"] is False

    # Gemini 3.7 Flash Medium: ceiling L3, no L4; no longer the default since
    # 2026-10-13 (Agy 1.3.4 no longer serves it).
    gemini_medium = workers["agy_flash_37_medium"]
    assert gemini_medium["model"] == "gemini-3.7-flash-medium"
    assert gemini_medium["autonomy"] == "L3"
    assert gemini_medium["default_route"] is False
    assert gemini_medium["availability"] == "UNAVAILABLE"
    assert gemini_medium["calibration_evidence"]["experimental_l4_admitted"] is False

    # Gemini 3.8 Flash Medium: sole default at the registered L3, no L4.
    gemini_38 = workers["agy_flash_38"]
    assert gemini_38["model"] == "gemini-3.8-flash-medium"
    assert gemini_38["autonomy"] == "L3"
    assert gemini_38["default_route"] is True
    assert "calibration_evidence" not in gemini_38

    # DeepSeek V4 Flash: ceiling L2, non-default, no L4
    deepseek_worker = workers["opencode_deepseek_v4_flash"]
    assert deepseek_worker["model"] == "opencode/deepseek-v4-flash-free"
    assert deepseek_worker["autonomy"] == "L2"
    assert deepseek_worker["default_route"] is False
    assert deepseek_worker["requalification_evidence"]["lineage"] == "deepseek-v4-flash"
    assert deepseek_worker["requalification_evidence"]["experimental_l4_admitted"] is False

    # Exact execution identity matching: opencode-go alias shares lineage only
    registered_models = {w["model"] for w in workers.values()}
    assert "opencode/deepseek-v4-flash-free" in registered_models
    assert "opencode-go/deepseek-v4-flash" not in registered_models

    # Requalification protocol and phase separation
    proto = manifest["evidence_layers"]["requalification_protocol"]
    assert proto["distinct_phases"] == [
        "FIRST_PASS",
        "HIDDEN_DEFECT_PROBES",
        "VERIFIER_GUIDED_REPAIR",
    ]
    assert proto["experimental_l4_not_admitted"] is True


# --- Combined Learning/Core Workforce route repair tests (Card: TASK-PWS-COMBINED-R2) ---


def test_combined_global_route_binds_to_37_medium() -> None:
    """GLOBAL: since 2026-10-13 fast_bounded_implementation routes to agy_flash_38, not 3.7."""
    manifest = _manifest()
    routing = manifest["routing"]
    assert routing["online"]["fast_bounded_implementation"] == "agy_flash_38"
    assert routing["online"]["fast_bounded_implementation_fallback"] is None
    defaults = routing["online"]["route_defaults"]["fast_bounded_implementation"]
    assert defaults["current_default"] == "agy_flash_38"
    assert defaults["fallback"] is None
    assert manifest["workers"]["agy_flash_37_medium"]["availability"] == "UNAVAILABLE"


def test_campaign_exact_match_resolves_to_37_medium() -> None:
    """CAMPAIGN: exact CAMPAIGN-NEXUS-LEARNING-CANONICAL-WIRING-01 resolves fast_bounded_implementation."""
    manifest = _manifest()
    campaign = manifest["routing"]["online"]["campaign_routing"][
        "CAMPAIGN-NEXUS-LEARNING-CANONICAL-WIRING-01"
    ]
    # The Learning campaign moved to 3.8 with the 2026-10-13 default switch.
    assert campaign["fast_bounded_implementation"] == "agy_flash_38"


def test_campaign_37_medium_worker_advertises_role() -> None:
    """WORKER: agy_flash_37_medium keeps the role on record but is UNAVAILABLE; agy_flash_38 serves it."""
    manifest = _manifest()
    w = manifest["workers"]["agy_flash_37_medium"]
    assert w["provider"] == "agy"
    assert w["model"] == "gemini-3.7-flash-medium"
    assert "fast_bounded_implementation" in w["roles"]
    assert w["availability"] == "UNAVAILABLE"
    assert w["state"] == "REGISTERED_CONDITIONAL"
    assert w["autonomy"] == "L3"
    assert w["default_route"] is False
    w38 = manifest["workers"]["agy_flash_38"]
    assert "fast_bounded_implementation" in w38["roles"]
    assert w38["availability"] == "AVAILABLE"
    assert w38["state"] == "REGISTERED_CONDITIONAL"
    assert w38["autonomy"] == "L3"
    assert w38["default_route"] is True


def test_36_high_is_fallback_not_default() -> None:
    """FALLBACK: agy_flash (3.6-high) is no longer the fallback; the fallback is null (fail closed)."""
    manifest = _manifest()
    defaults = manifest["routing"]["online"]["route_defaults"]["fast_bounded_implementation"]
    assert "fallback" in defaults
    assert defaults["fallback"] is None
    assert defaults["current_default"] != "agy_flash"
    w = manifest["workers"]["agy_flash"]
    assert w["default_route"] is False
    assert w["availability"] == "UNAVAILABLE"


def test_36_and_37_identity_separation_preserved() -> None:
    """IDENTITY: exact 3.6/3.7 identity separation is preserved."""
    manifest = _manifest()
    workers = manifest["workers"]
    w36 = workers["agy_flash"]
    w37 = workers["agy_flash_37_medium"]
    assert w36["model"] == "gemini-3.6-flash-high"
    assert w37["model"] == "gemini-3.7-flash-medium"
    assert w36["provider"] == "agy"
    assert w37["provider"] == "agy"
    assert w36["autonomy"] == "L2"
    assert w37["autonomy"] == "L3"


# --- Open SWE ChatGPT Workforce Onboarding tests (Card: open-swe-chatgpt-workforce-onboarding-20260908) ---


def test_opencli_chatgpt_balanced_web_registration() -> None:
    """Workforce policy registers opencli_chatgpt_balanced_web with exact properties."""
    manifest = _manifest()
    workers = manifest["workers"]
    assert "opencli_chatgpt_balanced_web" in workers
    w = workers["opencli_chatgpt_balanced_web"]
    assert w["provider"] == "opencli_chatgpt"
    assert w["model"] == "opencli_chatgpt/balanced"
    assert w["state"] == "REGISTERED_CONDITIONAL"
    assert w["availability"] == "AVAILABLE"
    assert w["autonomy"] == "L1"
    assert "bounded_candidate_generation" in w["roles"]
    assert w["default_route"] is False


def test_global_fast_bounded_implementation_remains_agy_flash_37_medium() -> None:
    """Global fast_bounded_implementation is agy_flash_38 since 2026-10-13 (name kept for node-id stability)."""
    manifest = _manifest()
    routing = manifest["routing"]
    assert routing["online"]["fast_bounded_implementation"] == "agy_flash_38"
    defaults = routing["online"]["route_defaults"]["fast_bounded_implementation"]
    assert defaults["current_default"] == "agy_flash_38"
    loader = WorkforcePolicyLoader()
    assert loader.resolve_route("fast_bounded_implementation") == "agy_flash_38"


def test_campaign_route_resolution_open_swe_resident_canary() -> None:
    """Exact canary campaign resolves fast_bounded_implementation to opencli_chatgpt_balanced_web; others use global."""
    manifest = _manifest()
    campaign_routing = manifest["routing"]["online"].get("campaign_routing", {})
    assert "open-swe-resident-five-repo-canary-20260908" in campaign_routing
    assert (
        campaign_routing["open-swe-resident-five-repo-canary-20260908"][
            "bounded_candidate_generation"
        ]
        == "opencli_chatgpt_balanced_web"
    )

    loader = WorkforcePolicyLoader()
    assert (
        loader.resolve_route(
            "bounded_candidate_generation",
            campaign_id="open-swe-resident-five-repo-canary-20260908",
        )
        == "opencli_chatgpt_balanced_web"
    )
    assert loader.resolve_route("fast_bounded_implementation", campaign_id="") == "agy_flash_38"
    assert (
        loader.resolve_route(
            "fast_bounded_implementation",
            campaign_id="prefix-open-swe-resident-five-repo-canary-20260908",
        )
        == "agy_flash_38"
    )
    assert (
        loader.resolve_route(
            "fast_bounded_implementation",
            campaign_id="unrelated-campaign",
        )
        == "agy_flash_38"
    )


def test_m5_host_alignment_2026_10_12_admission() -> None:
    manifest = _manifest()
    workers = manifest["workers"]
    assert manifest["last_verified"] == "2026-10-13"

    # local_deepseek67b was pulled to M5 Ollama on 2026-10-14 (nexus-runtime#202).
    deepseek = workers["local_deepseek67b"]
    assert deepseek["state"] == "LOCAL_CONDITIONAL"
    assert deepseek["prior_state"] == "INSTALLED_NOT_CONNECTED"
    assert deepseek["roles"] == ["committee_secondary_proposer_only"]
    assert deepseek["default_route"] is False
    assert deepseek["installation_evidence"]["digest"] == (
        "ce298d984115b93bb1b191b47fee6b39e4e9fbd5f18e651c02f9fa74e0edcd13"
    )

    for worker_id in ("local_qwythos9b",):
        assert workers[worker_id]["state"] == "INSTALLED_NOT_CONNECTED"
        assert workers[worker_id]["reason"] == "not_present_on_m5_ollama_2026-10-12"
        assert workers[worker_id]["roles"]

    qwen14b = workers["local_qwen14b"]
    assert qwen14b["state"] == "DISABLED_RESOURCE_RISK"
    assert "m5_64gb_host_2026-10-12" in qwen14b["reason"]

    splash = workers["local_splash_qwen36"]
    assert splash["model"] == "incoai/Qwen3.6-35B-A3B-Splash"
    assert splash["state"] == "LOCAL_CONDITIONAL"
    assert splash["autonomy"] == "L1"
    assert splash["roles"] == ["bounded_code_candidate", "bounded_reasoning_candidate"]
    assert splash["requires"] == workers["local_coder_7b"]["requires"]
    assert splash["forbidden_actions"] == workers["local_coder_7b"]["forbidden_actions"]

    big = workers["local_splash_qwen38_27b"]
    # nexus-runtime#177: calibration-only admission; still EXPERIMENT_ONLY and unrouted.
    assert big["state"] == "EXPERIMENT_ONLY"
    assert big["autonomy"] == "L1"
    assert big["roles"] == ["bounded_experiment", "bounded_code_candidate"]
    assert (
        big["reason"]
        == "served_on_m5_8001_gateway_mapped_2026-10-13; calibration_only_not_promoted"
    )

    agy = workers["agy_flash_38"]
    reference = workers["agy_flash_37_medium"]
    assert agy["provider"] == "agy"
    assert agy["state"] == "REGISTERED_CONDITIONAL"
    assert agy["roles"] == reference["roles"]
    assert agy["autonomy"] == reference["autonomy"]
    # Default since 2026-10-13 (section 15); the 2026-10-12 registration is unchanged otherwise.
    assert agy["default_route"] is True

    policy = POLICY_PATH.read_text(encoding="utf-8")
    assert "Dated amendment — 2026-10-12 (M5 inference host alignment)" in policy


def test_opencli_chatgpt_advanced_web_registration_and_eia_consumer_route() -> None:
    """Owner decision 2026-10-13: EIA routes to the free-plan Thinking web worker."""
    workers = _manifest()["workers"]
    w = workers["opencli_chatgpt_advanced_web"]
    balanced = workers["opencli_chatgpt_balanced_web"]
    assert w["provider"] == "opencli_chatgpt"
    assert w["model"] == "opencli_chatgpt/advanced"
    assert w["state"] == "REGISTERED_CONDITIONAL"
    assert w["autonomy"] == "L1"
    assert w["roles"] == ["bounded_candidate_generation"]
    assert w["default_route"] is False
    for key in ("requires", "forbidden_actions", "transport_contract"):
        assert w[key] == balanced[key]
    evidence = w["calibration_evidence"]
    assert evidence["owner_approved_consumers"] == ["external_intelligence"]
    assert (
        evidence["consumer_approval_ref"] == "owner-decision-2026-10-13-eia-gpt-web-free-thinking"
    )
    assert "owner_approved_consumers" not in balanced["calibration_evidence"]

    loader = WorkforcePolicyLoader()
    assert (
        loader.resolve_route("bounded_candidate_generation", consumer="external_intelligence")
        == "opencli_chatgpt_advanced_web"
    )
