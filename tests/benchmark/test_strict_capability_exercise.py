"""Strict mode v2: simulated capability receipts do not count as exercised (issue #1856)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.bench.capability_ab_runner import _summarize_with_strict_baseline
from scripts.bench.strict_llm_baseline import (
    classify_receipt,
    reclassify_report_dir,
)
from scripts.bench.strict_llm_baseline import (
    main as reclassify_main,
)


def _receipt(
    name: str, *, simulated: bool | None, invoked: bool = True, refs: tuple[str, ...] = ("ref:1",)
) -> dict[str, Any]:
    receipt: dict[str, Any] = {
        "name": name,
        "selected": True,
        "invoked": invoked,
        "evidence_refs": list(refs),
    }
    if simulated is not None:
        receipt["receipt_base"] = {"claim_boundary": {"simulated": simulated}}
    return receipt


def _row(
    mode: str,
    task: str,
    receipts: list[dict[str, Any]],
    *,
    status: str = "SUCCESS",
    model_calls: int = 1,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "task_id": task,
        "status": status,
        "model_calls": model_calls,
        "run_eligible": True,
        "attempt_count": 1,
        "capability_receipts": receipts,
    }


def _rows() -> list[dict[str, Any]]:
    return [
        _row("with_nexus", "real", [_receipt("hyper", simulated=False)]),
        _row(
            "with_nexus",
            "sim",
            [_receipt("codeintel", simulated=True), _receipt("claim_gate", simulated=True)],
        ),
        _row("with_nexus", "idle", [_receipt("hyper", simulated=False, invoked=False, refs=())]),
        _row(
            "with_nexus",
            "mixed",
            [
                _receipt("hyper", simulated=False),
                _receipt("codeintel", simulated=True),
                _receipt("research_route", simulated=True, invoked=False),
            ],
            model_calls=0,
        ),
        _row("with_nexus", "failed_sim", [_receipt("codeintel", simulated=True)], status="FAILED"),
        _row("without_nexus", "bare", [], model_calls=1),
    ]


def test_receipt_classification() -> None:
    assert classify_receipt(_receipt("a", simulated=False)) == "real"
    assert classify_receipt(_receipt("a", simulated=True)) == "simulated"
    assert classify_receipt(_receipt("a", simulated=False, refs=())) == "simulated"
    assert classify_receipt(_receipt("a", simulated=False, invoked=False)) == "selected_not_invoked"
    assert classify_receipt(_receipt("a", simulated=None)) == "real"
    assert classify_receipt(_receipt("a", simulated=None, refs=())) == "simulated"


def test_row_flags_and_status_untouched() -> None:
    rows = _rows()
    _summarize_with_strict_baseline(rows, strict=True)
    by_id = {r["task_id"]: r for r in rows}
    assert by_id["real"]["capabilities_real"] == ["hyper"]
    assert by_id["real"]["capability_not_exercised"] is False
    assert by_id["sim"]["capabilities_simulated"] == ["claim_gate", "codeintel"]
    assert by_id["sim"]["capability_not_exercised"] is True
    assert by_id["sim"]["solve_without_capability"] is True
    assert by_id["sim"]["status"] == "SUCCESS"
    assert by_id["idle"]["capabilities_selected_not_invoked"] == ["hyper"]
    assert by_id["idle"]["capability_not_exercised"] is True
    assert by_id["mixed"]["capabilities_real"] == ["hyper"]
    assert by_id["mixed"]["capabilities_simulated"] == ["codeintel"]
    assert by_id["mixed"]["capabilities_selected_not_invoked"] == ["research_route"]
    assert by_id["mixed"]["capability_not_exercised"] is False
    assert by_id["failed_sim"]["solve_without_capability"] is False
    assert "capability_not_exercised" not in by_id["bare"]


def test_summary_tallies() -> None:
    rows = _rows()
    arm = _summarize_with_strict_baseline(rows, strict=True)["with_nexus"]
    assert arm["real_capability_rows_n"] == 2
    assert arm["simulated_only_rows_n"] == 2
    assert arm["attested_real_capability_rows_n"] == 2
    assert arm["capability_not_exercised_rows_n"] == 3
    assert arm["solved_n"] == 3  # real, sim, idle (model_calls>0 and SUCCESS); mixed is a rescue
    assert arm["solves_with_real_capability_n"] == 1
    assert arm["solve_without_capability_n"] == 2
    assert arm["nexus_uplift_solved_n"] == 1
    assert arm["capability_tally"]["hyper"] == {
        "real": 2,
        "simulated": 0,
        "selected_not_invoked": 1,
    }
    assert arm["capability_tally"]["codeintel"] == {
        "real": 0,
        "simulated": 3,
        "selected_not_invoked": 0,
    }
    assert arm["capability_tally"]["research_route"] == {
        "real": 0,
        "simulated": 0,
        "selected_not_invoked": 1,
    }
    assert (
        "real_capability_rows_n"
        not in _summarize_with_strict_baseline(_rows(), strict=True)["without_nexus"]
    )


def test_noop_without_strict_flag() -> None:
    rows = _rows()
    summary = _summarize_with_strict_baseline(rows, strict=False)
    assert all("capability_not_exercised" not in r and "capabilities_real" not in r for r in rows)
    assert "real_capability_rows_n" not in summary["with_nexus"]
    assert "strict_llm_baseline_applied" not in summary["with_nexus"]


def test_reclassify_report_dir(tmp_path: Path, capsys: Any) -> None:
    rows = _rows()
    (tmp_path / "with_nexus_1.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows if r["mode"] == "with_nexus") + "\n", encoding="utf-8"
    )
    (tmp_path / "without_nexus_1.jsonl").write_text(json.dumps(rows[-1]) + "\n", encoding="utf-8")
    result = reclassify_report_dir(tmp_path)
    assert result["arms"]["with_nexus"]["real_capability_rows_n"] == 2
    assert len(result["with_nexus_rows"]) == 5
    assert reclassify_main(["--reclassify", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["arms"]["with_nexus"]["simulated_only_rows_n"] == 2


def test_unattested_real_receipt_is_reported_separately() -> None:
    rows = [_row("with_nexus", "backfill", [_receipt("hyper", simulated=None)])]
    arm = _summarize_with_strict_baseline(rows, strict=True)["with_nexus"]
    assert rows[0]["capabilities_real"] == ["hyper"]
    assert rows[0]["capabilities_real_unattested"] == ["hyper"]
    assert arm["real_capability_rows_n"] == 1
    assert arm["attested_real_capability_rows_n"] == 0


def test_claim_boundary_takes_the_stricter_of_receipt_base_and_runtime() -> None:
    def receipt(rb: bool | None, top: bool | None) -> dict[str, Any]:
        item = _receipt("acceptance_check", simulated=rb)
        if top is not None:
            item["claim_boundary"] = {"simulated": top}
        return item

    assert classify_receipt(receipt(False, False)) == "real"
    # Stale receipt_base true + runtime false: still simulated (tighten-only).
    assert classify_receipt(receipt(True, False)) == "simulated"
    assert classify_receipt(receipt(False, True)) == "simulated"
    assert classify_receipt(receipt(True, True)) == "simulated"
    assert classify_receipt(receipt(None, False)) == "real"
    assert classify_receipt(receipt(None, True)) == "simulated"


def test_not_executable_receipts_are_reported_apart() -> None:
    direct = _receipt("direct_mode", simulated=True, invoked=False, refs=())
    direct["failure_reason"] = "NOT_EXECUTABLE:control_plane_reference"
    route = _receipt("research_route", simulated=True, invoked=False, refs=())
    route["execution_state"] = "NOT_EXECUTABLE"
    assert classify_receipt(direct) == "not_executable"
    assert classify_receipt(route) == "not_executable"

    rows = [_row("with_nexus", "ne", [direct, route, _receipt("hyper", simulated=False)])]
    arm = _summarize_with_strict_baseline(rows, strict=True)["with_nexus"]
    assert rows[0]["capabilities_not_executable"] == ["direct_mode", "research_route"]
    assert rows[0]["capabilities_selected_not_invoked"] == []
    assert rows[0]["capabilities_simulated"] == []
    assert arm["capability_not_executable_tally"] == {"direct_mode": 1, "research_route": 1}
    assert "direct_mode" not in arm["capability_tally"]
