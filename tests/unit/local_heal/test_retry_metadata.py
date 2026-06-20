import pytest
from typing import Any
from nexus.services.local_heal.receipt import build_repair_receipt
from nexus.services.local_heal.latency_ledger import LatencyLedger


class MockContext:
    def __init__(self, attempt=1):
        self.instance_id = "test_instance"
        self.task_id = "test_task"
        self.attempt = attempt
        self.runner_completed = True
        self.initial_ctx_len = 1000
        self.final_ctx_len = 1200
        self.resolved_span_len = 50
        self.wall_time_sec = 15.5
        self.syntax_gate_passed = True
        self.solve_eligible = True
        
        self.repro_script = "reproduce_bug.py"
        self.final_patch = "diff --git a/a.py b/a.py"
        self.evaluation_report = "Tests passed"
        self.model_decisions = []
        
        self._sidecar_enabled = False
        self._sidecar_model = ""
        self._sidecar_contributed = False
        
        self._latency_ledger = LatencyLedger()
        self._latency_ledger.retry_count = max(0, attempt - 1)


def test_attempt_1_failure_attempt_2_success_records_retry_count_1():
    """Verify that attempt=2 (which means 1 failure, 1 success) yields retry_count=1."""
    ctx = MockContext(attempt=2)
    receipt = build_repair_receipt(ctx)
    
    assert receipt["eval_metrics"]["retry_count"] == 1


def test_final_success_after_retry_not_first_pass_success():
    """Verify that attempt > 1 is recognized as a retry and not first-pass success."""
    ctx = MockContext(attempt=2)
    receipt = build_repair_receipt(ctx)
    
    # retry_count > 0 indicates it was NOT first pass success
    assert receipt["eval_metrics"]["retry_count"] > 0
    assert receipt["telemetries"]["attempt"] == 2


def test_retry_evidence_citation_required():
    """Verify that when retry_count > 0, verification_report.txt is cited in evidence."""
    ctx = MockContext(attempt=2)
    receipt = build_repair_receipt(ctx)
    
    assert receipt["eval_metrics"]["retry_count"] == 1
    assert "verification_report.txt" in receipt["evidence_refs"]


def test_retry_count_consistent_across_summary_and_receipt():
    """Verify that latency_ledger.retry_count is consistent with eval_metrics.retry_count."""
    ctx = MockContext(attempt=3) # attempt = 3 -> 2 retries
    receipt = build_repair_receipt(ctx)
    
    assert receipt["eval_metrics"]["retry_count"] == 2
    assert receipt["latency_ledger"]["retry_count"] == 2
