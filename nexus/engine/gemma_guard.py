from __future__ import annotations

import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class ClassifierVerdict:
    accepted: bool
    reason: str
    score: float


def median_outlier_rejection(scores: list[float], *, tolerance: float = 0.35) -> ClassifierVerdict:
    if not scores:
        return ClassifierVerdict(False, "classifier_scores_missing", 0.0)
    median = statistics.median(scores)
    for value in scores:
        if abs(value - median) > tolerance:
            return ClassifierVerdict(False, "classifier_outlier_rejected", float(value))
    return ClassifierVerdict(True, "classifier_scores_consistent", float(median))

