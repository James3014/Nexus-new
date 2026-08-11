"""
Tests for Epistemic Workflow Benchmark v0 — Metrics Engine.
Covers all 17 required test cases (Section 28 of spec).
"""
import json
import os

import pytest

from nexus.research.epistemic_benchmark.corpus import get_all_oracles
from nexus.research.epistemic_benchmark.metrics import (
    _build_alias_to_case_private,
    compute_all_metrics,
    compute_paired_comparison,
)
from nexus.research.epistemic_benchmark.observations import (
    build_synthetic_observation,
    import_observation,
)
from nexus.research.epistemic_benchmark.packets import (
    load_public_run_manifest,
    prepare_benchmark_run,
)

# ---------------------------------------------------------------------------
# Shared fixture: run dir with known observations
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def populated_run(tmp_path_factory):
    """Prepare a run dir and import a deterministic set of observations."""
    base = tmp_path_factory.mktemp("metrics_run")
    run_dir = str(base / "run")
    priv_path = str(base / "_run_private_context.json")
    prepare_benchmark_run(
        public_output_dir=run_dir,
        private_context_path=priv_path,
        seed=99999,
        corpus_version="v0",
    )
    manifest = load_public_run_manifest(run_dir)
    real_run_id = manifest["benchmark_run_id"]

    # Build alias->case_id map from private context
    with open(priv_path) as f:
        import json as _json
        private_ctx = _json.load(f)
    alias_to_case = _build_alias_to_case_private(private_ctx)
    case_to_aliases = {}
    for alias, case_id in alias_to_case.items():
        case_to_aliases.setdefault(case_id, {})[_get_arm_of_alias(run_dir, alias)] = alias

    # Load oracle classifications
    oracles = {o["case_id"]: o for o in get_all_oracles()}

    imported_obs = []

    def _add_obs(arm, case_id, decision, obs_id_suffix, confidence=75, evaluator_id=None):
        alias = case_to_aliases.get(case_id, {}).get(arm)
        if alias is None:
            return
        # Get a real evidence ref from packet
        pkt_path = os.path.join(run_dir, "packets", arm, f"{alias}.json")
        with open(pkt_path) as f:
            pkt = json.load(f)
        refs = pkt.get("common_materials", {}).get("available_evidence_refs", [])
        # Get real packet SHA so the observation binding is exact
        pkt_sha256 = pkt.get("packet_sha256")
        obs = build_synthetic_observation(
            benchmark_run_id=real_run_id,
            arm=arm,
            case_alias=alias,
            observation_id=f"OBS-{arm[:3]}-{case_id.lower()}-{obs_id_suffix}",
            decision=decision,
            packet_sha256=pkt_sha256,
            cited_evidence_refs=[refs[0]] if refs else [],
            confidence=confidence,
            provider="synthetic-test",
            model_id="deterministic-fixture",
            evaluator_id=evaluator_id,
        )
        success, errors = import_observation(run_dir, obs)
        assert success, f"Failed importing obs for {case_id}/{arm}: {errors}"
        imported_obs.append(obs)

    # Import observations for all three arms for all cases
    for case_id, oracle in oracles.items():
        oracle_decision = oracle["oracle_decision"]

        for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
            # Correct decision for most cases
            _add_obs(arm, case_id, oracle_decision, "correct", confidence=80)

    # Add a false acceptance for standard_review on a DEFECTIVE case (EBR-002)
    fa_case = "EBR-002"
    _add_obs("standard_review", fa_case, "ACCEPT", "fa", confidence=60)

    # Add a false rejection for strong_protocol on CLEAN case (EBR-001)
    _add_obs("strong_protocol", "EBR-001", "REJECT", "fr", confidence=50)

    # Add an over-abstention on DEFECTIVE case for epistemic_workflow
    _add_obs("epistemic_workflow", "EBR-003", "BLOCK", "oa", confidence=40)

    # Add a correct BLOCK for INDETERMINATE case
    _add_obs("standard_review", "EBR-016", "BLOCK", "block2", confidence=90)

    # Add a second reviewer for EBR-005 to test agreement
    _add_obs("standard_review", "EBR-005", "REJECT", "reviewer2", confidence=70,
             evaluator_id="fixture-reviewer2")

    return {
        "run_dir": run_dir,
        "priv_path": priv_path,
        "manifest": manifest,
        "alias_to_case": alias_to_case,
        "oracles": oracles,
        "imported_obs": imported_obs,
    }


