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
    assert artifacts["compare_queue"]["summary"]["candidate_count"] == 2
    assert artifacts["apply_review"]["summary"]["pending_live_compare_count"] == 2
    assert artifacts["map_gate"]["summary"]["runtime_update_allowed"] is False
    assert artifacts["map_gate"]["summary"]["public_benchmark_allowed"] is False
    assert artifacts["compare_queue"]["rows"][0]["baseline_arm"]["arm_id"] == "mode_a_current_primary"
    assert artifacts["compare_queue"]["rows"][0]["challenger_arm"]["arm_id"] == "heep_multi_skill"
    assert artifacts["compare_queue"]["rows"][0]["mat_b_gate"]["status"] == "PENDING_LIVE_COMPARE"
    assert "pollution_pct" in artifacts["compare_queue"]["rows"][0]["mat_b_gate"]["required_kpis"]
    assert artifacts["apply_review"]["rows"][0]["mat_b_required_before_runtime_apply"] is True


def test_build_heep_live_pilot_returns_when_runtime_receipt_is_incomplete() -> None:
    artifacts = build_heep_live_pilot(
        assembly_catalog=_assembly(),
        gold_cases=_gold(used=False),
        pilot_capabilities=("codeintel",),
    )

    assert artifacts["run"]["status"] == "RETURN"
    assert "codeintel:Mode A (Solo):receipt_or_role_incomplete" in artifacts["run"]["blockers"]
    assert artifacts["map_gate"]["status"] == "RETURN"
    assert artifacts["compare_queue"]["status"] == "RETURN"
    assert artifacts["apply_review"]["status"] == "RETURN"


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
    assert Path(outputs["compare_queue"]).exists()
    assert Path(outputs["apply_review"]).exists()


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
    assert captured["live_compare_candidate_count"] == 2
    assert captured["pending_apply_review_count"] == 2
    assert (report_dir / "NEXUS_HEEP_LIVE_PILOT_RUN_2026-05-20.json").exists()


def test_heep_live_pilot_cli_defaults_to_all_assembly_capabilities(tmp_path: Path, capsys) -> None:
    assembly = tmp_path / "assembly.json"
    gold = tmp_path / "gold.json"
    assembly.write_text(json.dumps(_assembly()), encoding="utf-8")
    gold.write_text(json.dumps(_gold()), encoding="utf-8")

    rc = main(["--assembly", str(assembly), "--gold-cases", str(gold), "--dry-run"])
    captured = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert captured["pilot_capability_count"] == 2
    assert captured["row_count"] == 6


def test_heep_live_pilot_respects_assembly_recommended_solo_mode() -> None:
    assembly = _assembly()
    assembly["rows"].append(
        {
            "assembly": [{"role": "primary", "skill_id": "lean-primary"}],
            "capability": "hyper_sprint",
            "primary_role_tags": ["Logic"],
            "primary_skill_id": "lean-primary",
            "recommended_mode": "Mode A (Solo)",
        }
    )
    gold = _gold()
    gold["cases"].append(
        {
            "capability": "hyper_sprint",
            "primary_skill_id": "lean-primary",
            "runtime_final_receipt_chain": _chain(),
            "source_evidence_ref": ".nexus/reports/hyper/evidence_bundle.json",
        }
    )

    artifacts = build_heep_live_pilot(assembly_catalog=assembly, gold_cases=gold)

    decisions = {item["capability"]: item for item in artifacts["decision"]["decisions"]}
    assert decisions["hyper_sprint"]["selected_mode"] == "Mode A (Solo)"
    assert artifacts["compare_queue"]["summary"]["candidate_count"] == 3
    queue_rows = {item["capability"]: item for item in artifacts["compare_queue"]["rows"]}
    assert queue_rows["hyper_sprint"]["baseline_arm"]["mode"] == "Mode A (Solo)"
    assert queue_rows["hyper_sprint"]["challenger_arm"]["mode"] != "Mode A (Solo)"
    apply_rows = {item["capability"]: item for item in artifacts["apply_review"]["rows"]}
    assert apply_rows["hyper_sprint"]["disposition"] == "PENDING_FLASH_NEXUS_LIVE_COMPARE"
