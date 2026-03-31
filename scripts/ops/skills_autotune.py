#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SkillStat:
    count: int = 0
    score_sum: float = 0.0
    phase_health_sum: float = 0.0
    phase_health_count: int = 0

    def add(self, score: float, phase_health: float | None) -> None:
        self.count += 1
        self.score_sum += score
        if phase_health is not None:
            self.phase_health_sum += phase_health
            self.phase_health_count += 1

    @property
    def avg_score(self) -> float:
        return (self.score_sum / self.count) if self.count else 0.0

    @property
    def avg_phase_health(self) -> float | None:
        if not self.phase_health_count:
            return None
        return self.phase_health_sum / self.phase_health_count


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


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


def _discover_decision_logs(project_root: Path) -> list[Path]:
    logs: list[Path] = []
    root_log = project_root / "scripts" / "core" / "router_decisions.jsonl"
    if root_log.exists():
        logs.append(root_log)
    run_logs = sorted((project_root / ".nexus" / "runs").glob("**/router_decisions.jsonl"))
    logs.extend(run_logs)
    return logs


def _discover_phase_metrics(project_root: Path) -> list[Path]:
    return sorted((project_root / ".nexus").glob("**/phase_metrics/*_metrics.json"))


def _discover_outcome_logs(project_root: Path) -> list[Path]:
    logs: list[Path] = []
    root_log = project_root / ".nexus" / "metrics" / "skill_outcome_events.jsonl"
    if root_log.exists():
        logs.append(root_log)
    run_logs = sorted((project_root / ".nexus" / "runs").glob("**/skill_outcome_events.jsonl"))
    logs.extend(run_logs)
    return logs


def _build_phase_health_lookup(project_root: Path) -> dict[str, dict[str, float]]:
    lookup: dict[str, dict[str, float]] = {}
    for metrics_file in _discover_phase_metrics(project_root):
        payload = _load_json(metrics_file)
        task_id = str(payload.get("task_id", ""))
        phase_metrics = payload.get("metrics", {}) or {}
        if not task_id:
            continue
        phase_health: dict[str, float] = {}
        for phase, detail in phase_metrics.items():
            health = detail.get("health")
            if isinstance(health, (int, float)):
                phase_health[str(phase)] = float(health)
        if phase_health:
            lookup[task_id] = phase_health
    return lookup


def _phase_health_for_decision(
    decision: dict[str, Any],
    phase_health_by_task: dict[str, dict[str, float]],
) -> float | None:
    phase = str(decision.get("phase", "")).strip()
    if not phase:
        return None

    # Best-effort lookup by task id if available in future schema.
    task_id = str(decision.get("task_id", "")).strip()
    if task_id and task_id in phase_health_by_task:
        return phase_health_by_task[task_id].get(phase)
    return None


