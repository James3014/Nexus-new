from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.bench.taskset_contract import build_prompt_contract_hash, build_provider_transport_contract_hash


def _number(payload: dict[str, Any], path: list[str], default: float = 0.0) -> float:
    node: Any = payload
    for key in path:
        if not isinstance(node, dict):
            return default
        node = node.get(key)
    try:
        return float(node)
    except (TypeError, ValueError):
        return default


def _gate(payload: dict[str, Any], name: str) -> str:
    gate = payload.get(name)
    return str(gate.get("verdict") or "") if isinstance(gate, dict) else ""


def _arm(bundle_path: str, label: str) -> dict[str, Any]:
    payload = json.loads(Path(bundle_path).read_text(encoding="utf-8"))
    task_contract = payload.get("taskset_contract", {}) if isinstance(payload.get("taskset_contract"), dict) else {}
    config = payload.get("config", {}) if isinstance(payload.get("config"), dict) else {}
    contamination = (
        payload.get("session_worker_contamination", {})
        if isinstance(payload.get("session_worker_contamination"), dict)
        else {}
    )
    checks = payload.get("public_claim_gate", {}).get("checks", {}) if isinstance(payload.get("public_claim_gate"), dict) else {}
    roi_shadow = (
        payload.get("commercial_model_roi_shadow_hooks", {})
        if isinstance(payload.get("commercial_model_roi_shadow_hooks"), dict)
        else {}
    )
    wall_concentration = (
        roi_shadow.get("wall_regression_concentration", {})
        if isinstance(roi_shadow.get("wall_regression_concentration"), dict)
        else {}
    )
    task_prompt_hash = build_prompt_contract_hash(config) if config else ""
    provider_transport_hash = build_provider_transport_contract_hash(config) if config else ""
    return {
        "label": label,
        "bundle_path": bundle_path,
        "taskset_hash": str(payload.get("task_manifest", {}).get("sha256") or ""),
        "prompt_contract_hash": task_prompt_hash
        or str(task_contract.get("prompt_contract", {}).get("sha256") or ""),
        "source_prompt_contract_hash": str(task_contract.get("prompt_contract", {}).get("sha256") or ""),
        "provider_transport_contract_hash": provider_transport_hash
        or str(task_contract.get("provider_transport_contract", {}).get("sha256") or ""),
        "verifier_contract_hash": str(task_contract.get("verifier_contract", {}).get("sha256") or ""),
        "runner_hash": str(task_contract.get("runner_contract", {}).get("sha256") or ""),
        "fixed_public_taskset_ready": bool(task_contract.get("fixed_public_taskset_ready", False)),
        "public_verified_delivery_gate": _gate(payload, "public_verified_delivery_claim_gate"),
        "public_cost_gate": _gate(payload, "public_cost_claim_gate"),
        "public_cost_efficiency_gate": _gate(payload, "public_cost_efficiency_claim_gate"),
        "with_verified_rate": _number(payload, ["public_claim_gate", "checks", "with_semantic_verified_rate"]),
        "without_verified_rate": _number(payload, ["public_claim_gate", "checks", "without_semantic_verified_rate"]),
        "eligible_without_nexus": _number(payload, ["public_claim_gate", "checks", "eligible_without_nexus"]),
        "provider_token_measured_rate_without": _number(
            payload,
            ["public_claim_gate", "checks", "provider_token_measured_rate_without"],
        ),
        "wall_ledger_without_conserved_rate": _number(
            payload,
            ["public_claim_gate", "checks", "wall_ledger_without_conserved_rate"],
        ),
        "with_trust_mismatch_rate": _number(payload, ["public_claim_gate", "checks", "with_trust_mismatch_rate"]),
        "without_trust_mismatch_rate": _number(payload, ["public_claim_gate", "checks", "without_trust_mismatch_rate"]),
        "contamination_rate": float(contamination.get("contamination_rate", 0.0) or 0.0),
        "worker_clean": bool(contamination.get("clean", True)),
        "avg_tokens_with": float(checks.get("avg_tokens_with", 0.0) or 0.0),
        "avg_tokens_without": float(checks.get("avg_tokens_without", 0.0) or 0.0),
        "avg_model_calls_with": float(checks.get("avg_model_calls_with", 0.0) or 0.0),
        "avg_model_calls_without": float(checks.get("avg_model_calls_without", 0.0) or 0.0),
        "wall_cost_ratio_with_over_without": float(checks.get("wall_cost_ratio_with_over_without", 0.0) or 0.0),
        "token_cost_ratio_with_over_without": float(checks.get("token_cost_ratio_with_over_without", 0.0) or 0.0),
        "route_cost_regression_wall_ratio_threshold": float(
            checks.get("route_cost_regression_wall_ratio_threshold", 1.8) or 1.8
        ),
        "commercial_model_roi_shadow_reason_counts": dict(roi_shadow.get("reason_counts", {}) or {}),
        "commercial_model_roi_shadow_wall_buckets": list(wall_concentration.get("buckets", []) or []),
        "commercial_model_roi_shadow_status": str(roi_shadow.get("status") or ""),
        "commercial_model_basis_ready": bool(
            task_contract.get("benchmark_basis_contract", {}).get("commercial_model_basis_ready", False)
        )
        if isinstance(task_contract.get("benchmark_basis_contract"), dict)
        else False,
        "external_provider_public_claim_allowed": bool(
            payload.get("external_provider_claim_boundary_contract", {}).get("public_claim_allowed", True)
        )
        if isinstance(payload.get("external_provider_claim_boundary_contract"), dict)
        else True,
        "public_promotion_readiness_status": str(
            payload.get("public_promotion_readiness_contract", {}).get("status") or ""
        )
        if isinstance(payload.get("public_promotion_readiness_contract"), dict)
        else "",
    }


