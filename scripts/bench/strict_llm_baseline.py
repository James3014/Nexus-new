"""``--strict-llm-baseline`` semantics for the same-model A/B lane (issue #1820).

Legacy ADRs (teacher-student sweep plan, route-cost measurement lessons) require
that a success with ``model_calls == 0`` is not counted as a model solve: it came
from a deterministic/local rescue path. Under strict mode such rows are tagged
``solve_classification="deterministic_rescue"`` and reported separately.
"""

from __future__ import annotations

from typing import Any

DETERMINISTIC_RESCUE = "deterministic_rescue"
MODEL_SOLVE = "model_solve"
NOT_SOLVED = "not_solved"


def _model_calls(row: dict[str, Any]) -> int:
    try:
        return int(row.get("model_calls") or 0)
    except (TypeError, ValueError):
        return 0


def apply_strict_llm_baseline_classification(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Tag finished rows in place; a SUCCESS with no model call is a rescue."""

    for row in rows:
        row["strict_llm_baseline_applied"] = True
        if row.get("status") != "SUCCESS":
            row["solve_classification"] = NOT_SOLVED
            row["deterministic_rescue"] = False
            continue
        is_rescue = _model_calls(row) <= 0
        row["deterministic_rescue"] = is_rescue
        row["solve_classification"] = DETERMINISTIC_RESCUE if is_rescue else MODEL_SOLVE
    return rows


def apply_strict_llm_baseline_to_summary(
    rows: list[dict[str, Any]],
    summary: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Recompute solve counts per arm so deterministic rescues are not solves."""

    for mode, arm in summary.items():
        eligible = [
            row
            for row in rows
            if str(row.get("mode", "")) == mode and bool(row.get("run_eligible", True))
        ]
        solved = [row for row in eligible if row.get("solve_classification") == MODEL_SOLVE]
        first_pass = [row for row in solved if int(row.get("attempt_count", 0) or 0) <= 1]
        arm["strict_llm_baseline_applied"] = True
        arm["solved_n"] = len(solved)
        arm["deterministic_rescue_n"] = sum(
            1 for row in eligible if row.get("deterministic_rescue") is True
        )
        arm["solve_rate"] = round(len(solved) / len(eligible), 4) if eligible else None
        arm["first_pass_rate"] = round(len(first_pass) / len(eligible), 4) if eligible else None
    return summary
