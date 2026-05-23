from __future__ import annotations

import json

from scripts.bench.evidence_bundle_payload import (
    build_evidence_bundle_payload,
    build_evidence_bundle_claim_posture_sections,
    build_evidence_bundle_computed_sections,
    build_evidence_bundle_header_section,
    build_nexus_wearing_context,
    build_posture_finalization_gate_section,
    build_rubric_contract_bundle,
    build_telemetry_completeness_section,
    build_wall_ledger_conservation_section,
    build_warning_clean_gate_section,
    finalize_evidence_bundle_payload,
    summarize_rubric_contract_rows,
    write_evidence_bundle_payload,
)


def test_finalize_evidence_bundle_payload_adds_fail_closed_contracts_without_mutating_input():
    payload = {
        "schema": "nexus_public_benchmark_evidence_bundle_v2",
        "config": {"with_model_provider": "codex"},
        "model_lock": {"codex_model_name": "gpt-5.5"},
        "taskset_contract": {"fixed_public_taskset_ready": False},
        "session_worker_contamination": {"clean": True, "contamination_rate": 0.0},
        "outbound_prompt_ledger_gate": {"status": "PASS", "forbidden_literal_count": 0},
        "public_verified_delivery_claim_gate": {"verdict": "PASS"},
        "public_cost_claim_gate": {"verdict": "PASS"},
        "public_cost_efficiency_claim_gate": {"verdict": "IMPROVED"},
        "x3_promotion_gate": {"status": "PASS"},
        "valid_comparison_readiness_gate": {"status": "PASS"},
        "route_policy_evidence_contract": {"status": "PASS"},
        "expected_capability_evidence_contract": {"status": "PASS"},
        "public_gate_checks": {
            "with_trust_mismatch_rate": 0.0,
            "without_trust_mismatch_rate": 0.0,
            "wall_ledger_with_conserved_rate": 1.0,
            "wall_ledger_without_conserved_rate": 1.0,
            "provider_token_measured_rate_with": 1.0,
            "provider_token_measured_rate_without": 1.0,
        },
    }

    finalized = finalize_evidence_bundle_payload(payload)

    assert "external_provider_claim_boundary_contract" not in payload
    assert finalized["external_provider_claim_boundary_contract"]["status"] == "OBSERVATION_ONLY"
    assert finalized["public_promotion_readiness_contract"]["status"] == "RETURN"
    assert finalized["public_promotion_readiness_contract"]["requirements"][
        "external_provider_public_claim_allowed"
    ] is False


def test_write_evidence_bundle_payload_uses_utf8_json(tmp_path):
    path = tmp_path / "bundle.json"
    finalized = {"schema": "demo", "text": "成本效率"}

    written = write_evidence_bundle_payload(path, finalized)

    assert written == path
    assert json.loads(path.read_text(encoding="utf-8")) == finalized


def test_summarize_rubric_contract_rows_returns_zero_rates_for_empty_rows():
    assert summarize_rubric_contract_rows([]) == {
        "rows": 0,
        "overall_pass_rate": 0.0,
        "plan_pass_rate": 0.0,
        "evidence_pass_rate": 0.0,
        "delivery_pass_rate": 0.0,
        "cost_pass_rate": 0.0,
        "hard_fail_reasons": [],
    }


def test_summarize_rubric_contract_rows_counts_section_pass_rates_and_reasons():
    rows = [
        {
            "rubric_contract_status": "PASS",
            "rubric_contract": {
                "plan_rubric": {"status": "PASS"},
                "evidence_rubric": {"status": "PASS"},
                "delivery_rubric": {"status": "PASS"},
                "cost_rubric": {"status": "PASS"},
            },
            "rubric_contract_hard_fail_reasons": ["missing_trace"],
        },
        {
            "rubric_contract_status": "RETURN",
            "rubric_contract": {
                "plan_rubric": {"status": "PASS"},
                "evidence_rubric": {"status": "RETURN"},
                "delivery_rubric": {"status": "PASS"},
                "cost_rubric": {"status": "RETURN"},
            },
            "rubric_contract_hard_fail_reasons": ["missing_trace", "cost_data_missing"],
        },
    ]

    summary = summarize_rubric_contract_rows(rows)

    assert summary == {
        "rows": 2,
        "overall_pass_rate": 0.5,
        "plan_pass_rate": 1.0,
        "evidence_pass_rate": 0.5,
        "delivery_pass_rate": 1.0,
        "cost_pass_rate": 0.5,
        "hard_fail_reasons": ["cost_data_missing", "missing_trace"],
    }


