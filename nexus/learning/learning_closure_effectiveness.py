from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EffectivenessReport:
    total_entries: int
    improved_count: int
    no_change_count: int
    degraded_count: int
    improvement_rate: float
    details: list[dict[str, Any]] = field(default_factory=list)


def load_learning_closures(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def classify_closure_effectiveness(entry: dict[str, Any]) -> str:
    status = str(entry.get("status", "") or entry.get("writeback_status", "")).lower()
    classification = str(entry.get("classification", "") or entry.get("action", "")).lower()
    if status in ("ok", "success") or "pass" in classification:
        return "improved"
    if status in ("failed_non_blocking", "skipped"):
        return "no_change"
    if status in ("fail", "error", "rejected"):
        return "degraded"
    return "no_change"


def evaluate_effectiveness(entries: list[dict[str, Any]]) -> EffectivenessReport:
    details: list[dict[str, Any]] = []
    improved = 0
    no_change = 0
    degraded = 0
    for entry in entries:
        effect = classify_closure_effectiveness(entry)
        if effect == "improved":
            improved += 1
        elif effect == "degraded":
            degraded += 1
        else:
            no_change += 1
        details.append({
            "effect": effect,
            "classification": entry.get("classification", entry.get("action", "unknown")),
            "task_id": entry.get("task_id", "unknown"),
            "status": entry.get("status", entry.get("writeback_status", "unknown")),
        })
    total = len(entries)
    return EffectivenessReport(
        total_entries=total,
        improved_count=improved,
        no_change_count=no_change,
        degraded_count=degraded,
        improvement_rate=round(improved / total, 4) if total > 0 else 0.0,
        details=details[:50],
    )


def generate_effectiveness_report(entries: list[dict[str, Any]], output_path: Path) -> None:
    report = evaluate_effectiveness(entries)
    lines = [
        f"# Learning Closure Effectiveness Report",
        f"",
        f"**Total entries**: {report.total_entries}",
        f"**Improved**: {report.improved_count}",
        f"**No change**: {report.no_change_count}",
        f"**Degraded**: {report.degraded_count}",
        f"**Improvement rate**: {report.improvement_rate}",
        f"",
        f"## Top 50 Details",
        f"",
    ]
    for d in report.details:
        lines.append(f"- {d['effect']:>10} | {d['classification']:20} | task={d['task_id']:20} | status={d['status']}")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
