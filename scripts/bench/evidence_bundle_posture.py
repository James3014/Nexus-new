from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def derive_public_claim_posture(
    *,
    delivery_gate_passed: bool,
    cost_claim_passed: bool,
    cost_efficiency_status: str,
    cost_efficiency_failures: list[str],
    cost_efficiency_sample_sufficient: bool,
    efficiency_pair_count: int,
    min_required_pairs_for_efficiency_claim: int,
    token_roi_status: str,
    verified_lift_per_1k_with_tokens: float,
    marginal_token_utility: float,
    retry_cost_share_wall: float,
) -> dict[str, Any]:
    cost_efficiency_wording_allowed = bool(
        cost_efficiency_status == "IMPROVED" and cost_efficiency_sample_sufficient
    )
    if not delivery_gate_passed:
        public_wording_key = "no_public_claim"
        public_wording_allowed = False
    elif not cost_efficiency_sample_sufficient:
        public_wording_key = "promising_but_insufficient_sample"
        public_wording_allowed = True
    elif cost_efficiency_wording_allowed:
        public_wording_key = "cost_efficiency_improved"
        public_wording_allowed = True
    elif cost_efficiency_status == "REGRESSED" and retry_cost_share_wall > 0.0:
        public_wording_key = "verified_delivery_uplift_with_cost_regression_localized_to_hidden_retry"
        public_wording_allowed = True
    else:
        public_wording_key = "verified_delivery_uplift"
        public_wording_allowed = True
    return {
        "delivery": {
            "status": "PASS" if delivery_gate_passed else "FAIL",
            "scope": "same-model verified delivery and trust safety",
        },
        "cost_safety": {
            "status": "PASS" if cost_claim_passed else "FAIL",
            "scope": "cost telemetry completeness and public-safe accounting",
        },
        "cost_efficiency": {
            "status": cost_efficiency_status,
            "reason_codes": sorted(set(cost_efficiency_failures)),
            "scope": "wall/token/model-call efficiency versus bare baseline",
            "sample_sufficient": cost_efficiency_sample_sufficient,
            "pair_count": efficiency_pair_count,
            "min_required_pairs": min_required_pairs_for_efficiency_claim,
            "token_roi_status": token_roi_status,
            "verified_lift_per_1k_with_tokens": verified_lift_per_1k_with_tokens,
            "marginal_token_utility": marginal_token_utility,
        },
        "public_wording_key": public_wording_key,
        "public_wording_allowed": public_wording_allowed,
        "cost_efficiency_wording_allowed": cost_efficiency_wording_allowed,
        "allowed_public_wording": public_wording_key,
    }