def test_build_rubric_contract_bundle_centralizes_summary_schema():
    pass_row = {
        "rubric_contract_status": "PASS",
        "rubric_contract": {
            "plan_rubric": {"status": "PASS"},
            "evidence_rubric": {"status": "PASS"},
            "delivery_rubric": {"status": "PASS"},
            "cost_rubric": {"status": "PASS"},
        },
    }

    bundle = build_rubric_contract_bundle(
        with_rows=[pass_row],
        without_rows=[],
        eligible_with=[pass_row],
        eligible_without=[],
    )

    assert bundle["schema"] == "nexus_rubric_contract_bundle_v1"
    assert bundle["with_nexus"]["overall_pass_rate"] == 1.0
    assert bundle["without_nexus"]["rows"] == 0
    assert bundle["eligible_with_nexus"]["plan_pass_rate"] == 1.0
    assert bundle["eligible_without_nexus"]["hard_fail_reasons"] == []
    assert bundle["claim_boundary"] == [
        "Rubric PASS is required before public or training claims.",
        "Behavioral success with missing required artifacts remains observation-only.",
        "Cost efficiency wording requires cost rubric PASS plus sample sufficiency.",
    ]


def test_build_telemetry_completeness_section_preserves_gateway_stats_rates():
    section = build_telemetry_completeness_section(
        token_measured_rate_without=1.0,
        token_measured_rate_with=0.5,
        provider_token_measured_rate_without=0.75,
        provider_token_measured_rate_with=0.25,
        without_rows=[
            {"gateway_stats_present": True},
            {"gateway_stats_present": False},
            {},
        ],
        with_rows=[
            {"gateway_stats_present": True},
            {"gateway_stats_present": True},
        ],
    )

    assert section == {
        "token_measured_rate_without": 1.0,
        "token_measured_rate_with": 0.5,
        "provider_token_measured_rate_without": 0.75,
        "provider_token_measured_rate_with": 0.25,
        "gateway_stats_source_rate_without": 0.3333,
        "gateway_stats_source_rate_with": 1.0,
    }


def test_build_nexus_wearing_context_preserves_local_reflex_execution_semantics():
    context = build_nexus_wearing_context(
        [
            {
                "model_uses_nexus": False,
                "gemini_uses_nexus": False,
                "nexus_wearing_valid": True,
                "nexus_context_delivered": True,
                "nexus_usage_valid": False,
                "capability_claim_verified": True,
                "route_decision_schema_version": "v1",
                "local_success_source": "deterministic_rescue",
                "semantic_completed": True,
                "hidden_verifier_passed": True,
                "report_trust_mismatch": False,
            },
            {
                "model_uses_nexus": True,
                "gemini_uses_nexus": False,
                "nexus_wearing_valid": True,
                "nexus_context_delivered": True,
                "nexus_usage_valid": True,
                "capability_claim_verified": True,
                "route_decision_schema_version": "v1",
            },
        ]
    )

    assert context.local_reflex_verified_rate == 0.5
    assert context.nexus_system_execution_valid_rate == 1.0
    assert context.nexus_system_usage_valid_rate == 1.0
    assert context.payload == {
        "valid_rate": 1.0,
        "gemini_uses_nexus_rate": 0.0,
        "model_uses_nexus_rate": 0.5,
        "nexus_context_delivered_rate": 1.0,
        "nexus_usage_valid_rate": 0.5,
        "claim_verified_rate": 1.0,
    }


def test_build_wall_ledger_conservation_section_preserves_claim_boundary():
    with_summary = {"schema": "nexus_wall_ledger_conservation_summary_v1", "conserved_rate": 1.0}
    without_summary = {"schema": "nexus_wall_ledger_conservation_summary_v1", "conserved_rate": 0.5}

    section = build_wall_ledger_conservation_section(
        wall_ledger_summary_with=with_summary,
        wall_ledger_summary_without=without_summary,
        wall_ledger_invalid=True,
    )

    assert section == {
        "schema": "nexus_wall_ledger_conservation_bundle_v1",
        "with_nexus": with_summary,
        "without_nexus": without_summary,
        "telemetry_invalid": True,
        "claim_boundary": [
            "Telemetry-invalid wall ledger rows are excluded from cost-efficiency claims.",
            "A conserved ledger requires complete required components and reconciliation error below 5 percent.",
        ],
    }


