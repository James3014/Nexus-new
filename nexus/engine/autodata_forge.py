from __future__ import annotations

from dataclasses import dataclass, asdict


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
