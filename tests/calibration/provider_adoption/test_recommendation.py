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


def test_recommendation_metrics_config_throughput_breach_fails():
    """Verify negative control (D1): throughput below min_throughput_rps demotes recommendation to L0 / REGISTERED_BLOCKED."""
    from nexus.calibration.provider_adoption.contracts import MetricsConfig

    metrics_strict_thr = MetricsConfig(
        latency_p50_max_ms=500,
        latency_p95_max_ms=1000,
        max_error_rate=0.05,
        min_throughput_rps=10.0,
    )
    # Case 1: Low throughput fails
    rec_fail = build_admission_recommendation(
        experiment_id="EXP-1",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=0.99,
        format_compliance=0.99,
        error_rate=0.01,
        offline_verified=False,
        latency_p95_ms=100,
        throughput_rps=2.5,  # Below 10.0
        metrics_config=metrics_strict_thr,
    )
    assert rec_fail.recommended_autonomy == "L0"
    assert rec_fail.recommended_state == "REGISTERED_BLOCKED"
    assert any(
        "Throughput (2.50 rps) failed contract minimum threshold (10.00 rps)" in r
        for r in rec_fail.reasons
    )

    # Case 2: Adequate throughput passes
    rec_pass = build_admission_recommendation(
        experiment_id="EXP-1",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=0.99,
        format_compliance=0.99,
        error_rate=0.01,
        offline_verified=False,
        latency_p95_ms=100,
        throughput_rps=15.0,  # Above 10.0
        metrics_config=metrics_strict_thr,
    )
    assert rec_pass.recommended_autonomy == "L1"
    assert rec_pass.recommended_state == "REGISTERED_CONDITIONAL"


def test_recommendation_blocker_categories_distinguished():
    """Verify D4: blocker categories separate ENVIRONMENT, DATA/COHORT, and EVALUATION_STOP."""
    # 1. Environment blocker
    rec_env = build_admission_recommendation(
        experiment_id="EXP-1",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=0.0,
        format_compliance=0.0,
        error_rate=1.0,
        offline_verified=False,
        latency_p95_ms=0,
        blocker_category="ENVIRONMENT",
        blocker_reason="OS_MISMATCH",
    )
    assert rec_env.blocker_category == "ENVIRONMENT"
    assert "Candidate blocked by environment: OS_MISMATCH" in rec_env.reasons[0]
    assert rec_env.recommended_state == "REGISTERED_BLOCKED"
    assert rec_env.recommended_autonomy == "L0"

    # 2. Data / Cohort blocker (ground truth / leakage)
    rec_data = build_admission_recommendation(
        experiment_id="EXP-1",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=0.0,
        format_compliance=0.0,
        error_rate=1.0,
        offline_verified=False,
        latency_p95_ms=0,
        blocker_category="DATA/COHORT",
        blocker_reason="GROUND_TRUTH_NOT_READY",
    )
    assert rec_data.blocker_category == "DATA/COHORT"
    assert "Candidate blocked by dataset/cohort: GROUND_TRUTH_NOT_READY" in rec_data.reasons[0]
    assert "environment" not in rec_data.reasons[0].lower()
    assert rec_data.recommended_state == "REGISTERED_BLOCKED"
    assert rec_data.recommended_autonomy == "L0"

    # 3. Evaluation Stop condition blocker
    rec_stop = build_admission_recommendation(
        experiment_id="EXP-1",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=0.5,
        format_compliance=0.5,
        error_rate=0.5,
        offline_verified=False,
        latency_p95_ms=100,
        blocker_category="EVALUATION_STOP",
        blocker_reason="Consecutive failures limit reached",
    )
    assert rec_stop.blocker_category == "EVALUATION_STOP"
    assert (
        "Candidate stopped by evaluation condition: Consecutive failures limit reached"
        in rec_stop.reasons[0]
    )
    assert "environment" not in rec_stop.reasons[0].lower()
    assert rec_stop.recommended_state == "REGISTERED_BLOCKED"
    assert rec_stop.recommended_autonomy == "L0"


