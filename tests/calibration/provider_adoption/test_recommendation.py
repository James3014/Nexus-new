"""Unit tests for G6 Admission Recommendation module in Provider Adoption Framework."""

from nexus.calibration.provider_adoption.recommendation import (
    FIXED_VERDICT,
    RECOMMENDATION_SCHEMA,
    build_admission_recommendation,
)


def test_recommendation_fixed_non_authoritative_verdict():
    rec = build_admission_recommendation(
        experiment_id="EXP-1",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=0.99,
        format_compliance=0.99,
        error_rate=0.01,
        offline_verified=True,
        latency_p95_ms=200,
    )
    assert rec.schema == RECOMMENDATION_SCHEMA
    assert rec.verdict == FIXED_VERDICT
    assert "grants no permissions" in rec.authority_disclaimer
    assert rec.recommended_autonomy == "L1"
    assert rec.recommended_state == "LOCAL_CONDITIONAL"
    assert not rec.clamped_by_ceiling


def test_recommendation_clamped_by_ceiling():
    """Verify that preliminary autonomy is strictly clamped by contract claim ceiling."""
    rec = build_admission_recommendation(
        experiment_id="EXP-1",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L0.5",  # Ceiling lower than L1 qualification
        accuracy=0.99,
        format_compliance=0.99,
        error_rate=0.01,
        offline_verified=True,
        latency_p95_ms=200,
    )
    assert rec.recommended_autonomy == "L0.5"
    assert rec.clamped_by_ceiling is True
    assert any("clamped to contract ceiling L0.5" in r for r in rec.reasons)


def test_recommendation_environment_blocked():
    rec = build_admission_recommendation(
        experiment_id="EXP-1",
        candidate_provider_id="apple-fm",
        candidate_model_id="default",
        claim_ceiling="L0.5",
        accuracy=0.0,
        format_compliance=0.0,
        error_rate=1.0,
        offline_verified=False,
        latency_p95_ms=0,
        environment_blocked=True,
        blocker_reason="APPLE_FM_LICENSE_NOT_AGREED",
    )
    assert rec.recommended_state == "REGISTERED_BLOCKED"
    assert rec.recommended_autonomy == "L0"
    assert rec.recommended_roles == ()
    assert "APPLE_FM_LICENSE_NOT_AGREED" in rec.reasons[0]


