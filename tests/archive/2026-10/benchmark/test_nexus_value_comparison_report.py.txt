from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.nexus_value_comparison_report import final_report_failures, main, render_report, summarize_run


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _route_cost_ledger(schema: str = "nexus_route_cost_ledger_v1") -> dict:
    return {
        "schema": schema,
        "scope": "measured_benchmark_telemetry_not_billing_cost",
        "arms": {
            "with_nexus": {
                "route_decision_present_rate": 1.0,
                "route_recommended_flow_present_rate": 1.0,
                "chosen_flow_present_rate": 1.0,
                "capability_selected_avg": 18.0,
                "capability_required_avg": 5.0,
                "capability_conditional_avg": 13.0,
            },
            "without_nexus": {},
        },
    }


def _product_kpis() -> dict:
    return {
        "schema": "nexus_product_kpis_v1",
        "arms": {
            "without_nexus": {
                "avg_time_to_verified_sec": 10,
                "fail_closed_block_rate": 0.5,
                "replay_pass_rate": 0.5,
                "policy_hit_success_rate": 0.0,
            },
            "with_nexus": {
                "avg_time_to_verified_sec": 21,
                "fail_closed_block_rate": 0.0,
                "replay_pass_rate": 1.0,
                "policy_hit_success_rate": 1.0,
            },
        },
    }


