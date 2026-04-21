#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _run_git(project_root: Path, args: List[str]) -> str:
    try:
        out = subprocess.check_output(["git", *args], cwd=str(project_root), stderr=subprocess.DEVNULL)
        return out.decode("utf-8", errors="replace").rstrip("\n")
    except Exception:
        return ""


def _resolve_required_paths(project_root: Path, required_paths: List[str]) -> List[Path]:
    resolved: List[Path] = []
    for raw in required_paths:
        p = Path(raw)
        if not p.is_absolute():
            p = (project_root / p).resolve()
        resolved.append(p)
    return resolved


def _parse_porcelain_paths(raw_status: str) -> List[str]:
    paths: List[str] = []
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


def _load_ignore_dirty_paths(project_root: Path, config_path: str | None) -> List[str]:
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


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _sorted_nonempty_lines(raw: str) -> List[str]:
    return sorted([line.strip() for line in raw.splitlines() if line.strip()])


def _evaluate_report_integrity_lock(project_root: Path, report_file_rel: str | None) -> Dict[str, Any]:
    if not report_file_rel:
        return {"name": "report_integrity_lock", "passed": True, "detail": {"skipped": True}}

    report_path = Path(report_file_rel)
    if not report_path.is_absolute():
        report_path = (project_root / report_path).resolve()

    detail: Dict[str, Any] = {"path": str(report_path), "exists": report_path.exists()}
    if not report_path.exists():
        detail["error"] = "report_file_not_found"
        return {"name": "report_integrity_lock", "passed": False, "detail": detail}

    report = _read_json(report_path)
    head_sha = str(report.get("head_sha", "")).strip()
    if not head_sha:
        detail["error"] = "missing_report_head_sha"
        return {"name": "report_integrity_lock", "passed": False, "detail": detail}

    actual_head = _run_git(project_root, ["rev-parse", "--short", "HEAD"]).strip()
    head_ok = bool(actual_head) and actual_head == head_sha
    detail["head_alignment"] = {"passed": head_ok, "report_head_sha": head_sha, "actual_head_sha": actual_head}

    reported_commit_files = sorted([str(v).strip() for v in report.get("files_changed_in_this_commit", []) if str(v).strip()])
    actual_commit_files = _sorted_nonempty_lines(_run_git(project_root, ["show", "--name-only", "--pretty=format:", "HEAD"]))
    commit_ok = reported_commit_files == actual_commit_files
    detail["commit_integrity"] = {
        "passed": commit_ok,
        "reported_files": reported_commit_files,
        "actual_files": actual_commit_files,
    }

    base_branch = str(report.get("base_branch", "main")).strip() or "main"
    reported_delta = sorted([str(v).strip() for v in report.get("branch_delta_vs_base", []) if str(v).strip()])
    actual_delta = _sorted_nonempty_lines(_run_git(project_root, ["diff", "--name-only", f"{base_branch}...HEAD"]))
    delta_ok = reported_delta == actual_delta
    detail["branch_delta_integrity"] = {
        "passed": delta_ok,
        "base_branch": base_branch,
        "reported_delta": reported_delta,
        "actual_delta": actual_delta,
    }

    passed = head_ok and commit_ok and delta_ok
    return {"name": "report_integrity_lock", "passed": passed, "detail": detail}


