from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping

from nexus.contracts.optimization_report import ClaimClass, RetentionClass


EVIDENCE_RETENTION_DRY_RUN_SCHEMA = "nexus_evidence_retention_dry_run.v1"
RETENTION_REPORT_PREFIXES = (
    "NEXUS_OPT_",
    "NEXUS_SF_",
    "NEXUS_7R_",
    "NEXUS_8R_",
    "NEXUS_9R_",
    "NEXUS_LEARN_",
)
RETENTION_REPORT_SUFFIXES = (".json", ".md")


@dataclass(frozen=True)
class EvidenceRetentionItem:
    source_path: str
    retention_class: RetentionClass
    reason: str
    destination_path: str = ""
    tracked: bool = False
    pinned_by_catalog: bool = False
    current_evidence: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "retention_class": self.retention_class.value,
            "reason": self.reason,
            "destination_path": self.destination_path,
            "tracked": self.tracked,
            "pinned_by_catalog": self.pinned_by_catalog,
            "current_evidence": self.current_evidence,
        }


def build_evidence_retention_dry_run(
    paths: Iterable[str],
    *,
    tracked_paths: Iterable[str] = (),
    current_evidence_paths: Iterable[str] = (),
    catalog_pinned_paths: Iterable[str] = (),
    archive_root: str = "docs/reports/archive/optimization-retention-dry-run",
    claim_class: ClaimClass | str = ClaimClass.INTERNAL_DIAGNOSTIC,
) -> dict[str, Any]:
    tracked = _path_set(tracked_paths)
    current = _path_set(current_evidence_paths)
    pinned = _path_set(catalog_pinned_paths)
    items = [
        classify_evidence_retention_path(
            path,
            tracked_paths=tracked,
            current_evidence_paths=current,
            catalog_pinned_paths=pinned,
            archive_root=archive_root,
        )
        for path in sorted(_path_set(paths))
    ]
    rows = [item.to_dict() for item in items]
    blockers = _dry_run_blockers(rows)
    return {
        "schema": EVIDENCE_RETENTION_DRY_RUN_SCHEMA,
        "status": "PASS" if not blockers else "RETURN",
        "claim_class": _claim_class(claim_class).value,
        "delete_allowed": False,
        "move_allowed": False,
        "archive_root": _normalize_path(archive_root),
        "summary": {
            "path_count": len(rows),
            "retention_class_counts": _count(row["retention_class"] for row in rows),
            "archive_candidate_count": sum(
                1 for row in rows if row["retention_class"] == RetentionClass.ARCHIVE_CANDIDATE.value
            ),
            "tracked_keep_count": sum(
                1 for row in rows if row["retention_class"] == RetentionClass.KEEP_TRACKED_SOURCE.value
            ),
            "current_evidence_keep_count": sum(1 for row in rows if row["current_evidence"]),
            "pinned_by_catalog_count": sum(1 for row in rows if row["pinned_by_catalog"]),
            "blocker_count": len(blockers),
        },
        "blockers": blockers,
        "claim_boundary": [
            "Retention dry-run is internal diagnostic only.",
            "No files are moved or deleted by this manifest.",
            "Tracked, current, catalog-pinned, and transient receipt-root artifacts are fail-closed keep rows.",
        ],
        "items": rows,
    }