def test_summarize_run_prefers_markdown_gate_and_keeps_infra_boundary(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_jsonl(
        run_dir / "without_nexus_1.jsonl",
        [
            {"task_id": "a", "trial_index": 1, "semantic_status": "VERIFIED", "run_eligible": True, "wall_duration_sec": 10, "model_calls": 1, "total_tokens": 100},
            {"task_id": "b", "trial_index": 1, "semantic_status": "UNVERIFIED", "run_eligible": False, "infra_invalid_reason": "auth_failed"},
        ],
    )
    _write_jsonl(
        run_dir / "with_nexus_1.jsonl",
        [
            {"task_id": "a", "trial_index": 1, "semantic_status": "VERIFIED", "run_eligible": True, "wall_duration_sec": 20, "model_calls": 1, "total_tokens": 120},
            {"task_id": "b", "trial_index": 1, "semantic_status": "VERIFIED", "run_eligible": True, "wall_duration_sec": 22, "model_calls": 1, "total_tokens": 140},
        ],
    )
    (run_dir / "gemini_nexus_report_1.md").write_text("- Public claim gate: FAIL\n- Public claim gate failures: run_eligibility_incomplete:1\n", encoding="utf-8")
    (run_dir / "evidence_bundle.json").write_text(
        json.dumps(
            {
                "schema": "nexus_public_benchmark_evidence_bundle_v2",
                "task_manifest": {"sha256": "abc"},
                "public_disclosure_manifest": {"status": "PASS"},
                "public_claim_gate": {"verdict": "PASS", "failures": []},
                "route_cost_ledger": _route_cost_ledger(),
                "product_kpis": _product_kpis(),
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_run("GPT-5.5", run_dir, scope="2 rows", claim_status="observation")
    report = render_report([summary])

    assert summary.bare.eligible == 1
    assert summary.bare.verified == 1
    assert summary.nexus.verified == 2
    assert summary.route_cost_ledger["schema"] == "nexus_route_cost_ledger_v1"
    assert "markdown FAIL; bundle PASS" in summary.gate_status
    assert "## Route Cost Ledger" in report
    assert "## Product KPIs" in report
    assert "10.00s -> 21.00s" in report
    assert "measured benchmark telemetry" in report
    assert "selected 18.00, required 5.00, conditional 13.00" in report
    assert "markdown failures: run_eligibility_incomplete:1" in report
    assert "GPT-5.5" in report
    assert "Final gate: FAIL" in report


def test_main_accepts_claim_boundary_notes(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_jsonl(
        run_dir / "without_nexus_1.jsonl",
        [{"task_id": "a", "trial_index": 1, "semantic_status": "UNVERIFIED", "run_eligible": True}],
    )
    _write_jsonl(
        run_dir / "with_nexus_1.jsonl",
        [{"task_id": "a", "trial_index": 1, "semantic_status": "VERIFIED", "run_eligible": True}],
    )
    output = tmp_path / "out.md"
    monkeypatch.setattr(
        "sys.argv",
        [
            "report",
            "--run",
            f"GPT-5.5={run_dir}=1x1=performance candidate",
            "--note",
            "GPT-5.5=capability gate FAIL",
            "--output",
            str(output),
        ],
    )

    assert main() == 0
    assert "capability gate FAIL" in output.read_text(encoding="utf-8")


def test_final_report_gate_requires_v2_pass_same_scope_and_manifest(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    rows = [{"task_id": "a", "trial_index": 1, "semantic_status": "VERIFIED", "run_eligible": True}]
    _write_jsonl(run_dir / "without_nexus_1.jsonl", rows)
    _write_jsonl(run_dir / "with_nexus_1.jsonl", rows)
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
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_run("Gemini 3 Flash", run_dir, scope="12x2", claim_status="final")

    assert final_report_failures([summary], expected_models=("Gemini 3 Flash",)) == []
    assert final_report_failures([summary], expected_models=("Gemini 3 Flash",), require_route_cost_ledger=True) == [
        "Gemini 3 Flash:route_cost_ledger_missing"
    ]
    assert final_report_failures([summary], expected_models=("Gemini 3 Flash", "Gemini 3.1 Pro")) == [
        "model_missing:Gemini 3.1 Pro"
    ]


def test_final_report_gate_rejects_wrong_route_cost_ledger_schema_when_enabled(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    rows = [{"task_id": "a", "trial_index": 1, "semantic_status": "VERIFIED", "run_eligible": True}]
    _write_jsonl(run_dir / "without_nexus_1.jsonl", rows)
    _write_jsonl(run_dir / "with_nexus_1.jsonl", rows)
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
                "route_cost_ledger": _route_cost_ledger("old_schema"),
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_run("Gemini 3 Flash", run_dir, scope="12x2", claim_status="final")

    assert final_report_failures([summary], require_route_cost_ledger=True) == [
        "Gemini 3 Flash:route_cost_ledger_schema_not_v1"
    ]


def test_final_report_gate_detects_regression_against_baseline(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    _write_jsonl(
        run_dir / "without_nexus_1.jsonl",
        [{"task_id": "a", "trial_index": 1, "semantic_status": "UNVERIFIED", "run_eligible": True}],
    )
    _write_jsonl(
        run_dir / "with_nexus_1.jsonl",
        [{"task_id": "a", "trial_index": 1, "semantic_status": "UNVERIFIED", "run_eligible": True}],
    )
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
                "route_cost_ledger": _route_cost_ledger(),
            }
        ),
        encoding="utf-8",
    )
    summary = summarize_run("Gemini 3 Flash", run_dir, scope="1x1", claim_status="candidate")
    baseline = {
        "task_manifest": {"sha256": "same", "unique_tasks_requested": 1, "repeat_trials": 1},
        "public_gate_requirements": {"route_cost_ledger_schema": "nexus_route_cost_ledger_v1"},
        "model_baselines": [{"label": "Gemini 3 Flash", "nexus_verified": 1, "bare_verified": 1}],
    }

    assert final_report_failures([summary], baseline=baseline) == [
        "Gemini 3 Flash:bare_verified_regression",
        "Gemini 3 Flash:nexus_verified_regression",
    ]


def test_summarize_run_accepts_non_gemini_markdown_report_name(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    rows = [{"task_id": "a", "trial_index": 1, "semantic_status": "VERIFIED", "run_eligible": True}]
    _write_jsonl(run_dir / "without_nexus_1.jsonl", rows)
    _write_jsonl(run_dir / "with_nexus_1.jsonl", rows)
    (run_dir / "gpt55_nexus_report_final.md").write_text(
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
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_run("GPT-5.5", run_dir, scope="12x2", claim_status="final")

    assert summary.markdown_gate == "PASS"
    assert final_report_failures([summary], expected_models=("GPT-5.5",)) == []
