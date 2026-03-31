#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _find_latest_phase7_loop_report(workspace: Path | None) -> Path | None:
    if workspace is None or not workspace.exists():
        return None
    candidates = sorted(workspace.glob("*_final_report_cn.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def build_skills_health(project_root: Path, workspace: Path | None = None) -> dict[str, Any]:
    weights_path = project_root / "scripts" / "core" / "autonomic_weights.json"
    report_path = project_root / ".nexus" / "metrics" / "skills_autotune_report.json"
    queue_path = project_root / ".nexus" / "metrics" / "skills_optimization_queue.json"
    baseline_path = project_root / ".nexus" / "archive" / "baselines" / "acceptance_check_recovery_sprint_pass.json"

    weights = _load_json(weights_path)
    report = _load_json(report_path)
    queue = _load_json(queue_path)
    baseline_payload = _load_json(baseline_path)
    
    adjustments = dict(weights.get("skill_adjustments", {}) or {})
    suggestions = dict(report.get("suggestions", {}) or {})
    queue_items = list(queue.get("items", []) or [])

    sorted_adjustments = sorted(adjustments.items(), key=lambda item: float(item[1]), reverse=True)
    top_boosted = [{"skill_id": skill, "adjustment": round(float(score), 4)} for skill, score in sorted_adjustments[:5]]
    top_suppressed = [
        {"skill_id": skill, "adjustment": round(float(score), 4)}
        for skill, score in sorted(adjustments.items(), key=lambda item: float(item[1]))[:5]
    ]

    max_abs_delta = 0.0
    if suggestions:
        max_abs_delta = max(abs(float(item.get("delta", 0.0))) for item in suggestions.values())

    latest_phase7_loop = _find_latest_phase7_loop_report(workspace)
    phase7_payload = _load_json(latest_phase7_loop) if latest_phase7_loop else {}
    phase7_converged = bool(phase7_payload.get("converged", False)) if phase7_payload else None

    outcome_log = project_root / ".nexus" / "metrics" / "skill_outcome_events.jsonl"
    outcome_rows = _load_jsonl(outcome_log)
    last_rows = outcome_rows[-200:] if outcome_rows else []
    by_skill: dict[str, dict[str, float]] = {}
    for row in last_rows:
        skill = str(row.get("skill_id", "")).strip()
        if not skill:
            continue
        bucket = by_skill.setdefault(
            skill,
            {
                "count": 0.0,
                "pass_count": 0.0,
                "phantom_count": 0.0,
                "neutralized_count": 0.0,
                "retry_sum": 0.0,
                "pattern_sum": 0.0,
                "next_hit_sum": 0.0,
            },
        )
        bucket["count"] += 1.0
        bucket["pass_count"] += 1.0 if bool(row.get("pass", False)) else 0.0
        
        phantom_blocked = bool(row.get("phantom_blocked", False))
        bucket["phantom_count"] += 1.0 if phantom_blocked else 0.0
        bucket["neutralized_count"] += 1.0 if (phantom_blocked and bool(row.get("neutralized", False))) else 0.0
        
        bucket["retry_sum"] += float(row.get("retry_count", 0.0) or 0.0)
        bucket["pattern_sum"] += float(row.get("pattern_reuse", 0.0) or 0.0)
        bucket["next_hit_sum"] += float(row.get("next_run_hit", 0.0) or 0.0)

    top_skill = None
    if by_skill:
        top_skill = sorted(
            by_skill.items(),
            key=lambda item: (
                -(item[1]["pass_count"] / max(1.0, item[1]["count"])),
                -(item[1]["count"]),
            ),
        )[0][0]
        
    if top_skill:
        skill_row = by_skill[top_skill]
        c = max(1.0, skill_row["count"])
        phantom_risk = round((skill_row["phantom_count"] / c) * 100.0, 2)
        effective_phantom_risk = round(((skill_row["phantom_count"] - skill_row["neutralized_count"]) / c) * 100.0, 2)
        healing_efficiency = round(
            ((skill_row["pass_count"] / c) * 100.0) - min(25.0, skill_row["retry_sum"] / c * 10.0),
            2,
        )
        learning_gain = round(((skill_row["pattern_sum"] / c) * 0.5) + ((skill_row["next_hit_sum"] / c) * 0.5), 2)
    else:
        fallback_top = top_boosted[0]["skill_id"] if top_boosted else None
        top_skill = fallback_top
        phantom_risk = 0.0
        effective_phantom_risk = 0.0
        healing_efficiency = 0.0
        learning_gain = 0.0

    max_drop = 0.0
    max_drop_skill = None
    for skill, item in suggestions.items():
        drop = float(item.get("current", 0.0)) - float(item.get("proposed", 0.0))
        if drop > max_drop:
            max_drop = drop
            max_drop_skill = skill

    readiness = {
        "weights_loaded": bool(adjustments),
        "autotune_has_suggestions": bool(suggestions),
        "optimization_queue_empty": len(queue_items) == 0,
        "phase7_loop_converged": phase7_converged,
    }
    ready_for_formal_use = (
        readiness["weights_loaded"]
        and readiness["autotune_has_suggestions"]
        and readiness["optimization_queue_empty"]
        and (phase7_converged is not False)
    )

    return {
        "timestamp": datetime.now().isoformat(),
        "project_root": str(project_root),
        "workspace": str(workspace) if workspace else None,
        "weights_path": str(weights_path),
        "autotune_report_path": str(report_path),
        "optimization_queue_path": str(queue_path),
        "governance_baseline_ref": baseline_payload.get("timestamp", "unknown"),
        "latest_phase7_loop_report": str(latest_phase7_loop) if latest_phase7_loop else None,
        "summary": {
            "skill_adjustment_count": len(adjustments),
            "tuned_skill_count": int(report.get("tuned_skill_count", 0) or 0),
            "queue_count": len(queue_items),
            "max_abs_delta": round(float(max_abs_delta), 4),
            "total_rows": int(report.get("total_rows", 0) or 0),
            "top_skill": top_skill,
            "drop_risk": {
                "skill_id": max_drop_skill,
                "value": round(max_drop, 4),
            },
            "phantom_risk": phantom_risk,
            "effective_phantom_risk": effective_phantom_risk,
            "healing_efficiency": healing_efficiency,
            "learning_gain": learning_gain,
        },
        "top_boosted": top_boosted,
        "top_suppressed": top_suppressed,
        "queue_preview": queue_items[:5],
        "readiness": readiness,
        "ready_for_formal_use": ready_for_formal_use,
        "outcome_log_path": str(outcome_log),
        "outcome_rows_used": len(last_rows),
    }


def _print_text(payload: dict[str, Any]) -> None:
    summary = payload["summary"]
    print("Nexus Skills Health")
    print(f"- project_root: {payload['project_root']}")
    print(f"- governance_baseline: {payload.get('governance_baseline_ref')}")
    if payload.get("workspace"):
        print(f"- workspace: {payload['workspace']}")
    print(f"- tuned_skill_count: {summary['tuned_skill_count']}")
    print(f"- skill_adjustment_count: {summary['skill_adjustment_count']}")
    print(f"- queue_count: {summary['queue_count']}")
    print(f"- max_abs_delta: {summary['max_abs_delta']}")
    print(f"- total_rows: {summary['total_rows']}")
    print(f"- top_skill: {summary.get('top_skill')}")
    drop_risk = summary.get("drop_risk") or {}
    print(f"- drop_risk: {drop_risk.get('skill_id')}:{drop_risk.get('value')}")
    print(f"- phantom_risk: {summary.get('phantom_risk')}")
    print(f"- effective_phantom_risk: {summary.get('effective_phantom_risk')}")
    print(f"- healing_efficiency: {summary.get('healing_efficiency')}")
    print(f"- learning_gain: {summary.get('learning_gain')}")
    print(f"- ready_for_formal_use: {str(payload['ready_for_formal_use']).lower()}")
    print("- readiness:")
    for key, value in payload["readiness"].items():
        print(f"  - {key}: {str(value).lower() if isinstance(value, bool) else value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Nexus skills health summary.")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--workspace", default=None, help="Optional phase7 workspace for final report check.")
    parser.add_argument("--output", choices=["text", "json"], default="text")
    args = parser.parse_args()

    project_root = Path(args.project_root)
    workspace = Path(args.workspace) if args.workspace else None
    payload = build_skills_health(project_root=project_root, workspace=workspace)
    if args.output == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_text(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
