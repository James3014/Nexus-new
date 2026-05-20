#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import read_json, write_json


DEFAULT_APPLY_GATE = Path("docs/reports/NEXUS_HEEP_RUNTIME_APPLY_GATE_2026-05-20.json")
DEFAULT_SKILL_STATUS = Path("docs/reports/NEXUS_HEEP_FLASH_NEXUS_SKILL_STATUS_2026-05-20.json")
DEFAULT_OUTPUT = Path("docs/reports/NEXUS_HEEP_RUNTIME_CURATION_STATUS_2026-05-20.json")

DANGEROUS_TEXT_PATTERNS = (
    "rm -rf",
    "curl ",
    "wget ",
    "/etc/passwd",
    "ssh-key",
    "GITHUB_TOKEN",
)


def _skills_required_by_gate(apply_gate: Mapping[str, Any]) -> list[str]:
    skill_ids: set[str] = set()
    for case in apply_gate.get("cases", []) or []:
        if not isinstance(case, Mapping):
            continue
        for skill_id in case.get("skill_ids", []) or []:
            if str(skill_id):
                skill_ids.add(str(skill_id))
    return sorted(skill_ids)


def _status_by_skill(skill_status: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("name") or ""): dict(row)
        for row in skill_status.get("skills", []) or []
        if isinstance(row, Mapping) and row.get("name")
    }


def _screen_skill(row: Mapping[str, Any], *, repo_root: Path) -> tuple[str, list[str]]:
    blockers: list[str] = []
    raw_path = str(row.get("path") or "")
    path = repo_root / raw_path
    normalized = raw_path.replace("\\", "/")
    if not normalized.startswith(".agents/skills/"):
        blockers.append("not_repo_local_agents_skill")
    if "candidate-skill-from-" in normalized or "auto-gen-" in normalized:
        blockers.append("generated_or_candidate_inbox_skill")
    if ".codexworktrees" in normalized or "archived" in normalized or "vendor" in normalized:
        blockers.append("quarantine_or_vendor_path")
    if path.name != "SKILL.md":
        blockers.append("not_skill_md")
    if not path.exists():
        blockers.append("skill_file_missing")
        return raw_path, blockers
    text = path.read_text(encoding="utf-8", errors="ignore")
    for pattern in DANGEROUS_TEXT_PATTERNS:
        if pattern in text:
            blockers.append(f"dangerous_text_pattern:{pattern.strip()}")
    if not text.strip():
        blockers.append("empty_skill_md")
    return raw_path, blockers


def build_heep_runtime_curation_status(
    *,
    apply_gate: Mapping[str, Any],
    skill_status: Mapping[str, Any],
    repo_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    source_rows = _status_by_skill(skill_status)
    curated_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for skill_id in _skills_required_by_gate(apply_gate):
        source = source_rows.get(skill_id)
        if source is None:
            blockers.append(f"{skill_id}:missing_from_skill_status_report")
            review_rows.append({"skill_id": skill_id, "status": "BLOCKED", "blockers": ["missing_from_skill_status_report"]})
            continue
        path, row_blockers = _screen_skill(source, repo_root=repo_root)
        status = "PASS" if not row_blockers else "BLOCKED"
        if row_blockers:
            blockers.extend(f"{skill_id}:{reason}" for reason in row_blockers)
        else:
            curated = dict(source)
            curated.update(
                {
                    "skill_status": "nexus_curated_candidate",
                    "test_level": "runtime_reviewed",
                    "action": "heep_runtime_apply_review_only",
                    "reason_codes": [
                        "mat_b_approved",
                        "repo_local_skill_path",
                        "safe_surface_scan_pass",
                        "runtime_apply_review_only",
                    ],
                }
            )
            curated_rows.append(curated)
        review_rows.append({"skill_id": skill_id, "path": path, "status": status, "blockers": row_blockers})
    return {
        "schema": "nexus.heep_runtime_curation_status.v1",
        "status": "PASS" if curated_rows and not blockers else "RETURN",
        "created_at": datetime.now(UTC).isoformat(),
        "summary": {
            "required_skill_count": len(_skills_required_by_gate(apply_gate)),
            "curated_skill_count": len(curated_rows),
            "blocker_count": len(sorted(set(blockers))),
            "runtime_update_allowed": False,
            "public_benchmark_allowed": False,
        },
        "blockers": sorted(set(blockers)),
        "skills": sorted(curated_rows, key=lambda item: str(item.get("name") or "")),
        "review_rows": review_rows,
        "claim_boundary": [
            "This report is runtime apply review input only.",
            "It does not update runtime defaults.",
            "Public benchmark remains blocked.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build reviewed HEEP skill status for runtime apply gate input.")
    parser.add_argument("--apply-gate", default=str(DEFAULT_APPLY_GATE))
    parser.add_argument("--skill-status-report", default=str(DEFAULT_SKILL_STATUS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args(argv)
    report = build_heep_runtime_curation_status(
        apply_gate=read_json(args.apply_gate),
        skill_status=read_json(args.skill_status_report),
    )
    write_json(args.output, report)
    print(json.dumps({"status": report["status"], "output": args.output, **report["summary"]}, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