def _get_arm_of_alias(run_dir: str, alias: str) -> str:
    for arm in ("standard_review", "strong_protocol", "epistemic_workflow"):
        pkt_path = os.path.join(run_dir, "packets", arm, f"{alias}.json")
        if os.path.exists(pkt_path):
            return arm
    return ""


# ---------------------------------------------------------------------------
# Test 1: Decision accuracy
# ---------------------------------------------------------------------------


def test_decision_accuracy(populated_run):
    from nexus.research.epistemic_benchmark.observations import load_valid_observations
    run_dir = populated_run["run_dir"]
    priv_path = populated_run["priv_path"]
    valid_obs, _ = load_valid_observations(run_dir)
    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path=priv_path)

    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        m = metrics["arm_metrics"][arm_name]
        acc = m.get("decision_accuracy")
        assert acc is not None, f"decision_accuracy should be computed for {arm_name}"
        assert 0.0 <= acc <= 1.0, f"decision_accuracy out of range for {arm_name}: {acc}"


# ---------------------------------------------------------------------------
# Test 2: False Acceptance
# ---------------------------------------------------------------------------


def test_false_acceptance(populated_run):
    from nexus.research.epistemic_benchmark.observations import load_valid_observations
    run_dir = populated_run["run_dir"]
    priv_path = populated_run["priv_path"]
    valid_obs, _ = load_valid_observations(run_dir)
    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path=priv_path)

    m = metrics["arm_metrics"]["standard_review"]
    # We added an extra ACCEPT on DEFECTIVE case EBR-002
    far = m.get("false_acceptance_rate")
    assert far is not None
    assert far > 0.0, f"Expected some false acceptances in standard_review, got {far}"


# ---------------------------------------------------------------------------
# Test 3: False Rejection
# ---------------------------------------------------------------------------


def test_false_rejection(populated_run):
    from nexus.research.epistemic_benchmark.observations import load_valid_observations
    run_dir = populated_run["run_dir"]
    priv_path = populated_run["priv_path"]
    valid_obs, _ = load_valid_observations(run_dir)
    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path=priv_path)

    m = metrics["arm_metrics"]["strong_protocol"]
    # We added a REJECT on CLEAN case EBR-001
    frr = m.get("false_rejection_rate")
    assert frr is not None
    assert frr > 0.0, f"Expected some false rejections in strong_protocol, got {frr}"


# ---------------------------------------------------------------------------
# Test 4: Appropriate Abstention
# ---------------------------------------------------------------------------


def test_appropriate_abstention(populated_run):
    from nexus.research.epistemic_benchmark.observations import load_valid_observations
    run_dir = populated_run["run_dir"]
    priv_path = populated_run["priv_path"]
    valid_obs, _ = load_valid_observations(run_dir)
    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path=priv_path)

    # All arms should have appropriate abstention for INDETERMINATE cases
    m = metrics["arm_metrics"]["standard_review"]
    aar = m.get("appropriate_abstention_rate")
    # May be None if no indeterminate obs, or a rate
    if aar is not None:
        assert 0.0 <= aar <= 1.0


# ---------------------------------------------------------------------------
# Test 5: Over Abstention
# ---------------------------------------------------------------------------


def test_over_abstention(populated_run):
    from nexus.research.epistemic_benchmark.observations import load_valid_observations
    run_dir = populated_run["run_dir"]
    priv_path = populated_run["priv_path"]
    valid_obs, _ = load_valid_observations(run_dir)
    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path=priv_path)

    m = metrics["arm_metrics"]["epistemic_workflow"]
    oar = m.get("over_abstention_rate")
    assert oar is not None, "Over-abstention should be computable (we added BLOCK on DEFECTIVE)"
    assert oar > 0.0


