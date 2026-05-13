from __future__ import annotations

import json

from nexus.engine.autodata_forge import (
    DataForgeManifestRow,
    benchmark_row_audit_passed,
    benchmark_row_score,
    benchmark_rows_to_data_forge_rows,
    classify_trajectory_quality,
    validate_hard_trajectory_pool,
    write_data_forge_manifest,
)


def test_autodata_forge_marks_gold_only_for_audited_strong_weak_gap():
    label = classify_trajectory_quality(strong_score=0.82, weak_score=0.55, audit_passed=True)

    assert label.label == "GOLD"
    assert label.gap == 0.27
    assert label.reason == "strong_weak_gap_passed"


def test_autodata_forge_rejects_failed_audit_even_with_large_gap():
    label = classify_trajectory_quality(strong_score=0.9, weak_score=0.1, audit_passed=False)

    assert label.label == "REJECTED"
    assert label.reason == "audit_failed"


def test_autodata_forge_keeps_low_gap_as_silver():
    label = classify_trajectory_quality(strong_score=0.66, weak_score=0.51, audit_passed=True)

    assert label.label == "SILVER"
    assert label.reason == "strong_weak_gap_below_threshold"


def test_autodata_forge_writes_manifest_and_filters_low_step_gold(tmp_path):
    gold = classify_trajectory_quality(strong_score=0.82, weak_score=0.55, audit_passed=True)
    low_step_gold = DataForgeManifestRow(task_id="short", label=gold, evidence_refs=("pytest.log",), trajectory_step_count=3)
    long_gold = DataForgeManifestRow(task_id="long", label=gold, evidence_refs=("pytest.log",), trajectory_step_count=12)

    summary = write_data_forge_manifest(tmp_path / "manifest.json", [low_step_gold, long_gold])
    payload = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert summary["gold_count"] == 2
    assert summary["training_eligible_count"] == 1
    assert payload["schema_version"] == "nexus_autodata_forge_manifest.v1"
    assert payload["rows"][0]["eligible_for_training"] is False
    assert payload["rows"][0]["low_step_filter"]["filtered"] is True
    assert payload["rows"][1]["eligible_for_training"] is True


def test_autodata_forge_excludes_hard_negative_from_training():
    gold = classify_trajectory_quality(strong_score=0.82, weak_score=0.55, audit_passed=True)
    row = DataForgeManifestRow(
        task_id="negative",
        label=gold,
        evidence_refs=("pytest.log",),
        trajectory_step_count=12,
        hard_negative=True,
    )

    payload = row.to_dict()

    assert payload["hard_negative"] is True
    assert payload["eligible_for_training"] is False


def test_hard_trajectory_pool_requires_gold_negative_and_evidence():
    gold = classify_trajectory_quality(strong_score=0.82, weak_score=0.55, audit_passed=True)
    rejected = classify_trajectory_quality(strong_score=0.9, weak_score=0.1, audit_passed=False)

    payload = validate_hard_trajectory_pool(
        [
            DataForgeManifestRow(task_id="gold", label=gold, evidence_refs=("EV-1",), trajectory_step_count=12),
            DataForgeManifestRow(task_id="hard-neg", label=rejected, evidence_refs=("EV-2",), trajectory_step_count=12, hard_negative=True),
        ]
    )

    assert payload["passed"] is True
    assert payload["row_count"] == 2


def test_benchmark_row_score_requires_verified_success_without_infra_invalid():
    assert benchmark_row_score({"status": "SUCCESS", "semantic_status": "VERIFIED"}) == 1.0
    assert benchmark_row_score({"status": "FAILED", "semantic_status": "VERIFIED"}) == 0.0
    assert benchmark_row_score({"status": "SUCCESS", "semantic_status": "UNVERIFIED"}) == 0.0
    assert benchmark_row_score({"status": "SUCCESS", "semantic_status": "VERIFIED", "infra_invalid": True}) == 0.0
    assert benchmark_row_audit_passed({"status": "SUCCESS", "semantic_status": "VERIFIED", "trust_mismatch": True}) is False


def test_benchmark_rows_to_data_forge_rows_mines_gold_and_hard_negative():
    rows = benchmark_rows_to_data_forge_rows(
        strong_source="with.jsonl",
        weak_source="without.jsonl",
        strong_rows=[
            {
                "task_id": "governance-001",
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "trajectory_step_count": 18,
                "evidence_record_file": "with.row.json",
            },
            {
                "task_id": "easy-001",
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "trajectory_step_count": 4,
                "evidence_record_file": "with-easy.row.json",
            },
        ],
        weak_rows=[
            {
                "task_id": "governance-001",
                "status": "FAILED",
                "semantic_status": "UNVERIFIED",
                "evidence_record_file": "without.row.json",
            },
            {
                "task_id": "easy-001",
                "status": "SUCCESS",
                "semantic_status": "VERIFIED",
                "evidence_record_file": "without-easy.row.json",
            },
        ],
    )

    payloads = [row.to_dict() for row in rows]

    assert len(payloads) == 3
    assert payloads[0]["label"]["label"] == "GOLD"
    assert payloads[0]["eligible_for_training"] is True
    assert payloads[1]["task_id"] == "governance-001::weak_failure"
    assert payloads[1]["hard_negative"] is True
    assert payloads[1]["eligible_for_training"] is False
    assert payloads[2]["label"]["label"] == "SILVER"
    assert payloads[2]["low_step_filter"]["filtered"] is True