def test_build_warning_clean_gate_section_preserves_verdict_and_boundaries():
    summary = {"schema": "nexus_warning_rows_v1", "warning_clean": False}

    section = build_warning_clean_gate_section(
        warning_ledger_summary=summary,
        warning_ledger_invalid=True,
        warning_ledger_required=True,
    )

    assert section == {
        "schema": "nexus_warning_clean_gate_v1",
        "verdict": "RETURN",
        "required": True,
        "checks": summary,
        "claim_boundary": [
            "Public candidate runs require process-level warning capture.",
            "Warnings that are present but uncaptured or unclassified force RETURN.",
        ],
    }


def test_build_posture_finalization_gate_section_preserves_public_wording_gate():
    allowed = build_posture_finalization_gate_section(
        cost_efficiency_status="IMPROVED",
        cost_efficiency_sample_sufficient=True,
        valid_comparison_ready=True,
        training_eligibility_posture={"status": "ELIGIBLE"},
    )
    blocked = build_posture_finalization_gate_section(
        cost_efficiency_status="IMPROVED",
        cost_efficiency_sample_sufficient=True,
        valid_comparison_ready=False,
        training_eligibility_posture={"status": "OBSERVATION_ONLY"},
    )

    assert allowed == {
        "schema": "nexus_posture_finalization_gate_v1",
        "public_efficiency_wording_allowed": True,
        "training_eligible_requires": [
            "non_regressed",
            "full_contracts",
            "telemetry_clean",
            "sample_sufficient",
        ],
        "current_training_status": "ELIGIBLE",
    }
    assert blocked["public_efficiency_wording_allowed"] is False
    assert blocked["current_training_status"] == "OBSERVATION_ONLY"


def test_build_evidence_bundle_header_section_preserves_metadata_defaults():
    header = build_evidence_bundle_header_section(
        created_at_unix=123,
        run_identity={"runner_command": "run", "cwd": "/repo"},
        model_lock={"same_model": True},
        task_manifest={"tasks_file": "tasks.json"},
        taskset_contract={"schema": "taskset"},
        public_disclosure_manifest=None,
        timeouts={"timeout_sec": 30},
        config={"runner_command": "run"},
        raw_files={"with_nexus": {"sha256": "a"}, "without_nexus": {"sha256": "b"}},
        artifact_files={"artifact.json": {"sha256": "c"}},
        row_count=2,
        row_counts={"with_nexus": 1, "without_nexus": 1},
    )

    assert header == {
        "schema": "nexus_public_benchmark_evidence_bundle_v2",
        "created_at_unix": 123,
        "run_identity": {"runner_command": "run", "cwd": "/repo"},
        "model_lock": {"same_model": True},
        "task_manifest": {"tasks_file": "tasks.json"},
        "taskset_contract": {"schema": "taskset"},
        "public_disclosure_manifest": {
            "path": "",
            "sha256": "",
            "status": "not_provided",
            "failures": [],
        },
        "timeouts": {"timeout_sec": 30},
        "config": {"runner_command": "run"},
        "raw_files": {"with_nexus": {"sha256": "a"}, "without_nexus": {"sha256": "b"}},
        "artifact_files": {"artifact.json": {"sha256": "c"}},
        "row_count": 2,
        "row_counts": {"with_nexus": 1, "without_nexus": 1},
    }


