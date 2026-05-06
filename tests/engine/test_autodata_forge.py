from __future__ import annotations

import json

from nexus.engine.autodata_forge import DataForgeManifestRow, classify_trajectory_quality, write_data_forge_manifest


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
    assert payload["rows"][1]["eligible_for_training"] is True
