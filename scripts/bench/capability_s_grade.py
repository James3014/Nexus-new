#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid_json_payload: {path}")
    return payload


def _latest_file(glob_pattern: str) -> Path:
    files = sorted(Path(".").glob(glob_pattern), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"no_file_matched: {glob_pattern}")
    return files[-1].resolve()


def _num(payload: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(payload.get(key, default))
    except Exception:
        return float(default)


def _bucket_map(full_ab: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for bucket in list(full_ab.get("buckets", [])):
        if isinstance(bucket, dict) and isinstance(bucket.get("name"), str):
            out[str(bucket["name"])] = bucket
    return out


def _bucket_kpi_with_eval_fields(bucket: dict[str, Any], *, with_side: str = "b") -> dict[str, Any]:
    kpi = dict((bucket.get("kpi", {}) or {}) if isinstance(bucket.get("kpi", {}), dict) else {})
    summary = (((bucket.get("ab_eval", {}) or {}).get(with_side, {}) or {}).get("summary", {}) or {})
    if not isinstance(summary, dict):
        return kpi
    fallback_map = {
        "with_avg_model_calls": "avg_model_calls",
        "with_avg_total_tokens": "avg_total_tokens",
        "with_token_measured_rate": "token_measured_rate",
    }
    for dst, src in fallback_map.items():
        if dst not in kpi and src in summary:
            kpi[dst] = summary[src]
    return kpi


def _build_checks(
    *,
    rules: dict[str, Any],
    weighted_score: float,
    realism_score: float,
    daily_kpi: dict[str, Any],
    hard_kpi: dict[str, Any],
    cross_kpi: dict[str, Any],
    stress_kpi: dict[str, Any],
    stress_overhead_kpi: dict[str, Any],
    flash_file_task_kpi: dict[str, Any],
    ops_trend_verdict: str,
    ops_kpi: dict[str, Any],
    self_heal: dict[str, Any],
    capability: dict[str, Any],
    anti_hall: dict[str, Any],
    rolling_7: dict[str, Any],
    rolling_14: dict[str, Any],
) -> dict[str, bool]:
    learn_attempt = _num(capability, "learn_mode_attempt_rate", 1.0 if "learn_mode_attempt_rate" not in capability else 0.0)
    learn_citation = _num(
        capability, "learn_mode_citation_usage_rate", 1.0 if "learn_mode_citation_usage_rate" not in capability else 0.0
    )
    semantic_verified = _num(
        anti_hall, "semantic_contract_verified_rate", 1.0 if "semantic_contract_verified_rate" not in anti_hall else 0.0
    )

    checks: dict[str, bool] = {
        "full_ab_weighted_score": weighted_score >= float(rules["full_ab_weighted_score_min"]),
        "full_ab_realism_score": realism_score >= float(rules.get("full_ab_realism_score_min", 0.0)),
        "daily_solve_rate": _num(daily_kpi, "with_solve_rate") >= float(rules["daily_solve_rate_min"]),
        "daily_semantic_rate": _num(daily_kpi, "with_semantic_verified_rate") >= float(rules["daily_semantic_rate_min"]),
        "hard_delta_solve_rate": _num(hard_kpi, "delta_solve_rate") >= float(rules["hard_delta_solve_rate_min"]),
        "cross_delta_solve_rate": _num(cross_kpi, "delta_solve_rate") >= float(rules["cross_delta_solve_rate_min"]),
        "daily_trust_mismatch": _num(daily_kpi, "with_trust_mismatch_rate") <= float(rules["trust_mismatch_rate_max"]),
        "hard_trust_mismatch": _num(hard_kpi, "with_trust_mismatch_rate") <= float(rules["trust_mismatch_rate_max"]),
        "cross_trust_mismatch": _num(cross_kpi, "with_trust_mismatch_rate") <= float(rules["trust_mismatch_rate_max"]),
        "ops_rounds_trend_gate": ops_trend_verdict == str(rules["ops_rounds_trend_gate"]),
        "ops_solve_rate": _num(ops_kpi, "with_solve_rate") >= float(rules["ops_solve_rate_min"]),
        "ops_semantic_rate": _num(ops_kpi, "with_semantic_verified_rate") >= float(rules["ops_semantic_rate_min"]),
        "ops_overhead": (
            _num(ops_kpi, "wall_overhead_p95_sec", _num(ops_kpi, "wall_overhead_sec"))
            <= float(rules["ops_overhead_p95_sec_max"])
            and _num(ops_kpi, "wall_overhead_worst_decile_mean_sec", _num(ops_kpi, "wall_overhead_sec"))
            <= float(rules["ops_overhead_worst_decile_mean_sec_max"])
        ),
        "self_heal_first_pass": _num(self_heal, "first_pass_success_rate") >= float(rules["self_heal_first_pass_min"]),
        "self_heal_repair_success": (
            _num(self_heal, "repair_attempt_rate") == 0.0
            or _num(self_heal, "repair_success_rate") >= float(rules["self_heal_repair_success_min"])
        ),
        "learn_attempt_rate": learn_attempt >= float(rules["learn_attempt_rate_min"]),
        "learn_citation_usage_rate": learn_citation >= float(rules["learn_citation_usage_rate_min"]),
        "semantic_contract_verified_rate": semantic_verified >= float(rules["semantic_contract_verified_rate_min"]),
    }
    if "stress_delta_solve_rate_min" in rules:
        checks["stress_delta_solve_rate"] = _num(stress_kpi, "delta_solve_rate") >= float(rules["stress_delta_solve_rate_min"])
        checks["stress_trust_mismatch"] = _num(stress_kpi, "with_trust_mismatch_rate") <= float(rules["trust_mismatch_rate_max"])
    if "stress_wall_overhead_sec_max" in rules:
        checks["stress_wall_overhead"] = _num(stress_overhead_kpi, "wall_overhead_sec") <= float(rules["stress_wall_overhead_sec_max"])
    if flash_file_task_kpi:
        checks["flash_file_task_solve_rate"] = _num(flash_file_task_kpi, "with_solve_rate") >= float(
            rules.get("flash_file_task_solve_rate_min", 1.0)
        )
        checks["flash_file_task_semantic_rate"] = _num(flash_file_task_kpi, "with_semantic_verified_rate") >= float(
            rules.get("flash_file_task_semantic_rate_min", 1.0)
        )
        checks["flash_file_task_trust_mismatch"] = _num(flash_file_task_kpi, "with_trust_mismatch_rate") <= float(
            rules.get("trust_mismatch_rate_max", 0.0)
        )
        checks["flash_file_task_llm_used"] = _num(flash_file_task_kpi, "with_avg_model_calls") >= float(
            rules.get("flash_file_task_avg_model_calls_min", 1.0)
        )
        checks["flash_file_task_tokens_measured"] = _num(flash_file_task_kpi, "with_token_measured_rate") >= float(
            rules.get("flash_file_task_token_measured_rate_min", 1.0)
        )
        if "flash_file_task_wall_overhead_sec_max" in rules:
            checks["flash_file_task_wall_overhead"] = _num(flash_file_task_kpi, "wall_overhead_sec") <= float(
                rules["flash_file_task_wall_overhead_sec_max"]
            )
    if "rolling_7_window" in rules:
        checks["rolling_stability_7"] = (
            bool(rolling_7.get("pass", False))
            and int(rolling_7.get("window", 0) or 0) == int(rules["rolling_7_window"])
            and int(rolling_7.get("pass_count", 0) or 0) >= int(rules["rolling_7_min_passes"])
        )
    if "rolling_14_window" in rules:
        checks["rolling_stability_14"] = (
            bool(rolling_14.get("pass", False))
            and int(rolling_14.get("window", 0) or 0) == int(rules["rolling_14_window"])
            and int(rolling_14.get("pass_count", 0) or 0) >= int(rules["rolling_14_min_passes"])
        )
    return checks


def _ratio(checks: dict[str, bool]) -> float:
    total = max(1, len(checks))
    passed = sum(1 for v in checks.values() if bool(v))
    return round(passed / total, 4)


def _build_realism_checks(
    *,
    rules: dict[str, Any],
    realism_score: float,
    daily_kpi: dict[str, Any],
    hard_kpi: dict[str, Any],
    cross_kpi: dict[str, Any],
    flash_file_task_kpi: dict[str, Any],
    ops_trend_verdict: str,
    ops_kpi: dict[str, Any],
) -> dict[str, bool]:
    checks: dict[str, bool] = {
        "full_ab_realism_score": realism_score >= float(rules["full_ab_realism_score_min"]),
        "daily_semantic_rate": _num(daily_kpi, "with_semantic_verified_rate") >= float(rules["semantic_rate_min"]),
        "hard_semantic_rate": _num(hard_kpi, "with_semantic_verified_rate") >= float(rules["semantic_rate_min"]),
        "cross_semantic_rate": _num(cross_kpi, "with_semantic_verified_rate") >= float(rules["semantic_rate_min"]),
        "daily_trust_mismatch": _num(daily_kpi, "with_trust_mismatch_rate") <= float(rules["trust_mismatch_rate_max"]),
        "hard_trust_mismatch": _num(hard_kpi, "with_trust_mismatch_rate") <= float(rules["trust_mismatch_rate_max"]),
        "cross_trust_mismatch": _num(cross_kpi, "with_trust_mismatch_rate") <= float(rules["trust_mismatch_rate_max"]),
        "ops_rounds_trend_gate": ops_trend_verdict == str(rules["ops_rounds_trend_gate"]),
        "ops_semantic_rate": _num(ops_kpi, "with_semantic_verified_rate") >= float(rules["ops_semantic_rate_min"]),
    }
    if flash_file_task_kpi:
        checks.update(
            {
                "flash_file_task_solve_rate": _num(flash_file_task_kpi, "with_solve_rate")
                >= float(rules["flash_file_task_solve_rate_min"]),
                "flash_file_task_semantic_rate": _num(flash_file_task_kpi, "with_semantic_verified_rate")
                >= float(rules["flash_file_task_semantic_rate_min"]),
                "flash_file_task_trust_mismatch": _num(flash_file_task_kpi, "with_trust_mismatch_rate")
                <= float(rules["trust_mismatch_rate_max"]),
                "flash_file_task_llm_used": _num(flash_file_task_kpi, "with_avg_model_calls")
                >= float(rules["flash_file_task_avg_model_calls_min"]),
                "flash_file_task_tokens_measured": _num(flash_file_task_kpi, "with_token_measured_rate")
                >= float(rules["flash_file_task_token_measured_rate_min"]),
                "flash_file_task_wall_overhead": _num(flash_file_task_kpi, "wall_overhead_sec")
                <= float(rules["flash_file_task_wall_overhead_sec_max"]),
            }
        )
    return checks


def _select_verdict(*, checks: dict[str, dict[str, bool]], order: list[str], warn_fallback: str = "WARN") -> str:
    for level in order:
        if all(checks[level].values()):
            return level
    return warn_fallback


def evaluate_s_grade(*, full_ab: dict[str, Any], ops_rounds: dict[str, Any], service_full_ab: dict[str, Any] | None = None) -> dict[str, Any]:
    buckets = _bucket_map(full_ab)
    service_buckets = _bucket_map(service_full_ab or {})
    daily_kpi = (buckets.get("daily", {}) or {}).get("kpi", {}) if isinstance(buckets.get("daily", {}), dict) else {}
    hard_kpi = (buckets.get("hard", {}) or {}).get("kpi", {}) if isinstance(buckets.get("hard", {}), dict) else {}
    cross_kpi = (buckets.get("cross_module", {}) or {}).get("kpi", {}) if isinstance(buckets.get("cross_module", {}), dict) else {}
    stress_kpi = (buckets.get("cross_module_stress", {}) or {}).get("kpi", {}) if isinstance(buckets.get("cross_module_stress", {}), dict) else {}
    flash_file_task_bucket = buckets.get("flash_file_task_cross_module", {}) or {}
    flash_file_task_kpi = (
        _bucket_kpi_with_eval_fields(flash_file_task_bucket, with_side="b")
        if isinstance(flash_file_task_bucket, dict)
        else {}
    )
    service_stress_kpi = (
        (service_buckets.get("cross_module_stress", {}) or {}).get("kpi", {})
        if isinstance(service_buckets.get("cross_module_stress", {}), dict)
        else {}
    )
    stress_overhead_kpi = service_stress_kpi or stress_kpi

    weighted_score = float(full_ab.get("weighted_score", 0.0) or 0.0)
    realism_score = float(full_ab.get("realism_score", weighted_score) or 0.0)
    ops_trend_verdict = str(((ops_rounds.get("trend_gate", {}) or {}).get("verdict", "WARN")))
    ops_kpi = (ops_rounds.get("kpi_median_3round", {}) or {}) if isinstance(ops_rounds.get("kpi_median_3round", {}), dict) else {}
    rolling_7 = (ops_rounds.get("stability_rolling_7", {}) or {}) if isinstance(ops_rounds.get("stability_rolling_7", {}), dict) else {}
    rolling_14 = (ops_rounds.get("stability_rolling_14", {}) or {}) if isinstance(ops_rounds.get("stability_rolling_14", {}), dict) else {}
    self_heal = (ops_rounds.get("self_heal", {}) or {}) if isinstance(ops_rounds.get("self_heal", {}), dict) else {}
    anti_hall = (ops_rounds.get("anti_hallucination", {}) or {}) if isinstance(ops_rounds.get("anti_hallucination", {}), dict) else {}
    capability = (ops_rounds.get("capability_paths", {}) or {}) if isinstance(ops_rounds.get("capability_paths", {}), dict) else {}

    rules = {
        "S_PASS": {
            "full_ab_weighted_score_min": 0.965, "daily_solve_rate_min": 1.0, "daily_semantic_rate_min": 1.0,
            "hard_delta_solve_rate_min": 0.6, "cross_delta_solve_rate_min": 0.6, "trust_mismatch_rate_max": 0.0,
            "ops_rounds_trend_gate": "PASS", "ops_solve_rate_min": 0.95, "ops_semantic_rate_min": 0.95,
            "ops_overhead_p95_sec_max": 1.2, "ops_overhead_worst_decile_mean_sec_max": 1.3,
            "self_heal_first_pass_min": 0.8, "self_heal_repair_success_min": 0.8,
            "learn_attempt_rate_min": 0.8, "learn_citation_usage_rate_min": 0.7, "semantic_contract_verified_rate_min": 0.95,
        },
        "S_PLUS": {
            "full_ab_weighted_score_min": 0.99, "daily_solve_rate_min": 1.0, "daily_semantic_rate_min": 1.0,
            "hard_delta_solve_rate_min": 0.85, "cross_delta_solve_rate_min": 0.85, "trust_mismatch_rate_max": 0.0,
            "ops_rounds_trend_gate": "PASS", "ops_solve_rate_min": 0.98, "ops_semantic_rate_min": 0.98,
            "ops_overhead_p95_sec_max": 1.0, "ops_overhead_worst_decile_mean_sec_max": 1.1,
            "self_heal_first_pass_min": 0.9, "self_heal_repair_success_min": 0.9,
            "learn_attempt_rate_min": 0.8, "learn_citation_usage_rate_min": 0.8, "semantic_contract_verified_rate_min": 0.99,
        },
        "S2_PASS": {
            "full_ab_weighted_score_min": 0.995, "daily_solve_rate_min": 1.0, "daily_semantic_rate_min": 1.0,
            "hard_delta_solve_rate_min": 0.9, "cross_delta_solve_rate_min": 0.9, "trust_mismatch_rate_max": 0.0,
            "ops_rounds_trend_gate": "PASS", "ops_solve_rate_min": 1.0, "ops_semantic_rate_min": 1.0,
            "ops_overhead_p95_sec_max": 0.85, "ops_overhead_worst_decile_mean_sec_max": 0.95,
            "self_heal_first_pass_min": 0.95, "self_heal_repair_success_min": 0.95,
            "learn_attempt_rate_min": 0.85, "learn_citation_usage_rate_min": 0.85, "semantic_contract_verified_rate_min": 1.0,
        },
        "S_ELITE": {
            "full_ab_weighted_score_min": 0.998, "daily_solve_rate_min": 1.0, "daily_semantic_rate_min": 1.0,
            "hard_delta_solve_rate_min": 0.92, "cross_delta_solve_rate_min": 0.92, "trust_mismatch_rate_max": 0.0,
            "ops_rounds_trend_gate": "PASS", "ops_solve_rate_min": 1.0, "ops_semantic_rate_min": 1.0,
            "ops_overhead_p95_sec_max": 0.8, "ops_overhead_worst_decile_mean_sec_max": 0.9,
            "self_heal_first_pass_min": 0.98, "self_heal_repair_success_min": 0.98,
            "learn_attempt_rate_min": 0.9, "learn_citation_usage_rate_min": 0.9, "semantic_contract_verified_rate_min": 1.0,
        },
        "S3_PASS": {
            "full_ab_weighted_score_min": 0.999, "daily_solve_rate_min": 1.0, "daily_semantic_rate_min": 1.0,
            "hard_delta_solve_rate_min": 0.95, "cross_delta_solve_rate_min": 0.95, "trust_mismatch_rate_max": 0.0,
            "ops_rounds_trend_gate": "PASS", "ops_solve_rate_min": 1.0, "ops_semantic_rate_min": 1.0,
            "ops_overhead_p95_sec_max": 0.65, "ops_overhead_worst_decile_mean_sec_max": 0.75,
            "self_heal_first_pass_min": 0.99, "self_heal_repair_success_min": 0.99,
            "learn_attempt_rate_min": 0.95, "learn_citation_usage_rate_min": 0.95, "semantic_contract_verified_rate_min": 1.0,
            "stress_delta_solve_rate_min": 0.95, "rolling_7_window": 7, "rolling_7_min_passes": 6,
        },
        "S4_PASS": {
            "full_ab_weighted_score_min": 1.0, "daily_solve_rate_min": 1.0, "daily_semantic_rate_min": 1.0,
            "hard_delta_solve_rate_min": 0.97, "cross_delta_solve_rate_min": 0.97, "trust_mismatch_rate_max": 0.0,
            "ops_rounds_trend_gate": "PASS", "ops_solve_rate_min": 1.0, "ops_semantic_rate_min": 1.0,
            "ops_overhead_p95_sec_max": 0.55, "ops_overhead_worst_decile_mean_sec_max": 0.65,
            "self_heal_first_pass_min": 0.99, "self_heal_repair_success_min": 0.99,
            "learn_attempt_rate_min": 0.98, "learn_citation_usage_rate_min": 0.98, "semantic_contract_verified_rate_min": 1.0,
            "stress_delta_solve_rate_min": 0.97, "rolling_7_window": 7, "rolling_7_min_passes": 6,
        },
        "S5_PASS": {
            "full_ab_weighted_score_min": 1.0, "daily_solve_rate_min": 1.0, "daily_semantic_rate_min": 1.0,
            "hard_delta_solve_rate_min": 1.0, "cross_delta_solve_rate_min": 1.0, "trust_mismatch_rate_max": 0.0,
            "ops_rounds_trend_gate": "PASS", "ops_solve_rate_min": 1.0, "ops_semantic_rate_min": 1.0,
            "ops_overhead_p95_sec_max": 0.45, "ops_overhead_worst_decile_mean_sec_max": 0.55,
            "self_heal_first_pass_min": 1.0, "self_heal_repair_success_min": 1.0,
            "learn_attempt_rate_min": 1.0, "learn_citation_usage_rate_min": 1.0, "semantic_contract_verified_rate_min": 1.0,
            "stress_delta_solve_rate_min": 1.0, "rolling_7_window": 7, "rolling_7_min_passes": 6,
        },
        "S6_PASS": {
            "full_ab_weighted_score_min": 1.0, "daily_solve_rate_min": 1.0, "daily_semantic_rate_min": 1.0,
            "hard_delta_solve_rate_min": 1.0, "cross_delta_solve_rate_min": 1.0, "trust_mismatch_rate_max": 0.0,
            "ops_rounds_trend_gate": "PASS", "ops_solve_rate_min": 1.0, "ops_semantic_rate_min": 1.0,
            "ops_overhead_p95_sec_max": 0.40, "ops_overhead_worst_decile_mean_sec_max": 0.50,
            "self_heal_first_pass_min": 1.0, "self_heal_repair_success_min": 1.0,
            "learn_attempt_rate_min": 1.0, "learn_citation_usage_rate_min": 1.0, "semantic_contract_verified_rate_min": 1.0,
            "stress_delta_solve_rate_min": 1.0, "rolling_14_window": 14, "rolling_14_min_passes": 13,
        },
        "S7_PASS": {
            "full_ab_weighted_score_min": 1.0, "daily_solve_rate_min": 1.0, "daily_semantic_rate_min": 1.0,
            "hard_delta_solve_rate_min": 1.0, "cross_delta_solve_rate_min": 1.0, "trust_mismatch_rate_max": 0.0,
            "ops_rounds_trend_gate": "PASS", "ops_solve_rate_min": 1.0, "ops_semantic_rate_min": 1.0,
            "ops_overhead_p95_sec_max": 0.25, "ops_overhead_worst_decile_mean_sec_max": 0.30,
            "self_heal_first_pass_min": 1.0, "self_heal_repair_success_min": 1.0,
            "learn_attempt_rate_min": 1.0, "learn_citation_usage_rate_min": 1.0, "semantic_contract_verified_rate_min": 1.0,
            "stress_delta_solve_rate_min": 1.0, "rolling_14_window": 14, "rolling_14_min_passes": 13,
        },
        "S8_PASS": {
            "full_ab_weighted_score_min": 1.0, "daily_solve_rate_min": 1.0, "daily_semantic_rate_min": 1.0,
            "hard_delta_solve_rate_min": 1.0, "cross_delta_solve_rate_min": 1.0, "trust_mismatch_rate_max": 0.0,
            "ops_rounds_trend_gate": "PASS", "ops_solve_rate_min": 1.0, "ops_semantic_rate_min": 1.0,
            "ops_overhead_p95_sec_max": 0.20, "ops_overhead_worst_decile_mean_sec_max": 0.25,
            "self_heal_first_pass_min": 1.0, "self_heal_repair_success_min": 1.0,
            "learn_attempt_rate_min": 1.0, "learn_citation_usage_rate_min": 1.0, "semantic_contract_verified_rate_min": 1.0,
            "stress_delta_solve_rate_min": 1.0, "stress_wall_overhead_sec_max": 0.35,
            "rolling_14_window": 14, "rolling_14_min_passes": 14,
        },
        "S9_PASS": {
            "full_ab_weighted_score_min": 1.0, "daily_solve_rate_min": 1.0, "daily_semantic_rate_min": 1.0,
            "hard_delta_solve_rate_min": 1.0, "cross_delta_solve_rate_min": 1.0, "trust_mismatch_rate_max": 0.0,
            "ops_rounds_trend_gate": "PASS", "ops_solve_rate_min": 1.0, "ops_semantic_rate_min": 1.0,
            "ops_overhead_p95_sec_max": 0.12, "ops_overhead_worst_decile_mean_sec_max": 0.16,
            "self_heal_first_pass_min": 1.0, "self_heal_repair_success_min": 1.0,
            "learn_attempt_rate_min": 1.0, "learn_citation_usage_rate_min": 1.0, "semantic_contract_verified_rate_min": 1.0,
            "stress_delta_solve_rate_min": 1.0, "stress_wall_overhead_sec_max": 0.25,
            "rolling_14_window": 14, "rolling_14_min_passes": 14,
        },
        "S10_PASS": {
            "full_ab_weighted_score_min": 1.0, "daily_solve_rate_min": 1.0, "daily_semantic_rate_min": 1.0,
            "full_ab_realism_score_min": 0.9,
            "hard_delta_solve_rate_min": 0.8, "cross_delta_solve_rate_min": 0.8, "trust_mismatch_rate_max": 0.0,
            "ops_rounds_trend_gate": "PASS", "ops_solve_rate_min": 1.0, "ops_semantic_rate_min": 1.0,
            "ops_overhead_p95_sec_max": 0.08, "ops_overhead_worst_decile_mean_sec_max": 0.10,
            "self_heal_first_pass_min": 1.0, "self_heal_repair_success_min": 1.0,
            "learn_attempt_rate_min": 1.0, "learn_citation_usage_rate_min": 1.0, "semantic_contract_verified_rate_min": 1.0,
            "stress_delta_solve_rate_min": 0.8, "stress_wall_overhead_sec_max": 0.18,
            "flash_file_task_solve_rate_min": 1.0, "flash_file_task_semantic_rate_min": 1.0,
            "flash_file_task_avg_model_calls_min": 1.0, "flash_file_task_token_measured_rate_min": 1.0,
            "flash_file_task_wall_overhead_sec_max": 60.0,
            "rolling_14_window": 14, "rolling_14_min_passes": 14,
        },
    }

    realism_rules = {
        "REALISM_S_PASS": {
            "full_ab_realism_score_min": 0.90,
            "semantic_rate_min": 1.0,
            "trust_mismatch_rate_max": 0.0,
            "ops_rounds_trend_gate": "PASS",
            "ops_semantic_rate_min": 1.0,
            "flash_file_task_solve_rate_min": 1.0,
            "flash_file_task_semantic_rate_min": 1.0,
            "flash_file_task_avg_model_calls_min": 1.0,
            "flash_file_task_token_measured_rate_min": 1.0,
            "flash_file_task_wall_overhead_sec_max": 60.0,
        },
        "REALISM_S_PLUS": {
            "full_ab_realism_score_min": 0.93,
            "semantic_rate_min": 1.0,
            "trust_mismatch_rate_max": 0.0,
            "ops_rounds_trend_gate": "PASS",
            "ops_semantic_rate_min": 1.0,
            "flash_file_task_solve_rate_min": 1.0,
            "flash_file_task_semantic_rate_min": 1.0,
            "flash_file_task_avg_model_calls_min": 1.0,
            "flash_file_task_token_measured_rate_min": 1.0,
            "flash_file_task_wall_overhead_sec_max": 40.0,
        },
        "REALISM_S10_PASS": {
            "full_ab_realism_score_min": 0.95,
            "semantic_rate_min": 1.0,
            "trust_mismatch_rate_max": 0.0,
            "ops_rounds_trend_gate": "PASS",
            "ops_semantic_rate_min": 1.0,
            "flash_file_task_solve_rate_min": 1.0,
            "flash_file_task_semantic_rate_min": 1.0,
            "flash_file_task_avg_model_calls_min": 1.0,
            "flash_file_task_token_measured_rate_min": 1.0,
            "flash_file_task_wall_overhead_sec_max": 25.0,
        },
    }

    checks = {name: _build_checks(
        rules=rule,
        weighted_score=weighted_score,
        realism_score=realism_score,
        daily_kpi=daily_kpi,
        hard_kpi=hard_kpi,
        cross_kpi=cross_kpi,
        stress_kpi=stress_kpi,
        stress_overhead_kpi=stress_overhead_kpi,
        flash_file_task_kpi=flash_file_task_kpi,
        ops_trend_verdict=ops_trend_verdict,
        ops_kpi=ops_kpi,
        self_heal=self_heal,
        capability=capability,
        anti_hall=anti_hall,
        rolling_7=rolling_7,
        rolling_14=rolling_14,
    ) for name, rule in rules.items()}
    realism_checks = {
        name: _build_realism_checks(
            rules=rule,
            realism_score=realism_score,
            daily_kpi=daily_kpi,
            hard_kpi=hard_kpi,
            cross_kpi=cross_kpi,
            flash_file_task_kpi=flash_file_task_kpi,
            ops_trend_verdict=ops_trend_verdict,
            ops_kpi=ops_kpi,
        )
        for name, rule in realism_rules.items()
    }

    order = ["S10_PASS", "S9_PASS", "S8_PASS", "S7_PASS", "S6_PASS", "S5_PASS", "S4_PASS", "S3_PASS", "S_ELITE", "S2_PASS", "S_PLUS", "S_PASS"]
    verdict = _select_verdict(checks=checks, order=order)
    if verdict == "WARN":
        pass_ratio = _ratio(checks["S_PASS"])
        verdict = "A_PASS" if pass_ratio >= 0.85 else ("B_PASS" if pass_ratio >= 0.7 else "WARN")
    realism_order = ["REALISM_S10_PASS", "REALISM_S_PLUS", "REALISM_S_PASS"]
    realism_verdict = _select_verdict(checks=realism_checks, order=realism_order, warn_fallback="REALISM_WARN")

    summary: dict[str, Any] = {
        "verdict": verdict,
        "legacy_verdict": verdict,
        "realism_verdict": realism_verdict,
        "pass_count": sum(1 for v in checks["S_PASS"].values() if v),
        "total_count": len(checks["S_PASS"]),
        "pass_ratio": _ratio(checks["S_PASS"]),
    }
    for key in ["S_PLUS", "S2_PASS", "S_ELITE", "S3_PASS", "S4_PASS", "S5_PASS", "S6_PASS", "S7_PASS", "S8_PASS", "S9_PASS", "S10_PASS"]:
        label = key.lower().replace("_pass", "_pass").replace("+", "_plus")
        prefix = {
            "S_PLUS": "s_plus",
            "S2_PASS": "s2",
            "S_ELITE": "s_elite",
            "S3_PASS": "s3",
            "S4_PASS": "s4",
            "S5_PASS": "s5",
            "S6_PASS": "s6",
            "S7_PASS": "s7",
            "S8_PASS": "s8",
            "S9_PASS": "s9",
            "S10_PASS": "s10",
        }[key]
        summary[f"{prefix}_pass_count"] = sum(1 for v in checks[key].values() if v)
        summary[f"{prefix}_total_count"] = len(checks[key])
        summary[f"{prefix}_pass_ratio"] = _ratio(checks[key])
    for key in ["REALISM_S_PASS", "REALISM_S_PLUS", "REALISM_S10_PASS"]:
        prefix = {
            "REALISM_S_PASS": "realism_s",
            "REALISM_S_PLUS": "realism_s_plus",
            "REALISM_S10_PASS": "realism_s10",
        }[key]
        summary[f"{prefix}_pass_count"] = sum(1 for v in realism_checks[key].values() if v)
        summary[f"{prefix}_total_count"] = len(realism_checks[key])
        summary[f"{prefix}_pass_ratio"] = _ratio(realism_checks[key])

    return {
        "status": "SUCCESS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "full_ab_weighted_score": weighted_score,
            "full_ab_realism_score": realism_score,
            "ops_rounds_trend_gate": ops_trend_verdict,
            "ops_kpi_median_3round": ops_kpi,
            "rolling_stability_7": rolling_7,
            "rolling_stability_14": rolling_14,
            "self_heal": self_heal,
            "capability_paths": capability,
            "anti_hallucination": anti_hall,
            "cross_module_stress_kpi": stress_kpi,
            "cross_module_stress_overhead_kpi": stress_overhead_kpi,
            "flash_file_task_cross_module_kpi": flash_file_task_kpi,
        },
        "rules": rules["S_PASS"],
        "s_plus_rules": rules["S_PLUS"],
        "s2_rules": rules["S2_PASS"],
        "s_elite_rules": rules["S_ELITE"],
        "s3_rules": rules["S3_PASS"],
        "s4_rules": rules["S4_PASS"],
        "s5_rules": rules["S5_PASS"],
        "s6_rules": rules["S6_PASS"],
        "s7_rules": rules["S7_PASS"],
        "s8_rules": rules["S8_PASS"],
        "s9_rules": rules["S9_PASS"],
        "s10_rules": rules["S10_PASS"],
        "realism_rules": realism_rules["REALISM_S_PASS"],
        "realism_s_plus_rules": realism_rules["REALISM_S_PLUS"],
        "realism_s10_rules": realism_rules["REALISM_S10_PASS"],
        "checks": checks["S_PASS"],
        "s_plus_checks": checks["S_PLUS"],
        "s2_checks": checks["S2_PASS"],
        "s_elite_checks": checks["S_ELITE"],
        "s3_checks": checks["S3_PASS"],
        "s4_checks": checks["S4_PASS"],
        "s5_checks": checks["S5_PASS"],
        "s6_checks": checks["S6_PASS"],
        "s7_checks": checks["S7_PASS"],
        "s8_checks": checks["S8_PASS"],
        "s9_checks": checks["S9_PASS"],
        "s10_checks": checks["S10_PASS"],
        "realism_checks": realism_checks["REALISM_S_PASS"],
        "realism_s_plus_checks": realism_checks["REALISM_S_PLUS"],
        "realism_s10_checks": realism_checks["REALISM_S10_PASS"],
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate comprehensive S-grade from full_ab + ops_loop_rounds.")
    parser.add_argument("--full-ab-file", default="")
    parser.add_argument("--service-full-ab-file", default="")
    parser.add_argument("--ops-rounds-file", default="")
    parser.add_argument("--output-file", default="")
    parser.add_argument("--output-json", action="store_true")
    args = parser.parse_args()

    full_ab_file = Path(args.full_ab_file).resolve() if args.full_ab_file else _latest_file(
        ".nexus/reports/bench/full_ab/full_ab_report_*.json"
    )
    ops_rounds_file = Path(args.ops_rounds_file).resolve() if args.ops_rounds_file else _latest_file(
        ".nexus/reports/bench/ops_loop/ops_loop_rounds_daily_*.json"
    )

    full_ab = _load_json(full_ab_file)
    service_full_ab = _load_json(Path(args.service_full_ab_file).resolve()) if args.service_full_ab_file else None
    ops_rounds = _load_json(ops_rounds_file)
    payload = evaluate_s_grade(full_ab=full_ab, ops_rounds=ops_rounds, service_full_ab=service_full_ab)
    payload["sources"] = {
        "full_ab_file": str(full_ab_file),
        "service_full_ab_file": str(Path(args.service_full_ab_file).resolve()) if args.service_full_ab_file else "",
        "ops_rounds_file": str(ops_rounds_file),
    }

    out = Path(args.output_file).resolve() if args.output_file else Path(".nexus/reports/bench/s_grade").resolve() / f"s_grade_report_{int(time.time())}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    payload["report_file"] = str(out)

    if args.output_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"S-grade verdict: {payload['summary']['verdict']}")
        print(f"Report: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