def test_build_evidence_bundle_computed_sections_preserves_section_order_and_values():
    sections = build_evidence_bundle_computed_sections(
        route_cost_ledger={"schema": "nexus_route_cost_ledger_v1"},
        route_cost_trace_report={"schema": "nexus_route_cost_trace_report_v1"},
        commercial_model_roi_shadow_hooks={"schema": "nexus_commercial_model_roi_shadow_hooks_v1"},
        infra_quarantine_report={"schema": "nexus_infra_quarantine_report_v1"},
        session_worker_contamination={"schema": "nexus_session_worker_contamination_v1"},
        outbound_prompt_ledger_summary={"schema": "nexus_outbound_prompt_ledger_summary_v1"},
        public_lane_contract={"schema": "nexus_public_lane_contract_v1"},
        route_policy_evidence_contract={"schema": "nexus_route_policy_evidence_contract_v1"},
        expected_capability_evidence_contract={"schema": "nexus_expected_capability_evidence_contract_v1"},
        skill_mount_evidence_contract={"schema": "nexus_skill_mount_evidence_contract_v1"},
        s2t_shadow_report={"schema": "nexus_s2t_shadow_report_v1"},
        s2t_policy_draft={"schema": "nexus_promoted_s2t_policy_draft_v1"},
        product_kpis={"schema": "nexus_product_kpis_v1"},
        openseeker_kpis={"schema": "nexus_openseeker_benchmark_kpis_v1"},
    )

    assert list(sections) == [
        "route_cost_ledger",
        "route_cost_trace_report",
        "commercial_model_roi_shadow_hooks",
        "infra_quarantine_report",
        "session_worker_contamination",
        "outbound_prompt_ledger_gate",
        "public_lane_contract",
        "route_policy_evidence_contract",
        "expected_capability_evidence_contract",
        "skill_mount_evidence_contract",
        "s2t_shadow_report",
        "s2t_policy_draft",
        "product_kpis",
        "openseeker_alignment",
    ]
    assert sections["outbound_prompt_ledger_gate"]["schema"] == "nexus_outbound_prompt_ledger_summary_v1"
    assert sections["openseeker_alignment"]["schema"] == "nexus_openseeker_benchmark_kpis_v1"


def test_build_evidence_bundle_claim_posture_sections_preserves_gate_order_and_values():
    sections = build_evidence_bundle_claim_posture_sections(
        public_claim_gates={
            "public_claim_gate": {"verdict": "PASS"},
            "public_cost_claim_gate": {"verdict": "PASS"},
        },
        valid_comparison_readiness_gate={"status": "PASS"},
        direction_magnitude_gate={"status": "IMPROVED"},
        x3_promotion_gate={"status": "RETURN"},
        mutation_hardening_gate={"status": "PASS"},
        posture_finalization_gate={"schema": "nexus_posture_finalization_gate_v1"},
        public_claim_posture={"public_wording_key": "claim_ready"},
        training_eligibility_posture={"status": "ELIGIBLE"},
    )

    assert list(sections) == [
        "public_claim_gate",
        "public_cost_claim_gate",
        "valid_comparison_readiness_gate",
        "direction_magnitude_gate",
        "x3_promotion_gate",
        "mutation_hardening_gate",
        "posture_finalization_gate",
        "public_claim_posture",
        "training_eligibility_posture",
    ]
    assert sections["public_claim_gate"]["verdict"] == "PASS"
    assert sections["valid_comparison_readiness_gate"]["status"] == "PASS"
    assert sections["training_eligibility_posture"]["status"] == "ELIGIBLE"


def test_build_evidence_bundle_payload_preserves_top_level_section_order():
    payload = build_evidence_bundle_payload(
        header_section={"schema": "nexus_public_benchmark_evidence_bundle_v2", "row_count": 2},
        telemetry_completeness={"schema": "telemetry"},
        rubric_contract={"schema": "rubric"},
        wall_ledger_conservation={"schema": "wall"},
        warning_clean_gate={"schema": "warning"},
        computed_sections={
            "route_cost_ledger": {"schema": "route_cost"},
            "public_lane_contract": {"schema": "lane"},
        },
        nexus_wearing={"valid_rate": 1.0},
        claim_posture_sections={
            "public_claim_gate": {"verdict": "PASS"},
            "public_claim_posture": {"status": "PASS"},
        },
    )

    assert list(payload) == [
        "schema",
        "row_count",
        "telemetry_completeness",
        "rubric_contract",
        "wall_ledger_conservation",
        "warning_clean_gate",
        "route_cost_ledger",
        "public_lane_contract",
        "nexus_wearing",
        "public_claim_gate",
        "public_claim_posture",
    ]
    assert payload["telemetry_completeness"]["schema"] == "telemetry"
    assert payload["nexus_wearing"]["valid_rate"] == 1.0