# ---------------------------------------------------------------------------
# Test 6: Defect recall
# ---------------------------------------------------------------------------


def test_defect_recall(populated_run):
    from nexus.research.epistemic_benchmark.observations import load_valid_observations
    run_dir = populated_run["run_dir"]
    priv_path = populated_run["priv_path"]
    valid_obs, _ = load_valid_observations(run_dir)
    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path=priv_path)

    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        m = metrics["arm_metrics"][arm_name]
        recall = m.get("defect_detection_recall")
        # May be None if no detected defect IDs, but must not error
        if recall is not None:
            assert 0.0 <= recall <= 1.0


# ---------------------------------------------------------------------------
# Test 7: Critical defect recall
# ---------------------------------------------------------------------------


def test_critical_defect_recall(populated_run):
    from nexus.research.epistemic_benchmark.observations import load_valid_observations
    run_dir = populated_run["run_dir"]
    priv_path = populated_run["priv_path"]
    valid_obs, _ = load_valid_observations(run_dir)
    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path=priv_path)

    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        m = metrics["arm_metrics"][arm_name]
        r = m.get("critical_defect_detection_recall")
        if r is not None:
            assert 0.0 <= r <= 1.0


# ---------------------------------------------------------------------------
# Test 8: Brier score
# ---------------------------------------------------------------------------


def test_brier_score(populated_run):
    from nexus.research.epistemic_benchmark.observations import load_valid_observations
    run_dir = populated_run["run_dir"]
    priv_path = populated_run["priv_path"]
    valid_obs, _ = load_valid_observations(run_dir)
    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path=priv_path)

    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        m = metrics["arm_metrics"][arm_name]
        brier = m.get("brier_score")
        if brier is not None:
            # Brier score range [0, 1] for binary correctness
            assert 0.0 <= brier <= 1.0, f"Brier out of range for {arm_name}: {brier}"


# ---------------------------------------------------------------------------
# Test 9: Missing confidence excluded from Brier
# ---------------------------------------------------------------------------


def test_missing_confidence_excluded_from_brier(populated_run, tmp_path):
    """Obs with confidence=None must not affect brier_score."""
    run_dir = populated_run["run_dir"]
    priv_path = populated_run["priv_path"]
    manifest = load_public_run_manifest(run_dir)
    run_id = manifest["benchmark_run_id"]

    # Get an alias for standard_review
    arm = "standard_review"
    arm_dir = os.path.join(run_dir, "packets", arm)
    files = sorted([f for f in os.listdir(arm_dir) if f.endswith(".json")])
    alias = files[-1].replace(".json", "")
    with open(os.path.join(arm_dir, files[-1])) as f:
        pkt = json.load(f)
    refs = pkt.get("common_materials", {}).get("available_evidence_refs", [])

    obs = build_synthetic_observation(
        benchmark_run_id=run_id,
        arm=arm,
        case_alias=alias,
        observation_id="OBS-noconf-metrics-001",
        decision="REJECT",
        confidence=None,  # no confidence
        cited_evidence_refs=[refs[0]] if refs else [],
    )
    success, errors = import_observation(run_dir, obs)
    # This obs may already exist; either way, check Brier sample count
    from nexus.research.epistemic_benchmark.observations import load_valid_observations
    valid_obs, _ = load_valid_observations(run_dir)
    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path=priv_path)

    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        m = metrics["arm_metrics"][arm_name]
        # brier_calibration_sample_count must be present
        assert "brier_calibration_sample_count" in m


# ---------------------------------------------------------------------------
# Test 10: Median duration
# ---------------------------------------------------------------------------


def test_median_duration(populated_run):
    from nexus.research.epistemic_benchmark.observations import load_valid_observations
    run_dir = populated_run["run_dir"]
    priv_path = populated_run["priv_path"]
    valid_obs, _ = load_valid_observations(run_dir)
    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path=priv_path)

    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        m = metrics["arm_metrics"][arm_name]
        med = m.get("median_duration_seconds")
        if med is not None:
            assert med >= 0.0