def run_autotune(
    project_root: Path,
    apply: bool,
    min_samples: int,
    baseline: float,
    learning_rate: float,
    degrade_threshold: float,
    max_step: float,
    degrade_consecutive_rounds: int,
    include_sources: list[str] | None = None,
) -> int:
    if include_sources is None:
        include_sources = ["pipeline.crystallize"]

    weights_path = project_root / "scripts" / "core" / "autonomic_weights.json"
    weights = _load_json(weights_path)
    if not weights:
        weights = {"base_weights": {}, "skill_adjustments": {}}
    skill_adjustments = dict(weights.get("skill_adjustments", {}) or {})

    decision_logs = _discover_decision_logs(project_root)
    if not decision_logs:
        print("⚠️ [skills:autotune] No router decision logs found.")
        return 1

    outcome_logs = _discover_outcome_logs(project_root)
    phase_health_by_task = _build_phase_health_lookup(project_root)
    stats: dict[str, SkillStat] = defaultdict(SkillStat)
    decision_skill_map: dict[str, str] = {}
    skill_decision_order: dict[str, list[str]] = defaultdict(list)

    total_rows = 0
    for log_path in decision_logs:
        for row in _load_jsonl(log_path):
            total_rows += 1
            skill_id = str(row.get("selected_skill", "")).strip()
            decision_id = str(row.get("decision_id", "")).strip()
            if not skill_id or skill_id == "NONE":
                continue
            if decision_id:
                decision_skill_map[decision_id] = skill_id
                skill_decision_order[skill_id].append(decision_id)
            score = float(row.get("score") or 0.0)
            phase_health = _phase_health_for_decision(row, phase_health_by_task)
            stats[skill_id].add(score=score, phase_health=phase_health)

    outcome_events: list[dict[str, Any]] = []
    for log_path in outcome_logs:
        outcome_events.extend(_load_jsonl(log_path))

    true_stats: dict[str, list[float]] = defaultdict(list)
    event_counts: dict[str, int] = defaultdict(int)
    negative_streak: dict[str, int] = defaultdict(int)
    
    # Audit counters
    total_events_seen = 0
    events_used_for_learning = 0
    events_excluded_by_source = 0
    neutralized_phantom_events = 0

    for event in outcome_events:
        total_events_seen += 1
        source = event.get("source", "unknown")
        if source not in include_sources:
            events_excluded_by_source += 1
            continue

        decision_id = str(event.get("decision_id", "")).strip()
        skill_id = str(event.get("skill_id", "")).strip()
        mapped_skill = decision_skill_map.get(decision_id, "")
        if mapped_skill:
            skill_id = mapped_skill
        if not skill_id:
            continue
        
        events_used_for_learning += 1
        quality_pass = 1.0 if bool(event.get("pass", False)) else 0.0
        
        # Reward Recalibration: Neutralized phantom events don't get penalized
        phantom_blocked = bool(event.get("phantom_blocked", False))
        is_neutralized = bool(event.get("neutralized", False))
        
        if phantom_blocked and is_neutralized:
            phantom_penalty = 0.0
            neutralized_phantom_events += 1
        else:
            phantom_penalty = 1.0 if phantom_blocked else 0.0
            
        retry_penalty = min(1.0, float(event.get("retry_count", 0.0) or 0.0) / 3.0)
        repair_success = 1.0 if bool(event.get("repair_success", False)) else 0.0
        proof_bonus = 0.2 if bool(event.get("proof_present", False)) else 0.0
        stability_bonus = min(1.0, float(event.get("regression_pass_rate", 0.0) or 0.0) / 100.0) * 0.5
        learning_gain = (
            min(1.0, float(event.get("pattern_reuse", 0.0) or 0.0) / 100.0) * 0.2
            + min(1.0, float(event.get("next_run_hit", 0.0) or 0.0) / 100.0) * 0.2
        )
        reward = quality_pass - phantom_penalty - retry_penalty + stability_bonus + (repair_success * 0.3) + proof_bonus + learning_gain
        reward = max(-1.5, min(1.8, reward))
        true_stats[skill_id].append(reward)
        event_counts[skill_id] += 1
        if reward < baseline:
            negative_streak[skill_id] += 1
        else:
            negative_streak[skill_id] = 0

    suggestions: dict[str, dict[str, float | int | None]] = {}
    degraded_queue: list[dict[str, Any]] = []
    used_true_outcome = False
    for skill_id, stat in stats.items():
        if stat.count < min_samples:
            continue
        if len(true_stats.get(skill_id, [])) >= min_samples:
            used_true_outcome = True
            proxy_outcome = sum(true_stats[skill_id]) / len(true_stats[skill_id])
        else:
            # proxy_outcome combines phase-health (if available) and route score confidence
            health_proxy = (stat.avg_phase_health / 100.0) if stat.avg_phase_health is not None else 0.5
            score_proxy = min(1.0, stat.avg_score / 10.0)
            proxy_outcome = 0.7 * health_proxy + 0.3 * score_proxy

        # damped update to avoid unstable jumps
        delta = learning_rate * (proxy_outcome - baseline) * math.log1p(stat.count) * 2.0
        if delta > max_step:
            delta = max_step
        elif delta < -max_step:
            delta = -max_step
        current = float(skill_adjustments.get(skill_id, 0.0))
        proposed = max(-3.0, min(8.0, current + delta))
        suggestions[skill_id] = {
            "count": stat.count,
            "event_count": event_counts.get(skill_id, 0),
            "avg_score": round(stat.avg_score, 4),
            "avg_phase_health": round(stat.avg_phase_health, 4) if stat.avg_phase_health is not None else None,
            "proxy_outcome": round(proxy_outcome, 4),
            "mode": "true_outcome" if len(true_stats.get(skill_id, [])) >= min_samples else "proxy",
            "current": round(current, 4),
            "delta": round(delta, 4),
            "proposed": round(proposed, 4),
        }
        drop_amount = current - proposed
        if drop_amount >= degrade_threshold and negative_streak.get(skill_id, 0) >= degrade_consecutive_rounds:
            degraded_queue.append(
                {
                    "skill_id": skill_id,
                    "drop": round(drop_amount, 4),
                    "current": round(current, 4),
                    "proposed": round(proposed, 4),
                    "negative_streak": int(negative_streak.get(skill_id, 0)),
                    "handler_skill": "skill-creator-advanced",
                    "objective": "Improve trigger precision and output contract to recover routing confidence.",
                    "skill_path_builtin": str(
                        project_root / "scripts" / "skills_builtin" / skill_id / "SKILL.md"
                    ),
                    "inventory_path": str(project_root / "scripts" / "skills_inventory.json"),
                }
            )

    report = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "decision_logs": [str(p) for p in decision_logs],
        "outcome_logs": [str(p) for p in outcome_logs],
        "total_rows": total_rows,
        "skill_count": len(stats),
        "tuned_skill_count": len(suggestions),
        "baseline": baseline,
        "learning_rate": learning_rate,
        "min_samples": min_samples,
        "degrade_threshold": degrade_threshold,
        "max_step": max_step,
        "degrade_consecutive_rounds": degrade_consecutive_rounds,
        "reward_mode": "true_outcome" if used_true_outcome else "proxy",
        "governance": {
            "included_sources": include_sources,
            "total_events_seen": total_events_seen,
            "events_used_for_learning": events_used_for_learning,
            "events_excluded_by_source": events_excluded_by_source,
            "neutralized_phantom_events": neutralized_phantom_events,
        },
        "suggestions": suggestions,
        "degraded_skills": degraded_queue,
        "applied": apply,
    }

    report_path = project_root / ".nexus" / "metrics" / "skills_autotune_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    queue_path = project_root / ".nexus" / "metrics" / "skills_optimization_queue.json"
    queue_path.write_text(
        json.dumps(
            {
                "timestamp": report["timestamp"],
                "source_report": str(report_path),
                "handler_skill": "skill-creator-advanced",
                "items": degraded_queue,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    if apply:
        for skill_id, item in suggestions.items():
            skill_adjustments[skill_id] = item["proposed"]
        weights["skill_adjustments"] = skill_adjustments
        weights["last_updated"] = __import__("datetime").datetime.now().isoformat()
        weights["total_sessions_analyzed"] = int(weights.get("total_sessions_analyzed", 0)) + 1
        weights_path.write_text(json.dumps(weights, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ [skills:autotune] report: {report_path}")
    print(f"  - decision rows: {total_rows}")
    print(f"  - tuned skills: {len(suggestions)}")
    print(f"  - events excluded (source): {events_excluded_by_source}")
    print(f"  - neutralized phantom events: {neutralized_phantom_events}")
    print(f"  - apply: {apply}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Nexus skill auto-tuning helper.")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--min-samples", type=int, default=3)
    parser.add_argument("--baseline", type=float, default=0.55)
    parser.add_argument("--learning-rate", type=float, default=0.6)
    parser.add_argument("--degrade-threshold", type=float, default=0.2)
    parser.add_argument("--max-step", type=float, default=0.20)
    parser.add_argument("--degrade-consecutive-rounds", type=int, default=3)
    parser.add_argument("--include-sources", help="Comma-separated sources to include (default: pipeline.crystallize)")
    args = parser.parse_args()

    include_sources = None
    if args.include_sources:
        include_sources = [s.strip() for s in args.include_sources.split(",")]

    return run_autotune(
        project_root=Path(args.project_root),
        apply=bool(args.apply),
        min_samples=int(args.min_samples),
        baseline=float(args.baseline),
        learning_rate=float(args.learning_rate),
        degrade_threshold=float(args.degrade_threshold),
        max_step=float(args.max_step),
        degrade_consecutive_rounds=int(args.degrade_consecutive_rounds),
        include_sources=include_sources,
    )


if __name__ == "__main__":
    raise SystemExit(main())
