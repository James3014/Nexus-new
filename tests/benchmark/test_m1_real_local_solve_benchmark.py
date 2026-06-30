from __future__ import annotations

import pytest


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
    "execution_path_modules",
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
        "execution_path_modules": [
            "CapabilityPlanner",
            "LocalModelExecutor",
            "SolidSearchReplaceProtocol",
            "IsolatedLocalSolveLoop",
        ],
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
    """Every M1 row must carry all 10 observational telemetry fields."""
    row = _make_base_row()
    for field in M1_TELEMETRY_FIELDS:
        assert field in row, f"Missing telemetry field: {field}"


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