def _cost_policy_hook(arm: dict[str, Any], *, delivery_promotion_ready: bool, cost_promotion_ready: bool) -> dict[str, Any]:
    reason_counts = arm.get("commercial_model_roi_shadow_reason_counts", {})
    wall_ratio = float(arm.get("wall_cost_ratio_with_over_without", 0.0) or 0.0)
    token_ratio = float(arm.get("token_cost_ratio_with_over_without", 0.0) or 0.0)
    wall_threshold = float(arm.get("route_cost_regression_wall_ratio_threshold", 1.8) or 1.8)
    reason_codes: list[str] = []
    if delivery_promotion_ready and not cost_promotion_ready:
        reason_codes.append("delivery_ready_cost_not_ready")
    if wall_ratio > wall_threshold:
        reason_codes.append("wall_ratio_above_threshold")
    if 0.0 < token_ratio < 1.0:
        reason_codes.append("token_savings_present")
    if int(reason_counts.get("verified_lift_or_delivery_with_wall_regression", 0) or 0) > 0:
        reason_codes.append("shadow_wall_regression_signal_present")

    if delivery_promotion_ready and not cost_promotion_ready and "token_savings_present" in reason_codes:
        recommendation = "light_route_low_risk_full_nexus_high_risk"
    elif delivery_promotion_ready and not cost_promotion_ready:
        recommendation = "wall_cost_rca_required"
    elif delivery_promotion_ready and cost_promotion_ready:
        recommendation = "keep_current_route_for_public_candidate"
    else:
        recommendation = "not_delivery_ready"
    return {
        "schema": "nexus_dashboard_cost_policy_hook_v1",
        "status": "OBSERVATION_ONLY",
        "promotion_effect": "none",
        "recommendation": recommendation,
        "reason_codes": sorted(set(reason_codes)),
        "wall_ratio_with_over_without": round(wall_ratio, 4),
        "token_ratio_with_over_without": round(token_ratio, 4),
        "wall_ratio_threshold": wall_threshold,
        "shadow_reason_counts": reason_counts,
    }


