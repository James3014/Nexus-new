"""Unit tests for G4 Operational Metrics module in Provider Adoption Framework."""

from nexus.calibration.provider_adoption.cohort import (
    EvaluationResult,
    EvidenceLevel,
    QualityVerdict,
)
from nexus.calibration.provider_adoption.metrics import aggregate_operational_metrics


def _make_eval_result(case_id: str, latency_ms: int, passed: bool) -> EvaluationResult:
    return EvaluationResult(
        schema="nexus.provider_experiment.evaluation_result.v1",
        experiment_id="EXP-1",
        run_id="run-1",
        case_id=case_id,
        candidate_identity_digest="digest-1",
        input_digest="input-digest",
        output_text="output",
        output_digest="output-digest",
        schema_valid=True,
        quality_result=QualityVerdict.PASS if passed else QualityVerdict.FAIL,
        failure_class=None if passed else "INVALID_RESPONSE",
        latency_ms=latency_ms,
        retry_count=0,
        started_at="2026-09-27T00:00:00Z",
        completed_at="2026-09-27T00:00:01Z",
        evaluator_identity="test-evaluator",
        evidence_level=EvidenceLevel.SIMULATED,
    )


def test_operational_metrics_aggregation():
    results = [
        _make_eval_result("C1", 100, True),
        _make_eval_result("C2", 200, True),
        _make_eval_result("C3", 300, True),
        _make_eval_result("C4", 400, False),
    ]
    metrics = aggregate_operational_metrics(results, total_duration_sec=2.0)
    assert metrics.total_cases == 4
    assert metrics.successful_cases == 3
    assert metrics.failed_cases == 1
    assert metrics.accuracy == 0.75
    assert metrics.error_rate == 0.25
    assert metrics.p50_latency_ms == 200
    assert metrics.p95_latency_ms == 400
    assert metrics.min_latency_ms == 100
    assert metrics.max_latency_ms == 400
    assert metrics.mean_latency_ms == 250.0
    assert metrics.throughput_rps == 2.0


def test_offline_metrics_honesty_fix_6_1():
    results = [_make_eval_result("C1", 100, True)]

    # Unverified offline
    m_unknown = aggregate_operational_metrics(results, offline_verified=None)
    assert m_unknown.offline_status == "UNKNOWN"

    # Physically verified offline
    m_verified = aggregate_operational_metrics(results, offline_verified=True)
    assert m_verified.offline_status == "VERIFIED_OFFLINE"
