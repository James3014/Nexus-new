"""``--strict-llm-baseline`` semantics for the same-model A/B lane (issue #1820).

Legacy ADRs (teacher-student sweep plan, route-cost measurement lessons) require
that a success with ``model_calls == 0`` is not counted as a model solve: it came
from a deterministic/local rescue path. Under strict mode such rows are tagged
``solve_classification="deterministic_rescue"`` and reported separately.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

WITH_NEXUS_MODE = "with_nexus"
WITHOUT_NEXUS_MODE = "without_nexus"
SOLVE_WITHOUT_CAPABILITY = "solve_without_capability"
DETERMINISTIC_RESCUE = "deterministic_rescue"
# A with-Nexus SUCCESS that a model call preceded but Nexus's local path delivered
# (``local_preflight`` / ``local_hidden_shadow`` / ...): not a model solve.
LOCAL_RESCUE = "rescued_by_local"
MODEL_SOLVE = "model_solve"
NOT_SOLVED = "not_solved"
RECEIPT_DATA_CONTRACT_VIOLATION = "receipt_data_contract_violation"
SCORECARD_SCHEMA = "strict_v2_honest_scorecard_v1"


def _model_calls(row: dict[str, Any]) -> int:
    try:
        return int(row.get("model_calls") or 0)
    except (TypeError, ValueError):
        return 0


def local_delivery(row: dict[str, Any]) -> bool:
    """True when Nexus's local/deterministic path, not the model, delivered the result."""

    return row.get("local_success_source") is True or str(
        row.get("nexus_winner_source") or ""
    ).startswith("local")


def receipt_contract_violation(row: dict[str, Any]) -> bool:
    return (
        str(row.get("infra_invalid_reason") or "") == RECEIPT_DATA_CONTRACT_VIOLATION
        or str(row.get("receipt_data_contract_status") or "").lower() == "infra_invalid"
    )


