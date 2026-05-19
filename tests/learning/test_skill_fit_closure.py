from pathlib import Path

from nexus.learning.skill_fit_closure import (
    build_capability_local_test_matrix,
    build_final_capability_skill_catalog,
    build_sf_flash_pair_live_report,
    build_sf_paired_delta_report,
    build_sf_evidence_gate_schema,
    evaluate_bounded_probe_row,
    run_sf_bounded_probe,
)


def _skill(path: Path, name: str, body: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\n---\n# {name}\n{body}\n", encoding="utf-8")
    return str(path)


def test_capability_local_matrix_keeps_current_pairing_path(tmp_path):
    skill_path = _skill(
        tmp_path / "tdd" / "SKILL.md",
        "tdd",
        "Use repair loop test evidence receipt gate outcome verification.",
    )
    final_pairing = {
        "pairings": [
            {
                "capability_id": "repair_loop",
                "current_pairing_skill_id": "tdd",
                "current_pairing_identity_id": "id-current",
                "current_pairing_skill_path": skill_path,
                "current_pairing_source_status": "nexus_repo_local",
                "current_pairing_score": 20,
                "current_pairing_runtime_eligible": True,
                "canonical_top_skill_id": "tdd",
                "canonical_top_identity_id": "id-current",
            }
        ]
    }
    buckets = {"capability_buckets": [{"capability_id": "repair_loop", "top_candidates": []}]}

    matrix = build_capability_local_test_matrix(final_pairing=final_pairing, capability_buckets=buckets)

    assert matrix["status"] == "PASS"
    assert matrix["summary"]["public_benchmark_allowed"] is False
    skill_rows = [row for row in matrix["rows"] if row["arm_type"] == "skill_arm"]
    assert skill_rows[0]["skill_path"] == skill_path
    assert {row["arm_type"] for row in matrix["rows"]} == {
        "capability_only",
        "skill_arm",
        "negative_control",
    }


def test_selected_only_skill_arm_returns(tmp_path):
    row = {
        "row_id": "research::skill_arm_001::empty",
        "capability_id": "research",
        "arm_type": "skill_arm",
        "skill_id": "empty",
        "skill_path": str(tmp_path / "missing" / "SKILL.md"),
    }

    result = evaluate_bounded_probe_row(row)

    assert result["status"] == "RETURN"
    assert result["selected"] is True
    assert result["injected"] is False
    assert result["outcome_contributed"] is False


def test_bounded_probe_and_catalog_produce_primary_and_flow(tmp_path):
    skill_path = _skill(
        tmp_path / "research-citation-chain-verifier" / "SKILL.md",
        "research-citation-chain-verifier",
        "Use research source discipline evidence citation claim gate receipt outcome verification.",
    )
    matrix = {
        "rows": [
            {"row_id": "research::capability_only", "capability_id": "research", "arm_type": "capability_only"},
            {
                "row_id": "research::skill_arm_001::research-citation-chain-verifier",
                "capability_id": "research",
                "arm_type": "skill_arm",
                "skill_id": "research-citation-chain-verifier",
                "identity_id": "id-research",
                "skill_path": skill_path,
                "candidate_role": "current_pairing",
            },
            {
                "row_id": "research::negative_control",
                "capability_id": "research",
                "arm_type": "negative_control",
                "skill_id": "wrong_or_quarantined_skill",
            },
        ]
    }
    gate = build_sf_evidence_gate_schema()
    probe = run_sf_bounded_probe(matrix)
    catalog = build_final_capability_skill_catalog(bounded_probe=probe, evidence_gate=gate)

    assert probe["status"] == "PASS"
    assert catalog["status"] == "PASS"
    assert catalog["capability_skill_catalog"][0]["primary_default"] == "research-citation-chain-verifier"
    assert "run_capability_local_bounded_probe_against_current_primary" in catalog["future_replacement_flow"]
    assert catalog["summary"]["public_benchmark_allowed"] is False

    delta = build_sf_paired_delta_report(matrix=matrix, bounded_probe=probe, catalog=catalog)
    assert delta["status"] == "PASS"
    assert delta["summary"]["bounded_positive_delta_count"] == 1
    assert delta["summary"]["live_delta_measured_count"] == 0
    assert delta["deltas"][0]["live_solve_rate_delta"] == "not_measured_in_sf_bounded_delta"


def test_bounded_probe_does_not_require_flash_when_current_fails_and_canonical_wins(tmp_path):
    current_path = _skill(tmp_path / "old" / "SKILL.md", "old", "Generic helper.")
    canonical_path = _skill(
        tmp_path / "sf2-nightshift-route-fit-spec" / "SKILL.md",
        "sf2-nightshift-route-fit-spec",
        "Use nightshift autonomous long run recovery evidence receipt outcome gate.",
    )
    final_pairing = {
        "pairings": [
            {
                "capability_id": "nightshift",
                "current_pairing_skill_id": "old",
                "current_pairing_identity_id": "id-old",
                "current_pairing_skill_path": current_path,
                "canonical_top_skill_id": "sf2-nightshift-route-fit-spec",
                "canonical_top_identity_id": "id-nightshift",
                "canonical_top_skill_path": canonical_path,
                "canonical_top_score": 13,
            }
        ]
    }
    matrix = build_capability_local_test_matrix(
        final_pairing=final_pairing,
        capability_buckets={"capability_buckets": [{"capability_id": "nightshift", "top_candidates": []}]},
    )

    probe = run_sf_bounded_probe(matrix)

    assert probe["status"] == "PASS"
    assert probe["summary"]["flash_compare_required_count"] == 0
    assert probe["capabilities"][0]["primary_skill_id"] == "sf2-nightshift-route-fit-spec"


def test_flash_pair_live_report_uses_same_runner_pair_artifacts(tmp_path):
    baseline_dir = tmp_path / "baseline"
    skill_dir = tmp_path / "skill"
    for root in (baseline_dir, skill_dir):
        root.mkdir()
        (root / "with_nexus_1.jsonl").write_text("{}", encoding="utf-8")
        (root / "without_nexus_1.jsonl").write_text("{}", encoding="utf-8")
        (root / "evidence_bundle.json").write_text("{}", encoding="utf-8")
    live_summary = {
        "results": [
            {
                "row_id": "artifact_gate::task::flash_nexus",
                "capability": "artifact_gate",
                "task_ref": {"task_id": "task"},
                "arm_id": "flash_nexus",
                "status": "PASS",
                "output_dir": str(baseline_dir),
                "benchmark_row": {
                    "status": "SUCCESS",
                    "semantic_status": "VERIFIED",
                    "report_trust_mismatch": False,
                    "model_calls": 2,
                    "total_tokens": 100,
                    "phase_wall_total_sec": 10.0,
                    "session_worker_enabled": False,
                },
            },
            {
                "row_id": "artifact_gate::task::flash_nexus_with_skill::s",
                "capability": "artifact_gate",
                "task_ref": {"task_id": "task"},
                "arm_id": "flash_nexus_with_skill",
                "status": "PASS",
                "skill_id": "s",
                "output_dir": str(skill_dir),
                "benchmark_row": {
                    "status": "SUCCESS",
                    "semantic_status": "VERIFIED",
                    "report_trust_mismatch": False,
                    "model_calls": 2,
                    "total_tokens": 125,
                    "phase_wall_total_sec": 13.5,
                    "session_worker_enabled": False,
                },
                "ablation_gate_row": {
                    "skill_mount_contract_status": "PASS",
                    "selected": True,
                    "injected": True,
                    "used": True,
                    "evidence_present": True,
                    "gate_passed": True,
                    "outcome_contributed": True,
                },
            },
        ]
    }

    report = build_sf_flash_pair_live_report(live_summary=live_summary)

    assert report["status"] == "PASS"
    assert report["summary"]["same_runner_pair_artifact_count"] == 1
    assert report["summary"]["session_worker_clean_count"] == 1
    assert report["comparisons"][0]["verdict"] == "KEEP"
    assert report["comparisons"][0]["delta"]["token_delta"] == 25