def _performance_load_stress_hook(
    arm: dict[str, Any],
    *,
    delivery_promotion_ready: bool,
    cost_promotion_ready: bool,
) -> dict[str, Any]:
    reason_counts = arm.get("commercial_model_roi_shadow_reason_counts", {})
    wall_buckets = [bucket for bucket in arm.get("commercial_model_roi_shadow_wall_buckets", []) if isinstance(bucket, dict)]
    wall_ratio = float(arm.get("wall_cost_ratio_with_over_without", 0.0) or 0.0)
    token_ratio = float(arm.get("token_cost_ratio_with_over_without", 0.0) or 0.0)
    wall_threshold = float(arm.get("route_cost_regression_wall_ratio_threshold", 1.8) or 1.8)
    wall_regression_signals = int(reason_counts.get("verified_lift_or_delivery_with_wall_regression", 0) or 0)
    token_savings_present = bool(0.0 < token_ratio < 1.0)

    performance_status = "PASS"
    if wall_ratio > wall_threshold:
        performance_status = "REGRESSED"
    elif delivery_promotion_ready and not cost_promotion_ready:
        performance_status = "WATCH"

    load_status = "PASS" if delivery_promotion_ready and cost_promotion_ready else "RETURN"
    if not delivery_promotion_ready:
        load_status = "BLOCK"

    stress_status = "PASS"
    if wall_regression_signals > 0 and delivery_promotion_ready:
        stress_status = "NEEDS_ROUTE_COST_RCA"
    elif not delivery_promotion_ready:
        stress_status = "BLOCK"

    next_actions: list[str] = []
    if performance_status in {"WATCH", "REGRESSED"}:
        next_actions.append("measure_normal_mix_wall_token_model_call_cost_per_verified_success")
    if load_status == "RETURN":
        next_actions.append("rerun_public_safe_x1_readiness_before_final_promotion")
    if stress_status == "NEEDS_ROUTE_COST_RCA":
        next_actions.append("bucket_high_risk_routes_and_light_route_low_risk_tasks")
    if token_savings_present and not cost_promotion_ready:
        next_actions.append("preserve_token_saving_signal_without_cost_overclaim")

    stress_candidates = []
    for bucket in wall_buckets[:5]:
        lane = str(bucket.get("route_cost_policy_lane") or "unknown")
        strategy = str(bucket.get("strategy_path") or "unknown")
        reason_codes = [str(item) for item in bucket.get("reason_codes", []) or []]
        if strategy == "hyper_direct_forced" or "hyper_direct_forced_wall_regression" in reason_codes:
            action = "cap_hyper_or_try_supervised_preflight_before_second_model_call"
        elif lane in {"hidden_lite", "hidden_bugfix_supervised"}:
            action = "audit_hidden_repair_fast_path_and_receipt_floor"
        elif lane in {"governance_hardened", "governance_hardened_capped"}:
            action = "keep_governance_gates_but_reduce_redundant_model_rounds"
        elif lane == "context_sync_capped":
            action = "keep_docs_code_sync_evidence_but_measure_context_preflight_cost"
        else:
            action = "route_cost_rca_required"
        stress_candidates.append(
            {
                "route_cost_policy_lane": lane,
                "strategy_path": strategy,
                "task_type": str(bucket.get("task_type") or "unknown"),
                "pair_count": int(bucket.get("pair_count", 0) or 0),
                "verified_lift_count": int(bucket.get("verified_lift_count", 0) or 0),
                "avg_wall_ratio": round(float(bucket.get("avg_wall_ratio", 0.0) or 0.0), 4),
                "sum_wall_delta": round(float(bucket.get("sum_wall_delta", 0.0) or 0.0), 4),
                "reason_codes": sorted(set(reason_codes)),
                "suggested_action": action,
            }
        )

    return {
        "schema": "nexus_performance_load_stress_cost_hook_v1",
        "status": "OBSERVATION_ONLY",
        "promotion_effect": "none",
        "performance_test": {
            "question": "normal_mix_cost_baseline",
            "status": performance_status,
            "wall_ratio_with_over_without": round(wall_ratio, 4),
            "token_ratio_with_over_without": round(token_ratio, 4),
            "wall_ratio_threshold": wall_threshold,
        },
        "load_test": {
            "question": "public_promotion_load_readiness",
            "status": load_status,
            "delivery_promotion_ready": delivery_promotion_ready,
            "cost_promotion_ready": cost_promotion_ready,
        },
        "stress_test": {
            "question": "route_cost_breakpoint_and_failure_mode",
            "status": stress_status,
            "wall_regression_signal_count": wall_regression_signals,
            "top_wall_regression_buckets": stress_candidates,
            "claim_boundary": "stress diagnosis may route-cost RCA only; it must not change delivery, trust, cost, or x3 gates",
        },
        "next_actions": sorted(set(next_actions)),
    }


