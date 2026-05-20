from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_sfv2_role_requiredness_assertions import build_sfv2_role_requiredness_assertions, main


def _matrix() -> dict:
    return {
        "rows": [
            {"row_id": "full", "role_focus": "Scout"},
            {"row_id": "minus", "role_focus": "Scout"},
        ]
    }


def _bench(*, scan: bool = True, clean: bool = True) -> dict:
    return {
        "rubric_contract_status": "PASS" if clean else "RETURN",
        "token_data_contract_status": "PASS" if clean else "DATA_CONTRACT_VIOLATION",
        "receipt_data_contract_status": "PASS" if clean else "DATA_CONTRACT_VIOLATION",
        "skill_mount_contract_status": "PASS" if clean else "RETURN",
        "codeintel_scan_report_present": scan,
        "codeintel_impact_report_present": scan,
        "dci_locator_present": scan,
    }


def test_role_requiredness_is_not_proven_when_minus_role_stays_clean(tmp_path: Path) -> None:
    live = {
        "results": [
            {"row_id": "full", "capability": "codeintel", "arm_id": "full_assembly", "status": "PASS", "benchmark_row": _bench()},
            {"row_id": "minus", "capability": "codeintel", "arm_id": "minus_scout", "status": "PASS", "benchmark_row": _bench()},
        ]
    }

    packet = build_sfv2_role_requiredness_assertions(
        live_summary=live,
        matrix=_matrix(),
        output=tmp_path / "packet.json",
    )

    assert packet["status"] == "PASS"
    assert packet["summary"]["role_requiredness_proven_count"] == 0
    assert packet["assertions"][0]["status"] == "NOT_PROVEN"
    assert packet["assertions"][0]["reason"] == "minus_role_preserved_required_external_assertions"


def test_role_requiredness_is_proven_when_minus_role_loses_assertion(tmp_path: Path) -> None:
    live = {
        "results": [
            {"row_id": "full", "capability": "codeintel", "arm_id": "full_assembly", "status": "PASS", "benchmark_row": _bench()},
            {
                "row_id": "minus",
                "capability": "codeintel",
                "arm_id": "minus_scout",
                "status": "RETURN",
                "benchmark_row": _bench(scan=False, clean=False),
            },
        ]
    }

    packet = build_sfv2_role_requiredness_assertions(
        live_summary=live,
        matrix=_matrix(),
        output=tmp_path / "packet.json",
    )

    assert packet["summary"]["role_requiredness_proven_count"] == 1
    assert packet["assertions"][0]["status"] == "ROLE_REQUIREDNESS_PROVEN"
    assert packet["assertions"][0]["reason"] == "minus_role_lost_required_external_assertion"


def test_role_requiredness_cli_writes_packet(tmp_path: Path, capsys) -> None:
    live = tmp_path / "live.json"
    matrix = tmp_path / "matrix.json"
    output = tmp_path / "packet.json"
    live.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "row_id": "full",
                        "capability": "codeintel",
                        "arm_id": "full_assembly",
                        "status": "PASS",
                        "benchmark_row": _bench(),
                    },
                    {
                        "row_id": "minus",
                        "capability": "codeintel",
                        "arm_id": "minus_scout",
                        "status": "PASS",
                        "benchmark_row": _bench(),
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    matrix.write_text(json.dumps(_matrix()), encoding="utf-8")

    rc = main(["--live-summary", str(live), "--matrix", str(matrix), "--output", str(output)])
    captured = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert captured["status"] == "PASS"
    assert captured["assertion_count"] == 1
    assert output.exists()
