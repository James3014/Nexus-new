#!/usr/bin/env python3
"""Validate Nexus skill catalog mount policy.

The check is intentionally strict: only repo-local Nexus curated candidates may
produce runtime mount contracts. Candidate, vendor, archive, and worktree-copy
skills must remain blocked before benchmark lanes can consume skill context.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_catalog import SkillCatalog


DEFAULT_STATUS_REPORT = Path("docs/reports/NEXUS_SKILL_STATUS_2026-05-15.json")
ARCHIVED_STATUS_REPORT = Path(
    "docs/reports/archive/sf/2026-05-15/NEXUS_SKILL_STATUS_2026-05-15.json"
)


def resolve_status_report(path: str | Path) -> Path:
    requested = Path(path)
    if requested.exists():
        return requested
    if requested == DEFAULT_STATUS_REPORT and ARCHIVED_STATUS_REPORT.exists():
        return ARCHIVED_STATUS_REPORT
    return requested


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Nexus skill catalog policy.")
    parser.add_argument(
        "--status-report",
        default=str(DEFAULT_STATUS_REPORT),
        help="Path to a nexus.skill_status.v1 JSON report.",
    )
    parser.add_argument(
        "--requested-mount",
        action="append",
        default=[],
        help="Skill id requested for runtime mount; may be repeated.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    status_report = resolve_status_report(args.status_report)
    catalog = SkillCatalog.from_status_report(status_report)
    contracts = catalog.mount_contracts()
    contract_names = [contract["skill_id"] for contract in contracts]
    contract_violations = catalog.validate_requested_mounts(contract_names)
    requested_violations = catalog.validate_requested_mounts(args.requested_mount)

    summary = {
        "status_report": str(status_report),
        "total_entries": len(catalog.entries),
        "runtime_candidate_count": len(catalog.runtime_candidates()),
        "reference_candidate_count": len(catalog.reference_candidates()),
        "quarantine_count": len(catalog.quarantined_entries()),
        "mount_contract_count": len(contracts),
        "contract_violations": [violation.to_dict() for violation in contract_violations],
        "requested_mount_violations": [
            violation.to_dict() for violation in requested_violations
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if contract_violations or requested_violations else 0


if __name__ == "__main__":
    sys.exit(main())