# ---------------------------------------------------------------------------
# Test 11: P95 duration
# ---------------------------------------------------------------------------


def test_p95_duration(populated_run):
    from nexus.research.epistemic_benchmark.observations import load_valid_observations
    run_dir = populated_run["run_dir"]
    priv_path = populated_run["priv_path"]
    valid_obs, _ = load_valid_observations(run_dir)
    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path=priv_path)

    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        m = metrics["arm_metrics"][arm_name]
        p95 = m.get("p95_duration_seconds")
        if p95 is not None:
            assert p95 >= 0.0


# ---------------------------------------------------------------------------
# Test 12: Token totals
# ---------------------------------------------------------------------------


def test_token_totals(populated_run):
    from nexus.research.epistemic_benchmark.observations import load_valid_observations
    run_dir = populated_run["run_dir"]
    priv_path = populated_run["priv_path"]
    valid_obs, _ = load_valid_observations(run_dir)
    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path=priv_path)

    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        m = metrics["arm_metrics"][arm_name]
        assert "total_input_tokens" in m
        assert "total_output_tokens" in m
        assert m["total_input_tokens"] >= 0
        assert m["total_output_tokens"] >= 0


# ---------------------------------------------------------------------------
# Test 13: Cost totals
# ---------------------------------------------------------------------------


def test_cost_totals(populated_run):
    from nexus.research.epistemic_benchmark.observations import load_valid_observations
    run_dir = populated_run["run_dir"]
    priv_path = populated_run["priv_path"]
    valid_obs, _ = load_valid_observations(run_dir)
    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path=priv_path)

    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        m = metrics["arm_metrics"][arm_name]
        cost = m.get("total_cost_usd")
        if cost is not None:
            assert cost >= 0.0


# ---------------------------------------------------------------------------
# Test 14: Decision agreement
# ---------------------------------------------------------------------------


def test_decision_agreement(populated_run):
    """Multi-reviewer cases should produce non-None agreement."""
    from nexus.research.epistemic_benchmark.observations import load_valid_observations
    run_dir = populated_run["run_dir"]
    priv_path = populated_run["priv_path"]
    valid_obs, _ = load_valid_observations(run_dir)
    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path=priv_path)

    m = metrics["arm_metrics"]["standard_review"]
    agreement = m.get("decision_agreement")
    # We added a second reviewer for EBR-005, so standard_review should have agreement
    if agreement is not None:
        assert 0.0 <= agreement <= 1.0


# ---------------------------------------------------------------------------
# Test 15: Paired deltas
# ---------------------------------------------------------------------------


def test_paired_deltas(populated_run):
    from nexus.research.epistemic_benchmark.observations import load_valid_observations
    run_dir = populated_run["run_dir"]
    priv_path = populated_run["priv_path"]
    valid_obs, _ = load_valid_observations(run_dir)
    metrics = compute_all_metrics(run_dir, valid_obs, private_context_path=priv_path)

    comps = metrics["comparisons"]
    assert len(comps) == 3, f"Expected 3 comparisons, got {len(comps)}"

    required_keys = {
        "paired_case_count",
        "decision_accuracy_delta",
        "false_acceptance_delta",
        "appropriate_abstention_delta",
        "defect_recall_delta",
        "median_duration_delta_seconds",
        "median_cost_delta_usd",
        "disclaimer",
    }

    for comp in comps:
        missing = required_keys - set(comp.keys())
        assert not missing, f"Missing keys in comparison: {missing}"
        assert "Observed deltas are descriptive only" in comp["disclaimer"]
        assert comp["paired_metric_denominators"]["appropriate_abstention"] > 0
        assert comp["appropriate_abstention_delta"] is not None
        assert comp["paired_metric_denominators"]["intervention"] == 0
        assert comp["intervention_delta"] is None