def test_recommendation_contract_threshold_governs_verdict():
    """Verify that changing pass_thresholds directly changes recommendation verdict."""
    from nexus.calibration.provider_adoption.contracts import PassThresholds

    lenient_thresholds = PassThresholds(
        accuracy_min=0.80,
        format_compliance_min=0.90,
        semantic_correctness_min=0.80,
    )
    strict_accuracy_thresholds = PassThresholds(
        accuracy_min=0.90,  # candidate has 0.85 -> fails!
        format_compliance_min=0.90,
        semantic_correctness_min=0.80,
    )
    strict_semantic_thresholds = PassThresholds(
        accuracy_min=0.80,
        format_compliance_min=0.90,
        semantic_correctness_min=0.95,  # candidate has 0.85 -> fails!
    )
    strict_format_thresholds = PassThresholds(
        accuracy_min=0.80,
        format_compliance_min=0.99,  # candidate has 0.95 -> fails!
        semantic_correctness_min=0.80,
    )

    # 1. Under lenient thresholds: candidate qualifies for L0.5
    rec_pass = build_admission_recommendation(
        experiment_id="EXP-1",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=0.85,
        format_compliance=0.95,
        error_rate=0.03,
        offline_verified=False,
        latency_p95_ms=200,
        semantic_correctness=0.85,
        pass_thresholds=lenient_thresholds,
    )
    assert rec_pass.recommended_autonomy == "L0.5"
    assert rec_pass.recommended_state == "EXPERIMENT_ONLY"

    # 2. Under strict accuracy: candidate fails and is BLOCKED at L0
    rec_fail_acc = build_admission_recommendation(
        experiment_id="EXP-1",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=0.85,
        format_compliance=0.95,
        error_rate=0.03,
        offline_verified=False,
        latency_p95_ms=200,
        semantic_correctness=0.85,
        pass_thresholds=strict_accuracy_thresholds,
    )
    assert rec_fail_acc.recommended_autonomy == "L0"
    assert rec_fail_acc.recommended_state == "REGISTERED_BLOCKED"
    assert any(
        "Accuracy (0.85) failed contract minimum threshold (0.90)" in r
        for r in rec_fail_acc.reasons
    )

    # 3. Under strict semantic correctness: candidate fails and is BLOCKED at L0
    rec_fail_sem = build_admission_recommendation(
        experiment_id="EXP-1",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=0.85,
        format_compliance=0.95,
        error_rate=0.03,
        offline_verified=False,
        latency_p95_ms=200,
        semantic_correctness=0.85,
        pass_thresholds=strict_semantic_thresholds,
    )
    assert rec_fail_sem.recommended_autonomy == "L0"
    assert rec_fail_sem.recommended_state == "REGISTERED_BLOCKED"
    assert any(
        "Semantic correctness rate (0.85) failed contract minimum threshold (0.95)" in r
        for r in rec_fail_sem.reasons
    )

    # 4. Under strict format compliance: candidate fails and is BLOCKED at L0
    rec_fail_fmt = build_admission_recommendation(
        experiment_id="EXP-1",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=0.85,
        format_compliance=0.95,
        error_rate=0.03,
        offline_verified=False,
        latency_p95_ms=200,
        semantic_correctness=0.85,
        pass_thresholds=strict_format_thresholds,
    )
    assert rec_fail_fmt.recommended_autonomy == "L0"
    assert rec_fail_fmt.recommended_state == "REGISTERED_BLOCKED"
    assert any(
        "Format compliance rate (0.95) failed contract minimum threshold (0.99)" in r
        for r in rec_fail_fmt.reasons
    )


def test_recommendation_metrics_config_limits_govern_verdict():
    """Verify that operational metrics limits (error rate, p95 latency) govern recommendation."""
    from nexus.calibration.provider_adoption.contracts import MetricsConfig

    metrics_ok = MetricsConfig(
        latency_p50_max_ms=500,
        latency_p95_max_ms=1000,
        max_error_rate=0.05,
        min_throughput_rps=1.0,
    )
    metrics_strict_err = MetricsConfig(
        latency_p50_max_ms=500,
        latency_p95_max_ms=1000,
        max_error_rate=0.01,
        min_throughput_rps=1.0,
    )
    metrics_strict_lat = MetricsConfig(
        latency_p50_max_ms=500,
        latency_p95_max_ms=150,
        max_error_rate=0.05,
        min_throughput_rps=1.0,
    )

    # Within bounds: passes
    rec_ok = build_admission_recommendation(
        experiment_id="EXP-1",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=0.99,
        format_compliance=0.99,
        error_rate=0.01,
        offline_verified=False,
        latency_p95_ms=100,
        metrics_config=metrics_ok,
    )
    assert rec_ok.recommended_autonomy == "L1"

    # Error rate breach
    rec_err = build_admission_recommendation(
        experiment_id="EXP-1",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=0.99,
        format_compliance=0.99,
        error_rate=0.03,  # exceeds 0.01
        offline_verified=False,
        latency_p95_ms=100,
        metrics_config=metrics_strict_err,
    )
    assert rec_err.recommended_autonomy == "L0"
    assert rec_err.recommended_state == "REGISTERED_BLOCKED"
    assert any("Error rate (0.03) exceeded contract maximum (0.01)" in r for r in rec_err.reasons)

    # Latency breach
    rec_lat = build_admission_recommendation(
        experiment_id="EXP-1",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=0.99,
        format_compliance=0.99,
        error_rate=0.01,
        offline_verified=False,
        latency_p95_ms=200,  # exceeds 150
        metrics_config=metrics_strict_lat,
    )
    assert rec_lat.recommended_autonomy == "L0"
    assert rec_lat.recommended_state == "REGISTERED_BLOCKED"
    assert any(
        "P95 latency (200 ms) exceeded contract limit (150 ms)" in r for r in rec_lat.reasons
    )
