#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from scripts.ops.report_output import resolve_report_output


DEFAULT_REPORTS_DIR = Path("docs/reports")
DEFAULT_JSON_OUTPUT = Path("docs/reports/NEXUS_REPORT_RETENTION_INVENTORY_2026-05-22.json")
DEFAULT_MD_OUTPUT = Path("docs/reports/NEXUS_REPORT_RETENTION_PLAN_2026-05-22.md")

ACTIVE_WORKSTREAM_PATTERNS = ("ZERO_TRUST", "zero_trust")

CURRENT_KEEP_FILES = {
    "NEXUS_SF_FINAL_CURRENT_STATE_2026-05-20.md",
    "NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_2026-05-20.json",
    "NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_2026-05-20.md",
    "NEXUS_SF_RUNTIME_SKILL_POLICY_OVERLAY_CURRENT_SMOKE_2026-05-20.json",
    "NEXUS_SF_SYSTEMATIC_FINALIZATION_V32_2026-05-19.json",
    "NEXUS_SF_SYSTEMATIC_FINALIZATION_V32_2026-05-19.md",
    "NEXUS_SF_SYSTEMATIC_ALL_CAPABILITY_LIVE_ROLLUP_V32_2026-05-19.json",
    "NEXUS_SF_SYSTEMATIC_ALL_CAPABILITY_LIVE_ROLLUP_V32_2026-05-19.md",
    "NEXUS_SF_WORKSPACE_RETENTION_CURRENT_MANIFEST_2026-05-20.json",
    "NEXUS_SF_FINAL_RUNTIME_APPLY_DECISION_2026-05-21.json",
    "NEXUS_SF_FINAL_RUNTIME_SKILL_POLICY_OVERLAY_APPLIED_2026-05-21.json",
    "NEXUS_SF_FINAL_RUNTIME_SKILL_STATUS_MERGED_2026-05-21.json",
    "NEXUS_SF_FINAL_RUNTIME_POST_APPLY_SMOKE_2026-05-21.json",
    "NEXUS_HEEP_RUNTIME_APPLY_GATE_REVIEWED_2026-05-20.json",
    "NEXUS_HEEP_RUNTIME_APPLY_REVIEW_PACKET_V2_2026-05-20.json",
    "NEXUS_HEEP_MAT_B_FINAL_SKILL_DECISIONS_2026-05-20.json",
    "NEXUS_OPTIMIZATION_ARTIFACT_INDEX_2026-05-20.md",
    "NEXUS_PUBLICATION_READY_12X2_SUMMARY_2026-05-20.md",
    "NEXUS_WORKSPACE_NON_SF_RETENTION_2026-05-19.json",
}

