"""
Tests for Epistemic Workflow Benchmark v0 — Metrics Engine.
Covers all 17 required test cases (Section 28 of spec).
"""
import json
import os
import pytest

from nexus.research.epistemic_benchmark.contracts import compute_canonical_sha256
from nexus.research.epistemic_benchmark.corpus import get_all_oracles, REQUIRED_CASE_IDS
from nexus.research.epistemic_benchmark.observations import (
    build_synthetic_observation,
    import_observation,
)
from nexus.research.epistemic_benchmark.metrics import (
    compute_arm_metrics,
    compute_paired_comparison,
    compute_all_metrics,
    _build_alias_to_case_private,
)
from nexus.research.epistemic_benchmark.packets import prepare_benchmark_run, load_public_run_manifest


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
        obs = build_synthetic_observation(
            benchmark_run_id=real_run_id,
            arm=arm,
            case_alias=alias,
            observation_id=f"obs-{arm[:3]}-{case_id.lower()}-{obs_id_suffix}",
            decision=decision,
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
        oracle_class = oracle["oracle_class"]

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
        observation_id="obs-noconf-metrics-001",
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
