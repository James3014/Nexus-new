from __future__ import annotations

from typing import Any


def mean_number(source_rows: list[dict[str, Any]], *keys: str) -> float:
    values: list[float] = []
    for row in source_rows:
        for key in keys:
            value = row.get(key)
            if value in (None, ""):
                continue
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                pass
            break
    return round(sum(values) / len(values), 4) if values else 0.0


def safe_ratio(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator > 0 else 0.0


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[mid], 4)
    return round((ordered[mid - 1] + ordered[mid]) / 2, 4)


def paired_metric_ratios(
    with_rows: list[dict[str, Any]],
    without_rows: list[dict[str, Any]],
    metric_key: str,
) -> list[float]:
    with_by_key = {
        (str(row.get("task_id") or ""), str(row.get("trial_index") or "")): row
        for row in with_rows
    }
    ratios: list[float] = []
    for row in without_rows:
        key = (str(row.get("task_id") or ""), str(row.get("trial_index") or ""))
        with_row = with_by_key.get(key)
        if not with_row:
            continue
        numerator = mean_number([with_row], metric_key)
        denominator = mean_number([row], metric_key)
        if numerator > 0 and denominator > 0:
            ratios.append(safe_ratio(numerator, denominator))
    return ratios