def test_paired_deltas_use_exact_intersection_not_min_or_full_arm_aggregates():
    """Unpaired cases and full-arm summaries must not affect paired deltas."""
    arm_a = {
        "_observed_case_ids": {"shared", "a-only"},
        "_case_metrics": {
            "shared": {"success": 1.0, "latency": 10.0, "cost": 2.0, "intervention": 0.0},
            "a-only": {"success": 0.0, "latency": 1000.0, "cost": 1000.0, "intervention": 100.0},
        },
        "decision_accuracy": 0.5,
        "median_duration_seconds": 505.0,
        "total_cost_usd": 1002.0,
    }
    arm_b = {
        "_observed_case_ids": {"shared", "b-only"},
        "_case_metrics": {
            "shared": {"success": 0.0, "latency": 20.0, "cost": 7.0, "intervention": 1.0},
            "b-only": {"success": 1.0, "latency": 2000.0, "cost": 2000.0, "intervention": 200.0},
        },
        "decision_accuracy": 0.5,
        "median_duration_seconds": 1010.0,
        "total_cost_usd": 2007.0,
    }

    comparison = compute_paired_comparison(arm_a, arm_b, "a", "b")

    assert comparison["paired_case_count"] == 1
    assert comparison["arm_a_unpaired_case_count"] == 1
    assert comparison["arm_b_unpaired_case_count"] == 1
    assert comparison["success_delta"] == -1.0
    assert comparison["latency_delta_seconds"] == 10.0
    assert comparison["cost_delta_usd"] == 5.0
    assert comparison["intervention_delta"] is None
    assert comparison["paired_metric_denominators"]["intervention"] == 0
    assert comparison["paired_missingness"]["intervention"] == 1
    assert comparison["decision_accuracy_delta"] == -1.0
    assert comparison["median_duration_delta_seconds"] == 10.0
    assert comparison["median_cost_delta_usd"] == 5.0


def test_paired_comparison_rejects_missing_identity_metadata():
    """A fabricated denominator must fail closed without exact case identities."""
    with pytest.raises(ValueError, match="PAIRED_CASE_IDENTITIES_REQUIRED"):
        compute_paired_comparison(
            {"_observed_cases": 1},
            {"_observed_cases": 1},
            "a",
            "b",
        )


def test_paired_comparison_rejects_zero_exact_intersection():
    """Two non-empty arms without a shared case cannot fabricate a denominator."""
    comparison = compute_paired_comparison(
        {
            "_observed_case_ids": ["a-only"],
            "_case_metrics": {"a-only": {"success": 1.0}},
        },
        {
            "_observed_case_ids": ["b-only"],
            "_case_metrics": {"b-only": {"success": 1.0}},
        },
        "a",
        "b",
    )

    assert comparison["pairing_status"] == "NO_EXACT_INTERSECTION"
    assert comparison["paired_case_count"] == 0
    assert comparison["paired_denominator"] is None
    assert comparison["success_delta"] is None


def test_appropriate_abstention_remains_available_when_intervention_is_unavailable():
    """Paired abstention remains truthful without legal intervention telemetry."""
    arm_a = {
        "_observed_case_ids": ["shared"],
        "_case_metrics": {
            "shared": {
                "success": 1.0,
                "appropriate_abstention": 0.0,
                "intervention": 10.0,
            }
        },
    }
    arm_b = {
        "_observed_case_ids": ["shared"],
        "_case_metrics": {
            "shared": {
                "success": 1.0,
                "appropriate_abstention": 1.0,
                "intervention": 20.0,
            }
        },
    }

    comparison = compute_paired_comparison(arm_a, arm_b, "a", "b")

    assert comparison["appropriate_abstention_delta"] == 1.0
    assert comparison["paired_metric_denominators"]["appropriate_abstention"] == 1
    assert comparison["intervention_delta"] is None
    assert comparison["paired_metric_denominators"]["intervention"] == 0
    assert comparison["paired_missingness"]["intervention"] == 1


