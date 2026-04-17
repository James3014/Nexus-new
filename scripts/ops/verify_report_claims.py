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
        return out.decode("utf-8", errors="replace").strip()
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


def verify_claims(
    project_root: Path,
    *,
    required_paths: List[str] | None = None,
    require_clean: bool = False,
    require_acceptance_pass: bool = False,
    acceptance_report_rel: str = ".nexus/reports/acceptance_check.json",
) -> Dict[str, Any]:
    required_paths = required_paths or []
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

    dirty = _run_git(project_root, ["status", "--porcelain"])
    clean_ok = (not dirty.strip()) if require_clean else True
    checks.append(
        {
            "name": "working_tree",
            "passed": clean_ok,
            "detail": {
                "require_clean": require_clean,
                "dirty_entries": len([ln for ln in dirty.splitlines() if ln.strip()]),
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
        "--require-acceptance-pass",
        action="store_true",
        help="Require .nexus/reports/acceptance_check.json to be PASS and gate_passed=true.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    report = verify_claims(
        project_root,
        required_paths=list(args.require_path or []),
        require_clean=bool(args.require_clean),
        require_acceptance_pass=bool(args.require_acceptance_pass),
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
