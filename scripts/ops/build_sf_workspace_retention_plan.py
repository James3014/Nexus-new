#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_REPORTS_DIR = Path("docs/reports")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_SF_WORKSPACE_RETENTION_PLAN_2026-05-19.json")
DEFAULT_ARCHIVE_ROOT = Path("docs/reports/archive/sf")


KEEP_PATTERNS = (
    "NEXUS_SF_FINAL_CLOSURE_V16_2026-05-19",
    "NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V16_2026-05-19",
    "NEXUS_SF_POST_APPLY_POLICY_SMOKE_V16_2026-05-19",
    "NEXUS_SF_RUNTIME_RECEIPT_SMOKE_V16_2026-05-19",
    "NEXUS_SF_V16_RESIDUAL_SELECTION",
    "NEXUS_SF_V15_HELD_CHALLENGER",
    "NEXUS_SF_RUNTIME_PROMOTION_REVIEW_V15_2026-05-19",
    "NEXUS_SF_RUNTIME_POLICY_PATCH_PLAN_V15_2026-05-19",
    "NEXUS_SF_RUNTIME_POLICY_APPLY_GATE_V15_2026-05-19",
    "NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V15_2026-05-19",
    "NEXUS_SF_WORKSPACE_CLEANUP_INDEX_2026-05-19",
    "NEXUS_SF_WORKSPACE_RETENTION_PLAN_2026-05-19",
    "NEXUS_SF_WORKSPACE_RETENTION_APPLY_RESULT_2026-05-19",
)

REPORT_PREFIXES = (
    "NEXUS_SF_",
    "NEXUS_SKILL_",
    "NEXUS_CAPABILITY_SKILL_",
    "NEXUS_RESEARCH_",
    "NEXUS_GOVERNANCE_",
    "NEXUS_FAIR_SKILL_",
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _report_date(path: Path) -> str:
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", path.name)
    return match.group(1) if match else "undated"


def _referenced_paths(payload: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(payload, dict):
        for value in payload.values():
            refs.update(_referenced_paths(value))
    elif isinstance(payload, list):
        for value in payload:
            refs.update(_referenced_paths(value))
    elif isinstance(payload, str):
        if "docs/reports/" in payload or "/private/tmp/" in payload:
            refs.add(payload)
    return refs


def _keep_by_name(path: Path) -> bool:
    return any(pattern in path.name for pattern in KEEP_PATTERNS)


def _tracked_files(root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", str(root)],
        check=False,
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def build_plan(
    *,
    reports_dir: Path,
    archive_root: Path,
    latest_closure: Path,
    latest_overlay: Path,
) -> dict[str, Any]:
    keep_refs: set[str] = set()
    tracked = _tracked_files(reports_dir)
    for path in (latest_closure, latest_overlay):
        if path.exists() and path.suffix == ".json":
            keep_refs.add(str(path))
            keep_refs.add(str(path.resolve()))
            keep_refs.update(_referenced_paths(_read_json(path)))

    items: list[dict[str, Any]] = []
    blockers: list[str] = []
    sources = []
    for prefix in REPORT_PREFIXES:
        sources.extend(reports_dir.glob(f"{prefix}*"))
    for source in sorted(set(sources)):
        if not source.is_file():
            continue
        source_ref = str(source)
        source_abs = str(source.resolve())
        if source_ref in tracked:
            disposition = "keep_current_evidence"
            destination = ""
            reason = "tracked_report_not_moved_by_retention_plan"
        elif _keep_by_name(source) or source_ref in keep_refs or source_abs in keep_refs:
            disposition = "keep_current_evidence"
            destination = ""
            reason = "current_closure_or_direct_reference"
        else:
            disposition = "archive_candidate"
            date = _report_date(source)
            destination_path = archive_root / date / source.name
            destination = str(destination_path)
            reason = "superseded_sf_report_not_referenced_by_latest_closure_or_overlay"
            if destination_path.exists():
                blockers.append(f"{source}:destination_exists")
        items.append(
            {
                "source": str(source),
                "destination": destination,
                "disposition": disposition,
                "reason": reason,
            }
        )
    counts = Counter(item["disposition"] for item in items)
    return {
        "schema": "nexus.sf_workspace_retention_plan.v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "summary": {
            "reports_scanned": len(items),
            "keep_current_evidence": counts.get("keep_current_evidence", 0),
            "archive_candidate": counts.get("archive_candidate", 0),
            "blocker_count": len(blockers),
            "destructive_delete_allowed": False,
        },
        "latest_closure": str(latest_closure),
        "latest_overlay": str(latest_overlay),
        "archive_root": str(archive_root),
        "blockers": sorted(blockers),
        "items": items,
        "claim_boundary": [
            "This plan never deletes SF evidence.",
            "Archive mode only moves superseded docs/reports files that are not directly referenced by the latest closure or overlay.",
            "Private tmp receipt roots are not moved by this report-retention plan.",
        ],
    }


def apply_plan(plan: dict[str, Any], *, mode: str) -> dict[str, Any]:
    if mode not in {"dry-run", "archive"}:
        raise ValueError(f"unsupported mode: {mode}")
    results: list[dict[str, Any]] = []
    blockers: list[str] = []
    for item in plan.get("items", []):
        if item.get("disposition") != "archive_candidate":
            continue
        source = Path(str(item.get("source") or ""))
        destination = Path(str(item.get("destination") or ""))
        result = {"source": str(source), "destination": str(destination), "mode": mode}
        if not source.exists():
            result.update({"status": "SKIPPED", "reason": "source_missing"})
        elif destination.exists():
            result.update({"status": "BLOCKED", "reason": "destination_exists"})
            blockers.append(f"{source}:destination_exists")
        elif mode == "dry-run":
            result.update({"status": "WOULD_MOVE", "reason": "dry_run"})
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            result.update({"status": "MOVED", "reason": "archived_superseded_report"})
        results.append(result)
    counts = Counter(item["status"] for item in results)
    return {
        "schema": "nexus.sf_workspace_retention_apply_result.v1",
        "status": "PASS" if not blockers else "BLOCKED",
        "summary": {
            "mode": mode,
            "result_count": len(results),
            "status_counts": dict(sorted(counts.items())),
            "blocker_count": len(blockers),
        },
        "blockers": sorted(blockers),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or apply a non-destructive SF workspace report-retention plan.")
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    parser.add_argument("--archive-root", default=str(DEFAULT_ARCHIVE_ROOT))
    parser.add_argument("--latest-closure", default="docs/reports/NEXUS_SF_FINAL_CLOSURE_V16_2026-05-19.json")
    parser.add_argument("--latest-overlay", default="docs/reports/NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_V16_2026-05-19.json")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--apply-result-output", default="docs/reports/NEXUS_SF_WORKSPACE_RETENTION_APPLY_RESULT_2026-05-19.json")
    parser.add_argument("--mode", choices=("dry-run", "archive"), default="dry-run")
    args = parser.parse_args()

    plan = build_plan(
        reports_dir=Path(args.reports_dir),
        archive_root=Path(args.archive_root),
        latest_closure=Path(args.latest_closure),
        latest_overlay=Path(args.latest_overlay),
    )
    _write_json(Path(args.output), plan)
    result = apply_plan(plan, mode=args.mode)
    _write_json(Path(args.apply_result_output), result)
    print(
        json.dumps(
            {
                "plan_status": plan["status"],
                "apply_status": result["status"],
                "mode": args.mode,
                **plan["summary"],
                "apply": result["summary"],
            },
            sort_keys=True,
            ensure_ascii=False,
        )
    )
    return 0 if plan["status"] == "PASS" and result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
