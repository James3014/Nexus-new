#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from nexus.delivery.report_claims import ReportClaimsOptions
from nexus.delivery.report_claims import load_ignore_dirty_paths as _load_ignore_dirty_paths_core
from nexus.delivery.report_claims import parse_porcelain_paths as _parse_porcelain_paths_core
from nexus.delivery.report_claims import verify_claims_core


def _run_git(project_root: Path, args: List[str]) -> str:
    try:
        out = subprocess.check_output(["git", *args], cwd=str(project_root), stderr=subprocess.DEVNULL)
        return out.decode("utf-8", errors="replace").rstrip("\n")
    except Exception:
        return ""

def _parse_porcelain_paths(raw_status: str) -> List[str]:
    return _parse_porcelain_paths_core(raw_status)


def _load_ignore_dirty_paths(project_root: Path, config_path: str | None) -> List[str]:
    return _load_ignore_dirty_paths_core(project_root, config_path)


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
    require_test_evidence: bool = False,
    report_newer_than: str | None = None,
) -> Dict[str, Any]:
    options = ReportClaimsOptions(
        required_paths=list(required_paths or []),
        require_clean=bool(require_clean),
        ignore_dirty_paths=list(ignore_dirty_paths or []) + _load_ignore_dirty_paths(project_root, ignore_dirty_config),
        require_acceptance_pass=bool(require_acceptance_pass),
        acceptance_report_rel=acceptance_report_rel,
        require_baseline=bool(require_baseline),
        baseline_manifest_rel=baseline_manifest_rel,
        report_file_rel=report_file_rel,
        require_test_evidence=bool(require_test_evidence),
        report_newer_than=report_newer_than,
    )
    return verify_claims_core(project_root, options, _run_git)


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
    parser.add_argument(
        "--require-test-evidence",
        action="store_true",
        help="Require report_file tests_run evidence with all exit_code=0.",
    )
    parser.add_argument(
        "--report-newer-than",
        default=None,
        help="Require report_file mtime to be newer than the given reference file.",
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
        require_test_evidence=bool(args.require_test_evidence),
        report_newer_than=args.report_newer_than,
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
