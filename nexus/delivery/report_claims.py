from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ReportClaimsOptions:
    required_paths: list[str]
    require_clean: bool
    ignore_dirty_paths: list[str]
    require_acceptance_pass: bool
    acceptance_report_rel: str
    require_baseline: bool
    baseline_manifest_rel: str
    report_file_rel: str | None


def resolve_required_paths(project_root: Path, required_paths: list[str]) -> list[Path]:
    resolved: list[Path] = []
    for raw in required_paths:
        p = Path(raw)
        if not p.is_absolute():
            p = (project_root / p).resolve()
        resolved.append(p)
    return resolved


def parse_porcelain_paths(raw_status: str) -> list[str]:
    paths: list[str] = []
    for line in raw_status.splitlines():
        if not line.strip():
            continue
        if len(line) >= 3 and line[2] == " ":
            path = line[3:]
        elif len(line) >= 2 and line[1] == " ":
            path = line[2:]
        else:
            path = line
        path = path.strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        paths.append(path)
    return paths


def load_ignore_dirty_paths(project_root: Path, config_path: str | None) -> list[str]:
    if not config_path:
        return []
    path = Path(config_path)
    if not path.is_absolute():
        path = (project_root / path).resolve()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if isinstance(data, list):
        return [str(item) for item in data if str(item).strip()]
    if isinstance(data, dict):
        raw = data.get("ignore_dirty_paths", [])
        if isinstance(raw, list):
            return [str(item) for item in raw if str(item).strip()]
    return []


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def sorted_nonempty_lines(raw: str) -> list[str]:
    return sorted([line.strip() for line in raw.splitlines() if line.strip()])


def evaluate_report_integrity_lock(
    project_root: Path, report_file_rel: str | None, run_git: Any
) -> dict[str, Any]:
    if not report_file_rel:
        return {"name": "report_integrity_lock", "passed": True, "detail": {"skipped": True}}

    report_path = Path(report_file_rel)
    if not report_path.is_absolute():
        report_path = (project_root / report_path).resolve()

    detail: dict[str, Any] = {"path": str(report_path), "exists": report_path.exists()}
    if not report_path.exists():
        detail["error"] = "report_file_not_found"
        return {"name": "report_integrity_lock", "passed": False, "detail": detail}

    report = read_json(report_path)
    head_sha = str(report.get("head_sha", "")).strip()
    if not head_sha:
        detail["error"] = "missing_report_head_sha"
        return {"name": "report_integrity_lock", "passed": False, "detail": detail}

    actual_head = run_git(project_root, ["rev-parse", "--short", "HEAD"]).strip()
    head_ok = bool(actual_head) and actual_head == head_sha
    detail["head_alignment"] = {"passed": head_ok, "report_head_sha": head_sha, "actual_head_sha": actual_head}

    reported_commit_files = sorted([str(v).strip() for v in report.get("files_changed_in_this_commit", []) if str(v).strip()])
    actual_commit_files = sorted_nonempty_lines(run_git(project_root, ["show", "--name-only", "--pretty=format:", "HEAD"]))
    commit_ok = reported_commit_files == actual_commit_files
    detail["commit_integrity"] = {
        "passed": commit_ok,
        "reported_files": reported_commit_files,
        "actual_files": actual_commit_files,
    }

    base_branch = str(report.get("base_branch", "main")).strip() or "main"
    reported_delta = sorted([str(v).strip() for v in report.get("branch_delta_vs_base", []) if str(v).strip()])
    actual_delta = sorted_nonempty_lines(run_git(project_root, ["diff", "--name-only", f"{base_branch}...HEAD"]))
    delta_ok = reported_delta == actual_delta
    detail["branch_delta_integrity"] = {
        "passed": delta_ok,
        "base_branch": base_branch,
        "reported_delta": reported_delta,
        "actual_delta": actual_delta,
    }

    return {"name": "report_integrity_lock", "passed": head_ok and commit_ok and delta_ok, "detail": detail}


def verify_claims_core(project_root: Path, options: ReportClaimsOptions, run_git: Any) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    branch = run_git(project_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    commit = run_git(project_root, ["rev-parse", "--short", "HEAD"])
    checks.append(
        {
            "name": "git_context",
            "passed": bool(branch and commit),
            "detail": {"branch": branch or "unknown", "commit": commit or "unknown"},
        }
    )

    baseline_path = (project_root / options.baseline_manifest_rel).resolve()
    baseline_ok = True
    baseline_detail = {"path": str(baseline_path), "exists": baseline_path.exists()}
    if options.require_baseline:
        if not baseline_path.exists():
            baseline_ok = False
        else:
            data = read_json(baseline_path)
            baseline_detail["version"] = data.get("version")
            baseline_detail["generated_by_sha"] = data.get("generated_by_sha")
            if not baseline_detail["version"] or not baseline_detail["generated_by_sha"]:
                baseline_ok = False
                baseline_detail["error"] = "missing_schema_fields"
    checks.append({"name": "baseline_manifest", "passed": baseline_ok, "detail": baseline_detail})

    dirty = run_git(project_root, ["status", "--porcelain"])
    dirty_paths = parse_porcelain_paths(dirty)
    ignored_resolved = {str(p) for p in resolve_required_paths(project_root, options.ignore_dirty_paths)}
    effective_dirty: list[str] = []
    for rel_path in dirty_paths:
        resolved = project_root / rel_path
        if str(resolved.resolve()) in ignored_resolved:
            continue
        effective_dirty.append(rel_path)
    checks.append(
        {
            "name": "working_tree",
            "passed": (not effective_dirty) if options.require_clean else True,
            "detail": {
                "require_clean": options.require_clean,
                "dirty_entries": len(dirty_paths),
                "effective_dirty_entries": len(effective_dirty),
                "ignored_dirty_paths": sorted(options.ignore_dirty_paths),
                "effective_dirty_paths": effective_dirty,
            },
        }
    )

    resolved_paths = resolve_required_paths(project_root, options.required_paths)
    missing = [str(p) for p in resolved_paths if not p.exists()]
    checks.append(
        {
            "name": "required_paths",
            "passed": not missing,
            "detail": {"required_count": len(resolved_paths), "missing": missing},
        }
    )

    acceptance_report = (project_root / options.acceptance_report_rel).resolve()
    acceptance_ok = True
    acceptance_detail: dict[str, Any] = {
        "path": str(acceptance_report),
        "exists": acceptance_report.exists(),
        "status": "unknown",
        "gate_passed": None,
        "require_acceptance_pass": options.require_acceptance_pass,
    }
    if options.require_acceptance_pass:
        if not acceptance_report.exists():
            acceptance_ok = False
        else:
            data = read_json(acceptance_report)
            acceptance_detail["status"] = data.get("status", "unknown")
            acceptance_detail["gate_passed"] = bool(data.get("gate_passed", False))
            acceptance_ok = acceptance_detail["status"] == "PASS" and acceptance_detail["gate_passed"] is True
    checks.append({"name": "acceptance_report", "passed": acceptance_ok, "detail": acceptance_detail})

    checks.append(evaluate_report_integrity_lock(project_root, options.report_file_rel, run_git))

    passed = all(bool(c.get("passed", False)) for c in checks)
    return {
        "passed": passed,
        "project_root": str(project_root),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
