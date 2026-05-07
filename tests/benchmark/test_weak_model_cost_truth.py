from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.weak_model_cost_truth import (
    build_focused_runs,
    main,
    parse_run_spec,
    render_cost_truth_json,
    render_cost_truth_report,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _write_run_dir(run_dir: Path, *, bare_verified: int, nexus_verified: int, rows: int = 2, bare_tokens: int = 100, nexus_tokens: int = 140) -> None:
    run_dir.mkdir(parents=True)
    bare_rows = []
    nexus_rows = []
    for idx in range(rows):
        bare_rows.append(
            {
                "task_id": f"bare-{idx}",
                "trial_index": 1,
                "semantic_status": "VERIFIED" if idx < bare_verified else "UNVERIFIED",
                "run_eligible": True,
                "wall_duration_sec": 10 + idx,
                "model_calls": 1,
                "total_tokens": bare_tokens,
            }
        )
        nexus_rows.append(
            {
                "task_id": f"nexus-{idx}",
                "trial_index": 1,
                "semantic_status": "VERIFIED" if idx < nexus_verified else "UNVERIFIED",
                "run_eligible": True,
                "wall_duration_sec": 20 + idx,
                "model_calls": 1,
                "total_tokens": nexus_tokens,
            }
        )
    _write_jsonl(run_dir / "without_nexus_1.jsonl", bare_rows)
    _write_jsonl(run_dir / "with_nexus_1.jsonl", nexus_rows)
    (run_dir / "gemini_nexus_report_1.md").write_text(
        "- Public claim gate: PASS\n- Public claim gate failures: none\n",
        encoding="utf-8",
    )
    (run_dir / "evidence_bundle.json").write_text(
        json.dumps(
            {
                "schema": "nexus_public_benchmark_evidence_bundle_v2",
                "task_manifest": {"sha256": "same"},
                "public_disclosure_manifest": {"status": "PASS"},
                "public_claim_gate": {"verdict": "PASS", "failures": []},
                "route_cost_ledger": {"schema": "nexus_route_cost_ledger_v1", "arms": {"with_nexus": {"capability_selected_avg": 9}}},
                "product_kpis": {"schema": "nexus_product_kpis_v1", "arms": {"with_nexus": {"avg_time_to_verified_sec": 20}}},
            }
        ),
        encoding="utf-8",
    )


def test_parse_run_spec_requires_focus_arm() -> None:
    assert parse_run_spec("Gemini 3 Flash=/tmp/x=3x1=candidate=nexus")[4] == "nexus"


def test_render_cost_truth_report_compares_against_reference(tmp_path: Path) -> None:
    flash = tmp_path / "flash"
    gpt54 = tmp_path / "gpt54"
    gpt55 = tmp_path / "gpt55"
    _write_run_dir(flash, bare_verified=0, nexus_verified=2, bare_tokens=80, nexus_tokens=120)
    _write_run_dir(gpt54, bare_verified=2, nexus_verified=2, bare_tokens=90, nexus_tokens=130)
    _write_run_dir(gpt55, bare_verified=2, nexus_verified=2, bare_tokens=110, nexus_tokens=150)

    runs = build_focused_runs(
        [
            f"Gemini 3 Flash={flash}=3x1=candidate=nexus",
            f"GPT-5.4={gpt54}=3x1=reference=bare",
            f"GPT-5.5={gpt55}=3x1=reference=bare",
        ],
        {},
    )
    out = render_cost_truth_report(runs, reference_model="GPT-5.4", weak_model_name="Gemini 3 Flash")

    assert "## Weak Model Cost Truth" in out
    assert "Gemini 3 Flash" in out
    assert "GPT-5.4" in out
    assert "weak_model: Gemini 3 Flash" in out
    assert "reference_model: GPT-5.4" in out

    payload = render_cost_truth_json(runs, reference_model="GPT-5.4", weak_model_name="Gemini 3 Flash")
    assert payload["schema_version"] == "nexus_weak_model_cost_truth_v1"
    assert payload["weak_model_decision"]["decision"] in {"beats_reference", "near_reference", "partial_gap", "far_from_reference"}
    assert len(payload["rows"]) == 3


def test_main_writes_report_and_json(tmp_path: Path, monkeypatch) -> None:
    flash = tmp_path / "flash"
    gpt54 = tmp_path / "gpt54"
    _write_run_dir(flash, bare_verified=0, nexus_verified=2)
    _write_run_dir(gpt54, bare_verified=2, nexus_verified=2)
    output = tmp_path / "cost_truth.md"
    output_json = tmp_path / "cost_truth.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "weak_model_cost_truth.py",
            "--run",
            f"Gemini 3 Flash={flash}=3x1=candidate=nexus",
            "--run",
            f"GPT-5.4={gpt54}=3x1=reference=bare",
            "--reference-model",
            "GPT-5.4",
            "--weak-model-name",
            "Gemini 3 Flash",
            "--output",
            str(output),
            "--output-json",
            str(output_json),
        ],
    )

    assert main() == 0
    assert "Weak Model Cost Truth" in output.read_text(encoding="utf-8")
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["reference_model"] == "GPT-5.4"