def test_recommendation_omitting_capability_evidence_preserves_backward_compatibility():
    """Verify D12: omitting capability arguments preserves backward compatibility."""
    rec = build_admission_recommendation(
        experiment_id="EXP-BC-1",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=0.99,
        format_compliance=0.99,
        error_rate=0.01,
        offline_verified=False,
        latency_p95_ms=100,
    )
    assert rec.recommended_autonomy == "L1"
    assert rec.recommended_state == "REGISTERED_CONDITIONAL"
    assert "classification" in rec.recommended_roles
    assert "extraction" in rec.recommended_roles
    assert "read_only_schema_candidate" in rec.recommended_roles


def test_recommendation_unsupported_required_capability_caps_at_l025_experiment_only():
    """Verify D12: unsupported required capability caps autonomy at L0.25 / EXPERIMENT_ONLY
    and strips unsupported roles.
    """
    from nexus.calibration.provider_adoption.capability import (
        CapabilityProbeResult,
        CapabilityStatus,
    )

    allowed = ("CAP-001", "CAP-002", "CAP-004", "CAP-005", "CAP-006")
    probes = {
        "CAP-001": CapabilityProbeResult("CAP-001", CapabilityStatus.SUPPORTED, "ok", 0, 10),
        "CAP-002": CapabilityProbeResult("CAP-002", CapabilityStatus.UNSUPPORTED, "no", 0, 10),
        "CAP-004": CapabilityProbeResult("CAP-004", CapabilityStatus.UNSUPPORTED, "no", 0, 10),
        "CAP-005": CapabilityProbeResult("CAP-005", CapabilityStatus.UNSUPPORTED, "no", 0, 10),
        "CAP-006": CapabilityProbeResult("CAP-006", CapabilityStatus.UNSUPPORTED, "no", 0, 10),
    }

    rec = build_admission_recommendation(
        experiment_id="EXP-CAP-DEMOTE",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=1.0,
        format_compliance=1.0,
        error_rate=0.0,
        offline_verified=True,
        latency_p95_ms=100,
        allowed_capabilities=allowed,
        capability_matrix=probes,
    )

    assert rec.recommended_autonomy == "L0.25"
    assert rec.recommended_state == "EXPERIMENT_ONLY"
    # classification (CAP-004), extraction (CAP-005), schema (CAP-002) must be excluded
    for role in ("classification", "extraction", "simple_extraction", "read_only_schema_candidate"):
        assert role not in rec.recommended_roles
    assert "bounded_experiment" in rec.recommended_roles
    assert any("CAP-002" in r and "CAP-004" in r for r in rec.reasons)


def test_recommendation_role_capability_filtering():
    """Verify D12: individual roles require their corresponding capability to be SUPPORTED:
    - classification -> CAP-004
    - extraction/simple_extraction -> CAP-005
    - read_only_schema_candidate -> CAP-002
    - bounded_experiment may remain
    """
    from nexus.calibration.provider_adoption.capability import (
        CapabilityProbeResult,
        CapabilityStatus,
    )

    # Allowed has only CAP-001 and CAP-002, both SUPPORTED
    allowed = ("CAP-001", "CAP-002")
    probes = {
        "CAP-001": CapabilityProbeResult("CAP-001", CapabilityStatus.SUPPORTED, "ok", 0, 10),
        "CAP-002": CapabilityProbeResult("CAP-002", CapabilityStatus.SUPPORTED, "ok", 0, 10),
        "CAP-004": CapabilityProbeResult(
            "CAP-004", CapabilityStatus.NOT_EVALUATED, "none", None, 0
        ),
        "CAP-005": CapabilityProbeResult(
            "CAP-005", CapabilityStatus.NOT_EVALUATED, "none", None, 0
        ),
    }

    rec = build_admission_recommendation(
        experiment_id="EXP-ROLE-FILTER",
        candidate_provider_id="test-provider",
        candidate_model_id="test-model",
        claim_ceiling="L1",
        accuracy=1.0,
        format_compliance=1.0,
        error_rate=0.0,
        offline_verified=False,
        latency_p95_ms=100,
        allowed_capabilities=allowed,
        capability_matrix=probes,
    )

    assert rec.recommended_autonomy == "L1"
    # CAP-004 and CAP-005 not supported: no classification or extraction
    assert "classification" not in rec.recommended_roles
    assert "extraction" not in rec.recommended_roles
    assert "simple_extraction" not in rec.recommended_roles
    # CAP-002 is supported: read_only_schema_candidate is retained
    assert "read_only_schema_candidate" in rec.recommended_roles
    # bounded_experiment is retained
    assert "bounded_experiment" in rec.recommended_roles