RAW_HINTS = (
    "EXECUTION_MATRIX",
    "LIVE_COMPARE_MATRIX",
    "CANDIDATE_CLASSIFICATION",
    "COMPILED_INTERFACES",
    "SUCCESSIVE_HALVING",
    "TASK_MANIFEST",
    "TASKS",
    "QUEUE",
    "SKILL_STATUS",
    "CATALOG",
    "ROLLUP",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _date_from_name(path: Path) -> str:
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", path.name)
    return match.group(1) if match else "undated"


def _is_active_workstream(path: Path) -> bool:
    text = path.as_posix()
    return any(pattern in text for pattern in ACTIVE_WORKSTREAM_PATTERNS)


def _topic(path: Path) -> str:
    name = path.name
    if name.startswith("NEXUS_SF") or name.startswith("NEXUS_SKILL_FIT") or name.startswith("NEXUS_FAIR_SKILL"):
        return "SF"
    if name.startswith("NEXUS_HEEP"):
        return "HEEP"
    if "OPT" in name or "OPTIMIZATION" in name:
        return "OPTIMIZATION"
    if "PUBLIC" in name or "CLAIM" in name or "VALUE" in name:
        return "PUBLIC_CLAIM"
    if "REFACTOR" in name or "CLEAN_CODE" in name or "ENGINEERING_HYGIENE" in name:
        return "ENGINEERING_HYGIENE"
    if name.startswith(("FLASH_", "GEMINI", "GPT55", "IRON_", "ROUTING_", "MAIN_")):
        return "LEGACY"
    return "UNKNOWN_HOLD"


def _retention_class(path: Path, *, keep_refs: set[str]) -> tuple[str, str]:
    name = path.name
    ref = path.as_posix()
    if name in CURRENT_KEEP_FILES or ref in keep_refs:
        return "keep_current_entrypoint", "listed_current_or_manifest_referenced"
    if path.suffix == ".md" and any(token in name for token in ("SUMMARY", "INDEX", "PLAN", "CURRENT_STATE", "FINALIZATION")):
        return "keep_human_entrypoint", "human_readable_summary_or_plan"
    if path.suffix == ".json" and any(token in name for token in RAW_HINTS):
        return "archive_candidate", "raw_matrix_or_generated_evidence_candidate"
    if _topic(path) == "UNKNOWN_HOLD":
        return "unknown_hold", "no_safe_automatic_classification"
    return "keep_review", "topic_currentness_needs_owner_review"


def _manifest_keep_refs(reports_dir: Path) -> set[str]:
    refs: set[str] = set()
    manifest = reports_dir / "NEXUS_SF_WORKSPACE_RETENTION_CURRENT_MANIFEST_2026-05-20.json"
    if not manifest.exists():
        return refs
    payload = _read_json(manifest)
    for artifact in payload.get("keep_artifacts", []):
        if isinstance(artifact, str):
            refs.add(artifact)
            refs.add(str(Path(artifact).name))
    return refs


def build_inventory(*, reports_dir: Path = DEFAULT_REPORTS_DIR) -> dict[str, Any]:
    keep_refs = _manifest_keep_refs(reports_dir)
    rows: list[dict[str, Any]] = []
    excluded: list[str] = []
    for path in sorted(reports_dir.iterdir()):
        if not path.is_file():
            continue
        if _is_active_workstream(path):
            excluded.append(path.as_posix())
            continue
        retention_class, reason = _retention_class(path, keep_refs=keep_refs)
        stat = path.stat()
        rows.append(
            {
                "path": path.as_posix(),
                "name": path.name,
                "topic": _topic(path),
                "date": _date_from_name(path),
                "extension": path.suffix.lstrip(".") or "none",
                "size_bytes": stat.st_size,
                "retention_class": retention_class,
                "reason": reason,
                "action": "no_move_no_delete_inventory_only",
            }
        )

    by_class = Counter(row["retention_class"] for row in rows)
    by_topic = Counter(row["topic"] for row in rows)
    return {
        "schema": "nexus.report_retention_inventory.v1",
        "status": "PASS",
        "claim_class": "PLAN_ONLY",
        "destructive_delete_allowed": False,
        "excluded_active_workstreams": ["ZERO_TRUST_V2"],
        "summary": {
            "reports_dir": reports_dir.as_posix(),
            "rows": len(rows),
            "excluded_active_workstream_count": len(excluded),
            "retention_class_counts": dict(sorted(by_class.items())),
            "topic_counts": dict(sorted(by_topic.items())),
        },
        "excluded_active_workstream_paths": excluded,
        "rows": rows,
        "claim_boundary": [
            "This inventory does not move, delete, stage, or archive files.",
            "ZERO_TRUST_V2 artifacts are excluded because another agent is actively writing that workstream.",
            "Archive candidates require a separate owner-approved filesystem move plan before any action.",
        ],
    }


def render_markdown(inventory: dict[str, Any], *, title: str = "Nexus Report Retention Plan - 2026-05-22") -> str:
    summary = inventory["summary"]
    rows = list(inventory["rows"])
    archive_candidates = [row for row in rows if row["retention_class"] == "archive_candidate"]
    keep_rows = [row for row in rows if row["retention_class"].startswith("keep_")]
    unknown_rows = [row for row in rows if row["retention_class"] == "unknown_hold"]

    lines = [
        f"# {title}",
        "",
        "## Scope",
        "- Plan-only report retention inventory.",
        "- Excludes active `ZERO_TRUST_V2` artifacts.",
        "- No files are moved, deleted, staged, or archived by this artifact.",
        "",
        "## Summary",
        f"- Reports scanned: `{summary['rows']}`",
        f"- Active Zero Trust V2 reports excluded: `{summary['excluded_active_workstream_count']}`",
        f"- Retention class counts: `{summary['retention_class_counts']}`",
        f"- Topic counts: `{summary['topic_counts']}`",
        "",
        "## Keep Rules",
        "- Keep current decision, runtime apply, post-apply smoke, and human-readable summary/index files at `docs/reports` root.",
        "- Keep files referenced by `NEXUS_SF_WORKSPACE_RETENTION_CURRENT_MANIFEST_2026-05-20.json`.",
        "- Treat raw matrices, task manifests, queues, catalogs, and rollups as archive candidates only after owner review.",
        "",
        "## Current Entrypoints",
    ]
    for row in keep_rows[:40]:
        lines.append(f"- `{row['path']}` ({row['topic']}, {row['retention_class']})")
    if len(keep_rows) > 40:
        lines.append(f"- ... plus `{len(keep_rows) - 40}` more keep/review rows in the JSON inventory.")

    lines.extend(["", "## Archive Candidates"])
    for row in archive_candidates[:60]:
        lines.append(f"- `{row['path']}` ({row['topic']}, {row['size_bytes']} bytes)")
    if len(archive_candidates) > 60:
        lines.append(f"- ... plus `{len(archive_candidates) - 60}` more archive candidates in the JSON inventory.")

    lines.extend(["", "## Unknown Hold"])
    for row in unknown_rows[:40]:
        lines.append(f"- `{row['path']}` ({row['size_bytes']} bytes)")
    if len(unknown_rows) > 40:
        lines.append(f"- ... plus `{len(unknown_rows) - 40}` more unknown rows in the JSON inventory.")

    lines.extend(
        [
            "",
            "## Execution Gates",
            "- Do not move Zero Trust V2 files while that agent is active.",
            "- Do not use `git mv` for report retention cleanup.",
            "- Move at most 10 files per later cleanup slice.",
            "- Re-run `git status --short` and reference checks after each later move slice.",
            "",
            "## Claim Boundary",
        ]
    )
    for boundary in inventory["claim_boundary"]:
        lines.append(f"- {boundary}")
    lines.append("")
    return "\n".join(lines)


def write_inventory(
    *,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    json_output: Path = DEFAULT_JSON_OUTPUT,
    md_output: Path = DEFAULT_MD_OUTPUT,
    dry_run: bool = False,
) -> dict[str, Any]:
    inventory = build_inventory(reports_dir=reports_dir)
    if not dry_run:
        _write_json(json_output, inventory)
        md_output.parent.mkdir(parents=True, exist_ok=True)
        md_output.write_text(render_markdown(inventory), encoding="utf-8")
    return {
        "status": inventory["status"],
        "dry_run": dry_run,
        "json_output": json_output.as_posix(),
        "md_output": md_output.as_posix(),
        **inventory["summary"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a non-destructive Nexus report-retention inventory.")
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--json-output", type=Path, default=None)
    parser.add_argument("--md-output", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path(""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    output_dir = args.output_dir if str(args.output_dir) not in {"", "."} else None
    json_output = resolve_report_output(DEFAULT_JSON_OUTPUT, output=args.json_output, output_dir=output_dir)
    md_output = resolve_report_output(DEFAULT_MD_OUTPUT, output=args.md_output, output_dir=output_dir)
    summary = write_inventory(
        reports_dir=args.reports_dir,
        json_output=json_output,
        md_output=md_output,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, sort_keys=True, ensure_ascii=False))
    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
