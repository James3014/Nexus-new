from __future__ import annotations

from nexus.contracts.evidence_retention import (
    EVIDENCE_UNION_MERGE_GUARD_SCHEMA,
    build_evidence_union_merge_guard,
    build_evidence_retention_dry_run,
    classify_evidence_retention_path,
    current_evidence_paths_from_manifest,
)
from nexus.contracts.optimization_report import ClaimClass, RetentionClass


def test_tracked_report_is_kept_even_when_generated() -> None:
    item = classify_evidence_retention_path(
        "docs/reports/NEXUS_OPT_PLAN_2026-05-20.md",
        tracked_paths={"docs/reports/NEXUS_OPT_PLAN_2026-05-20.md"},
    )

    assert item.retention_class == RetentionClass.KEEP_TRACKED_SOURCE
    assert item.tracked is True
    assert item.destination_path == ""


def test_current_manifest_paths_are_kept() -> None:
    item = classify_evidence_retention_path(
        "docs/reports/NEXUS_SF_FINAL_CURRENT_STATE_2026-05-20.md",
        current_evidence_paths={"docs/reports/NEXUS_SF_FINAL_CURRENT_STATE_2026-05-20.md"},
    )

    assert item.retention_class == RetentionClass.KEEP_CURRENT_EVIDENCE
    assert item.current_evidence is True
    assert item.reason == "current_evidence_stays_in_place"


def test_catalog_pinned_paths_use_separate_retention_class() -> None:
    item = classify_evidence_retention_path(
        "docs/reports/NEXUS_SF_CAPABILITY_PRIMARY_ORIGINAL_SKILL_MAP_2026-05-20.json",
        catalog_pinned_paths={"docs/reports/NEXUS_SF_CAPABILITY_PRIMARY_ORIGINAL_SKILL_MAP_2026-05-20.json"},
    )

    assert item.retention_class == RetentionClass.PINNED_BY_CATALOG
    assert item.pinned_by_catalog is True


def test_untracked_generated_report_is_archive_candidate() -> None:
    item = classify_evidence_retention_path("docs/reports/NEXUS_OPT_TEMP_2026-05-20.json")

    assert item.retention_class == RetentionClass.ARCHIVE_CANDIDATE
    assert item.destination_path == (
        "docs/reports/archive/optimization-retention-dry-run/2026-05-20/"
        "NEXUS_OPT_TEMP_2026-05-20.json"
    )


def test_transient_receipt_roots_are_not_moved() -> None:
    item = classify_evidence_retention_path(".nexus/receipts/run-001.json")

    assert item.retention_class == RetentionClass.TRANSIENT_RECEIPT_ROOT
    assert item.destination_path == ""


def test_retention_dry_run_never_allows_delete_or_move() -> None:
    manifest = build_evidence_retention_dry_run(
        [
            "docs/reports/NEXUS_OPT_TEMP_2026-05-20.json",
            "docs/reports/NEXUS_SF_FINAL_CURRENT_STATE_2026-05-20.md",
            ".nexus/receipts/run-001.json",
        ],
        current_evidence_paths={"docs/reports/NEXUS_SF_FINAL_CURRENT_STATE_2026-05-20.md"},
        claim_class=ClaimClass.INTERNAL_DIAGNOSTIC,
    )

    assert manifest["status"] == "PASS"
    assert manifest["claim_class"] == ClaimClass.INTERNAL_DIAGNOSTIC.value
    assert manifest["delete_allowed"] is False
    assert manifest["move_allowed"] is False
    assert manifest["summary"]["archive_candidate_count"] == 1
    assert manifest["summary"]["current_evidence_keep_count"] == 1
    assert manifest["summary"]["blocker_count"] == 0


def test_current_evidence_paths_from_manifest_ignores_invalid_shape() -> None:
    assert current_evidence_paths_from_manifest({"keep_artifacts": "not-a-list"}) == ()
    assert current_evidence_paths_from_manifest(
        {"keep_artifacts": ["./docs/reports/NEXUS_SF_FINAL_CURRENT_STATE_2026-05-20.md"]}
    ) == ("docs/reports/NEXUS_SF_FINAL_CURRENT_STATE_2026-05-20.md",)


def test_union_merge_guard_passes_for_bounded_append_only_evidence() -> None:
    guard = build_evidence_union_merge_guard(
        path="docs/reports/evidence_bundle.json",
        append_only=True,
        file_size_bytes=1024,
        node_count=20,
    )

    assert guard["schema"] == EVIDENCE_UNION_MERGE_GUARD_SCHEMA
    assert guard["status"] == "PASS"
    assert guard["runtime_update_allowed"] is False
    assert guard["public_benchmark_allowed"] is False
    assert guard["delete_allowed"] is False
    assert guard["move_allowed"] is False


def test_union_merge_guard_blocks_unbounded_or_non_commutative_merge() -> None:
    guard = build_evidence_union_merge_guard(
        path="docs/reports/evidence_bundle.json",
        append_only=False,
        commutative=False,
        file_size_bytes=51 * 1024 * 1024,
        node_count=100_001,
        schema_validation_status="RETURN",
    )

    assert guard["status"] == "RETURN"
    assert guard["blockers"] == [
        "merge_file_size_over_limit",
        "merge_node_count_over_limit",
        "merge_requires_append_only_or_commutative_shape",
        "merge_schema_validation_not_pass",
    ]