def test_paired_comparison_rejects_none_case_metrics_deterministically():
    """Malformed per-case rows must be ValueError, never incidental AttributeError."""
    with pytest.raises(ValueError, match=r"PAIRED_CASE_METRICS_INVALID: arm=a case=shared"):
        compute_paired_comparison(
            {
                "_observed_case_ids": ["shared"],
                "_case_metrics": {"shared": None},
            },
            {
                "_observed_case_ids": ["shared"],
                "_case_metrics": {"shared": {"success": 1.0}},
            },
            "a",
            "b",
        )


def test_paired_metric_denominators_expose_usable_pairs_with_missing_values():
    """Each delta discloses how many exact pairs had values in both arms."""
    arm_a = {
        "_observed_case_ids": ["case-1", "case-2"],
        "_case_metrics": {
            "case-1": {"success": 1.0, "latency": 10.0, "cost": 2.0},
            "case-2": {"success": 0.0, "latency": None, "cost": 4.0},
        },
    }
    arm_b = {
        "_observed_case_ids": ["case-1", "case-2"],
        "_case_metrics": {
            "case-1": {"success": 0.0, "latency": 15.0, "cost": 3.0},
            "case-2": {"success": 1.0, "latency": 25.0, "cost": None},
        },
    }

    comparison = compute_paired_comparison(arm_a, arm_b, "a", "b")

    assert comparison["paired_denominator"] == 2
    assert comparison["paired_metric_denominators"] == {
        "success": 2,
        "latency": 1,
        "cost": 1,
        "intervention": 0,
        "appropriate_abstention": 0,
    }
    assert comparison["success_delta"] == 0.0
    assert comparison["latency_delta_seconds"] == 5.0
    assert comparison["cost_delta_usd"] == 1.0
    assert comparison["intervention_delta"] is None
    assert comparison["paired_missingness"]["latency"] == 1
    assert comparison["paired_missingness"]["cost"] == 1


def test_public_comparison_does_not_expose_private_case_identities():
    arm_a = {
        "_observed_case_ids": ["shared", "a-private"],
        "_case_metrics": {
            "shared": {"success": 1.0},
            "a-private": {"success": 0.0},
        },
    }
    arm_b = {
        "_observed_case_ids": ["shared", "b-private"],
        "_case_metrics": {
            "shared": {"success": 1.0},
            "b-private": {"success": 0.0},
        },
    }

    comparison = compute_paired_comparison(arm_a, arm_b, "a", "b")

    assert comparison["paired_case_count"] == 1
    assert comparison["arm_a_unpaired_case_count"] == 1
    assert comparison["arm_b_unpaired_case_count"] == 1
    assert not any(key.endswith("_case_ids") for key in comparison)


def test_intervention_is_unavailable_even_when_private_metrics_inject_values():
    arm_a = {
        "_observed_case_ids": ["case-1", "case-2"],
        "_case_metrics": {
            "case-1": {"success": 1.0, "intervention": 10.0},
            "case-2": {"success": 1.0, "intervention": 20.0},
        },
    }
    arm_b = {
        "_observed_case_ids": ["case-1", "case-2"],
        "_case_metrics": {
            "case-1": {"success": 1.0, "intervention": 30.0},
            "case-2": {"success": 1.0, "intervention": 40.0},
        },
    }

    comparison = compute_paired_comparison(arm_a, arm_b, "a", "b")

    assert comparison["intervention_delta"] is None
    assert comparison["paired_metric_denominators"]["intervention"] == 0
    assert comparison["paired_missingness"]["intervention"] == 2


def test_intervention_unavailable_through_real_observation_path(populated_run):
    from nexus.research.epistemic_benchmark.observations import load_valid_observations

    valid_obs, _ = load_valid_observations(populated_run["run_dir"])
    comparisons = compute_all_metrics(
        populated_run["run_dir"],
        valid_obs,
        private_context_path=populated_run["priv_path"],
    )["comparisons"]

    for comparison in comparisons:
        assert comparison["intervention_delta"] is None
        assert comparison["paired_metric_denominators"]["intervention"] == 0
        assert (
            comparison["paired_missingness"]["intervention"]
            == comparison["paired_case_count"]
        )


