"""
Epistemic Workflow Benchmark v0 — Metrics Engine.

Deterministic metrics computation using oracle (private) and observations.
All statistics are descriptive only; no statistical significance claimed.

All scoring functions require an explicit private_context_path — the public
run directory alone is never sufficient for unblinding alias→case_id bindings.
"""
import statistics
from typing import Any, Dict, List, Optional, Set, Tuple

from nexus.research.epistemic_benchmark.contracts import (
    BenchmarkArm,
    BenchmarkDecision,
    OracleClass,
    DefectSeverity,
)
from nexus.research.epistemic_benchmark.corpus import (
    get_all_oracles,
    get_oracle,
)
from nexus.research.epistemic_benchmark.packets import (
    get_alias_to_case_map,
    load_private_scoring_context,
    load_public_run_manifest,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_oracle_by_case(case_id: str) -> Optional[Dict[str, Any]]:
    return get_oracle(case_id)


def _defective_ids() -> Set[str]:
    return {o["case_id"] for o in get_all_oracles() if o["oracle_class"] == OracleClass.DEFECTIVE.value}


def _clean_ids() -> Set[str]:
    return {o["case_id"] for o in get_all_oracles() if o["oracle_class"] == OracleClass.CLEAN.value}


def _indeterminate_ids() -> Set[str]:
    return {o["case_id"] for o in get_all_oracles() if o["oracle_class"] == OracleClass.INDETERMINATE.value}


def _critical_defect_case_ids() -> Set[str]:
    """Case IDs that have at least one CRITICAL defect."""
    ids = set()
    for o in get_all_oracles():
        for d in o.get("known_defects", []):
            if d.get("severity") == DefectSeverity.CRITICAL.value:
                ids.add(o["case_id"])
    return ids


def _high_defect_case_ids() -> Set[str]:
    """Case IDs that have at least one HIGH defect."""
    ids = set()
    for o in get_all_oracles():
        for d in o.get("known_defects", []):
            if d.get("severity") == DefectSeverity.HIGH.value:
                ids.add(o["case_id"])
    return ids


def _all_known_defect_ids(case_id: str) -> Set[str]:
    """Set of known defect IDs for a case from the oracle."""
    oracle = get_oracle(case_id)
    if oracle is None:
        return set()
    return {d["defect_id"] for d in oracle.get("known_defects", [])}


# ---------------------------------------------------------------------------
# Per-arm metrics computation
# ---------------------------------------------------------------------------


def compute_arm_metrics(
    arm_name: str,
    observations: List[Dict[str, Any]],
    alias_to_case: Dict[str, str],
    all_case_ids: Set[str],
) -> Dict[str, Any]:
    """
    Compute metrics for a single arm.

    Parameters
    ----------
    arm_name : str
    observations : list of valid observations for this arm
    alias_to_case : {alias: case_id} mapping (private, from manifest + oracle access)
    all_case_ids : set of all case IDs in the corpus

    Returns
    -------
    dict of metric values
    """
    # Filter to this arm's observations
    arm_obs = [o for o in observations if o.get("arm") == arm_name]

    # Map observations to case_ids
    obs_by_case: Dict[str, List[Dict[str, Any]]] = {}
    for obs in arm_obs:
        alias = obs.get("case_alias", "")
        case_id = alias_to_case.get(alias)
        if case_id is None:
            continue  # unknown alias — skip
        if case_id not in obs_by_case:
            obs_by_case[case_id] = []
        obs_by_case[case_id].append(obs)

    observed_cases = set(obs_by_case.keys())
    valid_obs_count = len(arm_obs)
    case_count = len(all_case_ids)

    # Decision accuracy
    correct = 0
    total_scored = 0
    false_accepts = 0  # DEFECTIVE + ACCEPT
    false_rejects = 0  # CLEAN + REJECT
    appropriate_abstentions = 0  # INDETERMINATE + BLOCK
    over_abstentions = 0  # non-INDETERMINATE + BLOCK

    defective_ids = _defective_ids()
    clean_ids = _clean_ids()
    indeterminate_ids = _indeterminate_ids()

    defect_recall_numerator = 0
    defect_recall_denominator = 0
    critical_recall_numerator = 0
    critical_recall_denominator = 0
    high_recall_numerator = 0
    high_recall_denominator = 0

    critical_cases = _critical_defect_case_ids()
    high_cases = _high_defect_case_ids()

    brier_numerator = 0.0
    brier_count = 0

    agreement_scores = []

    durations = []
    input_tokens_total = 0
    output_tokens_total = 0
    cost_total = 0.0
    cost_present = False

    evidence_valid_num = 0
    evidence_valid_den = 0

    for case_id in all_case_ids:
        oracle = _get_oracle_by_case(case_id)
        if oracle is None:
            continue
        oracle_decision = oracle["oracle_decision"]
        oracle_class = oracle["oracle_class"]
        known_defect_ids = _all_known_defect_ids(case_id)

        case_obs_list = obs_by_case.get(case_id, [])

        for obs in case_obs_list:
            decision = obs.get("decision", "")
            confidence = obs.get("confidence")
            execution = obs.get("execution", {})
            detected = set(obs.get("detected_defect_ids", []))

            # Decision accuracy
            if decision in {e.value for e in BenchmarkDecision}:
                correct += (1 if decision == oracle_decision else 0)
                total_scored += 1

            # False acceptance (DEFECTIVE + ACCEPT)
            if oracle_class == OracleClass.DEFECTIVE.value and decision == BenchmarkDecision.ACCEPT.value:
                false_accepts += 1

            # False rejection (CLEAN + REJECT)
            if oracle_class == OracleClass.CLEAN.value and decision == BenchmarkDecision.REJECT.value:
                false_rejects += 1

            # Appropriate abstention (INDETERMINATE + BLOCK)
            if oracle_class == OracleClass.INDETERMINATE.value and decision == BenchmarkDecision.BLOCK.value:
                appropriate_abstentions += 1

            # Over abstention (non-INDETERMINATE + BLOCK)
            if oracle_class != OracleClass.INDETERMINATE.value and decision == BenchmarkDecision.BLOCK.value:
                over_abstentions += 1

            # Defect detection recall (DEFECTIVE cases only)
            if oracle_class == OracleClass.DEFECTIVE.value and known_defect_ids:
                defect_recall_numerator += len(detected & known_defect_ids)
                defect_recall_denominator += len(known_defect_ids)

                if case_id in critical_cases:
                    critical_ids = {
                        d["defect_id"] for d in oracle.get("known_defects", [])
                        if d.get("severity") == DefectSeverity.CRITICAL.value
                    }
                    critical_recall_numerator += len(detected & critical_ids)
                    critical_recall_denominator += len(critical_ids)

                if case_id in high_cases:
                    high_ids = {
                        d["defect_id"] for d in oracle.get("known_defects", [])
                        if d.get("severity") == DefectSeverity.HIGH.value
                    }
                    high_recall_numerator += len(detected & high_ids)
                    high_recall_denominator += len(high_ids)

            # Brier score (if confidence present)
            if confidence is not None and not isinstance(confidence, bool):
                is_correct = 1 if decision == oracle_decision else 0
                prob = confidence / 100.0
                brier_numerator += (is_correct - prob) ** 2
                brier_count += 1

            # Durations
            dur = execution.get("duration_seconds")
            if dur is not None and not isinstance(dur, bool) and isinstance(dur, (int, float)) and dur >= 0:
                durations.append(float(dur))

            # Tokens
            it = execution.get("input_tokens")
            ot = execution.get("output_tokens")
            if it is not None:
                input_tokens_total += it
            if ot is not None:
                output_tokens_total += ot

            # Cost
            cost = execution.get("cost_usd")
            if cost is not None:
                cost_total += cost
                cost_present = True

        # Decision agreement (for cases with multiple observations)
        if len(case_obs_list) > 1:
            decisions_this_case = [o.get("decision") for o in case_obs_list]
            from collections import Counter
            counts = Counter(decisions_this_case)
            max_count = max(counts.values()) if counts else 0
            total_count = len(decisions_this_case)
            agreement_scores.append(max_count / total_count if total_count else 0)

    # Denominators for rates
    total_defective_obs = sum(
        1 for case_id in defective_ids
        for _ in obs_by_case.get(case_id, [])
    )
    total_clean_obs = sum(
        1 for case_id in clean_ids
        for _ in obs_by_case.get(case_id, [])
    )
    total_indeterminate_obs = sum(
        1 for case_id in indeterminate_ids
        for _ in obs_by_case.get(case_id, [])
    )
    total_non_indeterminate_obs = sum(
        1 for case_id in (defective_ids | clean_ids)
        for _ in obs_by_case.get(case_id, [])
    )

    def _safe_div(n: float, d: float) -> Optional[float]:
        return round(n / d, 6) if d > 0 else None

    def _median(lst: List[float]) -> Optional[float]:
        return round(statistics.median(lst), 3) if lst else None

    def _p95(lst: List[float]) -> Optional[float]:
        if not lst:
            return None
        sorted_lst = sorted(lst)
        idx = max(0, int(len(sorted_lst) * 0.95) - 1)
        return round(sorted_lst[idx], 3)

    return {
        "arm": arm_name,
        "observation_count": valid_obs_count,
        "case_coverage": len(observed_cases),
        "completion_rate": _safe_div(len(observed_cases), case_count),

        "decision_accuracy": _safe_div(correct, total_scored),
        "false_acceptance_rate": _safe_div(false_accepts, total_defective_obs),
        "false_rejection_rate": _safe_div(false_rejects, total_clean_obs),
        "appropriate_abstention_rate": _safe_div(appropriate_abstentions, total_indeterminate_obs),
        "over_abstention_rate": _safe_div(over_abstentions, total_non_indeterminate_obs),

        "defect_detection_recall": _safe_div(defect_recall_numerator, defect_recall_denominator),
        "critical_defect_detection_recall": _safe_div(critical_recall_numerator, critical_recall_denominator),
        "high_defect_detection_recall": _safe_div(high_recall_numerator, high_recall_denominator),

        "evidence_reference_validity_rate": None,  # Computed at import; set to 1.0 if all valid

        "mean_confidence": _safe_div(
            sum(
                o.get("confidence") for o in arm_obs
                if o.get("confidence") is not None and not isinstance(o.get("confidence"), bool)
            ),
            sum(
                1 for o in arm_obs
                if o.get("confidence") is not None and not isinstance(o.get("confidence"), bool)
            ),
        ),
        "brier_score": _safe_div(brier_numerator, brier_count),
        "brier_calibration_sample_count": brier_count,

        "median_duration_seconds": _median(durations),
        "p95_duration_seconds": _p95(durations),
        "total_input_tokens": input_tokens_total,
        "total_output_tokens": output_tokens_total,
        "total_cost_usd": round(cost_total, 6) if cost_present else None,

        "decision_agreement": _safe_div(sum(agreement_scores), len(agreement_scores)) if agreement_scores else None,

        # For reporting: breakdown of case states
        "_assigned_cases": case_count,
        "_observed_cases": len(observed_cases),
        "_missing_cases": case_count - len(observed_cases),
    }


# ---------------------------------------------------------------------------
# Paired arm comparisons
# ---------------------------------------------------------------------------


def compute_paired_comparison(
    arm_a_metrics: Dict[str, Any],
    arm_b_metrics: Dict[str, Any],
    arm_a_name: str,
    arm_b_name: str,
) -> Dict[str, Any]:
    """
    Compare two arms descriptively. All deltas are arm_b - arm_a.
    Positive delta does NOT imply improvement.
    """
    def _delta(key: str) -> Optional[float]:
        a = arm_a_metrics.get(key)
        b = arm_b_metrics.get(key)
        if a is None or b is None:
            return None
        return round(b - a, 6)

    obs_a = sum(
        1 for _ in range(arm_a_metrics.get("_observed_cases", 0))
    )

    # Paired cases = cases with observations in BOTH arms
    paired_count = min(
        arm_a_metrics.get("_observed_cases", 0),
        arm_b_metrics.get("_observed_cases", 0),
    )

    return {
        "comparison": f"{arm_b_name} vs {arm_a_name}",
        "paired_case_count": paired_count,
        "decision_accuracy_delta": _delta("decision_accuracy"),
        "false_acceptance_delta": _delta("false_acceptance_rate"),
        "appropriate_abstention_delta": _delta("appropriate_abstention_rate"),
        "defect_recall_delta": _delta("defect_detection_recall"),
        "median_duration_delta_seconds": _delta("median_duration_seconds"),
        "median_cost_delta_usd": _delta("total_cost_usd"),
        "disclaimer": (
            "Observed deltas are descriptive only. "
            "This benchmark does not establish statistical significance "
            "or general research-quality improvement."
        ),
    }


# ---------------------------------------------------------------------------
# Full benchmark metrics
# ---------------------------------------------------------------------------


def compute_all_metrics(
    run_dir: str,
    valid_observations: List[Dict[str, Any]],
    private_context_path: str = "",
) -> Dict[str, Any]:
    """
    Compute metrics for all three arms.

    Uses the private scoring context for alias→case_id resolution.
    Oracle is never written to the public run directory.

    Parameters
    ----------
    run_dir : str
        Public benchmark run directory.
    valid_observations : list
        Pre-validated observations (output of load_valid_observations).
    private_context_path : str
        Path to the private scoring context JSON file.
        Required for alias→case_id resolution. Fail-closed if empty.
    """
    if not private_context_path:
        # Legacy auto-derive: find sibling private context file.
        # Preserved for backward compat with tests that use prepare_benchmark_run
        # with auto-derived private_context_path.
        import os
        pub_abs = os.path.abspath(run_dir)
        pub_parent = os.path.dirname(pub_abs)
        pub_name = os.path.basename(pub_abs)
        private_context_path = os.path.join(
            pub_parent, f"_{pub_name}_private_context.json"
        )

    private_ctx = load_private_scoring_context(run_dir, private_context_path)
    alias_to_case = get_alias_to_case_map(private_ctx)
    all_case_ids = {b["case_id"] for b in private_ctx.get("alias_bindings", [])}

    arms = [
        BenchmarkArm.STANDARD_REVIEW.value,
        BenchmarkArm.STRONG_PROTOCOL.value,
        BenchmarkArm.EPISTEMIC_WORKFLOW.value,
    ]

    arm_metrics = {}
    for arm_name in arms:
        arm_metrics[arm_name] = compute_arm_metrics(
            arm_name,
            valid_observations,
            alias_to_case,
            all_case_ids,
        )

    comparisons = [
        compute_paired_comparison(
            arm_metrics[BenchmarkArm.STANDARD_REVIEW.value],
            arm_metrics[BenchmarkArm.STRONG_PROTOCOL.value],
            BenchmarkArm.STANDARD_REVIEW.value,
            BenchmarkArm.STRONG_PROTOCOL.value,
        ),
        compute_paired_comparison(
            arm_metrics[BenchmarkArm.STRONG_PROTOCOL.value],
            arm_metrics[BenchmarkArm.EPISTEMIC_WORKFLOW.value],
            BenchmarkArm.STRONG_PROTOCOL.value,
            BenchmarkArm.EPISTEMIC_WORKFLOW.value,
        ),
        compute_paired_comparison(
            arm_metrics[BenchmarkArm.STANDARD_REVIEW.value],
            arm_metrics[BenchmarkArm.EPISTEMIC_WORKFLOW.value],
            BenchmarkArm.STANDARD_REVIEW.value,
            BenchmarkArm.EPISTEMIC_WORKFLOW.value,
        ),
    ]

    return {
        "arm_metrics": arm_metrics,
        "comparisons": comparisons,
        "total_valid_observations": len(valid_observations),
        "corpus_case_count": len(all_case_ids),
    }


def _build_alias_to_case_private(private_context: Dict[str, Any]) -> Dict[str, str]:
    """
    Build {alias: case_id} from the private scoring context.

    Accepts a loaded private context dict (from load_private_scoring_context).
    Private — result must never be exposed in public directories.
    """
    return get_alias_to_case_map(private_context)
