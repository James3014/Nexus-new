#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        payload = json.loads(text)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _load_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("runs"), list):
        return [row for row in payload["runs"] if isinstance(row, dict)]
    raise ValueError(f"Unsupported JSON payload at {path}")


def load_runs(path: str | Path) -> list[dict[str, Any]]:
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(src)
    ext = src.suffix.lower()
    if ext == ".csv":
        return _load_csv(src)
    if ext == ".jsonl":
        return _load_jsonl(src)
    if ext == ".json":
        return _load_json(src)
    raise ValueError(f"Unsupported file extension: {src}")


def _is_solved(row: dict[str, Any]) -> bool:
    semantic_raw = row.get("semantic_status")
    semantic = str(semantic_raw).strip().upper() if semantic_raw is not None else ""
    if semantic and semantic not in {"NONE", "NULL"}:
        return semantic == "VERIFIED"
    status = str(row.get("status", "")).strip().upper()
    if status:
        return status in {"PASS", "SUCCESS"}
    return False


def _is_trust_mismatch(row: dict[str, Any]) -> bool:
    if "report_trust_mismatch" in row:
        return bool(row.get("report_trust_mismatch"))
    # fallback signal for old rows
    return str(row.get("runtime_classification", "")).strip().lower() == "report_causality_defect"


def _median(values: list[float], default: float = 0.0) -> float:
    if not values:
        return float(default)
    return float(statistics.median(values))


def _rate(rows: list[dict[str, Any]], predicate) -> float:
    if not rows:
        return 0.0
    return round(sum(1 for row in rows if predicate(row)) / len(rows), 4)


def _relative_lift(baseline: float, treatment: float) -> float | None:
    if baseline <= 0:
        return None
    return round((treatment - baseline) / baseline, 4)


def _wilson_ci(successes: int, total: int, z: float = 1.96) -> list[float]:
    if total <= 0:
        return [0.0, 0.0]
    phat = successes / total
    denom = 1 + (z * z / total)
    centre = phat + (z * z / (2 * total))
    margin = z * ((phat * (1 - phat) + z * z / (4 * total)) / total) ** 0.5
    return [round(max(0.0, (centre - margin) / denom), 4), round(min(1.0, (centre + margin) / denom), 4)]


