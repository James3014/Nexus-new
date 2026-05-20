from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.run_heep_live_pilot import build_heep_live_pilot, main, write_heep_live_pilot


def _chain(*, used: bool = True) -> dict[str, bool]:
    return {
        "selected": True,
        "injected": True,
        "used": used,
        "evidence_present": True,
        "gate_passed": True,
        "outcome_contributed": True,
    }


def _assembly() -> dict:
    return {
        "status": "PASS",
        "rows": [
            {
                "assembly": [
                    {"role": "Scout", "skill_id": "code-scout"},
                    {"role": "Logic", "skill_id": "route-logic"},
                    {"role": "Audit", "skill_id": "evidence-audit"},
                ],
                "capability": "codeintel",
                "primary_role_tags": ["Scout"],
                "primary_skill_id": "code-scout",
                "recommended_mode": "Mode C (Swarm)",
            },
            {
                "assembly": [
                    {"role": "primary", "skill_id": "repair-primary"},
                    {"role": "Audit", "skill_id": "evidence-audit"},
                ],
                "capability": "repair_loop",
                "primary_role_tags": ["Logic"],
                "primary_skill_id": "repair-primary",
                "recommended_mode": "Mode B (Guard)",
            },
        ],
    }


def _gold(*, used: bool = True) -> dict:
    return {
        "status": "PASS",
        "cases": [
            {
                "capability": "codeintel",
                "primary_skill_id": "code-scout",
                "runtime_final_receipt_chain": _chain(used=used),
                "source_evidence_ref": ".nexus/reports/codeintel/evidence_bundle.json",
            },
            {
                "capability": "repair_loop",
                "primary_skill_id": "repair-primary",
                "runtime_final_receipt_chain": _chain(used=used),
                "source_evidence_ref": ".nexus/reports/repair/evidence_bundle.json",
            },
        ],
    }


def test_build_heep_live_pilot_outputs_three_mode_rows_and_gate_candidates() -> None:
    artifacts = build_heep_live_pilot(
        assembly_catalog=_assembly(),
        gold_cases=_gold(),
        pilot_capabilities=("codeintel", "repair_loop"),
    )

    assert artifacts["contract"]["status"] == "PASS"
    assert artifacts["run"]["summary"]["row_count"] == 6
    assert artifacts["run"]["summary"]["pass_count"] == 6
    assert artifacts["decision"]["summary"]["capability_count"] == 2
    assert artifacts["map_gate"]["summary"]["candidate_update_count"] == 2
    assert artifacts["map_gate"]["summary"]["runtime_update_allowed"] is False
    assert artifacts["map_gate"]["summary"]["public_benchmark_allowed"] is False


def test_build_heep_live_pilot_returns_when_runtime_receipt_is_incomplete() -> None:
    artifacts = build_heep_live_pilot(
        assembly_catalog=_assembly(),
        gold_cases=_gold(used=False),
        pilot_capabilities=("codeintel",),
    )

    assert artifacts["run"]["status"] == "RETURN"
    assert "codeintel:Mode A (Solo):receipt_or_role_incomplete" in artifacts["run"]["blockers"]
    assert artifacts["map_gate"]["status"] == "RETURN"


def test_write_heep_live_pilot_outputs_reports(tmp_path: Path) -> None:
    artifacts = build_heep_live_pilot(
        assembly_catalog=_assembly(),
        gold_cases=_gold(),
        pilot_capabilities=("codeintel",),
    )
    outputs = write_heep_live_pilot(artifacts=artifacts, report_dir=tmp_path / "reports")

    assert Path(outputs["contract"]).exists()
    assert Path(outputs["run"]).exists()
    assert Path(outputs["decision"]).exists()
    assert Path(outputs["map_gate"]).exists()


def test_heep_live_pilot_cli_writes_custom_reports(tmp_path: Path, capsys) -> None:
    assembly = tmp_path / "assembly.json"
    gold = tmp_path / "gold.json"
    report_dir = tmp_path / "reports"
    assembly.write_text(json.dumps(_assembly()), encoding="utf-8")
    gold.write_text(json.dumps(_gold()), encoding="utf-8")

    rc = main(
        [
            "--assembly",
            str(assembly),
            "--gold-cases",
            str(gold),
            "--report-dir",
            str(report_dir),
            "--pilot-capabilities",
            "codeintel,repair_loop",
        ]
    )
    captured = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert captured["status"] == "PASS"
    assert captured["row_count"] == 6
    assert (report_dir / "NEXUS_HEEP_LIVE_PILOT_RUN_2026-05-20.json").exists()
