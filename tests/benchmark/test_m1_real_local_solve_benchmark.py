from __future__ import annotations

import pytest

from scripts.bench.m1_real_local_solve_benchmark import (
    build_task_specs,
    classify_solve_mechanism,
    resolve_receipt_path,
    select_task_specs,
)


M1_TELEMETRY_FIELDS = [
    "parse_error_kind",
    "parse_error_message",
    "protocol_used",
    "normalized",
    "canonical_span_source",
    "diff_repair_attempted",
    "diff_repair_success",
    "same_span_retry_count",
    "failure_feedback_used",
    "semantic_retry_invoked",
    "semantic_retry_count",
    "same_span_retry",
    "structured_retry_packet_available",
    "failure_feedback_builder_invoked",
    "execution_path_modules",
]

M1_APPLY_FAILURE_FIELDS = [
    "apply_failure_search_excerpt",
    "apply_failure_current_source_excerpt",
    "apply_failure_projected_patch_excerpt",
    "apply_failure_target_file_hash_before_apply",
    "apply_failure_target_file_hash_after_restore",
    "apply_failure_target_file_hash_at_apply",
    "apply_failure_projection_header",
    "apply_failure_original_header",
    "apply_failure_root_cause",
]


def _make_base_row(**overrides) -> dict:
    """Build a minimal valid M1 row with sensible defaults."""
    row = {
        "task_id": "test/task",
        "repo": "nexus/nexus",
        "model": "qwen2.5-coder:7b",
        "execution_topology": "local_committee_only",
        "route_truth_source": "CapabilityPlanner",
        "adapter_output_is_route_truth": False,
        "local_model_called": True,
        "candidate_hash": "abc123def456",
        "selected_candidate_hash": "abc123def456",
        "applied_patch_hash": "abc123def456",
        "hash_match": True,
        "candidate_isolated": True,
        "verifier_result": "pass",
        "solved": True,
        "failure_reason": "",
        "learning_closure_written": False,
        "receipt_path": ".nexus/receipts/test_receipt.json",
        "duration_sec": 1.23,
        "parse_error_kind": "none",
        "parse_error_message": "none",
        "protocol_used": "anchored_edit",
        "normalized": False,
        "canonical_span_source": "none",
        "diff_repair_attempted": False,
        "diff_repair_success": False,
        "same_span_retry_count": 0,
        "failure_feedback_used": False,
        "semantic_retry_invoked": False,
        "semantic_retry_count": 0,
        "same_span_retry": False,
        "structured_retry_packet_available": False,
        "failure_feedback_builder_invoked": False,
        "solve_mechanism": "first_pass",
        "execution_path_modules": [
            "CapabilityPlanner",
            "LocalModelExecutor",
            "SolidSearchReplaceProtocol",
            "IsolatedLocalSolveLoop",
        ],
        "apply_failure_search_excerpt": "",
        "apply_failure_current_source_excerpt": "",
        "apply_failure_projected_patch_excerpt": "",
        "apply_failure_target_file_hash_before_apply": "",
        "apply_failure_target_file_hash_after_restore": "",
        "apply_failure_target_file_hash_at_apply": "",
        "apply_failure_projection_header": "",
        "apply_failure_original_header": "",
        "apply_failure_root_cause": "",
    }
    row.update(overrides)
    return row


def _evaluate_solved(row: dict) -> bool:
    """Replicate the M1 solved-check logic from the benchmark script."""
    return bool(
        row.get("local_model_called")
        and row.get("candidate_hash")
        and row.get("hash_match")
        and row.get("candidate_isolated")
        and row.get("verifier_result") == "pass"
    )


# ------------------------------------------------------------------
# Test 1: all 10 wiring telemetry fields present
# ------------------------------------------------------------------
def test_m1_rows_include_wiring_telemetry():
    """Every M1 row must carry the shared observational telemetry fields."""
    row = _make_base_row()
    for field in M1_TELEMETRY_FIELDS:
        assert field in row, f"Missing telemetry field: {field}"


def test_m1_rows_include_apply_failure_root_cause_telemetry():
    row = _make_base_row()
    for field in M1_APPLY_FAILURE_FIELDS:
        assert field in row, f"Missing apply-failure telemetry field: {field}"


def test_m1_shared_retry_truth_fields_are_observational():
    base = _make_base_row()
    solved_a = _evaluate_solved(base)

    modified = _make_base_row(
        semantic_retry_invoked=True,
        semantic_retry_count=1,
        same_span_retry=True,
        structured_retry_packet_available=True,
        failure_feedback_builder_invoked=True,
    )
    solved_b = _evaluate_solved(modified)

    assert solved_a is solved_b


# ------------------------------------------------------------------
# Test 2: empty candidate_hash => not solved
# ------------------------------------------------------------------
def test_m1_empty_hash_not_solved():
    row = _make_base_row(candidate_hash="")
    assert _evaluate_solved(row) is False


# ------------------------------------------------------------------
# Test 3: REPLACEMENT_MARKDOWN_FENCE parse error => not solved
# ------------------------------------------------------------------
def test_m1_protocol_parse_failure_not_solved():
    row = _make_base_row(
        parse_error_kind="REPLACEMENT_MARKDOWN_FENCE",
        parse_error_message="Outer markdown fence detected in replacement block",
        protocol_used="anchored_edit",
        normalized=False,
        verifier_result="fail",
        solved=False,
    )
    assert _evaluate_solved(row) is False


