from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidenceBundleRowSets:
    rows: list[dict[str, Any]]
    with_rows: list[dict[str, Any]]
    without_rows: list[dict[str, Any]]
    eligible_with: list[dict[str, Any]]
    eligible_without: list[dict[str, Any]]
    same_task_trials: bool
    row_counts: dict[str, int]


def build_evidence_bundle_row_sets(rows: list[dict[str, Any]]) -> EvidenceBundleRowSets:
    with_rows = [row for row in rows if str(row.get("mode")) == "with_nexus"]
    without_rows = [row for row in rows if str(row.get("mode")) == "without_nexus"]
    eligible_with = [row for row in with_rows if bool(row.get("run_eligible", True))]
    eligible_without = [row for row in without_rows if bool(row.get("run_eligible", True))]
    return EvidenceBundleRowSets(
        rows=rows,
        with_rows=with_rows,
        without_rows=without_rows,
        eligible_with=eligible_with,
        eligible_without=eligible_without,
        same_task_trials=row_key_counts(with_rows) == row_key_counts(without_rows),
        row_counts={
            "with_nexus": len(with_rows),
            "without_nexus": len(without_rows),
            "total": len(rows),
            "eligible_with_nexus": len(eligible_with),
            "eligible_without_nexus": len(eligible_without),
            "infra_invalid_with_nexus": len(with_rows) - len(eligible_with),
            "infra_invalid_without_nexus": len(without_rows) - len(eligible_without),
        },
    )


def row_key_counts(rows: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (str(row.get("task_id") or ""), str(row.get("trial_index") or "1"))
        counts[key] = counts.get(key, 0) + 1
    return counts
