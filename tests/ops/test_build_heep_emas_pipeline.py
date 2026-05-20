from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.build_heep_emas_pipeline import build_heep_emas_artifacts, main, write_heep_emas_artifacts


def _original_map() -> dict:
    return {
        "status": "PASS",
        "rows": [
            {
                "capability": "codeintel",
                "decision": "replace_candidate",
                "evidence_refs": [".nexus/reports/codeintel/evidence_bundle.json"],
                "original_skill_name": "First Principles Thinking",
                "original_source_path": "/private/tmp/round/first/SKILL.md",
                "primary_skill_id": "sf-systematic-codeintel-first-principles-thinking-f95019ea",
                "source_round_or_root": "round7",
            },
            {
                "capability": "hyper_sprint",
                "decision": "keep_current_best",
                "evidence_refs": [".nexus/reports/hyper/evidence_bundle.json"],
                "original_skill_name": "route-fit",
                "primary_skill_id": "sf2-hyper_sprint-route-fit-spec",
                "source_round_or_root": "current_best",
            },
        ],
    }


def _overlay() -> dict:
    return {
        "status": "PASS",
        "primary_skill_by_capability": {
            "codeintel": "sf-systematic-codeintel-first-principles-thinking-f95019ea",
            "hyper_sprint": "sf2-hyper_sprint-route-fit-spec",
        },
        "selected_primary": [
            {
                "capability_id": "codeintel",
                "receipt_path": ".nexus/reports/codeintel",
                "skill_id": "sf-systematic-codeintel-first-principles-thinking-f95019ea",
                "token_delta_challenger_minus_current": -12,
                "wall_delta_challenger_minus_current": -1.2,
            },
            {
                "capability_id": "hyper_sprint",
                "receipt_path": ".nexus/reports/hyper",
                "skill_id": "sf2-hyper_sprint-route-fit-spec",
                "token_delta_challenger_minus_current": 4,
                "wall_delta_challenger_minus_current": -2.5,
            },
        ],
    }


def _smoke(*, used: bool = True) -> dict:
    chain = {
        "selected": True,
        "injected": True,
        "used": used,
        "evidence_present": True,
        "gate_passed": True,
        "outcome_contributed": True,
    }
    return {
        "status": "PASS",
        "cases": [
            {"capability": "codeintel", "runtime_final_receipt_chain": chain},
            {"capability": "hyper_sprint", "runtime_final_receipt_chain": chain},
        ],
    }


def test_build_heep_emas_artifacts_keeps_runtime_and_public_gates_closed() -> None:
    mat_b_report = {
        "summary": {"comparison_count": 2},
        "comparisons": [
            {"capability": "codeintel", "verdict": "APPROVE_HEEP_MODE_CANDIDATE", "reason_codes": []},
            {"capability": "hyper_sprint", "verdict": "KEEP_SINGLE_PRIMARY", "reason_codes": ["efficiency_regressed"]},
        ],
    }
    artifacts = build_heep_emas_artifacts(
        original_map=_original_map(), overlay=_overlay(), smoke=_smoke(), mat_b_report=mat_b_report
    )

    assert artifacts["contract"]["status"] == "PASS"
    assert artifacts["assembly"]["summary"]["capability_count"] == 2
    assert artifacts["rollup"]["summary"]["ready_for_live_heep_count"] == 1
    assert artifacts["intake"]["summary"]["safe_candidate_count"] == 1
    assert artifacts["gold_cases"]["cases"][0]["receipt_chain_complete"] is True
    assert artifacts["contract"]["summary"]["runtime_update_allowed"] is False
    assert artifacts["rollup"]["summary"]["public_benchmark_allowed"] is False
    assert "Mode C (Swarm)" in artifacts["markdown_map"]
    assert "MAT-B live compare coverage: 2/2 capabilities" in artifacts["markdown_map"]
    assert "APPROVE_HEEP_MODE_CANDIDATE" in artifacts["markdown_map"]


def test_build_heep_emas_artifacts_returns_on_overlay_map_gap() -> None:
    overlay = _overlay()
    overlay["primary_skill_by_capability"]["missing_cap"] = "missing-skill"

    artifacts = build_heep_emas_artifacts(original_map=_original_map(), overlay=overlay, smoke=_smoke())

    assert artifacts["assembly"]["status"] == "RETURN"
    assert "missing_original_map_row:missing_cap" in artifacts["assembly"]["blockers"]


def test_build_heep_emas_artifacts_returns_on_incomplete_runtime_receipt() -> None:
    artifacts = build_heep_emas_artifacts(original_map=_original_map(), overlay=_overlay(), smoke=_smoke(used=False))

    assert artifacts["assembly"]["status"] == "RETURN"
    assert "codeintel:sf-systematic-codeintel-first-principles-thinking-f95019ea:runtime_receipt_chain_incomplete" in artifacts[
        "assembly"
    ]["blockers"]


def test_write_heep_emas_artifacts_outputs_all_files(tmp_path: Path) -> None:
    artifacts = build_heep_emas_artifacts(original_map=_original_map(), overlay=_overlay(), smoke=_smoke())
    outputs = write_heep_emas_artifacts(
        artifacts=artifacts,
        report_dir=tmp_path / "reports",
        info_map=tmp_path / "docs/info/NEXUS_CAPABILITY_SKILL_MAP.md",
    )

    assert Path(outputs["contract"]).exists()
    assert Path(outputs["assembly"]).exists()
    assert Path(outputs["gold_cases"]).exists()
    assert Path(outputs["rollup"]).exists()
    assert Path(outputs["intake"]).exists()
    assert Path(outputs["markdown_map"]).read_text(encoding="utf-8").startswith("# Nexus 能力")


def test_heep_emas_cli_writes_to_custom_paths(tmp_path: Path, capsys) -> None:
    original = tmp_path / "original.json"
    overlay = tmp_path / "overlay.json"
    smoke = tmp_path / "smoke.json"
    report_dir = tmp_path / "reports"
    info_map = tmp_path / "map.md"
    original.write_text(json.dumps(_original_map()), encoding="utf-8")
    overlay.write_text(json.dumps(_overlay()), encoding="utf-8")
    smoke.write_text(json.dumps(_smoke()), encoding="utf-8")

    rc = main(
        [
            "--original-map",
            str(original),
            "--overlay",
            str(overlay),
            "--smoke",
            str(smoke),
            "--report-dir",
            str(report_dir),
            "--info-map",
            str(info_map),
        ]
    )
    captured = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert captured["status"] == "PASS"
    assert captured["outputs"]["markdown_map"] == str(info_map)
    assert (report_dir / "NEXUS_HEEP_EMAS_CONTRACT_2026-05-20.json").exists()