def verify_claims(
    project_root: Path,
    *,
    required_paths: List[str] | None = None,
    require_clean: bool = False,
    ignore_dirty_paths: List[str] | None = None,
    ignore_dirty_config: str | None = None,
    require_acceptance_pass: bool = False,
    acceptance_report_rel: str = ".nexus/reports/acceptance_check.json",
    require_baseline: bool = False,
    baseline_manifest_rel: str = ".nexus/reports/baseline/baseline_manifest.json",
    report_file_rel: str | None = None,
) -> Dict[str, Any]:
    required_paths = required_paths or []
    ignore_dirty_paths = (ignore_dirty_paths or []) + _load_ignore_dirty_paths(project_root, ignore_dirty_config)
    checks: List[Dict[str, Any]] = []

    branch = _run_git(project_root, ["rev-parse", "--abbrev-ref", "HEAD"])
    commit = _run_git(project_root, ["rev-parse", "--short", "HEAD"])
    git_ok = bool(branch and commit)
    checks.append(
        {
            "name": "git_context",
            "passed": git_ok,
            "detail": {"branch": branch or "unknown", "commit": commit or "unknown"},
        }
    )

    baseline_path = (project_root / baseline_manifest_rel).resolve()
    baseline_ok = True
    baseline_detail = {"path": str(baseline_path), "exists": baseline_path.exists()}
    if require_baseline:
        if not baseline_path.exists():
            baseline_ok = False
        else:
            data = _read_json(baseline_path)
            baseline_detail["version"] = data.get("version")
            baseline_detail["generated_by_sha"] = data.get("generated_by_sha")
            if not baseline_detail["version"] or not baseline_detail["generated_by_sha"]:
                baseline_ok = False
                baseline_detail["error"] = "missing_schema_fields"
    checks.append({"name": "baseline_manifest", "passed": baseline_ok, "detail": baseline_detail})

    dirty = _run_git(project_root, ["status", "--porcelain"])
    dirty_paths = _parse_porcelain_paths(dirty)
    ignored_resolved = {str(p) for p in _resolve_required_paths(project_root, ignore_dirty_paths)}
    effective_dirty: List[str] = []
    for rel_path in dirty_paths:
        resolved = project_root / rel_path
        if str(resolved.resolve()) in ignored_resolved:
            continue
        effective_dirty.append(rel_path)
    clean_ok = (not effective_dirty) if require_clean else True
    checks.append(
        {
            "name": "working_tree",
            "passed": clean_ok,
            "detail": {
                "require_clean": require_clean,
                "dirty_entries": len(dirty_paths),
                "effective_dirty_entries": len(effective_dirty),
                "ignored_dirty_paths": sorted(ignore_dirty_paths),
                "effective_dirty_paths": effective_dirty,
            },
        }
    )

    resolved_paths = _resolve_required_paths(project_root, required_paths)
    missing = [str(p) for p in resolved_paths if not p.exists()]
    paths_ok = not missing
    checks.append(
        {
            "name": "required_paths",
            "passed": paths_ok,
            "detail": {"required_count": len(resolved_paths), "missing": missing},
        }
    )

    acceptance_report = (project_root / acceptance_report_rel).resolve()
    acceptance_ok = True
    acceptance_detail: Dict[str, Any] = {
        "path": str(acceptance_report),
        "exists": acceptance_report.exists(),
        "status": "unknown",
        "gate_passed": None,
        "require_acceptance_pass": require_acceptance_pass,
    }
    if require_acceptance_pass:
        if not acceptance_report.exists():
            acceptance_ok = False
        else:
            data = _read_json(acceptance_report)
            acceptance_detail["status"] = data.get("status", "unknown")
            acceptance_detail["gate_passed"] = bool(data.get("gate_passed", False))
            acceptance_ok = acceptance_detail["status"] == "PASS" and acceptance_detail["gate_passed"] is True
    checks.append({"name": "acceptance_report", "passed": acceptance_ok, "detail": acceptance_detail})

    checks.append(_evaluate_report_integrity_lock(project_root, report_file_rel))

    passed = all(bool(c.get("passed", False)) for c in checks)
    return {
        "passed": passed,
        "project_root": str(project_root),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify report claims against branch-scoped evidence.")
    parser.add_argument("--project-root", default=str(Path.cwd()))
    parser.add_argument("--require-path", action="append", default=[], help="Required file path (repeatable).")
    parser.add_argument("--require-clean", action="store_true", help="Require clean working tree.")
    parser.add_argument(
        "--ignore-dirty-path",
        action="append",
        default=[],
        help="Dirty path to ignore for clean-tree checks (repeatable).",
    )
    parser.add_argument(
        "--ignore-dirty-config",
        default=None,
        help="JSON file containing ignore_dirty_paths for clean-tree checks.",
    )
    parser.add_argument(
        "--require-acceptance-pass",
        action="store_true",
        help="Require .nexus/reports/acceptance_check.json to be PASS and gate_passed=true.",
    )
    parser.add_argument(
        "--baseline-manifest",
        default=".nexus/reports/baseline/baseline_manifest.json",
        help="Path to baseline manifest (relative to project root).",
    )
    parser.add_argument(
        "--no-require-baseline",
        action="store_true",
        help="Disable baseline schema hard requirement.",
    )
    parser.add_argument(
        "--report-file",
        default=None,
        help="Report JSON path used for report_integrity_lock checks.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    report = verify_claims(
        project_root,
        required_paths=list(args.require_path or []),
        require_clean=bool(args.require_clean),
        ignore_dirty_paths=list(args.ignore_dirty_path or []),
        ignore_dirty_config=args.ignore_dirty_config,
        require_acceptance_pass=bool(args.require_acceptance_pass),
        require_baseline=not args.no_require_baseline,
        baseline_manifest_rel=args.baseline_manifest,
        report_file_rel=args.report_file,
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"[report-verify] status={'PASS' if report['passed'] else 'FAIL'}")
        for check in report["checks"]:
            print(f"- {check['name']}: {'PASS' if check['passed'] else 'FAIL'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
