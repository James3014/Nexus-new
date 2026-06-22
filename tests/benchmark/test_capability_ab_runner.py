from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import pytest

import scripts.bench.capability_ab_runner as capability_ab_runner
from scripts.bench.build_sanitized_runner import (
    _learn_metadata_commit_hook,
    _session_marker_paths,
    _session_marker_reset_hook,
    build_sanitized_runner,
)
from scripts.bench.gemini_nexus_report import _claim_posture_lines
from scripts.bench.persistent_worker_gap_dashboard import build_gap_dashboard
from scripts.bench.public_lane_contract import (
    build_external_provider_claim_boundary_contract,
    build_expected_capability_evidence_contract,
    build_public_claim_gates,
    build_public_promotion_readiness_contract,
    build_route_policy_evidence_contract,
    build_skill_mount_evidence_contract,
    commercial_model_basis_gate_failures,
    derive_public_gate_failures,
)
from scripts.bench.route_execution_policy import decide_route_execution_policy
from scripts.bench.taskset_contract import (
    build_benchmark_basis_contract,
    build_prompt_contract_hash,
    build_provider_transport_contract_hash,
    build_taskset_contract,
)
from scripts.bench.warning_ledger import annotate_row as annotate_warning_row
from scripts.bench.warning_ledger import capture_python_warnings
from scripts.bench.warning_ledger import records_from_text as warning_records_from_text
from nexus.research.local_sprint_mutator import generate_local_candidate
from scripts.bench.capability_ab_runner import (
    CapabilityTask,
    _annotate_benchmark_eligibility,
    _annotate_with_contract,
    _apply_data_contract_audit,
    _apply_per_task_stop_loss,
    _benchmark_memory_db_path,
    _budget_exceeded,
    _classify_hidden_retry_failure,
    _classify_timeout_stage,
    _classify_r_phase_cost,
    _hidden_verifier_infra_reason,
    _nexus_cli_subprocess_cmd,
    _direct_gemini_timeout_sec,
    _direct_provider_infra_row,
    _direct_provider_timeout_row,
    _direct_infra_abort_reason,
    _direct_timeout_abort_reason,
    _ask_direct_codex_patch,
    _emit_progress,
    _effective_total_timeout_sec,
    _external_model_name_for_provider,
    _extract_record,
    _extract_json_payload,
    _summarize_rlm_trace,
    _summarize_benchmark_rows,
    _ensure_expected_capability_receipts,
    _expected_capability_receipt_coverage,
    _string_literals,
    evaluate_wall_ledger_conservation,
    expand_task_trials,
    _force_learn_slo_ready,
    _history_policy_name,
    _hyper_admission_after_model_attempt,
    _hidden_verifier_mode_enabled,
    _hidden_retry_decision_for_failure,
    _hidden_test_for_visible_test,
    _ask_direct_gemini_flash_patch,
    _ask_direct_codex_patch,
    _parse_direct_patch_json,
    _direct_codex_timeout_sec,
    _extract_codex_stdout_tokens,
    _expected_capability_coverage,
    _expected_capability_invocation_coverage,
    _prompt_leak_audit_failures,
    _prompt_leak_literal_is_structured,
    _benchmark_gateway_timeout_for_task,
    _benchmark_gateway_timeout_for_execution,
    _benchmark_gateway_timeout_sec,
    benchmark_skill_mount_requests,
    _build_parallel_smoke_rows,
    build_public_benchmark_preflight,
    _materialize_fixture,
    _merge_receipt_first_probe,
    _model_required_execution_policy,
    main,
    _nexus_task_desc,
    _nexus_codex_hidden_verifier_guidance,
    _compact_nexus_route_for_prompt,
    _parse_direct_gemini_json,
    _python_syntax_warning,
    _apply_direct_gemini_stats_outlier_policy,
    _post_model_deterministic_rescue_infra_allowed,
    _reconcile_benchmark_skill_mount_contract_from_expected_receipts,
    _reconcile_skill_mount_contract_after_receipts,
    _with_nexus_row_fail_fast_reason,
    _pytest_verifier_cmd,
    _read_preserved_target,
    _remaining_leg_timeout,
    _remaining_task_timeout,
    _report_model_label,
    _route_cost_controls_prefer_baseline_fast_path,
    _runner_overhead_polluted,
    _runner_overhead_class,
    _route_oracle_force_flow_policy,
    _render_partial_markdown_report,
    _restore_preserved_target,
    _resolve_task_files,
    _run_process_group,
    _looks_like_gemini_auth_prompt,
    _tail_text,
    _task_uses_materialized_fixture,
    _without_tasks_for_run,
    _with_nexus_timeout_payload,
    _write_trial_evidence,
    assert_clean_worktree,
    filter_tasks_by_id,
    filter_tasks_by_repo_kind,
    load_tasks,
    run_with_nexus,
    run_without_nexus,
    select_tasks,
    write_evidence_bundle,
    write_jsonl,
)


def test_benchmark_skill_mount_requests_maps_expected_capabilities(monkeypatch):
    monkeypatch.setenv("NEXUS_BENCH_SKILL_MOUNTS", "1")
    task = CapabilityTask(
        id="skill-map-001",
        difficulty="medium",
        task_type="public_bugfix",
        task_desc="Fix a semantic failure",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=("hyper", "codeintel", "claim_gate", "hyper"),
    )

    assert benchmark_skill_mount_requests(task) == [
        "tdd",
        "improve-codebase-architecture",
        "nexus-root-cause-probe",
    ]


def test_benchmark_skill_mount_requests_maps_research_capability(monkeypatch):
    monkeypatch.setenv("NEXUS_BENCH_SKILL_MOUNTS", "1")
    task = CapabilityTask(
        id="skill-map-research",
        difficulty="medium",
        task_type="public_docs_code_sync",
        task_desc="Research supporting evidence",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=("research",),
    )

    assert benchmark_skill_mount_requests(task) == ["notebooklm-context-bridge"]


def test_benchmark_skill_mount_requests_maps_skill_validation_long_tail(monkeypatch):
    monkeypatch.setenv("NEXUS_BENCH_SKILL_MOUNTS", "1")
    task = CapabilityTask(
        id="skill-map-long-tail",
        difficulty="medium",
        task_type="public_ops_research",
        task_desc="Validate long-tail skill mounts",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=(
            "memory",
            "semantic_searcher",
            "swarm_quiet_moment",
            "bdd_acceptance_skill",
        ),
    )

    assert benchmark_skill_mount_requests(task) == [
        "notebooklm-context-bridge",
        "nexus-goal-closure-executor",
        "tdd",
    ]


def test_reconcile_benchmark_skill_mount_from_expected_receipts(tmp_path, monkeypatch):
    status_report = tmp_path / "skill_status.json"
    status_report.write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "name": "nexus-root-cause-probe",
                        "path": "/repo/.agents/skills/nexus-root-cause-probe/SKILL.md",
                        "skill_status": "nexus_curated_candidate",
                        "capability_mount": "governance_and_trust",
                        "action": "eligible_for_capability_mount_review",
                    },
                    {
                        "name": "nexus-benchmark-public-report",
                        "path": "/repo/.agents/skills/nexus-benchmark-public-report/SKILL.md",
                        "skill_status": "nexus_curated_candidate",
                        "capability_mount": "benchmark_and_promotion",
                        "action": "eligible_for_capability_mount_review",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_BENCH_SKILL_MOUNTS", "1")
    monkeypatch.setenv("NEXUS_BENCH_SKILL_STATUS_REPORT", str(status_report))
    task = CapabilityTask(
        id="skill-reconcile-001",
        difficulty="medium",
        task_type="public_bugfix",
        task_desc="Fix hidden verifier claim",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=("claim_gate", "delivery_gate"),
    )
    row = {
        "status": "SUCCESS",
        "provider_token_measured": True,
        "model_calls": 1,
        "total_tokens": 10,
        "capability_receipts": [
            {
                "name": "claim_gate",
                "public_claim_safe": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "evidence_refs": ["claim_gate:evidence"],
            },
            {
                "name": "delivery_gate",
                "public_claim_safe": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "evidence_refs": ["delivery_gate:evidence"],
            },
        ],
        "skill_mount_contract": [],
        "skill_mount_violations": [
            {
                "skill_name": "nexus-root-cause-probe",
                "path": "",
                "reason": "skill_mount_not_confirmed_by_runtime_receipt",
            }
        ],
        "skill_mount_contract_status": "EMPTY",
    }

    _reconcile_benchmark_skill_mount_contract_from_expected_receipts(row, task=task, repo_root=tmp_path)

    assert row["skill_mount_contract_status"] == "PASS"
    assert row["skill_mount_count"] == 2
    assert {item["skill_id"] for item in row["skill_mount_contract"]} == {
        "nexus-root-cause-probe",
        "nexus-benchmark-public-report",
    }
    assert row["skill_mount_violations"] == []
    assert _with_nexus_row_fail_fast_reason(row, task=task) == ""


def test_reconcile_benchmark_skill_mount_allows_reference_ablation_receipt(tmp_path, monkeypatch):
    status_report = tmp_path / "skill_status.json"
    status_report.write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "name": "research-citation-chain-verifier",
                        "path": "/repo/.agents/skills/research-citation-chain-verifier/SKILL.md",
                        "skill_status": "external_reference_candidate",
                        "capability_mount": "reference:research_and_source_discipline",
                        "action": "candidate_only_until_live_receipts",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS", "1")
    monkeypatch.setenv("NEXUS_BENCH_SKILL_MOUNT_REQUESTS", '["research-citation-chain-verifier"]')
    monkeypatch.setenv("NEXUS_BENCH_SKILL_STATUS_REPORT", str(status_report))
    task = CapabilityTask(
        id="research-skill-reconcile-001",
        difficulty="medium",
        task_type="public_research",
        task_desc="Verify source chain",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=("research_and_source_discipline",),
    )
    row = {
        "status": "SUCCESS",
        "provider_token_measured": True,
        "model_calls": 1,
        "total_tokens": 10,
        "capability_receipts": [
            {
                "name": "research",
                "public_claim_safe": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "evidence_refs": ["source_discipline:evidence"],
            }
        ],
        "skill_mount_contract": [],
        "skill_mount_violations": [],
        "skill_mount_contract_status": "EMPTY",
    }

    _reconcile_benchmark_skill_mount_contract_from_expected_receipts(row, task=task, repo_root=tmp_path)

    assert row["skill_mount_contract_status"] == "PASS"
    assert row["skill_mount_count"] == 1
    contract = row["skill_mount_contract"][0]
    assert contract["skill_id"] == "research-citation-chain-verifier"
    assert contract["capability_mount"] == "research_and_source_discipline"
    assert contract["capability"] == "research"
    assert "benchmark_ablation_only_mount" in contract["load_reason_codes"]
    assert row["skill_mount_violations"] == []
    assert _with_nexus_row_fail_fast_reason(row, task=task) == ""


def test_with_nexus_fail_fast_allows_normalized_cumulative_token_stats():
    task = CapabilityTask(
        id="token-normalized-001",
        difficulty="medium",
        task_type="public_feature",
        task_desc="Implement feature",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=(),
    )
    row = {
        "status": "SUCCESS",
        "report_trust_mismatch": False,
        "model_calls": 1,
        "provider_token_measured": False,
        "total_tokens": 313,
        "token_ledger_normalized_tokens": 313,
        "token_ledger_status": "normalized_from_cumulative_stats",
        "skill_mount_contract_status": "EMPTY",
        "skill_mount_violations": [],
    }

    assert _with_nexus_row_fail_fast_reason(row, task=task) == ""


def test_benchmark_skill_mount_requests_honors_explicit_env(monkeypatch):
    monkeypatch.setenv("NEXUS_BENCH_SKILL_MOUNT_REQUESTS", '["diagnose", {"skill_id": "tdd"}, "diagnose"]')
    task = CapabilityTask(
        id="skill-map-explicit",
        difficulty="medium",
        task_type="public_bugfix",
        task_desc="Fix a semantic failure",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=("hyper",),
    )

    assert benchmark_skill_mount_requests(task) == ["diagnose", "tdd"]


def test_benchmark_skill_mount_requests_ignores_explicit_env_when_ablation_disallowed(monkeypatch):
    monkeypatch.setenv("NEXUS_BENCH_SKILL_MOUNT_REQUESTS", '["candidate-skill"]')
    monkeypatch.setenv("NEXUS_BENCH_ALLOW_ABLATION_SKILL_MOUNTS", "0")
    task = CapabilityTask(
        id="skill-map-explicit-blocked",
        difficulty="medium",
        task_type="public_bugfix",
        task_desc="Fix a semantic failure",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=("hyper",),
    )

    assert benchmark_skill_mount_requests(task) == []


def _route_policy(reason_codes: list[str] | None = None) -> dict[str, object]:
    return {
        "reason_codes": list(reason_codes or []),
        "pre_model_deterministic_rescue_allowed": False,
    }


def test_post_model_deterministic_rescue_allows_recoverable_receipt_violation():
    assert _post_model_deterministic_rescue_infra_allowed({"infra_invalid_reason": ""}) is True
    assert (
        _post_model_deterministic_rescue_infra_allowed(
            {
                "infra_invalid_reason": "receipt_data_contract_violation",
                "nexus_failure_recoverable": True,
                "nexus_failure_reasons": ["tests_failed"],
            }
        )
        is True
    )
    assert (
        _post_model_deterministic_rescue_infra_allowed(
            {
                "infra_invalid_reason": "receipt_data_contract_violation",
                "nexus_failure_recoverable": False,
                "nexus_failure_reasons": ["tests_failed"],
            }
        )
        is False
    )
    assert _post_model_deterministic_rescue_infra_allowed({"infra_invalid_reason": "model_call_without_tokens"}) is False


def test_reconcile_skill_mount_after_receipt_backfill(tmp_path: Path, monkeypatch):
    status_report = tmp_path / "skill_status.json"
    status_report.write_text(
        json.dumps(
            {
                "skills": [
                    {
                        "name": "nexus-root-cause-probe",
                        "path": "/repo/.agents/skills/nexus-root-cause-probe/SKILL.md",
                        "root": "nexus_repo",
                        "skill_status": "nexus_curated_candidate",
                        "test_level": "routing_plus_e2e",
                        "action": "eligible_for_capability_mount_review",
                        "capability_mount": "governance_and_trust",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_BENCH_SKILL_STATUS_REPORT", str(status_report))
    row = {
        "skill_mount_contract": [],
        "skill_mount_violations": [
            {
                "skill_name": "nexus-root-cause-probe",
                "path": "",
                "reason": "skill_mount_not_confirmed_by_runtime_receipt",
            }
        ],
        "capability_receipts": [
            {
                "name": "ultra_review",
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "public_claim_safe": True,
                "evidence_refs": ["ultra_review:verified"],
            }
        ],
    }

    _reconcile_skill_mount_contract_after_receipts(row, repo_root=tmp_path)

    assert row["skill_mount_count"] == 1
    assert row["skill_mount_contract_status"] == "PASS"
    assert row["skill_mount_violations"] == []
    assert row["skill_mount_contract"][0]["skill_id"] == "nexus-root-cause-probe"
    assert row["skill_mount_contract"][0]["capability"] == "ultra_review"


def test_python_syntax_warning_detects_return_in_finally():
    warning = _python_syntax_warning("def f():\n    try:\n        pass\n    finally:\n        return 1\n")

    assert "return" in warning
    assert "finally" in warning


def test_public_claim_gate_builder_keeps_delivery_and_cost_scopes_separate():
    gates = build_public_claim_gates(
        delivery_gate_passed=True,
        cost_claim_passed=False,
        cost_efficiency_status="REGRESSED",
        delivery_gate_failures=[],
        cost_gate_failures=["with_token_measured_below_threshold"],
        cost_efficiency_failures=["token_cost_not_improved"],
        public_gate_checks={"hidden_verifier_mode": True},
    )

    assert gates["public_delivery_gate"]["verdict"] == "PASS"
    assert gates["public_cost_claim_gate"]["verdict"] == "FAIL"
    assert gates["public_claim_gate"]["verdict"] == "FAIL"
    assert gates["public_cost_claim_gate"]["checks"]["delivery_gate_passed"] is True
    assert gates["public_cost_claim_gate"]["checks"]["cost_claim_public_safe"] is False
    assert gates["public_cost_efficiency_claim_gate"]["claim_scope"] == "cost_efficiency_direction_only"


def test_public_claim_gate_builder_blocks_cost_claim_when_delivery_fails_without_cost_failure():
    gates = build_public_claim_gates(
        delivery_gate_passed=False,
        cost_claim_passed=False,
        cost_efficiency_status="REGRESSED",
        delivery_gate_failures=["hidden_verifier_disabled"],
        cost_gate_failures=[],
        cost_efficiency_failures=["hidden_verifier_disabled"],
        public_gate_checks={"hidden_verifier_mode": False},
    )

    assert gates["public_delivery_gate"]["verdict"] == "FAIL"
    assert gates["public_delivery_gate"]["failures"] == ["hidden_verifier_disabled"]
    assert gates["public_cost_claim_gate"]["verdict"] == "FAIL"
    assert gates["public_cost_claim_gate"]["failures"] == ["hidden_verifier_disabled"]
    assert gates["public_cost_claim_gate"]["checks"]["cost_claim_public_safe"] is False
    assert "with_token_measured_below_threshold" not in gates["public_cost_claim_gate"]["failures"]


def test_public_promotion_readiness_contract_requires_all_public_gates():
    bundle = {
        "public_claim_gate": {
            "checks": {
                "with_trust_mismatch_rate": 0.0,
                "without_trust_mismatch_rate": 0.0,
                "wall_ledger_with_conserved_rate": 1.0,
                "wall_ledger_without_conserved_rate": 1.0,
                "provider_token_measured_rate_with": 1.0,
                "provider_token_measured_rate_without": 1.0,
            }
        },
        "public_verified_delivery_claim_gate": {"verdict": "PASS", "failures": []},
        "public_cost_claim_gate": {"verdict": "PASS", "failures": []},
        "public_cost_efficiency_claim_gate": {"verdict": "IMPROVED", "failures": []},
        "x3_promotion_gate": {"status": "PASS", "failures": []},
        "valid_comparison_readiness_gate": {"status": "PASS", "failures": []},
        "route_policy_evidence_contract": {"status": "PASS", "failures": []},
        "expected_capability_evidence_contract": {"status": "PASS", "failures": []},
        "external_provider_claim_boundary_contract": {"status": "PASS", "public_claim_allowed": True, "failures": []},
        "taskset_contract": {"fixed_public_taskset_ready": True},
        "session_worker_contamination": {"clean": True, "contamination_rate": 0.0},
        "outbound_prompt_ledger_gate": {"status": "PASS", "forbidden_literal_count": 0},
    }

    ready = build_public_promotion_readiness_contract(bundle)
    assert ready["status"] == "PASS"
    assert ready["promotion_allowed"] is True

    bundle["public_cost_efficiency_claim_gate"] = {"verdict": "REGRESSED", "failures": ["wall_cost_not_improved"]}
    blocked = build_public_promotion_readiness_contract(bundle)
    assert blocked["status"] == "RETURN"
    assert blocked["promotion_allowed"] is False
    assert "public_cost_efficiency_non_regressed" in blocked["failures"]
    assert "public_cost_efficiency_claim_gate:wall_cost_not_improved" in blocked["failures"]


def test_external_provider_claim_boundary_blocks_codex_public_claims():
    contract = build_external_provider_claim_boundary_contract(
        {
            "config": {"with_model_provider": "codex", "without_mode": "codex"},
            "model_lock": {"codex_model_name": "gpt-5.5", "direct_codex_model_name": "gpt-5.5"},
        }
    )

    assert contract["schema"] == "nexus_external_provider_claim_boundary_contract_v1"
    assert contract["status"] == "OBSERVATION_ONLY"
    assert contract["public_claim_allowed"] is False
    assert "codex_provider_prompt_wearing_only_for_external_model_claims" in contract["failures"]


def test_expected_capability_evidence_contract_fails_missing_receipt():
    contract = build_expected_capability_evidence_contract(
        [
            {
                "mode": "with_nexus",
                "run_eligible": True,
                "task_id": "route-oracle-swarm-001",
                "trial_index": 1,
                "expected_capability_receipt_coverage": {
                    "expected": ["swarm"],
                    "public_safe": [],
                    "missing": ["swarm"],
                    "all_public_safe": False,
                },
                "expected_capability_invocation_coverage": {
                    "expected": ["swarm"],
                    "invoked": ["swarm"],
                    "missing": [],
                    "all_invoked_with_evidence": True,
                },
            }
        ]
    )

    assert contract["status"] == "RETURN"
    assert contract["failures"] == ["route-oracle-swarm-001:1:receipt_missing:swarm"]


def test_expected_capability_evidence_contract_fails_missing_invocation():
    contract = build_expected_capability_evidence_contract(
        [
            {
                "mode": "with_nexus",
                "run_eligible": True,
                "task_id": "rlm-harder-v2-second-round-002",
                "trial_index": 1,
                "expected_capability_receipt_coverage": {
                    "expected": ["hyper"],
                    "public_safe": ["hyper"],
                    "missing": [],
                    "all_public_safe": True,
                },
                "expected_capability_invocation_coverage": {
                    "expected": ["hyper"],
                    "invoked": [],
                    "missing": ["hyper"],
                    "all_invoked_with_evidence": False,
                },
            }
        ]
    )

    assert contract["status"] == "RETURN"
    assert contract["failures"] == ["rlm-harder-v2-second-round-002:1:invocation_missing:hyper"]


def _receipt_lite_contract_for(receipt_overrides: dict[str, object], *, semantic_status: str = "VERIFIED") -> dict[str, object]:
    receipt = {
        "name": "hyper",
        "selected": True,
        "invoked": True,
        "evidence_present": True,
        "gate_passed": True,
        "outcome_contributed": True,
        "selection_source": "deterministic_receipt_lite",
        "evidence_refs": ["hyper:t:hidden_verifier"],
        "source_refs": ["hyper:t:hidden_verifier"],
        "replay_refs": ["hidden_verifier:t"],
        "distinct_roles": ["capability_executor", "hidden_verifier"],
        "semantic_evidence_complete": True,
        "public_claim_safe": True,
    }
    receipt.update(receipt_overrides)
    return build_expected_capability_evidence_contract(
        [
            {
                "mode": "with_nexus",
                "run_eligible": True,
                "task_id": "t",
                "trial_index": 1,
                "semantic_status": semantic_status,
                "expected_capabilities": ["hyper"],
                "capability_receipts": [receipt],
                "expected_capability_receipt_coverage": {
                    "expected": ["hyper"],
                    "public_safe": ["hyper"],
                    "missing": [],
                    "all_public_safe": True,
                },
                "expected_capability_invocation_coverage": {
                    "expected": ["hyper"],
                    "invoked": ["hyper"],
                    "missing": [],
                    "all_invoked_with_evidence": True,
                },
            }
        ]
    )


def test_expected_capability_evidence_contract_rejects_receipt_lite_missing_evidence_refs():
    contract = _receipt_lite_contract_for({"evidence_refs": []})

    assert contract["status"] == "RETURN"
    assert contract["failures"] == ["t:1:receipt_lite_missing_evidence_refs:hyper"]


def test_expected_capability_evidence_contract_rejects_receipt_lite_missing_distinct_roles():
    contract = _receipt_lite_contract_for({"distinct_roles": ["hidden_verifier"]})

    assert contract["status"] == "RETURN"
    assert contract["failures"] == ["t:1:receipt_lite_missing_distinct_roles:hyper"]


def test_expected_capability_evidence_contract_rejects_receipt_lite_missing_replay_refs():
    contract = _receipt_lite_contract_for({"replay_refs": []})

    assert contract["status"] == "RETURN"
    assert contract["failures"] == ["t:1:receipt_lite_missing_replay_refs:hyper"]


def test_expected_capability_evidence_contract_rejects_receipt_lite_missing_source_refs():
    contract = _receipt_lite_contract_for({"source_refs": []})

    assert contract["status"] == "RETURN"
    assert contract["failures"] == ["t:1:receipt_lite_missing_source_refs:hyper"]


def test_expected_capability_evidence_contract_rejects_receipt_lite_incomplete_semantic_evidence():
    contract = _receipt_lite_contract_for({"semantic_evidence_complete": False}, semantic_status="UNVERIFIED")

    assert contract["status"] == "RETURN"
    assert contract["failures"] == ["t:1:receipt_lite_semantic_evidence_incomplete:hyper"]


def test_public_promotion_readiness_contract_requires_external_provider_boundary():
    bundle = {
        "public_claim_gate": {
            "checks": {
                "with_trust_mismatch_rate": 0.0,
                "without_trust_mismatch_rate": 0.0,
                "wall_ledger_with_conserved_rate": 1.0,
                "wall_ledger_without_conserved_rate": 1.0,
                "provider_token_measured_rate_with": 1.0,
                "provider_token_measured_rate_without": 1.0,
            }
        },
        "public_verified_delivery_claim_gate": {"verdict": "PASS", "failures": []},
        "public_cost_claim_gate": {"verdict": "PASS", "failures": []},
        "public_cost_efficiency_claim_gate": {"verdict": "IMPROVED", "failures": []},
        "x3_promotion_gate": {"status": "PASS", "failures": []},
        "valid_comparison_readiness_gate": {"status": "PASS", "failures": []},
        "route_policy_evidence_contract": {"status": "PASS", "failures": []},
        "external_provider_claim_boundary_contract": {
            "status": "OBSERVATION_ONLY",
            "public_claim_allowed": False,
            "failures": ["codex_provider_prompt_wearing_only_for_external_model_claims"],
        },
        "taskset_contract": {"fixed_public_taskset_ready": True},
        "session_worker_contamination": {"clean": True, "contamination_rate": 0.0},
        "outbound_prompt_ledger_gate": {"status": "PASS", "forbidden_literal_count": 0},
    }

    blocked = build_public_promotion_readiness_contract(bundle)

    assert blocked["status"] == "RETURN"
    assert blocked["promotion_allowed"] is False
    assert "external_provider_public_claim_allowed" in blocked["failures"]
    assert (
        "external_provider_claim_boundary_contract:codex_provider_prompt_wearing_only_for_external_model_claims"
        in blocked["failures"]
    )


def test_route_policy_evidence_contract_blocks_missing_public_route_policy():
    contract = build_route_policy_evidence_contract(
        [
            {
                "task_id": "public-a",
                "trial_index": 1,
                "mode": "with_nexus",
                "run_eligible": True,
                "semantic_status": "VERIFIED",
            }
        ]
    )

    assert contract["status"] == "RETURN"
    assert contract["failures"] == ["public-a:1:route_execution_policy_missing"]


def test_route_policy_evidence_contract_accepts_verified_cost_capped_rescue():
    contract = build_route_policy_evidence_contract(
        [
            {
                "task_id": "public-a",
                "trial_index": 1,
                "mode": "with_nexus",
                "run_eligible": True,
                "capability_activation_contract": "cost_capped",
                "hidden_verifier_passed": True,
                "local_reflex_risk_level": "low",
                "local_reflex_bare_sufficiency": "high",
                "nexus_winner_source": "local_deterministic_pre_model_rescue",
                "route_execution_policy": {
                    "reason_codes": ["cost_capped_capability_allows_verified_pre_model_rescue"],
                    "pre_model_deterministic_rescue_allowed": True,
                },
            }
        ]
    )

    assert contract["status"] == "PASS"
    assert contract["cost_capped_rescue_rows"] == 1
    assert contract["failures"] == []


def test_route_policy_evidence_contract_blocks_unverified_cost_capped_rescue():
    contract = build_route_policy_evidence_contract(
        [
            {
                "task_id": "public-a",
                "trial_index": 1,
                "mode": "with_nexus",
                "run_eligible": True,
                "capability_activation_contract": "cost_capped",
                "hidden_verifier_passed": False,
                "local_reflex_risk_level": "low",
                "local_reflex_bare_sufficiency": "high",
                "nexus_winner_source": "local_deterministic_pre_model_rescue",
                "route_execution_policy": {
                    "reason_codes": ["cost_capped_capability_allows_verified_pre_model_rescue"],
                    "pre_model_deterministic_rescue_allowed": True,
                },
            }
        ]
    )

    assert contract["status"] == "RETURN"
    assert contract["failures"] == ["public-a:1:cost_capped_rescue_without_hidden_verifier_pass"]


def test_skill_mount_evidence_contract_accepts_causal_runtime_mount():
    contract = build_skill_mount_evidence_contract(
        [
            {
                "task_id": "skill-route-a",
                "trial_index": 1,
                "mode": "with_nexus",
                "run_eligible": True,
                "skill_mount_contract": {
                    "skill_id": "nexus-benchmark-public-report",
                    "skill_status": "nexus_curated_candidate",
                    "capability_mount": "benchmark_and_promotion",
                    "load_reason_codes": ["public_benchmark_report_required"],
                    "evidence_refs": ["row:skill-route-a:route_policy"],
                    "outcome_contributed": True,
                },
            }
        ]
    )

    assert contract["status"] == "PASS"
    assert contract["checked_mounts"] == 1
    assert contract["failures"] == []


def test_skill_mount_evidence_contract_rejects_quarantined_mount():
    contract = build_skill_mount_evidence_contract(
        [
            {
                "task_id": "skill-route-a",
                "trial_index": 1,
                "mode": "with_nexus",
                "run_eligible": True,
                "skill_mount_contract": {
                    "skill_id": "candidate-skill-from-run-001",
                    "skill_status": "candidate_quarantine",
                    "capability_mount": "repair_and_coding",
                    "load_reason_codes": [],
                    "evidence_refs": [],
                    "outcome_contributed": False,
                },
            }
        ]
    )

    assert contract["status"] == "RETURN"
    assert contract["failures"] == [
        "skill-route-a:1:skill_mount_missing_evidence_refs:candidate-skill-from-run-001",
        "skill-route-a:1:skill_mount_missing_load_reason_codes:candidate-skill-from-run-001",
        "skill-route-a:1:skill_mount_missing_outcome_contribution:candidate-skill-from-run-001",
        "skill-route-a:1:skill_mount_non_runtime_status:candidate-skill-from-run-001:candidate_quarantine",
    ]


def test_public_gate_requires_full_token_ledger_for_public_cost_claim():
    context = {
        "with_rows": [{"task_id": "a"}],
        "without_rows": [{"task_id": "a"}],
        "with_models": {"gemini-3-flash-preview"},
        "without_models": {"gemini-3-flash-preview"},
        "same_task_trials": True,
        "hidden_verifier_mode": True,
        "eligibility_complete": True,
        "with_trust_mismatch_rate": 0.0,
        "without_trust_mismatch_rate": 0.0,
        "nexus_valid_rate": 1.0,
        "nexus_system_execution_valid_rate": 1.0,
        "nexus_context_delivered_rate": 1.0,
        "nexus_system_usage_valid_rate": 1.0,
        "claim_verified_rate": 1.0,
        "route_decision_present_rate": 1.0,
        "token_measured_rate_with": 0.9999,
        "token_measured_rate_without": 1.0,
        "provider_token_measured_rate_with": 1.0,
        "provider_token_measured_rate_without": 1.0,
        "prompt_purity_gate_passed": True,
        "verified_equal_without_lift": False,
        "wall_cost_ratio_with_over_without": 1.0,
        "route_cost_regression_wall_ratio_threshold": 1.8,
        "wall_regression_systemic": False,
        "token_cost_ratio_with_over_without": 1.0,
        "route_cost_regression_token_ratio_threshold": 1.5,
        "token_regression_systemic": False,
    }

    failures = derive_public_gate_failures(context, {"tasks_file": "tasks.json", "tasks_manifest_hash": "abc", "runner_command": "cmd"})

    assert failures["delivery_gate_failures"] == []
    assert failures["cost_gate_failures"] == ["with_token_measured_below_threshold"]


def test_commercial_model_basis_gate_rejects_skill_fit_matrix_as_public_claim_basis(tmp_path: Path):
    matrix = tmp_path / "skill_fit_matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "schema": "nexus.skill_fit_execution_matrix.v1",
                "rows": [{"arm_type": "skill_ablation"}],
            }
        ),
        encoding="utf-8",
    )

    failures = commercial_model_basis_gate_failures(
        {"commercial_model_basis_required": True, "tasks_file": str(matrix)}
    )

    assert "commercial_model_basis:not_ready" in failures
    assert "commercial_model_basis:not_commercial_model_basis" in failures
    assert "commercial_model_basis:skill_fit_matrix_not_public_claim_basis" in failures
    assert "commercial_model_basis:ablation_rows_not_public_claim_basis" in failures


def test_commercial_model_basis_gate_accepts_compiled_commercial_manifest(tmp_path: Path):
    manifest = tmp_path / "commercial.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "nexus-public-commercial-lanes-v1:all",
                "commercial_lane_source": "scripts/bench/public_benchmark_commercial_lanes_v1.json",
                "tasks": [{"id": "task-1", "commercial_lane": "governed_delivery"}],
            }
        ),
        encoding="utf-8",
    )

    assert commercial_model_basis_gate_failures(
        {"commercial_model_basis_required": True, "tasks_file": str(manifest)}
    ) == []


def test_expected_capability_protection_blocks_hidden_lite_baseline_fast_path():
    assert not _route_cost_controls_prefer_baseline_fast_path(
        {
            "lite_route": True,
            "route_lane": "hidden_lite",
            "context_mode": "compact",
            "max_rounds": 1,
            "expected_capability_protection": ["hyper"],
        }
    )


def test_hidden_bugfix_supervised_lane_allows_deterministic_pre_rescue():
    controls = {
        "route_lane": "hidden_bugfix_supervised",
        "context_mode": "compact",
        "max_rounds": 1,
        "disable_research": True,
    }

    assert capability_ab_runner._route_cost_controls_allow_deterministic_pre_rescue(controls) is True


def test_hidden_bugfix_supervised_lane_allows_pre_model_deterministic_rescue_without_protected_capabilities():
    controls = {
        "route_lane": "hidden_bugfix_supervised",
        "context_mode": "compact",
        "max_rounds": 1,
        "disable_research": True,
    }

    assert capability_ab_runner._route_cost_controls_allow_pre_model_deterministic_rescue(controls) is False

    controls["allow_pre_model_deterministic_rescue"] = True
    assert capability_ab_runner._route_cost_controls_allow_pre_model_deterministic_rescue(controls) is True

    controls["expected_capability_protection"] = ["hyper"]
    assert capability_ab_runner._route_cost_controls_allow_pre_model_deterministic_rescue(controls) is False


def test_hidden_lite_lane_allows_explicit_pre_model_deterministic_rescue_without_protected_capabilities():
    controls = {
        "route_lane": "hidden_lite",
        "context_mode": "compact",
        "max_rounds": 1,
        "disable_research": True,
        "lite_route": True,
    }

    assert capability_ab_runner._route_cost_controls_allow_pre_model_deterministic_rescue(controls) is False

    controls["allow_pre_model_deterministic_rescue"] = True
    assert capability_ab_runner._route_cost_controls_allow_pre_model_deterministic_rescue(controls) is True

    controls["expected_capability_protection"] = ["hyper"]
    assert capability_ab_runner._route_cost_controls_allow_pre_model_deterministic_rescue(controls) is False


def test_route_execution_policy_records_model_required_pre_model_rescue_blocker():
    policy = decide_route_execution_policy(
        route_cost_controls={
            "route_lane": "hidden_lite",
            "context_mode": "compact",
            "max_rounds": 1,
            "disable_research": True,
            "lite_route": True,
            "supervised_bare_first": True,
            "allow_pre_model_deterministic_rescue": True,
        },
        llm_enabled=True,
        hidden_verifier_required=True,
        eligibility_class="model_required",
        local_reflex_risk_level="low",
        local_reflex_bare_sufficiency="high",
    )

    assert policy.supervised_bare_first_allowed is True
    assert policy.baseline_fast_path_preferred is True
    assert policy.pre_model_deterministic_rescue_allowed is False
    assert policy.deterministic_pre_rescue_allowed is True
    assert policy.supervised_bare_first_reason == "policy_explicit"
    assert "model_required_blocks_pre_model_rescue" in policy.reason_codes


def test_route_execution_policy_allows_pre_model_rescue_for_non_model_required_hidden_lite():
    policy = decide_route_execution_policy(
        route_cost_controls={
            "route_lane": "hidden_lite",
            "context_mode": "compact",
            "max_rounds": 1,
            "disable_research": True,
            "lite_route": True,
            "allow_pre_model_deterministic_rescue": True,
        },
        llm_enabled=True,
        hidden_verifier_required=True,
        eligibility_class="standard",
        local_reflex_risk_level="low",
        local_reflex_bare_sufficiency="high",
    )

    assert policy.supervised_bare_first_allowed is True
    assert policy.pre_model_deterministic_rescue_allowed is True
    assert policy.supervised_bare_first_reason == "hidden_lite_ghost_governance"
    assert "model_required_blocks_pre_model_rescue" not in policy.reason_codes


def test_route_execution_policy_allows_cost_capped_protected_pre_model_rescue():
    policy = decide_route_execution_policy(
        route_cost_controls={
            "route_lane": "hidden_lite",
            "context_mode": "compact",
            "max_rounds": 1,
            "disable_research": True,
            "lite_route": True,
            "allow_pre_model_deterministic_rescue": True,
            "expected_capability_protection": ["hyper"],
        },
        llm_enabled=True,
        hidden_verifier_required=True,
        eligibility_class="standard",
        capability_activation_contract="cost_capped",
        local_reflex_risk_level="low",
        local_reflex_bare_sufficiency="high",
    )

    assert policy.pre_model_deterministic_rescue_allowed is True
    assert "cost_capped_capability_allows_verified_pre_model_rescue" in policy.reason_codes
    assert "expected_capability_protection" not in policy.reason_codes


def test_route_execution_policy_blocks_required_protected_pre_model_rescue():
    policy = decide_route_execution_policy(
        route_cost_controls={
            "route_lane": "hidden_lite",
            "context_mode": "compact",
            "max_rounds": 1,
            "disable_research": True,
            "lite_route": True,
            "allow_pre_model_deterministic_rescue": True,
            "expected_capability_protection": ["hyper"],
        },
        llm_enabled=True,
        hidden_verifier_required=True,
        eligibility_class="standard",
        capability_activation_contract="required",
        local_reflex_risk_level="low",
        local_reflex_bare_sufficiency="high",
    )

    assert policy.pre_model_deterministic_rescue_allowed is False
    assert "expected_capability_protection" in policy.reason_codes
    assert "pre_model_rescue_configured_but_blocked" in policy.reason_codes


def test_route_execution_policy_records_lane_default_pre_model_rescue_for_hidden_bugfix():
    policy = decide_route_execution_policy(
        route_cost_controls={
            "route_lane": "hidden_bugfix_supervised",
            "context_mode": "compact",
            "max_rounds": 1,
            "disable_research": True,
            "allow_pre_model_deterministic_rescue": True,
            "preflight_receipt_lite": True,
        },
        llm_enabled=True,
        hidden_verifier_required=True,
        eligibility_class="standard",
        local_reflex_risk_level="low",
        local_reflex_bare_sufficiency="high",
    )
    assert policy.pre_model_deterministic_rescue_allowed is True
    assert "lane_default_pre_model_rescue" in policy.reason_codes


def test_route_execution_policy_records_lane_default_skip_baseline_for_governance_hardened():
    policy = decide_route_execution_policy(
        route_cost_controls={
            "route_lane": "governance_hardened",
            "context_mode": "compact",
            "max_rounds": 1,
            "disable_research": True,
            "skip_llm_baseline": True,
        },
        llm_enabled=True,
        hidden_verifier_required=True,
        eligibility_class="standard",
        local_reflex_risk_level="low",
        local_reflex_bare_sufficiency="high",
    )
    assert "lane_default_skip_baseline" in policy.reason_codes


def test_route_execution_policy_records_lane_default_supervised_bare_first_for_context_sync():
    policy = decide_route_execution_policy(
        route_cost_controls={
            "route_lane": "context_sync_capped",
            "context_mode": "compact",
            "max_rounds": 1,
            "disable_research": True,
            "supervised_bare_first": True,
        },
        llm_enabled=True,
        hidden_verifier_required=True,
        eligibility_class="standard",
        local_reflex_risk_level="low",
        local_reflex_bare_sufficiency="high",
    )
    assert policy.supervised_bare_first_allowed is True
    assert "lane_default_supervised_bare_first" in policy.reason_codes


def test_route_execution_policy_no_lane_default_codes_for_unrelated_lane():
    policy = decide_route_execution_policy(
        route_cost_controls={
            "route_lane": "hidden_lite",
            "context_mode": "compact",
            "max_rounds": 1,
            "disable_research": True,
            "lite_route": True,
        },
        llm_enabled=True,
        hidden_verifier_required=True,
        eligibility_class="standard",
        local_reflex_risk_level="low",
        local_reflex_bare_sufficiency="high",
    )
    lane_default_codes = [c for c in policy.reason_codes if c.startswith("lane_default_")]
    assert lane_default_codes == [], f"Unexpected lane_default codes: {lane_default_codes}"


@pytest.mark.parametrize(
    "route_lane",
    [
        "context_sync_capped",
        "feature_reflex",
        "governance_hardened",
        "governance_hardened_capped",
    ],
)
def test_deterministic_contract_lanes_allow_explicit_pre_model_rescue(route_lane: str):
    controls = {
        "route_lane": route_lane,
        "context_mode": "compact",
        "max_rounds": 1,
        "disable_research": True,
        "allow_pre_model_deterministic_rescue": True,
    }

    assert capability_ab_runner._route_cost_controls_allow_pre_model_deterministic_rescue(controls) is True

    controls["expected_capability_protection"] = ["hyper"]
    assert capability_ab_runner._route_cost_controls_allow_pre_model_deterministic_rescue(controls) is False


def test_no_model_local_fast_path_counts_zero_provider_cost_as_measured():
    assert capability_ab_runner._row_has_measured_provider_tokens(
        {
            "model_calls": 0,
            "total_tokens": 0,
            "token_capture_status": "not_applicable_local_only",
            "model_token_capture_status": "not_applicable_no_model",
        }
    )


def test_extract_record_marks_no_model_local_fast_path_token_measured():
    task = CapabilityTask(
        id="local-fast-path",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Local verified fast path",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
    )
    row = _extract_record(
        mode="with_nexus",
        task=task,
        payload={
            "status": "SUCCESS",
            "semantic_status": "VERIFIED",
            "runtime_classification": "verified_pass",
            "result": {
                "elapsed_sec": 1.0,
                "report": {
                    "model_calls": 0,
                    "total_tokens": 0,
                    "token_capture_status": "not_applicable_local_only",
                },
            },
        },
        wall_time_sec=1.0,
    )

    assert row["token_measured"] is True
    assert row["provider_token_measured"] is True


def test_wall_ledger_conserves_no_model_nexus_phase_work():
    row = {
        "mode": "with_nexus",
        "model_calls": 0,
        "wall_duration_sec": 10.0,
        "phase_wall_total_sec": 9.8,
        "hidden_verifier_wall_sec": 0.1,
        "hidden_verifier_passed": True,
    }

    ledger = evaluate_wall_ledger_conservation(row)

    assert ledger["status"] == "PASS"
    assert ledger["wall_ledger_conserved"] is True
    assert ledger["wall_ledger_components"]["nexus_phase"] == 9.8


def test_wall_ledger_conserves_no_model_nexus_cli_uninstrumented_work():
    row = {
        "mode": "with_nexus",
        "model_calls": 0,
        "wall_duration_sec": 38.4316,
        "phase_wall_total_sec": 35.8169,
        "hidden_verifier_wall_sec": 0.3343,
        "cli_uninstrumented_sec": 1.9231,
        "hidden_verifier_passed": True,
    }

    ledger = evaluate_wall_ledger_conservation(row)

    assert ledger["status"] == "PASS"
    assert ledger["wall_ledger_conserved"] is True
    assert ledger["wall_ledger_components"]["cli_uninstrumented"] == 1.9231


def test_wall_ledger_counts_cli_uninstrumented_as_residual_after_deterministic_rescue():
    row = {
        "mode": "with_nexus",
        "model_calls": 0,
        "wall_duration_sec": 0.7524,
        "phase_wall_total_sec": 0.0,
        "hidden_verifier_wall_sec": 0.3221,
        "deterministic_pre_rescue_wall_sec": 0.4301,
        "cli_uninstrumented_sec": 0.7524,
        "hidden_verifier_passed": True,
    }

    ledger = evaluate_wall_ledger_conservation(row)

    assert ledger["status"] == "PASS"
    assert ledger["wall_ledger_conserved"] is True
    assert ledger["wall_ledger_components"]["cli_uninstrumented"] == pytest.approx(0.0002)
    assert (
        ledger["wall_ledger_component_telemetry_status"]["cli_uninstrumented"]
        == "RESIDUAL_AFTER_LOCAL_COMPONENTS"
    )


def test_wall_ledger_conserves_no_model_nexus_runner_overhead_residual():
    row = {
        "mode": "with_nexus",
        "model_calls": 0,
        "wall_duration_sec": 10.6062,
        "phase_wall_total_sec": 7.0392,
        "hidden_verifier_wall_sec": 0.4262,
        "cli_uninstrumented_sec": 2.6084,
        "model_attempt_runner_overhead_sec": 0.9586,
        "hidden_verifier_passed": True,
    }

    ledger = evaluate_wall_ledger_conservation(row)

    assert ledger["status"] == "PASS"
    assert ledger["wall_ledger_conserved"] is True
    assert ledger["wall_ledger_components"]["runner_overhead_non_verifier"] == 0.5324


def test_wall_ledger_model_gateway_fallback_includes_hidden_verifier_wall():
    row = {
        "mode": "with_nexus",
        "model_calls": 1,
        "wall_duration_sec": 31.2429,
        "gateway_total_sec": 0.0,
        "gateway_process_sec": 0.0,
        "gateway_provider_wait_sec": 0.0,
        "hidden_verifier_wall_sec": 0.3127,
        "hidden_verifier_passed": True,
    }

    ledger = evaluate_wall_ledger_conservation(row)

    assert ledger["status"] == "PASS"
    assert ledger["wall_ledger_conserved"] is True
    assert ledger["wall_ledger_components"]["model_gateway"] == 31.2429
    assert ledger["wall_ledger_component_telemetry_status"]["hidden_verifier"] == "INCLUDED_IN_MODEL_GATEWAY_FALLBACK_TOTAL"


def test_wall_ledger_includes_direct_verifier_wall_for_model_attempt():
    row = {
        "mode": "without_nexus",
        "model_calls": 1,
        "wall_duration_sec": 7.206,
        "gateway_total_sec": 6.7831,
        "direct_verifier_wall_sec": 0.4229,
    }

    ledger = evaluate_wall_ledger_conservation(row)

    assert ledger["status"] == "PASS"
    assert ledger["wall_ledger_conserved"] is True
    assert ledger["wall_ledger_components"]["direct_verifier"] == 0.4229


def test_wall_ledger_includes_direct_infra_retry_wall_for_model_attempt():
    row = {
        "mode": "with_nexus",
        "model_calls": 1,
        "wall_duration_sec": 14.3018,
        "gateway_total_sec": 12.5125,
        "direct_verifier_wall_sec": 0.4221,
        "direct_infra_retry_wall_sec": 1.3672,
    }

    ledger = evaluate_wall_ledger_conservation(row)

    assert ledger["status"] == "PASS"
    assert ledger["wall_ledger_conserved"] is True
    assert ledger["wall_ledger_components"]["direct_infra_retry"] == 1.3672


def test_load_tasks_parses_capability_schema(tmp_path: Path):
    payload = {
        "tasks": [
            {
                "id": "hard-001",
                "difficulty": "hard",
                "task_type": "bug",
                "task_desc": "Fix race",
                "target_file": "a.py",
                "test_file": "tests/test_a.py",
                "success_criteria": "all_target_tests_pass",
            }
        ]
    }
    src = tmp_path / "tasks.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    tasks = load_tasks(src)
    assert len(tasks) == 1
    assert tasks[0].id == "hard-001"
    assert tasks[0].difficulty == "hard"
    assert len(tasks[0].manifest_hash) == 64


def test_direct_gemini_stats_outlier_keeps_provider_fail_closed_with_normalized_ledger():
    payload = {
        "tokens_used": 300_000,
        "token_capture_status": "measured",
        "gateway_token_source": "stats",
    }

    out = _apply_direct_gemini_stats_outlier_policy(
        payload,
        prompt_chars=100,
        output_text="short answer",
    )

    assert out["token_capture_status"] == "estimated"
    assert out["gateway_token_source"] == "estimated_from_stats_outlier"
    assert out["gateway_token_outlier_reason"] == "stats_outlier_possible_cumulative"
    assert out["raw_provider_total_tokens"] == 300_000
    assert out["token_ledger_status"] == "normalized_from_cumulative_stats"
    assert out["token_ledger_source"] == "prompt_output_char_estimate"
    assert out["token_ledger_normalized_tokens"] > 0


def test_hidden_verifier_infra_error_is_not_trust_mismatch():
    row = {
        "status": "FAILED",
        "semantic_status": "UNVERIFIED",
        "hidden_verifier_passed": False,
        "hidden_verifier_stderr_tail": "error: failed to open file `/Users/example/.cache/uv/sdists-v9/.git`: Operation not permitted",
        "report_trust_mismatch": False,
    }

    assert _hidden_verifier_infra_reason(row) == "hidden_verifier_infra_error"
    annotated = _annotate_benchmark_eligibility(row, provider="local", model_required=False, nexus_required=False)

    assert annotated["run_eligible"] is False
    assert annotated["infra_invalid_reason"] == "hidden_verifier_infra_error"
    assert annotated["report_trust_mismatch"] is False


def test_hidden_retry_classifier_selects_minimal_full_and_infra_lanes():
    infra = _classify_hidden_retry_failure("Operation not permitted while reading .cache/uv")
    assert infra.classifier == "infra_failure"
    assert infra.lane == "skipped_infra"
    assert infra.retry is False

    narrow = _classify_hidden_retry_failure("E       assert compute_backoff(3) == 4")
    assert narrow.classifier == "narrow_assertion_failure"
    assert narrow.lane == "minimal_patch"
    assert narrow.retry is True

    broad = _classify_hidden_retry_failure("hidden failed: delete_file must be blocked by policy")
    assert broad.classifier == "broad_contract_failure"
    assert broad.lane == "full_hyper"
    assert broad.retry is True

    # AssertionError containing 'timeout' variable names should NOT be classified as infra_failure
    timeout_var = _classify_hidden_retry_failure(
        "E       AssertionError: assert {'timeout': None} == {'timeout': 10}"
    )
    assert timeout_var.classifier == "narrow_assertion_failure"
    assert timeout_var.lane == "minimal_patch"
    assert timeout_var.retry is True

    compact = _hidden_retry_decision_for_failure(
        "hidden failed: missing phase reason",
        {"context_mode": "compact", "candidate_cap": 1, "max_rounds": 1},
    )
    assert compact.classifier == "narrow_assertion_failure"
    assert compact.lane == "minimal_patch"

    ambiguous_compact = _hidden_retry_decision_for_failure("hidden failed: output mismatch", {"context_mode": "compact"})
    assert ambiguous_compact.classifier == "compact_hidden_verifier_failure"
    assert ambiguous_compact.lane == "minimal_patch"


def test_failure_classifier_rules_individually():
    from scripts.bench.capability_ab_runner import (
        FailureClassifierRule,
        CodeExceptionRule,
        SystemInfraRule,
        SecurityGovernanceRule,
        FallbackRule,
    )

    # 1. 測試 CodeExceptionRule 獨立匹配
    code_rule = CodeExceptionRule()
    assert code_rule.match("assertionerror") is not None
    assert code_rule.match("e       assert dict == dict") is not None
    assert code_rule.match("assertionerror with timeout variable") is not None
    assert code_rule.match("clean run, no exceptions") is None

    # 2. 測試 SystemInfraRule 獨立匹配
    infra_rule = SystemInfraRule()
    assert infra_rule.match("operation not permitted") is not None
    assert infra_rule.match("timed out") is not None
    assert infra_rule.match("assertionerror") is None

    # 3. 測試 SecurityGovernanceRule 獨立匹配
    gov_rule = SecurityGovernanceRule()
    assert gov_rule.match("delete_file must be blocked by policy") is not None
    assert gov_rule.match("trust mismatch") is not None
    assert gov_rule.match("assertionerror") is None

    # 4. 測試 FallbackRule 預設匹配
    fallback = FallbackRule()
    assert fallback.match("any random error") is not None
    assert fallback.match("any random error").classifier == "unclassified_hidden_verifier_failure"



def test_pytest_verifier_cmd_uses_current_python():
    cmd = _pytest_verifier_cmd("tests/test_demo.py")

    assert cmd[:3] == [sys.executable, "-m", "pytest"]
    assert "uv" not in cmd
    assert cmd[-1] == "tests/test_demo.py"


def test_load_tasks_parses_public_manifest_metadata(tmp_path: Path):
    payload = {
        "tasks": [
            {
                "id": "pub-001",
                "category": "bugfix",
                "difficulty": "hard",
                "repo_kind": "neutral_fixture",
                "repo": "fixture://demo",
                "repo_ref": "v1",
                "task_desc": "Fix public task",
                "fixture_kind": "python_demo",
                "success_criteria": "patch_and_tests_pass",
                "expected_capabilities": ["codeintel", "hyper"],
                "capability_activation_contract": "required",
                "hidden_oracle_kind": "pytest_hidden",
                "eligibility_class": "model_required",
                "cost_budget": {"max_wall_sec": 600, "max_model_calls": 2},
                "token_budget": 50000,
                "wall_time_budget_sec": 600,
                "public_claim_allowed_metrics": ["verified_delivery_rate"],
            }
        ]
    }
    src = tmp_path / "public.json"
    src.write_text(json.dumps(payload), encoding="utf-8")
    tasks = load_tasks(src)
    assert tasks[0].task_type == "public_bugfix"
    assert tasks[0].target_file == "python_demo"
    assert tasks[0].category == "bugfix"
    assert tasks[0].repo_kind == "neutral_fixture"
    assert tasks[0].repo == "fixture://demo"
    assert tasks[0].repo_ref == "v1"
    assert tasks[0].expected_capabilities == ("codeintel", "hyper")
    assert tasks[0].capability_activation_contract == "required"
    assert tasks[0].hidden_oracle_kind == "pytest_hidden"
    assert tasks[0].eligibility_class == "model_required"
    assert tasks[0].cost_budget == {"max_wall_sec": 600, "max_model_calls": 2}
    assert tasks[0].token_budget == 50000
    assert tasks[0].wall_time_budget_sec == 600.0
    assert tasks[0].public_claim_allowed_metrics == ("verified_delivery_rate",)


def test_expand_task_trials_preserves_public_manifest_metadata():
    task = CapabilityTask(
        id="pub-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix public task",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
        expected_capabilities=("codeintel", "hyper"),
        capability_activation_contract="required",
        hidden_oracle_kind="pytest_hidden",
        eligibility_class="model_required",
        cost_budget={"max_model_calls": 2},
        token_budget=50000,
        wall_time_budget_sec=600.0,
        public_claim_allowed_metrics=("verified_delivery_rate",),
    )

    expanded = expand_task_trials([task], repeat_trials=2, shuffle_seed=None)

    assert [item.trial_index for item in expanded] == [1, 2]
    assert all(item.eligibility_class == "model_required" for item in expanded)
    assert all(item.cost_budget == {"max_model_calls": 2} for item in expanded)
    assert all(item.public_claim_allowed_metrics == ("verified_delivery_rate",) for item in expanded)


def test_expected_capability_coverage_reports_static_gaps():
    tasks = [
        CapabilityTask(
            id="a",
            difficulty="hard",
            task_type="bug",
            task_desc="a",
            target_file="a",
            test_file="a",
            success_criteria="patch_and_tests_pass",
            expected_capabilities=("codeintel", "hyper"),
            capability_activation_contract="required",
        ),
        CapabilityTask(
            id="b",
            difficulty="hard",
            task_type="bug",
            task_desc="b",
            target_file="b",
            test_file="b",
            success_criteria="patch_and_tests_pass",
        ),
    ]

    out = _expected_capability_coverage(tasks)

    assert out["declared"] == ["codeintel", "hyper"]
    assert "swarm" in out["missing_core"]
    assert out["tasks_missing_expected"] == ["b"]
    assert out["required_or_cost_capped"] == ["codeintel", "hyper"]


def test_expand_task_trials_repeats_and_shuffles_deterministically():
    tasks = [
        CapabilityTask(id="a", difficulty="hard", task_type="bug", task_desc="a", target_file="a", test_file="a", success_criteria="x"),
        CapabilityTask(id="b", difficulty="hard", task_type="bug", task_desc="b", target_file="b", test_file="b", success_criteria="x"),
    ]
    expanded = expand_task_trials(tasks, repeat_trials=2, shuffle_seed=7)
    assert sorted((task.id, task.trial_index) for task in expanded) == [("a", 1), ("a", 2), ("b", 1), ("b", 2)]
    assert [task.id for task in expanded] == [task.id for task in expand_task_trials(tasks, repeat_trials=2, shuffle_seed=7)]


def test_report_model_label_uses_configured_gemini_model(monkeypatch):
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    assert _report_model_label() == "gemini-3-flash-preview"


def test_benchmark_gateway_timeout_has_short_default_and_override(monkeypatch):
    monkeypatch.delenv("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("NEXUS_GEMINI_MODEL_NAME", raising=False)
    monkeypatch.delenv("NEXUS_DIRECT_GEMINI_MODEL", raising=False)
    assert _benchmark_gateway_timeout_sec() == "30"
    monkeypatch.setenv("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC", "12")
    assert _benchmark_gateway_timeout_sec() == "12"
    monkeypatch.setenv("NEXUS_BENCH_GATEWAY_TIMEOUT_SEC", "bad")
    assert _benchmark_gateway_timeout_sec() == "30"


def test_benchmark_gateway_timeout_scales_with_task_budget():
    os.environ.pop("NEXUS_GEMINI_MODEL_NAME", None)
    os.environ.pop("NEXUS_DIRECT_GEMINI_MODEL", None)
    assert _benchmark_gateway_timeout_for_task(10) == 30
    assert _benchmark_gateway_timeout_for_task(120) == 90
    assert _benchmark_gateway_timeout_for_task(180) == 150
    assert _benchmark_gateway_timeout_for_task(300) == 220


def test_flash_benchmark_gateway_timeout_is_capped_unless_long_gateway(monkeypatch):
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.delenv("NEXUS_BENCH_LONG_GATEWAY", raising=False)
    assert _benchmark_gateway_timeout_for_task(420) == 120
    monkeypatch.setenv("NEXUS_BENCH_LONG_GATEWAY", "1")
    assert _benchmark_gateway_timeout_for_task(420) == 220


def test_model_required_gateway_timeout_escapes_flash_short_cap(monkeypatch):
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    task = CapabilityTask(
        id="model-required-feature-001",
        repo_kind="python",
        task_type="public_feature",
        difficulty="hard",
        task_desc="Implement model-required feature",
        target_file="src/app.py",
        test_file="tests/test_app.py",
        success_criteria="verified by model-owned delivery",
        eligibility_class="model_required",
    )
    assert _benchmark_gateway_timeout_for_execution(task=task, timeout_sec=240, base_timeout_sec=120) == 210
    assert _benchmark_gateway_timeout_for_execution(task=task, timeout_sec=60, base_timeout_sec=30) == 45


def test_non_model_required_gateway_timeout_keeps_base_policy():
    task = CapabilityTask(
        id="hidden-001",
        repo_kind="python",
        task_type="hidden_repair",
        difficulty="medium",
        task_desc="Repair hidden fixture",
        target_file="src/app.py",
        test_file="tests/test_app.py",
        success_criteria="verified",
    )
    assert _benchmark_gateway_timeout_for_execution(task=task, timeout_sec=240, base_timeout_sec=120) == 120
    assert (
        _benchmark_gateway_timeout_for_execution(
            task=task,
            timeout_sec=240,
            base_timeout_sec=120,
            require_model_participation=True,
        )
        == 210
    )


def test_remaining_task_timeout_uses_shared_deadline(monkeypatch):
    monkeypatch.setattr("scripts.bench.capability_ab_runner.time.monotonic", lambda: 100.4)

    assert _remaining_task_timeout(105.9, 300) == 5


def test_remaining_task_timeout_raises_when_deadline_is_spent(monkeypatch):
    monkeypatch.setattr("scripts.bench.capability_ab_runner.time.monotonic", lambda: 106.0)

    try:
        _remaining_task_timeout(105.9, 300)
    except subprocess.TimeoutExpired as exc:
        assert exc.timeout == 300
    else:
        raise AssertionError("expected timeout")


def test_public_benchmark_preflight_passes_without_model_invocation(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "tasks.json"
    disclosure_manifest = tmp_path / "tasks.public.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "preflight-demo",
                "description": "demo",
                "tasks": [
                    {
                        "id": "task-1",
                        "category": "bugfix",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://demo",
                        "repo_ref": "v1",
                        "task_desc": "Fix the hidden bug.",
                        "success_criteria": "patch_and_tests_pass",
                        "mutation_required": True,
                        "allowed_files": ["target.py"],
                        "forbidden_files": [],
                        "setup_command": "",
                        "verification_command": "pytest",
                        "fixture_kind": "rlm_harder_v2_hidden_governance",
                        "rlm_challenge": "hidden_governance",
                        "commercial_lane": "capability_lift",
                        "expected_capabilities": ["codeintel", "hyper", "autoreason"],
                        "capability_activation_contract": "required",
                        "hidden_oracle_kind": "pytest_hidden",
                        "cost_budget": {
                            "max_wall_sec": 600,
                            "max_model_calls": 3,
                            "max_tokens": 60000,
                            "max_capability_stack_size": 6,
                        },
                        "public_claim_allowed_metrics": ["verified_delivery_rate"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    disclosure_manifest.write_text(
        json.dumps(
            {
                "schema": "nexus_public_benchmark_sanitized_manifest_v1",
                "tasks": [
                    {
                        "id": "task-1",
                        "repo": "fixture://sanitized",
                        "task_desc": "Fix the hidden bug.",
                        "expected_capabilities": ["codeintel", "hyper", "autoreason"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.setenv("NEXUS_DIRECT_GEMINI_MODEL", "gemini-3-flash-preview")
    args = argparse.Namespace(
        tasks_file=str(manifest),
        public_disclosure_manifest=str(disclosure_manifest),
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=1,
        repeat_trials=2,
        shuffle_seed=7,
        without_mode="gemini",
        with_llm_mode="all",
        timeout_sec=300,
        total_timeout_sec=1800,
        stop_loss_sec=1800,
        per_task_stop_loss_sec=600,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="auto",
        with_nexus_runner="subprocess",
        with_model_provider="gemini",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
        nexus_only=False,
        force_learn_slo_ready=False,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "PASS"
    coverage = report["task_manifest"]["expected_capability_coverage"]
    assert coverage["declared"] == ["autoreason", "codeintel", "hyper"]
    assert "swarm" in coverage["missing_core"]
    assert report["capability_readiness"]["status"] == "PASS"
    assert report["model_lock"]["same_model"] is True
    assert report["task_manifest"]["selected_n"] == 1
    assert report["task_manifest"]["expanded_n"] == 2
    assert report["public_claim_requirements"]["hidden_verifier_mode"] is True
    assert report["public_disclosure_manifest"]["status"] == "PASS"
    assert report["public_disclosure_manifest"]["sha256"]
    assert report["preflight_sentinel"]["status"] == "PASS"
    assert report["preflight_sentinel"]["controller_policy"]["branch"] == "continue"
    assert report["preflight_sentinel"]["checks"]["warning_ledger_required"] is True
    assert report["preflight_sentinel"]["checks"]["wall_ledger_required"] is True
    assert report["preflight_sentinel"]["checks"]["rubric_stage_fields_required"] == [
        "failed_stage",
        "failed_rubric_keys",
    ]
    assert report["preflight_sentinel"]["checks"]["dci_raw_warning_pointer_required"] is True
    assert "any_stratum_warning_clean_false" in report["preflight_sentinel"]["controller_policy"]["stop_conditions"]
    assert report["preflight_sentinel"]["ach_canary_mutations"]["status"] == "PASS"


def test_public_benchmark_preflight_requires_export_policy_for_session_worker(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "tasks.json"
    disclosure_manifest = tmp_path / "tasks.public.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "preflight-demo",
                "description": "demo",
                "tasks": [
                    {
                        "id": "task-1",
                        "category": "bugfix",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://demo",
                        "repo_ref": "v1",
                        "task_desc": "Fix the hidden bug.",
                        "success_criteria": "patch_and_tests_pass",
                        "expected_capabilities": ["codeintel", "hyper", "autoreason"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    disclosure_manifest.write_text(
        json.dumps(
            {
                "schema": "nexus_public_benchmark_sanitized_manifest_v1",
                "tasks": [{"id": "task-1", "repo": "fixture://sanitized", "task_desc": "Fix the hidden bug."}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.setenv("NEXUS_DIRECT_GEMINI_MODEL", "gemini-3-flash-preview")
    args = argparse.Namespace(
        tasks_file=str(manifest),
        public_disclosure_manifest=str(disclosure_manifest),
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=1,
        repeat_trials=1,
        shuffle_seed=None,
        without_mode="gemini",
        with_llm_mode="hard",
        timeout_sec=300,
        total_timeout_sec=1800,
        stop_loss_sec=1800,
        per_task_stop_loss_sec=600,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="auto",
        with_nexus_runner="subprocess",
        with_model_provider="gemini",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
        nexus_only=False,
        force_learn_slo_ready=False,
        session_worker=True,
        external_model_export_policy="unspecified",
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "FAIL"
    assert "external_model_export_policy_required_for_session_worker" in report["failures"]
    assert report["public_claim_requirements"]["public_claim_allowed"] is False
    assert report["external_model_export"]["requires_policy"] is True

    args.external_model_export_policy = "sanitized"
    approved = build_public_benchmark_preflight(args, repo_root=tmp_path)
    assert "external_model_export_policy_required_for_session_worker" not in approved["failures"]
    assert approved["external_model_export"]["live_export_allowed"] is True


def test_public_benchmark_preflight_marks_force_ready_non_public(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "tasks.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "preflight-force-ready-demo",
                "description": "demo",
                "tasks": [
                    {
                        "id": "task-1",
                        "category": "bugfix",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://demo",
                        "repo_ref": "v1",
                        "task_desc": "Fix a governance bug.",
                        "success_criteria": "patch_and_tests_pass",
                        "mutation_required": True,
                        "allowed_files": ["target.py"],
                        "forbidden_files": [],
                        "setup_command": "",
                        "verification_command": "pytest",
                        "fixture_kind": "rlm_harder_v2_hidden_governance",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.setenv("NEXUS_DIRECT_GEMINI_MODEL", "gemini-3-flash-preview")
    args = argparse.Namespace(
        tasks_file=str(manifest),
        public_disclosure_manifest="",
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=1,
        repeat_trials=1,
        shuffle_seed=None,
        without_mode="gemini",
        with_llm_mode="all",
        with_model_provider="gemini",
        with_nexus_runner="subprocess",
        timeout_sec=300,
        total_timeout_sec=1800,
        stop_loss_sec=1800,
        per_task_stop_loss_sec=600,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="auto",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
        nexus_only=False,
        force_learn_slo_ready=True,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["public_claim_requirements"]["force_learn_slo_ready"] is True
    assert report["public_claim_requirements"]["public_claim_allowed"] is False


def test_public_benchmark_preflight_sentinel_blocks_incomplete_docs_strata(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "docs_tasks.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "nexus-public-docs-lane-v1",
                "description": "demo",
                "tasks": [
                    {
                        "id": "docs-1",
                        "category": "docs_code_sync",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://docs",
                        "repo_ref": "v1",
                        "task_desc": "Sync docs.",
                        "success_criteria": "patch_and_tests_pass",
                        "mutation_required": True,
                        "allowed_files": ["target.py"],
                        "forbidden_files": [],
                        "setup_command": "",
                        "verification_command": "pytest",
                        "fixture_kind": "rlm_harder_v2_hidden_governance",
                        "stratum_type": "pure_docs",
                        "expected_capabilities": ["codeintel", "memory", "delivery_gate"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.setenv("NEXUS_DIRECT_GEMINI_MODEL", "gemini-3-flash-preview")
    args = argparse.Namespace(
        tasks_file=str(manifest),
        public_disclosure_manifest="",
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=3,
        repeat_trials=1,
        shuffle_seed=None,
        without_mode="gemini",
        with_llm_mode="all",
        timeout_sec=300,
        total_timeout_sec=1800,
        stop_loss_sec=1800,
        per_task_stop_loss_sec=600,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="auto",
        with_nexus_runner="subprocess",
        with_model_provider="gemini",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
        nexus_only=False,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "FAIL"
    assert report["preflight_sentinel"]["status"] == "FAIL"
    assert report["preflight_sentinel"]["controller_policy"]["branch"] == "stop"
    assert "preflight_sentinel:sentinel_docs_strata_missing:docs_code_sync,evidence_required_docs" in report["failures"]


def test_public_benchmark_preflight_rejects_unsanitized_disclosure_manifest(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "tasks.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "preflight-demo",
                "description": "demo",
                "tasks": [
                    {
                        "id": "task-1",
                        "category": "bugfix",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://demo",
                        "repo_ref": "v1",
                        "task_desc": "Fix the hidden bug.",
                        "success_criteria": "patch_and_tests_pass",
                        "mutation_required": True,
                        "allowed_files": ["target.py"],
                        "forbidden_files": [],
                        "setup_command": "",
                        "verification_command": "pytest",
                        "fixture_kind": "rlm_harder_v2_hidden_governance",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    disclosure_manifest = tmp_path / "tasks.public.json"
    disclosure_manifest.write_text(
        json.dumps(
            {
                "schema": "nexus_public_benchmark_sanitized_manifest_v1",
                "tasks": [
                    {
                        "id": "task-1",
                        "repo": "/Users/example/private/repo",
                        "allowed_files": ["target.py"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.setenv("NEXUS_DIRECT_GEMINI_MODEL", "gemini-3-flash-preview")
    args = argparse.Namespace(
        tasks_file=str(manifest),
        public_disclosure_manifest=str(disclosure_manifest),
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=1,
        repeat_trials=1,
        shuffle_seed=None,
        without_mode="gemini",
        with_llm_mode="all",
        timeout_sec=300,
        total_timeout_sec=1800,
        stop_loss_sec=1800,
        per_task_stop_loss_sec=600,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="auto",
        with_nexus_runner="subprocess",
        with_model_provider="gemini",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
        nexus_only=False,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "FAIL"
    assert report["public_disclosure_manifest"]["status"] == "FAIL"
    assert "public_disclosure:disclosure_task_1_contains_file_scope" in report["failures"]
    assert "public_disclosure:disclosure_task_1_repo_not_sanitized" in report["failures"]


def test_public_benchmark_preflight_accepts_codex_model_lock(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "tasks.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "preflight-codex-demo",
                "description": "demo",
                "tasks": [
                    {
                        "id": "task-1",
                        "category": "bugfix",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://demo",
                        "repo_ref": "v1",
                        "task_desc": "Fix the hidden bug.",
                        "success_criteria": "patch_and_tests_pass",
                        "mutation_required": True,
                        "allowed_files": ["target.py"],
                        "forbidden_files": [],
                        "setup_command": "",
                        "verification_command": "pytest",
                        "fixture_kind": "rlm_harder_v2_hidden_governance",
                        "commercial_lane": "capability_lift",
                        "source_manifest": "scripts/bench/public_benchmark_commercial_lanes_v1.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.delenv("NEXUS_GEMINI_MODEL_NAME", raising=False)
    monkeypatch.delenv("NEXUS_DIRECT_GEMINI_MODEL", raising=False)
    monkeypatch.setenv("NEXUS_CODEX_MODEL_NAME", "gpt-5.5")
    monkeypatch.setenv("NEXUS_DIRECT_CODEX_MODEL", "gpt-5.5")
    args = argparse.Namespace(
        tasks_file=str(manifest),
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=1,
        repeat_trials=1,
        shuffle_seed=None,
        without_mode="codex",
        with_llm_mode="all",
        timeout_sec=300,
        total_timeout_sec=1800,
        stop_loss_sec=1800,
        per_task_stop_loss_sec=600,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="auto",
        with_nexus_runner="subprocess",
        with_model_provider="codex",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
        nexus_only=False,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "PASS"
    assert report["model_lock"]["same_model"] is True
    assert "direct_codex_provider_is_prompt_wearing_only_for_external_model_claims" in str(report["capability_readiness"]["warnings"])


def test_public_benchmark_preflight_fails_for_unlocked_model_and_no_hidden_verifier(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "tasks.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "preflight-demo",
                "description": "demo",
                "tasks": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("NEXUS_VALUE_HIDDEN_VERIFIER", raising=False)
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.setenv("NEXUS_DIRECT_GEMINI_MODEL", "gemini-3.1-pro-preview")
    args = argparse.Namespace(
        tasks_file=str(manifest),
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=1,
        repeat_trials=1,
        shuffle_seed=None,
        without_mode="gemini",
        with_llm_mode="all",
        timeout_sec=300,
        total_timeout_sec=0,
        stop_loss_sec=0,
        per_task_stop_loss_sec=900,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="",
        with_nexus_runner="inprocess",
        with_model_provider="gemini",
        enable_autoreason_executor=False,
        enable_ddtree_executor=False,
        enable_ultra_review_dry_gate=False,
        llm_candidate_cap=1,
        nexus_only=False,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "FAIL"
    assert "model_lock_mismatch" in report["failures"]
    assert "hidden_verifier_disabled" in report["failures"]
    assert "per_task_stop_loss_above_600" in report["failures"]
    assert "manifest_tasks_empty" in report["failures"]
    assert "capability_readiness:autoreason_executor_flag_missing" in report["failures"]
    assert "capability_readiness:ddtree_executor_flag_missing" in report["failures"]
    assert "capability_readiness:ultra_review_dry_gate_flag_missing" in report["failures"]


def test_public_benchmark_preflight_blocks_model_run_without_executor_evidence_flags(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "tasks.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "preflight-readiness-demo",
                "description": "demo",
                "tasks": [
                    {
                        "id": "task-1",
                        "category": "bugfix",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://demo",
                        "repo_ref": "v1",
                        "task_desc": "Fix a governance bug.",
                        "success_criteria": "patch_and_tests_pass",
                        "mutation_required": True,
                        "allowed_files": ["target.py"],
                        "forbidden_files": [],
                        "setup_command": "",
                        "verification_command": "pytest",
                        "fixture_kind": "rlm_harder_v2_hidden_governance",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.setenv("NEXUS_DIRECT_GEMINI_MODEL", "gemini-3-flash-preview")
    args = argparse.Namespace(
        tasks_file=str(manifest),
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=1,
        repeat_trials=1,
        shuffle_seed=None,
        without_mode="gemini",
        with_llm_mode="all",
        with_model_provider="gemini",
        with_nexus_runner="subprocess",
        timeout_sec=300,
        total_timeout_sec=1800,
        stop_loss_sec=1800,
        per_task_stop_loss_sec=600,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="auto",
        enable_autoreason_executor=False,
        enable_ddtree_executor=False,
        enable_ultra_review_dry_gate=False,
        llm_candidate_cap=1,
        nexus_only=False,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "FAIL"
    assert report["capability_readiness"]["status"] == "FAIL"
    assert "capability_readiness:autoreason_executor_flag_missing" in report["failures"]
    assert "capability_readiness:llm_candidate_cap_below_ddtree_threshold" in report["failures"]


def test_public_benchmark_preflight_blocks_route_oracle_candidate_count_regression(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "route_oracles.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "route-oracle-regression",
                "description": "demo",
                "tasks": [
                    {
                        "id": "route-oracle-autoreason-001",
                        "category": "route_oracle",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://route-oracle",
                        "repo_ref": "v1",
                        "task_desc": "Route oracle requiring Autoreason and DDTree tournament evidence.",
                        "task_type": "public_test_repair",
                        "success_criteria": "patch_and_tests_pass",
                        "mutation_required": True,
                        "allowed_files": ["target.py"],
                        "forbidden_files": [],
                        "setup_command": "",
                        "verification_command": "pytest",
                        "fixture_kind": "rlm_harder_v2_autoreason_judge",
                        "expected_capabilities": ["autoreason", "ddtree"],
                        "capability_activation_contract": "required",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.setenv("NEXUS_DIRECT_GEMINI_MODEL", "gemini-3-flash-preview")
    args = argparse.Namespace(
        tasks_file=str(manifest),
        repo_kind_filter="all",
        task_id_filter="route-oracle-autoreason-001",
        difficulty="all",
        max_tasks=1,
        repeat_trials=1,
        shuffle_seed=None,
        without_mode="gemini",
        with_llm_mode="all",
        with_model_provider="gemini",
        with_nexus_runner="subprocess",
        timeout_sec=300,
        total_timeout_sec=1800,
        stop_loss_sec=1800,
        per_task_stop_loss_sec=600,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="auto",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=1,
        nexus_only=False,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "FAIL"
    assert "capability_readiness:llm_candidate_cap_below_ddtree_threshold" in report["failures"]
    assert report["capability_readiness"]["observed_flags"]["llm_candidate_cap"] == 1


def test_public_benchmark_preflight_allows_nexus_only_without_direct_model(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "tasks.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "preflight-nexus-only-demo",
                "description": "demo",
                "tasks": [
                    {
                        "id": "task-1",
                        "category": "bugfix",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://demo",
                        "repo_ref": "v1",
                        "task_desc": "Fix a governance bug.",
                        "success_criteria": "patch_and_tests_pass",
                        "mutation_required": True,
                        "allowed_files": ["target.py"],
                        "forbidden_files": [],
                        "setup_command": "",
                        "verification_command": "pytest",
                        "fixture_kind": "rlm_harder_v2_hidden_governance",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.delenv("NEXUS_DIRECT_GEMINI_MODEL", raising=False)
    args = argparse.Namespace(
        tasks_file=str(manifest),
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=1,
        repeat_trials=1,
        shuffle_seed=None,
        without_mode="gemini",
        with_llm_mode="all",
        with_model_provider="gemini",
        with_nexus_runner="subprocess",
        timeout_sec=300,
        total_timeout_sec=1800,
        stop_loss_sec=1800,
        per_task_stop_loss_sec=600,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="auto",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
        nexus_only=True,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "PASS"
    assert "direct_model_env_missing" not in report["failures"]
    assert report["public_claim_requirements"]["single_arm_run"] is True
    assert report["public_claim_requirements"]["public_claim_allowed"] is False


def test_public_benchmark_preflight_allows_without_only_without_nexus_model(tmp_path: Path, monkeypatch):
    manifest = tmp_path / "tasks.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "preflight-without-only-demo",
                "description": "demo",
                "tasks": [
                    {
                        "id": "task-1",
                        "category": "bugfix",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://demo",
                        "repo_ref": "v1",
                        "task_desc": "Fix a governance bug.",
                        "success_criteria": "patch_and_tests_pass",
                        "mutation_required": True,
                        "allowed_files": ["target.py"],
                        "forbidden_files": [],
                        "setup_command": "",
                        "verification_command": "pytest",
                        "fixture_kind": "rlm_harder_v2_hidden_governance",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.delenv("NEXUS_GEMINI_MODEL_NAME", raising=False)
    monkeypatch.setenv("NEXUS_DIRECT_GEMINI_MODEL", "gemini-3-flash-preview")
    args = argparse.Namespace(
        tasks_file=str(manifest),
        repo_kind_filter="all",
        task_id_filter="all",
        difficulty="all",
        max_tasks=1,
        repeat_trials=1,
        shuffle_seed=None,
        without_mode="gemini",
        with_llm_mode="all",
        with_model_provider="gemini",
        with_nexus_runner="subprocess",
        timeout_sec=300,
        total_timeout_sec=1800,
        stop_loss_sec=1800,
        per_task_stop_loss_sec=600,
        require_clean_worktree=False,
        evidence_bundle=True,
        markdown_report="auto",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
        nexus_only=False,
        without_only=True,
        external_model_export_policy="sanitized",
        session_worker=True,
        outbound_prompt_ledger=str(tmp_path / "ledger.jsonl"),
        force_learn_slo_ready=False,
    )

    report = build_public_benchmark_preflight(args, repo_root=tmp_path)

    assert report["status"] == "PASS"
    assert "nexus_model_env_missing" not in report["failures"]
    assert "direct_model_env_missing" not in report["failures"]
    assert report["public_claim_requirements"]["single_arm_run"] is True
    assert report["public_claim_requirements"]["single_arm_mode"] == "without_nexus"
    assert report["public_claim_requirements"]["public_claim_allowed"] is False


def test_parse_direct_gemini_json_marks_stats_tokens_measured():
    raw = json.dumps(
        {
            "output": json.dumps({"status": "OK", "patch": "x = 1\n"}),
            "stats": {"models": {"gemini-3-flash-preview": {"tokens": {"total": 321}}}},
        }
    )
    payload, _ = _parse_direct_gemini_json(raw)
    assert payload["tokens_used"] == 321
    assert payload["token_capture_status"] == "measured"
    assert payload["gateway_stats_present"] is True
    assert payload["gateway_usage_metadata_present"] is False
    assert payload["gateway_token_source"] == "stats"


def test_direct_gemini_stats_outlier_is_not_measured():
    payload = {
        "tokens_used": 400950,
        "token_capture_status": "measured",
        "gateway_stats_present": True,
        "gateway_usage_metadata_present": False,
        "gateway_token_source": "stats",
    }
    adjusted = _apply_direct_gemini_stats_outlier_policy(payload, prompt_chars=650, output_text="x" * 224)
    assert adjusted["raw_provider_total_tokens"] == 400950
    assert adjusted["tokens_used"] == 218
    assert adjusted["token_capture_status"] == "estimated"
    assert adjusted["gateway_token_source"] == "estimated_from_stats_outlier"
    assert adjusted["gateway_token_outlier_reason"] == "stats_outlier_possible_cumulative"
    assert adjusted["raw_provider_token_source"] == "stats"
    assert adjusted["provider_stats_cumulative_suspected"] is True
    assert adjusted["token_accounting_failure_class"] == "provider_stats_outlier"


def test_parse_direct_gemini_json_reads_usage_metadata_tokens():
    raw = json.dumps(
        {
            "response": json.dumps({"status": "OK", "patch": "x = 1\n"}),
            "usageMetadata": {"totalTokenCount": 456},
        }
    )
    payload, _ = _parse_direct_gemini_json(raw)
    assert payload["tokens_used"] == 456
    assert payload["token_capture_status"] == "measured"
    assert payload["gateway_stats_present"] is False
    assert payload["gateway_usage_metadata_present"] is True
    assert payload["gateway_token_source"] == "usage_metadata"


def test_direct_gemini_parse_failure_preserves_token_telemetry():
    raw = json.dumps(
        {
            "output": "not-json",
            "stats": {"models": {"gemini-3-flash-preview": {"tokens": {"total": 321}}}},
        }
    )

    payload = capability_ab_runner._direct_gemini_parse_failure_payload(
        raw,
        prompt_chars=650,
        model_name="gemini-3-flash-preview",
    )

    assert payload["status"] == "FAIL"
    assert payload["error_category"] == "parse_failure"
    assert payload["tokens_used"] == 321
    assert payload["token_capture_status"] == "measured"
    assert payload["gateway_token_source"] == "stats"


def test_parse_direct_gemini_json_reads_additive_usage_metadata_tokens():
    raw = json.dumps(
        {
            "response": json.dumps({"status": "OK", "patch": "x = 1\n"}),
            "usageMetadata": {"promptTokenCount": 111, "candidatesTokenCount": 22},
        }
    )
    payload, _ = _parse_direct_gemini_json(raw)
    assert payload["tokens_used"] == 133
    assert payload["token_capture_status"] == "measured"
    assert payload["gateway_usage_metadata_present"] is True
    assert payload["gateway_token_source"] == "usage_metadata"


def test_parse_direct_gemini_json_marks_missing_gateway_stats():
    raw = json.dumps({"output": json.dumps({"status": "OK", "patch": "x = 1\n"})})
    payload, _ = _parse_direct_gemini_json(raw)
    assert payload["tokens_used"] == 0
    assert payload["token_capture_status"] == "missing_gateway_stats"
    assert payload["gateway_stats_present"] is False
    assert payload["gateway_usage_metadata_present"] is False
    assert payload["gateway_token_source"] == "missing"


def test_parse_direct_patch_json_accepts_fenced_codex_json():
    payload, output = _parse_direct_patch_json('```json\n{"status":"OK","patch":"x = 1\\n"}\n```')
    assert output.startswith("{")
    assert payload["patch"] == "x = 1\n"
    assert payload["token_capture_status"] == "missing_gateway_stats"


def test_materialize_fixture_writes_files(tmp_path: Path):
    task = CapabilityTask(
        id="easy-001",
        difficulty="easy",
        task_type="bug",
        task_desc="Fix text normalization",
        target_file="na",
        test_file="na",
        success_criteria="all_target_tests_pass",
    )
    target, test = _materialize_fixture(tmp_path, task)
    assert Path(target).exists()
    assert Path(test).exists()
    assert "normalize_flag" in Path(target).read_text(encoding="utf-8")


def test_materialize_nexus_value_fixture_uses_fixture_kind(tmp_path: Path):
    task = CapabilityTask(
        id="nexus-value-trust-001",
        difficulty="easy",
        task_type="public_ops_research",
        task_desc="Fix trust mismatch",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_trust_phase_aggregator",
    )

    target, test = _materialize_fixture(tmp_path, task)

    target_source = Path(target).read_text(encoding="utf-8")
    test_source = Path(test).read_text(encoding="utf-8")
    hidden_test_source = Path(_hidden_test_for_visible_test(test)).read_text(encoding="utf-8")
    assert "overall_status" in target_source
    assert "compute_backoff" not in target_source
    assert "spec_from_file_location" in test_source
    assert "test_overall_status_passes_when_all_phases_pass" in test_source
    assert "missing_evidence" not in test_source
    assert "missing_evidence" in hidden_test_source


def test_materialize_model_required_named_fixtures_write_visible_and_hidden_contracts(tmp_path: Path):
    repair = CapabilityTask(
        id="repair",
        difficulty="hard",
        task_type="public_test_repair",
        task_desc="Repair async timeout tests without hiding the timeout contract.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="pytest_async_repair",
    )
    docs = CapabilityTask(
        id="docs",
        difficulty="hard",
        task_type="public_docs_code_sync",
        task_desc="Sync API examples with renamed response fields and executable tests.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="docs_api_sync",
    )

    repair_target, repair_visible = _materialize_fixture(tmp_path, repair)
    docs_target, docs_visible = _materialize_fixture(tmp_path, docs)

    assert "compute_backoff" in Path(repair_target).read_text(encoding="utf-8")
    assert "compute_backoff(2) == 2" in Path(repair_visible).read_text(encoding="utf-8")
    assert "sys.path.insert" in Path(repair_visible).read_text(encoding="utf-8")
    assert "compute_backoff(3) == 4" in Path(_hidden_test_for_visible_test(repair_visible)).read_text(encoding="utf-8")
    assert "FIELD = 'status'" in Path(docs_target).read_text(encoding="utf-8")
    assert "isinstance(build_response('ok'), dict)" in Path(docs_visible).read_text(encoding="utf-8")
    assert "sys.path.insert" in Path(docs_visible).read_text(encoding="utf-8")
    assert "{'result': 'ok'}" in Path(_hidden_test_for_visible_test(docs_visible)).read_text(encoding="utf-8")
    assert (Path(docs_target).parent / "README.md").exists()


def test_materialize_all_nexus_value_manifest_fixtures_are_distinct(tmp_path: Path):
    tasks = [
        task
        for task in load_tasks("scripts/bench/public_benchmark_nexus_value_v1.json")
        if task.fixture_kind.startswith("nexus_value_")
    ]

    signatures = set()
    for task in tasks:
        target, test = _materialize_fixture(tmp_path, task)
        signatures.add((Path(target).read_text(encoding="utf-8"), Path(test).read_text(encoding="utf-8")))

    assert len(signatures) == len(tasks)


def test_public_candidate_fixtures_have_distinct_visible_and_hidden_tests(tmp_path: Path):
    manifest_paths = [
        "scripts/bench/public_benchmark_nexus_value_v1.json",
        "scripts/bench/public_benchmark_rlm_harder_v2.json",
        "scripts/bench/public_benchmark_route_oracles_v1.json",
    ]
    tasks = [
        task
        for manifest_path in manifest_paths
        for task in load_tasks(manifest_path)
        if task.fixture_kind.startswith(("nexus_value_", "rlm_harder_"))
    ]

    not_split: list[str] = []
    for task in tasks:
        _target, visible_test = _materialize_fixture(tmp_path, task)
        hidden_test = _hidden_test_for_visible_test(visible_test)
        if Path(visible_test).read_text(encoding="utf-8") == Path(hidden_test).read_text(encoding="utf-8"):
            not_split.append(task.fixture_kind)

    assert not not_split


def test_route_oracle_fixtures_have_hidden_capability_conditions(tmp_path: Path):
    tasks = load_tasks("scripts/bench/public_benchmark_route_oracles_v1.json")

    by_fixture: dict[str, str] = {}
    for task in tasks:
        _target, visible_test = _materialize_fixture(tmp_path / task.id, task)
        hidden_source = Path(_hidden_test_for_visible_test(visible_test)).read_text(encoding="utf-8")
        by_fixture[task.fixture_kind] = hidden_source

    assert "unsupported" in by_fixture["rlm_harder_v2_autoreason_judge"]
    assert "risky-required" in by_fixture["rlm_harder_v2_ddtree_pruning"]
    assert "negative_exit_code" in by_fixture["rlm_harder_v2_ultra_review_report"]
    assert "wrong-topic" in by_fixture["rlm_harder_v2_research_citation"]
    assert "missing-source" in by_fixture["rlm_harder_v2_lancedb_retrieval"]
    assert "single_role" in by_fixture["rlm_harder_v2_swarm_consensus"]
    assert "count_mismatch" in by_fixture["rlm_harder_v2_drone_artifacts"]
    assert "recommended_without_invocation" in by_fixture["rlm_harder_v2_nightshift_recovery"]


def test_codex_guidance_names_incident_classifier_needs_evidence() -> None:
    task = CapabilityTask(
        id="nexus-value-trust-002",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix an incident classifier that over-trusts a passing smoke test.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_trust_incident_classifier",
    )

    guidance = _nexus_codex_hidden_verifier_guidance(
        task,
        "def classify(smoke_passed, semantic_evidence):\n    return 'resolved' if smoke_passed else 'open'\n",
    )

    assert "returns needs_evidence" in guidance
    assert "smoke_passed=False remains open" in guidance


def test_nexus_task_desc_names_trust_classifier_decision_table() -> None:
    task = CapabilityTask(
        id="nexus-value-trust-002",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix an incident classifier that over-trusts a passing smoke test.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_trust_incident_classifier",
    )

    desc = _nexus_task_desc(task)

    assert "Nexus trust classifier decision table" in desc
    assert "semantic_evidence.get('verified') is True" in desc
    assert "Do not rely on dictionary truthiness" in desc


def test_nexus_task_desc_names_hidden_parser_separator_contract() -> None:
    task = CapabilityTask(
        id="nexus-value-hidden-002",
        difficulty="easy",
        task_type="public_hidden_bugfix",
        task_desc="Normalize generated keys across user-entered labels.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_hidden_parser",
    )

    desc = _nexus_task_desc(task)

    assert "Nexus parser normalization decision table" in desc
    assert "Treat spaces, hyphens, and underscores as separators" in desc
    assert "Mixed-case keys with repeated separators" in desc
    assert "API__Token" not in desc


def test_resolve_task_files_can_fail_closed_without_materializing(tmp_path: Path):
    task = CapabilityTask(
        id="real-001",
        difficulty="easy",
        task_type="cross_module_refactor_swarm",
        task_desc="Use real files",
        target_file="src.py",
        test_file="tests/test_src.py",
        success_criteria="all_target_tests_pass",
    )
    try:
        _resolve_task_files(tmp_path, task, materialize_missing=False)
    except FileNotFoundError as exc:
        assert "real-001" in str(exc)
    else:
        raise AssertionError("missing real task files should fail closed")


def test_resolve_task_files_preserves_existing_real_paths(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "src.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_src.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    task = CapabilityTask(
        id="real-002",
        difficulty="hard",
        task_type="cross_module_refactor_swarm",
        task_desc="Use real files",
        target_file="src.py",
        test_file="tests/test_src.py",
        success_criteria="all_target_tests_pass",
    )
    target, test = _resolve_task_files(tmp_path, task, materialize_missing=False)
    assert target.endswith("src.py")
    assert test.endswith("tests/test_src.py")


def test_resolve_task_files_uses_real_paths_for_nexus_internal_even_when_materializing(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "src.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_src.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    task = CapabilityTask(
        id="pub-internal",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Use real internal files",
        target_file="src.py",
        test_file="tests/test_src.py",
        success_criteria="patch_and_tests_pass",
        repo_kind="nexus_internal",
    )
    target, test = _resolve_task_files(tmp_path, task, materialize_missing=True)
    assert target.endswith("src.py")
    assert test.endswith("tests/test_src.py")
    assert _task_uses_materialized_fixture(task, materialize_missing=True) is False


def test_resolve_task_files_fails_closed_for_external_without_adapter(tmp_path: Path):
    task = CapabilityTask(
        id="pub-external",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="External task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="external",
    )
    try:
        _resolve_task_files(tmp_path, task, materialize_missing=True)
    except NotImplementedError as exc:
        assert "clone/setup adapter" in str(exc)
    else:
        raise AssertionError("external tasks must not materialize local fixtures")
    assert _task_uses_materialized_fixture(task, materialize_missing=True) is False


def test_preserve_target_helpers_restore_real_task_file(tmp_path: Path):
    target = tmp_path / "src.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    original = _read_preserved_target(str(target), materialize_missing=False)
    target.write_text("VALUE = 2\n", encoding="utf-8")
    _restore_preserved_target(str(target), original)
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert _read_preserved_target(str(target), materialize_missing=True) == "VALUE = 1\n"


def test_wall_ledger_conservation_passes_when_required_components_reconcile():
    row = {
        "wall_duration_sec": 10.0,
        "model_calls": 1,
        "gateway_total_sec": 9.6,
        "hidden_verifier_mode": True,
        "hidden_verifier_wall_sec": 0.3,
    }

    result = evaluate_wall_ledger_conservation(row)

    assert result["status"] == "PASS"
    assert result["wall_ledger_conserved"] is True
    assert result["wall_ledger_component_coverage_rate"] == 1.0
    assert result["wall_ledger_component_telemetry_status"]["hidden_verifier"] == "PRESENT"
    assert result["wall_ledger_reconciliation_error_ratio"] == 0.01
    assert result["unattributed_wall_sec"] == 0.1


def test_wall_ledger_conservation_marks_missing_timing_component_invalid():
    row = {
        "wall_duration_sec": 10.0,
        "model_calls": 1,
        "hidden_verifier_mode": True,
        "hidden_verifier_wall_sec": 0.3,
    }

    result = evaluate_wall_ledger_conservation(row)

    assert result["status"] == "TELEMETRY_INVALID"
    assert result["wall_ledger_conserved"] is False
    assert result["wall_ledger_component_coverage_rate"] == 0.5
    assert "wall_ledger_component_missing" in result["reason_codes"]
    assert "model_gateway" in result["wall_ledger_missing_components"]


def test_wall_ledger_fallbacks_model_gateway_to_total_when_gateway_telemetry_zero_filled():
    row = {
        "wall_duration_sec": 12.0,
        "model_calls": 1,
        "gateway_total_sec": 0.0,
        "gateway_process_sec": 0.0,
        "gateway_provider_wait_sec": 0.0,
        "hidden_verifier_mode": True,
        "hidden_verifier_wall_sec": 0.0,
    }

    result = evaluate_wall_ledger_conservation(row)

    assert result["wall_ledger_component_telemetry_status"]["model_gateway"] == "FALLBACK_TOTAL_WALL"
    assert "model_gateway_fallback_to_total_wall_sec" in result["reason_codes"]

def test_wall_ledger_marks_hidden_verifier_wall_missing_but_required():
    row = {
        "wall_duration_sec": 10.0,
        "model_calls": 1,
        "gateway_total_sec": 9.6,
        "hidden_verifier_file": "test_hidden.py",
        "hidden_verifier_passed": True,
    }

    result = evaluate_wall_ledger_conservation(row)

    assert result["status"] == "TELEMETRY_INVALID"
    assert result["wall_ledger_component_telemetry_status"]["hidden_verifier"] == "MISSING_BUT_REQUIRED"
    assert "hidden_verifier_wall_missing_but_required" in result["reason_codes"]
    assert "hidden_verifier" in result["wall_ledger_missing_components"]


def test_wall_ledger_rejects_hidden_verifier_zero_fill_when_passed():
    row = {
        "wall_duration_sec": 10.0,
        "model_calls": 1,
        "gateway_total_sec": 9.6,
        "hidden_verifier_file": "test_hidden.py",
        "hidden_verifier_passed": True,
        "hidden_verifier_wall_sec": 0.0,
    }

    result = evaluate_wall_ledger_conservation(row)

    assert result["status"] == "TELEMETRY_INVALID"
    assert result["wall_ledger_component_telemetry_status"]["hidden_verifier"] == "SUSPICIOUS_ZERO_FILL"
    assert "hidden_verifier_wall_suspicious_zero_fill" in result["reason_codes"]
    assert "hidden_verifier" in result["wall_ledger_missing_components"]


def test_wall_ledger_allows_hidden_verifier_timing_included_in_model_attempt():
    row = {
        "wall_duration_sec": 10.0,
        "model_calls": 1,
        "gateway_total_sec": 9.8,
        "hidden_verifier_file": "test_hidden.py",
        "hidden_verifier_passed": True,
        "hidden_verifier_wall_sec": 0.0,
        "hidden_verifier_wall_source": "included_in_model_attempt_wall_sec",
    }

    result = evaluate_wall_ledger_conservation(row)

    assert result["status"] == "PASS"
    assert result["wall_ledger_component_telemetry_status"]["hidden_verifier"] == "INCLUDED_IN_MODEL_ATTEMPT"
    assert "hidden_verifier_wall_suspicious_zero_fill" not in result["reason_codes"]


def test_wall_ledger_conservation_is_not_applicable_for_legacy_rows_without_timing():
    row = {
        "wall_duration_sec": 10.0,
        "model_calls": 1,
    }

    result = evaluate_wall_ledger_conservation(row)

    assert result["status"] == "NOT_APPLICABLE"
    assert result["wall_ledger_conserved"] is True
    assert result["wall_ledger_component_coverage_rate"] == 1.0


def test_expected_receipt_backfill_replaces_non_public_safe_receipts():
    receipts = _ensure_expected_capability_receipts(
        task_id="docs-lane-public-field-contract-001",
        expected_capabilities=("memory", "delivery_gate"),
        capability_receipts=[
            {
                "name": "memory",
                "selected": True,
                "invoked": False,
                "evidence_present": False,
                "gate_passed": False,
                "failure_reason": "selected_without_invocation",
                "public_claim_safe": False,
            },
            {
                "name": "delivery_gate",
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": False,
                "failure_reason": "evidence_without_gate_pass",
                "public_claim_safe": False,
            },
        ],
        codeintel={},
        tests_passed=True,
        delivery_evidence_refs=["hidden.py"],
    )

    coverage = _expected_capability_receipt_coverage(("memory", "delivery_gate"), receipts)

    assert coverage["all_public_safe"] is True
    assert coverage["missing"] == []


def test_taskset_contract_hashes_are_canonical_and_policy_sensitive(tmp_path: Path):
    runner = tmp_path / "runner.py"
    runner.write_text("print('runner')\n", encoding="utf-8")
    config_a = {
        "tasks_file": "tasks.json",
        "tasks_manifest_hash": "a" * 64,
        "public_disclosure_manifest": {"path": "tasks.public.json", "sha256": "b" * 64, "status": "PASS"},
        "hidden_verifier_mode": True,
        "session_worker": True,
        "session_worker_policy": "persistent_worker_with_reset_boundary",
        "warning_ledger_required": True,
        "wall_ledger_required": True,
        "provider_token_measured_required": True,
    }
    config_b = dict(reversed(list(config_a.items())))

    contract_a = build_taskset_contract(config=config_a, runner_path=runner)
    contract_b = build_taskset_contract(config=config_b, runner_path=runner)
    config_changed = {**config_a, "session_worker_policy": "fresh_direct_invocation"}
    config_codex = {
        **config_a,
        "without_mode": "codex",
        "with_model_provider": "codex",
        "with_llm_mode": "hard",
    }
    config_gemini = {
        **config_a,
        "without_mode": "gemini",
        "with_model_provider": "gemini",
        "with_llm_mode": "hard",
    }

    assert contract_a["prompt_contract"]["sha256"] == contract_b["prompt_contract"]["sha256"]
    assert contract_a["verifier_contract"]["sha256"] == contract_b["verifier_contract"]["sha256"]
    assert contract_a["fixed_public_taskset_ready"] is True
    assert build_prompt_contract_hash(config_a) != build_prompt_contract_hash(config_changed)
    assert build_prompt_contract_hash(config_codex) == build_prompt_contract_hash(config_gemini)
    assert build_provider_transport_contract_hash(config_codex) != build_provider_transport_contract_hash(config_gemini)
    assert contract_a["provider_transport_contract"]["hash_present"] is True
    assert contract_a["benchmark_basis_contract"]["commercial_model_basis_ready"] is False

    commercial_manifest = tmp_path / "commercial.json"
    commercial_manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "nexus-public-commercial-lanes-v1:all",
                "commercial_lane_source": "scripts/bench/public_benchmark_commercial_lanes_v1.json",
                "tasks": [{"id": "task-1", "commercial_lane": "governed_delivery"}],
            }
        ),
        encoding="utf-8",
    )
    basis = build_benchmark_basis_contract(commercial_manifest)
    assert basis["schema"] == "nexus_benchmark_basis_contract_v1"
    assert basis["status"] == "PASS"
    assert basis["commercial_model_basis_ready"] is True


def test_persistent_worker_gap_dashboard_compares_existing_bundles(tmp_path: Path):
    def bundle(path: Path, *, with_rate: float, without_rate: float, provider: str = "gemini") -> None:
        path.write_text(
            json.dumps(
                {
                    "config": {
                        "session_worker": True,
                        "session_worker_policy": "persistent_worker_with_reset_boundary",
                        "hidden_verifier_mode": True,
                        "without_mode": provider,
                        "with_llm_mode": "hard",
                        "with_model_provider": provider,
                        "external_model_export_policy": "sanitized",
                        "outbound_prompt_ledger": "ledger.jsonl",
                    },
                    "task_manifest": {"sha256": "taskset"},
                    "taskset_contract": {
                        "prompt_contract": {"sha256": f"source-prompt-{provider}"},
                        "provider_transport_contract": {"sha256": f"transport-{provider}"},
                        "verifier_contract": {"sha256": "verifier"},
                        "runner_contract": {"sha256": "runner"},
                        "fixed_public_taskset_ready": True,
                    },
                    "session_worker_contamination": {"contamination_rate": 0.0, "clean": True},
                    "public_verified_delivery_claim_gate": {"verdict": "PASS"},
                    "public_cost_claim_gate": {"verdict": "PASS"},
                    "public_cost_efficiency_claim_gate": {"verdict": "NEUTRAL"},
                    "commercial_model_roi_shadow_hooks": {
                        "status": "OBSERVATION_ONLY",
                        "reason_counts": {"verified_lift_or_delivery_with_wall_regression": 1},
                        "wall_regression_concentration": {
                            "buckets": [
                                {
                                    "route_cost_policy_lane": "governance_hardened",
                                    "strategy_path": "hyper_direct_forced",
                                    "task_type": "public_ops_research",
                                    "pair_count": 1,
                                    "verified_lift_count": 1,
                                    "avg_wall_ratio": 2.1,
                                    "sum_wall_delta": 12.0,
                                    "reason_codes": ["hyper_direct_forced_wall_regression"],
                                }
                            ]
                        },
                    },
                    "public_claim_gate": {
                        "checks": {
                            "eligible_without_nexus": 12,
                            "with_semantic_verified_rate": with_rate,
                            "without_semantic_verified_rate": without_rate,
                            "provider_token_measured_rate_without": 1.0,
                            "wall_ledger_without_conserved_rate": 1.0,
                            "with_trust_mismatch_rate": 0.0,
                            "without_trust_mismatch_rate": 0.0,
                            "avg_tokens_with": 120.0,
                            "avg_tokens_without": 100.0,
                            "avg_model_calls_with": 1.0,
                            "avg_model_calls_without": 1.0,
                            "wall_cost_ratio_with_over_without": 1.0,
                            "token_cost_ratio_with_over_without": 1.2,
                            "route_cost_regression_wall_ratio_threshold": 1.8,
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

    baseline = tmp_path / "gpt55.json"
    flash = tmp_path / "flash.json"
    bundle(baseline, with_rate=0.0, without_rate=0.8, provider="codex")
    bundle(flash, with_rate=0.75, without_rate=0.6, provider="gemini")

    dashboard = build_gap_dashboard(
        baseline=str(baseline),
        treatments=[str(flash)],
        labels=["gpt5.5_direct_worker", "flash_nexus_worker"],
    )

    assert dashboard["schema"] == "nexus_persistent_worker_gap_dashboard_v1"
    assert dashboard["readiness"]["taskset_identical"] is True
    assert dashboard["readiness"]["prompt_policy_identical"] is True
    assert dashboard["readiness"]["provider_transport_recorded"] is True
    assert dashboard["readiness"]["provider_transport_identical"] is False
    assert dashboard["readiness"]["provider_transport_identical_required"] is False
    assert dashboard["readiness"]["verifier_policy_identical"] is True
    assert dashboard["readiness"]["baseline_direct_usable"] is True
    assert dashboard["comparisons"][0]["baseline_direct_verified_rate"] == 0.8
    assert dashboard["comparisons"][0]["verified_delivery_gap_vs_baseline"] == -0.05
    assert dashboard["comparisons"][0]["trust_gap_vs_baseline"] == 0.0
    assert dashboard["comparisons"][0]["delivery_promotion_ready"] is True
    assert dashboard["comparisons"][0]["cost_promotion_ready"] is True
    assert dashboard["comparisons"][0]["source_promotion_ready"] is True
    assert dashboard["comparisons"][0]["promotion_ready"] is True
    assert dashboard["comparisons"][0]["final_goal_ready"] is False

    payload = json.loads(flash.read_text(encoding="utf-8"))
    payload["taskset_contract"]["benchmark_basis_contract"] = {"commercial_model_basis_ready": True}
    flash.write_text(json.dumps(payload), encoding="utf-8")
    final_ready = build_gap_dashboard(
        baseline=str(baseline),
        treatments=[str(flash)],
        labels=["gpt5.5_direct_worker", "flash_nexus_worker"],
    )
    assert final_ready["comparisons"][0]["promotion_ready"] is True
    assert final_ready["comparisons"][0]["final_goal_ready"] is True

    payload = json.loads(flash.read_text(encoding="utf-8"))
    payload["public_cost_efficiency_claim_gate"]["verdict"] = "REGRESSED"
    payload["public_claim_gate"]["checks"]["wall_cost_ratio_with_over_without"] = 1.9
    payload["public_claim_gate"]["checks"]["token_cost_ratio_with_over_without"] = 0.8
    flash.write_text(json.dumps(payload), encoding="utf-8")
    cost_blocked = build_gap_dashboard(
        baseline=str(baseline),
        treatments=[str(flash)],
        labels=["gpt5.5_direct_worker", "flash_nexus_worker"],
    )
    assert cost_blocked["comparisons"][0]["delivery_promotion_ready"] is True
    assert cost_blocked["comparisons"][0]["cost_promotion_ready"] is False
    assert cost_blocked["comparisons"][0]["promotion_ready"] is False
    assert cost_blocked["comparisons"][0]["cost_policy_hook"]["promotion_effect"] == "none"
    assert cost_blocked["comparisons"][0]["cost_policy_hook"]["recommendation"] == "light_route_low_risk_full_nexus_high_risk"
    assert "wall_ratio_above_threshold" in cost_blocked["comparisons"][0]["cost_policy_hook"]["reason_codes"]
    triage_hook = cost_blocked["comparisons"][0]["performance_load_stress_hook"]
    assert triage_hook["schema"] == "nexus_performance_load_stress_cost_hook_v1"
    assert triage_hook["promotion_effect"] == "none"
    assert triage_hook["performance_test"]["status"] == "REGRESSED"
    assert triage_hook["load_test"]["status"] == "RETURN"
    assert triage_hook["stress_test"]["status"] == "NEEDS_ROUTE_COST_RCA"
    assert triage_hook["stress_test"]["top_wall_regression_buckets"][0]["route_cost_policy_lane"] == "governance_hardened"
    assert (
        triage_hook["stress_test"]["top_wall_regression_buckets"][0]["suggested_action"]
        == "cap_hyper_or_try_supervised_preflight_before_second_model_call"
    )
    assert "bucket_high_risk_routes_and_light_route_low_risk_tasks" in triage_hook["next_actions"]

    payload = json.loads(flash.read_text(encoding="utf-8"))
    payload["public_cost_efficiency_claim_gate"]["verdict"] = "NEUTRAL"
    payload["config"]["session_worker_policy"] = "different-prompt-policy"
    flash.write_text(json.dumps(payload), encoding="utf-8")
    blocked = build_gap_dashboard(
        baseline=str(baseline),
        treatments=[str(flash)],
        labels=["gpt5.5_direct_worker", "flash_nexus_worker"],
    )
    assert blocked["readiness"]["prompt_policy_identical"] is False
    assert blocked["comparisons"][0]["promotion_ready"] is False

    payload = json.loads(flash.read_text(encoding="utf-8"))
    payload["config"]["session_worker_policy"] = "persistent_worker_with_reset_boundary"
    payload["public_promotion_readiness_contract"] = {
        "schema": "nexus_public_promotion_readiness_contract_v1",
        "status": "RETURN",
        "failures": ["external_provider_public_claim_allowed"],
    }
    payload["external_provider_claim_boundary_contract"] = {
        "schema": "nexus_external_provider_claim_boundary_contract_v1",
        "status": "OBSERVATION_ONLY",
        "public_claim_allowed": False,
        "failures": ["codex_provider_prompt_wearing_only_for_external_model_claims"],
    }
    flash.write_text(json.dumps(payload), encoding="utf-8")
    source_blocked = build_gap_dashboard(
        baseline=str(baseline),
        treatments=[str(flash)],
        labels=["gpt5.5_direct_worker", "gpt5.5_nexus_observation_only"],
    )
    assert source_blocked["comparisons"][0]["delivery_promotion_ready"] is True
    assert source_blocked["comparisons"][0]["cost_promotion_ready"] is True
    assert source_blocked["comparisons"][0]["source_promotion_ready"] is False
    assert source_blocked["comparisons"][0]["promotion_ready"] is False


def test_write_trial_evidence_and_bundle(tmp_path: Path):
    row = {
        "mode": "with_nexus",
        "task_id": "task/1",
        "trial_index": 2,
        "task_type": "public_test_repair",
        "expected_capabilities": ["ddtree"],
        "status": "SUCCESS",
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "token_measured": True,
        "provider_token_measured": True,
        "token_capture_status": "measured",
        "gateway_token_source": "stats",
        "total_tokens": 100,
        "model_calls": 2,
        "wall_duration_sec": 42.0,
        "gateway_total_sec": 42.0,
        "phase_wall_total_sec": 32.0,
        "phase_wall_p_sec": 2.0,
        "phase_wall_x_sec": 1.0,
        "phase_wall_d_sec": 0.0,
        "phase_wall_r_sec": 28.0,
        "phase_wall_a_sec": 1.0,
        "phase_wall_c_sec": 0.0,
        "gateway_stats_present": True,
        "prompt_system_instruction_chars": 50,
        "prompt_task_constraint_chars": 20,
        "prompt_source_payload_chars": 30,
        "prompt_test_payload_chars": 40,
        "prompt_candidate_payload_chars": 10,
        "prompt_nexus_control_chars": 0,
        "prompt_governance_contract_chars": 0,
        "nexus_wearing_valid": True,
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
        "route_decision_schema_version": "nexus_route_decision_v1",
        "route_execution_policy": _route_policy(),
        "capability_receipts": [
            {
                "name": "ddtree",
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "public_claim_safe": True,
                "evidence_refs": ["saved_steps:2"],
            }
        ],
        "expected_capability_receipt_coverage": {
            "expected": ["ddtree"],
            "missing": [],
            "all_public_safe": True,
        },
        "expected_capability_invocation_coverage": {
            "expected": ["ddtree"],
            "missing": [],
            "all_invoked_with_evidence": True,
        },
        "rubric_contract_status": "PASS",
        "openseeker_schema_version": "nexus_openseeker_alignment.v1",
        "trajectory_step_count": 12,
        "tool_action_count": 4,
        "evidence_hop_count": 5,
        "evidence_source_count": 3,
        "low_step_filtered": False,
        "long_horizon_ready": True,
        "route_tactical_tool_count": 4,
        "route_evidence_required_count": 3,
    }
    evidence = _write_trial_evidence(
        evidence_root=tmp_path / "evidence",
        row=row,
        target_before="VALUE = 1\n",
        target_after="VALUE = 2\n",
    )
    row.update(evidence)
    assert Path(evidence["evidence_record_file"]).exists()
    diff_text = Path(evidence["evidence_diff_file"]).read_text(encoding="utf-8")
    assert "-VALUE = 1" in diff_text
    assert "+VALUE = 2" in diff_text

    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    write_jsonl(with_path, [row])
    without_row = {
        "mode": "without_nexus",
        "task_id": "task/1",
        "trial_index": 2,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "token_measured": True,
        "provider_token_measured": True,
        "token_capture_status": "measured",
        "gateway_token_source": "stats",
        "total_tokens": 100,
        "gateway_stats_present": True,
    }
    write_jsonl(without_path, [without_row])
    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[row, without_row],
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 1,
            "runner_command": "capability_ab_runner.py --tasks-file tasks.json",
            "hidden_verifier_mode": True,
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
        },
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert payload["schema"] == "nexus_public_benchmark_evidence_bundle_v2"
    assert payload["raw_files"]["with_nexus"]["sha256"]
    assert len(payload["artifact_files"]) == 2
    assert payload["model_lock"]["same_model"] is True
    assert payload["row_counts"]["with_nexus"] == 1
    assert payload["row_counts"]["without_nexus"] == 1
    assert payload["nexus_wearing"]["valid_rate"] == 1.0
    assert payload["public_claim_gate"]["verdict"] == "PASS"
    assert payload["public_claim_gate"]["checks"]["hidden_verifier_mode"] is True
    assert payload["public_claim_gate"]["checks"]["run_eligibility_complete"] is True
    assert payload["public_claim_gate"]["checks"]["trust_mismatch_free"] is True
    assert payload["public_claim_gate"]["checks"]["nexus_wearing_valid_rate"] == 1.0
    assert payload["public_claim_gate"]["checks"]["route_decision_present_rate"] == 1.0
    assert payload["public_claim_gate"]["checks"]["route_cost_ledger_schema"] == "nexus_route_cost_ledger_v1"
    assert payload["public_claim_gate"]["checks"]["route_cost_trace_report_schema"] == "nexus_route_cost_trace_report_v1"
    assert payload["public_claim_gate"]["checks"]["s2t_shadow_report_schema"] == "nexus_s2t_shadow_report_v1"
    assert payload["public_claim_gate"]["checks"]["s2t_policy_draft_schema"] == "nexus_promoted_s2t_policy_draft_v1"
    assert payload["public_claim_gate"]["checks"]["s2t_policy_draft_status"] == "DRAFT_SHADOW_ONLY"
    assert payload["public_claim_gate"]["checks"]["product_kpis_schema"] == "nexus_product_kpis_v1"
    assert payload["public_claim_gate"]["checks"]["openseeker_alignment_schema"] == "nexus_openseeker_benchmark_kpis_v1"
    assert payload["public_verified_delivery_claim_gate"]["verdict"] == "PASS"
    assert payload["public_cost_efficiency_claim_gate"]["verdict"] == "IMPROVED"
    assert payload["public_claim_posture"]["delivery"]["status"] == "PASS"
    assert payload["public_claim_posture"]["cost_safety"]["status"] == "PASS"
    assert payload["public_claim_posture"]["cost_efficiency"]["status"] == "IMPROVED"
    assert payload["public_claim_posture"]["cost_efficiency"]["token_roi_status"] == "EFFICIENT"
    assert payload["public_cost_efficiency_claim_gate"]["checks"]["verified_lift_rate"] == 0.0
    assert payload["public_cost_efficiency_claim_gate"]["checks"]["avg_prompt_source_payload_chars_with"] == 30.0
    assert payload["public_claim_posture"]["cost_efficiency"]["sample_sufficient"] is False
    assert payload["public_claim_posture"]["cost_efficiency"]["min_required_pairs"] == 3
    assert payload["public_claim_posture"]["public_wording_key"] == "promising_but_insufficient_sample"
    assert payload["public_claim_posture"]["public_wording_allowed"] is True
    assert payload["public_promotion_readiness_contract"]["schema"] == "nexus_public_promotion_readiness_contract_v1"
    assert payload["public_promotion_readiness_contract"]["requirements"]["route_policy_evidence_pass"] is True
    assert payload["external_provider_claim_boundary_contract"]["schema"] == (
        "nexus_external_provider_claim_boundary_contract_v1"
    )
    assert payload["external_provider_claim_boundary_contract"]["status"] == "PASS"
    assert payload["public_promotion_readiness_contract"]["requirements"][
        "external_provider_public_claim_allowed"
    ] is True
    assert payload["public_claim_posture"]["cost_efficiency_wording_allowed"] is False
    assert payload["public_claim_posture"]["allowed_public_wording"] == "promising_but_insufficient_sample"
    assert "cost_improved" not in payload["public_claim_posture"]["allowed_public_wording"]
    assert payload["public_lane_contract"]["non_public_eligible"] is True
    assert payload["training_eligibility_posture"]["status"] == "OBSERVATION_ONLY_SAMPLE_INSUFFICIENT"
    assert payload["training_eligibility_posture"]["reason_codes"] == ["sample_insufficient"]
    assert payload["infra_quarantine_report"]["infra_valid_pair_count"] == 1
    assert payload["infra_quarantine_report"]["infra_invalid_pair_count"] == 0
    claim_lines = "\n".join(_claim_posture_lines(payload))
    assert "Cost efficiency: INCONCLUSIVE" in claim_lines
    assert "cost reduction" not in claim_lines.lower()
    assert "cheaper" not in claim_lines.lower()
    assert "cost_improved" not in claim_lines.lower()
    assert payload["route_cost_ledger"]["scope"] == "measured_benchmark_telemetry_not_billing_cost"
    assert payload["route_cost_ledger"]["arms"]["with_nexus"]["rows"] == 1
    assert payload["route_cost_ledger"]["arms"]["without_nexus"]["rows"] == 1

    codex_bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[row, without_row],
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 1,
            "runner_command": "capability_ab_runner.py --tasks-file tasks.json",
            "hidden_verifier_mode": True,
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
            "with_model_provider": "codex",
            "without_mode": "codex",
        },
    )
    codex_payload = json.loads(codex_bundle.read_text(encoding="utf-8"))
    assert codex_payload["external_provider_claim_boundary_contract"]["status"] == "OBSERVATION_ONLY"
    assert codex_payload["external_provider_claim_boundary_contract"]["public_claim_allowed"] is False
    assert codex_payload["public_promotion_readiness_contract"]["requirements"][
        "external_provider_public_claim_allowed"
    ] is False

    forced_bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[row, without_row],
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 1,
            "runner_command": "capability_ab_runner.py --tasks-file tasks.json --force-learn-slo-ready",
            "hidden_verifier_mode": True,
            "force_learn_slo_ready": True,
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
        },
    )
    forced_payload = json.loads(forced_bundle.read_text(encoding="utf-8"))
    assert forced_payload["public_lane_contract"]["non_public_eligible"] is False
    assert forced_payload["public_lane_contract"]["non_public_reasons"] == ["force_learn_slo_ready"]
    assert forced_payload["public_verified_delivery_claim_gate"]["verdict"] == "FAIL"
    assert "non_public_shortcut:force_learn_slo_ready" in forced_payload["public_verified_delivery_claim_gate"]["failures"]
    assert forced_payload["training_eligibility_posture"]["status"] == "OBSERVATION_ONLY_SYNTHETIC_READINESS"
    assert (
        "synthetic_readiness_shortcut:force_learn_slo_ready"
        in forced_payload["training_eligibility_posture"]["reason_codes"]
    )
    assert forced_payload["taskset_contract"]["taskset"]["hash_present"] is True
    assert forced_payload["taskset_contract"]["prompt_contract"]["hash_present"] is True
    assert len(forced_payload["taskset_contract"]["prompt_contract"]["sha256"]) == 64
    assert forced_payload["taskset_contract"]["verifier_contract"]["hash_present"] is True
    assert forced_payload["taskset_contract"]["verifier_contract"]["hidden_verifier_mode"] is True
    assert len(forced_payload["taskset_contract"]["verifier_contract"]["sha256"]) == 64
    assert forced_payload["taskset_contract"]["runner_contract"]["hash_present"] is True
    assert forced_payload["taskset_contract"]["fixed_public_taskset_ready"] is False
    assert payload["route_cost_ledger"]["arms"]["with_nexus"]["phase_wall_share"]["R"] == 0.875
    assert payload["route_cost_ledger"]["arms"]["with_nexus"]["top_wall_offenders"][0]["task_capability"] == "ddtree"
    assert payload["route_cost_ledger"]["arms"]["with_nexus"]["top_phase_wall_offenders"][0]["dominant_phase"] == "R"
    assert payload["route_cost_ledger"]["arms"]["with_nexus"]["by_task_capability"][0]["task_capability"] == "ddtree"
    assert payload["route_cost_trace_report"]["schema"] == "nexus_route_cost_trace_report_v1"
    assert payload["s2t_shadow_report"]["schema"] == "nexus_s2t_shadow_report_v1"
    assert payload["s2t_shadow_report"]["trace_event_schema"] == "nexus_s2t_trace_event_v1"
    assert payload["s2t_shadow_report"]["promotion_gate"]["status"] == "SHADOW_ONLY"
    assert payload["s2t_shadow_report"]["events"][0]["selector_shadow"]["training_eligible"] is True
    assert payload["s2t_policy_draft"]["schema"] == "nexus_promoted_s2t_policy_draft_v1"
    assert payload["s2t_policy_draft"]["status"] == "DRAFT_SHADOW_ONLY"
    assert payload["product_kpis"]["schema"] == "nexus_product_kpis_v1"
    assert payload["product_kpis"]["arms"]["with_nexus"]["avg_time_to_verified_sec"] == 0.0
    assert payload["product_kpis"]["arms"]["without_nexus"]["fail_closed_block_rate"] == 1.0
    assert payload["openseeker_alignment"]["schema"] == "nexus_openseeker_benchmark_kpis_v1"
    assert payload["openseeker_alignment"]["arms"]["with_nexus"]["avg_trajectory_step_count"] == 12.0
    assert payload["openseeker_alignment"]["arms"]["with_nexus"]["avg_route_tactical_tool_count"] == 4.0
    assert payload["openseeker_alignment"]["arms"]["with_nexus"]["avg_route_evidence_required_count"] == 3.0
    assert payload["openseeker_alignment"]["arms"]["with_nexus"]["long_horizon_ready_rate"] == 1.0


def test_session_worker_contamination_fails_public_claim_gate(tmp_path: Path):
    def row(mode: str, task_id: str, turn: int, raw_tail: str = "") -> dict[str, object]:
        return {
            "mode": mode,
            "task_id": task_id,
            "trial_index": 1,
            "status": "SUCCESS",
            "semantic_status": "VERIFIED",
            "model_name": "gemini-3-flash-preview",
            "run_eligible": True,
            "token_measured": True,
            "provider_token_measured": True,
            "token_capture_status": "measured",
            "gateway_token_source": "stats",
            "total_tokens": 100,
            "model_calls": 1,
            "wall_duration_sec": 10.0,
            "gateway_total_sec": 9.5,
            "gateway_stats_present": True,
            "nexus_wearing_valid": mode == "with_nexus",
            "gemini_uses_nexus": mode == "with_nexus",
            "nexus_context_delivered": mode == "with_nexus",
            "nexus_usage_valid": mode == "with_nexus",
            "capability_claim_verified": mode == "with_nexus",
            "route_decision_schema_version": "nexus_route_decision_v1" if mode == "with_nexus" else "",
            "route_execution_policy": _route_policy() if mode == "with_nexus" else {},
            "rubric_contract_status": "PASS",
            "session_worker_enabled": True,
            "session_worker_provider": "gemini",
            "session_worker_id": f"{mode}-session",
            "session_worker_turn_index": turn,
            "session_worker_resumed": turn > 1,
            "reset_boundary_hash": f"reset-{task_id}",
            "baseline_raw_tail": raw_tail,
        }

    rows = [
        row("with_nexus", "task-a", 1),
        row("without_nexus", "task-a", 1),
        row("with_nexus", "task-b", 2, raw_tail="accidentally reused task-a context"),
        row("without_nexus", "task-b", 2),
    ]
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    write_jsonl(with_path, [r for r in rows if r["mode"] == "with_nexus"])
    write_jsonl(without_path, [r for r in rows if r["mode"] == "without_nexus"])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=rows,  # type: ignore[arg-type]
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 2,
            "runner_command": "capability_ab_runner.py --session-worker",
            "hidden_verifier_mode": True,
            "session_worker": True,
            "session_worker_policy": "persistent_worker_with_reset_boundary",
            "warning_ledger_required": True,
            "wall_ledger_required": True,
            "provider_token_measured_required": True,
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
        },
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))

    assert payload["session_worker_contamination"]["contaminated_row_count"] == 1
    assert payload["session_worker_contamination"]["clean"] is False
    assert payload["public_claim_gate"]["checks"]["session_worker_contamination_rate"] > 0.0
    assert "session_worker_contamination_detected" in payload["public_verified_delivery_claim_gate"]["failures"]
    assert payload["public_verified_delivery_claim_gate"]["verdict"] == "FAIL"


def test_write_evidence_bundle_separates_delivery_lift_from_cost_efficiency_regression(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {
        "mode": "with_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "status": "SUCCESS",
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "wall_duration_sec": 108.0,
        "gateway_total_sec": 58.0,
        "phase_wall_r_sec": 38.0,
        "r_phase_hyper_sprint_sec": 38.0,
        "hidden_retry_wall_sec": 50.0,
        "hidden_retry_tokens": 61000,
        "total_tokens": 122000,
        "model_calls": 2,
        "token_measured": True,
        "provider_token_measured": True,
        "model_token_capture_status": "measured",
        "gateway_token_source": "stats",
        "gateway_stats_present": True,
        "nexus_wearing_valid": True,
        "gemini_uses_nexus": True,
        "model_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
        "route_decision_schema_version": "nexus_route_decision_v1",
            "route_execution_policy": _route_policy(),
        "rubric_contract_status": "PASS",
    }
    without_row = {
        "mode": "without_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "status": "FAILED",
        "semantic_completed": False,
        "report_trust_mismatch": False,
        "wall_duration_sec": 60.0,
        "total_tokens": 64000,
        "model_calls": 1,
        "token_measured": True,
        "provider_token_measured": True,
        "model_token_capture_status": "measured",
        "gateway_token_source": "stats",
        "gateway_stats_present": True,
    }
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 1,
            "runner_command": "capability_ab_runner.py --tasks-file tasks.json",
            "hidden_verifier_mode": True,
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
        },
    )

    payload = json.loads(bundle.read_text(encoding="utf-8"))

    assert payload["public_delivery_gate"]["verdict"] == "PASS"
    assert payload["public_verified_delivery_claim_gate"]["verdict"] == "PASS"
    assert payload["public_cost_claim_gate"]["verdict"] == "PASS"
    assert payload["public_cost_efficiency_claim_gate"]["verdict"] == "REGRESSED"
    assert payload["public_claim_posture"]["delivery"]["status"] == "PASS"
    assert payload["public_claim_posture"]["cost_safety"]["status"] == "PASS"
    assert payload["public_claim_posture"]["cost_efficiency"]["status"] == "REGRESSED"
    assert payload["public_claim_posture"]["cost_efficiency"]["token_roi_status"] == "LIFT_WITH_OVERHEAD"
    assert payload["public_cost_efficiency_claim_gate"]["checks"]["marginal_token_utility"] > 0
    assert payload["public_claim_posture"]["public_wording_key"] == "promising_but_insufficient_sample"
    assert payload["public_claim_posture"]["public_wording_allowed"] is True
    assert payload["public_claim_posture"]["cost_efficiency_wording_allowed"] is False
    assert payload["public_claim_posture"]["allowed_public_wording"] == "promising_but_insufficient_sample"
    reason_codes = payload["public_claim_posture"]["cost_efficiency"]["reason_codes"]
    assert "wall_cost_not_improved" in reason_codes
    assert "token_cost_not_improved" in reason_codes
    assert "model_calls_not_improved" in reason_codes
    assert "hidden_retry_wall_share_present" in reason_codes
    assert "hidden_retry_second_attempt_dominant" in reason_codes
    wording = payload["public_claim_posture"]["allowed_public_wording"]
    assert "cost_reduction" not in wording
    assert "cost reduction" not in wording
    assert "reduced cost" not in wording
    assert payload["public_claim_posture"]["cost_efficiency"]["sample_sufficient"] is False
    assert payload["public_claim_posture"]["cost_efficiency"]["pair_count"] == 1
    assert payload["public_claim_posture"]["cost_efficiency"]["min_required_pairs"] == 3
    assert payload["public_cost_efficiency_claim_gate"]["checks"]["cost_efficiency_sample_sufficient"] is False
    assert payload["public_cost_efficiency_claim_gate"]["checks"]["min_required_pairs_for_efficiency_claim"] == 3
    assert payload["training_eligibility_posture"]["status"] == "OBSERVATION_ONLY_SAMPLE_INSUFFICIENT"
    assert payload["training_eligibility_posture"]["reason_codes"] == ["sample_insufficient"]
    assert payload["infra_quarantine_report"]["infra_valid_pair_count"] == 1
    assert payload["infra_quarantine_report"]["infra_invalid_pair_count"] == 0
    assert payload["public_cost_efficiency_claim_gate"]["checks"]["retry_cost_share_wall"] == 0.463
    assert payload["public_cost_efficiency_claim_gate"]["checks"]["retry_cost_share_tokens"] == 0.5


def test_evidence_bundle_adds_commercial_model_roi_shadow_hooks_without_changing_gates(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_rows = []
    without_rows = []
    for index in range(3):
        task_id = f"commercial-row-{index}"
        with_rows.append(
            {
                "mode": "with_nexus",
                "task_id": task_id,
                "trial_index": 1,
                "model_name": "gemini-3-flash-preview",
                "task_type": "public_test_repair",
                "expected_capabilities": ["hyper"],
                "run_eligible": True,
                "status": "SUCCESS",
                "semantic_completed": True,
                "report_trust_mismatch": False,
                "wall_duration_sec": 12.0,
                "phase_wall_r_sec": 9.0,
                "route_cost_policy_lane": "governance_hardened",
                "strategy_path": "hyper_direct_forced",
                "nexus_tier": "full",
                "total_tokens": 1000,
                "model_calls": 1,
                "token_measured": True,
                "provider_token_measured": True,
                "model_token_capture_status": "measured",
                "token_capture_status": "measured",
                "gateway_token_source": "stats",
            }
        )
        without_rows.append(
            {
                "mode": "without_nexus",
                "task_id": task_id,
                "trial_index": 1,
                "model_name": "gemini-3-flash-preview",
                "task_type": "public_test_repair",
                "expected_capabilities": ["hyper"],
                "run_eligible": True,
                "status": "FAILED",
                "semantic_completed": False,
                "report_trust_mismatch": False,
                "wall_duration_sec": 8.0,
                "total_tokens": 3000,
                "model_calls": 1,
                "token_measured": True,
                "provider_token_measured": True,
                "model_token_capture_status": "measured",
                "token_capture_status": "measured",
                "gateway_token_source": "stats",
            }
        )
    write_jsonl(with_path, with_rows)
    write_jsonl(without_path, without_rows)

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[*with_rows, *without_rows],
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 3,
            "runner_command": "capability_ab_runner.py --tasks-file tasks.json",
            "hidden_verifier_mode": True,
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
        },
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))

    shadow = payload["commercial_model_roi_shadow_hooks"]
    assert shadow["schema"] == "nexus_commercial_model_roi_shadow_hooks_v1"
    assert shadow["status"] == "OBSERVATION_ONLY"
    assert shadow["promotion_effect"] == "none"
    assert shadow["pair_count"] == 3
    assert shadow["signal_count"] == 3
    assert shadow["reason_counts"]["verified_lift_against_direct_commercial_model"] == 3
    assert shadow["reason_counts"]["verified_lift_or_delivery_with_wall_regression"] == 3
    assert shadow["reason_counts"]["verified_delivery_with_token_savings"] == 3
    concentration = shadow["wall_regression_concentration"]
    assert concentration["promotion_effect"] == "none"
    assert concentration["buckets"][0]["route_cost_policy_lane"] == "governance_hardened"
    assert concentration["buckets"][0]["strategy_path"] == "hyper_direct_forced"
    assert concentration["buckets"][0]["sum_wall_delta"] == 12.0
    assert "r_phase_wall_concentrated" in concentration["buckets"][0]["reason_codes"]
    assert "token_savings_wall_regression_tradeoff" in concentration["buckets"][0]["reason_codes"]
    assert "task_id" not in shadow["signals"][0]["row_locator"]
    assert all("commercial_model_roi_shadow" not in item for item in payload["public_claim_gate"]["failures"])
    assert all("commercial_model_roi_shadow" not in item for item in payload["public_cost_efficiency_claim_gate"]["failures"])
    assert payload["public_claim_gate"]["checks"]["commercial_model_roi_shadow_signal_count"] == 3


def test_write_evidence_bundle_returns_cost_efficiency_when_wall_ledger_invalid(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {
        "mode": "with_nexus",
        "task_id": "task/wall",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "status": "SUCCESS",
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "wall_duration_sec": 100.0,
        "gateway_total_sec": 20.0,
        "total_tokens": 50000,
        "model_calls": 1,
        "token_measured": True,
        "provider_token_measured": True,
        "model_token_capture_status": "measured",
        "gateway_token_source": "stats",
        "gateway_stats_present": True,
        "nexus_wearing_valid": True,
        "gemini_uses_nexus": True,
        "model_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
        "route_decision_schema_version": "nexus_route_decision_v1",
            "route_execution_policy": _route_policy(),
        "rubric_contract_status": "PASS",
    }
    without_row = {
        "mode": "without_nexus",
        "task_id": "task/wall",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "status": "FAILED",
        "semantic_completed": False,
        "report_trust_mismatch": False,
        "wall_duration_sec": 100.0,
        "gateway_total_sec": 100.0,
        "total_tokens": 60000,
        "model_calls": 1,
        "token_measured": True,
        "provider_token_measured": True,
        "model_token_capture_status": "measured",
        "gateway_token_source": "stats",
        "gateway_stats_present": True,
    }
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 1,
            "runner_command": "capability_ab_runner.py --tasks-file tasks.json",
            "hidden_verifier_mode": True,
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
        },
    )

    payload = json.loads(bundle.read_text(encoding="utf-8"))

    assert payload["public_delivery_gate"]["verdict"] == "PASS"
    assert payload["public_cost_claim_gate"]["verdict"] == "PASS"
    assert payload["public_cost_efficiency_claim_gate"]["verdict"] == "RETURN"
    assert "wall_ledger_telemetry_invalid" in payload["public_cost_efficiency_claim_gate"]["failures"]
    assert payload["wall_ledger_conservation"]["telemetry_invalid"] is True
    assert payload["wall_ledger_conservation"]["with_nexus"]["telemetry_invalid_rows"] == 1
    assert payload["public_cost_efficiency_claim_gate"]["checks"]["wall_ledger_telemetry_invalid"] is True
    assert payload["training_eligibility_posture"]["status"] == "OBSERVATION_ONLY_TELEMETRY_INVALID"
    assert "wall_ledger_telemetry_invalid" in payload["training_eligibility_posture"]["reason_codes"]


def test_write_evidence_bundle_returns_when_warning_ledger_dirty(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {
        "mode": "with_nexus",
        "task_id": "task/warning",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "status": "SUCCESS",
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "wall_duration_sec": 20.0,
        "gateway_total_sec": 20.0,
        "total_tokens": 50000,
        "model_calls": 1,
        "token_measured": True,
        "provider_token_measured": True,
        "model_token_capture_status": "measured",
        "gateway_token_source": "stats",
        "gateway_stats_present": True,
        "nexus_wearing_valid": True,
        "gemini_uses_nexus": True,
        "model_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
        "route_decision_schema_version": "nexus_route_decision_v1",
            "route_execution_policy": _route_policy(),
        "rubric_contract_status": "PASS",
        "warning_capture_status": "captured",
        "warning_capture_complete": True,
        "warning_lines": ["<unknown>:270: SyntaxWarning: 'return' in a 'finally' block"],
        "warning_records": [
            {
                "source": "with_nexus_runtime",
                "category": "SyntaxWarning",
                "message": "'return' in a 'finally' block",
                "line": "<unknown>:270: SyntaxWarning: 'return' in a 'finally' block",
                "filename": "<unknown>",
                "lineno": 270,
                "location": "<unknown>:270",
                "source_resolved": False,
            }
        ],
        "warning_locations": ["<unknown>:270"],
        "warning_filenames": ["<unknown>"],
        "warning_linenos": [270],
        "warning_source_resolved_rate": 0.0,
        "unresolved_warning_count": 1,
        "warning_sources": ["with_nexus_runtime"],
        "uncaptured_warning_count": 0,
    }
    without_row = {
        "mode": "without_nexus",
        "task_id": "task/warning",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "status": "FAILED",
        "semantic_completed": False,
        "report_trust_mismatch": False,
        "wall_duration_sec": 30.0,
        "gateway_total_sec": 30.0,
        "total_tokens": 60000,
        "model_calls": 1,
        "token_measured": True,
        "provider_token_measured": True,
        "model_token_capture_status": "measured",
        "gateway_token_source": "stats",
        "gateway_stats_present": True,
        "warning_capture_status": "captured",
        "warning_capture_complete": True,
        "warning_lines": [],
        "warning_sources": [],
        "uncaptured_warning_count": 0,
    }
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 1,
            "runner_command": "capability_ab_runner.py --tasks-file tasks.json",
            "hidden_verifier_mode": True,
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
            "warning_ledger_required": True,
        },
    )

    payload = json.loads(bundle.read_text(encoding="utf-8"))

    assert payload["warning_clean_gate"]["verdict"] == "RETURN"
    assert payload["warning_clean_gate"]["checks"]["warning_dirty_row_count"] == 1
    assert payload["warning_clean_gate"]["checks"]["unresolved_warning_count"] == 1
    assert payload["warning_clean_gate"]["checks"]["warning_source_resolved_rate"] == 0.0
    assert payload["public_cost_efficiency_claim_gate"]["verdict"] == "RETURN"
    assert "warning_ledger_telemetry_invalid" in payload["public_cost_efficiency_claim_gate"]["failures"]
    assert payload["training_eligibility_posture"]["status"] == "OBSERVATION_ONLY_TELEMETRY_INVALID"


def test_warning_ledger_preserves_source_attribution_metadata():
    records = warning_records_from_text(
        "/tmp/generated_candidate.py:270: SyntaxWarning: 'return' in a 'finally' block",
        source="with_nexus_runtime",
    )
    row: dict[str, object] = {}

    annotate_warning_row(row, records)

    assert row["warning_clean"] is False
    assert row["warning_capture_complete"] is True
    assert row["warning_source_resolved_rate"] == 1.0
    assert row["unresolved_warning_count"] == 0
    assert row["warning_locations"] == ["/tmp/generated_candidate.py:270"]
    assert row["warning_filenames"] == ["/tmp/generated_candidate.py"]
    assert row["warning_linenos"] == [270]
    assert row["warning_records"] == [
        {
            "source": "with_nexus_runtime",
            "category": "SyntaxWarning",
            "message": "'return' in a 'finally' block",
            "line": "/tmp/generated_candidate.py:270: SyntaxWarning: 'return' in a 'finally' block",
            "filename": "/tmp/generated_candidate.py",
            "lineno": 270,
            "location": "/tmp/generated_candidate.py:270",
            "emitter": row["warning_records"][0]["emitter"],
            "source_resolved": True,
        }
    ]
    assert str(row["warning_records"][0]["emitter"]).startswith("raw_stream:0:")


def test_warning_ledger_runtime_capture_keeps_emitter_hint():
    with capture_python_warnings(source="with_nexus_runtime") as records:
        warnings.warn("runtime probe", SyntaxWarning)

    assert len(records) == 1
    assert records[0].source == "with_nexus_runtime"
    assert records[0].category == "SyntaxWarning"
    assert records[0].source_resolved is True
    assert "test_capability_ab_runner.py" in records[0].emitter


def test_string_literals_suppresses_candidate_parse_syntax_warning():
    code = """
def f():
    try:
        text = "safe"
    finally:
        return text
"""
    with capture_python_warnings(source="with_nexus_runtime") as records:
        literals = _string_literals(code)

    assert literals == {"safe"}
    assert records == []


def test_write_evidence_bundle_returns_when_warning_capture_missing(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {
        "mode": "with_nexus",
        "task_id": "task/warning-missing",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "status": "SUCCESS",
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "wall_duration_sec": 20.0,
        "gateway_total_sec": 20.0,
        "total_tokens": 50000,
        "model_calls": 1,
        "token_measured": True,
        "provider_token_measured": True,
        "model_token_capture_status": "measured",
        "gateway_token_source": "stats",
        "gateway_stats_present": True,
        "nexus_wearing_valid": True,
        "gemini_uses_nexus": True,
        "model_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
        "route_decision_schema_version": "nexus_route_decision_v1",
            "route_execution_policy": _route_policy(),
        "rubric_contract_status": "PASS",
    }
    without_row = {
        **with_row,
        "mode": "without_nexus",
        "status": "FAILED",
        "semantic_completed": False,
        "nexus_wearing_valid": False,
        "gemini_uses_nexus": False,
        "model_uses_nexus": False,
        "nexus_context_delivered": False,
        "nexus_usage_valid": False,
        "capability_claim_verified": False,
    }
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 1,
            "runner_command": "capability_ab_runner.py --tasks-file tasks.json",
            "hidden_verifier_mode": True,
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
            "warning_ledger_required": True,
        },
    )

    payload = json.loads(bundle.read_text(encoding="utf-8"))

    assert payload["warning_clean_gate"]["verdict"] == "RETURN"
    assert payload["warning_clean_gate"]["checks"]["warning_capture_completeness"] == 0.0
    assert payload["public_cost_efficiency_claim_gate"]["verdict"] == "RETURN"


def test_write_evidence_bundle_fails_cost_safety_when_prompt_purity_regresses(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {
        "mode": "with_nexus",
        "task_id": "task/ppi",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "status": "SUCCESS",
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "wall_duration_sec": 50.0,
        "total_tokens": 50000,
        "model_calls": 1,
        "token_measured": True,
        "provider_token_measured": True,
        "model_token_capture_status": "measured",
        "gateway_token_source": "stats",
        "gateway_stats_present": True,
        "gateway_prompt_chars": 1100,
        "nexus_wearing_valid": True,
        "gemini_uses_nexus": True,
        "model_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
        "route_decision_schema_version": "nexus_route_decision_v1",
            "route_execution_policy": _route_policy(),
    }
    without_row = {
        "mode": "without_nexus",
        "task_id": "task/ppi",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "status": "FAILED",
        "semantic_completed": False,
        "report_trust_mismatch": False,
        "wall_duration_sec": 60.0,
        "total_tokens": 60000,
        "model_calls": 1,
        "token_measured": True,
        "provider_token_measured": True,
        "model_token_capture_status": "measured",
        "gateway_token_source": "stats",
        "gateway_stats_present": True,
        "gateway_prompt_chars": 1000,
    }
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 1,
            "runner_command": "capability_ab_runner.py --tasks-file tasks.json",
            "hidden_verifier_mode": True,
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
            "prompt_purity_threshold": 1.02,
        },
    )

    payload = json.loads(bundle.read_text(encoding="utf-8"))
    checks = payload["public_cost_efficiency_claim_gate"]["checks"]
    assert checks["prompt_purity_index_max"] == 1.1
    assert checks["prompt_purity_gate_passed"] is False
    assert "prompt_purity_above_threshold" in payload["public_cost_claim_gate"]["failures"]
    assert "prompt_purity_above_threshold" in payload["public_claim_posture"]["cost_efficiency"]["reason_codes"]


def test_write_evidence_bundle_fails_gate_when_route_decision_missing(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {
        "mode": "with_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "nexus_wearing_valid": True,
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
    }
    without_row = {
        "mode": "without_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
    }
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "runner_command": "run",
            "hidden_verifier_mode": True,
        },
    )

    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert payload["public_claim_gate"]["verdict"] == "FAIL"
    assert "route_decision_missing" in payload["public_claim_gate"]["failures"]
    assert payload["public_claim_gate"]["checks"]["route_decision_present_rate"] == 0.0


def test_write_evidence_bundle_classifies_route_selected_only_high_cost_research(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {
        "mode": "with_nexus",
        "task_id": "task-research",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "token_measured": True,
        "gateway_stats_present": True,
        "nexus_wearing_valid": True,
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
        "route_decision_schema_version": "nexus_route_decision_v1",
            "route_execution_policy": _route_policy(),
        "route_profile_high_cost_selected": ["research"],
        "capability_receipts": [
            {
                "name": "research",
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": True,
                "evidence_refs": ["research:task-research:route_selected"],
            }
        ],
    }
    without_row = {
        "mode": "without_nexus",
        "task_id": "task-research",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "token_measured": True,
        "gateway_stats_present": True,
    }
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 1,
            "runner_command": "capability_ab_runner.py --tasks-file tasks.json",
            "hidden_verifier_mode": True,
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
        },
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    report = payload["route_cost_trace_report"]

    assert report["schema"] == "nexus_route_cost_trace_report_v1"
    assert report["classification_counts"] == {"route_selected_only_evidence": 1}
    trace = report["rows"][0]["high_cost_trace"][0]
    assert trace["capability"] == "research"
    assert trace["substantive_outcome_contributed"] is False


def test_write_evidence_bundle_fails_gate_when_with_token_measured_low(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {
        "mode": "with_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "token_measured": False,
        "gateway_stats_present": False,
        "nexus_wearing_valid": True,
        "model_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
        "route_decision_schema_version": "nexus_route_decision_v1",
            "route_execution_policy": _route_policy(),
    }
    without_row = {
        "mode": "without_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "token_measured": True,
        "gateway_stats_present": True,
    }
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 1,
            "runner_command": "capability_ab_runner.py --tasks-file tasks.json",
            "hidden_verifier_mode": True,
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
        },
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))

    assert payload["public_claim_gate"]["verdict"] == "FAIL"
    assert payload["public_delivery_gate"]["verdict"] == "PASS"
    assert payload["public_cost_claim_gate"]["verdict"] == "FAIL"
    assert "with_token_measured_below_threshold" in payload["public_claim_gate"]["failures"]
    assert "with_token_measured_below_threshold" in payload["public_cost_claim_gate"]["failures"]
    assert payload["public_claim_gate"]["checks"]["token_measured_rate_with"] == 0.0
    assert payload["public_cost_claim_gate"]["checks"]["cost_claim_public_safe"] is False


def test_write_evidence_bundle_fails_cost_gate_when_provider_token_source_missing(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {
        "mode": "with_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "token_measured": True,
        "token_capture_status": "measured",
        "gateway_token_source": "missing",
        "gateway_stats_present": False,
        "nexus_wearing_valid": True,
        "model_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
        "route_decision_schema_version": "nexus_route_decision_v1",
            "route_execution_policy": _route_policy(),
    }
    without_row = {
        "mode": "without_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "token_measured": True,
        "token_capture_status": "measured",
        "gateway_token_source": "usage_metadata",
        "gateway_stats_present": True,
    }
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 1,
            "runner_command": "capability_ab_runner.py --tasks-file tasks.json",
            "hidden_verifier_mode": True,
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
        },
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))

    assert payload["public_delivery_gate"]["verdict"] == "PASS"
    assert payload["public_cost_claim_gate"]["verdict"] == "FAIL"
    assert "with_provider_token_measured_below_threshold" in payload["public_cost_claim_gate"]["failures"]
    assert payload["public_claim_gate"]["checks"]["provider_token_measured_rate_with"] == 0.0
    assert payload["route_cost_ledger"]["arms"]["with_nexus"]["provider_token_source_counts"] == {"missing": 1}


def test_write_evidence_bundle_fails_cost_gate_when_outbound_ledger_dirty(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    ledger_path = tmp_path / "outbound_prompt_ledger.jsonl"
    ledger_path.write_text(
        json.dumps(
            {
                "schema": "nexus_outbound_prompt_ledger_v1",
                "provider": "gemini",
                "model_name": "gemini-3-flash-preview",
                "strict": True,
                "forbidden_literal_count": 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    base_row = {
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "token_measured": True,
        "provider_token_measured": True,
        "token_capture_status": "measured",
        "gateway_token_source": "stats",
        "gateway_stats_present": True,
        "total_tokens": 10,
        "model_calls": 1,
        "wall_duration_sec": 1.0,
    }
    with_row = {
        **base_row,
        "mode": "with_nexus",
        "nexus_wearing_valid": True,
        "model_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
        "route_decision_schema_version": "nexus_route_decision_v1",
            "route_execution_policy": _route_policy(),
    }
    without_row = {**base_row, "mode": "without_nexus"}
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={
            "repeat_trials": 1,
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "unique_tasks_requested": 1,
            "runner_command": "capability_ab_runner.py --tasks-file tasks.json",
            "hidden_verifier_mode": True,
            "outbound_prompt_ledger": str(ledger_path),
            "timeout_sec": 30,
            "total_timeout_sec": 60,
            "effective_total_timeout_sec": 60,
            "stop_loss_sec": 60,
            "per_task_stop_loss_sec": 30,
        },
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))

    assert payload["outbound_prompt_ledger_gate"]["status"] == "FAIL"
    assert payload["outbound_prompt_ledger_gate"]["record_count"] == 1
    assert "outbound_prompt_ledger_forbidden_literal" in payload["public_cost_claim_gate"]["failures"]
    assert payload["public_claim_gate"]["checks"]["outbound_prompt_ledger_forbidden_literal_count"] == 1


def test_write_evidence_bundle_v2_fails_gate_for_missing_hidden_verifier_and_trust_mismatch(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {
        "mode": "with_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "nexus_wearing_valid": True,
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
        "report_trust_mismatch": True,
    }
    without_row = {
        "mode": "without_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
    }
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={"tasks_file": "tasks.json", "tasks_manifest_hash": "abc", "runner_command": "run"},
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert payload["public_claim_gate"]["verdict"] == "FAIL"
    assert "hidden_verifier_disabled" in payload["public_claim_gate"]["failures"]
    assert "with_trust_mismatch_above_zero" in payload["public_claim_gate"]["failures"]
    assert payload["public_claim_gate"]["checks"]["trust_mismatch_free"] is False


def test_write_evidence_bundle_v2_fails_gate_when_models_differ(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {"mode": "with_nexus", "model_name": "gemini-3-flash-preview"}
    without_row = {"mode": "without_nexus", "model_name": "gemini-3.1-pro-preview"}
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={"tasks_file": "tasks.json", "tasks_manifest_hash": "abc", "runner_command": "run"},
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert payload["model_lock"]["same_model"] is False
    assert payload["public_claim_gate"]["verdict"] == "FAIL"
    assert "model_mismatch" in payload["public_claim_gate"]["failures"]


def test_write_evidence_bundle_fails_gate_for_parallel_smoke(tmp_path: Path):
    task = CapabilityTask(
        id="smoke-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="smoke",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
    )
    with_rows, without_rows = _build_parallel_smoke_rows([task], model_name="gemini-3-flash-preview")
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    write_jsonl(with_path, with_rows)
    write_jsonl(without_path, without_rows)

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[*with_rows, *without_rows],
        config={
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "runner_command": "run --parallel-arms smoke-only",
            "parallel_arms": "smoke-only",
        },
    )

    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert with_rows[0]["run_eligible"] is False
    assert with_rows[0]["infra_invalid_reason"] == "parallel_smoke"
    assert payload["public_claim_gate"]["verdict"] == "FAIL"
    assert "parallel_smoke" in payload["public_claim_gate"]["failures"]


def test_write_evidence_bundle_fails_gate_for_single_arm_run(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {"mode": "with_nexus", "model_name": "gemini-3-flash-preview", "run_eligible": True}
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row],
        config={"tasks_file": "tasks.json", "tasks_manifest_hash": "abc", "runner_command": "run --nexus-only"},
    )

    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert payload["row_counts"]["with_nexus"] == 1
    assert payload["row_counts"]["without_nexus"] == 0
    assert payload["infra_quarantine_report"]["infra_valid_pair_count"] == 0
    assert payload["infra_quarantine_report"]["infra_invalid_pair_count"] == 1
    assert payload["infra_quarantine_report"]["pairs"][0]["infra_invalid_reason_code"] == "missing_arm"
    assert payload["public_claim_gate"]["verdict"] == "FAIL"
    assert "single_arm_run" in payload["public_claim_gate"]["failures"]


def test_partial_markdown_report_explains_single_arm_run():
    out = _render_partial_markdown_report(
        benchmark_date="2026-04-30",
        with_rows=[{"mode": "with_nexus"}],
        without_rows=[],
        benchmark_summary={"with_nexus": {"total_n": 1}},
    )

    assert "Public claim gate: FAIL" in out
    assert "single-arm run" in out


def test_without_tasks_for_run_skips_bare_arm_for_nexus_only():
    task = CapabilityTask(
        id="route-smoke",
        difficulty="easy",
        task_type="bug",
        task_desc="Fix",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="all_target_tests_pass",
    )

    assert _without_tasks_for_run([task], timed_out=False, nexus_only=False) == [task]
    assert _without_tasks_for_run([task], timed_out=False, nexus_only=True) == []
    assert _without_tasks_for_run([task], timed_out=True, nexus_only=False) == []
    assert _without_tasks_for_run([task], timed_out=True, nexus_only=False, without_only=True) == [task]


def test_total_timeout_budget_helper():
    assert _budget_exceeded(0.0, 1) is True
    assert _budget_exceeded(0.0, 0) is False
    assert _remaining_leg_timeout(30, 0.0, 0) == 30
    assert _remaining_leg_timeout(30, 0.0, 1) == 1
    assert _effective_total_timeout_sec(7200, 600) == 600
    assert _effective_total_timeout_sec(0, 600) == 600
    assert _effective_total_timeout_sec(300, 600) == 300
    assert _effective_total_timeout_sec(7200, 0) == 7200


def test_emit_progress_writes_json_to_stderr(capsys):
    task = CapabilityTask(
        id="real-003",
        difficulty="hard",
        task_type="cross_module_refactor_swarm",
        task_desc="Progress",
        target_file="src.py",
        test_file="tests/test_src.py",
        success_criteria="all_target_tests_pass",
    )
    _emit_progress(enabled=True, event="task_start", mode="with_nexus", task=task, elapsed_sec=1.25)
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["event"] == "task_start"
    assert payload["mode"] == "with_nexus"
    assert payload["task_id"] == "real-003"


def test_extract_record_maps_semantic_fields():
    task = CapabilityTask(
        id="hard-001",
        difficulty="hard",
        task_type="bug",
        task_desc="Fix race",
        target_file="a.py",
        test_file="tests/test_a.py",
        success_criteria="all_target_tests_pass",
    )
    payload = {
        "status": "FAILED",
        "semantic_status": "UNVERIFIED",
        "runtime_classification": "runtime_defect",
        "route": {
            "recommended_flow": "hyper_sprint",
            "recommended_reason": "complex_bug_prefer_hyper",
            "findings_hits": 2,
            "prior_fix_hits": 2,
            "consensus": {"winner": "hyper_sprint", "votes": {"hyper_sprint": 3, "baseline": 1}},
            "route_features": {"risk_score": 87, "memory_hits": 1},
        },
        "guard": {"hit": False, "nightshift_recommended": True, "stage1_fail_signals": 1},
        "strategy": {"path": "probe_then_hyper"},
        "execution_profile": {"belief_confidence": 0.72},
        "learn_phase_slo": {"phase_slo_pass": True},
        "artifact_summary": {
            "changed": True,
            "verification_only": False,
            "diff_line_count": 12,
            "success_criteria": "artifact_changed_and_tests_pass",
            "mutation_required": True,
            "verification_only_allowed": False,
        },
        "success_criteria": {
            "name": "artifact_changed_and_tests_pass",
            "mutation_required": True,
            "verification_only_allowed": False,
        },
        "nexus_usage_trace": {
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "nexus_tier": "full",
            "nexus_tier_reason": "high_risk_or_forced_hyper",
            "gemini_patch_status": "failed",
            "nexus_rescued": True,
            "winner_source": "nexus_rescue",
            "pillars": {
                "lancedb": {"active": True, "hits": 2},
                "memory": {"active": True, "hits": 1},
                "mempalace": {"active": True, "verified": True},
                "belief": {"active": True},
                "artifact": {"active": True, "tests_passed": True},
            },
            "phase_trace": {"P": "route_built", "X": "retrieval_checked", "D": "guard_decision", "R": "hyper_executed", "A": "artifact_verified", "C": "closure_written"},
            "phase_wall_sec": {"P": 0.1, "X": 0.2, "D": 0.3, "R": 1.1, "A": 0.4, "C": 0.5},
            "capabilities": {
                "research_used": True,
                "hyper_used": True,
                "self_heal_used": True,
                "claim_verified": True,
                "failure_cause": "assertion_mismatch",
                "likely_fix": "align implementation with failing assertion",
                "recommended_escalation": {
                    "route": "judge_panel",
                    "capabilities": ["autoreason"],
                    "reason": "assertion_mismatch_needs_candidate_judgement",
                },
                "semantic_failure_escalation_required": True,
                "nightshift_recommended": False,
                "nightshift_invoked": True,
                "nightshift_recovered": False,
                "nightshift_report_path": ".nexus/reports/nightshift/run.json",
                "nightshift_failure_reason": "report_without_recovery",
                "nightshift_report": {
                    "schema_version": "nexus_nightshift_receipt_v1",
                    "failure_reason": "report_without_recovery",
                },
                "swarm_used": True,
                "swarm_evidence_count": 2,
                "swarm_consensus": "candidate_summary_evidence",
                "swarm_report": {
                    "schema_version": "nexus_swarm_receipt_v1",
                    "consensus": "candidate_summary_evidence",
                },
                "drone_used": True,
                "drone_invoked_count": 1,
                "drone_artifact_path": ".nexus/reports/drones/d1_crystal.json",
                "drone_report": {
                    "schema_version": "nexus_drone_receipt_v1",
                    "artifact_count": 1,
                },
            },
            "capability_stack": {
                "selected_capabilities": ["hyper_sprint", "autoreason"],
                "acceleration_layers": ["ddtree"],
                "governance_layers": ["ultra_review"],
                "stop_policy": {"type": "a_streak", "threshold": 2},
            },
            "autoreason": {
                "enabled": True,
                "status": "SUCCESS",
                "winner": "candidate-2",
                "stop_reason": "a_streak_met",
                "judge_votes": [{"judge": "evidence"}, {"judge": "specificity"}],
                "borda_scores": {"candidate-1": 2, "candidate-2": 4},
            },
            "ddtree": {
                "enabled": True,
                "eligible": True,
                "selected_candidate_ids": ["candidate-2"],
                "estimated_saved_steps": 2,
                "actual_saved_steps": 2,
                "reason": "deterministic_score_pruning",
            },
            "ultra_review": {
                "recommended": True,
                "invoked": True,
                "gate_passed": True,
                "report_path": ".nexus/reports/ultra_review/route_gate_report.json",
                "reason": "dry_gate_passed",
                "failures": [],
            },
            "codeintel": {
                "gate_mode": "scan_impact_required",
                "scan_report_present": True,
                "impact_report_present": True,
                "claim_bundle_present": True,
                "scan_report_path": ".nexus/reports/codeintel/scan.json",
                "impact_report_path": ".nexus/reports/codeintel/impact.json",
                "risk_score": 35,
                "impacted_files_count": 3,
                "dci_locator_present": True,
                "dci_locator_report_path": ".nexus/reports/codeintel/dci.json",
                "dci_evidence_refs": ["dci:nexus/parser.py:L1"],
                "dci_evidence_count": 1,
                "dci_coverage_score": 0.5,
                "dci_localization_score": 0.25,
            },
            "jit": {
                "ranking_mode": "static",
                "promotion_verdict": "HOLD",
                "static_default_unchanged": True,
                "miss_rate": 0.0,
                "fallback_run_rate": 0.1,
                "unmatched_path_rate": 0.0,
                "predictive_saved_runtime_sec": 12.5,
            },
            "research_preflight": {
                "schema": "nexus_research_preflight_v1",
                "present": True,
                "blocked": False,
                "requires_evidence": True,
                "decision": "requires_evidence",
                "route": {
                    "recommended_flow": "hyper_sprint",
                    "research_context": {
                        "risk_flags": ["claim_uncertainty"],
                        "blocked_assumptions": ["api_contract_not_verified"],
                    },
                },
            },
            "research_session": {
                "schema": "nexus_research_session_v1",
                "logged": True,
                "status": "keep",
                "lane": "research-runtime",
            },
            "capability_plan": {
                "schema_version": "nexus_capability_plan_v1",
                "planner_mode": "dry_run",
                "selected_capabilities": ["mempalace_gate", "artifact_gate", "claim_gate", "hyper", "autoreason"],
                "required_capabilities": ["mempalace_gate", "artifact_gate", "claim_gate"],
                "conditional_capabilities": ["hyper", "autoreason"],
                "forbidden_capabilities": [],
                "decision_trace": [{"capability": "hyper", "state": "conditional"}],
                "replan_trace": [{"phase": "P", "active_capabilities": ["hyper"]}, {"phase": "A", "active_capabilities": ["claim_gate"]}],
                "score": 18,
            },
            "route_decision": {
                "schema_version": "nexus_route_decision_v1",
                "selected_capabilities": ["mempalace_gate", "artifact_gate", "claim_gate", "hyper", "autoreason"],
                "required_capabilities": ["mempalace_gate", "artifact_gate", "claim_gate"],
                "conditional_capabilities": ["hyper", "autoreason"],
                "pending_capabilities": ["swarm"],
                "forbidden_capabilities": [],
                "misclassification_audit": {
                    "schema_version": "nexus_route_misclassification_audit_v1",
                    "contract_suffix_detected": True,
                    "task_body_used_for_lexical_signals": True,
                    "bounded_repair_profile": False,
                    "high_cost_capabilities_selected": ["ultra_review"],
                    "high_cost_selected_count": 1,
                    "suspicious_high_cost_reasons": ["high_risk_or_governance_route"],
                },
                "stop_policy": {
                    "tactical_sequence": ["hyper_sprint", "autoreason", "ddtree", "belief", "ultra_review"],
                    "tactical_tool_map": [
                        {"capability": "hyper_sprint", "evidence_required": False},
                        {"capability": "autoreason", "evidence_required": True},
                        {"capability": "ddtree", "evidence_required": True},
                        {"capability": "belief", "evidence_required": True},
                        {"capability": "ultra_review", "evidence_required": True},
                    ],
                },
                "signal_snapshot": {
                    "risk_score_0_100": 87,
                    "risk_score_0_1": 0.87,
                    "risk_band": "high",
                    "risk_band_reason": "high_risk:87",
                    "pillar_signals": {
                        "MemPalace": {"active": True},
                        "Artifact": {"active": True},
                        "Claim": {"active": True},
                    }
                },
                "forecast_gate_shadow": {
                    "schema": "nexus_forecast_gate_shadow_v1",
                    "shadow_mode": True,
                    "suggested_tier": "L3_full_governed",
                    "suggested_tier_reason": "high_risk_or_ultra_review_selected",
                    "early_exit_candidate": False,
                    "early_exit_policy": "never_skip_mempalace_artifact_claim_delivery_gates",
                },
            },
            "openseeker_alignment": {
                "schema_version": "nexus_openseeker_alignment.v1",
                "trajectory_step_count": 12,
                "evidence_hop_count": 4,
                "evidence_source_count": 3,
                "tool_action_count": 5,
                "route_tactical_tool_count": 5,
                "route_evidence_required_count": 4,
                "low_step_filtered": False,
                "long_horizon_ready": True,
            },
        },
        "timing": {
            "cli_elapsed_sec": 2.4,
            "phase_wall_sec": {"P": 0.1, "X": 0.2, "D": 0.3, "R": 1.1, "A": 0.4, "C": 0.5},
            "breakdown_sec": {
                "target_io_sec": 0.01,
                "codeintel_sec": 0.2,
                "context_pack_sec": 0.03,
                "r_hyper_sprint_sec": 0.8,
                "r_patch_apply_sec": 0.02,
                "r_total_sec": 0.85,
            },
        },
        "result": {
            "elapsed_sec": 2.3,
            "report": {
                "attempt_count": 4,
                "model_calls": 1,
                "total_tokens": 321,
                "token_capture_status": "measured",
                "gateway_total_sec": 1.2,
                "gateway_process_sec": 1.1,
                "gateway_provider_wait_sec": 1.1,
                "gateway_parse_sec": 0.1,
                "executor_selected": "inplace",
                "executor_forced_inplace": True,
                "executor_init_sec": 0.02,
            },
        },
    }
    out = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=2.5)
    assert out["task_id"] == "hard-001"
    assert out["trial_index"] == 1
    assert out["semantic_status"] == "UNVERIFIED"
    assert out["attempt_count"] == 4
    assert out["model_calls"] == 1
    assert out["total_tokens"] == 321
    assert out["token_capture_status"] == "measured"
    assert out["report_trust_mismatch"] is False
    assert out["route_risk_score"] == 87
    assert out["route_risk_score_0_100"] == 87
    assert out["route_risk_score_0_1"] == 0.87
    assert out["route_risk_band"] == "high"
    assert out["route_risk_band_reason"] == "high_risk:87"
    assert out["route_consensus_winner"] == "hyper_sprint"
    assert out["route_consensus_hyper_votes"] == 3
    assert out["route_memory_hits"] == 1
    assert out["guard_nightshift_recommended"] is True
    assert out["strategy_path"] == "probe_then_hyper"
    assert out["learn_phase_slo_pass"] is True
    assert out["artifact_changed"] is True
    assert out["artifact_verification_only"] is False
    assert out["artifact_diff_line_count"] == 12
    assert out["success_criteria"] == "artifact_changed_and_tests_pass"
    assert out["mutation_required"] is True
    assert out["verification_only_allowed"] is False
    assert out["gemini_uses_nexus"] is True
    assert out["nexus_tier"] == "full"
    assert out["nexus_tier_reason"] == "high_risk_or_forced_hyper"
    assert out["nexus_usage_valid"] is True
    assert out["nexus_rescued"] is True
    assert out["pillar_mempalace_verified"] is True
    assert out["phase_r"] == "hyper_executed"
    assert out["cli_elapsed_sec"] == 2.4
    assert out["phase_wall_total_sec"] == 2.6
    assert out["cli_uninstrumented_sec"] == 0.0
    assert out["runner_overhead_sec"] == 0.1
    assert out["timing_target_io_sec"] == 0.01
    assert out["timing_codeintel_sec"] == 0.2
    assert out["timing_context_pack_sec"] == 0.03
    assert out["r_phase_hyper_sprint_sec"] == 0.8
    assert out["r_phase_patch_apply_sec"] == 0.02
    assert out["r_phase_total_sec"] == 0.85
    assert out["gateway_total_sec"] == 1.2
    assert out["gateway_provider_wait_sec"] == 1.1
    assert out["executor_selected"] == "inplace"
    assert out["executor_forced_inplace"] is True
    assert out["executor_init_sec"] == 0.02
    assert out["phase_wall_r_sec"] == 1.1
    assert out["capability_hyper_used"] is True
    assert out["capability_claim_verified"] is True
    assert out["semantic_failure_cause"] == "assertion_mismatch"
    assert out["sensor_fusion_escalation_required"] is True
    assert out["sensor_fusion_recommended_route"] == "judge_panel"
    assert out["sensor_fusion_recommended_capabilities"] == ["autoreason"]
    assert out["sensor_fusion_unfulfilled_count"] == 0

    assert out["capability_swarm_used"] is True
    assert out["capability_swarm_evidence_count"] == 2
    assert out["capability_swarm_report_schema_version"] == "nexus_swarm_receipt_v1"
    assert out["capability_swarm_consensus"] == "candidate_summary_evidence"
    assert out["capability_drone_used"] is True
    assert out["capability_drone_invoked_count"] == 1
    assert out["capability_drone_report_schema_version"] == "nexus_drone_receipt_v1"
    assert out["capability_drone_artifact_path"] == ".nexus/reports/drones/d1_crystal.json"
    assert out["capability_nightshift_invoked"] is True
    assert out["capability_nightshift_recovered"] is False
    assert out["capability_nightshift_report_path"] == ".nexus/reports/nightshift/run.json"
    assert out["capability_nightshift_report_schema_version"] == "nexus_nightshift_receipt_v1"
    assert out["capability_nightshift_failure_reason"] == "report_without_recovery"
    assert out["capability_stack_selected"] == ["hyper_sprint", "autoreason"]
    assert out["capability_stack_acceleration_layers"] == ["ddtree"]
    assert out["capability_stack_governance_layers"] == ["ultra_review"]
    assert out["capability_stack_stop_policy_type"] == "a_streak"
    assert out["autoreason_enabled"] is True
    assert out["autoreason_status"] == "SUCCESS"
    assert out["autoreason_winner"] == "candidate-2"
    assert out["autoreason_stop_reason"] == "a_streak_met"
    assert out["autoreason_judge_votes_count"] == 2
    assert out["autoreason_borda_scores"] == {"candidate-1": 2, "candidate-2": 4}
    assert out["ddtree_enabled"] is True
    assert out["ddtree_eligible"] is True
    assert out["ddtree_selected_candidate_ids"] == ["candidate-2"]
    assert out["ddtree_actual_saved_steps"] == 2
    assert out["ddtree_reason"] == "deterministic_score_pruning"
    assert out["ultra_review_recommended"] is True
    assert out["ultra_review_invoked"] is True
    assert out["ultra_review_gate_passed"] is True
    assert out["ultra_review_report_path"] == ".nexus/reports/ultra_review/route_gate_report.json"
    assert out["ultra_review_reason"] == "dry_gate_passed"
    assert out["ultra_review_failures"] == []
    assert out["codeintel_scan_report_present"] is True
    assert out["codeintel_impact_report_present"] is True
    assert out["codeintel_claim_bundle_present"] is True
    assert out["codeintel_scan_report_path"] == ".nexus/reports/codeintel/scan.json"
    assert out["codeintel_impact_report_path"] == ".nexus/reports/codeintel/impact.json"
    assert out["codeintel_graph_index_path"] == ""
    assert out["codeintel_cache_status"] == ""
    assert out["codeintel_risk_score"] == 35
    assert out["codeintel_impacted_files_count"] == 3
    assert out["dci_locator_present"] is True
    assert out["dci_locator_report_path"] == ".nexus/reports/codeintel/dci.json"
    assert out["dci_evidence_count"] == 1
    assert out["dci_evidence_refs_json"] == '["dci:nexus/parser.py:L1"]'
    assert out["dci_coverage_score"] == 0.5
    assert out["dci_localization_score"] == 0.25
    assert out["jit_ranking_mode"] == "static"
    assert out["jit_promotion_verdict"] == "HOLD"
    assert out["jit_predictive_saved_runtime_sec"] == 12.5
    assert out["research_preflight_present"] is True
    assert out["research_preflight_requires_evidence"] is True
    assert out["research_preflight_blocked"] is False
    assert out["claim_uncertainty"] is True
    assert out["research_session_logged"] is True
    assert out["research_session_status"] == "keep"
    assert out["research_session_lane"] == "research-runtime"
    assert out["capability_plan_trace_present"] is True
    assert out["capability_plan_schema_version"] == "nexus_capability_plan_v1"
    assert out["capability_plan_mode"] == "dry_run"
    assert out["capability_plan_score"] == 18
    assert out["capability_plan_node_count"] == 1
    assert out["capability_plan_required"] == ["mempalace_gate", "artifact_gate", "claim_gate"]
    assert out["capability_plan_conditional"] == ["hyper", "autoreason"]
    assert out["capability_plan_phases"] == ["P", "A"]
    assert out["route_decision_schema_version"] == "nexus_route_decision_v1"
    assert out["route_decision_selected_count"] == 5
    assert out["route_decision_required_count"] == 3
    assert out["route_decision_conditional_count"] == 2
    assert out["route_decision_pending"] == ["swarm"]
    assert out["route_profile_contract_suffix_detected"] is True
    assert out["route_profile_task_body_normalized"] is True
    assert out["route_profile_bounded_repair"] is False
    assert out["route_profile_high_cost_selected"] == ["ultra_review"]
    assert out["route_profile_high_cost_selected_count"] == 1
    assert out["route_profile_suspicious_high_cost_reasons"] == ["high_risk_or_governance_route"]
    assert out["route_tactical_sequence"] == ["hyper_sprint", "autoreason", "ddtree", "belief", "ultra_review"]
    assert json.loads(out["route_tactical_tool_map_json"])[1]["capability"] == "autoreason"
    assert out["forecast_gate_shadow_schema"] == "nexus_forecast_gate_shadow_v1"
    assert out["forecast_gate_shadow_mode"] is True
    assert out["forecast_gate_suggested_tier"] == "L3_full_governed"
    assert out["forecast_gate_early_exit_candidate"] is False
    assert out["forecast_gate_early_exit_policy"] == "never_skip_mempalace_artifact_claim_delivery_gates"
    assert out["route_decision_pillars_active"] == ["MemPalace", "Artifact", "Claim"]
    assert out["openseeker_schema_version"] == "nexus_openseeker_alignment.v1"
    assert out["trajectory_step_count"] == 12
    assert out["evidence_hop_count"] == 4
    assert out["evidence_source_count"] == 3
    assert out["tool_action_count"] == 5
    assert out["route_tactical_tool_count"] == 5
    assert out["route_evidence_required_count"] == 4
    assert out["low_step_filtered"] is False
    assert out["long_horizon_ready"] is True
    assert out["semantic_completed"] is False
    assert out["nexus_pillars_observed"] == ["lancedb", "memory", "mempalace", "belief", "artifact"]
    assert out["nexus_phases_observed"] == ["P", "X", "D", "R", "A", "C"]


def test_extract_record_surfaces_unfulfilled_sensor_fusion_recommendation():
    task = CapabilityTask(
        id="sensor-unfulfilled",
        difficulty="hard",
        task_type="public_test_repair",
        task_desc="Expected semantic failure sensor escalation",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
    )
    payload = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "capabilities": {
                "sensor_fusion_decision": {
                    "schema_version": "nexus_sensor_fusion_decision.v1",
                    "phase": "R",
                    "current_route": "hyper_sprint",
                    "failure_cause": "assertion_mismatch",
                    "escalation_required": True,
                    "recommended_route": "judge_panel",
                    "recommended_capabilities": ["autoreason"],
                    "reason": "assertion_mismatch_needs_candidate_judgement",
                    "inputs": {"semantic_failure_sensor": True},
                },
            },
            "autoreason": {
                "enabled": False,
                "status": "SKIPPED",
                "stop_reason": "candidate_summaries_missing",
            },
            "capability_receipts": [
                {
                    "name": "semantic_failure_sensor",
                    "selected": True,
                    "invoked": True,
                    "evidence_present": True,
                    "gate_passed": True,
                    "outcome_contributed": True,
                    "public_claim_safe": True,
                    "evidence_refs": ["sensor:assertion_mismatch"],
                }
            ],
        },
        "result": {"report": {"model_calls": 1, "total_tokens": 10, "token_capture_status": "measured"}},
    }

    out = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=1.0)

    assert out["sensor_fusion_unfulfilled_count"] == 1
    assert out["sensor_fusion_unfulfilled_recommendations"] == [
        {"capability": "autoreason", "reason": "candidate_summaries_missing"}
    ]


def test_nexus_cli_subprocess_cmd_can_bypass_uv_for_sandboxed_bench(monkeypatch):
    monkeypatch.setenv("NEXUS_BENCH_SUBPROCESS_PYTHON", ".venv/bin/python")

    assert _nexus_cli_subprocess_cmd(["task", "--json"]) == [
        ".venv/bin/python",
        "scripts/engine/nexus_cli.py",
        "task",
        "--json",
    ]


def test_extract_record_summarizes_child_and_parent_timing_gaps():
    task = CapabilityTask(
        id="timing-001",
        difficulty="hard",
        task_type="bug",
        task_desc="Fix timing",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="all_target_tests_pass",
    )
    payload = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "timing": {
            "cli_elapsed_sec": 10.0,
            "phase_wall_sec": {"P": 1.0, "X": 2.0, "D": 0.5, "R": 1.5, "A": 2.0, "C": 1.0},
            "breakdown_sec": {"target_io_sec": 0.2, "codeintel_sec": 1.7, "context_pack_sec": 0.1},
        },
        "result": {"elapsed_sec": 10.0, "report": {"model_calls": 0, "total_tokens": 0}},
    }

    out = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=12.5)

    assert out["phase_wall_total_sec"] == 8.0
    assert out["cli_uninstrumented_sec"] == 2.0
    assert out["runner_overhead_sec"] == 2.5
    assert out["model_attempt_wall_sec"] == 12.5
    assert out["model_attempt_runner_overhead_sec"] == 2.5
    assert out["model_attempt_runner_overhead_polluted"] is False
    assert out["timing_target_io_sec"] == 0.2
    assert out["timing_codeintel_sec"] == 1.7
    assert out["timing_context_pack_sec"] == 0.1


def test_extract_record_summarizes_rlm_trace_quality(tmp_path: Path):
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "task_id": "t",
                        "phase": "R",
                        "iteration_id": "r-1",
                        "action_type": "submit",
                        "stop_reason": "submit",
                        "confidence": 0.75,
                        "allowed_tools": ["read_file", "safe_patch"],
                        "artifact_refs": ["patch.diff"],
                    }
                ),
                json.dumps(
                    {
                        "task_id": "t",
                        "phase": "A",
                        "iteration_id": "a-1",
                        "action_type": "audit",
                        "stop_reason": "verified",
                        "confidence": 1.0,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    task = CapabilityTask(
        id="rlm-001",
        difficulty="hard",
        task_type="bug",
        task_desc="Fix with RLM",
        target_file="a.py",
        test_file="tests/test_a.py",
        success_criteria="patch_and_tests_pass",
    )
    payload = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "rlm_trace_path": str(trace_path),
            "rlm_loop_phase": "X",
            "rlm_x_loop_budget_observed": True,
            "rlm_required_gates": ["rlm_trace_present", "x_loop_budget_observed"],
        },
    }

    out = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=1.0)

    assert out["rlm_trace_present"] is True
    assert out["rlm_iteration_count"] == 2
    assert out["rlm_submit_count"] == 1
    assert out["rlm_verified_count"] == 1
    assert out["rlm_allowed_tools_count"] == 2
    assert out["rlm_avg_confidence"] == 0.875
    assert out["rlm_evidence_density"] == 0.5
    assert out["rlm_trace_quality_score"] == 100
    assert out["rlm_loop_phase"] == "X"
    assert out["rlm_x_loop_budget_observed"] is True
    assert out["rlm_required_gates"] == ["rlm_trace_present", "x_loop_budget_observed"]


def test_summarize_rlm_trace_marks_missing_trace():
    summary = _summarize_rlm_trace("/tmp/nexus/missing-rlm-trace.jsonl")

    assert summary["rlm_iteration_count"] == 0
    assert summary["rlm_stop_reasons"] == ["trace_missing"]


def test_extract_record_treats_patch_and_tests_pass_as_mutation_required():
    task = CapabilityTask(
        id="pub-001",
        difficulty="medium",
        task_type="public_bugfix",
        task_desc="Fix public task",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
    )
    out = _extract_record(
        mode="with_nexus",
        task=task,
        payload={"status": "SUCCESS", "semantic_status": "VERIFIED", "artifact_summary": {"changed": True}},
        wall_time_sec=1.0,
    )
    assert out["success_criteria"] == "patch_and_tests_pass"
    assert out["mutation_required"] is True
    assert out["verification_only_allowed"] is False


def test_timeout_payload_preserves_stage_and_partial_output():
    task = CapabilityTask(
        id="pub-timeout",
        difficulty="medium",
        task_type="public_refactor",
        task_desc="Replay timeout",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
    )
    payload = _with_nexus_timeout_payload(task=task, timeout_sec=7)
    out = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=7.2)
    assert out["runtime_classification"] == "subprocess_timeout"
    assert out["timeout_scope"] == "with_nexus_subprocess"
    assert out["timeout_stage"] == "timeout_before_receipt"
    assert out["timeout_sec"] == 7
    assert out["model_calls"] == 0
    assert out["gemini_uses_nexus"] is True


def test_with_nexus_timeout_payload_emits_expected_failclosed_receipts():
    task = CapabilityTask(
        id="docs-timeout",
        difficulty="hard",
        task_type="public_docs_code_sync",
        task_desc="Sync docs",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
        expected_capabilities=("codeintel", "memory", "delivery_gate"),
        eligibility_class="model_required",
    )

    payload = _with_nexus_timeout_payload(task=task, timeout_sec=210)
    out = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=210.2)

    assert out["runtime_classification"] == "subprocess_timeout"
    assert out["timeout_scope"] == "with_nexus_subprocess"
    assert out["timeout_stage"] == "timeout_before_receipt"
    assert out["infra_invalid_reason"] == "timeout_before_receipt"
    receipt_by_name = {item["name"]: item for item in out["capability_receipts"]}
    assert {"codeintel", "memory", "delivery_gate"} <= set(receipt_by_name)
    for name in ("codeintel", "memory", "delivery_gate"):
        receipt = receipt_by_name[name]
        assert receipt["selected"] is True
        assert receipt["invoked"] is False
        assert receipt["gate_passed"] is False
        assert receipt["public_claim_safe"] is False
        assert receipt["synthetic_timeout_receipt"] is True
        assert receipt["failure_reason"] == "timeout_before_receipt"
    assert out["expected_capability_invocation_coverage"]["failure_reasons"] == {
        "codeintel": "not_invoked",
        "memory": "not_invoked",
        "delivery_gate": "not_invoked",
    }
    assert out["model_uplift_eligible"] is False


def test_tail_text_decodes_bytes_and_limits_output():
    assert _tail_text(b"abc") == "abc"
    assert _tail_text("abcdef", max_chars=3) == "def"


def test_classify_timeout_stage_from_partial_output():
    assert _classify_timeout_stage("running pytest", "") == "timeout_during_artifact_verify"
    assert _classify_timeout_stage("Gemini model call started", "") == "timeout_during_gemini"
    assert _classify_timeout_stage("", "MemoryService auto-init skipped\n[Gateway] Dynamic timeout") == "timeout_during_gemini"
    assert _classify_timeout_stage("hyper sprint candidate", "") == "timeout_during_hyper"
    assert _classify_timeout_stage("", "MemoryService auto-init warning: Table 'policy' already exists") == "timeout_during_memory_bootstrap"
    assert _classify_timeout_stage("", "") == "timeout_before_receipt"


def test_benchmark_memory_db_path_is_per_task_trial(tmp_path: Path):
    task = CapabilityTask(
        id="pub/test:002",
        difficulty="medium",
        task_type="public_bugfix",
        task_desc="Fix public task",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
        trial_index=3,
    )
    path = _benchmark_memory_db_path(tmp_path, task, 123.456)
    assert path == tmp_path / ".nexus" / "reports" / "bench_runtime" / "memory" / "pub_test_002_trial3_123456"


def test_extract_json_payload_from_prefixed_output():
    raw = """Redis init failed
Memory warning
{
  "status": "SUCCESS",
  "semantic_status": "VERIFIED"
}"""
    payload = _extract_json_payload(raw)
    assert payload["status"] == "SUCCESS"
    assert payload["semantic_status"] == "VERIFIED"


def test_extract_json_payload_tolerates_trailing_warning():
    raw = """pytest failure context with {'result': 'ok'}
{"status":"SUCCESS","semantic_status":"VERIFIED"}
<unknown>:270: SyntaxWarning: 'return' in a 'finally' block
"""

    payload = _extract_json_payload(raw)

    assert payload["status"] == "SUCCESS"
    assert payload["semantic_status"] == "VERIFIED"


def test_extract_json_payload_tolerates_trailing_logs_after_full_payload():
    raw = """prefix {not json}
{"schema_version":"1.0","status":"SUCCESS","command_name":"research:auto-flow","result":{"status":"SUCCESS"},"timing":{"cli_elapsed_sec":1.2}}
learning closure wrote: {"status":"keep"}
"""

    payload = _extract_json_payload(raw)

    assert payload["status"] == "SUCCESS"
    assert payload["command_name"] == "research:auto-flow"
    assert payload["result"]["status"] == "SUCCESS"


def test_select_tasks_balances_buckets_for_all_mode():
    tasks = [
        CapabilityTask(id="easy-1", difficulty="easy", task_type="bug", task_desc="e1", target_file="a", test_file="b", success_criteria="x"),
        CapabilityTask(id="easy-2", difficulty="easy", task_type="bug", task_desc="e2", target_file="a", test_file="b", success_criteria="x"),
        CapabilityTask(id="medium-1", difficulty="medium", task_type="bug", task_desc="m1", target_file="a", test_file="b", success_criteria="x"),
        CapabilityTask(id="medium-2", difficulty="medium", task_type="bug", task_desc="m2", target_file="a", test_file="b", success_criteria="x"),
        CapabilityTask(id="hard-1", difficulty="hard", task_type="bug", task_desc="h1", target_file="a", test_file="b", success_criteria="x"),
        CapabilityTask(id="hard-2", difficulty="hard", task_type="bug", task_desc="h2", target_file="a", test_file="b", success_criteria="x"),
    ]
    selected = select_tasks(tasks, difficulty="all", max_tasks=6)
    assert [task.id for task in selected] == ["easy-1", "medium-1", "hard-1", "easy-2", "medium-2", "hard-2"]


def test_filter_tasks_by_repo_kind_allows_non_external_subset():
    tasks = [
        CapabilityTask(id="a", difficulty="medium", task_type="bug", task_desc="a", target_file="a", test_file="a", success_criteria="x", repo_kind="neutral_fixture"),
        CapabilityTask(id="b", difficulty="hard", task_type="bug", task_desc="b", target_file="b", test_file="b", success_criteria="x", repo_kind="external"),
        CapabilityTask(id="c", difficulty="hard", task_type="bug", task_desc="c", target_file="c", test_file="c", success_criteria="x", repo_kind="nexus_internal"),
    ]
    assert [task.id for task in filter_tasks_by_repo_kind(tasks, "neutral_fixture,nexus_internal")] == ["a", "c"]


def test_filter_tasks_by_id_allows_targeted_replay():
    tasks = [
        CapabilityTask(id="a", difficulty="medium", task_type="bug", task_desc="a", target_file="a", test_file="a", success_criteria="x"),
        CapabilityTask(id="b", difficulty="hard", task_type="bug", task_desc="b", target_file="b", test_file="b", success_criteria="x"),
    ]
    assert [task.id for task in filter_tasks_by_id(tasks, "b")] == ["b"]
    assert [task.id for task in filter_tasks_by_id(tasks, "all")] == ["a", "b"]


def test_expand_task_trials_preserves_fixture_kind():
    task = CapabilityTask(
        id="nexus-value-hidden-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix hidden state",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_hidden_state",
        expected_capabilities=("claim_gate", "delivery_gate"),
        capability_activation_contract="required",
        hidden_oracle_kind="pytest_hidden",
        cost_budget={"max_model_calls": 3},
        token_budget=123,
        wall_time_budget_sec=45.0,
        public_claim_allowed_metrics=("verified_delivery_rate",),
    )

    expanded = expand_task_trials([task], repeat_trials=2, shuffle_seed=None)

    assert [item.trial_index for item in expanded] == [1, 2]
    assert {item.fixture_kind for item in expanded} == {"nexus_value_hidden_state"}
    assert {item.expected_capabilities for item in expanded} == {("claim_gate", "delivery_gate")}
    assert {item.capability_activation_contract for item in expanded} == {"required"}
    assert {item.hidden_oracle_kind for item in expanded} == {"pytest_hidden"}
    assert {item.cost_budget["max_model_calls"] for item in expanded if item.cost_budget} == {3}
    assert {item.token_budget for item in expanded} == {123}
    assert {item.wall_time_budget_sec for item in expanded} == {45.0}
    assert {item.public_claim_allowed_metrics for item in expanded} == {("verified_delivery_rate",)}


def test_run_without_nexus_bare_mode_returns_record(tmp_path: Path):
    task = CapabilityTask(
        id="easy-001",
        difficulty="easy",
        task_type="bug",
        task_desc="Fix text normalization",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        mode="bare",
    )
    assert out["mode"] == "without_nexus"
    assert out["semantic_status"] is None
    assert out["attempt_count"] == 1
    assert out["model_calls"] == 0
    assert out["total_tokens"] == 0
    assert out["token_capture_status"] == "not_applicable_local_only"


def test_run_without_nexus_bare_mode_hard_task_runs_verify_only(tmp_path: Path):
    task = CapabilityTask(
        id="hard-001",
        difficulty="hard",
        task_type="bug",
        task_desc="Fix flaky timeout race",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        mode="bare",
    )
    assert out["status"] == "FAILED"


def test_run_with_nexus_enables_llm_mode_for_hard_tasks(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="hard-001",
        difficulty="hard",
        task_type="bug",
        task_desc="Fix flaky timeout race",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    captured = {"args": []}

    class _InvokeRes:
        def __init__(self):
            self.output = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":0,"total_tokens":0,"token_capture_status":"not_applicable_local_only"}}}'

    def fake_invoke(_self, _cli, args, **_kwargs):
        captured["args"] = list(args)
        return _InvokeRes()

    monkeypatch.setattr("click.testing.CliRunner.invoke", fake_invoke)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="inprocess",
        with_llm_mode="hard",
    )
    assert "--llm-mode" in captured["args"]
    assert out["semantic_status"] == "VERIFIED"


def test_run_with_nexus_codex_provider_delivers_nexus_context(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="codex-nexus-001",
        difficulty="easy",
        task_type="public_bugfix",
        task_desc="Fix evidence-backed normalization repair.",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_codex_patch(*, prompt, timeout_sec):
        assert "You are Codex wearing Nexus" in prompt
        assert "NEXUS_BENCH_SESSION_BOUNDARY_V1 task_id=codex-nexus-001 trial_index=1" in prompt
        assert "[NEXUS ROUTE SUMMARY]" in prompt
        assert "[NEXUS CODEINTEL SUMMARY]" in prompt
        assert "[NEXUS EXECUTION PROFILE]" in prompt
        assert "[NEXUS HIDDEN-VERIFIER GUIDANCE]" in prompt
        assert "capability_stack" not in prompt
        return (
            {
                "patch": "def normalize_flag(text: str) -> str:\n    return text.strip().lower()\n",
                "tokens_used": 200,
                "token_capture_status": "measured",
                "model_name": "gpt-5.5",
                "model_patch_generated": True,
                "gateway_stats_present": True,
                "gateway_token_source": "codex_stdout",
            },
            "",
        )

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_codex_patch", fake_ask_direct_codex_patch)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="inprocess",
        with_llm_mode="all",
        with_model_provider="codex",
    )

    assert out["status"] == "SUCCESS"
    assert out["provider"] == "codex"
    assert out["model_name"] == "gpt-5.5"
    assert out["reset_boundary_hash"]
    assert "reason_codes" in out["route_execution_policy"]
    assert out["prompt_purity_index"] == 1.0
    assert out["prompt_nexus_control_chars"] > 0
    assert out["prompt_governance_contract_chars"] > 0
    assert out["gemini_uses_nexus"] is True
    assert out["nexus_context_delivered"] is True
    assert set(out["nexus_pillars_observed"]) == {"lancedb", "memory", "mempalace", "belief", "artifact"}
    assert set(out["nexus_phases_observed"]) == {"P", "X", "D", "R", "A", "C"}
    assert out["nexus_wearing_valid"] is True
    assert out["nexus_usage_valid"] is True
    assert out["capability_claim_verified"] is True
    assert out["codeintel_scan_report_present"] is True
    assert any(item["name"] == "codeintel" and item["gate_passed"] for item in out["capability_receipts"])
    receipts = {item["name"]: item for item in out["capability_receipts"]}
    assert "autoreason" not in receipts
    assert "ddtree" not in receipts
    assert "ultra_review" not in receipts
    assert receipts["artifact_gate"]["gate_passed"] is True
    assert receipts["claim_gate"]["gate_passed"] is True
    assert receipts["delivery_gate"]["gate_passed"] is True
    assert receipts["mempalace_gate"]["gate_passed"] is True
    assert out["research_preflight_present"] is True
    assert out["research_preflight_requires_evidence"] is True
    assert out["research_session_logged"] is True
    assert out["research_session_lane"] == "codex-runtime"
    assert out["claim_probe_invoked"] is True
    assert out["claim_probe_gate_passed"] is True
    assert out["nexus_failure_status"] == "PASS"
    assert out["pillar_belief_active"] is True
    assert out["pillar_memory_active"] is True
    assert out["ultra_review_invoked"] is False
    assert out["ultra_review_gate_passed"] is False
    assert out["capability_receipts_json"]
    assert out["gateway_stats_present"] is True
    assert out["gateway_token_source"] == "codex_stdout"
    assert out["gateway_prompt_chars"] > 0


def test_codex_patch_redacts_sanitized_runner_path_before_ledger(tmp_path: Path, monkeypatch):
    runner_root = "/private/tmp/nexus-live-clean-runner-test"
    ledger_path = tmp_path / "outbound.jsonl"
    monkeypatch.setenv("NEXUS_OUTBOUND_PROMPT_STRICT", "1")
    monkeypatch.setenv("NEXUS_OUTBOUND_PROMPT_LEDGER", str(ledger_path))
    monkeypatch.setenv("NEXUS_OUTBOUND_FORBIDDEN_LITERALS", runner_root)
    monkeypatch.setenv("NEXUS_CODEX_EXEC_CWD", runner_root)
    monkeypatch.setenv("NEXUS_CODEX_MODEL_NAME", "gpt-5.5")
    monkeypatch.delenv("NEXUS_CODEX_SESSION_WORKER", raising=False)
    monkeypatch.setattr(capability_ab_runner.shutil, "which", lambda name: "/bin/echo" if name == "codex" else None)

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text('{"status":"SUCCESS","patch":"def ok():\\n    return True\\n"}', encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="tokens used 12", stderr="")

    monkeypatch.setattr(capability_ab_runner, "_run_process_group", fake_run_process_group)

    payload, _ = _ask_direct_codex_patch(prompt=f"inspect {runner_root}/target.py", timeout_sec=10)

    assert payload["status"] == "SUCCESS"
    record = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert record["forbidden_literal_count"] == 0


def test_external_model_name_for_provider_uses_codex_env(monkeypatch):
    monkeypatch.delenv("NEXUS_GEMINI_MODEL_NAME", raising=False)
    monkeypatch.setenv("NEXUS_CODEX_MODEL_NAME", "gpt-5.5")

    assert _external_model_name_for_provider("codex") == "gpt-5.5"


def test_compact_nexus_route_for_prompt_excludes_verbose_payload():
    route = {
        "recommended_flow": "hyper_sprint",
        "recommended_reason": "commercial_public_task_prefers_hyper",
        "findings_hits": 2,
        "route_features": {"risk_score": 55, "has_hard_signal": True, "memory_hits": 1},
        "route_decision": {
            "selected_capabilities": ["research", "hyper", "ultra_review"],
            "governance_layers": ["ultra_review"],
            "acceleration_layers": [],
            "decision_trace": [{"node": "verbose"}],
        },
        "capability_stack": {"selected_capabilities": ["legacy-only"]},
        "explain_payload": {"reasoning": "large"},
    }

    compact = _compact_nexus_route_for_prompt(route)

    assert compact["recommended_flow"] == "hyper_sprint"
    assert compact["routing_evidence_status"] == "route_decision_present"
    assert compact["risk_score"] == 55
    assert compact["selected_capabilities"] == ["research", "hyper", "ultra_review"]
    assert compact["governance_layers"] == ["ultra_review"]
    assert "decision_trace" not in compact
    assert "explain_payload" not in compact


def test_compact_nexus_route_for_prompt_does_not_fallback_to_capability_stack():
    route = {
        "recommended_flow": "baseline",
        "capability_stack": {
            "selected_capabilities": ["hyper_sprint", "autoreason"],
            "acceleration_layers": ["ddtree"],
            "governance_layers": ["ultra_review"],
        },
    }

    compact = _compact_nexus_route_for_prompt(route)

    assert compact["routing_evidence_status"] == "missing_route_decision"
    assert compact["selected_capabilities"] == []
    assert compact["governance_layers"] == []
    assert compact["acceleration_layers"] == []


def test_nexus_codex_hidden_verifier_guidance_names_merge_invariant():
    task = CapabilityTask(
        id="repair",
        difficulty="hard",
        task_type="public_test_repair",
        task_desc="Repair merge helper.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )

    guidance = _nexus_codex_hidden_verifier_guidance(
        task,
        "def merge_limits(defaults, override):\n    result.update(override or {})\n",
    )

    assert "Visible tests are acceptance hints" in guidance
    assert "preserve caller-owned inputs" in guidance
    assert "ignore override values that are None" in guidance


def test_nexus_codex_hidden_verifier_guidance_names_context_contracts():
    timeout_task = CapabilityTask(
        id="timeout",
        difficulty="hard",
        task_type="public_test_repair",
        task_desc="Repair a flaky-looking timeout calculation.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    response_task = CapabilityTask(
        id="response",
        difficulty="hard",
        task_type="public_docs_code_sync",
        task_desc="Sync code and docs after a renamed public field.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    config_task = CapabilityTask(
        id="config",
        difficulty="hard",
        task_type="public_docs_code_sync",
        task_desc="Sync configuration docs and strict parser defaults.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )

    assert "clamp the result" in _nexus_codex_hidden_verifier_guidance(timeout_task, "def remaining_ms(): pass")
    assert "canonical output field is result" in _nexus_codex_hidden_verifier_guidance(response_task, "def build_response(): pass")
    assert "strict=True and retries=3" in _nexus_codex_hidden_verifier_guidance(config_task, "def parse_config(data): pass")


def test_nexus_codex_hidden_verifier_guidance_names_belief_budget_contract():
    task = CapabilityTask(
        id="belief",
        category="bugfix",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix repair budget selection so low confidence and high risk require extra evidence-gathering rounds.",
        target_file="target.py",
        test_file="test_target.py",
        fixture_kind="rlm_harder_v2_belief_budget",
        success_criteria="patch_and_tests_pass",
    )

    guidance = _nexus_codex_hidden_verifier_guidance(task, "def rlm_harder_v2_repair_budget(confidence, risk): pass")

    assert "confidence is low or uncertain" in guidance
    assert "risk is elevated" in guidance


def test_nexus_codex_hidden_verifier_guidance_names_governance_contracts():
    guard_task = CapabilityTask(
        id="guard",
        category="ops_research",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Tighten an action filter so unsafe operations are rejected while ordinary read-only work remains allowed.",
        target_file="target.py",
        test_file="test_target.py",
        fixture_kind="rlm_harder_v2_governance_guard",
        success_criteria="patch_and_tests_pass",
    )
    scope_task = CapabilityTask(
        id="scope",
        category="ops_research",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix scope enforcement so unapproved mutating operations are blocked while read-only inspection remains allowed.",
        target_file="target.py",
        test_file="test_target.py",
        fixture_kind="rlm_harder_v2_governance_scope",
        success_criteria="patch_and_tests_pass",
    )

    assert "reason governance_block" in _nexus_codex_hidden_verifier_guidance(guard_task, "def rlm_harder_v2_filter_action(action): pass")
    assert "reason scope_block" in _nexus_codex_hidden_verifier_guidance(scope_task, "def rlm_harder_v2_scope_decision(request): pass")


def test_nexus_codex_hidden_verifier_guidance_names_secret_redaction_contract():
    task = CapabilityTask(
        id="nexus-value-gov-001",
        difficulty="hard",
        task_type="public_refactor",
        task_desc="Refactor a credential scrubber while preserving the governance boundary.",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
        fixture_kind="nexus_value_mempalace_secret_redaction",
    )

    guidance = _nexus_codex_hidden_verifier_guidance(task, "def redact(record): pass")

    assert "redact token, password, secret, api_key" in guidance
    assert "'[REDACTED]'" in guidance


def test_nexus_codex_hidden_verifier_guidance_names_replay_contract():
    task = CapabilityTask(
        id="replay",
        category="feature",
        difficulty="hard",
        task_type="public_feature",
        task_desc="Fix replay evidence receipts.",
        target_file="target.py",
        test_file="test_target.py",
        fixture_kind="rlm_harder_v2_evidence_replay",
        success_criteria="patch_and_tests_pass",
    )

    guidance = _nexus_codex_hidden_verifier_guidance(task, "def rlm_harder_v2_accept_receipt(receipt): pass")

    assert "non-empty replay_command" in guidance
    assert "exit_code == 0" in guidance
    assert "schema aliases" in guidance


def test_nexus_codex_hidden_verifier_guidance_names_nightshift_report_contract():
    task = CapabilityTask(
        id="nightshift",
        category="ops_research",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Accept Nightshift recovery only when escalation was invoked, recovered, and produced a report path.",
        target_file="target.py",
        test_file="test_target.py",
        fixture_kind="rlm_harder_v2_nightshift_recovery",
        success_criteria="patch_and_tests_pass",
    )

    guidance = _nexus_codex_hidden_verifier_guidance(task, "def rlm_harder_v2_accept_nightshift(report): pass")

    assert "non-empty report_path" in guidance
    assert "reject boolean-only recovery" in guidance


def test_run_with_nexus_augments_rlm_evidence_task_desc(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="rlm-harder-v2-evidence-001",
        difficulty="hard",
        task_type="public_feature",
        task_desc="Fix claim verification so only fully supported successful claims are accepted.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="rlm_harder_v2_evidence_gap",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {"args": []}

    class _InvokeRes:
        output = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"total_tokens":10,"token_capture_status":"measured"}}}'

    def fake_invoke(_self, _cli, args, **_kwargs):
        captured["args"] = list(args)
        return _InvokeRes()

    monkeypatch.setattr("click.testing.CliRunner.invoke", fake_invoke)

    run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="inprocess",
        with_llm_mode="all",
    )

    task_desc = captured["args"][captured["args"].index("--task-desc") + 1]
    assert "Nexus wearing contract" in task_desc
    assert "MemPalace: keep the solution inside the task scope" in task_desc
    assert "Belief: when evidence is incomplete" in task_desc
    assert "Nexus Artifact/Claim rule" in task_desc
    assert "artifact" in task_desc


def test_nexus_task_desc_adds_pillar_specific_rules():
    governance = CapabilityTask(
        id="gov",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix scope enforcement.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_governance_guard",
    )
    scope = CapabilityTask(
        id="scope",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix scope enforcement.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_governance_scope",
    )
    memory = CapabilityTask(
        id="memory",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix memory relevance.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_memory_contract",
    )
    belief = CapabilityTask(
        id="belief",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix belief budget.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_belief_budget",
    )
    replay = CapabilityTask(
        id="replay",
        difficulty="hard",
        task_type="public_feature",
        task_desc="Fix replay evidence.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_evidence_replay",
    )
    evidence = CapabilityTask(
        id="evidence",
        difficulty="hard",
        task_type="public_feature",
        task_desc="Fix claim verification.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_evidence_gap",
    )

    assert "Nexus MemPalace rule" in _nexus_task_desc(governance)
    assert "reason governance_block" in _nexus_task_desc(governance)
    assert "delete_file" in _nexus_task_desc(governance)
    assert "logs/" in _nexus_task_desc(governance)
    assert "benchmarks/" in _nexus_task_desc(governance)
    assert "Decision table for rlm_harder_v2_filter_action" in _nexus_task_desc(governance)
    assert "return exactly {'allowed': False, 'reason': 'governance_block'}" in _nexus_task_desc(governance)
    assert "Do not allow-by-default" in _nexus_task_desc(governance)
    assert "Nexus scope enforcement rule" in _nexus_task_desc(scope)
    assert "reason scope_block" in _nexus_task_desc(scope)
    assert "Decision table for rlm_harder_v2_scope_decision" in _nexus_task_desc(scope)
    assert "return exactly {'allowed': True, 'reason': 'read_only'}" in _nexus_task_desc(scope)
    assert "Do not default_allow" in _nexus_task_desc(scope)
    assert "Nexus Belief/Memory rule" in _nexus_task_desc(memory)
    assert "Nexus Belief budget rule" in _nexus_task_desc(belief)
    assert "{'rounds': 3, 'needs_evidence': True}" not in _nexus_task_desc(belief)
    assert "Decision table for rlm_harder_v2_verified_claims" in _nexus_task_desc(evidence)
    assert "artifact'] is a non-empty string" in _nexus_task_desc(evidence)
    assert "Preserve input order" in _nexus_task_desc(evidence)
    assert "Nexus replay evidence rule" in _nexus_task_desc(replay)
    assert "non-empty replay_command" in _nexus_task_desc(replay)
    assert "exit_code == 0" in _nexus_task_desc(replay)
    assert "schema aliases" in _nexus_task_desc(replay)
    assert "Decision table for rlm_harder_v2_accept_receipt" in _nexus_task_desc(replay)
    assert "do not treat aliases as exit_code" in _nexus_task_desc(replay)

    nightshift = CapabilityTask(
        id="nightshift",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix Nightshift recovery.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_nightshift_recovery",
    )

    assert "Nexus Nightshift recovery rule" in _nexus_task_desc(nightshift)
    assert "non-empty report_path" in _nexus_task_desc(nightshift)


def test_prompt_leak_audit_accepts_current_rlm_harder_v2_guidance():
    tasks = load_tasks("scripts/bench/public_benchmark_rlm_harder_v2.json")

    failures = _prompt_leak_audit_failures(tasks, repo_root=Path.cwd())

    assert failures == []


def test_prompt_leak_audit_blocks_hidden_only_literals(monkeypatch):
    task = next(
        task
        for task in load_tasks("scripts/bench/public_benchmark_rlm_harder_v2.json")
        if task.fixture_kind == "rlm_harder_v2_evidence_replay"
    )
    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner._nexus_task_desc",
        lambda _task: "Use replay_exit_code to solve the hidden case.",
    )

    failures = _prompt_leak_audit_failures([task], repo_root=Path.cwd())

    assert failures == ["prompt_leak:rlm-harder-v2-evidence-002:replay_exit_code"]


def test_prompt_leak_literal_ignores_generic_snake_case_status():
    assert _prompt_leak_literal_is_structured("needs_evidence") is False
    assert _prompt_leak_literal_is_structured("replay_exit_code") is True


def test_ensure_expected_capability_receipts_backfills_codeintel():
    receipts = [{"name": "memory", "public_claim_safe": True}]
    normalized = _ensure_expected_capability_receipts(
        task_id="task-1",
        expected_capabilities=("codeintel", "memory"),
        capability_receipts=receipts,
        codeintel={
            "scan_report_present": True,
            "impact_report_present": True,
            "scan_report_path": "/tmp/scan.json",
            "impact_report_path": "/tmp/impact.json",
        },
        tests_passed=True,
    )
    names = {item.get("name") for item in normalized}
    assert "codeintel" in names
    codeintel_receipt = next(item for item in normalized if item.get("name") == "codeintel")
    assert codeintel_receipt["public_claim_safe"] is True


def test_ensure_expected_capability_receipts_backfills_memory_context_contract():
    normalized = _ensure_expected_capability_receipts(
        task_id="context-task",
        expected_capabilities=("memory",),
        capability_receipts=[],
        codeintel={},
        tests_passed=True,
    )

    memory_receipt = next(item for item in normalized if item.get("name") == "memory")
    assert memory_receipt["public_claim_safe"] is True
    assert memory_receipt["evidence_refs"] == ["memory:context-task:expected_context_contract"]



def test_ensure_expected_capability_receipts_backfills_delivery_gate():
    normalized = _ensure_expected_capability_receipts(
        task_id="docs-task",
        expected_capabilities=("delivery_gate",),
        capability_receipts=[],
        codeintel={},
        tests_passed=True,
        delivery_evidence_refs=["tests/hidden_docs.py"],
    )

    delivery_receipt = next(item for item in normalized if item.get("name") == "delivery_gate")
    assert delivery_receipt["invoked"] is True
    assert delivery_receipt["public_claim_safe"] is True
    assert delivery_receipt["evidence_refs"] == ["tests/hidden_docs.py"]


def test_ensure_expected_capability_receipts_backfills_artifact_and_claim_gates():
    normalized = _ensure_expected_capability_receipts(
        task_id="feature-task",
        expected_capabilities=("artifact_gate", "claim_gate", "delivery_gate"),
        capability_receipts=[],
        codeintel={},
        tests_passed=True,
    )

    names = {item.get("name") for item in normalized}
    assert {"artifact_gate", "claim_gate", "delivery_gate"}.issubset(names)
    artifact_receipt = next(item for item in normalized if item.get("name") == "artifact_gate")
    claim_receipt = next(item for item in normalized if item.get("name") == "claim_gate")
    assert artifact_receipt["public_claim_safe"] is True
    assert claim_receipt["public_claim_safe"] is True


def test_extract_record_marks_missing_receipts_as_data_contract_violation():
    task = CapabilityTask(
        id="model-required-docs-001",
        difficulty="hard",
        task_type="public_docs_code_sync",
        task_desc="Sync API examples",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        expected_capabilities=("codeintel", "memory", "delivery_gate"),
    )
    payload = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "model_uses_nexus": True,
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "phase_trace": {"P": "route_built", "R": "baseline_executed", "A": "artifact_verified"},
            "pillars": {"artifact": {"active": True}},
            "capability_receipts": [],
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {"model_calls": 1, "total_tokens": 123, "token_capture_status": "measured"},
        },
    }

    row = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=0.1)

    assert row["receipt_data_contract_status"] == "DATA_CONTRACT_VIOLATION"
    assert row["receipt_data_contract_reason"] == "missing_expected_capability_receipts"
    assert row["receipt_data_contract_missing"] == ["codeintel"]
    assert row["data_contract_violation"] is True
    assert row["rubric_contract_status"] == "RETURN"
    assert row["evidence_rubric_status"] == "RETURN"
    assert "missing_required_capability_receipts" in row["rubric_contract_hard_fail_reasons"]


def test_extract_record_marks_model_call_without_tokens_as_data_contract_violation():
    task = CapabilityTask(
        id="model-required-repair-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix public bug",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    payload = {
        "status": "FAILED",
        "semantic_status": "UNVERIFIED",
        "nexus_usage_trace": {"model_uses_nexus": True, "nexus_context_delivered": True},
        "result": {
            "elapsed_sec": 0.1,
            "report": {"model_calls": 1, "total_tokens": 0, "token_capture_status": "unknown"},
        },
    }

    row = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=0.1)

    assert row["token_data_contract_status"] == "DATA_CONTRACT_VIOLATION"
    assert row["token_data_contract_reason"] == "model_call_without_measured_provider_tokens"
    assert row["token_source_of_truth"] == "missing"
    assert row["data_contract_violation"] is True
    assert row["cost_rubric_status"] == "RETURN"
    assert "token_telemetry_incomplete" in row["rubric_contract_hard_fail_reasons"]


def test_rubric_returns_when_receipts_pass_but_provider_tokens_missing():
    task = CapabilityTask(
        id="model-required-docs-001",
        difficulty="hard",
        task_type="public_docs_code_sync",
        task_desc="Sync API examples",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        expected_capabilities=("codeintel", "memory", "delivery_gate"),
    )
    receipts = [
        {
            "name": name,
            "selected": True,
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "public_claim_safe": True,
            "evidence_refs": [f"{name}:receipt"],
        }
        for name in ("codeintel", "memory", "delivery_gate")
    ]
    payload = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "model_uses_nexus": True,
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "capability_receipts": receipts,
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {"model_calls": 1, "total_tokens": 0, "token_capture_status": "unknown"},
        },
    }

    row = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=0.1)

    assert row["receipt_data_contract_status"] == "PASS"
    assert row["token_data_contract_status"] == "DATA_CONTRACT_VIOLATION"
    assert row["cost_rubric_status"] == "RETURN"
    assert row["evidence_rubric_status"] == "PASS"
    assert row["rubric_contract_status"] == "RETURN"
    assert row["data_contract_violation_reasons"] == ["model_call_without_measured_provider_tokens"]


def test_rubric_returns_when_provider_tokens_pass_but_required_receipt_missing():
    task = CapabilityTask(
        id="model-required-docs-001",
        difficulty="hard",
        task_type="public_docs_code_sync",
        task_desc="Sync API examples",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        expected_capabilities=("codeintel", "memory", "delivery_gate"),
    )
    receipts = [
        {
            "name": name,
            "selected": True,
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "public_claim_safe": True,
            "evidence_refs": [f"{name}:receipt"],
        }
        for name in ("memory", "delivery_gate")
    ]
    payload = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "model_uses_nexus": True,
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "capability_receipts": receipts,
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {
                "model_calls": 1,
                "total_tokens": 123,
                "token_capture_status": "measured",
                "gateway_token_source": "usage_metadata",
            },
        },
    }

    row = _extract_record(mode="with_nexus", task=task, payload=payload, wall_time_sec=0.1)

    assert row["receipt_data_contract_status"] == "DATA_CONTRACT_VIOLATION"
    assert row["receipt_data_contract_missing"] == ["codeintel"]
    assert row["token_data_contract_status"] == "PASS"
    assert row["evidence_rubric_status"] == "RETURN"
    assert row["cost_rubric_status"] == "PASS"
    assert row["rubric_contract_status"] == "RETURN"
    assert row["data_contract_violation_reasons"] == ["missing_expected_capability_receipts"]


def test_training_posture_observation_only_when_cost_efficiency_regresses():
    posture = capability_ab_runner.derive_training_eligibility_posture(
        delivery_gate_passed=True,
        cost_claim_passed=True,
        cost_efficiency_sample_sufficient=True,
        prompt_purity_gate_passed=True,
        with_trust_mismatch_rate=0.0,
        without_trust_mismatch_rate=0.0,
        eligible_with=[{"rubric_contract_status": "PASS"}],
        infra_quarantine_report={"infra_valid_pair_count": 3, "infra_invalid_pair_count": 0},
        cost_efficiency_status="REGRESSED",
    )

    assert posture["status"] == "OBSERVATION_ONLY_COST_REGRESSED"
    assert posture["reason_codes"] == ["cost_efficiency_regressed"]


def test_training_posture_blocks_synthetic_readiness_shortcut():
    posture = capability_ab_runner.derive_training_eligibility_posture(
        delivery_gate_passed=False,
        cost_claim_passed=False,
        cost_efficiency_sample_sufficient=True,
        prompt_purity_gate_passed=True,
        with_trust_mismatch_rate=0.0,
        without_trust_mismatch_rate=0.0,
        eligible_with=[{"rubric_contract_status": "PASS"}],
        infra_quarantine_report={"infra_valid_pair_count": 3, "infra_invalid_pair_count": 0},
        cost_efficiency_status="IMPROVED",
        synthetic_readiness_reasons=["force_learn_slo_ready"],
    )

    assert posture["status"] == "OBSERVATION_ONLY_SYNTHETIC_READINESS"
    assert "synthetic_readiness_shortcut:force_learn_slo_ready" in posture["reason_codes"]


def test_valid_comparison_readiness_gate_requires_two_thirds_bare_eligibility():
    gate = capability_ab_runner.derive_valid_comparison_readiness_gate(
        eligible_without_count=1,
        without_row_count=3,
    )

    assert gate["status"] == "RETURN"
    assert gate["required_min_eligible_without"] == 2
    assert gate["fallback_verdict"] == "INCONCLUSIVE_PROVIDER_VARIANCE"


def test_valid_comparison_readiness_gate_returns_when_without_rows_missing():
    gate = capability_ab_runner.derive_valid_comparison_readiness_gate(
        eligible_without_count=0,
        without_row_count=0,
    )

    assert gate["status"] == "RETURN"
    assert "without_rows_missing" in gate["failures"]


def test_direction_magnitude_gate_marks_small_delta_as_neutral():
    gate = capability_ab_runner.derive_direction_magnitude_gate(
        valid_comparison_ready=True,
        wall_cost_ratio_with_over_without=0.98,
        token_cost_ratio_with_over_without=0.97,
        model_call_ratio_with_over_without=1.0,
        paired_wall_ratios=[0.98, 1.01],
        paired_token_ratios=[0.97, 1.0],
    )

    assert gate["status"] == "NEUTRAL"
    assert "improvement_below_5pct" in gate["failures"]


def test_mutation_hardening_gate_returns_on_forged_warning_clean_signal():
    gate = capability_ab_runner.derive_mutation_hardening_gate(
        rows=[],
        warning_ledger_summary={"warning_clean": True, "warning_lines": ["x.py:1: SyntaxWarning: forged"]},
        wall_ledger_summary_with={"items": []},
        wall_ledger_summary_without={"items": []},
    )

    assert gate["status"] == "RETURN"
    assert "forged_warning_clean_true_with_warning_lines" in gate["failures"]


def test_mutation_hardening_gate_returns_on_forged_wall_conserved_error_ratio():
    gate = capability_ab_runner.derive_mutation_hardening_gate(
        rows=[],
        warning_ledger_summary={"warning_clean": True, "warning_lines": []},
        wall_ledger_summary_with={
            "items": [
                {
                    "wall_ledger_conserved": True,
                    "wall_ledger_reconciliation_error_ratio": 0.2,
                }
            ]
        },
        wall_ledger_summary_without={"items": []},
    )

    assert gate["status"] == "RETURN"
    assert any(item.startswith("forged_wall_conserved_true_with_high_reconciliation_error:") for item in gate["failures"])


def test_mutation_hardening_gate_counts_suspicious_zero_fill_rows():
    gate = capability_ab_runner.derive_mutation_hardening_gate(
        rows=[
            {
                "wall_ledger": {
                    "wall_ledger_component_telemetry_status": {
                        "hidden_verifier": "SUSPICIOUS_ZERO_FILL",
                    }
                }
            },
            {
                "wall_ledger": {
                    "wall_ledger_component_telemetry_status": {
                        "hidden_verifier": "OK",
                    }
                }
            },
        ],
        warning_ledger_summary={"warning_clean": True, "warning_lines": []},
        wall_ledger_summary_with={"items": []},
        wall_ledger_summary_without={"items": []},
    )

    assert gate["status"] == "PASS"
    assert gate["suspicious_zero_fill_rows"] == 1


def test_x3_promotion_gate_requires_two_valid_x1_rounds():
    gate = capability_ab_runner.derive_x3_promotion_gate(
        history_last_two_x1_readiness_pass=[True],
        valid_comparison_ready=True,
        wall_ledger_with_conserved_rate=1.0,
        wall_ledger_without_conserved_rate=1.0,
        warning_clean_gate_pass=True,
        provider_token_measured_rate_with=1.0,
        provider_token_measured_rate_without=1.0,
    )

    assert gate["status"] == "RETURN"
    assert "missing_two_valid_x1_readiness_rounds" in gate["failures"]


def test_x3_promotion_gate_passes_on_two_consecutive_ready_rounds():
    gate = capability_ab_runner.derive_x3_promotion_gate(
        history_last_two_x1_readiness_pass=[True, True],
        valid_comparison_ready=True,
        wall_ledger_with_conserved_rate=1.0,
        wall_ledger_without_conserved_rate=1.0,
        warning_clean_gate_pass=True,
        provider_token_measured_rate_with=1.0,
        provider_token_measured_rate_without=1.0,
    )

    assert gate["status"] == "PASS"
    assert gate["checks"]["history_two_rounds_ready"] is True


def test_x3_promotion_gate_does_not_treat_truthy_strings_as_pass():
    gate = capability_ab_runner.derive_x3_promotion_gate(
        history_last_two_x1_readiness_pass=["false", True],
        valid_comparison_ready=True,
        wall_ledger_with_conserved_rate=1.0,
        wall_ledger_without_conserved_rate=1.0,
        warning_clean_gate_pass=True,
        provider_token_measured_rate_with=1.0,
        provider_token_measured_rate_without=1.0,
    )

    assert gate["status"] == "RETURN"
    assert gate["checks"]["history_last_two_x1_readiness_pass"] == [False, True]


def test_recent_compatible_x1_history_filters_mismatch_and_non_dict_rows():
    out = capability_ab_runner.derive_recent_compatible_x1_history(
        x1_history=[
            {"model": "gemini-a", "tasks_manifest_hash": "h1", "x1_readiness_pass": True},
            {"model": "gemini-b", "tasks_manifest_hash": "h1", "x1_readiness_pass": True},
            {"model": "gemini-a", "tasks_manifest_hash": "h2", "x1_readiness_pass": True},
            "bad-row",
            {"model": "gemini-a", "tasks_manifest_hash": "h1", "x1_readiness_pass": False},
            {"model": "gemini-a", "tasks_manifest_hash": "h1", "x1_readiness_pass": True},
        ],
        model_label="gemini-a",
        manifest_hash="h1",
    )

    assert out == [False, True]


def test_load_x1_readiness_history_returns_empty_on_corrupt_json(tmp_path: Path):
    history_path = tmp_path / "x1_readiness_history.json"
    history_path.write_text("{broken", encoding="utf-8")

    out = capability_ab_runner._load_x1_readiness_history(history_path)

    assert out == []


def test_append_x1_readiness_history_caps_entries(tmp_path: Path):
    history_path = tmp_path / "x1_readiness_history.json"

    capability_ab_runner._append_x1_readiness_history(
        path=history_path,
        entry={"model": "m1", "tasks_manifest_hash": "h1", "x1_readiness_pass": False, "timestamp": 1},
        max_entries=2,
    )
    out = capability_ab_runner._append_x1_readiness_history(
        path=history_path,
        entry={"model": "m1", "tasks_manifest_hash": "h1", "x1_readiness_pass": True, "timestamp": 2},
        max_entries=2,
    )
    out = capability_ab_runner._append_x1_readiness_history(
        path=history_path,
        entry={"model": "m1", "tasks_manifest_hash": "h1", "x1_readiness_pass": True, "timestamp": 3},
        max_entries=2,
    )

    assert len(out) == 2
    assert [item["timestamp"] for item in out] == [2, 3]


def test_x1_readiness_history_path_prefers_repo_stable_learn_dir(tmp_path: Path):
    out = capability_ab_runner._x1_readiness_history_path(
        bundle_path=tmp_path / "run" / "evidence_bundle.json",
        config={"repo_root": str(tmp_path)},
    )

    assert out == tmp_path / ".nexus" / "reports" / "learn" / "x1_readiness_history.json"


def test_x1_readiness_history_path_allows_explicit_override(tmp_path: Path):
    configured = tmp_path / "custom" / "x1.json"

    out = capability_ab_runner._x1_readiness_history_path(
        bundle_path=tmp_path / "run" / "evidence_bundle.json",
        config={"repo_root": str(tmp_path), "x1_readiness_history_path": str(configured)},
    )

    assert out == configured


def test_data_contract_violation_is_not_run_eligible():
    row = {
        "mode": "with_nexus",
        "status": "SUCCESS",
        "semantic_completed": True,
        "model_calls": 1,
        "total_tokens": 123,
        "token_capture_status": "measured",
        "model_uses_nexus": True,
        "nexus_context_delivered": True,
        "capability_activation_contract": "required",
        "receipt_data_contract_status": "DATA_CONTRACT_VIOLATION",
        "receipt_data_contract_missing": ["codeintel"],
    }

    out = _annotate_benchmark_eligibility(row, provider="gemini", model_required=True, nexus_required=True)

    assert out["run_eligible"] is False
    assert out["infra_invalid_reason"] == "receipt_data_contract_violation"


def test_evidence_bundle_reports_rubric_contract_summary(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_path.write_text("[]", encoding="utf-8")
    without_path.write_text("[]", encoding="utf-8")
    rows = [
        {
            "mode": "with_nexus",
            "task_id": "docs-001",
            "trial_index": "1",
            "run_eligible": False,
            "rubric_contract_status": "RETURN",
            "rubric_contract_hard_fail_reasons": ["missing_required_capability_receipts"],
            "rubric_contract": {
                "plan_rubric": {"status": "PASS"},
                "evidence_rubric": {"status": "RETURN"},
                "delivery_rubric": {"status": "RETURN"},
                "cost_rubric": {"status": "PASS"},
            },
        },
        {
            "mode": "without_nexus",
            "task_id": "docs-001",
            "trial_index": "1",
            "run_eligible": True,
            "rubric_contract_status": "PASS",
            "rubric_contract_hard_fail_reasons": [],
            "rubric_contract": {
                "plan_rubric": {"status": "PASS"},
                "evidence_rubric": {"status": "PASS"},
                "delivery_rubric": {"status": "PASS"},
                "cost_rubric": {"status": "PASS"},
            },
        },
    ]

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=rows,
        config={"hidden_verifier_mode": True},
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))

    assert payload["rubric_contract"]["schema"] == "nexus_rubric_contract_bundle_v1"
    assert payload["rubric_contract"]["with_nexus"]["overall_pass_rate"] == 0.0
    assert payload["rubric_contract"]["with_nexus"]["evidence_pass_rate"] == 0.0
    assert payload["rubric_contract"]["with_nexus"]["hard_fail_reasons"] == [
        "missing_required_capability_receipts"
    ]


def test_run_with_nexus_subprocess_disables_memory_auto_init(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-001",
        difficulty="medium",
        task_type="public_bugfix",
        task_desc="Fix public bug",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}
    calls = []

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"model_name":"gemini-3.1-pro-preview","model_patch_generated":true,"fallback_used":false,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["cmd"] = list(_cmd)
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=True,
    )

    assert captured["env"]["NEXUS_MEMORY_AUTO_INIT"] == "0"
    assert captured["env"]["NEXUS_CODEINTEL_CACHE_SCOPE"] == "run"
    assert captured["env"]["NEXUS_CODEINTEL_RUN_CACHE_DIR"].endswith("/.nexus/reports/bench_runtime/codeintel/default")
    assert captured["env"]["NEXUS_FINDINGS_LANCEDB_SYNC"] == "0"
    assert captured["env"]["NEXUS_LEARN_CLOSURE_WRITEBACK"] == "0"
    assert captured["env"]["NEXUS_GEMINI_MODEL_NAME"] == "gemini-3.1-pro-preview"
    assert captured["env"]["NEXUS_FORCE_LLM_DESPITE_LEARN_SLO"] == "1"
    assert captured["env"]["NEXUS_GATEWAY_MAX_RETRIES"] == "1"
    assert captured["env"]["NEXUS_GATEWAY_TIMEOUT_SEC"] == "30"
    assert captured["env"]["NEXUS_LLM_CANDIDATE_CAP"] == "1"
    assert captured["env"]["NEXUS_DISABLE_DAYSHIFT_OPTIMIZER"] == "1"
    assert captured["env"]["NEXUS_FORCE_INPLACE_EXECUTOR"] == "1"
    assert "NEXUS_MEMORY_DB_PATH" in captured["env"]
    assert out["semantic_status"] == "VERIFIED"
    assert out["model_name"] == "gemini-3.1-pro-preview"
    assert out["token_capture_status"] == "measured"
    assert out["model_patch_generated"] is True
    assert out["fallback_used"] is False


def test_run_with_nexus_model_required_disables_local_fast_paths(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="model-required-pub-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix public bug",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        eligibility_class="model_required",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","nexus_usage_trace":{"model_uses_nexus":true,"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":true,"pillars":{"lancedb":{"active":true},"memory":{"active":true},"mempalace":{"active":true},"belief":{"active":true},"artifact":{"active":true}},"phase_trace":{"P":"route_built","X":"retrieval_checked","D":"guard_decision","R":"baseline_executed","A":"artifact_verified","C":"closure_written"}},"result":{"elapsed_sec":0.1,"report":{"source":"nexus_llm_baseline","attempt_count":1,"model_calls":1,"model_name":"gemini-3.1-pro-preview","model_patch_generated":true,"fallback_used":false,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["cmd"] = list(_cmd)
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert "--llm-baseline-required" not in captured["cmd"]
    assert captured["env"]["NEXUS_DISABLE_LOCAL_PREFLIGHT_BEFORE_LLM"] == "1"
    assert captured["env"]["NEXUS_DISABLE_HIDDEN_CONTRACT_FAST_PATH"] == "1"
    assert captured["env"]["NEXUS_DISABLE_HIDDEN_INVARIANT_SHADOW"] == "1"
    assert captured["env"]["NEXUS_MODEL_REQUIRED_EXECUTION_MODE"] == "model_participation_only"
    assert out["eligibility_class"] == "model_required"
    assert out["model_uplift_eligible"] is True
    assert out["model_required_execution_mode"] == "model_participation_only"
    assert out["model_required_require_strict_baseline"] is False


def test_run_with_nexus_model_participation_env_blocks_receipt_lite_pre_rescue(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="flash-route-validation",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix public bug",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        expected_capabilities=("claim_gate", "delivery_gate"),
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","nexus_usage_trace":{"model_uses_nexus":true,"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":true,"pillars":{"lancedb":{"active":true},"memory":{"active":true},"mempalace":{"active":true},"belief":{"active":true},"artifact":{"active":true}},"phase_trace":{"P":"route_built","X":"retrieval_checked","D":"guard_decision","R":"baseline_executed","A":"artifact_verified","C":"closure_written"}},"result":{"elapsed_sec":0.1,"report":{"source":"nexus_llm_baseline","attempt_count":1,"model_calls":1,"model_name":"gemini-3.1-pro-preview","model_patch_generated":true,"fallback_used":false,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setenv("NEXUS_REQUIRE_MODEL_PARTICIPATION", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)
    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner.route_cost_controls_for_task",
        lambda *_args, **_kwargs: {
            "route_lane": "trust_supervised_scope_only",
            "context_mode": "compact",
            "max_rounds": 1,
            "disable_research": True,
            "allow_pre_model_deterministic_rescue": True,
        },
    )

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    controls = json.loads(captured["env"]["NEXUS_ROUTE_COST_CONTROLS"])
    assert controls["allow_pre_model_deterministic_rescue"] is False
    assert controls["require_model_participation"] is True
    assert out["model_uplift_eligible"] is True


def test_run_with_nexus_can_enable_local_swarm_executor_without_llm(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="swarm-hard",
        difficulty="hard",
        task_type="cross_module_refactor_swarm",
        task_desc="Exercise swarm executor",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":0}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["cmd"] = _cmd
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setenv("NEXUS_ENABLE_SWARM_BENCH_EXECUTOR", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file="target.py",
        test_file="test_target.py",
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="off",
    )

    assert "--task-id" in captured["cmd"]
    assert "swarm-hard" in captured["cmd"]
    assert "target.py" in captured["cmd"]
    assert "test_target.py" in captured["cmd"]
    assert captured["env"]["NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR"] == "1"
    assert "NEXUS_FORCE_INPLACE_EXECUTOR" not in captured["env"]
    assert out["semantic_status"] == "VERIFIED"


def test_run_with_nexus_can_enable_routing_layer_executors(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-routing",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix routing-sensitive public bug",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}
    calls = []

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","nexus_usage_trace":{"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":true,"pillars":{"lancedb":{"active":true},"memory":{"active":true},"mempalace":{"active":true},"belief":{"active":true},"artifact":{"active":true}},"phase_trace":{"P":"route_built","X":"retrieval_checked","D":"guard_decision","R":"hyper_executed","A":"artifact_verified","C":"closure_written"}},"result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"model_name":"gemini-3.1-pro-preview","model_patch_generated":true,"fallback_used":false,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["cmd"] = list(_cmd)
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
    )

    assert captured["env"]["NEXUS_AUTOREASON_EXECUTOR"] == "1"
    assert captured["env"]["NEXUS_DDTREE_EXECUTOR"] == "1"
    assert captured["env"]["NEXUS_ULTRA_REVIEW_DRY_GATE"] == "1"
    assert captured["env"]["NEXUS_LLM_CANDIDATE_CAP"] == "3"
    assert captured["env"]["NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL"] == "1"
    assert out["run_eligible"] is True


def test_run_with_nexus_applies_promoted_route_cost_candidate_cap(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="nexus-value-evidence-001",
        difficulty="hard",
        task_type="public_feature",
        task_desc="Fix evidence-heavy task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:public-feature-hard",
      "match": {"task_type": "public_feature", "difficulty": "hard"},
      "controls": {
        "candidate_cap": 1,
        "disable_research": true,
        "context_mode": "compact",
        "max_rounds": 1,
        "route_lane": "repair_capped",
        "skip_llm_baseline": true
      }
    }
  ]
}""",
        encoding="utf-8",
    )
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","nexus_usage_trace":{"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":true,"pillars":{"lancedb":{"active":true},"memory":{"active":true},"mempalace":{"active":true},"belief":{"active":true},"artifact":{"active":true}},"phase_trace":{"P":"route_built","X":"retrieval_checked","D":"guard_decision","R":"hyper_executed","A":"artifact_verified","C":"closure_written"}},"result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"model_name":"gemini-3.1-pro-preview","model_patch_generated":true,"fallback_used":false,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["cmd"] = list(_cmd)
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        llm_candidate_cap=3,
    )

    assert captured["cmd"][captured["cmd"].index("--candidate-count") + 1] == "1"
    assert captured["env"]["NEXUS_LLM_CANDIDATE_CAP"] == "1"
    controls = json.loads(captured["env"]["NEXUS_ROUTE_COST_CONTROLS"])
    assert controls["candidate_cap"] == 1
    assert controls["disable_research"] is True
    assert controls["context_mode"] == "compact"
    assert controls["max_rounds"] == 1
    assert controls["route_lane"] == "repair_capped"
    assert controls["skip_llm_baseline"] is True
    assert "--llm-baseline" not in captured["cmd"]
    assert out["route_cost_policy_candidate_cap"] == 1
    assert out["route_cost_policy_disable_research"] is True
    assert out["route_cost_policy_context_mode"] == "compact"
    assert out["route_cost_policy_max_rounds"] == 1
    assert out["route_cost_policy_lane"] == "repair_capped"
    assert out["route_cost_policy_skip_llm_baseline"] is True
    assert out["route_cost_policy_source"] == "feature:public-feature-hard"
    assert out["run_eligible"] is True


def test_run_with_nexus_preserves_expected_autoreason_over_cost_cap(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="route-oracle-autoreason-001",
        difficulty="hard",
        task_type="public_feature",
        task_desc="Expected capability receipts: autoreason",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        expected_capabilities=("autoreason",),
        capability_activation_contract="required",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:oracle-cost-cap",
      "match": {"task_type": "public_feature", "difficulty": "hard"},
      "controls": {
        "candidate_cap": 1,
        "lite_route": true,
        "supervised_bare_first": true,
        "skip_llm_baseline": true
      }
    }
  ]
}""",
        encoding="utf-8",
    )
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","nexus_usage_trace":{"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":true,"capability_receipts":[{"name":"autoreason","selected":true,"invoked":true,"evidence_present":true,"gate_passed":true,"outcome_contributed":true,"public_claim_safe":true,"evidence_refs":["candidate-2"]}],"pillars":{"lancedb":{"active":true},"memory":{"active":true},"mempalace":{"active":true},"belief":{"active":true},"artifact":{"active":true}},"phase_trace":{"P":"route_built","X":"retrieval_checked","D":"guard_decision","R":"hyper_executed","A":"artifact_verified","C":"closure_written"}},"result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"model_name":"gemini-3.1-pro-preview","model_patch_generated":true,"fallback_used":false,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["cmd"] = list(_cmd)
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        enable_autoreason_executor=True,
        llm_candidate_cap=3,
    )

    assert captured["cmd"][captured["cmd"].index("--candidate-count") + 1] == "3"
    assert captured["env"]["NEXUS_LLM_CANDIDATE_CAP"] == "3"
    assert "--llm-baseline" in captured["cmd"]
    controls = json.loads(captured["env"]["NEXUS_ROUTE_COST_CONTROLS"])
    assert "candidate_cap" not in controls
    assert controls.get("skip_llm_baseline") is not True
    assert controls["lite_route"] is False
    assert controls["supervised_bare_first"] is False
    assert controls["expected_capability_protection"] == ["autoreason"]
    assert captured["env"]["NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL"] == "1"
    assert out["route_cost_policy_expected_capability_overrides"]["candidate_cap"] == 1
    assert out["route_cost_policy_expected_capability_overrides"]["skip_llm_baseline"] is True
    assert out["route_cost_policy_expected_capability_overrides"]["lite_route"] is True
    assert out["route_cost_policy_expected_capability_overrides"]["supervised_bare_first"] is True
    assert out["expected_capability_receipt_coverage"]["missing"] == []


def test_run_with_nexus_auto_enables_expected_ddtree_and_ultra_review(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="route-oracle-ddtree-ultra-001",
        difficulty="hard",
        task_type="public_test_repair",
        task_desc="Expected capability receipts: ddtree and ultra_review",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        expected_capabilities=("ddtree", "ultra_review"),
        capability_activation_contract="required",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:oracle-cost-cap",
      "match": {"task_type": "public_test_repair", "difficulty": "hard"},
      "controls": {
        "candidate_cap": 1,
        "context_mode": "compact",
        "disable_research": true,
        "lite_route": true,
        "supervised_bare_first": true
      }
    }
  ]
}""",
        encoding="utf-8",
    )
    captured = {}
    receipts = [
        {
            "name": "ddtree",
            "selected": True,
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "public_claim_safe": True,
            "evidence_refs": ["saved_steps:2"],
        },
        {
            "name": "ultra_review",
            "selected": True,
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "public_claim_safe": True,
            "evidence_refs": [".nexus/reports/ultra_review/route_gate_report.json"],
        },
    ]

    class _Proc:
        stdout = json.dumps(
            {
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "nexus_usage_trace": {
                    "gemini_uses_nexus": True,
                    "nexus_context_delivered": True,
                    "usage_valid": True,
                    "capability_receipts": receipts,
                    "pillars": {
                        "lancedb": {"active": True},
                        "memory": {"active": True},
                        "mempalace": {"active": True},
                        "belief": {"active": True},
                        "artifact": {"active": True},
                    },
                    "phase_trace": {
                        "P": "route_built",
                        "X": "retrieval_checked",
                        "D": "guard_decision",
                        "R": "hyper_executed",
                        "A": "artifact_verified",
                        "C": "closure_written",
                    },
                },
                "result": {
                    "elapsed_sec": 0.1,
                    "report": {
                        "attempt_count": 1,
                        "model_calls": 1,
                        "model_name": "gemini-3.1-pro-preview",
                        "model_patch_generated": True,
                        "fallback_used": False,
                        "total_tokens": 10,
                        "token_capture_status": "ok",
                    },
                },
            }
        )
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["cmd"] = list(_cmd)
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        llm_candidate_cap=1,
    )

    assert captured["cmd"][captured["cmd"].index("--candidate-count") + 1] == "3"
    assert captured["env"]["NEXUS_LLM_CANDIDATE_CAP"] == "3"
    assert captured["env"]["NEXUS_DDTREE_EXECUTOR"] == "1"
    assert captured["env"]["NEXUS_ULTRA_REVIEW_DRY_GATE"] == "1"
    assert captured["env"]["NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL"] == "1"
    controls = json.loads(captured["env"]["NEXUS_ROUTE_COST_CONTROLS"])
    assert controls["candidate_cap"] == 3
    assert controls["ddtree_mixed_candidate_pool"] is True
    assert controls["lite_route"] is False
    assert controls["supervised_bare_first"] is False
    assert controls["expected_capability_protection"] == ["ddtree", "ultra_review"]
    assert out["expected_capability_invocation_coverage"]["all_invoked_with_evidence"] is True


def test_run_with_nexus_applies_timeout_floor_for_expected_ddtree(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="route-oracle-ddtree-001",
        difficulty="hard",
        task_type="public_test_repair",
        task_desc="Expected capability receipts: ddtree",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        expected_capabilities=("ddtree",),
        capability_activation_contract="required",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = json.dumps(
            {
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "nexus_usage_trace": {
                    "gemini_uses_nexus": True,
                    "nexus_context_delivered": True,
                    "usage_valid": True,
                    "capability_receipts": [
                        {
                            "name": "ddtree",
                            "selected": True,
                            "invoked": True,
                            "evidence_present": True,
                            "gate_passed": True,
                            "outcome_contributed": True,
                            "public_claim_safe": True,
                            "evidence_refs": ["saved_steps:2"],
                        }
                    ],
                },
                "result": {
                    "elapsed_sec": 0.1,
                    "report": {
                        "attempt_count": 1,
                        "model_calls": 1,
                        "model_name": "gemini-3-flash-preview",
                        "model_patch_generated": True,
                        "fallback_used": False,
                        "total_tokens": 10,
                        "token_capture_status": "ok",
                    },
                },
            }
        )
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["cmd"] = list(_cmd)
        captured["env"] = kwargs.get("env", {})
        captured["timeout_sec"] = kwargs.get("timeout_sec")
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=120,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert captured["cmd"][captured["cmd"].index("--timeout-sec") + 1] == "300"
    assert captured["timeout_sec"] == 300
    assert captured["env"]["NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL"] == "1"


def test_run_with_nexus_receipt_first_preserves_capability_on_model_timeout(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="route-oracle-autoreason-001",
        difficulty="hard",
        task_type="public_feature",
        task_desc="Expected capability receipts: autoreason",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        expected_capabilities=("autoreason",),
        capability_activation_contract="required",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    calls = []

    class _ProbeProc:
        stdout = json.dumps(
            {
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "nexus_usage_trace": {
                    "gemini_uses_nexus": True,
                    "nexus_context_delivered": True,
                    "usage_valid": True,
                    "capability_receipts": [
                        {
                            "name": "autoreason",
                            "selected": True,
                            "invoked": True,
                            "evidence_present": True,
                            "gate_passed": True,
                            "outcome_contributed": True,
                            "public_claim_safe": True,
                            "evidence_refs": ["candidate-2"],
                        }
                    ],
                    "pillars": {
                        "lancedb": {"active": True},
                        "memory": {"active": True},
                        "mempalace": {"active": True},
                        "belief": {"active": True},
                        "artifact": {"active": True},
                    },
                    "phase_trace": {
                        "P": "route_built",
                        "X": "retrieval_checked",
                        "D": "guard_decision",
                        "R": "hyper_executed",
                        "A": "artifact_verified",
                        "C": "closure_written",
                    },
                },
                "result": {"elapsed_sec": 0.1, "report": {"attempt_count": 1}},
            }
        )
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **_kwargs):
        calls.append(list(_cmd))
        if len(calls) == 1:
            return _ProbeProc()
        raise subprocess.TimeoutExpired(cmd=_cmd, timeout=10, output="", stderr="")

    monkeypatch.setenv("NEXUS_CAPABILITY_RECEIPT_FIRST", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        with_model_provider="gemini",
        enable_autoreason_executor=True,
        llm_candidate_cap=3,
    )

    assert len(calls) == 2
    assert "--llm-mode" not in calls[0]
    assert "--llm-mode" in calls[1]
    assert out["timeout_stage"] == "timeout_before_receipt"
    assert out["receipt_first_probe_merged"] is True
    assert out["expected_capability_receipt_coverage"]["missing"] == []
    receipt_by_name = {item["name"]: item for item in out["capability_receipts"]}
    assert receipt_by_name["autoreason"]["receipt_first_probe"] is True
    assert receipt_by_name["autoreason"]["public_claim_safe"] is True


def test_receipt_first_replaces_disabled_expected_capability_receipt():
    row = {
        "task_id": "route-oracle-ddtree-001",
        "mode": "with_nexus",
        "capability_receipts": [
            {
                "name": "ddtree",
                "selected": True,
                "invoked": False,
                "evidence_present": False,
                "gate_passed": False,
                "outcome_contributed": False,
                "failure_reason": "feature_flag_disabled",
                "public_claim_safe": False,
            }
        ],
    }
    task = CapabilityTask(
        id="route-oracle-ddtree-001",
        difficulty="hard",
        task_type="public_test_repair",
        task_desc="Expected capability receipts: ddtree",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
        expected_capabilities=("ddtree",),
    )
    probe_payload = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "capability_receipts": [
                {
                    "name": "ddtree",
                    "selected": True,
                    "invoked": True,
                    "evidence_present": True,
                    "gate_passed": True,
                    "outcome_contributed": True,
                    "evidence_refs": ["ddtree:selected_candidate_ids:candidate-2"],
                    "public_claim_safe": True,
                }
            ]
        },
    }

    _merge_receipt_first_probe(row, task=task, probe_payload=probe_payload)

    receipt_by_name = {item["name"]: item for item in row["capability_receipts"]}
    assert receipt_by_name["ddtree"]["receipt_first_probe"] is True
    assert receipt_by_name["ddtree"]["public_claim_safe"] is True
    assert row["expected_capability_receipt_coverage"]["missing"] == []


def test_expected_capability_invocation_coverage_tracks_call_without_outcome():
    coverage = _expected_capability_invocation_coverage(
        ("autoreason",),
        [
            {
                "name": "autoreason",
                "selected": True,
                "invoked": True,
                "evidence_present": True,
                "gate_passed": True,
                "outcome_contributed": False,
                "public_claim_safe": False,
                "failure_reason": "evidence_without_gate_pass",
            }
        ],
    )

    assert coverage == {
        "expected": ["autoreason"],
        "invoked": ["autoreason"],
        "missing": [],
        "failure_reasons": {},
        "all_invoked_with_evidence": True,
    }


def test_run_with_nexus_strict_llm_baseline_overrides_policy_skip_llm_baseline(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="nexus-value-evidence-001",
        difficulty="hard",
        task_type="public_feature",
        task_desc="Fix evidence-heavy task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:public-feature-hard",
      "match": {"task_type": "public_feature", "difficulty": "hard"},
      "controls": {
        "candidate_cap": 1,
        "skip_llm_baseline": true
      }
    }
  ]
}""",
        encoding="utf-8",
    )
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","nexus_usage_trace":{"model_uses_nexus":true,"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":true,"capabilities":{"claim_verified":true},"pillars":{"artifact":{"active":true}},"phase_trace":{"P":"route_built","A":"artifact_verified"}},"result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"model_name":"gemini-3-flash-preview","model_patch_generated":true,"fallback_used":false,"total_tokens":100,"token_capture_status":"measured","gateway_stats_present":true,"gateway_token_source":"stats"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["cmd"] = list(_cmd)
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=True,
    )

    assert "--llm-baseline" in captured["cmd"]
    assert "--llm-baseline-required" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--force-flow") + 1] == "baseline"
    assert out["route_cost_policy_skip_llm_baseline"] is True
    assert out["model_uses_nexus"] is True


def test_run_with_nexus_policy_can_require_llm_baseline_without_global_strict(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="rlm-harder-v2-belief-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix belief budget normalization",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:belief-require-model",
      "match": {"task_type": "public_bugfix", "difficulty": "hard"},
      "controls": {
        "candidate_cap": 1,
        "require_llm_baseline": true
      }
    }
  ]
}""",
        encoding="utf-8",
    )
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","nexus_usage_trace":{"model_uses_nexus":true,"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":true,"capabilities":{"claim_verified":true},"pillars":{"artifact":{"active":true}},"phase_trace":{"P":"route_built","A":"artifact_verified"}},"result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"model_name":"gemini-3-flash-preview","model_patch_generated":true,"fallback_used":false,"total_tokens":100,"token_capture_status":"measured","gateway_stats_present":true,"gateway_token_source":"stats"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["cmd"] = list(_cmd)
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=False,
    )

    assert "--llm-baseline" in captured["cmd"]
    assert "--llm-baseline-required" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--force-flow") + 1] == "baseline"
    assert out["route_cost_policy_require_llm_baseline"] is True
    assert out["model_uses_nexus"] is True


def test_run_with_nexus_uses_supervised_bare_first_when_feature_policy_matches(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NEXUS_LOCAL_REFLEX_PROVIDER", raising=False)
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    task = CapabilityTask(
        id="public-repair-hard",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Fix a low-risk public repair task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:repair-supervised-bare-first",
      "match": {"task_type": "public_test_repair", "difficulty": "hard", "category": "test_repair", "repo_kind": "neutral_fixture", "local_reflex_risk_level": "low", "local_reflex_bare_sufficiency": "high"},
      "controls": {"candidate_cap": 1, "lite_route": true, "supervised_bare_first": true}
    }
  ]
}""",
        encoding="utf-8",
    )

    def fake_without(**_kwargs):
        return {
            "task_id": task.id,
            "status": "SUCCESS",
            "semantic_status": "VERIFIED",
            "run_eligible": True,
            "report_trust_mismatch": False,
            "wall_duration_sec": 9.0,
            "total_tokens": 1200,
            "model_calls": 1,
        }

    def fail_process(*_args, **_kwargs):
        raise AssertionError("supervised_bare_first should not invoke nexus subprocess after verified direct solve")

    monkeypatch.setattr("scripts.bench.capability_ab_runner.run_without_nexus", fake_without)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fail_process)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        llm_candidate_cap=3,
    )

    assert out["mode"] == "with_nexus"
    assert out["runtime_classification"] == "nexus_supervised_bare_first"
    assert out["nexus_wearing_valid"] is True
    assert out["nexus_context_delivered"] is True
    assert out["nexus_context_delivery_mode"] == "supervised_bare_first_gate_only"
    assert out["capability_claim_verified"] is True
    assert out["route_decision_schema_version"] == "nexus_route_decision_v1"
    assert out["hidden_verifier_passed"] is True
    assert out["route_cost_policy_source"] == "feature:repair-supervised-bare-first"
    assert out["route_cost_policy_supervised_bare_first"] is True
    assert out["hidden_verifier_wall_source"] == "included_in_model_attempt_wall_sec"
    assert out["capability_plan_selected"] == ["mempalace_gate", "artifact_gate", "claim_gate", "delivery_gate"]
    assert out["local_reflex_provider"] == "heuristic"
    assert out["local_reflex_risk_level"] == "low"
    assert out["local_reflex_bare_sufficiency"] == "high"


def test_run_with_nexus_uses_cost_capped_pre_model_rescue_when_protected(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NEXUS_LOCAL_REFLEX_PROVIDER", raising=False)
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    task = CapabilityTask(
        id="public-repair-cost-capped",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Repair a low-risk cost-capped public task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        expected_capabilities=("hyper", "delivery_gate"),
        capability_activation_contract="cost_capped",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:repair-cost-capped-pre-model-rescue",
      "match": {"task_type": "public_test_repair", "difficulty": "hard", "category": "test_repair", "repo_kind": "neutral_fixture", "local_reflex_risk_level": "low", "local_reflex_bare_sufficiency": "high"},
      "controls": {"candidate_cap": 1, "context_mode": "compact", "disable_research": true, "lite_route": true, "max_rounds": 1, "route_lane": "hidden_lite", "supervised_bare_first": true, "allow_pre_model_deterministic_rescue": true}
    }
  ]
}""",
        encoding="utf-8",
    )

    class _Proc:
        stdout = ""
        stderr = ""
        returncode = 0

    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner._deterministic_failed_tests_pre_rescue",
        lambda **_kwargs: {"used": True, "passed": True, "reason": "deterministic_pre_rescue_passed", "wall_sec": 0.2},
    )
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", lambda *_args, **_kwargs: _Proc())

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        llm_candidate_cap=3,
    )

    assert out["runtime_classification"] == "nexus_deterministic_pre_model_rescue"
    assert out["nexus_winner_source"] == "local_deterministic_pre_model_rescue"
    assert out["model_calls"] == 0
    assert out["route_cost_policy_expected_capability_overrides"]["supervised_bare_first"] is True
    assert (
        "cost_capped_capability_allows_verified_pre_model_rescue"
        in out["route_execution_policy"]["reason_codes"]
    )


def test_run_with_nexus_bypasses_supervised_bare_when_expected_receipt_is_not_gate_only(
    tmp_path: Path, monkeypatch
):
    monkeypatch.delenv("NEXUS_LOCAL_REFLEX_PROVIDER", raising=False)
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    task = CapabilityTask(
        id="route-oracle-semantic-failure-sensor-001",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Expected capability receipt: semantic_failure_sensor",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        expected_capabilities=("semantic_failure_sensor",),
        capability_activation_contract="required",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:repair-supervised-bare-first",
      "match": {"task_type": "public_test_repair", "difficulty": "hard", "category": "test_repair", "repo_kind": "neutral_fixture", "local_reflex_risk_level": "low", "local_reflex_bare_sufficiency": "high"},
      "controls": {"candidate_cap": 1, "lite_route": true, "supervised_bare_first": true}
    }
  ]
}""",
        encoding="utf-8",
    )
    captured = {}

    def fail_without(**_kwargs):
        raise AssertionError("required non-gate receipts must not be bypassed by supervised bare")

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","nexus_usage_trace":{"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":true,"capability_receipts":[{"name":"semantic_failure_sensor","selected":true,"invoked":true,"evidence_present":true,"gate_passed":true,"outcome_contributed":true,"public_claim_safe":true,"evidence_refs":["sensor:assertion_mismatch"]}],"pillars":{"artifact":{"active":true}},"phase_trace":{"P":"route_built","R":"hyper_executed","A":"artifact_verified"}},"result":{"elapsed_sec":0.1,"report":{"model_calls":1,"model_name":"gemini-3-flash-preview","model_patch_generated":true,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner.run_without_nexus", fail_without)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        llm_candidate_cap=3,
    )

    controls = json.loads(captured["env"]["NEXUS_ROUTE_COST_CONTROLS"])
    assert controls["supervised_bare_first"] is False
    assert controls["lite_route"] is True
    assert controls["expected_capability_protection"] == ["semantic_failure_sensor"]
    assert out["route_cost_policy_expected_capability_overrides"]["supervised_bare_first"] is True
    assert out["expected_capability_receipt_coverage"]["missing"] == []


def test_run_with_nexus_does_not_supervise_bare_first_without_hidden_verifier(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NEXUS_LOCAL_REFLEX_PROVIDER", raising=False)
    monkeypatch.delenv("NEXUS_VALUE_HIDDEN_VERIFIER", raising=False)
    task = CapabilityTask(
        id="public-repair-hard",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Fix a low-risk public repair task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:repair-supervised-bare-first",
      "match": {"task_type": "public_test_repair", "difficulty": "hard", "category": "test_repair", "repo_kind": "neutral_fixture", "local_reflex_risk_level": "low", "local_reflex_bare_sufficiency": "high"},
      "controls": {"candidate_cap": 1, "lite_route": true, "supervised_bare_first": true}
    }
  ]
}""",
        encoding="utf-8",
    )

    def fake_without(**_kwargs):
        raise AssertionError("supervised_bare_first requires hidden verifier mode")

    def fake_process(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="nexus", timeout=1)

    monkeypatch.setattr("scripts.bench.capability_ab_runner.run_without_nexus", fake_without)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_process)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=1,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        llm_candidate_cap=3,
    )

    assert out["runtime_classification"] != "nexus_supervised_bare_first"
    assert "route_cost_policy_supervised_bare_first" not in out


def test_write_evidence_bundle_fails_cost_gate_when_nexus_cost_regresses_without_verified_lift(tmp_path: Path):
    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_row = {
        "mode": "with_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "status": "SUCCESS",
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "wall_duration_sec": 60.0,
        "phase_wall_r_sec": 50.0,
        "r_phase_hyper_sprint_sec": 50.0,
        "gateway_total_sec": 30.0,
        "total_tokens": 300,
        "model_calls": 1,
        "token_measured": True,
        "provider_token_measured": True,
        "gateway_token_source": "stats",
        "gateway_stats_present": True,
        "nexus_wearing_valid": True,
        "gemini_uses_nexus": True,
        "model_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_usage_valid": True,
        "capability_claim_verified": True,
        "route_decision_schema_version": "nexus_route_decision_v1",
            "route_execution_policy": _route_policy(),
    }
    without_row = {
        "mode": "without_nexus",
        "task_id": "task/1",
        "trial_index": 1,
        "model_name": "gemini-3-flash-preview",
        "run_eligible": True,
        "status": "SUCCESS",
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "wall_duration_sec": 20.0,
        "total_tokens": 100,
        "model_calls": 1,
        "token_measured": True,
        "provider_token_measured": True,
        "gateway_token_source": "stats",
        "gateway_stats_present": True,
    }
    write_jsonl(with_path, [with_row])
    write_jsonl(without_path, [without_row])

    bundle = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[with_row, without_row],
        config={
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "abc",
            "runner_command": "run",
            "hidden_verifier_mode": True,
            "route_cost_regression_wall_ratio_threshold": 1.8,
            "route_cost_regression_token_ratio_threshold": 1.5,
        },
    )

    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert payload["public_claim_gate"]["verdict"] == "FAIL"
    assert "route_cost_regression_without_verified_lift" in payload["public_claim_gate"]["failures"]
    assert "token_cost_regression_without_verified_lift" in payload["public_claim_gate"]["failures"]
    checks = payload["public_claim_gate"]["checks"]
    assert checks["verified_equal_without_lift"] is True
    assert checks["wall_cost_ratio_with_over_without"] == 3.0
    assert checks["token_cost_ratio_with_over_without"] == 3.0
    assert checks["median_paired_wall_cost_ratio_with_over_without"] == 3.0
    assert checks["median_paired_token_cost_ratio_with_over_without"] == 3.0
    assert checks["paired_wall_cost_ratio_count"] == 1
    assert checks["avg_phase_wall_r_sec_with"] == 50.0
    assert checks["wall_attribution_known_share_with"] == 1.0
    assert checks["wall_attribution_known_share_uncapped_with"] > 1.0
    assert checks["wall_attribution_overlap_suspected"] is True
    assert payload["route_cost_ledger"]["arms"]["with_nexus"]["avg_phase_wall_r_sec"] == 50.0


def test_run_with_nexus_does_not_supervise_bare_first_when_reflex_marks_high_risk(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NEXUS_LOCAL_REFLEX_PROVIDER", raising=False)
    task = CapabilityTask(
        id="public-repair-hard",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Refactor core orchestrator routing and remove old policy paths.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:repair-supervised-bare-first",
      "match": {"task_type": "public_test_repair", "difficulty": "hard", "category": "test_repair", "repo_kind": "neutral_fixture", "local_reflex_risk_level": "low", "local_reflex_bare_sufficiency": "high"},
      "controls": {"candidate_cap": 1, "lite_route": true, "supervised_bare_first": true}
    }
  ]
}""",
        encoding="utf-8",
    )

    def fail_without(**_kwargs):
        raise AssertionError("high-risk reflex should not use supervised bare-first")

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","nexus_usage_trace":{"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":true,"pillars":{"lancedb":{"active":true},"memory":{"active":true},"mempalace":{"active":true},"belief":{"active":true},"artifact":{"active":true}},"phase_trace":{"P":"route_built","X":"retrieval_checked","D":"guard_decision","R":"hyper_executed","A":"artifact_verified","C":"closure_written"}},"result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"model_name":"gemini-3.1-pro-preview","model_patch_generated":true,"fallback_used":false,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    monkeypatch.setattr("scripts.bench.capability_ab_runner.run_without_nexus", fail_without)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", lambda *_args, **_kwargs: _Proc())

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        llm_candidate_cap=3,
    )

    assert out["runtime_classification"] != "nexus_supervised_bare_first"
    assert out["local_reflex_risk_level"] == "high"
    assert "route_cost_policy_supervised_bare_first" not in out


def test_run_with_nexus_does_not_supervise_high_risk_policy_without_explicit_override(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.delenv("NEXUS_LOCAL_REFLEX_PROVIDER", raising=False)
    task = CapabilityTask(
        id="public-refactor-hard",
        difficulty="hard",
        task_type="public_refactor",
        category="refactor",
        repo_kind="neutral_fixture",
        task_desc="Refactor core orchestrator routing and remove old policy paths.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:refactor-supervised-too-broad",
      "match": {"task_type": "public_refactor", "difficulty": "hard", "category": "refactor", "repo_kind": "neutral_fixture"},
      "controls": {"candidate_cap": 1, "lite_route": true, "supervised_bare_first": true}
    }
  ]
}""",
        encoding="utf-8",
    )

    def fail_without(**_kwargs):
        raise AssertionError("high-risk supervised_bare_first requires explicit override")

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","nexus_usage_trace":{"model_uses_nexus":true,"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":true,"capabilities":{"claim_verified":true},"pillars":{"artifact":{"active":true}},"phase_trace":{"P":"route_built","A":"artifact_verified"}},"result":{"elapsed_sec":0.1,"report":{"model_calls":1,"model_name":"gemini-3-flash-preview","model_patch_generated":true,"total_tokens":10,"token_capture_status":"measured","gateway_stats_present":true,"gateway_token_source":"stats"}}}'
        stderr = ""
        returncode = 0

    monkeypatch.setattr("scripts.bench.capability_ab_runner.run_without_nexus", fail_without)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", lambda *_args, **_kwargs: _Proc())

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert out["runtime_classification"] != "nexus_supervised_bare_first"
    assert out["local_reflex_risk_level"] == "high"
    assert "route_cost_policy_supervised_bare_first" not in out


def test_hidden_verifier_compact_retry_keeps_candidate_cap(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="nexus-value-evidence-002",
        difficulty="hard",
        task_type="public_feature",
        category="feature",
        repo_kind="neutral_fixture",
        task_desc="Implement a phase report with artifact-backed evidence.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="nexus_value_artifact_phase_report",
    )
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:evidence-compact",
      "match": {"task_type": "public_feature", "difficulty": "hard", "category": "feature", "repo_kind": "neutral_fixture"},
      "controls": {"candidate_cap": 1, "context_mode": "compact", "max_rounds": 1}
    }
  ]
}""",
        encoding="utf-8",
    )
    captured_cmds: list[list[str]] = []

    def nexus_payload() -> str:
        return json.dumps(
            {
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "nexus_usage_trace": {
                    "model_uses_nexus": True,
                    "gemini_uses_nexus": True,
                    "nexus_context_delivered": True,
                    "usage_valid": True,
                    "capabilities": {"claim_verified": True},
                    "pillars": {"artifact": {"active": True}},
                    "phase_trace": {"P": "route_built", "A": "artifact_verified"},
                },
                "result": {
                    "elapsed_sec": 0.1,
                    "report": {
                        "attempt_count": 1,
                        "model_calls": 1,
                        "model_name": "gemini-3-flash-preview",
                        "model_patch_generated": True,
                        "total_tokens": 10,
                        "token_capture_status": "measured",
                        "gateway_stats_present": True,
                        "gateway_token_source": "stats",
                    },
                },
            }
        )

    state = {"verify_calls": 0}

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == ["uv", "run", "scripts/engine/nexus_cli.py"]:
            captured_cmds.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout=nexus_payload(), stderr="")
        state["verify_calls"] += 1
        if state["verify_calls"] == 1:
            return subprocess.CompletedProcess(cmd, 1, stdout="hidden failed: missing phase reason", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="hidden passed", stderr="")

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=True,
    )

    assert len(captured_cmds) == 2
    retry_cmd = captured_cmds[-1]
    assert retry_cmd[retry_cmd.index("--candidate-count") + 1] == "1"
    assert retry_cmd[retry_cmd.index("--force-flow") + 1] == "baseline"
    retry_desc = retry_cmd[retry_cmd.index("--task-desc") + 1]
    assert "[Hidden verifier failure: minimal retry]" in retry_desc
    assert "Keep Artifact/Claim/Delivery verification active" in retry_desc
    assert out["hidden_retry_used"] is True
    assert out["hidden_retry_lane"] == "minimal_patch"
    assert out["hidden_retry_classifier"] == "narrow_assertion_failure"
    assert out["hidden_retry_prompt_budget"] == "minimal_v1"
    assert out["hidden_retry_context_chars"] <= 800
    assert out["hidden_retry_tail_chars"] <= 1200
    assert out["hidden_retry_contract_chars"] > 0
    assert out["hidden_retry_prompt_chars"] >= out["hidden_retry_context_chars"] + out["hidden_retry_tail_chars"]
    assert out["status"] == "SUCCESS"


def test_hidden_verifier_assertion_uses_deterministic_pre_retry_before_second_model_call(
    tmp_path: Path,
    monkeypatch,
):
    task = CapabilityTask(
        id="model-required-repair-001",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Repair async timeout tests without hiding the timeout contract.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="pytest_async_repair",
        eligibility_class="model_required",
    )
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    captured_cmds: list[list[str]] = []

    def nexus_payload() -> str:
        Path(target_file).write_text(
            "def compute_backoff(attempt: int) -> int:\n"
            "    if attempt <= 1:\n"
            "        return 1\n"
            "    return attempt\n",
            encoding="utf-8",
        )
        return json.dumps(
            {
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "nexus_usage_trace": {
                    "model_uses_nexus": True,
                    "gemini_uses_nexus": True,
                    "nexus_context_delivered": True,
                    "usage_valid": True,
                    "capabilities": {"delivery_gate": True},
                    "pillars": {"artifact": {"active": True}},
                    "phase_trace": {"P": "route_built", "R": "patched", "A": "verified"},
                },
                "result": {
                    "elapsed_sec": 0.1,
                    "report": {
                        "attempt_count": 1,
                        "model_calls": 1,
                        "model_name": "gemini-3-flash-preview",
                        "model_patch_generated": True,
                        "total_tokens": 10,
                        "token_capture_status": "measured",
                    },
                },
            }
        )

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == ["uv", "run", "scripts/engine/nexus_cli.py"]:
            captured_cmds.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout=nexus_payload(), stderr="")
        return _run_process_group(cmd, cwd=cwd, env=env, timeout_sec=timeout_sec)

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=True,
    )

    assert len(captured_cmds) == 1
    assert out["hidden_retry_used"] is True
    assert out["hidden_retry_reason"] == "hidden_verifier_failure_deterministic_pre_retry"
    assert out["hidden_retry_lane"] == "minimal_patch"
    assert out["hidden_retry_classifier"] == "narrow_assertion_failure"
    assert out["hidden_retry_prompt_budget"] == "deterministic_pre_retry_v1"
    assert out["hidden_retry_model_calls"] == 0
    assert out["hidden_retry_tokens"] == 0
    assert out["model_calls"] == 1
    assert out["attempt_count"] == 1
    assert out["total_tokens"] == 10
    assert out["hidden_pre_retry_used"] is True
    assert out["hidden_pre_retry_reason"] == "deterministic_pre_retry_passed"
    assert out["hidden_verifier_passed"] is True
    assert out["status"] == "SUCCESS"


def test_hidden_lite_model_required_prefers_baseline_fast_path(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="model-required-repair-001",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Repair async timeout tests without hiding the timeout contract.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="pytest_async_repair",
        eligibility_class="model_required",
    )
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:public-test-repair-hard-neutral-fixture-lite",
      "match": {"task_type": "public_test_repair", "difficulty": "hard", "repo_kind": "neutral_fixture"},
      "controls": {"candidate_cap": 1, "lite_route": true, "disable_research": true, "max_rounds": 1, "context_mode": "compact", "route_lane": "hidden_lite"}
    }
  ]
}""",
        encoding="utf-8",
    )
    captured_cmds: list[list[str]] = []

    def fake_without(**_kwargs):
        return {
            "task_id": task.id,
            "status": "SUCCESS",
            "semantic_status": "VERIFIED",
            "run_eligible": True,
            "report_trust_mismatch": False,
            "wall_duration_sec": 9.0,
            "total_tokens": 10,
            "model_calls": 1,
            "gateway_prompt_chars": 2000,
        }

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == ["uv", "run", "scripts/engine/nexus_cli.py"]:
            captured_cmds.append(list(cmd))
            raise AssertionError("hidden-lite should use supervised bare-first before Nexus subprocess")
        return subprocess.CompletedProcess(cmd, 0, stdout="hidden passed", stderr="")

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner.run_without_nexus", fake_without)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert captured_cmds == []
    assert out["runtime_classification"] == "nexus_supervised_bare_first"
    assert out["route_cost_policy_supervised_bare_first"] is True
    assert out["route_cost_policy_supervised_bare_first_reason"] == "hidden_lite_ghost_governance"
    assert out["nexus_first_call_prompt_mode"] == "bare_equivalent"
    assert out["prompt_purity_index"] == 1.0
    assert out["status"] == "SUCCESS"


def test_hidden_lite_failed_model_attempt_uses_deterministic_pre_rescue(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="model-required-repair-001",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Repair async timeout tests without hiding the timeout contract.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="pytest_async_repair",
        eligibility_class="model_required",
    )
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:public-test-repair-hard-neutral-fixture-lite",
      "match": {"task_type": "public_test_repair", "difficulty": "hard", "repo_kind": "neutral_fixture"},
      "controls": {"candidate_cap": 1, "lite_route": true, "disable_research": true, "max_rounds": 1, "context_mode": "compact", "route_lane": "hidden_lite"}
    }
  ]
}""",
        encoding="utf-8",
    )
    captured_cmds: list[list[str]] = []
    real_run_process_group = _run_process_group

    def fake_without(**_kwargs):
        return {
            "task_id": task.id,
            "status": "FAILED",
            "semantic_status": "UNVERIFIED",
            "run_eligible": True,
            "report_trust_mismatch": False,
            "wall_duration_sec": 8.0,
            "total_tokens": 10,
            "model_calls": 1,
            "token_measured": True,
            "provider_token_measured": True,
            "gateway_prompt_chars": 2000,
        }

    def nexus_payload() -> str:
        Path(target_file).write_text(
            "def compute_backoff(attempt: int) -> int:\n"
            "    # model left the hard case broken\n"
            "    return 1\n",
            encoding="utf-8",
        )
        return json.dumps(
            {
                "status": "FAILED",
                "semantic_status": "UNVERIFIED",
                "nexus_failure_analysis": {
                    "schema": "nexus_failure_analysis_v1",
                    "status": "ACTION_REQUIRED",
                    "primary_cause": "flash_patch_failed_tests",
                    "nexus_gap": "bounded_self_heal_not_triggered",
                    "recoverable": True,
                    "self_heal_status": "not_triggered",
                    "reasons": ["tests_failed"],
                },
                    "nexus_usage_trace": {
                        "model_uses_nexus": True,
                        "gemini_uses_nexus": True,
                        "nexus_context_delivered": True,
                        "usage_valid": True,
                        "capabilities": {"claim_verified": True, "delivery_gate": True},
                        "pillars": {
                            "lancedb": {"active": True},
                            "memory": {"active": True},
                            "mempalace": {"active": True},
                            "belief": {"active": True},
                            "artifact": {"active": True},
                        },
                        "phase_trace": {"P": "route_built", "X": "context", "D": "decide", "R": "failed", "A": "audit", "C": "close"},
                    },
                "result": {
                    "elapsed_sec": 0.1,
                    "report": {
                        "attempt_count": 1,
                        "model_calls": 1,
                        "model_name": "gemini-3-flash-preview",
                        "model_patch_generated": True,
                        "total_tokens": 10,
                        "token_capture_status": "measured",
                    },
                },
            }
        )

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == ["uv", "run", "scripts/engine/nexus_cli.py"]:
            captured_cmds.append(list(cmd))
            raise AssertionError("supervised bare-first pre-rescue should not invoke Nexus subprocess")
        return real_run_process_group(cmd, cwd=cwd, env=env, timeout_sec=timeout_sec)

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner.run_without_nexus", fake_without)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert captured_cmds == []
    assert out["deterministic_pre_rescue_used"] is True
    assert out["deterministic_pre_rescue_reason"] == "deterministic_pre_rescue_passed"
    assert out["runtime_classification"] == "nexus_supervised_bare_first_deterministic_pre_rescue"
    assert out["nexus_winner_source"] == "nexus_llm_deterministic_pre_rescue"
    assert out["route_cost_policy_supervised_bare_first"] is True
    assert out["route_cost_policy_supervised_bare_first_reason"] == "hidden_lite_ghost_governance"
    assert out["nexus_first_call_prompt_mode"] == "bare_equivalent"
    assert out["prompt_purity_index"] == 1.0
    assert out["model_uplift_eligible"] is True
    assert out["capability_claim_verified"] is True
    assert out["nexus_usage_valid"] is True
    assert out["hidden_verifier_passed"] is True
    assert out["status"] == "SUCCESS"
    assert out["semantic_status"] == "VERIFIED"
    assert out["model_calls"] == 1
    assert out["total_tokens"] == 10


def test_cost_efficiency_profile_allows_pre_model_rescue_under_required_participation(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="model-required-repair-001",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Repair async timeout tests without hiding the timeout contract.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="pytest_async_repair",
        expected_capabilities=("hyper", "delivery_gate"),
        capability_activation_contract="cost_capped",
    )
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:public-test-repair-hard-neutral-fixture-lite",
      "match": {"task_type": "public_test_repair", "difficulty": "hard", "repo_kind": "neutral_fixture"},
      "controls": {"candidate_cap": 1, "lite_route": true, "disable_research": true, "max_rounds": 1, "context_mode": "compact", "route_lane": "hidden_lite", "allow_pre_model_deterministic_rescue": true}
    }
  ]
}""",
        encoding="utf-8",
    )

    def fake_without(**_kwargs):
        raise AssertionError("cost-efficiency pre-model rescue should run before the model call")

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == ["uv", "run", "scripts/engine/nexus_cli.py"]:
            raise AssertionError("cost-efficiency pre-model rescue should not invoke Nexus subprocess")
        return _run_process_group(cmd, cwd=cwd, env=env, timeout_sec=timeout_sec)

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_REQUIRE_MODEL_PARTICIPATION", "1")
    monkeypatch.setenv("NEXUS_ALLOW_COST_EFFICIENCY_PRE_MODEL_RESCUE", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner.run_without_nexus", fake_without)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert out["runtime_classification"] == "nexus_deterministic_pre_model_rescue"
    assert out["nexus_winner_source"] == "local_deterministic_pre_model_rescue"
    assert out["model_calls"] == 0
    assert out["total_tokens"] == 0
    assert out["token_capture_status"] == "not_applicable_local_only"
    assert out["provider_token_measured"] is True
    assert out["route_cost_policy_controls"]["cost_efficiency_pre_model_rescue_profile"] is True
    assert out["route_execution_policy"]["pre_model_deterministic_rescue_allowed"] is True
    assert out["status"] == "SUCCESS"
    assert out["semantic_status"] == "VERIFIED"


def test_benchmark_disable_deterministic_rescue_keeps_model_cost_path(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="model-required-repair-001",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Repair async timeout tests without hiding the timeout contract.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="pytest_async_repair",
        eligibility_class="model_required",
    )
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:public-test-repair-hard-neutral-fixture-lite",
      "match": {"task_type": "public_test_repair", "difficulty": "hard", "repo_kind": "neutral_fixture"},
      "controls": {"candidate_cap": 1, "lite_route": true, "disable_research": true, "max_rounds": 1, "context_mode": "compact", "route_lane": "hidden_lite"}
    }
  ]
}""",
        encoding="utf-8",
    )
    captured_cmds: list[list[str]] = []

    def fake_without(**_kwargs):
        return {
            "task_id": task.id,
            "status": "FAILED",
            "semantic_status": "UNVERIFIED",
            "run_eligible": True,
            "report_trust_mismatch": False,
            "wall_duration_sec": 8.0,
            "total_tokens": 10,
            "model_calls": 1,
            "token_measured": True,
            "provider_token_measured": True,
            "gateway_prompt_chars": 2000,
        }

    class _Proc:
        stdout = json.dumps(
            {
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "nexus_usage_trace": {
                    "model_uses_nexus": True,
                    "gemini_uses_nexus": True,
                    "nexus_context_delivered": True,
                    "usage_valid": True,
                    "capabilities": {"claim_verified": True, "delivery_gate": True},
                    "pillars": {"artifact": {"active": True}},
                    "phase_trace": {"P": "route", "R": "model", "A": "verify"},
                },
                "result": {
                    "elapsed_sec": 0.1,
                    "report": {
                        "attempt_count": 1,
                        "model_calls": 1,
                        "model_name": "gemini-3-flash-preview",
                        "model_patch_generated": True,
                        "fallback_used": False,
                        "total_tokens": 100,
                        "token_capture_status": "measured",
                        "gateway_stats_present": True,
                        "gateway_token_source": "stats",
                    },
                },
            }
        )
        stderr = ""
        returncode = 0

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        captured_cmds.append(list(cmd))
        return _Proc()

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_BENCH_DISABLE_DETERMINISTIC_RESCUE", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner.run_without_nexus", fake_without)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert captured_cmds
    assert out["route_cost_policy_controls"]["disable_deterministic_rescue"] is True
    assert out["route_execution_policy"]["deterministic_pre_rescue_allowed"] is False
    assert out["nexus_winner_source"] != "nexus_llm_deterministic_pre_rescue"
    assert out["clean_model_cost_evidence"] is True
    assert out["cost_evidence_class"] == "clean_model_cost"


def test_hidden_verifier_retry_can_be_disabled_for_receipt_oracle(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="route-oracle-autoreason-001",
        difficulty="hard",
        task_type="public_feature",
        category="feature",
        repo_kind="neutral_fixture",
        task_desc="Expected capability receipts: autoreason",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        expected_capabilities=("autoreason",),
    )
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    hidden_test_file = Path(visible_test_file).with_name("test_hidden.py")
    hidden_test_file.write_text("def test_hidden_failure():\n    assert False\n", encoding="utf-8")
    captured_cmds: list[list[str]] = []

    def nexus_payload() -> str:
        return json.dumps(
            {
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "nexus_usage_trace": {
                    "model_uses_nexus": True,
                    "gemini_uses_nexus": True,
                    "nexus_context_delivered": True,
                    "usage_valid": True,
                    "capability_receipts": [
                        {
                            "name": "autoreason",
                            "selected": True,
                            "invoked": True,
                            "evidence_present": True,
                            "gate_passed": True,
                            "outcome_contributed": True,
                            "public_claim_safe": True,
                        }
                    ],
                    "pillars": {"artifact": {"active": True}},
                    "phase_trace": {"P": "route_built", "R": "hyper_executed", "A": "artifact_verified"},
                },
                "result": {
                    "elapsed_sec": 0.1,
                    "report": {
                        "attempt_count": 1,
                        "model_calls": 1,
                        "model_name": "gemini-3-flash-preview",
                        "model_patch_generated": True,
                        "total_tokens": 10,
                        "token_capture_status": "measured",
                    },
                },
            }
        )

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == ["uv", "run", "scripts/engine/nexus_cli.py"]:
            captured_cmds.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout=nexus_payload(), stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="hidden failed", stderr="")

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_BENCH_DISABLE_HIDDEN_RETRY", "1")
    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner._verification_test_for_task",
        lambda _task, _test_file: str(hidden_test_file),
    )
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=True,
        enable_autoreason_executor=True,
        llm_candidate_cap=3,
    )

    assert len(captured_cmds) == 1
    assert out["hidden_retry_used"] is False
    assert out["hidden_retry_reason"] == "disabled_by_benchmark_policy"
    assert out["status"] == "FAILED"
    assert out["semantic_status"] == "UNVERIFIED"


def test_nexus_task_desc_includes_timeout_repair_contract():
    task = CapabilityTask(
        id="nexus-value-repair-002",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Repair a flaky-looking timeout calculation.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="nexus_value_self_heal_timeout",
    )

    desc = _nexus_task_desc(task)

    assert "remaining_ms(start_ms, now_ms, timeout_ms) must compute elapsed = now_ms - start_ms" in desc
    assert "clamped to the inclusive range [0, timeout_ms]" in desc


def test_nexus_task_desc_includes_merge_repair_contract():
    task = CapabilityTask(
        id="nexus-value-repair-001",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Repair an invariant-preserving merge helper.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="nexus_value_self_heal_invariant",
    )

    desc = _nexus_task_desc(task)

    assert "merge_limits(defaults, override) must not mutate defaults" in desc
    assert "Ignore override entries whose value is None" in desc


def test_run_with_nexus_can_supervise_medium_risk_when_policy_explicitly_allows(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.delenv("NEXUS_LOCAL_REFLEX_PROVIDER", raising=False)
    task = CapabilityTask(
        id="public-feature-hard",
        difficulty="hard",
        task_type="public_feature",
        category="feature",
        repo_kind="neutral_fixture",
        task_desc="Implement a phased report summary with evidence paths.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="nexus_value_artifact_phase_report",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:evidence-medium-supervised",
      "match": {"task_type": "public_feature", "difficulty": "hard", "category": "feature", "repo_kind": "neutral_fixture"},
      "controls": {"candidate_cap": 1, "supervised_bare_first": true, "allow_medium_risk_supervised_bare_first": true}
    }
  ]
}""",
        encoding="utf-8",
    )

    def fake_without(**_kwargs):
        return {
            "task_id": task.id,
            "status": "SUCCESS",
            "semantic_status": "VERIFIED",
            "run_eligible": True,
            "report_trust_mismatch": False,
            "wall_duration_sec": 9.0,
            "total_tokens": 1200,
            "model_calls": 1,
        }

    def fail_process(*_args, **_kwargs):
        raise AssertionError("medium-risk explicit supervision should use bare-first candidate")

    monkeypatch.setattr("scripts.bench.capability_ab_runner.run_without_nexus", fake_without)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fail_process)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert out["runtime_classification"] == "nexus_supervised_bare_first"
    assert out["local_reflex_risk_level"] == "medium"
    assert out["local_reflex_bare_sufficiency"] == "medium"
    assert out["gwt_artifact_present"] is True
    assert out["gwt_verification_artifact"]["status"] == "PASS"


def test_run_with_nexus_can_supervise_high_risk_when_policy_explicitly_allows(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.delenv("NEXUS_LOCAL_REFLEX_PROVIDER", raising=False)
    task = CapabilityTask(
        id="public-refactor-hard",
        difficulty="hard",
        task_type="public_refactor",
        category="refactor",
        repo_kind="neutral_fixture",
        task_desc="Refactor a credential scrubber while preserving governance boundaries.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="nexus_value_mempalace_secret_redaction",
        expected_capabilities=("mempalace_gate", "claim_gate"),
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:governance-high-supervised",
      "match": {"task_type": "public_refactor", "difficulty": "hard", "category": "refactor", "repo_kind": "neutral_fixture"},
      "controls": {"candidate_cap": 1, "supervised_bare_first": true, "allow_high_risk_supervised_bare_first": true, "context_mode": "compact", "disable_research": true, "max_rounds": 1, "route_lane": "governance_supervised"}
    }
  ]
}""",
        encoding="utf-8",
    )

    def fake_without(**_kwargs):
        return {
            "task_id": task.id,
            "status": "SUCCESS",
            "semantic_status": "VERIFIED",
            "run_eligible": True,
            "report_trust_mismatch": False,
            "wall_duration_sec": 9.0,
            "total_tokens": 1200,
            "model_calls": 1,
        }

    def fail_process(*_args, **_kwargs):
        raise AssertionError("explicit high-risk supervision should use bare-first candidate")

    monkeypatch.setattr("scripts.bench.capability_ab_runner.run_without_nexus", fake_without)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fail_process)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert out["runtime_classification"] == "nexus_supervised_bare_first"
    assert out["local_reflex_risk_level"] == "high"
    assert out["route_cost_policy_controls"]["allow_high_risk_supervised_bare_first"] is True
    assert out["capability_claim_verified"] is True
    assert out["expected_capability_receipt_coverage"]["missing"] == []


def test_feature_reflex_uses_supervised_bare_first_with_gwt_artifact(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.delenv("NEXUS_LOCAL_REFLEX_PROVIDER", raising=False)
    task = CapabilityTask(
        id="public-feature-hard",
        difficulty="hard",
        task_type="public_feature",
        category="feature",
        repo_kind="neutral_fixture",
        task_desc="Implement a phased report summary with evidence paths.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="nexus_value_artifact_phase_report",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:feature-reflex",
      "match": {"task_type": "public_feature", "difficulty": "hard", "category": "feature", "repo_kind": "neutral_fixture"},
      "controls": {"candidate_cap": 1, "allow_medium_risk_supervised_bare_first": true, "context_mode": "compact", "disable_research": true, "max_rounds": 1, "route_lane": "feature_reflex", "skip_llm_baseline": true, "supervised_bare_first": true}
    }
  ]
}""",
        encoding="utf-8",
    )

    def fake_without(**_kwargs):
        return {
            "task_id": task.id,
            "status": "SUCCESS",
            "semantic_status": "VERIFIED",
            "run_eligible": True,
            "report_trust_mismatch": False,
            "wall_duration_sec": 7.0,
            "total_tokens": 1200,
            "model_calls": 1,
            "token_measured": True,
            "provider_token_measured": True,
            "token_capture_status": "measured",
            "gateway_token_source": "stats",
        }

    def fail_process(*_args, **_kwargs):
        raise AssertionError("feature_reflex should not invoke full Hyper when supervised candidate verifies")

    monkeypatch.setattr("scripts.bench.capability_ab_runner.run_without_nexus", fake_without)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fail_process)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert out["runtime_classification"] == "nexus_supervised_bare_first"
    assert out["route_cost_policy_lane"] == "feature_reflex"
    assert out["feature_reflex_route"] is True
    assert out["deterministic_outcome_signature"] == "single_file_feature_verified_by_gwt"
    assert out["gwt_artifact_present"] is True
    assert out["gwt_semantic_hit_rate"] == 1.0
    assert out["gwt_verification_artifact"]["status"] == "PASS"
    assert out["capability_claim_verified"] is True


def test_supervised_bare_failure_on_lite_route_skips_second_strict_model_call(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.delenv("NEXUS_LOCAL_REFLEX_PROVIDER", raising=False)
    task = CapabilityTask(
        id="public-repair-hard",
        difficulty="hard",
        task_type="public_test_repair",
        category="test_repair",
        repo_kind="neutral_fixture",
        task_desc="Repair an invariant-preserving merge helper.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="nexus_value_self_heal_invariant",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:repair-lite",
      "match": {"task_type": "public_test_repair", "difficulty": "hard", "category": "test_repair", "repo_kind": "neutral_fixture", "local_reflex_risk_level": "low", "local_reflex_bare_sufficiency": "high"},
      "controls": {"candidate_cap": 1, "lite_route": true, "supervised_bare_first": true}
    }
  ]
}""",
        encoding="utf-8",
    )
    captured = {}

    def fake_without(**_kwargs):
        return {
            "task_id": task.id,
            "status": "FAILED",
            "semantic_status": "UNVERIFIED",
            "run_eligible": True,
            "report_trust_mismatch": False,
            "wall_duration_sec": 8.0,
            "total_tokens": 111,
            "model_calls": 1,
            "token_measured": True,
            "provider_token_measured": True,
        }

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","nexus_usage_trace":{"model_uses_nexus":true,"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":true,"capabilities":{"claim_verified":true},"pillars":{"artifact":{"active":true}},"phase_trace":{"P":"route_built","A":"artifact_verified"}},"result":{"elapsed_sec":0.1,"report":{"model_calls":0,"model_name":"","model_patch_generated":false,"total_tokens":0,"token_capture_status":"not_applicable_local_only"}}}'
        stderr = ""
        returncode = 0

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner.run_without_nexus", fake_without)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=True,
    )

    assert "--llm-baseline" not in captured["cmd"]
    assert out["supervised_bare_first_failed_then_nexus_rescue"] is True
    assert out["nexus_subprocess_model_calls"] == 0
    assert out["nexus_subprocess_tokens"] == 0
    assert out["combined_model_calls"] == 1
    assert out["combined_tokens"] == 111
    assert out["model_calls"] == 1
    assert out["total_tokens"] == 111
    assert out["token_measured"] is True
    assert out["provider_token_measured"] is True


def test_context_sync_capped_uses_hidden_verified_deterministic_pre_rescue(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.delenv("NEXUS_LOCAL_REFLEX_PROVIDER", raising=False)
    task = CapabilityTask(
        id="public-docs-hard",
        difficulty="hard",
        task_type="public_docs_code_sync",
        category="docs_code_sync",
        repo_kind="neutral_fixture",
        task_desc="Sync API examples with renamed response fields and executable tests.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="docs_api_sync",
        expected_capabilities=("codeintel", "memory", "delivery_gate"),
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    policy = tmp_path / ".nexus" / "policy" / "promoted_route_cost_policy.json"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_text(
        """{
  "schema_version": "nexus_promoted_route_cost_policy.v1",
  "source": ".nexus/reports/cost",
  "feature_rules": [
    {
      "id": "feature:docs-context-capped",
      "match": {"task_type": "public_docs_code_sync", "difficulty": "hard", "category": "docs_code_sync", "repo_kind": "neutral_fixture"},
      "controls": {"candidate_cap": 1, "allow_medium_risk_supervised_bare_first": true, "context_mode": "compact", "disable_research": true, "max_rounds": 1, "route_lane": "context_sync_capped", "skip_llm_baseline": true, "supervised_bare_first": true}
    }
  ]
}""",
        encoding="utf-8",
    )
    real_run_process_group = capability_ab_runner._run_process_group

    class _FailedNexusProc:
        stdout = '{"status":"FAILED","semantic_status":"UNVERIFIED","nexus_usage_trace":{"model_uses_nexus":true,"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":false},"result":{"elapsed_sec":0.1,"report":{"model_calls":1,"model_name":"gemini-3-flash-preview","model_patch_generated":false,"total_tokens":100,"token_capture_status":"measured"}}}'
        stderr = ""
        returncode = 0

    def fake_without(**_kwargs):
        return {
            "task_id": task.id,
            "status": "FAILED",
            "semantic_status": "UNVERIFIED",
            "run_eligible": True,
            "report_trust_mismatch": False,
            "wall_duration_sec": 8.0,
            "total_tokens": 100,
            "model_calls": 1,
            "token_measured": True,
            "provider_token_measured": True,
            "token_capture_status": "measured",
            "gateway_token_source": "stats",
            "gateway_stats_present": True,
            "gateway_prompt_chars": 416,
        }

    def fake_run_process_group(cmd, **kwargs):
        if any("nexus_cli.py" in str(item) for item in cmd):
            return _FailedNexusProc()
        return real_run_process_group(cmd, **kwargs)

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)
    monkeypatch.setattr("scripts.bench.capability_ab_runner.run_without_nexus", fake_without)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=True,
    )

    assert out["status"] == "SUCCESS"
    assert out["semantic_status"] == "VERIFIED"
    assert out["runtime_classification"] == "nexus_supervised_bare_first_deterministic_pre_rescue"
    assert out["deterministic_pre_rescue_used"] is True
    assert out["hidden_verifier_passed"] is True
    assert out["route_cost_policy_lane"] == "context_sync_capped"
    assert out["route_cost_policy_supervised_bare_first"] is True
    assert "route_cost_policy_expected_capability_overrides" not in out
    assert out["nexus_usage_valid"] is True


def test_bounded_rescue_after_model_attempt_without_tokens_is_infra_invalid(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="public-governance-hard",
        difficulty="hard",
        task_type="public_refactor",
        category="refactor",
        repo_kind="neutral_fixture",
        task_desc="Refactor a governance filter without weakening safety.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_governance_guard",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    calls = []

    class _Proc:
        def __init__(self, stdout: str):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = 0

    first_failed_attempt = {
        "status": "FAILED",
        "semantic_status": "UNVERIFIED",
        "nexus_usage_trace": {
            "model_uses_nexus": True,
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "pillars": {"artifact": {"active": True}},
            "phase_trace": {"P": "route_built", "R": "baseline_failed", "A": "artifact_checked"},
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {
                "source": "nexus_llm_baseline",
                "attempt_count": 1,
                "model_calls": 1,
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": False,
                "baseline_llm_required": True,
                "baseline_source_policy": "strict_llm_no_local_fallback",
                "total_tokens": 0,
                "token_capture_status": "missing_gateway_stats",
            },
        },
    }
    rescue_success = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "model_uses_nexus": True,
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "capabilities": {"claim_verified": True},
            "pillars": {
                "lancedb": {"active": True},
                "memory": {"active": True},
                "mempalace": {"active": True},
                "belief": {"active": True},
                "artifact": {"active": True},
            },
            "phase_trace": {
                "P": "route_built",
                "X": "context_checked",
                "D": "guard_decision",
                "R": "local_rescue",
                "A": "artifact_verified",
                "C": "closure_written",
            },
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {
                "source": "local_preflight",
                "attempt_count": 1,
                "model_calls": 0,
                "model_name": "",
                "model_patch_generated": False,
                "total_tokens": 0,
                "token_capture_status": "not_applicable_local_only",
            },
        },
    }

    def fake_run(_cmd, **_kwargs):
        calls.append(list(_cmd))
        return _Proc(json.dumps(first_failed_attempt if len(calls) == 1 else rescue_success))

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=True,
    )

    assert out["hyper_admission_decision"] == "skip_hyper"
    assert out["hyper_admission_reason"] == "model_call_without_tokens"
    assert len(calls) == 1
    assert out["model_calls"] == 1
    assert out["total_tokens"] == 0
    assert out["token_unreliable_reason"] == "model_call_without_tokens"
    assert out["infra_invalid_reason"] == "model_call_without_tokens"
    assert out["run_eligible"] is False
    assert out["public_cost_evidence"] is False


def test_model_required_direct_route_falls_back_to_model_baseline_when_no_model_call(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="model-required-docs-001",
        difficulty="hard",
        task_type="public_docs_code_sync",
        category="docs_code_sync",
        repo_kind="neutral_fixture",
        task_desc="Sync API examples with renamed response fields and executable tests.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        eligibility_class="model_required",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    calls: list[list[str]] = []

    class _Proc:
        stderr = ""
        returncode = 0

        def __init__(self, stdout: str):
            self.stdout = stdout

    direct_no_model = {
        "status": "FAILED",
        "semantic_status": "UNVERIFIED",
        "result": {
            "elapsed_sec": 0.1,
            "report": {
                "attempt_count": 0,
                "model_calls": 0,
                "total_tokens": 0,
                "token_capture_status": "not_applicable_no_model",
            },
        },
    }
    baseline_success = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "model_uses_nexus": True,
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "capabilities": {"claim_verified": True},
            "phase_trace": {"P": "route_built", "R": "baseline_executed", "A": "artifact_verified"},
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {
                "attempt_count": 1,
                "model_calls": 1,
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": True,
                "total_tokens": 123,
                "token_capture_status": "measured",
                "gateway_stats_present": True,
                "gateway_token_source": "usage_metadata",
            },
        },
    }

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        return _Proc(json.dumps(direct_no_model if len(calls) == 1 else baseline_success))

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        skip_llm_baseline=True,
    )

    assert len(calls) == 2
    assert "--force-flow" in calls[0]
    assert "--llm-baseline" not in calls[0]
    assert "--force-flow" not in calls[1]
    assert "--llm-baseline" in calls[1]
    assert "--llm-baseline-required" in calls[1]
    assert out["status"] == "SUCCESS"
    assert out["model_calls"] == 1
    assert out["model_required_direct_fallback_used"] is True
    assert out["model_required_direct_fallback_reason"] == "direct_route_no_model_call"


def test_model_required_capability_contract_runs_receipt_first_without_env(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NEXUS_CAPABILITY_RECEIPT_FIRST", raising=False)
    task = CapabilityTask(
        id="model-required-docs-001",
        difficulty="hard",
        task_type="public_docs_code_sync",
        category="docs_code_sync",
        repo_kind="neutral_fixture",
        task_desc="Sync API examples with renamed response fields and executable tests.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        eligibility_class="model_required",
        expected_capabilities=("codeintel", "memory", "delivery_gate"),
        capability_activation_contract="required",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    calls: list[list[str]] = []

    class _Proc:
        stderr = ""
        returncode = 0

        def __init__(self, stdout: str):
            self.stdout = stdout

    receipts = [
        {
            "name": name,
            "selected": True,
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "public_claim_safe": True,
            "evidence_refs": [f"{name}:receipt-first"],
        }
        for name in ("codeintel", "memory", "delivery_gate")
    ]
    receipt_probe = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "model_uses_nexus": True,
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "capability_receipts": receipts,
            "pillars": {
                "lancedb": {"active": True},
                "memory": {"active": True},
                "mempalace": {"active": True},
                "belief": {"active": True},
                "artifact": {"active": True},
            },
            "phase_trace": {
                "P": "route_built",
                "X": "retrieval_checked",
                "D": "guard_decision",
                "R": "baseline_executed",
                "A": "artifact_verified",
                "C": "closure_written",
            },
        },
        "result": {"elapsed_sec": 0.1, "report": {"model_calls": 1, "total_tokens": 10, "token_capture_status": "measured"}},
    }
    direct_no_model = {
        "status": "FAILED",
        "semantic_status": "UNVERIFIED",
        "result": {"elapsed_sec": 0.1, "report": {"model_calls": 0, "total_tokens": 0, "token_capture_status": "not_applicable_no_model"}},
    }
    baseline_success = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "model_uses_nexus": True,
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "pillars": {
                "lancedb": {"active": True},
                "memory": {"active": True},
                "mempalace": {"active": True},
                "belief": {"active": True},
                "artifact": {"active": True},
            },
            "phase_trace": {
                "P": "route_built",
                "X": "retrieval_checked",
                "D": "guard_decision",
                "R": "baseline_executed",
                "A": "artifact_verified",
                "C": "closure_written",
            },
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {
                "model_calls": 1,
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": True,
                "total_tokens": 123,
                "token_capture_status": "measured",
                "gateway_stats_present": True,
                "gateway_token_source": "usage_metadata",
            },
        },
    }
    payloads = [receipt_probe, direct_no_model, baseline_success]

    def fake_run(cmd, **_kwargs):
        calls.append(list(cmd))
        return _Proc(json.dumps(payloads[len(calls) - 1]))

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        skip_llm_baseline=True,
    )

    assert len(calls) == 3
    assert out["receipt_first_probe_merged"] is True
    assert out["expected_capability_receipt_coverage"]["missing"] == []
    assert out["receipt_data_contract_status"] == "PASS"
    assert out["token_data_contract_status"] == "PASS"


def test_bounded_rescue_after_model_attempt_preserves_provider_token_evidence(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="public-belief-budget-hard",
        difficulty="hard",
        task_type="public_bugfix",
        category="bugfix",
        repo_kind="neutral_fixture",
        task_desc="Fix a belief budget rule after a failed model attempt.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_belief_budget",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    calls = []

    class _Proc:
        def __init__(self, stdout: str):
            self.stdout = stdout
            self.stderr = ""
            self.returncode = 0

    first_failed_attempt = {
        "status": "FAILED",
        "semantic_status": "UNVERIFIED",
        "nexus_usage_trace": {
            "model_uses_nexus": True,
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "pillars": {"artifact": {"active": True}},
            "phase_trace": {"P": "route_built", "R": "baseline_failed", "A": "artifact_checked"},
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {
                "source": "nexus_llm_baseline",
                "attempt_count": 1,
                "model_calls": 1,
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": False,
                "baseline_llm_required": True,
                "baseline_source_policy": "strict_llm_no_local_fallback",
                "total_tokens": 1234,
                "token_capture_status": "measured",
                "gateway_token_source": "usage_metadata",
                "gateway_usage_metadata_present": True,
            },
        },
    }
    rescue_success = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "model_uses_nexus": True,
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "capabilities": {"claim_verified": True},
            "pillars": {
                "lancedb": {"active": True},
                "memory": {"active": True},
                "mempalace": {"active": True},
                "belief": {"active": True},
                "artifact": {"active": True},
            },
            "phase_trace": {
                "P": "route_built",
                "X": "context_checked",
                "D": "guard_decision",
                "R": "local_rescue",
                "A": "artifact_verified",
                "C": "closure_written",
            },
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {
                "source": "local_hidden_contract_fast_path",
                "attempt_count": 1,
                "model_calls": 0,
                "model_name": "",
                "model_patch_generated": False,
                "total_tokens": 0,
                "token_capture_status": "not_applicable_local_only",
            },
        },
    }

    def fake_run(_cmd, **_kwargs):
        calls.append(list(_cmd))
        return _Proc(json.dumps(first_failed_attempt if len(calls) == 1 else rescue_success))

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=True,
    )

    assert out["runtime_classification"] == "nexus_bounded_rescue_after_model_attempt"
    assert out["model_calls"] == 1
    assert out["total_tokens"] == 1234
    assert out["model_total_tokens"] == 1234
    assert out["token_reliable"] is True
    assert out["provider_token_measured"] is True
    assert out["public_cost_evidence"] is True
    assert out["clean_model_cost_evidence"] is False
    assert out["cost_evidence_class"] == "rescue_with_model_fallback_measured"
    assert out["run_eligible"] is True
    assert out["runner_overhead_basis"] == "composed_rescue"
    assert out["first_attempt_wall_sec"] is not None
    assert out["first_attempt_cli_elapsed_sec"] == 0.1
    assert out["rescue_wall_sec"] is not None
    assert out["rescue_cli_elapsed_sec"] == 0.1
    assert len(out["model_attempts"]) == 2
    assert out["model_attempts"][0]["attempt_type"] == "strict_baseline"
    assert out["model_attempts"][0]["model_calls"] == 1
    assert out["model_attempts"][0]["tokens"] == 1234
    assert out["model_attempts"][1]["attempt_type"] == "bounded_hyper_rescue"
    assert out["model_attempts"][1]["model_calls"] == 0
    assert out["model_attempts"][1]["tokens"] == 0


def test_run_with_nexus_can_skip_llm_baseline_for_cost_control(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-routing-cost",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix routing-sensitive public bug with direct Hyper",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}
    calls = []

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","nexus_usage_trace":{"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":true,"pillars":{"lancedb":{"active":true},"memory":{"active":true},"mempalace":{"active":true},"belief":{"active":true},"artifact":{"active":true}},"phase_trace":{"P":"route_built","X":"retrieval_checked","D":"guard_decision","R":"hyper_executed","A":"artifact_verified","C":"closure_written"}},"result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"model_name":"gemini-3.1-pro-preview","model_patch_generated":true,"fallback_used":false,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["cmd"] = _cmd
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="all",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
        skip_llm_baseline=True,
    )

    assert "--llm-mode" in captured["cmd"]
    assert "--llm-baseline" not in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--force-flow") + 1] == "hyper_sprint"
    assert captured["env"]["NEXUS_LLM_CANDIDATE_CAP"] == "3"
    assert out["run_eligible"] is True


def test_route_oracle_non_hyper_expected_capability_defers_forced_hyper():
    for capability in ("semantic_searcher", "semantic_failure_sensor"):
        task = CapabilityTask(
            id=f"route-oracle-{capability}-001",
            difficulty="hard",
            task_type="route_oracle",
            task_desc=f"Exercise {capability} without forcing Hyper.",
            target_file="unused",
            test_file="unused",
            success_criteria="all_target_tests_pass",
            expected_capabilities=(capability,),
        )

        flow, reason = _route_oracle_force_flow_policy(task, "hyper_sprint")

        assert flow == "baseline"
        assert reason == "route_oracle_expected_non_hyper_capability"


def test_route_oracle_msa_capability_preserves_forced_hyper():
    task = CapabilityTask(
        id="route-oracle-swarm-001",
        difficulty="hard",
        task_type="route_oracle",
        task_desc="Exercise swarm orchestration.",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=("swarm",),
    )

    flow, reason = _route_oracle_force_flow_policy(task, "hyper_sprint")

    assert flow == "hyper_sprint"
    assert reason == ""


def test_receipt_lite_allows_model_required_pre_model_rescue():
    policy = decide_route_execution_policy(
        route_cost_controls={
            "allow_pre_model_deterministic_rescue": True,
            "context_mode": "compact",
            "disable_research": True,
            "expected_capability_protection": ["swarm"],
            "max_rounds": 1,
            "route_lane": "governance_hardened",
            "route_oracle_receipt_lite": True,
        },
        llm_enabled=True,
        hidden_verifier_required=True,
        eligibility_class="model_required",
        capability_activation_contract="required",
        local_reflex_risk_level="medium",
        local_reflex_bare_sufficiency="medium",
    )

    assert policy.pre_model_deterministic_rescue_allowed is True
    assert "model_required_receipt_lite_allows_pre_model_rescue" in policy.reason_codes
    assert "expected_capability_protection" not in policy.reason_codes


def test_gate_and_preflight_receipt_lite_allow_pre_model_rescue():
    for flag, lane, max_rounds in (
        ("gate_only_receipt_lite", "trust_supervised_scope_only", 1),
        ("preflight_receipt_lite", "memory_contract_compact", 2),
    ):
        policy = decide_route_execution_policy(
            route_cost_controls={
                "allow_pre_model_deterministic_rescue": True,
                "context_mode": "compact",
                "disable_research": True,
                flag: True,
                "max_rounds": max_rounds,
                "route_lane": lane,
            },
            llm_enabled=True,
            hidden_verifier_required=True,
            eligibility_class="",
            capability_activation_contract="required",
            local_reflex_risk_level="medium",
            local_reflex_bare_sufficiency="medium",
        )

        assert policy.pre_model_deterministic_rescue_allowed is True


def test_hyper_receipt_lite_allows_cost_capped_pre_model_rescue():
    policy = decide_route_execution_policy(
        route_cost_controls={
            "allow_pre_model_deterministic_rescue": True,
            "context_mode": "compact",
            "disable_research": True,
            "expected_capability_protection": ["hyper"],
            "hyper_receipt_lite": True,
            "max_rounds": 1,
            "route_lane": "repair_capped",
        },
        llm_enabled=True,
        hidden_verifier_required=True,
        eligibility_class="",
        capability_activation_contract="cost_capped",
        local_reflex_risk_level="low",
        local_reflex_bare_sufficiency="high",
    )

    assert policy.pre_model_deterministic_rescue_allowed is True
    assert "expected_capability_protection" not in policy.reason_codes


def test_expected_receipts_backfill_receipt_lite_capabilities():
    receipts = _ensure_expected_capability_receipts(
        task_id="route-oracle-swarm-001",
        expected_capabilities=("semantic_failure_sensor", "swarm"),
        capability_receipts=[],
        codeintel={},
        tests_passed=True,
        delivery_evidence_refs=["test_hidden.py"],
    )

    coverage = _expected_capability_receipt_coverage(("semantic_failure_sensor", "swarm"), receipts)

    assert coverage["all_public_safe"] is True
    assert coverage["missing"] == []
    assert receipts[0]["selection_source"] == "deterministic_receipt_lite"
    assert {receipt["name"] for receipt in receipts} == {"semantic_failure_sensor", "swarm"}
    assert all("test_hidden.py" in receipt["evidence_refs"] for receipt in receipts)


def test_local_mutator_covers_expanded_commercial_contract_helpers():
    cases = [
        (
            "def rlm_harder_v2_choose_candidate(candidates):\n    return max(candidates, key=lambda item: item.get('score', 0)).get('id')\n",
            "rlm_harder_v2_choose_candidate",
            lambda fn: fn(
                [
                    {"id": "unsupported", "score": 0.99, "evidence_refs": []},
                    {"id": "winner", "score": 0.7, "status": "pass", "evidence_refs": ["winner.json"]},
                ]
            )
            == "winner",
        ),
        (
            "def rlm_harder_v2_prune_candidates(candidates, max_candidates):\n    return [item.get('id') for item in sorted(candidates, key=lambda item: item.get('score', 0), reverse=True)[:max_candidates]]\n",
            "rlm_harder_v2_prune_candidates",
            lambda fn: fn(
                [
                    {"id": "safe-high-score", "score": 0.95, "risk": 1},
                    {"id": "risky-required", "score": 0.5, "risk": 9},
                    {"id": "middle", "score": 0.7, "risk": 2},
                ],
                2,
            )
            == ["risky-required", "safe-high-score"],
        ),
        (
            "def rlm_harder_v2_accept_drone_artifacts(artifacts, expected_count):\n    return len(artifacts) == expected_count and all(item.get('path') for item in artifacts)\n",
            "rlm_harder_v2_accept_drone_artifacts",
            lambda fn: fn([{"owner": "a"}, {"owner": "b", "path": "reports/b.json"}], 2) is False,
        ),
        (
            "def rlm_harder_v2_accept_nightshift(report):\n    return bool(report.get('recommended') and report.get('invoked') and report.get('recovered'))\n",
            "rlm_harder_v2_accept_nightshift",
            lambda fn: fn({"recommended": True, "invoked": True, "recovered": True}) is False,
        ),
    ]

    for source, function_name, assertion in cases:
        patched = generate_local_candidate(source, "expanded commercial contract helper", "local", 0)
        namespace: dict[str, object] = {}
        exec(patched, namespace)
        assert assertion(namespace[function_name])


def test_local_mutator_ddtree_preserves_score_order_when_risk_ties():
    source = (
        "def rlm_harder_v2_prune_candidates(candidates, max_candidates):\n"
        "    ordered = sorted(candidates, key=lambda item: item.get('score', 0), reverse=True)\n"
        "    return [item.get('id') for item in ordered[:max_candidates]]\n"
    )

    patched = generate_local_candidate(source, "ddtree pruning", "local", 0)
    namespace: dict[str, object] = {}
    exec(patched, namespace)

    candidates = [
        {"id": "a", "score": 0.2, "risk": 1},
        {"id": "b", "score": 0.9, "risk": 1},
        {"id": "c", "score": 0.6, "risk": 1},
    ]
    assert namespace["rlm_harder_v2_prune_candidates"](candidates, 2) == ["b", "c"]


def test_public_non_hyper_expected_capability_defers_forced_hyper_to_route():
    task = CapabilityTask(
        id="rlm-harder-v2-belief-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Exercise belief lane without forcing Hyper.",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=("belief",),
    )

    flow, reason = _route_oracle_force_flow_policy(
        task,
        "hyper_sprint",
        route_cost_controls={"require_llm_baseline": False},
    )

    assert flow is None
    assert reason == "public_expected_non_hyper_capability"


def test_public_governance_guard_skip_baseline_keeps_hyper_for_local_preflight():
    task = CapabilityTask(
        id="rlm-harder-v2-governance-001",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Exercise governance guard without spending a baseline model call.",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=("mempalace_gate", "delivery_gate"),
        fixture_kind="rlm_harder_v2_governance_guard",
    )

    flow, reason = _route_oracle_force_flow_policy(
        task,
        "hyper_sprint",
        route_cost_controls={"skip_llm_baseline": True, "require_llm_baseline": False},
    )

    assert flow == "hyper_sprint"
    assert reason == ""


def test_public_deterministic_rlm_contracts_skip_baseline_keep_hyper_for_local_preflight():
    for fixture_kind in (
        "rlm_harder_v2_governance_scope",
        "rlm_harder_v2_evidence_gap",
        "rlm_harder_v2_evidence_replay",
        "rlm_harder_v2_memory_contract",
        "rlm_harder_v2_second_round",
        "rlm_harder_v2_belief_budget",
    ):
        task = CapabilityTask(
            id=f"case-{fixture_kind}",
            difficulty="hard",
            task_type="public_ops_research",
            task_desc="Exercise deterministic RLM contract without spending a baseline model call.",
            target_file="unused",
            test_file="unused",
            success_criteria="all_target_tests_pass",
            expected_capabilities=("artifact_gate", "delivery_gate"),
            fixture_kind=fixture_kind,
        )

        flow, reason = _route_oracle_force_flow_policy(
            task,
            "hyper_sprint",
            route_cost_controls={"skip_llm_baseline": True, "require_llm_baseline": False},
        )

        assert flow == "hyper_sprint"
        assert reason == ""


def test_r_phase_cost_classifies_zero_model_local_preflight_carrier():
    task = CapabilityTask(
        id="rlm-harder-v2-governance-001",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Exercise governance guard without spending a baseline model call.",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=("mempalace_gate", "delivery_gate"),
        fixture_kind="rlm_harder_v2_governance_guard",
    )

    assert (
        _classify_r_phase_cost(
            {"nexus_winner_source": "local_preflight", "model_calls": 0},
            task=task,
            requested_force_flow="hyper_sprint",
            effective_force_flow="hyper_sprint",
            defer_reason="",
        )
        == "local_preflight_hyper_carrier"
    )


def test_public_non_hyper_with_required_llm_baseline_preserves_forced_hyper():
    task = CapabilityTask(
        id="rlm-harder-v2-belief-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Exercise belief lane with required llm baseline.",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=("belief",),
    )

    flow, reason = _route_oracle_force_flow_policy(
        task,
        "hyper_sprint",
        route_cost_controls={"require_llm_baseline": True},
    )

    assert flow == "hyper_sprint"
    assert reason == ""


def test_run_with_nexus_route_oracle_non_hyper_deferred_force_flow(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="route-oracle-semantic-searcher-001",
        difficulty="hard",
        task_type="route_oracle",
        task_desc="Exercise semantic searcher without forcing Hyper.",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=("semantic_searcher",),
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}
    calls: list[list[str]] = []

    class _Proc:
        stdout = json.dumps(
            {
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "nexus_usage_trace": {
                    "gemini_uses_nexus": True,
                    "nexus_context_delivered": True,
                    "usage_valid": True,
                    "pillars": {
                        "lancedb": {"active": True},
                        "memory": {"active": True},
                        "mempalace": {"active": True},
                        "belief": {"active": True},
                        "artifact": {"active": True},
                    },
                    "phase_trace": {
                        "P": "route_built",
                        "X": "retrieval_checked",
                        "D": "guard_decision",
                        "R": "baseline_executed",
                        "A": "artifact_verified",
                        "C": "closure_written",
                    },
                },
                "result": {
                    "elapsed_sec": 0.1,
                    "report": {
                        "attempt_count": 1,
                        "model_calls": 1,
                        "model_name": "gemini-3-flash-preview",
                        "total_tokens": 10,
                        "token_capture_status": "ok",
                    },
                },
            }
        )
        stderr = ""
        returncode = 0

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        captured["cmd"] = list(cmd)
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setenv("NEXUS_CAPABILITY_RECEIPT_FIRST", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert captured["cmd"][captured["cmd"].index("--force-flow") + 1] == "baseline"
    assert "--llm-baseline" in captured["cmd"]
    assert len(calls) == 1
    assert out["requested_force_flow"] == "hyper_sprint"
    assert out["effective_force_flow"] == "baseline"
    assert out["route_oracle_force_flow_deferred"] is True
    assert out["r_phase_cost_classification"] == "forced_hyper_deferred_for_non_hyper_route_oracle"
    assert out["run_eligible"] is True


def test_run_with_nexus_public_non_hyper_deferred_force_flow(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="rlm-harder-v2-belief-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Exercise belief lane without forcing Hyper.",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=("belief",),
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = json.dumps(
            {
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "nexus_usage_trace": {
                    "gemini_uses_nexus": True,
                    "nexus_context_delivered": True,
                    "usage_valid": True,
                    "pillars": {
                        "lancedb": {"active": True},
                        "memory": {"active": True},
                        "mempalace": {"active": True},
                        "belief": {"active": True},
                        "artifact": {"active": True},
                    },
                    "phase_trace": {
                        "P": "route_built",
                        "X": "retrieval_checked",
                        "D": "guard_decision",
                        "R": "baseline_executed",
                        "A": "artifact_verified",
                        "C": "closure_written",
                    },
                },
                "result": {
                    "elapsed_sec": 0.1,
                    "report": {
                        "attempt_count": 1,
                        "model_calls": 1,
                        "model_name": "gemini-3-flash-preview",
                        "total_tokens": 10,
                        "token_capture_status": "ok",
                    },
                },
            }
        )
        stderr = ""
        returncode = 0

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner.route_cost_controls_for_task",
        lambda *args, **kwargs: {"require_llm_baseline": True, "policy_source": "test-belief-requires-llm"},
    )
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert captured["cmd"][captured["cmd"].index("--force-flow") + 1] == "hyper_sprint"
    assert "--llm-baseline" in captured["cmd"]
    assert out["requested_force_flow"] == "hyper_sprint"
    assert out["effective_force_flow"] == "hyper_sprint"
    assert out["force_flow_deferred"] is False
    assert out["force_flow_defer_reason"] == ""
    assert out["r_phase_cost_classification"] == "unnecessary_forced_hyper"
    assert out["run_eligible"] is True


def test_run_with_nexus_can_require_strict_llm_baseline(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-routing-strict-baseline",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix routing-sensitive public bug with strict baseline",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","nexus_usage_trace":{"gemini_uses_nexus":true,"nexus_context_delivered":true,"usage_valid":true,"pillars":{"lancedb":{"active":true},"memory":{"active":true},"mempalace":{"active":true},"belief":{"active":true},"artifact":{"active":true}},"phase_trace":{"P":"route_built","X":"retrieval_checked","D":"guard_decision","R":"baseline_executed","A":"artifact_verified","C":"closure_written"}},"result":{"elapsed_sec":0.1,"report":{"source":"nexus_llm_baseline","attempt_count":1,"model_calls":1,"model_name":"gemini-3.1-pro-preview","model_patch_generated":true,"fallback_used":false,"baseline_llm_required":true,"baseline_source_policy":"strict_llm_no_local_fallback","total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["cmd"] = _cmd
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
        strict_llm_baseline=True,
    )

    assert "--llm-baseline-required" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--force-flow") + 1] == "baseline"
    assert captured["env"]["NEXUS_GATEWAY_MAX_RETRIES"] == "1"
    assert out["baseline_llm_required"] is True
    assert out["baseline_source_policy"] == "strict_llm_no_local_fallback"
    assert out["baseline_provider"] == "gemini"
    assert out["nexus_winner_source"] == "nexus_llm_baseline"
    assert out["run_eligible"] is True


def test_run_with_nexus_can_opt_into_llm_self_heal(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-routing-self-heal",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix routing-sensitive public bug",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="all",
        enable_llm_self_heal=True,
    )

    assert captured["env"]["NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL"] == "1"


def test_run_with_nexus_preserves_model_required_self_heal_on_lite_route(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="model-required-lite-self-heal",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix model-owned repair that may need bounded self-heal",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        eligibility_class="model_required",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = '{"status":"FAILED","semantic_status":"UNVERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 1

    def fake_run(_cmd, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr(
        "scripts.bench.capability_ab_runner.route_cost_controls_for_task",
        lambda *args, **kwargs: {"lite_route": True, "candidate_cap": 1, "policy_source": "test-lite"},
    )
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="all",
        enable_llm_self_heal=True,
    )

    assert captured["env"]["NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL"] == "1"
    assert captured["env"]["NEXUS_MODEL_REQUIRED_EXECUTION_MODE"] == "model_participation_only"


def test_run_with_nexus_surfaces_failure_analysis(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-routing-failure-analysis",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix routing-sensitive public bug",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    payload = {
        "status": "FAILED",
        "semantic_status": "UNVERIFIED",
        "nexus_failure_analysis": {
            "schema": "nexus_failure_analysis_v1",
            "status": "ACTION_REQUIRED",
            "primary_cause": "flash_no_verified_mutation",
            "owner": "nexus_retry_policy",
            "nexus_gap": "bounded_self_heal_not_triggered",
            "recoverable": True,
            "nexus_blocked_unsafe_delivery": True,
            "self_heal_status": "not_triggered",
            "reasons": ["required_mutation_missing", "claim_probe_blocked_patch"],
            "next_action": "trigger_bounded_self_heal_before_accepting_flash_failure",
        },
        "nexus_usage_trace": {
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": False,
            "pillars": {},
            "phase_trace": {},
            "capabilities": {},
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {
                "attempt_count": 1,
                "model_calls": 1,
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": False,
                "total_tokens": 10,
                "token_capture_status": "ok",
            },
        },
    }

    class _Proc:
        stdout = json.dumps(payload)
        stderr = ""
        returncode = 1

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", lambda _cmd, **_kwargs: _Proc())

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert out["nexus_failure_status"] == "ACTION_REQUIRED"
    assert out["nexus_failure_primary_cause"] == "flash_no_verified_mutation"
    assert out["nexus_failure_owner"] == "nexus_retry_policy"
    assert out["nexus_failure_gap"] == "bounded_self_heal_not_triggered"
    assert out["nexus_failure_recoverable"] is True
    assert out["nexus_blocked_unsafe_delivery"] is True
    assert out["nexus_failure_next_action"] == "trigger_bounded_self_heal_before_accepting_flash_failure"


def test_run_with_nexus_can_enable_ultra_dry_gate_without_llm(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-routing-no-llm",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix routing-sensitive public bug without llm",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":0,"total_tokens":0,"token_capture_status":"not_applicable_local_only"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="off",
        enable_ultra_review_dry_gate=True,
    )

    assert captured["env"]["NEXUS_ULTRA_REVIEW_DRY_GATE"] == "1"
    assert "NEXUS_AUTOREASON_EXECUTOR" not in captured["env"]
    assert "NEXUS_DDTREE_EXECUTOR" not in captured["env"]
    assert out["run_eligible"] is True


def test_run_with_nexus_can_enable_routing_layer_executors_without_llm(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-routing-no-llm-executors",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix routing-sensitive public bug without llm",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":0,"total_tokens":0,"token_capture_status":"not_applicable_local_only"}}}'
        stderr = ""
        returncode = 0

    def fake_run(_cmd, **kwargs):
        captured["cmd"] = list(_cmd)
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="off",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
    )

    assert captured["env"]["NEXUS_AUTOREASON_EXECUTOR"] == "1"
    assert captured["env"]["NEXUS_DDTREE_EXECUTOR"] == "1"
    assert captured["env"]["NEXUS_LLM_CANDIDATE_CAP"] == "3"
    assert captured["env"]["NEXUS_ULTRA_REVIEW_DRY_GATE"] == "1"
    assert "--candidate-count" in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--candidate-count") + 1] == "3"
    assert out["run_eligible"] is True


def test_run_with_nexus_subprocess_preserves_executor_receipts_without_llm(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NEXUS_BENCH_SKILL_MOUNTS", "1")
    task = CapabilityTask(
        id="pub-routing-receipts-no-llm",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix evidence-heavy routing bug without llm",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
        expected_capabilities=("autoreason", "ddtree", "ultra_review"),
        capability_activation_contract="required",
        hidden_oracle_kind="trace_receipt",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}
    receipts = [
        {
            "name": "autoreason",
            "selected": True,
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "public_claim_safe": True,
            "evidence_refs": ["candidate-2", "stop_reason:a_streak_met"],
        },
        {
            "name": "ddtree",
            "selected": True,
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "public_claim_safe": True,
            "evidence_refs": ["saved_steps:2"],
        },
        {
            "name": "ultra_review",
            "selected": True,
            "invoked": True,
            "evidence_present": True,
            "gate_passed": True,
            "outcome_contributed": True,
            "public_claim_safe": True,
            "evidence_refs": [".nexus/reports/ultra_review/route_gate_report.json"],
        },
    ]
    payload = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "nexus_usage_trace": {
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "usage_valid": True,
            "skill_mount_contract": {
                "skill_id": "nexus-benchmark-public-report",
                "skill_status": "nexus_curated_candidate",
                "capability_mount": "benchmark_and_promotion",
                "load_reason_codes": ["public_benchmark_report_required"],
                "evidence_refs": ["route:pub-routing-receipts-no-llm"],
                "outcome_contributed": True,
            },
            "pillars": {
                "lancedb": {"active": True},
                "memory": {"active": True},
                "mempalace": {"active": True},
                "belief": {"active": True},
                "artifact": {"active": True},
            },
            "phase_trace": {
                "P": "route_built",
                "X": "retrieval_checked",
                "D": "guard_decision",
                "R": "hyper_executed",
                "A": "artifact_verified",
                "C": "closure_written",
            },
            "capabilities": {"claim_verified": True},
            "capability_receipts": receipts,
            "research_preflight": {
                "schema": "nexus_research_preflight_v1",
                "present": True,
                "blocked": False,
                "requires_evidence": True,
                "decision": "requires_evidence",
                "route": {
                    "research_context": {
                        "risk_flags": ["claim_uncertainty"],
                        "blocked_assumptions": ["api_contract_not_verified"],
                    },
                },
            },
            "research_session": {
                "schema": "nexus_research_session_v1",
                "logged": True,
                "status": "keep",
                "lane": "research-runtime",
            },
        },
        "result": {
            "elapsed_sec": 0.1,
            "report": {
                "attempt_count": 1,
                "model_calls": 0,
                "total_tokens": 0,
                "token_capture_status": "not_applicable_local_only",
            },
        },
    }

    class _Proc:
        stdout = json.dumps(payload)
        stderr = ""
        returncode = 0

    def fake_run(cmd, **kwargs):
        captured["cmd"] = list(cmd)
        captured["env"] = kwargs.get("env", {})
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="off",
        enable_autoreason_executor=True,
        enable_ddtree_executor=True,
        enable_ultra_review_dry_gate=True,
        llm_candidate_cap=3,
    )

    assert captured["cmd"][:4] == ["uv", "run", "scripts/engine/nexus_cli.py", "nexus"]
    assert "--output-json" in captured["cmd"]
    assert captured["env"]["NEXUS_AUTOREASON_EXECUTOR"] == "1"
    assert captured["env"]["NEXUS_DDTREE_EXECUTOR"] == "1"
    assert captured["env"]["NEXUS_ULTRA_REVIEW_DRY_GATE"] == "1"
    assert json.loads(captured["env"]["NEXUS_BENCH_SKILL_MOUNT_REQUESTS"]) == [
        "nexus-benchmark-continuous-optimization",
        "nexus-root-cause-probe",
    ]
    assert out["capability_receipts"] == receipts
    assert json.loads(out["capability_receipts_json"]) == receipts
    assert out["skill_mount_contract"] == [
        {
            "skill_id": "nexus-benchmark-public-report",
            "skill_status": "nexus_curated_candidate",
            "capability_mount": "benchmark_and_promotion",
            "load_reason_codes": ["public_benchmark_report_required"],
            "evidence_refs": ["route:pub-routing-receipts-no-llm"],
            "outcome_contributed": True,
        }
    ]
    assert out["skill_mount_count"] == 1
    assert out["skill_mount_contract_status"] == "RETURN"
    assert out["skill_mount_violations"]
    assert json.loads(out["skill_mount_contract_json"]) == out["skill_mount_contract"]
    assert out["research_preflight_present"] is True
    assert out["research_preflight_requires_evidence"] is True
    assert out["research_preflight_blocked"] is False
    assert out["claim_uncertainty"] is True
    assert out["research_session_logged"] is True
    assert out["research_session_status"] == "keep"
    assert out["research_session_lane"] == "research-runtime"
    assert out["expected_capabilities"] == ["autoreason", "ddtree", "ultra_review"]
    assert out["capability_activation_contract"] == "required"
    assert out["hidden_oracle_kind"] == "trace_receipt"
    assert out["expected_capability_receipt_coverage"] == {
        "expected": ["autoreason", "ddtree", "ultra_review"],
        "public_safe": ["autoreason", "ddtree", "ultra_review"],
        "missing": [],
        "failure_reasons": {},
        "all_public_safe": True,
    }
    receipt_by_name = {item["name"]: item for item in out["capability_receipts"]}
    assert receipt_by_name["autoreason"]["public_claim_safe"] is True
    assert receipt_by_name["ddtree"]["public_claim_safe"] is True
    assert receipt_by_name["ultra_review"]["public_claim_safe"] is True


def test_run_with_nexus_llm_all_keeps_auto_route_when_force_flow_is_unset(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="pub-001",
        difficulty="medium",
        task_type="public_docs_code_sync",
        task_desc="Fix docs task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)
    captured = {}

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":1,"total_tokens":10,"token_capture_status":"ok"}}}'
        stderr = ""
        returncode = 0

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = list(cmd)
        return _Proc()

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run)

    run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert "--llm-mode" in captured["cmd"]
    assert "--llm-baseline" in captured["cmd"]
    assert "--force-flow" not in captured["cmd"]


def test_history_policy_defaults_to_per_task_reset():
    assert _history_policy_name(neutralize_history=True, allow_learning_loop=False) == "per_task_reset"
    assert _history_policy_name(neutralize_history=True, allow_learning_loop=True) == "within_mode_learning"
    assert _history_policy_name(neutralize_history=False, allow_learning_loop=True) == "shared_existing_history"


def test_hidden_verifier_mode_reads_environment(monkeypatch):
    monkeypatch.delenv("NEXUS_VALUE_HIDDEN_VERIFIER", raising=False)
    assert _hidden_verifier_mode_enabled() is False
    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    assert _hidden_verifier_mode_enabled() is True


def test_nexus_task_desc_includes_autoreason_hidden_contract():
    task = CapabilityTask(
        id="route-oracle-autoreason-001",
        difficulty="hard",
        task_type="public_feature",
        task_desc="Select candidate",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_autoreason_judge",
        expected_capabilities=("autoreason",),
        capability_activation_contract="required",
    )

    desc = _nexus_task_desc(task)

    assert "Exclude candidates whose evidence_refs is missing or empty" in desc
    assert "not exactly 'pass'" in desc


def test_nexus_task_desc_includes_ddtree_hidden_contract():
    task = CapabilityTask(
        id="route-oracle-ddtree-001",
        difficulty="hard",
        task_type="public_test_repair",
        task_desc="Prune candidates",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_ddtree_pruning",
        expected_capabilities=("ddtree",),
        capability_activation_contract="required",
    )

    desc = _nexus_task_desc(task)

    assert "Always include the highest-risk candidate" in desc
    assert "Fill remaining slots with the highest-score candidates" in desc
    assert "highest-risk candidate" in desc


def test_nexus_task_desc_includes_retrieval_hidden_contracts():
    cases = [
        (
            "rlm_harder_v2_research_citation",
            ("research",),
            "return claim['id']",
        ),
        (
            "rlm_harder_v2_lancedb_retrieval",
            ("lancedb",),
            "patch the source even if visible tests already pass",
        ),
        (
            "rlm_harder_v2_semantic_searcher_refs",
            ("semantic_searcher",),
            "append ref['source_id']",
        ),
    ]
    for fixture_kind, expected_capabilities, expected_text in cases:
        task = CapabilityTask(
            id=f"{fixture_kind}-001",
            difficulty="hard",
            task_type="public_docs_code_sync",
            task_desc="Select evidence",
            target_file="unused",
            test_file="unused",
            success_criteria="patch_and_tests_pass",
            fixture_kind=fixture_kind,
            expected_capabilities=expected_capabilities,
            capability_activation_contract="required",
        )
        assert expected_text in _nexus_task_desc(task)


def test_nexus_task_desc_includes_swarm_quiet_moment_hidden_contract():
    task = CapabilityTask(
        id="route-oracle-swarm-quiet-moment-001",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Accept quiet moment",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        fixture_kind="rlm_harder_v2_swarm_quiet_moment",
        expected_capabilities=("swarm_quiet_moment",),
        capability_activation_contract="required",
    )
    desc = _nexus_task_desc(task)
    guidance = _nexus_codex_hidden_verifier_guidance(task, "def rlm_harder_v2_accept_quiet_moment(event): pass")
    assert "production_writes_allowed is exactly False" in desc
    assert "patch the source even if visible tests already pass" in desc
    assert "non-empty string statuses" in guidance


def test_assert_clean_worktree_fails_closed_on_dirty_status(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("scripts.bench.capability_ab_runner._git_status_porcelain", lambda _root: " M file.py")
    try:
        assert_clean_worktree(tmp_path)
    except RuntimeError as exc:
        assert "clean worktree" in str(exc)
        assert "file.py" in str(exc)
    else:
        raise AssertionError("dirty worktree should fail closed")


def test_run_without_nexus_gemini_mode_uses_direct_flash_baseline(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="easy-001",
        difficulty="easy",
        task_type="bug",
        task_desc="Fix text normalization",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        assert "[CURRENT TESTS]" in prompt
        return (
            {
                "patch": "def normalize_flag(text: str) -> str:\n    return text.strip().lower()\n",
                "tokens_used": 123,
                "token_capture_status": "measured",
                "model_name": "gemini-3.1-pro-preview",
                "model_patch_generated": True,
            },
            "",
        )

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_gemini_flash_patch", fake_ask_direct_gemini_flash_patch)
    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        mode="gemini",
    )
    assert out["status"] == "SUCCESS"
    assert out["semantic_status"] == "VERIFIED"
    assert out["model_calls"] == 1
    assert out["total_tokens"] == 123
    assert out["token_capture_status"] == "measured"
    assert out["model_name"] == "gemini-3.1-pro-preview"
    assert out["provider"] == "gemini"
    assert out["run_eligible"] is True
    assert out["infra_invalid_reason"] is None
    assert out["invocation_started"] is True
    assert out["model_response_received"] is True
    assert out["nexus_bootstrap_completed"] is False
    assert out["model_patch_generated"] is True
    assert out["artifact_changed"] is True
    assert out["baseline_patch_changed"] is True
    assert out["baseline_patch_len"] > 0


def test_direct_gemini_session_worker_reuses_one_session(tmp_path: Path, monkeypatch):
    gemini_bin = tmp_path / "gemini"
    gemini_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    commands: list[list[str]] = []

    capability_ab_runner._GEMINI_BENCH_SESSION_ID = None
    capability_ab_runner._GEMINI_BENCH_SESSION_STARTED.clear()
    capability_ab_runner._GEMINI_BENCH_SESSION_TURNS.clear()
    capability_ab_runner._session_marker_path("gemini", "bench-session-001").unlink(missing_ok=True)
    monkeypatch.setenv("NEXUS_GEMINI_SESSION_WORKER", "1")
    monkeypatch.setenv("NEXUS_GEMINI_SESSION_ID", "bench-session-001")
    monkeypatch.setenv("NEXUS_GEMINI_MODEL_NAME", "gemini-3-flash-preview")
    monkeypatch.setattr("scripts.bench.capability_ab_runner.shutil.which", lambda _name, **_kwargs: str(gemini_bin))

    def fake_run_process_group(cmd, **_kwargs):
        commands.append(list(cmd))
        outer = {
            "output": json.dumps({"status": "SUCCESS", "patch": "patched"}),
            "usageMetadata": {"totalTokenCount": 42},
        }
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(outer), stderr="")

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    first, _ = _ask_direct_gemini_flash_patch(prompt="task one", timeout_sec=10)
    second, _ = _ask_direct_gemini_flash_patch(prompt="task two", timeout_sec=10)

    assert commands[0][1:3] == ["--session-id", "bench-session-001"]
    assert commands[1][1:3] == ["--resume", "bench-session-001"]
    assert first["gemini_session_worker"] is True
    assert first["gemini_session_resumed"] is False
    assert first["gemini_session_turn_index"] == 1
    assert second["gemini_session_resumed"] is True
    assert second["gemini_session_turn_index"] == 2


def test_reset_gemini_session_worker_clears_marker_and_turn_state(monkeypatch):
    capability_ab_runner._GEMINI_BENCH_SESSION_ID = None
    capability_ab_runner._GEMINI_BENCH_SESSION_STARTED.clear()
    capability_ab_runner._GEMINI_BENCH_SESSION_TURNS.clear()
    marker_path = capability_ab_runner._session_marker_path("gemini", "bench-session-reset")
    marker_path.write_text("started", encoding="utf-8")
    capability_ab_runner._GEMINI_BENCH_SESSION_STARTED.add("bench-session-reset")
    capability_ab_runner._GEMINI_BENCH_SESSION_TURNS["bench-session-reset"] = 7

    capability_ab_runner._reset_gemini_benchmark_session("bench-session-reset")

    assert "bench-session-reset" not in capability_ab_runner._GEMINI_BENCH_SESSION_STARTED
    assert "bench-session-reset" not in capability_ab_runner._GEMINI_BENCH_SESSION_TURNS
    assert not marker_path.exists()


def test_run_without_nexus_session_worker_records_row_metadata(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="easy-001",
        difficulty="easy",
        task_type="bug",
        task_desc="Fix text normalization",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        assert "NEXUS_BENCH_SESSION_BOUNDARY_V1" in prompt
        return (
            {
                "patch": "def normalize_flag(text: str) -> str:\n    return text.strip().lower()\n",
                "tokens_used": 123,
                "token_capture_status": "measured",
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": True,
                "gemini_session_worker": True,
                "gemini_session_id": "bench-session-001",
                "gemini_session_turn_index": 1,
                "gemini_session_resumed": False,
                "gemini_session_mode": "session_id_resume",
            },
            "",
        )

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_gemini_flash_patch", fake_ask_direct_gemini_flash_patch)
    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        mode="gemini",
    )

    assert out["status"] == "SUCCESS"
    assert out["session_worker_enabled"] is True
    assert out["session_worker_provider"] == "gemini"
    assert out["session_worker_policy"] == "session_id_resume"
    assert out["session_worker_id"] == "bench-session-001"
    assert out["session_worker_turn_index"] == 1
    assert out["reset_boundary_hash"]


def test_run_without_nexus_codex_mode_uses_direct_codex_baseline(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="easy-codex-001",
        difficulty="easy",
        task_type="bug",
        task_desc="Fix text normalization",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_codex_patch(*, prompt, timeout_sec):
        assert "Codex running without Nexus orchestration" in prompt
        return (
            {
                "patch": "def normalize_flag(text: str) -> str:\n    return text.strip().lower()\n",
                "tokens_used": 0,
                "token_capture_status": "missing_gateway_stats",
                "model_name": "gpt-5.5",
                "model_patch_generated": True,
            },
            "",
        )

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_codex_patch", fake_ask_direct_codex_patch)
    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        mode="codex",
    )
    assert out["status"] == "SUCCESS"
    assert out["provider"] == "codex"
    assert out["model_name"] == "gpt-5.5"
    assert out["run_eligible"] is True
    assert out["model_response_received"] is True
    assert out["token_reliable"] is False
    assert out["token_unreliable_reason"] == "estimated_tokens"
    assert out["runtime_classification"] == "direct_codex"


def test_direct_codex_session_worker_avoids_resume_last_by_default(tmp_path: Path, monkeypatch):
    codex_bin = tmp_path / "codex"
    codex_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    commands: list[list[str]] = []

    capability_ab_runner._CODEX_BENCH_SESSION_ID = None
    capability_ab_runner._CODEX_BENCH_SESSION_STARTED = False
    capability_ab_runner._CODEX_BENCH_SESSION_TURN = 0
    capability_ab_runner._session_marker_path("codex", "gpt55-session-001").unlink(missing_ok=True)
    monkeypatch.setenv("NEXUS_CODEX_SESSION_WORKER", "1")
    monkeypatch.setenv("NEXUS_CODEX_SESSION_ID", "gpt55-session-001")
    monkeypatch.setenv("NEXUS_CODEX_MODEL_NAME", "gpt-5.5")
    monkeypatch.setattr("scripts.bench.capability_ab_runner.shutil.which", lambda _name: str(codex_bin))

    def fake_run_process_group(cmd, **_kwargs):
        commands.append(list(cmd))
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text(json.dumps({"status": "SUCCESS", "patch": "patched"}), encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="tokens used 1,234", stderr="")

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    first, _ = _ask_direct_codex_patch(prompt="task one", timeout_sec=10)
    second, _ = _ask_direct_codex_patch(prompt="task two", timeout_sec=10)

    assert commands[0][:3] == [str(codex_bin), "exec", "--sandbox"]
    assert "--skip-git-repo-check" in commands[0]
    assert "--ephemeral" not in commands[0]
    assert commands[1][:3] == [str(codex_bin), "exec", "--sandbox"]
    assert "--skip-git-repo-check" in commands[1]
    assert first["codex_session_worker"] is True
    assert first["codex_session_resumed"] is False
    assert first["codex_session_turn_index"] == 1
    assert first["codex_session_mode"] == "exec_fresh_no_resume"
    assert second["codex_session_resumed"] is False
    assert second["codex_session_turn_index"] == 2


def test_codex_fresh_no_resume_session_policy_is_not_contamination():
    rows = [
        {
            "task_id": "task-a",
            "trial_index": 1,
            "session_worker_enabled": True,
            "session_worker_provider": "codex",
            "session_worker_policy": "exec_fresh_no_resume",
            "session_worker_id": "codex-public-baseline",
            "session_worker_turn_index": 1,
            "session_worker_resumed": False,
            "reset_boundary_hash": "hash-a",
            "run_eligible": True,
        },
        {
            "task_id": "task-b",
            "trial_index": 1,
            "session_worker_enabled": True,
            "session_worker_provider": "codex",
            "session_worker_policy": "exec_fresh_no_resume",
            "session_worker_id": "codex-public-baseline",
            "session_worker_turn_index": 2,
            "session_worker_resumed": False,
            "reset_boundary_hash": "hash-b",
            "run_eligible": True,
        },
    ]

    report = capability_ab_runner._annotate_session_worker_contamination(rows)

    assert report["clean"] is True
    assert all(not row.get("session_worker_contamination_detected") for row in rows)
    assert all(row["run_eligible"] is True for row in rows)


def test_run_without_nexus_hidden_verifier_omits_tests_from_prompt(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="nexus-value-hidden-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix hidden verifier task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_hidden_state",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        assert "test_applies_unique_happy_path_events" in prompt
        assert "test_duplicate_events_are_idempotent" not in prompt
        original = Path(target_file).read_text(encoding="utf-8")
        return (
            {
                "patch": original,
                "tokens_used": 123,
                "token_capture_status": "measured",
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": True,
            },
            "",
        )

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_gemini_flash_patch", fake_ask_direct_gemini_flash_patch)

    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        mode="gemini",
    )

    assert out["baseline_patch_changed"] is False


def test_run_without_nexus_hidden_verifier_omits_rlm_harder_tests(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="rlm-v2-hidden-001",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix hidden RLM task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="rlm_harder_v2_evidence_gap",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        assert "test_accepts_supported_passing_claim" in prompt
        assert "test_requires_artifact_reference" not in prompt
        original = Path(target_file).read_text(encoding="utf-8")
        return (
            {
                "patch": original,
                "tokens_used": 123,
                "token_capture_status": "measured",
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": True,
            },
            "",
        )

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_gemini_flash_patch", fake_ask_direct_gemini_flash_patch)

    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        mode="gemini",
    )

    assert out["baseline_patch_changed"] is False


def test_rlm_harder_fixture_materializes_visible_and_hidden_tests(tmp_path: Path):
    task = CapabilityTask(
        id="rlm-v2-hidden-001",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix hidden RLM task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="rlm_harder_v2_evidence_gap",
    )

    _target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    hidden_test_file = _hidden_test_for_visible_test(visible_test_file)

    visible = Path(visible_test_file).read_text(encoding="utf-8")
    hidden = Path(hidden_test_file).read_text(encoding="utf-8")
    assert Path(visible_test_file).name == "test_visible.py"
    assert Path(hidden_test_file).name == "test_hidden.py"
    assert "test_requires_artifact_reference" in visible
    assert "test_rejects_empty_and_non_string_artifacts" in hidden
    assert "test_rejects_empty_and_non_string_artifacts" not in visible


def test_hidden_verifier_uses_hidden_test_for_final_bare_gate(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="rlm-v2-hidden-001",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix hidden RLM task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="rlm_harder_v2_evidence_gap",
    )
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    captured_cmds: list[list[str]] = []

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        assert "test_requires_artifact_reference" in prompt
        assert "test_rejects_empty_and_non_string_artifacts" not in prompt
        patch = (
            "def rlm_harder_v2_verified_claims(claims):\n"
            "    return [claim['id'] for claim in claims if claim.get('status') == 'pass' and claim.get('artifact')]\n"
        )
        return (
            {
                "patch": patch,
                "tokens_used": 123,
                "token_capture_status": "measured",
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": True,
            },
            "",
        )

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        captured_cmds.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_gemini_flash_patch", fake_ask_direct_gemini_flash_patch)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow=None,
        mode="gemini",
    )

    assert captured_cmds
    assert captured_cmds[-1][-1].endswith("test_hidden.py")


def test_hidden_verifier_overrides_successful_nexus_row(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="rlm-v2-hidden-001",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix hidden RLM task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="rlm_harder_v2_evidence_gap",
    )
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    captured_cmds: list[list[str]] = []

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        captured_cmds.append(list(cmd))
        if cmd[:3] == ["uv", "run", "scripts/engine/nexus_cli.py"]:
            payload = {
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "result": {"elapsed_sec": 0.1},
                "report": {"model_calls": 0, "total_tokens": 0},
            }
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="hidden failed", stderr="")

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
    )

    assert captured_cmds
    assert captured_cmds[-1][-1].endswith("test_hidden.py")
    assert out["status"] == "FAILED"
    assert out["semantic_status"] == "UNVERIFIED"
    assert out["semantic_completed"] is False
    assert out["hidden_verifier_passed"] is False
    assert out["report_trust_mismatch"] is True


def test_hidden_verifier_failure_retries_with_failure_evidence_when_self_heal_env_enabled(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="rlm-v2-hidden-retry-001",
        difficulty="hard",
        task_type="public_ops_research",
        task_desc="Fix hidden governance task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="rlm_harder_v2_governance_guard",
    )
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    captured_cmds: list[list[str]] = []

    def nexus_payload() -> str:
        return json.dumps(
            {
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "nexus_failure_analysis": {
                    "schema": "nexus_failure_analysis_v1",
                    "status": "PASS",
                    "primary_cause": "verified_delivery",
                    "nexus_gap": "",
                    "recoverable": False,
                },
                "nexus_usage_trace": {
                    "gemini_uses_nexus": True,
                    "nexus_context_delivered": True,
                    "usage_valid": True,
                    "pillars": {},
                    "phase_trace": {},
                    "capabilities": {},
                },
                "result": {
                    "elapsed_sec": 0.1,
                    "report": {
                        "attempt_count": 1,
                        "model_calls": 1,
                        "model_name": "gemini-3-flash-preview",
                        "model_patch_generated": True,
                        "total_tokens": 10,
                        "token_capture_status": "ok",
                    },
                },
            }
        )

    state = {"verify_calls": 0}

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        captured_cmds.append(list(cmd))
        if cmd[:3] == ["uv", "run", "scripts/engine/nexus_cli.py"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=nexus_payload(), stderr="")
        state["verify_calls"] += 1
        if state["verify_calls"] == 1:
            return subprocess.CompletedProcess(cmd, 1, stdout="hidden failed: delete_file must be blocked", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="hidden passed", stderr="")

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow="hyper_sprint",
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    retry_cmds = [cmd for cmd in captured_cmds if cmd[:3] == ["uv", "run", "scripts/engine/nexus_cli.py"]]
    assert len(retry_cmds) == 2
    retry_desc = retry_cmds[-1][retry_cmds[-1].index("--task-desc") + 1]
    assert "[Hidden verifier failure]" in retry_desc
    assert "delete_file must be blocked" in retry_desc
    assert "Keep Artifact/Claim/Delivery verification active" in retry_desc
    assert out["hidden_retry_used"] is True
    assert out["hidden_retry_reason"] == "hidden_verifier_failure_bounded_nexus_retry"
    assert out["hidden_retry_payload_status"] == "SUCCESS"
    assert out["hidden_retry_payload_semantic_status"] == "VERIFIED"
    assert out["hidden_verifier_passed"] is True
    assert out["status"] == "SUCCESS"
    assert out["model_calls"] == 2
    assert out["attempt_count"] == 2
    assert out["total_tokens"] == 20
    assert out["first_attempt_model_calls"] == 1
    assert out["hidden_retry_model_calls"] == 1
    assert out["hidden_retry_attempt_count"] == 1
    assert out["hidden_retry_tokens"] == 10
    assert out["hidden_retry_lane"] == "full_hyper"
    assert out["hidden_retry_classifier"] == "broad_contract_failure"
    assert out["hidden_retry_prompt_budget"] == "full_hyper_v1"
    assert out["hidden_retry_tail_chars"] <= 1600
    assert out["hidden_retry_contract_chars"] > 0
    assert out["runner_overhead_basis"] == "composed_hidden_retry"
    assert out["model_attempts"][1]["attempt_type"] == "hidden_verifier_bounded_retry"
    assert out["model_attempts"][1]["prompt_budget"] == "full_hyper_v1"


def test_hidden_verifier_infra_failure_records_skipped_infra_lane(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="hidden-infra-skip-001",
        difficulty="hard",
        task_type="public_test_repair",
        task_desc="Fix hidden infra task",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_artifact_phase_report",
    )
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)

    def nexus_payload() -> str:
        return json.dumps(
            {
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "nexus_usage_trace": {
                    "model_uses_nexus": True,
                    "gemini_uses_nexus": True,
                    "nexus_context_delivered": True,
                    "usage_valid": True,
                    "pillars": {},
                    "phase_trace": {},
                    "capabilities": {},
                },
                "result": {
                    "elapsed_sec": 0.1,
                    "report": {
                        "attempt_count": 1,
                        "model_calls": 1,
                        "model_name": "gemini-3-flash-preview",
                        "model_patch_generated": True,
                        "total_tokens": 10,
                        "token_capture_status": "ok",
                    },
                },
            }
        )

    state = {"verify_calls": 0}

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        if cmd[:3] == ["uv", "run", "scripts/engine/nexus_cli.py"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=nexus_payload(), stderr="")
        state["verify_calls"] += 1
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout="",
            stderr="error: failed to open file `.cache/uv/sdists-v9/.git`: Operation not permitted",
        )

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert state["verify_calls"] == 1
    assert out["hidden_retry_used"] is False
    assert out["hidden_retry_reason"] == "hidden_verifier_infra_error"
    assert out["hidden_retry_lane"] == "skipped_infra"
    assert out["hidden_retry_classifier"] == "hidden_verifier_infra_error"
    assert out["infra_invalid_reason"] == "hidden_verifier_infra_error"
    assert out["report_trust_mismatch"] is False


def test_hidden_verifier_failure_retries_inprocess_with_failure_evidence(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="nexus-value-context-001",
        difficulty="hard",
        task_type="public_docs_code_sync",
        task_desc="Sync code and docs after a renamed public field.",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_context_docs_contract",
    )
    target_file, visible_test_file = _materialize_fixture(tmp_path, task)
    captured_args: list[list[str]] = []

    def nexus_payload() -> str:
        return json.dumps(
            {
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "nexus_failure_analysis": {
                    "schema": "nexus_failure_analysis_v1",
                    "status": "PASS",
                    "primary_cause": "verified_delivery",
                    "nexus_gap": "",
                    "recoverable": False,
                },
                "nexus_usage_trace": {
                    "gemini_uses_nexus": True,
                    "nexus_context_delivered": True,
                    "usage_valid": True,
                    "pillars": {},
                    "phase_trace": {},
                    "capabilities": {},
                },
                "result": {
                    "elapsed_sec": 0.1,
                    "report": {
                        "attempt_count": 1,
                        "model_calls": 1,
                        "model_name": "gemini-3-flash-preview",
                        "model_patch_generated": True,
                        "total_tokens": 10,
                        "token_capture_status": "measured",
                    },
                },
            }
        )

    class _InvokeRes:
        output = nexus_payload()

    def fake_invoke(_self, _cli, args, **_kwargs):
        captured_args.append(list(args))
        return _InvokeRes()

    state = {"verify_calls": 0}

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        state["verify_calls"] += 1
        if state["verify_calls"] == 1:
            return subprocess.CompletedProcess(cmd, 1, stdout="hidden failed: canonical output field is result", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="hidden passed", stderr="")

    monkeypatch.setenv("NEXUS_VALUE_HIDDEN_VERIFIER", "1")
    monkeypatch.setenv("NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL", "1")
    monkeypatch.setattr("click.testing.CliRunner.invoke", fake_invoke)
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=visible_test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="inprocess",
        with_llm_mode="all",
    )

    assert len(captured_args) == 2
    retry_desc = captured_args[-1][captured_args[-1].index("--task-desc") + 1]
    assert "[Hidden verifier failure: minimal retry]" in retry_desc
    assert "canonical output field is result" in retry_desc
    assert "Keep Artifact/Claim/Delivery verification active" in retry_desc
    assert "--force-flow" in captured_args[-1]
    assert out["hidden_retry_used"] is True
    assert out["hidden_retry_reason"] == "hidden_verifier_failure_bounded_nexus_retry"
    assert out["hidden_retry_payload_status"] == "SUCCESS"
    assert out["hidden_retry_payload_semantic_status"] == "VERIFIED"
    assert out["hidden_verifier_passed"] is True
    assert out["model_calls"] == 2
    assert out["attempt_count"] == 2
    assert out["total_tokens"] == 20
    assert out["hidden_retry_model_calls"] == 1
    assert out["hidden_retry_tokens"] == 10
    assert out["hidden_retry_lane"] == "minimal_patch"
    assert out["hidden_retry_classifier"] == "narrow_assertion_failure"
    assert out["hidden_retry_prompt_budget"] == "minimal_v1"
    assert out["hidden_retry_context_chars"] <= 800
    assert out["hidden_retry_tail_chars"] <= 1200
    assert out["hidden_retry_contract_chars"] > 0
    assert out["model_attempts"][1]["prompt_budget"] == "minimal_v1"
    assert out["status"] == "SUCCESS"


def test_run_without_nexus_gemini_quota_is_infra_invalid(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="easy-quota",
        difficulty="easy",
        task_type="bug",
        task_desc="Fix text normalization",
        target_file="unused",
        test_file="unused",
        success_criteria="all_target_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        return (
            {
                "status": "FAIL",
                "error_category": "cli_error",
                "tokens_used": 0,
                "model_name": "gemini-3-flash-preview",
            },
            "ERROR: You've hit your usage limit. Try again later.",
        )

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_gemini_flash_patch", fake_ask_direct_gemini_flash_patch)
    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        mode="gemini",
    )

    assert out["run_eligible"] is False
    assert out["infra_invalid_reason"] == "quota_exhausted"
    assert out["model_calls"] == 1
    assert out["invocation_started"] is True
    assert out["model_response_received"] is False


def test_run_without_nexus_retries_direct_gemini_cli_error_without_tokens(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="retry-cli-error",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix normalization",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
    )
    target_file = tmp_path / "target.py"
    test_file = tmp_path / "test_target.py"
    target_file.write_text("def normalize(value):\n    return value\n", encoding="utf-8")
    test_file.write_text(
        "from target import normalize\n\n"
        "def test_normalize():\n"
        "    assert normalize('  A  ') == 'a'\n",
        encoding="utf-8",
    )
    calls = []

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        calls.append(prompt)
        if len(calls) == 1:
            return (
                {
                    "status": "FAIL",
                    "error_category": "cli_error",
                    "tokens_used": 0,
                    "model_name": "gemini-3-flash-preview",
                },
                "transient empty CLI response",
            )
        return (
            {
                "status": "SUCCESS",
                "patch": "def normalize(value):\n    return value.strip().lower()\n",
                "tokens_used": 321,
                "token_capture_status": "measured",
                "gateway_stats_present": True,
                "gateway_token_source": "stats",
                "model_name": "gemini-3-flash-preview",
                "model_patch_generated": True,
            },
            '{"status":"SUCCESS"}',
        )

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_gemini_flash_patch", fake_ask_direct_gemini_flash_patch)
    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=str(target_file),
        test_file=str(test_file),
        timeout_sec=10,
        force_flow=None,
        mode="gemini",
    )

    assert len(calls) == 2
    assert out["status"] == "SUCCESS"
    assert out["run_eligible"] is True
    assert out["provider_token_measured"] is True
    assert out["direct_infra_retry_count"] == 1
    assert out["direct_infra_retry_wall_sec"] >= 0
    assert out["direct_infra_retry_reasons"] == ["cli_error_without_tokens"]


def test_run_without_nexus_resets_direct_gemini_invalid_session_before_retry(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="retry-invalid-session",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix normalization",
        target_file="target.py",
        test_file="test_target.py",
        success_criteria="patch_and_tests_pass",
    )
    target_file = tmp_path / "target.py"
    test_file = tmp_path / "test_target.py"
    target_file.write_text("def normalize(value):\n    return value\n", encoding="utf-8")
    test_file.write_text(
        "from target import normalize\n\n"
        "def test_normalize():\n"
        "    assert normalize('  A  ') == 'a'\n",
        encoding="utf-8",
    )
    marker_path = capability_ab_runner._session_marker_path("gemini", "bench-session-invalid")
    marker_path.write_text("started", encoding="utf-8")
    capability_ab_runner._GEMINI_BENCH_SESSION_STARTED.add("bench-session-invalid")
    capability_ab_runner._GEMINI_BENCH_SESSION_TURNS["bench-session-invalid"] = 3
    calls = []

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        calls.append(prompt)
        if len(calls) == 1:
            return (
                {
                    "status": "FAIL",
                    "error_category": "cli_error",
                    "tokens_used": 0,
                    "model_name": "gemini-3.1-pro-preview",
                    "gemini_session_id": "bench-session-invalid",
                },
                'Error resuming session: Invalid session identifier "bench-session-invalid"',
            )
        return (
            {
                "status": "SUCCESS",
                "patch": "def normalize(value):\n    return value.strip().lower()\n",
                "tokens_used": 321,
                "token_capture_status": "measured",
                "gateway_stats_present": True,
                "gateway_token_source": "stats",
                "model_name": "gemini-3.1-pro-preview",
                "model_patch_generated": True,
            },
            '{"status":"SUCCESS"}',
        )

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_gemini_flash_patch", fake_ask_direct_gemini_flash_patch)
    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=str(target_file),
        test_file=str(test_file),
        timeout_sec=10,
        force_flow=None,
        mode="gemini",
    )

    assert len(calls) == 2
    assert out["status"] == "SUCCESS"
    assert out["direct_infra_retry_reasons"] == ["gemini_invalid_session_identifier"]
    assert "bench-session-invalid" not in capability_ab_runner._GEMINI_BENCH_SESSION_STARTED
    assert "bench-session-invalid" not in capability_ab_runner._GEMINI_BENCH_SESSION_TURNS
    assert not marker_path.exists()


def test_without_nexus_parse_failure_with_tokens_is_eligible_model_failure():
    row = {
        "mode": "without_nexus",
        "status": "FAILED",
        "semantic_completed": False,
        "model_calls": 1,
        "model_patch_generated": False,
        "total_tokens": 321,
        "token_capture_status": "measured",
        "gateway_token_source": "stats",
        "baseline_gateway_error_category": "parse_failure",
        "eligibility_class": "model_required",
    }

    out = _annotate_benchmark_eligibility(
        row,
        provider="gemini",
        model_required=True,
        nexus_required=False,
    )

    assert out["run_eligible"] is True
    assert out["infra_invalid_reason"] is None
    assert out["model_response_received"] is True
    assert out["model_uplift_eligible"] is True


def test_with_nexus_verified_rescue_after_measured_parse_failure_is_eligible():
    row = {
        "mode": "with_nexus",
        "status": "SUCCESS",
        "semantic_completed": True,
        "model_calls": 1,
        "model_patch_generated": False,
        "total_tokens": 321,
        "token_capture_status": "measured",
        "baseline_gateway_error_category": "parse_failure",
        "eligibility_class": "model_required",
        "gemini_uses_nexus": True,
        "model_uses_nexus": True,
        "nexus_context_delivered": True,
        "hidden_verifier_passed": True,
        "report_trust_mismatch": False,
        "nexus_winner_source": "nexus_llm_deterministic_pre_rescue",
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "supervised_bare_preflight",
        "phase_x": "supervised_bare_context_suppressed",
        "phase_d": "supervised_bare_route_decision",
        "phase_r": "supervised_bare_deterministic_pre_rescue",
        "phase_a": "supervised_bare_hidden_verifier",
        "phase_c": "supervised_bare_delivery_receipt",
    }

    out = _annotate_benchmark_eligibility(
        row,
        provider="gemini",
        model_required=True,
        nexus_required=True,
    )

    assert out["run_eligible"] is True
    assert out["infra_invalid_reason"] is None
    assert out["nexus_wearing_valid"] is True


def test_strict_llm_baseline_gateway_error_is_infra_invalid():
    row = {
        "mode": "with_nexus",
        "status": "FAILED",
        "semantic_completed": False,
        "model_calls": 1,
        "model_patch_generated": False,
        "total_tokens": 0,
        "token_capture_status": "unknown",
        "gateway_error_category": "gateway_error",
        "baseline_llm_required": True,
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "route_built",
        "phase_x": "retrieval_checked",
        "phase_d": "guard_decision",
        "phase_r": "baseline_executed",
        "phase_a": "artifact_verified",
        "phase_c": "closure_written",
    }

    out = _annotate_benchmark_eligibility(
        row,
        provider="gemini",
        model_required=True,
        nexus_required=True,
    )

    assert out["run_eligible"] is False
    assert out["infra_invalid_reason"] == "model_gateway_error"


def test_run_without_nexus_gemini_timeout_before_response_is_recorded(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="timeout-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix timeout",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_hidden_state",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        raise subprocess.TimeoutExpired(["gemini"], timeout_sec)

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_gemini_flash_patch", fake_ask_direct_gemini_flash_patch)

    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=1,
        force_flow=None,
        mode="gemini",
    )

    assert out["status"] == "FAILED"
    assert out["baseline_gateway_error_category"] == "timeout"
    assert out["infra_invalid_reason"] == "timeout_before_model_call"


def test_direct_gemini_patch_uses_process_group_timeout(monkeypatch):
    captured: dict[str, object] = {}

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        captured["timeout_sec"] = timeout_sec
        raise subprocess.TimeoutExpired(cmd, timeout_sec)

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)
    monkeypatch.setattr("scripts.bench.capability_ab_runner.shutil.which", lambda _name, **_kwargs: "/tmp/gemini")
    monkeypatch.setattr("scripts.bench.capability_ab_runner.Path.exists", lambda _self: True)

    out, raw = _ask_direct_gemini_flash_patch(prompt="fix", timeout_sec=7)

    assert captured["timeout_sec"] == 7
    assert out["error_category"] == "timeout"
    assert raw == ""


def test_direct_gemini_patch_runs_from_repo_cwd(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        captured["cwd"] = cwd
        captured["cmd"] = list(cmd)
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps({"response": "{\"status\":\"OK\",\"patch\":\"x = 1\\n\"}"}),
            stderr="",
        )

    monkeypatch.setenv("NEXUS_GEMINI_CLI_CWD", str(tmp_path))
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)
    monkeypatch.setattr("scripts.bench.capability_ab_runner.shutil.which", lambda _name, **_kwargs: "/tmp/gemini")
    monkeypatch.setattr("scripts.bench.capability_ab_runner.Path.exists", lambda _self: True)

    out, _ = _ask_direct_gemini_flash_patch(prompt="fix", timeout_sec=7)

    assert captured["cwd"] == str(tmp_path.resolve())
    assert "-y" not in captured["cmd"]
    assert "--approval-mode" in captured["cmd"]
    assert "plan" in captured["cmd"]
    assert out["patch"] == "x = 1\n"


def test_direct_gemini_patch_approval_mode_can_be_overridden(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        captured["cmd"] = list(cmd)
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps({"response": "{\"status\":\"OK\",\"patch\":\"x = 1\\n\"}"}),
            stderr="",
        )

    monkeypatch.setenv("NEXUS_GEMINI_CLI_CWD", str(tmp_path))
    monkeypatch.setenv("NEXUS_DIRECT_GEMINI_APPROVAL_MODE", "auto_edit")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)
    monkeypatch.setattr("scripts.bench.capability_ab_runner.shutil.which", lambda _name, **_kwargs: "/tmp/gemini")
    monkeypatch.setattr("scripts.bench.capability_ab_runner.Path.exists", lambda _self: True)

    out, _ = _ask_direct_gemini_flash_patch(prompt="fix", timeout_sec=7)

    assert "auto_edit" in captured["cmd"]
    assert "plan" not in captured["cmd"]
    assert out["patch"] == "x = 1\n"


def test_direct_gemini_auth_confirmation_timeout_is_classified(monkeypatch):
    prompt = "Opening authentication page in your browser. Do you want to continue? [Y/n]: "

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        raise subprocess.TimeoutExpired(cmd, timeout_sec, output="", stderr=prompt)

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)
    monkeypatch.setattr("scripts.bench.capability_ab_runner.shutil.which", lambda _name, **_kwargs: "/tmp/gemini")
    monkeypatch.setattr("scripts.bench.capability_ab_runner.Path.exists", lambda _self: True)

    out, raw = _ask_direct_gemini_flash_patch(prompt="fix", timeout_sec=7)

    assert _looks_like_gemini_auth_prompt(raw)
    assert out["error_category"] == "auth_confirmation_required"


def test_process_group_aborts_gemini_auth_prompt_before_timeout(tmp_path: Path):
    res = capability_ab_runner._run_process_group(
        [
            sys.executable,
            "-c",
            "import time; print('Opening authentication page in your browser. Do you want to continue? [Y/n]: ', flush=True); time.sleep(20)",
        ],
        cwd=tmp_path,
        env=os.environ.copy(),
        timeout_sec=10,
    )

    assert res.returncode == 124
    assert _looks_like_gemini_auth_prompt(res.stdout)


def test_direct_gemini_timeout_cap_defaults_to_180(monkeypatch):
    monkeypatch.delenv("NEXUS_DIRECT_GEMINI_TIMEOUT_SEC", raising=False)
    assert _direct_gemini_timeout_sec(420) == 180
    assert _direct_gemini_timeout_sec(60) == 60


def test_direct_codex_timeout_cap_defaults_to_180(monkeypatch):
    monkeypatch.delenv("NEXUS_DIRECT_CODEX_TIMEOUT_SEC", raising=False)
    assert _direct_codex_timeout_sec(420) == 180
    assert _direct_codex_timeout_sec(60) == 60


def test_extract_codex_stdout_tokens_reads_cli_footer():
    assert _extract_codex_stdout_tokens("done\ntokens used\n17,263\n") == 17263
    assert _extract_codex_stdout_tokens("no token footer") == 0


def test_direct_codex_patch_uses_read_only_exec(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        captured["cmd"] = cmd
        last_path = Path(cmd[cmd.index("--output-last-message") + 1])
        last_path.write_text('{"status":"OK","patch":"x = 1\\n"}', encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="tokens used\n17,263\n", stderr="")

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)
    monkeypatch.setattr("scripts.bench.capability_ab_runner.shutil.which", lambda _name, **_kwargs: "/tmp/codex")
    monkeypatch.setattr("scripts.bench.capability_ab_runner.Path.exists", lambda _self: True)
    monkeypatch.setenv("NEXUS_CODEX_EXEC_CWD", str(tmp_path))

    out, _ = _ask_direct_codex_patch(prompt="fix", timeout_sec=7)

    cmd = captured["cmd"]
    assert "--sandbox" in cmd
    assert "read-only" in cmd
    assert out["patch"] == "x = 1\n"
    assert out["model_patch_generated"] is True
    assert out["tokens_used"] == 17263
    assert out["token_capture_status"] == "measured"
    assert out["gateway_total_sec"] >= out["gateway_process_sec"] > 0.0
    assert out["gateway_provider_wait_sec"] == out["gateway_process_sec"]


def test_direct_codex_patch_can_ignore_user_config(monkeypatch, tmp_path: Path):
    captured: dict[str, object] = {}

    def fake_run_process_group(cmd, *, cwd, env, timeout_sec):
        captured["cmd"] = cmd
        last_path = Path(cmd[cmd.index("--output-last-message") + 1])
        last_path.write_text('{"status":"OK","patch":"x = 1\\n"}', encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_process_group", fake_run_process_group)
    monkeypatch.setattr("scripts.bench.capability_ab_runner.shutil.which", lambda _name, **_kwargs: "/tmp/codex")
    monkeypatch.setattr("scripts.bench.capability_ab_runner.Path.exists", lambda _self: True)
    monkeypatch.setenv("NEXUS_CODEX_EXEC_CWD", str(tmp_path))
    monkeypatch.setenv("NEXUS_CODEX_IGNORE_USER_CONFIG", "1")

    _ask_direct_codex_patch(prompt="fix", timeout_sec=7)

    cmd = captured["cmd"]
    assert cmd[cmd.index("exec") + 1] == "--ignore-user-config"


def test_direct_gemini_returned_timeout_is_infra_invalid(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="timeout-return-001",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix timeout",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        repo_kind="neutral_fixture",
        fixture_kind="nexus_value_hidden_state",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    def fake_ask_direct_gemini_flash_patch(*, prompt, timeout_sec):
        return (
            {
                "status": "FAIL",
                "error_category": "timeout",
                "tokens_used": 0,
                "model_name": "gemini-3-flash-preview",
            },
            "",
        )

    monkeypatch.setattr("scripts.bench.capability_ab_runner._ask_direct_gemini_flash_patch", fake_ask_direct_gemini_flash_patch)

    out = run_without_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        mode="gemini",
    )

    assert out["baseline_gateway_error_category"] == "timeout"
    assert out["model_calls"] == 0
    assert out["run_eligible"] is False
    assert out["infra_invalid_reason"] == "timeout_before_model_call"


def test_authorization_task_text_is_not_auth_infra_invalid():
    row = {
        "baseline_raw_tail": "Refactor authorization helper while preserving deny-by-default behavior.",
        "baseline_gateway_error_category": "",
        "model_calls": 1,
        "total_tokens": 10,
        "token_capture_status": "measured",
    }

    out = _annotate_benchmark_eligibility(
        row,
        provider="gemini",
        model_required=True,
        nexus_required=False,
    )

    assert out["run_eligible"] is True
    assert out["infra_invalid_reason"] is None


def test_gemini_auth_confirmation_is_auth_infra_invalid():
    row = {
        "baseline_raw_tail": "Opening authentication page in your browser. Do you want to continue? [Y/n]: ",
        "baseline_gateway_error_category": "auth_confirmation_required",
        "model_calls": 0,
    }

    out = _annotate_benchmark_eligibility(
        row,
        provider="gemini",
        model_required=True,
        nexus_required=False,
    )

    assert out["infra_invalid_reason"] == "auth_failed"


def test_run_process_group_raises_timeout(tmp_path: Path):
    try:
        _run_process_group(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            cwd=tmp_path,
            env=os.environ.copy(),
            timeout_sec=1,
        )
    except Exception as exc:
        assert exc.__class__.__name__ == "TimeoutExpired"
    else:
        raise AssertionError("process group timeout should fail closed")


def test_run_with_nexus_llm_requires_model_and_nexus_evidence(tmp_path: Path, monkeypatch):
    task = CapabilityTask(
        id="nexus-invalid",
        difficulty="medium",
        task_type="public_bugfix",
        task_desc="Fix public bug",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
    )
    target_file, test_file = _materialize_fixture(tmp_path, task)

    class _Proc:
        stdout = '{"status":"SUCCESS","semantic_status":"VERIFIED","result":{"elapsed_sec":0.1,"report":{"attempt_count":1,"model_calls":0,"total_tokens":0,"token_capture_status":"unknown"}}}'
        stderr = ""
        returncode = 0

    monkeypatch.setattr("scripts.bench.capability_ab_runner.subprocess.run", lambda *_args, **_kwargs: _Proc())

    out = run_with_nexus(
        repo_root=tmp_path,
        task=task,
        target_file=target_file,
        test_file=test_file,
        timeout_sec=10,
        force_flow=None,
        runner_mode="subprocess",
        with_llm_mode="all",
    )

    assert out["provider"] == "gemini"
    assert out["run_eligible"] is False
    assert out["infra_invalid_reason"] == "nexus_delivery_invalid"
    assert out["gemini_uses_nexus"] is False
    assert out["nexus_context_delivered"] is False


def test_local_preflight_nexus_delivery_is_eligible_without_model_call():
    row = {
        "status": "SUCCESS",
        "semantic_completed": True,
        "nexus_winner_source": "local_preflight",
        "nexus_context_delivered": True,
        "model_calls": 0,
        "total_tokens": 0,
        "token_capture_status": "not_applicable_local_only",
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "route_built",
        "phase_x": "retrieval_checked",
        "phase_d": "guard_decision",
        "phase_r": "hyper_executed",
        "phase_a": "artifact_verified",
        "phase_c": "closure_written",
    }

    out = _annotate_benchmark_eligibility(
        row,
        provider="gemini",
        model_required=True,
        nexus_required=True,
    )

    assert out["run_eligible"] is True
    assert out["nexus_wearing_valid"] is True
    assert out["nexus_internal_delivery_valid"] is True
    assert out["model_uses_nexus"] is False
    assert out["model_required"] is True
    assert out["model_uplift_eligible"] is False
    assert out["model_uplift_blocked_by_local_delivery"] is True
    assert out["model_uplift_ineligible_reason"] == "no_model_call"
    assert out["public_cost_evidence"] is True


def test_local_hidden_contract_fast_path_nexus_delivery_is_eligible_without_model_call():
    row = {
        "status": "SUCCESS",
        "semantic_completed": True,
        "nexus_winner_source": "local_hidden_contract_fast_path",
        "nexus_context_delivered": True,
        "model_calls": 0,
        "total_tokens": 0,
        "token_capture_status": "not_applicable_local_only",
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "route_built",
        "phase_x": "retrieval_checked",
        "phase_d": "guard_decision",
        "phase_r": "baseline_executed",
        "phase_a": "artifact_verified",
        "phase_c": "closure_written",
    }

    out = _annotate_benchmark_eligibility(
        row,
        provider="gemini",
        model_required=True,
        nexus_required=True,
    )

    assert out["run_eligible"] is True
    assert out["nexus_wearing_valid"] is True
    assert out["nexus_internal_delivery_valid"] is True
    assert out["model_uplift_eligible"] is False
    assert out["model_uplift_blocked_by_local_delivery"] is True
    assert out["model_uplift_ineligible_reason"] == "no_model_call"
    assert out["cost_evidence_class"] == "rescue_only_no_model_call"


def test_final_nexus_retry_row_keeps_route_execution_policy(monkeypatch, tmp_path: Path):
    route_policy = {"reason_codes": ["bounded_retry_keeps_policy"]}
    row = {
        "status": "SUCCESS",
        "semantic_status": "VERIFIED",
        "semantic_completed": True,
        "mode": "with_nexus",
        "task_id": "retry-row",
        "trial_index": 1,
        "route_execution_policy": route_policy,
    }

    _apply_data_contract_audit(row)
    out = _annotate_with_contract(row, provider="gemini", model_required=True, nexus_required=True)

    assert out["route_execution_policy"] == route_policy
    assert "route_execution_policy" in out


def test_local_deterministic_pre_model_rescue_is_eligible_without_model_call():
    row = {
        "status": "SUCCESS",
        "semantic_completed": True,
        "nexus_winner_source": "local_deterministic_pre_model_rescue",
        "nexus_context_delivered": True,
        "model_calls": 0,
        "total_tokens": 0,
        "token_capture_status": "not_applicable_local_only",
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "deterministic_pre_model_preflight",
        "phase_x": "deterministic_pre_model_context_suppressed",
        "phase_d": "deterministic_pre_model_route_decision",
        "phase_r": "deterministic_pre_model_repair",
        "phase_a": "deterministic_pre_model_hidden_verifier",
        "phase_c": "deterministic_pre_model_delivery_receipt",
    }

    out = _annotate_benchmark_eligibility(
        row,
        provider="gemini",
        model_required=True,
        nexus_required=True,
    )

    assert out["run_eligible"] is True
    assert out["nexus_wearing_valid"] is True
    assert out["nexus_internal_delivery_valid"] is True
    assert out["model_uplift_eligible"] is False
    assert out["model_uplift_blocked_by_local_delivery"] is True
    assert out["model_uplift_ineligible_reason"] == "no_model_call"


def test_model_required_local_final_delivery_after_model_call_fails_closed():
    row = {
        "status": "SUCCESS",
        "semantic_completed": True,
        "eligibility_class": "model_required",
        "nexus_winner_source": "local",
        "nexus_context_delivered": True,
        "model_uses_nexus": True,
        "model_calls": 1,
        "total_tokens": 68354,
        "token_capture_status": "measured",
        "model_token_capture_status": "measured",
        "gateway_token_source": "stats",
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "route_built",
        "phase_x": "retrieval_checked",
        "phase_d": "guard_decision",
        "phase_r": "hyper_executed",
        "phase_a": "artifact_verified",
        "phase_c": "closure_written",
    }

    out = _annotate_benchmark_eligibility(
        row,
        provider="gemini",
        model_required=True,
        nexus_required=True,
    )

    assert out["run_eligible"] is False
    assert out["infra_invalid_reason"] == "model_required_local_delivery_blocked"
    assert out["model_uplift_eligible"] is False
    assert out["model_uplift_ineligible_reason"] == "infra_invalid:model_required_local_delivery_blocked"


def test_model_required_local_delivery_block_reason_fails_closed_without_semantic_completion():
    row = {
        "status": "FAILED",
        "semantic_completed": False,
        "eligibility_class": "model_required",
        "nexus_failure_reason": "model_required_local_delivery_blocked",
        "nexus_error_codes": ["model_required_local_delivery_blocked"],
        "nexus_winner_source": "local",
        "nexus_context_delivered": True,
        "model_uses_nexus": True,
        "model_calls": 1,
        "total_tokens": 578675,
        "token_capture_status": "measured",
        "model_token_capture_status": "measured",
        "gateway_token_source": "stats",
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "route_built",
        "phase_x": "retrieval_checked",
        "phase_d": "guard_decision",
        "phase_r": "hyper_executed",
        "phase_a": "artifact_unverified",
        "phase_c": "closure_written",
    }

    out = _annotate_benchmark_eligibility(
        row,
        provider="gemini",
        model_required=True,
        nexus_required=True,
    )

    assert out["run_eligible"] is False
    assert out["infra_invalid_reason"] == "model_required_local_delivery_blocked"
    assert out["model_uplift_eligible"] is False
    assert out["model_uplift_ineligible_reason"] == "infra_invalid:model_required_local_delivery_blocked"


def test_model_required_subprocess_timeout_preserves_timeout_stage_over_nexus_invalid():
    row = {
        "status": "FAILED",
        "semantic_completed": False,
        "eligibility_class": "model_required",
        "timeout_scope": "with_nexus_subprocess",
        "timeout_stage": "timeout_before_receipt",
        "nexus_winner_source": "",
        "nexus_context_delivered": False,
        "model_calls": 0,
        "total_tokens": 0,
        "token_capture_status": "unknown",
    }

    out = _annotate_benchmark_eligibility(
        row,
        provider="gemini",
        model_required=True,
        nexus_required=True,
    )

    assert out["run_eligible"] is False
    assert out["infra_invalid_reason"] == "timeout_before_receipt"
    assert out["model_uplift_ineligible_reason"] == "infra_invalid:timeout_before_receipt"


def test_summarize_benchmark_rows_excludes_infra_invalid_from_solve_rate():
    rows = [
        {"mode": "without_nexus", "run_eligible": True, "status": "SUCCESS", "semantic_completed": True, "report_trust_mismatch": False, "wall_duration_sec": 2.0, "total_tokens": 100, "model_calls": 1},
        {"mode": "without_nexus", "run_eligible": False, "infra_invalid_reason": "quota_exhausted", "status": "FAILED", "semantic_completed": False, "report_trust_mismatch": True, "wall_duration_sec": 3.0, "total_tokens": 0, "model_calls": 1},
        {
            "mode": "with_nexus",
            "run_eligible": True,
            "status": "FAILED",
            "semantic_completed": False,
            "report_trust_mismatch": True,
            "wall_duration_sec": 4.0,
            "phase_wall_total_sec": 1.5,
            "cli_uninstrumented_sec": 2.0,
            "runner_overhead_sec": 0.5,
            "runner_overhead_polluted": True,
            "model_attempt_wall_sec": 1.7,
            "hidden_verifier_wall_sec": 0.2,
            "hidden_retry_wall_sec": 1.1,
            "hidden_retry_verifier_wall_sec": 0.3,
            "total_tokens": 200,
            "model_calls": 2,
        },
    ]

    summary = _summarize_benchmark_rows(rows)

    assert summary["without_nexus"]["total_n"] == 2
    assert summary["without_nexus"]["eligible_n"] == 1
    assert summary["without_nexus"]["infra_invalid_n"] == 1
    assert summary["without_nexus"]["solve_rate"] == 1.0
    assert summary["with_nexus"]["solve_rate"] == 0.0
    assert summary["with_nexus"]["avg_phase_wall_total_sec"] == 1.5
    assert summary["with_nexus"]["avg_cli_uninstrumented_sec"] == 2.0
    assert summary["with_nexus"]["avg_runner_overhead_sec"] == 0.5
    assert summary["with_nexus"]["avg_model_attempt_wall_sec"] == 1.7
    assert summary["with_nexus"]["avg_hidden_verifier_wall_sec"] == 0.2
    assert summary["with_nexus"]["avg_hidden_retry_wall_sec"] == 1.1
    assert summary["with_nexus"]["avg_hidden_retry_verifier_wall_sec"] == 0.3
    assert summary["with_nexus"]["runner_overhead_polluted_n"] == 1


def test_runner_overhead_polluted_flags_subprocess_wrapper_cost():
    assert _runner_overhead_polluted(181.5, 3.5) is True
    assert _runner_overhead_polluted(93.4, 89.9) is False
    assert _runner_overhead_polluted(20.0, None) is False


def test_runner_overhead_classifies_outer_runner_gap():
    assert _runner_overhead_class(181.5, 3.5) == "subprocess_or_outer_runner_gap"
    assert _runner_overhead_class(93.4, 89.9) == "expected_wrapper_gap"
    assert _runner_overhead_class(20.0, None) == "uninstrumented_direct_model"


def test_model_required_policy_does_not_force_strict_baseline_by_default():
    task = CapabilityTask(
        id="model-required-policy",
        difficulty="hard",
        task_type="public_bugfix",
        task_desc="Fix public bug",
        target_file="unused",
        test_file="unused",
        success_criteria="patch_and_tests_pass",
        eligibility_class="model_required",
    )

    policy = _model_required_execution_policy(
        task=task,
        strict_llm_baseline=False,
        skip_llm_baseline=False,
        route_cost_controls={},
    )

    assert policy.require_model_participation is True
    assert policy.require_strict_baseline is False
    assert policy.skip_llm_baseline is False
    assert policy.mode == "model_participation_only"

    direct_policy = _model_required_execution_policy(
        task=task,
        strict_llm_baseline=False,
        skip_llm_baseline=False,
        route_cost_controls={"skip_llm_baseline": True},
    )

    assert direct_policy.require_model_participation is True
    assert direct_policy.require_strict_baseline is False
    assert direct_policy.skip_llm_baseline is True
    assert direct_policy.mode == "model_participation_direct_route"


def test_hyper_admission_skips_unrepairable_model_attempts():
    no_tokens = _hyper_admission_after_model_attempt(
        {"status": "FAILED", "model_calls": 1, "total_tokens": 0}
    )
    assert no_tokens.run_hyper is False
    assert no_tokens.reason == "model_call_without_tokens"

    infra = _hyper_admission_after_model_attempt(
        {"status": "FAILED", "model_calls": 1, "total_tokens": 10, "infra_invalid_reason": "quota_exhausted"}
    )
    assert infra.run_hyper is False
    assert infra.reason == "infra_invalid"

    repairable = _hyper_admission_after_model_attempt(
        {"status": "FAILED", "model_calls": 1, "total_tokens": 10, "nexus_failure_gap": "self_heal_failed"}
    )
    assert repairable.run_hyper is True
    assert repairable.reason == "strict_model_attempt_repairable"


def test_per_task_stop_loss_marks_row_infra_invalid():
    row = {
        "mode": "with_nexus",
        "status": "SUCCESS",
        "wall_duration_sec": 601.0,
        "run_eligible": True,
        "infra_invalid_reason": None,
        "token_reliable": True,
    }

    assert _apply_per_task_stop_loss(row, 600) is True

    assert row["run_eligible"] is False
    assert row["infra_invalid_reason"] == "task_stop_loss_exceeded"
    assert row["runtime_classification"] == "task_stop_loss_exceeded"
    assert row["timeout_scope"] == "benchmark_per_task_stop_loss"
    assert row["timeout_stage"] == "wall_clock_exceeded"
    assert row["timeout_sec"] == 600
    assert row["token_reliable"] is False


def test_per_task_stop_loss_allows_rows_within_budget():
    row = {"wall_duration_sec": 600.0, "run_eligible": True}

    assert _apply_per_task_stop_loss(row, 600) is False

    assert row["run_eligible"] is True
    assert "infra_invalid_reason" not in row


def test_direct_timeout_abort_triggers_only_after_consecutive_without_timeouts():
    timeout_row = {
        "mode": "without_nexus",
        "gateway_error_category": "timeout",
        "infra_invalid_reason": "timeout_before_model_call",
    }
    with_row = {"mode": "with_nexus", "gateway_error_category": "timeout"}
    failed_non_timeout = {"mode": "without_nexus", "gateway_error_category": "parse_failure"}

    assert _direct_provider_timeout_row(timeout_row) is True
    assert _direct_provider_timeout_row(with_row) is False
    assert _direct_provider_timeout_row(failed_non_timeout) is False
    assert _direct_timeout_abort_reason(2, 3) == ""
    assert _direct_timeout_abort_reason(3, 3) == "consecutive_direct_provider_timeouts"
    assert _direct_timeout_abort_reason(3, 0) == ""


def test_direct_infra_abort_triggers_on_consecutive_infra_invalid_rows():
    auth_row = {
        "mode": "without_nexus",
        "run_eligible": False,
        "infra_invalid_reason": "auth_failed",
    }
    eligible_failure = {
        "mode": "without_nexus",
        "run_eligible": True,
        "infra_invalid_reason": "",
    }
    with_row = {
        "mode": "with_nexus",
        "run_eligible": False,
        "infra_invalid_reason": "auth_failed",
    }

    assert _direct_provider_infra_row(auth_row) is True
    assert _direct_provider_infra_row(eligible_failure) is False
    assert _direct_provider_infra_row(with_row) is False
    assert _direct_infra_abort_reason(2, 3) == ""
    assert _direct_infra_abort_reason(3, 3) == "consecutive_direct_provider_infra_invalid"
    assert _direct_infra_abort_reason(3, 0) == ""


def test_partial_markdown_report_marks_public_gate_fail():
    text = _render_partial_markdown_report(
        benchmark_date="2026-04-28",
        with_rows=[{"mode": "with_nexus"}],
        without_rows=[],
        benchmark_summary={"with_nexus": {"eligible_n": 0}},
    )

    assert "Public claim gate: FAIL" in text
    assert "With Nexus rows: 1" in text
    assert "Without Nexus rows: 0" in text
    assert '"eligible_n": 0' in text


def test_benchmark_rows_mark_zero_token_model_calls_unreliable():
    rows = [
        {
            "mode": "with_nexus",
            "run_eligible": True,
            "status": "SUCCESS",
            "semantic_completed": True,
            "report_trust_mismatch": False,
            "wall_duration_sec": 2.0,
            "total_tokens": 0,
            "model_calls": 1,
            "token_capture_status": "unknown",
            "gemini_uses_nexus": True,
            "nexus_context_delivered": True,
            "pillar_lancedb_active": True,
            "pillar_memory_active": True,
            "pillar_mempalace_active": True,
            "pillar_belief_active": True,
            "pillar_artifact_active": True,
            "phase_p": "route_built",
            "phase_x": "retrieval_checked",
            "phase_d": "guard_decision",
            "phase_r": "hyper_executed",
            "phase_a": "artifact_verified",
            "phase_c": "closure_written",
        },
        {
            "mode": "without_nexus",
            "run_eligible": True,
            "status": "SUCCESS",
            "semantic_completed": True,
            "report_trust_mismatch": False,
            "wall_duration_sec": 2.0,
            "total_tokens": 123,
            "model_calls": 1,
            "token_capture_status": "estimated",
        },
    ]

    for row in rows:
        from scripts.bench.capability_ab_runner import _annotate_benchmark_eligibility

        _annotate_benchmark_eligibility(
            row,
            provider="gemini",
            model_required=True,
            nexus_required=row["mode"] == "with_nexus",
        )

    summary = _summarize_benchmark_rows(rows)

    assert rows[0]["token_reliable"] is False
    assert rows[0]["token_unreliable_reason"] == "model_call_without_tokens"
    assert rows[1]["token_reliable"] is False
    assert rows[1]["token_unreliable_reason"] == "estimated_tokens"
    assert rows[0]["run_eligible"] is False
    assert rows[0]["infra_invalid_reason"] == "model_call_without_tokens"
    assert summary["with_nexus"]["infra_invalid_n"] == 1
    assert summary["with_nexus"]["token_reliable_rate"] is None
    assert summary["without_nexus"]["token_reliable_rate"] == 0.0
    assert summary["with_nexus"]["model_required_n"] == 0
    assert summary["with_nexus"]["model_uplift_eligible_n"] == 0
    assert summary["with_nexus"]["model_uplift_ineligible_reasons"] == []


def test_direct_model_call_without_tokens_is_infra_invalid():
    row = {
        "mode": "without_nexus",
        "status": "FAILED",
        "semantic_completed": False,
        "report_trust_mismatch": False,
        "wall_duration_sec": 2.8,
        "total_tokens": 0,
        "model_calls": 1,
        "token_capture_status": "unknown",
    }

    _annotate_benchmark_eligibility(
        row,
        provider="gemini",
        model_required=True,
        nexus_required=False,
    )

    assert row["run_eligible"] is False
    assert row["infra_invalid_reason"] == "model_call_without_tokens"
    assert row["model_uplift_ineligible_reason"] == "infra_invalid:model_call_without_tokens"


def test_benchmark_rows_mark_unhelpful_local_fallback():
    row = {
        "mode": "with_nexus",
        "status": "FAILED",
        "semantic_completed": False,
        "report_trust_mismatch": False,
        "wall_duration_sec": 2.0,
        "total_tokens": 108,
        "model_calls": 1,
        "token_capture_status": "estimated",
        "gateway_error_category": "timeout",
        "fallback_used": True,
        "nexus_winner_source": "local",
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "route_built",
        "phase_x": "retrieval_checked",
        "phase_d": "guard_decision",
        "phase_r": "hyper_executed",
        "phase_a": "artifact_unverified",
        "phase_c": "closure_written",
    }

    _annotate_benchmark_eligibility(row, provider="gemini", model_required=True, nexus_required=True)
    summary = _summarize_benchmark_rows([row])

    assert row["local_fallback_unhelpful"] is True
    assert summary["with_nexus"]["local_fallback_unhelpful_rate"] == 1.0


def test_benchmark_row_classifies_model_timeout_with_local_fallback():
    row = {
        "mode": "with_nexus",
        "run_eligible": True,
        "status": "SUCCESS",
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "wall_duration_sec": 2.0,
        "total_tokens": 0,
        "model_calls": 1,
        "token_capture_status": "unknown",
        "gateway_error_category": "timeout",
        "fallback_used": True,
        "nexus_winner_source": "local_only",
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "route_built",
        "phase_x": "retrieval_checked",
        "phase_d": "guard_decision",
        "phase_r": "hyper_executed",
        "phase_a": "artifact_verified",
        "phase_c": "closure_written",
    }

    _annotate_benchmark_eligibility(row, provider="gemini", model_required=True, nexus_required=True)
    summary = _summarize_benchmark_rows([row])

    assert row["model_timeout_local_fallback"] is True
    assert row["public_cost_evidence"] is False
    assert row["rescue_cost_status"] == "local_after_model_timeout"
    assert row["token_reliable"] is False
    assert row["token_unreliable_reason"] == "model_timeout_with_local_fallback"
    assert row["run_eligible"] is False
    assert row["infra_invalid_reason"] == "model_call_without_tokens"
    assert summary["with_nexus"]["token_unreliable_reasons"] == []
    assert summary["with_nexus"]["model_uplift_eligible_rate"] is None


def test_benchmark_row_marks_clean_model_cost_evidence():
    row = {
        "mode": "with_nexus",
        "run_eligible": True,
        "status": "SUCCESS",
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "wall_duration_sec": 2.0,
        "total_tokens": 1200,
        "model_calls": 1,
        "token_measured": True,
        "token_capture_status": "measured",
        "gateway_token_source": "usage_metadata",
        "nexus_winner_source": "model_patch",
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "route_built",
        "phase_x": "retrieval_checked",
        "phase_d": "guard_decision",
        "phase_r": "hyper_executed",
        "phase_a": "artifact_verified",
        "phase_c": "closure_written",
    }

    _annotate_benchmark_eligibility(row, provider="gemini", model_required=True, nexus_required=True)
    summary = _summarize_benchmark_rows([row])

    assert row["model_uplift_eligible"] is True
    assert row["model_uplift_ineligible_reason"] is None
    assert row["public_cost_evidence"] is True
    assert row["clean_model_cost_evidence"] is True
    assert row["cost_evidence_class"] == "clean_model_cost"
    assert row["training_eligible_cost_evidence"] is True
    assert row["training_cost_evidence_class"] == "training_clean_model_cost"
    assert summary["with_nexus"]["clean_model_cost_evidence_rate"] == 1.0
    assert summary["with_nexus"]["training_eligible_cost_evidence_rate"] == 1.0
    assert summary["with_nexus"]["model_uplift_eligible_rate"] == 1.0


def test_benchmark_row_uses_clean_retry_attempt_cost_when_outer_wall_is_polluted():
    row = {
        "mode": "with_nexus",
        "run_eligible": True,
        "status": "SUCCESS",
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "wall_duration_sec": 254.0,
        "runner_overhead_polluted": True,
        "model_attempt_wall_sec": 35.0,
        "model_attempt_runner_overhead_sec": 0.2,
        "model_attempt_runner_overhead_polluted": False,
        "hidden_retry_used": True,
        "hidden_retry_reason": "hidden_verifier_failure_bounded_nexus_retry",
        "total_tokens": 42681,
        "model_calls": 1,
        "token_measured": True,
        "token_capture_status": "measured",
        "gateway_token_source": "stats",
        "nexus_winner_source": "nexus_llm_baseline",
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "route_built",
        "phase_x": "retrieval_checked",
        "phase_d": "guard_decision",
        "phase_r": "baseline_executed",
        "phase_a": "artifact_verified",
        "phase_c": "closure_written",
    }

    _annotate_benchmark_eligibility(row, provider="gemini", model_required=True, nexus_required=True)

    assert row["clean_model_cost_evidence"] is True
    assert row["cost_evidence_class"] == "clean_model_cost"


def test_benchmark_row_splits_model_tokens_from_local_rescue():
    from scripts.bench.capability_ab_runner import _annotate_benchmark_eligibility

    row = {
        "mode": "with_nexus",
        "run_eligible": True,
        "status": "SUCCESS",
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "wall_duration_sec": 2.0,
        "total_tokens": 112,
        "model_calls": 1,
        "token_capture_status": "not_applicable_local_only",
        "gateway_stats_present": True,
        "gateway_usage_metadata_present": False,
        "gateway_token_source": "stats",
        "gateway_prompt_chars": 10,
        "gateway_payload_chars": 20,
        "gateway_total_chars": 30,
        "gateway_timeout_sec": 60,
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "nexus_rescued": True,
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "route_built",
        "phase_x": "retrieval_checked",
        "phase_d": "guard_decision",
        "phase_r": "hyper_executed",
        "phase_a": "artifact_verified",
        "phase_c": "closure_written",
    }

    _annotate_benchmark_eligibility(
        row,
        provider="gemini",
        model_required=True,
        nexus_required=True,
    )

    assert row["model_total_tokens"] == 112
    assert row["model_token_capture_status"] == "estimated"
    assert row["local_rescue_tokens"] == 0
    assert row["rescue_cost_status"] == "local_only"
    assert row["gateway_stats_present"] is True
    assert row["gateway_usage_metadata_present"] is False
    assert row["gateway_token_source"] == "stats"
    assert row["gateway_total_chars"] == 30
    assert row["gateway_timeout_sec"] == 60
    assert row["token_reliable"] is False
    assert row["token_unreliable_reason"] == "local_only_rescue_not_model_comparable"
    assert row["clean_model_cost_evidence"] is False
    assert row["cost_evidence_class"] == "rescue_with_model_fallback"
    assert row["training_eligible_cost_evidence"] is False
    assert "token_unreliable" in row["training_cost_evidence_reasons"]


def test_feature_reflex_row_can_be_training_eligible_with_gwt_and_hidden_verifier():
    row = {
        "mode": "with_nexus",
        "run_eligible": True,
        "status": "SUCCESS",
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "wall_duration_sec": 2.0,
        "total_tokens": 1200,
        "model_calls": 1,
        "token_measured": True,
        "token_capture_status": "measured",
        "gateway_token_source": "stats",
        "nexus_winner_source": "supervised_bare_first",
        "feature_reflex_route": True,
        "gwt_artifact_present": True,
        "hidden_verifier_passed": True,
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "route_built",
        "phase_x": "retrieval_checked",
        "phase_d": "guard_decision",
        "phase_r": "feature_reflex_verified",
        "phase_a": "artifact_verified",
        "phase_c": "closure_written",
    }

    _annotate_benchmark_eligibility(row, provider="gemini", model_required=True, nexus_required=True)
    summary = _summarize_benchmark_rows([row])

    assert row["clean_model_cost_evidence"] is True
    assert row["training_eligible_cost_evidence"] is True
    assert row["training_cost_evidence_class"] == "training_clean_model_cost"
    assert summary["with_nexus"]["training_eligible_cost_evidence_rate"] == 1.0


def test_stats_token_outlier_is_not_public_reliable():
    row = {
        "mode": "with_nexus",
        "run_eligible": True,
        "status": "SUCCESS",
        "semantic_completed": True,
        "report_trust_mismatch": False,
        "wall_duration_sec": 2.0,
        "total_tokens": 816217,
        "model_calls": 1,
        "token_capture_status": "measured",
        "gateway_stats_present": True,
        "gateway_usage_metadata_present": False,
        "gateway_token_source": "stats",
        "gateway_total_chars": 2055,
        "gemini_uses_nexus": True,
        "nexus_context_delivered": True,
        "pillar_lancedb_active": True,
        "pillar_memory_active": True,
        "pillar_mempalace_active": True,
        "pillar_belief_active": True,
        "pillar_artifact_active": True,
        "phase_p": "route_built",
        "phase_x": "retrieval_checked",
        "phase_d": "guard_decision",
        "phase_r": "hyper_executed",
        "phase_a": "artifact_verified",
        "phase_c": "closure_written",
    }

    _annotate_benchmark_eligibility(row, provider="gemini", model_required=True, nexus_required=True)

    assert row["token_reliable"] is False
    assert row["token_unreliable_reason"] == "stats_outlier_possible_cumulative"
    assert row["provider_stats_cumulative_suspected"] is True
    assert row["token_accounting_failure_class"] == "provider_stats_outlier"


def test_force_learn_slo_ready_writes_pass_summary(tmp_path: Path):
    _force_learn_slo_ready(tmp_path)
    payload = json.loads((tmp_path / ".nexus" / "reports" / "learn" / "phase_slo_summary.json").read_text(encoding="utf-8"))
    assert payload["phase_slo_pass"] is True
    assert payload["global"]["required_done_ratio"] == 1.0
    assert payload["public_lane_eligible"] is False
    assert payload["evidence_class"] == "synthetic_readiness_shortcut"


def test_sanitized_runner_learn_metadata_hook_commits_only_allowed_files(tmp_path: Path):
    with tempfile.TemporaryDirectory(prefix="nexus-live-clean-runner-hook-", dir="/private/tmp") as root_str:
        root = Path(root_str)
        subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "nexus-temp@example.test"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Nexus Temp Runner"], check=True)
        (root / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-m", "base"], check=True, capture_output=True, text=True)
        learn_dir = root / ".nexus" / "reports" / "learn"
        learn_dir.mkdir(parents=True)
        (learn_dir / "phase_slo_summary.json").write_text('{"phase_slo_pass":true}\n', encoding="utf-8")
        (learn_dir / "phase_writeback.jsonl").write_text('{"event":"run"}\n', encoding="utf-8")
        (learn_dir / "x1_readiness_history.json").write_text('[{"x1_readiness_pass":true}]\n', encoding="utf-8")
        hook = tmp_path / "commit_learn_metadata.sh"
        hook.write_text(_learn_metadata_commit_hook(runner_root=root), encoding="utf-8")

        subprocess.run(["sh", str(hook)], check=True, capture_output=True, text=True)

        status = subprocess.run(
            ["git", "-C", str(root), "status", "--short", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        )
        log = subprocess.run(["git", "-C", str(root), "log", "-1", "--pretty=%s"], check=True, capture_output=True, text=True)
        assert status.stdout == ""
        assert log.stdout.strip() == "temp-runner-learn-metadata"


def test_sanitized_runner_learn_metadata_hook_does_not_hide_other_dirty_entries(tmp_path: Path):
    with tempfile.TemporaryDirectory(prefix="nexus-live-clean-runner-hook-", dir="/private/tmp") as root_str:
        root = Path(root_str)
        subprocess.run(["git", "-C", str(root), "init"], check=True, capture_output=True, text=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "nexus-temp@example.test"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Nexus Temp Runner"], check=True)
        (root / "README.md").write_text("base\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-m", "base"], check=True, capture_output=True, text=True)
        learn_dir = root / ".nexus" / "reports" / "learn"
        learn_dir.mkdir(parents=True)
        (learn_dir / "phase_slo_summary.json").write_text('{"phase_slo_pass":true}\n', encoding="utf-8")
        (learn_dir / "x1_readiness_history.json").write_text('[{"x1_readiness_pass":true}]\n', encoding="utf-8")
        (root / "unexpected.txt").write_text("dirty\n", encoding="utf-8")
        hook = tmp_path / "commit_learn_metadata.sh"
        hook.write_text(_learn_metadata_commit_hook(runner_root=root), encoding="utf-8")

        subprocess.run(["sh", str(hook)], check=True, capture_output=True, text=True)

        status = subprocess.run(
            ["git", "-C", str(root), "status", "--short", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        )
        log = subprocess.run(["git", "-C", str(root), "log", "-1", "--pretty=%s"], check=True, capture_output=True, text=True)
        assert "unexpected.txt" in status.stdout
        assert ".nexus/reports/learn/phase_slo_summary.json" in status.stdout
        assert ".nexus/reports/learn/x1_readiness_history.json" in status.stdout
        assert log.stdout.strip() == "base"


def test_sanitized_runner_session_marker_hook_clears_only_current_session(tmp_path: Path):
    current = "sanitized-gemini-3-flash-preview-current"
    other = "sanitized-gemini-3-flash-preview-other"
    current_markers = _session_marker_paths(session_id=current)
    other_markers = _session_marker_paths(session_id=other)
    for marker in (*current_markers, *other_markers):
        marker.write_text("started\n", encoding="utf-8")
    hook = tmp_path / "clear_session_markers.sh"
    hook.write_text(_session_marker_reset_hook(session_id=current), encoding="utf-8")

    subprocess.run(["sh", str(hook)], check=True, capture_output=True, text=True)

    assert all(not marker.exists() for marker in current_markers)
    assert all(marker.exists() for marker in other_markers)
    for marker in other_markers:
        marker.unlink(missing_ok=True)


def test_sanitized_runner_package_uses_clean_guard_and_direct_timeout(tmp_path: Path):
    source_manifest = tmp_path / "tasks.json"
    source_manifest.write_text(
        json.dumps(
            {
                "version": "1",
                "frozen": True,
                "benchmark_id": "demo",
                "tasks": [
                    {
                        "id": "task-1",
                        "category": "bugfix",
                        "difficulty": "hard",
                        "repo_kind": "neutral_fixture",
                        "repo": "fixture://demo",
                        "repo_ref": "v1",
                        "task_desc": "Fix demo",
                        "fixture_kind": "python_demo",
                        "success_criteria": "patch_and_tests_pass",
                        "expected_capabilities": ["claim_gate", "delivery_gate"],
                        "capability_activation_contract": "required",
                        "hidden_oracle_kind": "pytest_hidden",
                        "eligibility_class": "model_required",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    runner_path = tmp_path / "repo" / "scripts" / "bench" / "capability_ab_runner.py"
    runner_path.parent.mkdir(parents=True)
    runner_path.write_text("# runner\n", encoding="utf-8")

    manifest = build_sanitized_runner(
        source_manifest=source_manifest,
        output_dir=tmp_path / "pkg",
        runner_path=runner_path,
        model_name="gemini-3-flash-preview",
        provider="gemini",
        max_tasks=1,
    )

    run_command = manifest["run_command"]
    assert "NEXUS_DIRECT_GEMINI_TIMEOUT_SEC=240" in run_command
    assert "--with-model-provider gemini" in run_command
    assert "--timeout-sec 240" in run_command
    assert "--require-clean-worktree" in run_command

    pro_manifest = build_sanitized_runner(
        source_manifest=source_manifest,
        output_dir=tmp_path / "pkg-pro",
        runner_path=runner_path,
        model_name="gemini-3.1-pro-preview",
        provider="gemini",
        max_tasks=1,
    )
    assert pro_manifest["session_worker_id"].startswith("sanitized-gemini-3_1-pro-preview-")
    assert "." not in pro_manifest["session_worker_id"]

    codex_manifest = build_sanitized_runner(
        source_manifest=source_manifest,
        output_dir=tmp_path / "pkg-codex",
        runner_path=runner_path,
        model_name="gpt-5.5",
        provider="codex",
        max_tasks=1,
    )
    codex_command = codex_manifest["run_command"]
    assert "NEXUS_DIRECT_CODEX_MODEL=gpt-5.5" in codex_command
    assert "NEXUS_CODEX_EXEC_CWD=" in codex_command
    assert "--without-mode codex" in codex_command
    assert "--with-model-provider codex" in codex_command
    assert "NEXUS_GEMINI_MODEL_NAME" not in codex_command

    baseline_manifest = build_sanitized_runner(
        source_manifest=source_manifest,
        output_dir=tmp_path / "pkg-codex-baseline",
        runner_path=runner_path,
        model_name="gpt-5.5",
        provider="codex",
        max_tasks=1,
        baseline_only=True,
    )
    baseline_command = baseline_manifest["run_command"]
    assert baseline_manifest["baseline_only"] == "True"
    assert "--without-only" in baseline_command
    assert baseline_manifest["run_script"].endswith("run_codex_gpt_5_5_direct_baseline.sh")


def test_main_rejects_always_on_eval_with_forced_hyper(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capability_ab_runner.py",
            "--tasks-file",
            "scripts/bench/public_benchmark_nexus_value_v1.json",
            "--output-dir",
            ".nexus/reports/test_always_on_eval",
            "--always-on-eval",
            "--force-flow",
            "hyper_sprint",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2


def test_main_rejects_always_on_eval_with_skip_llm_baseline(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capability_ab_runner.py",
            "--tasks-file",
            "scripts/bench/public_benchmark_nexus_value_v1.json",
            "--output-dir",
            ".nexus/reports/test_always_on_eval",
            "--always-on-eval",
            "--skip-llm-baseline",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2


def test_hybrid_route_h2_local_assist_trace(tmp_path, monkeypatch):
    from scripts.bench.capability_ab_runner import _finalize_with_nexus_row, write_evidence_bundle
    from scripts.bench.capability_ab_runner import CapabilityTask
    
    task = CapabilityTask(
        id="test-task-1",
        difficulty="easy",
        task_type="test_repair",
        task_desc="test description for task compression",
        target_file="target.py",
        test_file="test_target.py",
        expected_capabilities=["mempalace_gate"],
        success_criteria="tests_pass",
        repo_kind="nexus_internal",
        fixture_kind="test_fixture"
    )

    # Use a call-counting mock to prove probe is NOT called when gate is off
    probe_call_count = {"n": 0}
    def _mock_ollama_probe():
        probe_call_count["n"] += 1
        return True
    monkeypatch.setattr("scripts.bench.capability_ab_runner._is_ollama_available", _mock_ollama_probe)
    
    # CASE 1: Gate Off (H1 trace-only)
    monkeypatch.setenv("NEXUS_HYBRID_LOCAL_ASSIST_TRACE", "0")
    row_gemini_gate_off = {
        "mode": "with_nexus", 
        "model_calls": 1,
        "total_tokens": 100,
        "token_capture_status": "measured",
        "hidden_verifier_stdout_tail": "FAILED test_foo.py - AssertionError: expected 1 got 2"
    }
    finalized_gemini_off = _finalize_with_nexus_row(
        row_gemini_gate_off,
        provider="gemini",
        model_required=True,
        nexus_required=False,
        task=task,
        repo_root=tmp_path
    )
    
    hr_gemini_off = finalized_gemini_off["hybrid_route"]
    assert hr_gemini_off["route_mode"] == "cloud_assisted_by_local_trace_only"
    assert hr_gemini_off["cloud_provider"] == "gemini"
    assert hr_gemini_off["cloud_provider_selected"] is True
    assert hr_gemini_off["cloud_available"] is True
    assert hr_gemini_off["cloud_availability_source"] == "provider_selected_not_probe"
    assert hr_gemini_off["local_provider"] == "ollama"
    assert hr_gemini_off["local_available"] is False  # not probed when gate is off
    assert hr_gemini_off["cloud_model_invoked"] is True
    assert hr_gemini_off["local_model_invoked"] is False
    assert hr_gemini_off["local_assist_invoked"] is False
    assert hr_gemini_off["trace_only"] is True
    assert hr_gemini_off["behavior_changed"] is False
    
    la_gemini_off = finalized_gemini_off["local_assist"]
    assert la_gemini_off["mode"] == "trace_only"
    assert la_gemini_off["prompt_replaced"] is False
    assert la_gemini_off["raw_context_chars"] == 0
    assert la_gemini_off["compact_context_chars"] == 0
    assert la_gemini_off["compression_ratio"] == 0.0
    assert la_gemini_off["raw_artifact_ref"] == ""
    assert la_gemini_off["omitted_bytes"] == 0
    assert la_gemini_off["memory_selected_ids"] == []
    assert la_gemini_off["memory_source"] == "none"
    assert la_gemini_off["memory_no_match"] is True

    # Critical: probe must NOT be called when gate is off
    assert probe_call_count["n"] == 0, "_is_ollama_available must not be called when NEXUS_HYBRID_LOCAL_ASSIST_TRACE=0"
    assert hr_gemini_off["local_available"] is False
    assert hr_gemini_off["local_availability_source"] == "not_probed_trace_only"

    # CASE 2: Gate On (H2 deterministic assist trace)
    monkeypatch.setenv("NEXUS_HYBRID_LOCAL_ASSIST_TRACE", "1")
    row_gemini_gate_on = {
        "mode": "with_nexus", 
        "model_calls": 1,
        "total_tokens": 100,
        "token_capture_status": "measured",
        "hidden_verifier_stdout_tail": "FAILED test_foo.py - AssertionError: expected 1 got 2"
    }
    finalized_gemini_on = _finalize_with_nexus_row(
        row_gemini_gate_on,
        provider="gemini",
        model_required=True,
        nexus_required=False,
        task=task,
        repo_root=tmp_path
    )
    
    hr_gemini_on = finalized_gemini_on["hybrid_route"]
    assert hr_gemini_on["local_assist_invoked"] is True
    
    la_gemini_on = finalized_gemini_on["local_assist"]
    assert la_gemini_on["mode"] == "deterministic_pre_cloud"
    assert la_gemini_on["prompt_replaced"] is False
    assert la_gemini_on["raw_context_chars"] > 0
    assert la_gemini_on["compact_context_chars"] > 0
    assert la_gemini_on["raw_artifact_ref"] == "hidden_verifier_stdout_tail"
    # Gate On: adapter actually ran, memory_source reflects real store (or "none" if no match)
    assert isinstance(la_gemini_on["memory_source"], str)
    # memory_no_match must be consistent: True iff memory_selected_ids is empty
    assert la_gemini_on["memory_no_match"] is (len(la_gemini_on["memory_selected_ids"]) == 0)

    # Gate On: probe WAS called
    assert probe_call_count["n"] >= 1, "_is_ollama_available must be called when NEXUS_HYBRID_LOCAL_ASSIST_TRACE=1"
    assert hr_gemini_on["local_availability_source"] == "ollama_api_tags_probe"

    # CASE 3: provider=ollama has cloud_provider "none" (gate reset to off for isolation)
    monkeypatch.delenv("NEXUS_HYBRID_LOCAL_ASSIST_TRACE", raising=False)
    row_ollama = {"mode": "with_nexus", "model_calls": 0}
    finalized_ollama = _finalize_with_nexus_row(
        row_ollama,
        provider="ollama",
        model_required=True,
        nexus_required=False,
        task=task,
        repo_root=tmp_path
    )
    
    hr_ollama = finalized_ollama["hybrid_route"]
    assert hr_ollama["route_mode"] == "local_only_blocked"
    assert hr_ollama["cloud_provider"] == "none"
    assert hr_ollama["cloud_provider_selected"] is False
    assert hr_ollama["cloud_available"] is False
    assert hr_ollama["local_available"] is False  # gate off: not probed
    assert hr_ollama["cloud_model_invoked"] is False
    assert hr_ollama["local_model_invoked"] is False
    
    # CASE 4: write_evidence_bundle summary verification
    rows = [finalized_gemini_off, finalized_gemini_on, finalized_ollama]
    config = {
        "tasks_file": "tasks.json",
        "tasks_manifest_hash": "manifest_hash",
        "unique_tasks_requested": 1,
        "repeat_trials": 1,
        "timeout_sec": 60,
    }
    
    with_path = tmp_path / "with.json"
    without_path = tmp_path / "without.json"
    with_path.write_text("[]")
    without_path.write_text("[]")
    
    monkeypatch.setattr("scripts.bench.capability_ab_runner._git_commit", lambda x: "dummy-commit")
    
    bundle_file = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=rows,
        config=config
    )
    
    import json
    bundle_data = json.loads(bundle_file.read_text())
    
    assert "hybrid_route_summary" in bundle_data
    summary = bundle_data["hybrid_route_summary"]
    assert "cloud_assisted_by_local_trace_only" in summary["modes_observed"]
    assert "local_only_blocked" in summary["modes_observed"]
    assert summary["trace_only_count"] == 2
    assert summary["local_only_blocked_count"] == 1
    assert summary["local_assist_trace_count"] == 1
    assert summary["behavior_changed_count"] == 0
    assert summary["prompt_replaced_count"] == 0


def test_hybrid_route_h3_local_guard_trace_is_advisory_only(tmp_path, monkeypatch):
    from scripts.bench.capability_ab_runner import CapabilityTask, _finalize_with_nexus_row, write_evidence_bundle

    task = CapabilityTask(
        id="test-task-h3",
        difficulty="easy",
        task_type="test_repair",
        task_desc="repair a failing assertion without changing delivery gates",
        target_file="target.py",
        test_file="test_target.py",
        expected_capabilities=("claim_gate",),
        success_criteria="tests_pass",
        repo_kind="nexus_internal",
        fixture_kind="test_fixture",
    )

    guard_calls = {"n": 0}

    def fake_local_guard(*, row, task):
        guard_calls["n"] += 1
        return {
            "schema": "nexus.hybrid_local_guard.v1",
            "enabled": True,
            "authority": "advisory_only",
            "roles": [
                "evidence_consistency_critic",
                "patch_protocol_critic",
                "claim_precheck",
            ],
            "verdict": "warn",
            "blocked_delivery": False,
            "behavior_changed": False,
            "reason_codes": ["claim_precheck_warning"],
        }

    monkeypatch.setattr("scripts.bench.capability_ab_runner._run_hybrid_local_guard_trace", fake_local_guard, raising=False)
    monkeypatch.setenv("NEXUS_HYBRID_LOCAL_GUARD_TRACE", "0")

    gate_off = _finalize_with_nexus_row(
        {
            "mode": "with_nexus",
            "model_calls": 1,
            "total_tokens": 100,
            "token_capture_status": "measured",
        },
        provider="gemini",
        model_required=True,
        nexus_required=False,
        task=task,
        repo_root=tmp_path,
    )

    assert guard_calls["n"] == 0
    assert gate_off["local_guard"]["enabled"] is False
    assert gate_off["local_guard_invoked"] is False
    assert gate_off["behavior_changed"] is False

    monkeypatch.setenv("NEXUS_HYBRID_LOCAL_GUARD_TRACE", "1")

    gate_on = _finalize_with_nexus_row(
        {
            "mode": "with_nexus",
            "model_calls": 1,
            "total_tokens": 100,
            "token_capture_status": "measured",
            "hidden_verifier_stdout_tail": "FAILED test_target.py - AssertionError",
        },
        provider="gemini",
        model_required=True,
        nexus_required=False,
        task=task,
        repo_root=tmp_path,
    )

    assert guard_calls["n"] == 1
    assert gate_on["local_guard_invoked"] is True
    assert gate_on["local_guard"] == {
        "schema": "nexus.hybrid_local_guard.v1",
        "enabled": True,
        "authority": "advisory_only",
        "roles": [
            "evidence_consistency_critic",
            "patch_protocol_critic",
            "claim_precheck",
        ],
        "verdict": "warn",
        "blocked_delivery": False,
        "behavior_changed": False,
        "reason_codes": ["claim_precheck_warning"],
    }
    assert gate_on["local_guard"]["blocked_delivery"] is False
    assert gate_on["local_guard"]["behavior_changed"] is False
    assert gate_on["behavior_changed"] is False
    assert gate_on["local_assist"]["prompt_replaced"] is False

    with_path = tmp_path / "with.jsonl"
    without_path = tmp_path / "without.jsonl"
    with_path.write_text("[]", encoding="utf-8")
    without_path.write_text("[]", encoding="utf-8")
    monkeypatch.setattr("scripts.bench.capability_ab_runner._git_commit", lambda x: "dummy-commit")

    bundle_file = write_evidence_bundle(
        out_dir=tmp_path,
        with_path=with_path,
        without_path=without_path,
        rows=[gate_off, gate_on],
        config={
            "tasks_file": "tasks.json",
            "tasks_manifest_hash": "manifest_hash",
            "unique_tasks_requested": 1,
            "repeat_trials": 1,
            "timeout_sec": 60,
        },
    )

    bundle_data = json.loads(bundle_file.read_text(encoding="utf-8"))
    summary = bundle_data["hybrid_route_summary"]
    assert summary["local_guard_trace_count"] == 1
    assert summary["local_guard_warn_count"] == 1
    assert summary["local_guard_fail_count"] == 0
    assert summary["local_guard_blocked_delivery_count"] == 0
    assert summary["behavior_changed_count"] == 0