def _is_true(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


_NEXUS_PILLAR_KEYS = (
    "pillar_lancedb_active",
    "pillar_memory_active",
    "pillar_mempalace_active",
    "pillar_belief_active",
    "pillar_artifact_active",
)
_NEXUS_PHASE_KEYS = ("phase_p", "phase_x", "phase_d", "phase_r", "phase_a", "phase_c")


def _task_id(row: dict[str, Any], index: int) -> str:
    value = row.get("task_id", row.get("id", f"row_{index + 1}"))
    return str(value)


def _formal_nexus_issues(row: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not _is_true(row.get("gemini_uses_nexus")):
        issues.append("gemini_uses_nexus_false")
    if _as_int(row.get("model_calls"), 0) <= 0:
        issues.append("model_calls_zero")
    if not _is_true(row.get("nexus_context_delivered")):
        issues.append("nexus_context_not_delivered")
    if not _is_true(row.get("nexus_usage_valid")):
        issues.append("nexus_usage_invalid")
    missing_pillars = [key.removeprefix("pillar_").removesuffix("_active") for key in _NEXUS_PILLAR_KEYS if not _is_true(row.get(key))]
    if missing_pillars:
        issues.append("pillars_missing:" + ",".join(missing_pillars))
    missing_phases = [key.removeprefix("phase_").upper() for key in _NEXUS_PHASE_KEYS if not str(row.get(key, "") or "").strip()]
    if missing_phases:
        issues.append("phases_missing:" + ",".join(missing_phases))
    if not _is_true(row.get("capability_claim_verified")):
        issues.append("claim_not_verified")
    return issues


def summarize_formal_nexus_treatment(rows: list[dict[str, Any]]) -> dict[str, Any]:
    invalid_rows = [
        {"task_id": _task_id(row, index), "issues": _formal_nexus_issues(row)}
        for index, row in enumerate(rows)
        if _formal_nexus_issues(row)
    ]
    total = len(rows)
    valid_count = total - len(invalid_rows)
    return {
        "total_runs": total,
        "valid_count": valid_count,
        "valid_rate": round(valid_count / total, 4) if total else 0.0,
        "invalid_count": len(invalid_rows),
        "invalid_task_ids": [row["task_id"] for row in invalid_rows],
        "invalid_rows": invalid_rows,
        "criteria": [
            "gemini_uses_nexus=true",
            "model_calls>0",
            "nexus_context_delivered=true",
            "nexus_usage_valid=true",
            "five_pillars_active",
            "six_phases_present",
            "capability_claim_verified=true",
        ],
    }


def summarize_runs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total == 0:
        return {
            "total_runs": 0,
            "solve_count": 0,
            "solve_rate": 0.0,
            "solve_rate_ci95": [0.0, 0.0],
            "avg_duration_sec": 0.0,
            "avg_total_tokens": 0.0,
            "avg_total_tokens_measured_only": 0.0,
            "avg_model_calls": 0.0,
            "avg_attempt_count": 0.0,
            "token_observable_rate": 0.0,
            "token_measured_rate": 0.0,
            "trust_mismatch_rate": 0.0,
            "nexus_usage_valid_rate": 0.0,
            "gemini_uses_nexus_rate": 0.0,
            "nexus_rescue_rate": 0.0,
            "local_rescue_rate": 0.0,
            "guard_fallback_rate": 0.0,
            "verification_rescue_rate": 0.0,
            "llm_self_heal_rate": 0.0,
            "gemini_patch_pass_rate": 0.0,
            "pillar_lancedb_active_rate": 0.0,
            "pillar_memory_active_rate": 0.0,
            "pillar_mempalace_active_rate": 0.0,
            "pillar_belief_active_rate": 0.0,
            "pillar_artifact_active_rate": 0.0,
            "phase_completion_rate": 0.0,
            "claim_verified_rate": 0.0,
            "hyper_used_rate": 0.0,
            "self_heal_used_rate": 0.0,
            "swarm_used_rate": 0.0,
            "drone_used_rate": 0.0,
            "nightshift_recommended_rate": 0.0,
            "patch_success_count": 0,
            "patch_success_rate": 0.0,
            "verification_only_rate": 0.0,
            "mutation_required_rate": 0.0,
            "mutation_success_rate": 0.0,
            "rlm_trace_present_rate": 0.0,
        }

    solved = sum(1 for row in rows if _is_solved(row))
    semantic_verified = sum(
        1
        for row in rows
        if str(row.get("semantic_status", "")).strip().upper() == "VERIFIED"
    )
    total_duration = sum(
        _as_float(
            row.get(
                "task_duration_sec",
                row.get("duration_sec", row.get("elapsed_sec", row.get("avg_duration_sec", 0.0))),
            ),
            0.0,
        )
        for row in rows
    )
    total_wall_duration = sum(
        _as_float(row.get("wall_duration_sec", row.get("duration_sec", row.get("elapsed_sec", 0.0))), 0.0)
        for row in rows
    )
    durations = [
        _as_float(
            row.get(
                "task_duration_sec",
                row.get("duration_sec", row.get("elapsed_sec", row.get("avg_duration_sec", 0.0))),
            ),
            0.0,
        )
        for row in rows
    ]
    hard_rows = [row for row in rows if str(row.get("difficulty", "")).strip().lower() == "hard"]
    total_tokens = sum(_as_float(row.get("total_tokens"), 0.0) for row in rows)
    measured_token_rows = [
        row
        for row in rows
        if str(row.get("token_capture_status", "")).strip().lower() == "measured"
    ]
    estimated_token_rows = [
        row
        for row in rows
        if str(row.get("token_capture_status", "")).strip().lower() == "estimated"
    ]
    local_only_token_rows = [
        row
        for row in rows
        if str(row.get("token_capture_status", "")).strip().lower() == "not_applicable_local_only"
    ]
    model_measured_rows = [
        row
        for row in rows
        if str(row.get("model_token_capture_status", "")).strip().lower() == "measured"
    ]
    model_estimated_rows = [
        row
        for row in rows
        if str(row.get("model_token_capture_status", "")).strip().lower() == "estimated"
    ]
    local_rescue_rows = [
        row
        for row in rows
        if str(row.get("nexus_winner_source", "")).strip().lower() == "local"
        or (
            not str(row.get("nexus_winner_source", "")).strip()
            and str(row.get("rescue_cost_status", "")).strip().lower() == "local_only"
        )
    ]
    guard_fallback_rows = [
        row
        for row in rows
        if _is_true(row.get("guard_hit")) and _is_true(row.get("nexus_rescued"))
        and str(row.get("nexus_winner_source", "")).strip().lower() in {"local", "verification_only"}
    ]
    verification_rescue_rows = [
        row
        for row in rows
        if _is_true(row.get("artifact_verification_only"))
        and _is_true(row.get("nexus_rescued"))
    ]
    llm_self_heal_rows = [
        row
        for row in rows
        if "self_heal" in str(row.get("nexus_winner_source", "")).strip().lower()
        or (
            not str(row.get("nexus_winner_source", "")).strip()
            and _is_true(row.get("capability_self_heal_used"))
        )
    ]
    gateway_stats_source_rows = [
        row
        for row in rows
        if str(row.get("gateway_token_source", "")).strip().lower() == "stats"
    ]
    gateway_usage_source_rows = [
        row
        for row in rows
        if str(row.get("gateway_token_source", "")).strip().lower() == "usage_metadata"
    ]
    total_tokens_measured_only = sum(_as_float(row.get("total_tokens"), 0.0) for row in measured_token_rows)
    total_model_tokens = sum(_as_float(row.get("model_total_tokens"), 0.0) for row in rows)
    total_model_calls = sum(_as_int(row.get("model_calls"), 0) for row in rows)
    total_attempts = sum(_as_int(row.get("attempt_count"), 0) for row in rows)
    token_observable = sum(
        1
        for row in rows
        if str(row.get("token_capture_status", "")).strip().lower()
        not in {"", "unknown", "missing", "none", "null"}
    )
    token_measured = len(measured_token_rows)
    token_estimated = len(estimated_token_rows)
    token_local_only = len(local_only_token_rows)
    cost_comparable = token_measured
    trust_mismatch = sum(1 for row in rows if _is_trust_mismatch(row))
    phase_keys = ("phase_p", "phase_x", "phase_d", "phase_r", "phase_a", "phase_c")
    mutation_required_rows = [row for row in rows if _is_true(row.get("mutation_required"))]
    patch_success = sum(1 for row in rows if _is_solved(row) and _is_true(row.get("artifact_changed")))

    return {
        "total_runs": total,
        "solve_count": solved,
        "solve_rate": round(solved / total, 4),
        "solve_rate_ci95": _wilson_ci(solved, total),
        "semantic_verified_rate": round(semantic_verified / total, 4),
        "hard_success_rate": _rate(hard_rows, _is_solved),
        "avg_duration_sec": round(total_duration / total, 4),
        "median_duration_sec": round(_median(durations), 4),
        "avg_wall_duration_sec": round(total_wall_duration / total, 4),
        "avg_total_tokens": round(total_tokens / total, 2),
        "avg_total_tokens_measured_only": round(
            total_tokens_measured_only / max(1, token_measured),
            2,
        ),
        "avg_model_total_tokens": round(total_model_tokens / total, 2),
        "avg_model_calls": round(total_model_calls / total, 2),
        "avg_attempt_count": round(total_attempts / total, 2),
        "token_observable_rate": round(token_observable / total, 4),
        "token_measured_rate": round(token_measured / total, 4),
        "token_estimated_rate": round(token_estimated / total, 4),
        "token_local_only_rate": round(token_local_only / total, 4),
        "cost_comparable_rate": round(cost_comparable / total, 4),
        "model_token_measured_rate": round(len(model_measured_rows) / total, 4),
        "model_token_estimated_rate": round(len(model_estimated_rows) / total, 4),
        "local_rescue_rate": round(len(local_rescue_rows) / total, 4),
        "guard_fallback_rate": round(len(guard_fallback_rows) / total, 4),
        "verification_rescue_rate": round(len(verification_rescue_rows) / total, 4),
        "llm_self_heal_rate": round(len(llm_self_heal_rows) / total, 4),
        "gateway_stats_source_rate": round(len(gateway_stats_source_rows) / total, 4),
        "gateway_usage_metadata_source_rate": round(len(gateway_usage_source_rows) / total, 4),
        "trust_mismatch_rate": round(trust_mismatch / total, 4),
        "nexus_usage_valid_rate": _rate(rows, lambda r: _is_true(r.get("nexus_usage_valid"))),
        "gemini_uses_nexus_rate": _rate(rows, lambda r: _is_true(r.get("gemini_uses_nexus"))),
        "nexus_rescue_rate": _rate(rows, lambda r: _is_true(r.get("nexus_rescued"))),
        "gemini_patch_pass_rate": _rate(rows, lambda r: str(r.get("gemini_patch_status", "")).lower() == "passed"),
        "pillar_lancedb_active_rate": _rate(rows, lambda r: _is_true(r.get("pillar_lancedb_active"))),
        "pillar_memory_active_rate": _rate(rows, lambda r: _is_true(r.get("pillar_memory_active"))),
        "pillar_mempalace_active_rate": _rate(rows, lambda r: _is_true(r.get("pillar_mempalace_active"))),
        "pillar_belief_active_rate": _rate(rows, lambda r: _is_true(r.get("pillar_belief_active"))),
        "pillar_artifact_active_rate": _rate(rows, lambda r: _is_true(r.get("pillar_artifact_active"))),
        "phase_completion_rate": _rate(rows, lambda r: all(str(r.get(k, "") or "").strip() for k in phase_keys)),
        "claim_verified_rate": _rate(rows, lambda r: _is_true(r.get("capability_claim_verified"))),
        "hyper_used_rate": _rate(rows, lambda r: _is_true(r.get("capability_hyper_used"))),
        "self_heal_used_rate": _rate(rows, lambda r: _is_true(r.get("capability_self_heal_used"))),
        "swarm_used_rate": _rate(rows, lambda r: _is_true(r.get("capability_swarm_used"))),
        "drone_used_rate": _rate(rows, lambda r: _is_true(r.get("capability_drone_used"))),
        "nightshift_recommended_rate": _rate(
            rows,
            lambda r: _is_true(r.get("capability_nightshift_recommended"))
            or _is_true(r.get("guard_nightshift_recommended")),
        ),
        "patch_success_count": patch_success,
        "patch_success_rate": round(patch_success / total, 4),
        "verification_only_rate": _rate(rows, lambda r: _is_true(r.get("artifact_verification_only"))),
        "mutation_required_rate": _rate(rows, lambda r: _is_true(r.get("mutation_required"))),
        "mutation_success_rate": _rate(mutation_required_rows, lambda r: _is_solved(r) and _is_true(r.get("artifact_changed"))),
        "rlm_trace_present_rate": _rate(rows, lambda r: _is_true(r.get("rlm_trace_present"))),
    }


def _group_rows(rows: list[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get(field, "") or "uncategorized")
        grouped.setdefault(key, []).append(row)
    return grouped


def compare_grouped(rows_a: list[dict[str, Any]], rows_b: list[dict[str, Any]], *, field: str) -> dict[str, Any]:
    grouped_a = _group_rows(rows_a, field)
    grouped_b = _group_rows(rows_b, field)
    out: dict[str, Any] = {}
    for key in sorted(set(grouped_a) | set(grouped_b)):
        summary_a = summarize_runs(grouped_a.get(key, []))
        summary_b = summarize_runs(grouped_b.get(key, []))
        out[key] = {
            "a": summary_a,
            "b": summary_b,
            "solve_rate_delta": round(summary_b["solve_rate"] - summary_a["solve_rate"], 4),
            "patch_success_rate_delta": round(summary_b["patch_success_rate"] - summary_a["patch_success_rate"], 4),
        }
    return out


def compare_datasets(label_a: str, rows_a: list[dict[str, Any]], label_b: str, rows_b: list[dict[str, Any]]) -> dict[str, Any]:
    summary_a = summarize_runs(rows_a)
    summary_b = summarize_runs(rows_b)
    formal_treatment = summarize_formal_nexus_treatment(rows_b)
    baseline_solve = float(summary_a["solve_rate"])
    baseline_semantic = float(summary_a["semantic_verified_rate"])
    delta = {
        "solve_rate_delta": round(summary_b["solve_rate"] - summary_a["solve_rate"], 4),
        "semantic_verified_rate_delta": round(
            summary_b["semantic_verified_rate"] - summary_a["semantic_verified_rate"], 4
        ),
        "hard_success_rate_delta": round(summary_b["hard_success_rate"] - summary_a["hard_success_rate"], 4),
        "nexus_lift": _relative_lift(baseline_solve, float(summary_b["solve_rate"])),
        "semantic_nexus_lift": _relative_lift(baseline_semantic, float(summary_b["semantic_verified_rate"])),
        "avg_duration_sec_delta": round(summary_b["avg_duration_sec"] - summary_a["avg_duration_sec"], 4),
        "median_duration_sec_delta": round(summary_b["median_duration_sec"] - summary_a["median_duration_sec"], 4),
        "avg_wall_duration_sec_delta": round(
            summary_b["avg_wall_duration_sec"] - summary_a["avg_wall_duration_sec"], 4
        ),
        "avg_total_tokens_delta": round(summary_b["avg_total_tokens"] - summary_a["avg_total_tokens"], 2),
        "avg_total_tokens_measured_only_delta": round(
            summary_b["avg_total_tokens_measured_only"] - summary_a["avg_total_tokens_measured_only"],
            2,
        ),
        "avg_model_total_tokens_delta": round(
            summary_b["avg_model_total_tokens"] - summary_a["avg_model_total_tokens"],
            2,
        ),
        "avg_model_calls_delta": round(summary_b["avg_model_calls"] - summary_a["avg_model_calls"], 2),
        "avg_attempt_count_delta": round(summary_b["avg_attempt_count"] - summary_a["avg_attempt_count"], 2),
        "rlm_trace_present_rate_delta": round(
            summary_b["rlm_trace_present_rate"] - summary_a["rlm_trace_present_rate"], 4
        ),
        "token_observable_rate_delta": round(
            summary_b["token_observable_rate"] - summary_a["token_observable_rate"], 4
        ),
        "token_measured_rate_delta": round(
            summary_b["token_measured_rate"] - summary_a["token_measured_rate"], 4
        ),
        "token_estimated_rate_delta": round(
            summary_b["token_estimated_rate"] - summary_a["token_estimated_rate"], 4
        ),
        "token_local_only_rate_delta": round(
            summary_b["token_local_only_rate"] - summary_a["token_local_only_rate"], 4
        ),
        "cost_comparable_rate_delta": round(
            summary_b["cost_comparable_rate"] - summary_a["cost_comparable_rate"], 4
        ),
        "model_token_measured_rate_delta": round(
            summary_b["model_token_measured_rate"] - summary_a["model_token_measured_rate"], 4
        ),
        "model_token_estimated_rate_delta": round(
            summary_b["model_token_estimated_rate"] - summary_a["model_token_estimated_rate"], 4
        ),
        "gateway_stats_source_rate_delta": round(
            summary_b["gateway_stats_source_rate"] - summary_a["gateway_stats_source_rate"], 4
        ),
        "gateway_usage_metadata_source_rate_delta": round(
            summary_b["gateway_usage_metadata_source_rate"] - summary_a["gateway_usage_metadata_source_rate"], 4
        ),
        "local_rescue_rate_delta": round(
            summary_b["local_rescue_rate"] - summary_a["local_rescue_rate"], 4
        ),
        "guard_fallback_rate_delta": round(
            summary_b["guard_fallback_rate"] - summary_a["guard_fallback_rate"], 4
        ),
        "verification_rescue_rate_delta": round(
            summary_b["verification_rescue_rate"] - summary_a["verification_rescue_rate"], 4
        ),
        "llm_self_heal_rate_delta": round(
            summary_b["llm_self_heal_rate"] - summary_a["llm_self_heal_rate"], 4
        ),
        "hyper_used_rate_delta": round(summary_b["hyper_used_rate"] - summary_a["hyper_used_rate"], 4),
        "self_heal_used_rate_delta": round(summary_b["self_heal_used_rate"] - summary_a["self_heal_used_rate"], 4),
        "swarm_used_rate_delta": round(summary_b["swarm_used_rate"] - summary_a["swarm_used_rate"], 4),
        "drone_used_rate_delta": round(summary_b["drone_used_rate"] - summary_a["drone_used_rate"], 4),
        "nightshift_recommended_rate_delta": round(
            summary_b["nightshift_recommended_rate"] - summary_a["nightshift_recommended_rate"], 4
        ),
        "trust_mismatch_rate_delta": round(summary_b["trust_mismatch_rate"] - summary_a["trust_mismatch_rate"], 4),
        "nexus_usage_valid_rate_delta": round(summary_b["nexus_usage_valid_rate"] - summary_a["nexus_usage_valid_rate"], 4),
        "gemini_uses_nexus_rate_delta": round(summary_b["gemini_uses_nexus_rate"] - summary_a["gemini_uses_nexus_rate"], 4),
        "nexus_rescue_rate_delta": round(summary_b["nexus_rescue_rate"] - summary_a["nexus_rescue_rate"], 4),
        "gemini_patch_pass_rate_delta": round(summary_b["gemini_patch_pass_rate"] - summary_a["gemini_patch_pass_rate"], 4),
        "phase_completion_rate_delta": round(summary_b["phase_completion_rate"] - summary_a["phase_completion_rate"], 4),
        "claim_verified_rate_delta": round(summary_b["claim_verified_rate"] - summary_a["claim_verified_rate"], 4),
        "patch_success_rate_delta": round(summary_b["patch_success_rate"] - summary_a["patch_success_rate"], 4),
        "verification_only_rate_delta": round(summary_b["verification_only_rate"] - summary_a["verification_only_rate"], 4),
        "mutation_success_rate_delta": round(summary_b["mutation_success_rate"] - summary_a["mutation_success_rate"], 4),
    }
    return {
        "a": {"label": label_a, "summary": summary_a},
        "b": {"label": label_b, "summary": summary_b},
        "delta": delta,
        "by_category": compare_grouped(rows_a, rows_b, field="category"),
        "by_repo_kind": compare_grouped(rows_a, rows_b, field="repo_kind"),
        "formal_treatment": formal_treatment,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Nexus A/B benchmark results.")
    parser.add_argument("file_a", nargs="?", help="Dataset A (.csv/.jsonl/.json)")
    parser.add_argument("file_b", nargs="?", help="Dataset B (.csv/.jsonl/.json)")
    parser.add_argument("--a", dest="file_a_opt", help="Dataset A (.csv/.jsonl/.json)")
    parser.add_argument("--b", dest="file_b_opt", help="Dataset B (.csv/.jsonl/.json)")
    parser.add_argument("--label-a", default="A")
    parser.add_argument("--label-b", default="B")
    parser.add_argument("--output-json", action="store_true")
    parser.add_argument("--output-file", type=str, default="")
    args = parser.parse_args()

    file_a = args.file_a_opt or args.file_a
    file_b = args.file_b_opt or args.file_b
    if not file_a or not file_b:
        parser.error("Both dataset paths are required.")

    rows_a = load_runs(file_a)
    rows_b = load_runs(file_b)
    report = compare_datasets(args.label_a, rows_a, args.label_b, rows_b)

    if args.output_file:
        out_path = Path(args.output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.output_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"--- A/B Comparison: {file_a} vs {file_b} ---")
        print(f"Solve Rate: {report['a']['summary']['solve_rate']:.2%} -> {report['b']['summary']['solve_rate']:.2%} ({report['delta']['solve_rate_delta']:+.2%})")
        print(
            f"Semantic Verified Rate: {report['a']['summary']['semantic_verified_rate']:.2%} -> "
            f"{report['b']['summary']['semantic_verified_rate']:.2%} "
            f"({report['delta']['semantic_verified_rate_delta']:+.2%})"
        )
        print(
            f"Avg Duration: {report['a']['summary']['avg_duration_sec']:.2f}s -> "
            f"{report['b']['summary']['avg_duration_sec']:.2f}s "
            f"({report['delta']['avg_duration_sec_delta']:+.2f}s)"
        )
        print(
            f"Avg Wall Duration: {report['a']['summary']['avg_wall_duration_sec']:.2f}s -> "
            f"{report['b']['summary']['avg_wall_duration_sec']:.2f}s "
            f"({report['delta']['avg_wall_duration_sec_delta']:+.2f}s)"
        )
        print(
            f"Avg Tokens: {report['a']['summary']['avg_total_tokens']:.1f} -> "
            f"{report['b']['summary']['avg_total_tokens']:.1f} "
            f"({report['delta']['avg_total_tokens_delta']:+.1f})"
        )
        print(
            f"Trust Mismatch Rate: {report['a']['summary']['trust_mismatch_rate']:.2%} -> "
            f"{report['b']['summary']['trust_mismatch_rate']:.2%} "
            f"({report['delta']['trust_mismatch_rate_delta']:+.2%})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