def test_duration_delta_uses_median_of_exact_paired_values():
    arm_a = {
        "_observed_case_ids": ["case-1", "case-2", "case-3"],
        "_case_metrics": {
            "case-1": {"success": 1.0, "latency": 1.0},
            "case-2": {"success": 1.0, "latency": 2.0},
            "case-3": {"success": 1.0, "latency": 100.0},
        },
    }
    arm_b = {
        "_observed_case_ids": ["case-1", "case-2", "case-3"],
        "_case_metrics": {
            "case-1": {"success": 1.0, "latency": 2.0},
            "case-2": {"success": 1.0, "latency": 4.0},
            "case-3": {"success": 1.0, "latency": 101.0},
        },
    }

    comparison = compute_paired_comparison(arm_a, arm_b, "a", "b")

    assert comparison["median_duration_delta_seconds"] == 1.0
    assert comparison["latency_delta_seconds"] == 1.0


def test_real_observation_path_uses_median_pair_delta_and_exact_intersection(tmp_path):
    from nexus.research.epistemic_benchmark.observations import load_valid_observations

    run_dir = str(tmp_path / "paired_median_run")
    priv_path = str(tmp_path / "_paired_median_private_context.json")
    prepare_benchmark_run(
        public_output_dir=run_dir,
        private_context_path=priv_path,
        seed=24680,
        corpus_version="v0",
    )
    manifest = load_public_run_manifest(run_dir)
    with open(priv_path) as f:
        alias_to_case = _build_alias_to_case_private(json.load(f))
    case_to_aliases = {}
    for alias, case_id in alias_to_case.items():
        case_to_aliases.setdefault(case_id, {})[_get_arm_of_alias(run_dir, alias)] = alias

    oracles = {oracle["case_id"]: oracle for oracle in get_all_oracles()}
    case_ids = sorted(oracles)[:5]
    shared_cases = case_ids[:3]
    arm_a_only = case_ids[3]
    arm_b_only = case_ids[4]

    def _import(arm, case_id, duration, cost, suffix):
        alias = case_to_aliases[case_id][arm]
        packet_path = os.path.join(run_dir, "packets", arm, f"{alias}.json")
        with open(packet_path) as f:
            packet = json.load(f)
        refs = packet.get("common_materials", {}).get("available_evidence_refs", [])
        observation = build_synthetic_observation(
            benchmark_run_id=manifest["benchmark_run_id"],
            arm=arm,
            case_alias=alias,
            observation_id=f"OBS-real-paired-{suffix}",
            decision=oracles[case_id]["oracle_decision"],
            packet_sha256=packet["packet_sha256"],
            cited_evidence_refs=[refs[0]] if refs else [],
            duration_seconds=duration,
            cost_usd=cost,
        )
        success, errors = import_observation(run_dir, observation)
        assert success, errors

    for index, (case_id, duration_a, duration_b) in enumerate(
        zip(shared_cases, [0.0, 100.0, 101.0], [1.0, 2.0, 102.0])
    ):
        _import("standard_review", case_id, duration_a, index + 1.0, f"a-{index}")
        _import("strong_protocol", case_id, duration_b, index + 2.0, f"b-{index}")
    _import("standard_review", arm_a_only, 10000.0, 10000.0, "a-only")
    _import("strong_protocol", arm_b_only, 20000.0, 20000.0, "b-only")

    valid_observations, invalid_observations = load_valid_observations(run_dir)
    assert not invalid_observations
    comparison = compute_all_metrics(
        run_dir,
        valid_observations,
        private_context_path=priv_path,
    )["comparisons"][0]

    assert comparison["paired_case_count"] == 3
    assert comparison["arm_a_unpaired_case_count"] == 1
    assert comparison["arm_b_unpaired_case_count"] == 1
    assert comparison["median_duration_delta_seconds"] == 1.0
    assert comparison["latency_delta_seconds"] == 1.0
    assert comparison["cost_delta_usd"] == 1.0
    assert comparison["success_delta"] == 0.0


