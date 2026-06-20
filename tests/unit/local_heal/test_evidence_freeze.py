import pytest
from nexus.services.local_heal.evidence_freeze import (
    classify_file,
    build_freeze_report,
    build_clean_replay_manifest,
)


def test_classify_source_file():
    fc = classify_file("nexus/engine/local_model_policy.py")
    assert fc.category == "source"
    assert fc.can_claim


def test_classify_test_file():
    fc = classify_file("tests/unit/test_local_model_policy.py")
    assert fc.category == "tests"
    assert fc.can_claim


def test_classify_pycache():
    fc = classify_file("nexus/experimental/__pycache__/__init__.cpython-314.pyc")
    assert fc.category == "pycache_build"
    assert not fc.can_claim


def test_classify_doc_report():
    fc = classify_file("docs/reports/some_report.json")
    assert fc.category == "docs_reports"
    assert not fc.can_claim


def test_classify_artifact():
    fc = classify_file("artifacts/runtime/some_artifact.json")
    assert fc.category == "generated_artifacts"
    assert not fc.can_claim


def test_classify_benchmark():
    fc = classify_file("benchmarks/some_bench.py")
    assert fc.category == "benchmarks"
    assert not fc.can_claim


def test_classify_script():
    fc = classify_file("scripts/bench/evidence_bundle_gates.py")
    assert fc.category == "scripts"
    assert fc.can_claim


def test_classify_config():
    fc = classify_file("pyproject.toml")
    assert fc.category == "config"
    assert not fc.can_claim


def test_classify_other():
    fc = classify_file("some_random_file.xyz")
    assert fc.category == "other"
    assert not fc.can_claim


def test_build_freeze_report_summary():
    report = build_freeze_report(".")
    summary = report.summary()
    assert "total_dirty" in summary
    assert "claimable" in summary
    assert "non_claimable" in summary
    assert "by_category" in summary
    assert summary["total_dirty"] == summary["claimable"] + summary["non_claimable"]


def test_build_clean_replay_manifest():
    report = build_freeze_report(".")
    manifest = build_clean_replay_manifest(
        candidate_ids=["astropy__astropy-13236", "sympy__sympy-13852"],
        freeze_report=report,
    )
    assert manifest["public_claim_allowed"] is False
    assert manifest["claim_type"] == "internal_evidence_only"
    assert len(manifest["candidates"]) == 2
    assert "source_files_changed" in manifest["replay_constraints"]
    assert "test_files_changed" in manifest["replay_constraints"]
    assert "must_not_include" in manifest["replay_constraints"]


def test_freeze_report_classifications_match_total():
    report = build_freeze_report(".")
    assert len(report.classifications) == report.total_dirty