def apply_strict_llm_baseline_classification(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Tag finished rows in place; only a model-delivered SUCCESS is a model solve.

    * SUCCESS with no model call -> ``deterministic_rescue`` (#1820).
    * SUCCESS after a model call but delivered by Nexus's local path -> with-Nexus:
      ``rescued_by_local``; bare arm: ``not_solved`` (the bare arm has no Nexus path, so a
      local delivery there is never credited).
    * A with-Nexus ``receipt_data_contract_violation`` is flagged as a wiring defect.
    """

    for row in rows:
        row["strict_llm_baseline_applied"] = True
        mode = str(row.get("mode", ""))
        row["rescued_by_local"] = False
        if row.get("status") != "SUCCESS":
            row["solve_classification"] = NOT_SOLVED
            row["deterministic_rescue"] = False
        else:
            is_rescue = _model_calls(row) <= 0
            row["deterministic_rescue"] = is_rescue
            if is_rescue:
                row["solve_classification"] = DETERMINISTIC_RESCUE
            elif local_delivery(row):
                if mode == WITH_NEXUS_MODE:
                    row["solve_classification"] = LOCAL_RESCUE
                    row["rescued_by_local"] = True
                else:
                    row["solve_classification"] = NOT_SOLVED
                    row["bare_local_delivery_rejected"] = True
            else:
                row["solve_classification"] = MODEL_SOLVE
        if mode == WITH_NEXUS_MODE and receipt_contract_violation(row):
            row["wiring_defect"] = RECEIPT_DATA_CONTRACT_VIOLATION
        if mode == WITH_NEXUS_MODE:
            classify_row_capabilities(row)
    return rows


def honest_scorecard(rows: Iterable[dict[str, Any]], mode: str) -> dict[str, Any]:
    """Per-arm scorecard over ALL rows of ``mode`` (nothing is dropped from the denominator).

    ``solved_by_model + rescued_by_local + failed == total_n``.  ``rescued_by_local`` is
    always 0 for the bare arm (its deterministic rescues count as failed: no model solve and
    no Nexus).  ``contract_violation`` (with-Nexus receipt data contract violations, a wiring
    defect) and ``infra_invalid`` are reported alongside, not removed.
    """

    arm = [r for r in rows if str(r.get("mode", "")) == mode]
    solved = [r for r in arm if r.get("solve_classification") == MODEL_SOLVE]
    if mode == WITH_NEXUS_MODE:
        rescued = [
            r for r in arm if r.get("solve_classification") in {LOCAL_RESCUE, DETERMINISTIC_RESCUE}
        ]
    else:
        rescued = []
    total = len(arm)
    violations = [r for r in arm if mode == WITH_NEXUS_MODE and receipt_contract_violation(r)]
    return {
        "schema": SCORECARD_SCHEMA,
        "total_n": total,
        "solved_by_model": len(solved),
        "rescued_by_local": len(rescued),
        "failed": total - len(solved) - len(rescued),
        "contract_violation": len(violations),
        "contract_violation_failed": sum(1 for r in violations if r.get("status") != "SUCCESS"),
        "infra_invalid": sum(1 for r in arm if r.get("infra_invalid_reason")),
        "model_solve_rate_all_rows": round(len(solved) / total, 4) if total else None,
        "wiring_defects": sorted({
            str(r.get("wiring_defect")) for r in violations if r.get("wiring_defect")
        }),
    }


def _claim_boundary(receipt: dict[str, Any]) -> dict[str, Any] | None:
    """Return the receipt's claim_boundary mapping, or None when it carries none."""

    base = receipt.get("receipt_base")
    if isinstance(base, dict) and isinstance(base.get("claim_boundary"), dict):
        return base["claim_boundary"]
    if isinstance(receipt.get("claim_boundary"), dict):
        return receipt["claim_boundary"]
    return None


def classify_receipt(receipt: dict[str, Any]) -> str:
    """Return ``real``, ``simulated`` or ``selected_not_invoked`` for one receipt.

    ``real``: invoked, ``claim_boundary.simulated`` is not true, and ``evidence_refs`` is non-empty.
    A receipt that carries no claim_boundary at all (runner-synthesized telemetry backfill or
    deterministic receipt-lite entries) makes no simulated claim; it is counted real only when it
    has evidence refs and is reported under ``capabilities_real_unattested`` so it stays visible.
    ``selected_not_invoked``: selected by the planner but never invoked.
    Everything else invoked (simulated=true, or no evidence) is ``simulated``.
    """

    if not bool(receipt.get("invoked")):
        return "selected_not_invoked"
    boundary = _claim_boundary(receipt)
    simulated = False if boundary is None else boundary.get("simulated", True) is not False
    has_refs = bool([ref for ref in (receipt.get("evidence_refs") or []) if str(ref).strip()])
    return "real" if (not simulated and has_refs) else "simulated"


def classify_row_capabilities(row: dict[str, Any]) -> dict[str, Any]:
    """Split a with-Nexus row's capability receipts; set ``capability_not_exercised`` in place."""

    real: list[str] = []
    unattested: list[str] = []
    simulated: list[str] = []
    not_invoked: list[str] = []
    for receipt in row.get("capability_receipts") or []:
        if not isinstance(receipt, dict) or not receipt.get("selected", True):
            continue
        name = str(receipt.get("name") or "")
        kind = classify_receipt(receipt)
        if kind == "real":
            real.append(name)
            if _claim_boundary(receipt) is None:
                unattested.append(name)
        elif kind == "simulated":
            simulated.append(name)
        else:
            not_invoked.append(name)
    row["capabilities_real"] = sorted(set(real))
    row["capabilities_real_unattested"] = sorted(set(unattested))
    row["capabilities_simulated"] = sorted(set(simulated) - set(real))
    row["capabilities_selected_not_invoked"] = sorted(set(not_invoked) - set(real) - set(simulated))
    row["capability_not_exercised"] = not row["capabilities_real"]
    row["solve_without_capability"] = bool(
        row.get("solve_classification") == MODEL_SOLVE and row["capability_not_exercised"]
    )
    return row


def capability_tally(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Per-capability ``{real, simulated, selected_not_invoked}`` over classified with-Nexus rows."""

    tally: dict[str, dict[str, int]] = {}
    for row in rows:
        for key, field in (
            ("real", "capabilities_real"),
            ("simulated", "capabilities_simulated"),
            ("selected_not_invoked", "capabilities_selected_not_invoked"),
        ):
            for name in row.get(field) or []:
                entry = tally.setdefault(
                    name, {"real": 0, "simulated": 0, "selected_not_invoked": 0}
                )
                entry[key] += 1
    return dict(sorted(tally.items()))


def capability_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Strict capability-exercise figures for the with-Nexus rows of one arm."""

    classified = [r for r in rows if "capability_not_exercised" in r]
    eligible = [r for r in classified if bool(r.get("run_eligible", True))]
    solves = [r for r in eligible if r.get("solve_classification") == MODEL_SOLVE]
    uplift = [r for r in solves if not r["capability_not_exercised"]]
    return {
        "capability_rows_n": len(classified),
        "real_capability_rows_n": sum(1 for r in classified if not r["capability_not_exercised"]),
        "attested_real_capability_rows_n": sum(
            1
            for r in classified
            if set(r.get("capabilities_real") or [])
            - set(r.get("capabilities_real_unattested") or [])
        ),
        "simulated_only_rows_n": sum(
            1
            for r in classified
            if r["capability_not_exercised"] and r.get("capabilities_simulated")
        ),
        "capability_not_exercised_rows_n": sum(
            1 for r in classified if r["capability_not_exercised"]
        ),
        "capability_tally": capability_tally(classified),
        "solves_with_real_capability_n": len(uplift),
        "solve_without_capability_n": len(solves) - len(uplift),
        "nexus_uplift_solved_n": len(uplift),
        "nexus_uplift_solve_rate": round(len(uplift) / len(eligible), 4) if eligible else None,
    }


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
        arm["scorecard"] = honest_scorecard(rows, mode)
        arm["solve_rate"] = round(len(solved) / len(eligible), 4) if eligible else None
        arm["first_pass_rate"] = round(len(first_pass) / len(eligible), 4) if eligible else None
        if mode == WITH_NEXUS_MODE:
            arm.update(
                capability_summary([row for row in rows if str(row.get("mode", "")) == mode])
            )
    return summary


def reclassify_report_dir(report_dir: str | Path) -> dict[str, Any]:
    """Re-read ``*.jsonl`` rows of an existing report dir and compute strict tallies."""

    root = Path(report_dir)
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                if isinstance(row, dict) and "mode" in row:
                    rows.append(row)
    apply_strict_llm_baseline_classification(rows)
    by_mode: dict[str, dict[str, Any]] = {}
    for mode in sorted({str(r.get("mode", "")) for r in rows}):
        by_mode[mode] = {"rows_n": sum(1 for r in rows if str(r.get("mode", "")) == mode)}
    apply_strict_llm_baseline_to_summary(rows, by_mode)
    per_row = [
        {
            "task_id": r.get("task_id"),
            "status": r.get("status"),
            "model_calls": _model_calls(r),
            "solve_classification": r.get("solve_classification"),
            "wiring_defect": r.get("wiring_defect"),
            "capabilities_real": r.get("capabilities_real"),
            "capabilities_real_unattested": r.get("capabilities_real_unattested"),
            "capabilities_simulated": r.get("capabilities_simulated"),
            "capability_not_exercised": r.get("capability_not_exercised"),
        }
        for r in rows
        if str(r.get("mode", "")) == WITH_NEXUS_MODE
    ]
    return {"report_dir": str(root), "arms": by_mode, "with_nexus_rows": per_row}


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Re-read a bench report dir with strict capability tallies."
    )
    parser.add_argument("--reclassify", metavar="REPORT_DIR", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(reclassify_report_dir(args.reclassify), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
