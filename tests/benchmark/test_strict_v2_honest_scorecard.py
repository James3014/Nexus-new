"""Online A/B gap B: strict-v2 scoring must not credit local rescues or drop wiring defects."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.bench.capability_ab_runner import _summarize_with_strict_baseline
from scripts.bench.gemini_nexus_report import _strict_scorecard_lines
from scripts.bench.strict_llm_baseline import (
    LOCAL_RESCUE,
    MODEL_SOLVE,
    NOT_SOLVED,
    RECEIPT_DATA_CONTRACT_VIOLATION,
    apply_strict_llm_baseline_classification,
    honest_scorecard,
    reclassify_report_dir,
)


def _row(mode: str, task: str, status: str, model_calls: int, **extra: Any) -> dict[str, Any]:
    return {
        "mode": mode,
        "task_id": task,
        "status": status,
        "model_calls": model_calls,
        "run_eligible": True,
        **extra,
    }


def _dry_run_like_rows() -> list[dict[str, Any]]:
    """Shapes observed in the 2026-10-13 zero-model dry run (fake agy, empty patch)."""

    return [
        # fake model returned an empty patch, Nexus's local preflight delivered the fix
        _row("with_nexus", "context-001", "SUCCESS", 1, nexus_winner_source="local_preflight"),
        _row("with_nexus", "context-002", "SUCCESS", 2, nexus_winner_source="local_hidden_shadow"),
        _row(
            "with_nexus",
            "repair-001",
            "SUCCESS",
            1,
            local_success_source=True,
            nexus_winner_source="llm",
        ),
        # failed candidate -> claim/delivery gates fail -> receipt data contract violation
        _row(
            "with_nexus",
            "gov-001",
            "FAILED",
            1,
            run_eligible=False,
            infra_invalid_reason=RECEIPT_DATA_CONTRACT_VIOLATION,
            receipt_data_contract_status="infra_invalid",
        ),
        _row("with_nexus", "gov-002", "SUCCESS", 1, nexus_winner_source="nexus_llm_baseline"),
        _row(
            "with_nexus",
            "rescue-0",
            "SUCCESS",
            0,
            nexus_winner_source="local_hidden_contract_fast_path",
        ),
        # bare arm: a model solve, a local-looking delivery (never credited), an infra row
        _row("without_nexus", "context-001", "SUCCESS", 1, nexus_winner_source="direct_agy"),
        _row("without_nexus", "context-002", "SUCCESS", 1, local_success_source=True),
        _row(
            "without_nexus",
            "gov-001",
            "FAILED",
            1,
            run_eligible=False,
            infra_invalid_reason="model_identity_unobserved",
        ),
        _row("without_nexus", "rescue-0", "SUCCESS", 0),
    ]


def test_local_delivery_after_model_call_is_rescued_by_local_not_model_solve() -> None:
    rows = apply_strict_llm_baseline_classification(_dry_run_like_rows())
    by = {(r["mode"], r["task_id"]): r for r in rows}

    for task in ("context-001", "context-002", "repair-001"):
        assert by[("with_nexus", task)]["solve_classification"] == LOCAL_RESCUE
        assert by[("with_nexus", task)]["rescued_by_local"] is True
    assert by[("with_nexus", "gov-002")]["solve_classification"] == MODEL_SOLVE
    assert by[("with_nexus", "rescue-0")]["solve_classification"] == "deterministic_rescue"


def test_bare_arm_never_gets_local_rescue_credit() -> None:
    rows = apply_strict_llm_baseline_classification(_dry_run_like_rows())
    bare = {r["task_id"]: r for r in rows if r["mode"] == "without_nexus"}

    assert bare["context-002"]["solve_classification"] == NOT_SOLVED
    assert bare["context-002"]["bare_local_delivery_rejected"] is True
    assert bare["context-001"]["solve_classification"] == MODEL_SOLVE
    card = honest_scorecard(rows, "without_nexus")
    assert card["rescued_by_local"] == 0
    assert card == {
        **card,
        "total_n": 4,
        "solved_by_model": 1,
        "failed": 3,
        "infra_invalid": 1,
        "contract_violation": 0,
    }


def test_contract_violation_counts_as_failure_and_wiring_defect() -> None:
    rows = _dry_run_like_rows()
    summary = _summarize_with_strict_baseline(rows, strict=True)
    card = summary["with_nexus"]["scorecard"]

    # denominator is every with-Nexus row, including the run_eligible=False violation
    assert card["total_n"] == 6
    assert card["solved_by_model"] == 1
    assert card["rescued_by_local"] == 4
    assert card["failed"] == 1
    assert card["contract_violation"] == 1
    assert card["contract_violation_failed"] == 1
    assert card["wiring_defects"] == [RECEIPT_DATA_CONTRACT_VIOLATION]
    assert card["model_solve_rate_all_rows"] == round(1 / 6, 4)
    assert card["solved_by_model"] + card["rescued_by_local"] + card["failed"] == card["total_n"]
    violation = next(r for r in rows if r["task_id"] == "gov-001" and r["mode"] == "with_nexus")
    assert violation["wiring_defect"] == RECEIPT_DATA_CONTRACT_VIOLATION
    # legacy eligible-denominator fields stay available but no longer stand alone
    assert summary["with_nexus"]["solved_n"] == 1


def test_reclassify_report_dir_and_markdown_carry_scorecard(tmp_path: Path) -> None:
    rows = _dry_run_like_rows()
    for mode in ("with_nexus", "without_nexus"):
        (tmp_path / f"{mode}_1.jsonl").write_text(
            "\n".join(json.dumps(r) for r in rows if r["mode"] == mode) + "\n", encoding="utf-8"
        )
    result = reclassify_report_dir(tmp_path)
    assert result["arms"]["with_nexus"]["scorecard"]["rescued_by_local"] == 4
    assert result["arms"]["without_nexus"]["scorecard"]["rescued_by_local"] == 0

    classified = apply_strict_llm_baseline_classification(_dry_run_like_rows())
    lines = _strict_scorecard_lines(
        [r for r in classified if r["mode"] == "without_nexus"],
        [r for r in classified if r["mode"] == "with_nexus"],
    )
    assert lines[0].startswith("## Strict-v2 Honest Scorecard")
    assert "| With Nexus | 6 | 1 | 4 | 1 | 1 | 1 |" in lines
    assert "| Without Nexus | 4 | 1 | 0 | 3 | 0 | 1 |" in lines
    assert _strict_scorecard_lines([{"mode": "with_nexus"}], []) == []