def derive_training_eligibility_posture(
    *,
    delivery_gate_passed: bool,
    cost_claim_passed: bool,
    cost_efficiency_sample_sufficient: bool,
    prompt_purity_gate_passed: bool,
    with_trust_mismatch_rate: float,
    without_trust_mismatch_rate: float,
    eligible_with: list[dict[str, Any]],
    infra_quarantine_report: dict[str, Any],
    wall_ledger_invalid: bool = False,
    warning_ledger_invalid: bool = False,
    cost_efficiency_status: str = "",
    synthetic_readiness_reasons: list[str] | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    for reason in synthetic_readiness_reasons or []:
        reasons.append(f"synthetic_readiness_shortcut:{reason}")
    if not delivery_gate_passed:
        reasons.append("delivery_gate_not_passed")
    if with_trust_mismatch_rate > 0.0 or without_trust_mismatch_rate > 0.0:
        reasons.append("trust_mismatch_present")
    if not cost_claim_passed:
        reasons.append("cost_safety_not_passed")
    if not cost_efficiency_sample_sufficient:
        reasons.append("sample_insufficient")
    if not prompt_purity_gate_passed:
        reasons.append("prompt_purity_above_threshold")
    if any(str(row.get("rubric_contract_status") or "") != "PASS" for row in eligible_with):
        reasons.append("rubric_not_pass")
    if wall_ledger_invalid:
        reasons.append("wall_ledger_telemetry_invalid")
    if warning_ledger_invalid:
        reasons.append("warning_ledger_telemetry_invalid")
    if cost_efficiency_sample_sufficient and str(cost_efficiency_status or "").upper() == "REGRESSED":
        reasons.append("cost_efficiency_regressed")
    if not reasons:
        status = "TRAINING_ELIGIBLE"
    elif any(reason.startswith("synthetic_readiness_shortcut:") for reason in reasons):
        status = "OBSERVATION_ONLY_SYNTHETIC_READINESS"
    elif "wall_ledger_telemetry_invalid" in reasons or "warning_ledger_telemetry_invalid" in reasons:
        status = "OBSERVATION_ONLY_TELEMETRY_INVALID"
    elif any(reason in reasons for reason in ("delivery_gate_not_passed", "cost_safety_not_passed")):
        status = "OBSERVATION_ONLY_INFRA_INVALID"
    elif "sample_insufficient" in reasons:
        status = "OBSERVATION_ONLY_SAMPLE_INSUFFICIENT"
    elif "cost_efficiency_regressed" in reasons:
        status = "OBSERVATION_ONLY_COST_REGRESSED"
    else:
        status = "OBSERVATION_ONLY"
    return {
        "schema": "nexus_training_eligibility_posture_v1",
        "status": status,
        "reason_codes": sorted(set(reasons)),
        "sample_sufficient": cost_efficiency_sample_sufficient,
        "infra_valid_pair_count": infra_quarantine_report.get("infra_valid_pair_count", 0),
        "infra_invalid_pair_count": infra_quarantine_report.get("infra_invalid_pair_count", 0),
        "rubric_required": True,
        "cost_safety_required": True,
        "claim_boundary": "Rubric PASS without sample sufficiency or cost efficiency remains observation-only.",
    }


def derive_valid_comparison_readiness_gate(*, eligible_without_count: int, without_row_count: int) -> dict[str, Any]:
    required = 0 if without_row_count <= 0 else max(1, (2 * without_row_count + 2) // 3)
    ready = eligible_without_count >= required and without_row_count > 0
    failures: list[str] = []
    if without_row_count <= 0:
        failures.append("without_rows_missing")
    elif not ready:
        failures.append("bare_eligibility_below_two_thirds")
    return {
        "schema": "nexus_valid_comparison_readiness_gate_v1",
        "status": "PASS" if ready else "RETURN",
        "eligible_without_count": int(eligible_without_count),
        "without_row_count": int(without_row_count),
        "required_min_eligible_without": int(required),
        "failures": failures,
        "fallback_verdict": "INCONCLUSIVE_PROVIDER_VARIANCE" if not ready else "NONE",
        "claim_boundary": "Cost comparison denominator requires at least 2/3 eligible bare rows.",
    }


def derive_direction_magnitude_gate(
    *,
    valid_comparison_ready: bool,
    wall_cost_ratio_with_over_without: float,
    token_cost_ratio_with_over_without: float,
    model_call_ratio_with_over_without: float,
    paired_wall_ratios: list[float],
    paired_token_ratios: list[float],
) -> dict[str, Any]:
    if not valid_comparison_ready:
        return {
            "schema": "nexus_direction_magnitude_gate_v1",
            "status": "INCONCLUSIVE_VARIANCE",
            "failures": ["valid_comparison_not_ready"],
            "claim_boundary": "Direction/magnitude evaluation requires valid comparison readiness.",
        }

    wall_improvement = max(0.0, 1.0 - float(wall_cost_ratio_with_over_without))
    token_improvement = max(0.0, 1.0 - float(token_cost_ratio_with_over_without))
    model_call_improvement = max(0.0, 1.0 - float(model_call_ratio_with_over_without))
    improvement_floor = min(wall_improvement, token_improvement, model_call_improvement)

    all_ratios = [float(x) for x in [*paired_wall_ratios, *paired_token_ratios] if x > 0]
    variance_band = (max(all_ratios) - min(all_ratios)) if all_ratios else 0.0

    status = "IMPROVED"
    failures: list[str] = []
    if variance_band > 0.10:
        status = "INCONCLUSIVE_VARIANCE"
        failures.append("paired_ratio_variance_above_10pct")
    elif improvement_floor < 0.05:
        status = "NEUTRAL"
        failures.append("improvement_below_5pct")

    return {
        "schema": "nexus_direction_magnitude_gate_v1",
        "status": status,
        "failures": failures,
        "wall_improvement_pct": round(wall_improvement, 4),
        "token_improvement_pct": round(token_improvement, 4),
        "model_call_improvement_pct": round(model_call_improvement, 4),
        "paired_ratio_variance_band": round(variance_band, 4),
        "claim_boundary": "Direction requires two valid x1 rounds; <5% is practical NEUTRAL, >10% variance is INCONCLUSIVE.",
    }


def derive_mutation_hardening_gate(
    *,
    rows: list[dict[str, Any]],
    warning_ledger_summary: dict[str, Any],
    wall_ledger_summary_with: dict[str, Any],
    wall_ledger_summary_without: dict[str, Any],
) -> dict[str, Any]:
    failures: list[str] = []

    warning_lines = list(warning_ledger_summary.get("warning_lines") or [])
    warning_clean = bool(warning_ledger_summary.get("warning_clean", True))
    if warning_clean and warning_lines:
        failures.append("forged_warning_clean_true_with_warning_lines")

    for summary_name, summary in (
        ("with_nexus", wall_ledger_summary_with),
        ("without_nexus", wall_ledger_summary_without),
    ):
        for item in list(summary.get("items") or []):
            if not isinstance(item, dict):
                continue
            conserved = bool(item.get("wall_ledger_conserved", False))
            error_ratio = float(item.get("wall_ledger_reconciliation_error_ratio", 0.0) or 0.0)
            if conserved and error_ratio >= 0.05:
                failures.append(f"forged_wall_conserved_true_with_high_reconciliation_error:{summary_name}")

    suspicious_zero_fill_rows = 0
    for row in rows:
        hv = ((row.get("wall_ledger") or {}).get("wall_ledger_component_telemetry_status") or {}).get("hidden_verifier")
        if str(hv or "") == "SUSPICIOUS_ZERO_FILL":
            suspicious_zero_fill_rows += 1

    status = "PASS" if not failures else "RETURN"
    return {
        "schema": "nexus_mutation_hardening_gate_v1",
        "status": status,
        "failures": sorted(set(failures)),
        "suspicious_zero_fill_rows": suspicious_zero_fill_rows,
        "cases": [
            {
                "mutation": "forged_warning_clean_true_with_warning_lines",
                "expected_verdict": "RETURN",
            },
            {
                "mutation": "forged_wall_conserved_true_with_high_reconciliation_error",
                "expected_verdict": "RETURN",
            },
            {
                "mutation": "forged_hidden_verifier_wall_zero_with_passed_true",
                "expected_telemetry": "SUSPICIOUS_ZERO_FILL",
            },
        ],
    }


def derive_recent_compatible_x1_history(
    *,
    x1_history: list[dict[str, Any]],
    model_label: str,
    manifest_hash: str,
) -> list[bool]:
    compatible_history = [
        item
        for item in x1_history
        if isinstance(item, dict)
        and str(item.get("model") or "") == str(model_label or "")
        and str(item.get("tasks_manifest_hash") or "") == str(manifest_hash or "")
    ]
    return [item.get("x1_readiness_pass") is True for item in compatible_history[-2:]]


def load_x1_readiness_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(loaded, list):
        return []
    return [item for item in loaded if isinstance(item, dict)]


def append_x1_readiness_history(
    *,
    path: Path,
    entry: dict[str, Any],
    max_entries: int = 20,
) -> list[dict[str, Any]]:
    history = load_x1_readiness_history(path)
    history.append(entry)
    history = history[-max(1, int(max_entries)):]
    path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    return history


def x1_readiness_history_path(*, bundle_path: Path, config: dict[str, Any]) -> Path:
    configured = str(config.get("x1_readiness_history_path") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    repo_root = str(config.get("repo_root") or "").strip()
    if repo_root:
        return Path(repo_root).expanduser().resolve() / ".nexus" / "reports" / "learn" / "x1_readiness_history.json"
    return bundle_path.parent / "x1_readiness_history.json"


def _x1_readiness_pass(
    *,
    valid_comparison_ready: bool,
    wall_ledger_with_conserved_rate: float,
    wall_ledger_without_conserved_rate: float,
    warning_clean_gate_pass: bool,
    provider_token_measured_rate_with: float,
    provider_token_measured_rate_without: float,
) -> bool:
    return bool(
        valid_comparison_ready
        and wall_ledger_with_conserved_rate >= 1.0
        and wall_ledger_without_conserved_rate >= 1.0
        and warning_clean_gate_pass
        and provider_token_measured_rate_with >= 1.0
        and provider_token_measured_rate_without >= 1.0
    )


def derive_x3_promotion_gate(
    *,
    history_last_two_x1_readiness_pass: list[bool],
    valid_comparison_ready: bool,
    wall_ledger_with_conserved_rate: float,
    wall_ledger_without_conserved_rate: float,
    warning_clean_gate_pass: bool,
    provider_token_measured_rate_with: float,
    provider_token_measured_rate_without: float,
) -> dict[str, Any]:
    x1_readiness_pass = _x1_readiness_pass(
        valid_comparison_ready=valid_comparison_ready,
        wall_ledger_with_conserved_rate=wall_ledger_with_conserved_rate,
        wall_ledger_without_conserved_rate=wall_ledger_without_conserved_rate,
        warning_clean_gate_pass=warning_clean_gate_pass,
        provider_token_measured_rate_with=provider_token_measured_rate_with,
        provider_token_measured_rate_without=provider_token_measured_rate_without,
    )
    recent = [item is True for item in history_last_two_x1_readiness_pass[-2:]]
    two_rounds_ready = len(recent) == 2 and all(recent)
    checks = {
        "valid_comparison_ready": bool(valid_comparison_ready),
        "wall_ledger_with_conserved_rate": round(float(wall_ledger_with_conserved_rate), 4),
        "wall_ledger_without_conserved_rate": round(float(wall_ledger_without_conserved_rate), 4),
        "warning_clean_gate_pass": bool(warning_clean_gate_pass),
        "provider_token_measured_rate_with": round(float(provider_token_measured_rate_with), 4),
        "provider_token_measured_rate_without": round(float(provider_token_measured_rate_without), 4),
        "current_x1_readiness_pass": x1_readiness_pass,
        "history_last_two_x1_readiness_pass": recent,
        "history_two_rounds_ready": two_rounds_ready,
    }
    failures: list[str] = []
    if not two_rounds_ready:
        failures.append("missing_two_valid_x1_readiness_rounds")
    if not x1_readiness_pass:
        failures.append("current_x1_readiness_not_passed")
    return {
        "schema": "nexus_x3_promotion_gate_v2",
        "status": "PASS" if two_rounds_ready and x1_readiness_pass else "RETURN",
        "checks": checks,
        "failures": failures,
        "claim_boundary": "x3 requires two consecutive valid x1 readiness rounds under same manifest/model plus clean warning/wall/token gates.",
    }