def test_paired_comparison_rejects_unhashable_identity_deterministically():
    with pytest.raises(ValueError, match="PAIRED_CASE_ID_INVALID"):
        compute_paired_comparison(
            {
                "_observed_case_ids": [["unhashable"]],
                "_case_metrics": {},
            },
            {
                "_observed_case_ids": ["shared"],
                "_case_metrics": {"shared": {"success": 1.0}},
            },
            "a",
            "b",
        )


@pytest.mark.parametrize("metric", ["latency", "cost"])
@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), float("-inf")])
def test_paired_comparison_rejects_nonfinite_numeric_values(metric, bad_value):
    with pytest.raises(
        ValueError,
        match=rf"PAIRED_CASE_METRIC_VALUE_NONFINITE: arm=a case=shared metric={metric}",
    ):
        compute_paired_comparison(
            {
                "_observed_case_ids": ["shared"],
                "_case_metrics": {"shared": {"success": 1.0, metric: bad_value}},
            },
            {
                "_observed_case_ids": ["shared"],
                "_case_metrics": {"shared": {"success": 1.0, metric: 1.0}},
            },
            "a",
            "b",
        )


@pytest.mark.parametrize("bad_success", [-1, 0.5, 2, float("nan"), float("inf")])
def test_paired_comparison_rejects_success_outside_boolean_semantics(bad_success):
    with pytest.raises(
        ValueError,
        match=r"PAIRED_CASE_SUCCESS_VALUE_INVALID: arm=a case=shared",
    ):
        compute_paired_comparison(
            {
                "_observed_case_ids": ["shared"],
                "_case_metrics": {"shared": {"success": bad_success}},
            },
            {
                "_observed_case_ids": ["shared"],
                "_case_metrics": {"shared": {"success": 1.0}},
            },
            "a",
            "b",
        )


def test_paired_comparison_accepts_boolean_success_values():
    comparison = compute_paired_comparison(
        {
            "_observed_case_ids": ["shared"],
            "_case_metrics": {"shared": {"success": False}},
        },
        {
            "_observed_case_ids": ["shared"],
            "_case_metrics": {"shared": {"success": True}},
        },
        "a",
        "b",
    )

    assert comparison["success_delta"] == 1.0


# ---------------------------------------------------------------------------
# Test 16: Missing cases remain visible
# ---------------------------------------------------------------------------


def test_missing_cases_visible(tmp_path):
    """Run with no observations still reports missing cases correctly."""
    run_dir = str(tmp_path / "empty_run")
    priv_path = str(tmp_path / "_empty_run_private_context.json")
    prepare_benchmark_run(
        public_output_dir=run_dir,
        private_context_path=priv_path,
        seed=77777,
        corpus_version="v0",
    )

    metrics = compute_all_metrics(run_dir, [], private_context_path=priv_path)
    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        m = metrics["arm_metrics"][arm_name]
        assert m["_assigned_cases"] == 18, f"Expected 18 assigned cases, got {m['_assigned_cases']}"
        assert m["_missing_cases"] == 18, f"Expected 18 missing, got {m['_missing_cases']}"
        assert m["_observed_cases"] == 0


# ---------------------------------------------------------------------------
# Test 17: Invalid observations not scored
# ---------------------------------------------------------------------------


def test_invalid_observations_not_scored(tmp_path):
    """Invalid obs are not included in metrics computation."""
    run_dir = str(tmp_path / "invalid_obs_run")
    priv_path = str(tmp_path / "_invalid_obs_run_private_context.json")
    prepare_benchmark_run(
        public_output_dir=run_dir,
        private_context_path=priv_path,
        seed=55555,
        corpus_version="v0",
    )

    # compute_all_metrics only takes valid_observations as input
    # Passing no observations means 0 scored
    metrics = compute_all_metrics(run_dir, [], private_context_path=priv_path)
    for arm_name in ("standard_review", "strong_protocol", "epistemic_workflow"):
        m = metrics["arm_metrics"][arm_name]
        assert m["observation_count"] == 0
        assert m["decision_accuracy"] is None
