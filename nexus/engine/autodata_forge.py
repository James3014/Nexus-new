from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
from typing import Any


GOLD_GAP_THRESHOLD = 0.20


@dataclass(frozen=True)
class DataForgeLabel:
    """Deterministic label for high-value self-instruct trajectories."""

    label: str
    strong_score: float
    weak_score: float
    gap: float
    audit_passed: bool
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DataForgeManifestRow:
    task_id: str
    label: DataForgeLabel
    evidence_refs: tuple[str, ...] = ()
    trajectory_step_count: int = 0
    hard_negative: bool = False
    low_step_filter: dict[str, Any] | None = None

    def to_dict(self) -> dict:
        low_step_filter = dict(self.low_step_filter or {})
        filtered = bool(low_step_filter.get("filtered", self.trajectory_step_count < 10))
        low_step_filter.setdefault("filtered", filtered)
        low_step_filter.setdefault("min_steps", 10)
        return {
            "schema_version": "nexus_autodata_forge_row.v1",
            "task_id": self.task_id,
            "label": self.label.to_dict(),
            "evidence_refs": list(self.evidence_refs),
            "trajectory_step_count": self.trajectory_step_count,
            "hard_negative": bool(self.hard_negative),
            "low_step_filter": low_step_filter,
            "eligible_for_training": self.label.label == "GOLD" and not self.hard_negative and not filtered,
        }


def classify_trajectory_quality(
    *,
    strong_score: float,
    weak_score: float,
    audit_passed: bool,
    gold_gap_threshold: float = GOLD_GAP_THRESHOLD,
) -> DataForgeLabel:
    """Mark a trajectory GOLD only when it is both discriminative and audited."""
    strong = max(0.0, min(1.0, float(strong_score)))
    weak = max(0.0, min(1.0, float(weak_score)))
    threshold = max(0.0, min(1.0, float(gold_gap_threshold)))
    gap = round(strong - weak, 4)
    if not audit_passed:
        label = "REJECTED"
        reason = "audit_failed"
    elif gap >= threshold:
        label = "GOLD"
        reason = "strong_weak_gap_passed"
    else:
        label = "SILVER"
        reason = "strong_weak_gap_below_threshold"
    return DataForgeLabel(
        label=label,
        strong_score=strong,
        weak_score=weak,
        gap=gap,
        audit_passed=bool(audit_passed),
        reason=reason,
    )


def write_data_forge_manifest(path: str | Path, rows: list[DataForgeManifestRow]) -> dict:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "nexus_autodata_forge_manifest.v1",
        "rows": [row.to_dict() for row in rows],
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "schema_version": "nexus_autodata_forge_manifest_write.v1",
        "path": str(target),
        "row_count": len(rows),
        "gold_count": sum(1 for row in rows if row.label.label == "GOLD"),
        "training_eligible_count": sum(1 for row in rows if row.to_dict()["eligible_for_training"]),
    }


def validate_hard_trajectory_pool(rows: list[DataForgeManifestRow], *, min_rows: int = 2) -> dict[str, Any]:
    failures: list[str] = []
    if len(rows) < min_rows:
        failures.append("insufficient_hard_trajectory_rows")
    if not any(row.hard_negative for row in rows):
        failures.append("hard_negative_missing")
    if not any(row.to_dict()["eligible_for_training"] for row in rows):
        failures.append("training_eligible_gold_missing")
    if any(not row.evidence_refs for row in rows):
        failures.append("trajectory_missing_evidence_refs")
    return {
        "schema_version": "nexus_hard_trajectory_pool.v1",
        "passed": not failures,
        "row_count": len(rows),
        "failures": failures,
    }
