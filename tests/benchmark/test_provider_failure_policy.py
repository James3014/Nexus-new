from __future__ import annotations

from scripts.bench.provider_failure_policy import (
    apply_per_task_stop_loss,
    direct_infra_abort_reason,
    direct_provider_infra_row,
    direct_provider_timeout_row,
    direct_timeout_abort_reason,
)


def test_apply_per_task_stop_loss_marks_row_ineligible_and_retryable():
    row = {"mode": "without_nexus", "wall_duration_sec": 42.0}

    assert apply_per_task_stop_loss(row, 10) is True

    assert row["runtime_classification"] == "task_stop_loss_exceeded"
    assert row["timeout_scope"] == "benchmark_per_task_stop_loss"
    assert row["run_eligible"] is False
    assert row["retryable"] is True
    assert row["token_reliable"] is False


def test_apply_per_task_stop_loss_ignores_rows_within_limit():
    row = {"mode": "without_nexus", "wall_duration_sec": 5.0}

    assert apply_per_task_stop_loss(row, 10) is False
    assert "runtime_classification" not in row


def test_direct_provider_timeout_row_only_counts_without_nexus_timeout_markers():
    assert direct_provider_timeout_row({"mode": "without_nexus", "gateway_error_category": "timeout"}) is True
    assert direct_provider_timeout_row({"mode": "without_nexus", "infra_invalid_reason": "task_stop_loss_exceeded"}) is True
    assert direct_provider_timeout_row({"mode": "with_nexus", "gateway_error_category": "timeout"}) is False
    assert direct_provider_timeout_row({"mode": "without_nexus", "gateway_error_category": "auth"}) is False


def test_direct_provider_infra_row_requires_without_nexus_ineligible_reason():
    assert direct_provider_infra_row(
        {"mode": "without_nexus", "run_eligible": False, "infra_invalid_reason": "auth_error"}
    ) is True
    assert direct_provider_infra_row(
        {"mode": "without_nexus", "run_eligible": True, "infra_invalid_reason": "auth_error"}
    ) is False
    assert direct_provider_infra_row(
        {"mode": "with_nexus", "run_eligible": False, "infra_invalid_reason": "auth_error"}
    ) is False


def test_direct_abort_reasons_require_thresholds():
    assert direct_timeout_abort_reason(2, 3) == ""
    assert direct_timeout_abort_reason(3, 3) == "consecutive_direct_provider_timeouts"
    assert direct_timeout_abort_reason(3, 0) == ""
    assert direct_infra_abort_reason(2, 3) == ""
    assert direct_infra_abort_reason(3, 3) == "consecutive_direct_provider_infra_invalid"
    assert direct_infra_abort_reason(3, 0) == ""