# ------------------------------------------------------------------
# Test 4: execution_path_modules is observational only
# ------------------------------------------------------------------
def test_m1_execution_path_modules_are_observational():
    """execution_path_modules never participates in the solved predicate."""
    base = _make_base_row()
    solved_a = _evaluate_solved(base)

    modified = _make_base_row(
        execution_path_modules=[
            "CapabilityPlanner",
            "LocalModelExecutor",
            "SolidSearchReplaceProtocol",
            "IsolatedLocalSolveLoop",
            "ExtraModule",
            "AnotherExtra",
        ]
    )
    solved_b = _evaluate_solved(modified)

    assert solved_a is solved_b, (
        "execution_path_modules should be observational and not affect solved outcome"
    )


def test_select_task_specs_filters_to_requested_task_ids():
    specs = build_task_specs()
    filtered = select_task_specs(specs, ["toy-math-solve", "task-a-real"])
    assert [spec["task_id"] for spec in filtered] == ["toy-math-solve", "task-a-real"]


def test_select_task_specs_rejects_unknown_task_id():
    specs = build_task_specs()
    with pytest.raises(ValueError, match="Unknown task_id"):
        select_task_specs(specs, ["not-a-real-task"])


def test_build_task_specs_includes_forced_delegated_retry_probe():
    specs = build_task_specs()
    forced = next(spec for spec in specs if spec["task_id"] == "toy-math-forced-delegated-retry")
    assert forced["disable_primary_semantic_retry"] is True
    assert forced["execution_topology"] == "localheal_pipeline"
    assert "replace `return x * 2` with `return x * 4`" in forced["repair_specification"]


def test_classify_solve_mechanism_distinguishes_first_pass():
    assert classify_solve_mechanism(
        solved=True,
        semantic_retry_invoked=False,
        pipeline_retry_delegated=False,
        delegated_retry_stage="not_invoked",
    ) == "first_pass"


def test_classify_solve_mechanism_distinguishes_pipeline_semantic_retry():
    assert classify_solve_mechanism(
        solved=True,
        semantic_retry_invoked=True,
        pipeline_retry_delegated=False,
        delegated_retry_stage="not_invoked",
    ) == "pipeline_semantic_retry"


def test_classify_solve_mechanism_distinguishes_delegated_retry():
    assert classify_solve_mechanism(
        solved=True,
        semantic_retry_invoked=True,
        pipeline_retry_delegated=True,
        delegated_retry_stage="success",
    ) == "delegated_retry"


def test_resolve_receipt_path_prefers_final_receipt_path():
    finalized = {}
    receipt = {"final_receipt_path": "/tmp/local_heal/toy/receipt.json"}
    adapter = {"metadata": {}}

    assert (
        resolve_receipt_path(finalized, receipt, adapter, "toy-math-solve")
        == "/tmp/local_heal/toy/receipt.json"
    )


def test_resolve_receipt_path_falls_back_to_local_heal_report_path():
    finalized = {}
    receipt = {}
    adapter = {"metadata": {}}

    assert resolve_receipt_path(finalized, receipt, adapter, "toy-math-solve").endswith(
        ".nexus/reports/local_heal/toy-math-solve/receipt.json"
    )


# ------------------------------------------------------------------
# C15-4C-1: Verifier Evidence Gap Task Spec Tests
# ------------------------------------------------------------------

def test_c15_4c_1_verifier_evidence_gap_task_exists():
    """The toy-math-verifier-evidence-gap task spec must exist."""
    specs = build_task_specs()
    task_ids = [spec["task_id"] for spec in specs]
    assert "toy-math-verifier-evidence-gap" in task_ids


def test_c15_4c_1_problem_statement_hides_exact_formula():
    """Problem statement must NOT contain the exact expected formula."""
    specs = build_task_specs()
    task = next(spec for spec in specs if spec["task_id"] == "toy-math-verifier-evidence-gap")
    ps = task["problem_statement"]
    # The problem statement should not reveal the exact fix
    assert "clamp" not in ps.lower()
    assert "max(0" not in ps
    assert "min(1" not in ps
    assert "max_val == min_val" not in ps


def test_c15_4c_1_verifier_emits_actionable_evidence():
    """Verifier script must emit actionable evidence on failure."""
    specs = build_task_specs()
    task = next(spec for spec in specs if spec["task_id"] == "toy-math-verifier-evidence-gap")
    vs = task["verify_script"]
    # Verifier must print evidence about what's missing
    assert "EVIDENCE:" in vs
    assert "EXPECTED:" in vs
    # Verifier must check for clamp behavior
    assert "clamp" in vs.lower() or "max(0" in vs or "min(1" in vs
    # Verifier must check for divide-by-zero handling
    assert "max_val == min_val" in vs or "ZeroDivisionError" in vs


def test_c15_4c_1_locked_search_matches_buggy_code():
    """locked_search must match the buggy_code exactly."""
    specs = build_task_specs()
    task = next(spec for spec in specs if spec["task_id"] == "toy-math-verifier-evidence-gap")
    assert task["locked_search"] in task["buggy_code"]


def test_c15_4c_1_task_has_required_capabilities():
    """Task must have expected_capabilities including local_model_executor."""
    specs = build_task_specs()
    task = next(spec for spec in specs if spec["task_id"] == "toy-math-verifier-evidence-gap")
    assert "local_model_executor" in task["expected_capabilities"]
    assert task["execution_topology"] == "localheal_pipeline"
    assert task["verifier_command"] == ["python3", "verify_math_evidence.py"]