def classify_evidence_retention_path(
    path: str,
    *,
    tracked_paths: set[str] | Iterable[str] = (),
    current_evidence_paths: set[str] | Iterable[str] = (),
    catalog_pinned_paths: set[str] | Iterable[str] = (),
    archive_root: str = "docs/reports/archive/optimization-retention-dry-run",
) -> EvidenceRetentionItem:
    normalized = _normalize_path(path)
    tracked = normalized in _path_set(tracked_paths)
    current = normalized in _path_set(current_evidence_paths)
    pinned = normalized in _path_set(catalog_pinned_paths)
    if _is_transient_receipt_root(normalized):
        return EvidenceRetentionItem(
            source_path=normalized,
            retention_class=RetentionClass.TRANSIENT_RECEIPT_ROOT,
            reason="transient_receipt_root_not_moved_by_report_retention",
            tracked=tracked,
            pinned_by_catalog=pinned,
            current_evidence=current,
        )
    if tracked:
        return EvidenceRetentionItem(
            source_path=normalized,
            retention_class=RetentionClass.KEEP_TRACKED_SOURCE,
            reason="tracked_source_stays_in_place",
            tracked=True,
            pinned_by_catalog=pinned,
            current_evidence=current,
        )
    if pinned:
        return EvidenceRetentionItem(
            source_path=normalized,
            retention_class=RetentionClass.PINNED_BY_CATALOG,
            reason="pinned_by_catalog_stays_in_place",
            tracked=tracked,
            pinned_by_catalog=True,
            current_evidence=current,
        )
    if current:
        return EvidenceRetentionItem(
            source_path=normalized,
            retention_class=RetentionClass.KEEP_CURRENT_EVIDENCE,
            reason="current_evidence_stays_in_place",
            tracked=tracked,
            pinned_by_catalog=pinned,
            current_evidence=True,
        )
    if _is_generated_report(normalized):
        return EvidenceRetentionItem(
            source_path=normalized,
            retention_class=RetentionClass.ARCHIVE_CANDIDATE,
            reason="untracked_generated_report_archive_candidate",
            destination_path=_archive_destination(normalized, archive_root),
            tracked=tracked,
            pinned_by_catalog=pinned,
            current_evidence=current,
        )
    return EvidenceRetentionItem(
        source_path=normalized,
        retention_class=RetentionClass.KEEP_CURRENT_EVIDENCE,
        reason="unclassified_artifact_kept_by_default",
        tracked=tracked,
        pinned_by_catalog=pinned,
        current_evidence=current,
    )


def current_evidence_paths_from_manifest(payload: Mapping[str, Any]) -> tuple[str, ...]:
    keep = payload.get("keep_artifacts", []) or []
    if not isinstance(keep, list):
        return ()
    return tuple(_normalize_path(str(item)) for item in keep if str(item).strip())


def _dry_run_blockers(rows: list[Mapping[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for row in rows:
        if row.get("retention_class") == RetentionClass.DELETE_CANDIDATE.value:
            blockers.append(f"delete_candidate_not_allowed:{row.get('source_path')}")
        if row.get("tracked") and row.get("retention_class") == RetentionClass.ARCHIVE_CANDIDATE.value:
            blockers.append(f"tracked_report_marked_archive_candidate:{row.get('source_path')}")
    return sorted(set(blockers))


def _archive_destination(path: str, archive_root: str) -> str:
    date = _date_part(PurePosixPath(path).name)
    return _normalize_path(f"{archive_root.rstrip('/')}/{date}/{PurePosixPath(path).name}")


def _date_part(name: str) -> str:
    parts = name.split("_")
    for part in reversed(parts):
        value = part.rsplit(".", 1)[0]
        if len(value) == 10 and value.count("-") == 2:
            return value
    return "undated"


def _is_generated_report(path: str) -> bool:
    name = PurePosixPath(path).name
    return name.endswith(RETENTION_REPORT_SUFFIXES) and name.startswith(RETENTION_REPORT_PREFIXES)


def _is_transient_receipt_root(path: str) -> bool:
    return path.startswith(".nexus/") or path.startswith("/private/tmp/")


def _normalize_path(path: str) -> str:
    normalized = str(PurePosixPath(path))
    if normalized.startswith("./"):
        return normalized[2:]
    return normalized


def _path_set(paths: Iterable[str]) -> set[str]:
    return {_normalize_path(str(path)) for path in paths if str(path).strip()}


def _claim_class(value: ClaimClass | str | Any) -> ClaimClass:
    if isinstance(value, ClaimClass):
        return value
    return ClaimClass(str(value))


def _count(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))