def build_gap_dashboard(*, baseline: str, treatments: list[str], labels: list[str] | None = None) -> dict[str, Any]:
    labels = labels or []
    baseline_arm = _arm(baseline, labels[0] if labels else "gpt5.5_direct_worker")
    treatment_arms = [
        _arm(path, labels[index + 1] if index + 1 < len(labels) else f"treatment_{index + 1}")
        for index, path in enumerate(treatments)
    ]
    arms = [baseline_arm, *treatment_arms]
    taskset_identical = len({arm["taskset_hash"] for arm in arms}) == 1
    prompt_policy_identical = len({arm["prompt_contract_hash"] for arm in arms}) == 1
    provider_transport_hashes = {arm["provider_transport_contract_hash"] for arm in arms if arm["provider_transport_contract_hash"]}
    provider_transport_identical = len(provider_transport_hashes) == 1
    provider_transport_recorded = all(bool(arm["provider_transport_contract_hash"]) for arm in arms)
    verifier_policy_identical = len({arm["verifier_contract_hash"] for arm in arms}) == 1
    all_taskset_contracts_ready = all(bool(arm["fixed_public_taskset_ready"]) for arm in arms)
    baseline_direct_usable = bool(
        baseline_arm["eligible_without_nexus"] > 0
        and baseline_arm["provider_token_measured_rate_without"] == 1.0
        and baseline_arm["wall_ledger_without_conserved_rate"] == 1.0
        and baseline_arm["without_trust_mismatch_rate"] == 0.0
    )
    comparisons = []
    for arm in treatment_arms:
        delivery_promotion_ready = bool(
            baseline_direct_usable
            and taskset_identical
            and prompt_policy_identical
            and verifier_policy_identical
            and all_taskset_contracts_ready
            and arm["public_verified_delivery_gate"] == "PASS"
            and arm["contamination_rate"] == 0.0
            and arm["with_trust_mismatch_rate"] == 0.0
            and arm["without_trust_mismatch_rate"] == 0.0
        )
        cost_promotion_ready = bool(
            arm["public_cost_gate"] == "PASS"
            and arm["public_cost_efficiency_gate"] in {"PASS", "NEUTRAL", "IMPROVED"}
        )
        source_promotion_ready = bool(
            arm["external_provider_public_claim_allowed"]
            and arm["public_promotion_readiness_status"] != "RETURN"
        )
        promotion_ready = bool(delivery_promotion_ready and cost_promotion_ready and source_promotion_ready)
        final_goal_ready = bool(promotion_ready and arm["commercial_model_basis_ready"])
        comparisons.append(
            {
                "label": arm["label"],
                "baseline_direct_verified_rate": baseline_arm["without_verified_rate"],
                "verified_delivery_gap_vs_baseline": round(
                    arm["with_verified_rate"] - baseline_arm["without_verified_rate"], 4
                ),
                "trust_gap_vs_baseline": round(
                    max(arm["with_trust_mismatch_rate"], arm["without_trust_mismatch_rate"])
                    - max(baseline_arm["with_trust_mismatch_rate"], baseline_arm["without_trust_mismatch_rate"]),
                    4,
                ),
                "contamination_rate": arm["contamination_rate"],
                "token_delta_with_vs_baseline_without": round(
                    arm["avg_tokens_with"] - baseline_arm["avg_tokens_without"], 4
                ),
                "model_call_delta_with_vs_baseline_without": round(
                    arm["avg_model_calls_with"] - baseline_arm["avg_model_calls_without"], 4
                ),
                "delivery_promotion_ready": delivery_promotion_ready,
                "cost_promotion_ready": cost_promotion_ready,
                "source_promotion_ready": source_promotion_ready,
                "promotion_ready": promotion_ready,
                "final_goal_ready": final_goal_ready,
                "cost_policy_hook": _cost_policy_hook(
                    arm,
                    delivery_promotion_ready=delivery_promotion_ready,
                    cost_promotion_ready=cost_promotion_ready,
                ),
                "performance_load_stress_hook": _performance_load_stress_hook(
                    arm,
                    delivery_promotion_ready=delivery_promotion_ready,
                    cost_promotion_ready=cost_promotion_ready,
                ),
            }
        )
    return {
        "schema": "nexus_persistent_worker_gap_dashboard_v1",
        "baseline": baseline_arm,
        "treatments": treatment_arms,
        "comparisons": comparisons,
        "readiness": {
            "taskset_identical": taskset_identical,
            "prompt_policy_identical": prompt_policy_identical,
            "provider_transport_recorded": provider_transport_recorded,
            "provider_transport_identical": provider_transport_identical,
            "provider_transport_identical_required": False,
            "verifier_policy_identical": verifier_policy_identical,
            "all_taskset_contracts_ready": all_taskset_contracts_ready,
            "all_workers_clean": all(bool(arm["worker_clean"]) for arm in arms),
            "baseline_direct_usable": baseline_direct_usable,
        },
        "claim_boundary": [
            "Dashboard compares existing evidence bundles only; it does not create live model evidence.",
            "Promotion requires identical taskset and verifier policy plus PASS gates in source bundles.",
            "Cross-provider dashboards require provider-neutral prompt policy identity, not provider transport identity.",
            "Final promotion requires delivery readiness plus a non-regressed public cost-efficiency gate.",
            "A direct baseline may be usable even when the baseline bundle's with-arm is not public-claim eligible.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a persistent-worker gap dashboard from evidence bundles.")
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--treatment", action="append", required=True)
    parser.add_argument("--label", action="append", default=[])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    dashboard = build_gap_dashboard(baseline=args.baseline, treatments=args.treatment, labels=args.label)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "PASS", "output": str(out), "schema": dashboard["schema"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
