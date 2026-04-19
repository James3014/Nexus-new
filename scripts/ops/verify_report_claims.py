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
        # Keep leading spaces on porcelain status lines; only trim trailing newlines.
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
            # Fallback for non-standard one-column short status output.
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


def verify_claims(
    project_root: Path,
    *,
    required_paths: List[str] | None = None,
    require_clean: bool = False,
    ignore_dirty_paths: List[str] | None = None,
    ignore_dirty_config: str | None = None,
    require_acceptance_pass: bool = False,
    acceptance_report_rel: str = ".nexus/reports/acceptance_check.json",
    require_baseline: bool = True,
    baseline_manifest_rel: str = ".nexus/reports/baseline/baseline_manifest.json",
) -> Dict[str, Any]:
    required_paths = required_paths or []
    ignore_dirty_paths = (ignore_dirty_paths or []) + _load_ignore_dirty_paths(project_root, ignore_dirty_config)
    checks: List[Dict[str, Any]] = []

    # 1. Git Context
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

    # 2. Baseline Manifest Check
    baseline_path = (project_root / baseline_manifest_rel).resolve()
    baseline_ok = True
    baseline_detail = {"path": str(baseline_path), "exists": baseline_path.exists()}
    if require_baseline:
        if not baseline_path.exists():
            baseline_ok = False
        else:
            try:
                data = json.loads(baseline_path.read_text(encoding="utf-8"))
                baseline_detail["version"] = data.get("version")
                baseline_detail["generated_by_sha"] = data.get("generated_by_sha")
                if not baseline_detail["version"] or not baseline_detail["generated_by_sha"]:
                    baseline_ok = False
                    baseline_detail["error"] = "missing_schema_fields"
            except Exception as e:
                baseline_ok = False
                baseline_detail["error"] = f"parse_error:{e}"
    checks.append({"name": "baseline_manifest", "passed": baseline_ok, "detail": baseline_detail})

    # 3. Working Tree
    dirty = _run_git(project_root, ["status", "--porcelain"])
    dirty_paths = _parse_porcelain_paths(dirty)
    ignored_resolved = {str(p) for p in _resolve_required_paths(project_root, ignore_dirty_paths)}
    effective_dirty = []
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
            try:
                data = json.loads(acceptance_report.read_text(encoding="utf-8"))
                acceptance_detail["status"] = data.get("status", "unknown")
                acceptance_detail["gate_passed"] = bool(data.get("gate_passed", False))
                acceptance_ok = acceptance_detail["status"] == "PASS" and acceptance_detail["gate_passed"] is True
            except Exception as exc:
                acceptance_ok = False
                acceptance_detail["error"] = f"parse_error:{exc}"
    checks.append({"name": "acceptance_report", "passed": acceptance_ok, "detail": acceptance_detail})

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
        baseline_manifest_rel=args.baseline_manifest,
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
