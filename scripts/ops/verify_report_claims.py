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

    # R1/R2: Report Integrity Lock
    integrity_ok = True
    integrity_detail: Dict[str, Any] = {"report_file": report_file_rel}
    if report_file_rel:
        p_report = (project_root / report_file_rel).resolve()
        if not p_report.exists():
            integrity_ok = False
            integrity_detail["error"] = "report_file_not_found"
        else:
            try:
                data = json.loads(p_report.read_text(encoding="utf-8"))
                head_sha = data.get("head_sha", "")
                
                # R1: Local Commit Verification
                claimed_files = set(data.get("files_changed_in_this_commit", []))
                actual_files_raw = _run_git(project_root, ["show", "--name-only", "--pretty=format:", head_sha or "HEAD"])
                actual_files = {f.strip() for f in actual_files_raw.splitlines() if f.strip()}
                
                commit_match = claimed_files == actual_files
                integrity_detail["commit_integrity"] = {
                    "passed": commit_match,
                    "claimed_count": len(claimed_files),
                    "actual_count": len(actual_files),
                    "missing_in_report": sorted(list(actual_files - claimed_files)),
                    "extra_in_report": sorted(list(claimed_files - actual_files))
                }
                
                # R2: Branch Delta Verification
                base_branch = data.get("base_branch", "main")
                claimed_delta = set(data.get("branch_delta_vs_base", []))
                actual_delta_raw = _run_git(project_root, ["diff", "--name-only", f"{base_branch}..{head_sha or 'HEAD'}"])
                actual_delta = {f.strip() for f in actual_delta_raw.splitlines() if f.strip()}
                
                delta_match = claimed_delta == actual_delta
                integrity_detail["delta_integrity"] = {
                    "passed": delta_match,
                    "base_branch": base_branch,
                    "claimed_count": len(claimed_delta),
                    "actual_count": len(actual_delta),
                    "missing_in_report": sorted(list(actual_delta - claimed_delta)),
                    "extra_in_report": sorted(list(claimed_delta - actual_delta))
                }
                integrity_ok = commit_match and delta_match
            except Exception as e:
                integrity_ok = False
                integrity_detail["error"] = f"integrity_check_failed: {str(e)}"
    
    checks.append({
        "name": "report_integrity_lock",
        "passed": integrity_ok,
        "detail": integrity_detail
    })

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

    # === NEW: T5 Anti-Fraud Hardening v1: Raw Proof Validation ===
    # R3: 強制「非空 + 最低關鍵字」檢查
    proof_specs = {
        "pytest_raw": {
            "rel": ".nexus/reports/pytest_output.txt",
            "keywords": ["passed", "collected"]
        },
        "effectiveness_proof": {
            "rel": ".nexus/reports/effectiveness_proof.txt",
            "keywords": ["總測試場景"]
        },
        "closed_loop_proof": {
            "rel": ".nexus/reports/closed_loop_proof.txt",
            "keywords": ["閉環驗證"]
        }
    }
    proof_results = []
    for name, spec in proof_specs.items():
        rel = spec["rel"]
        keywords = spec["keywords"]
        p_path = project_root / rel
        
        exists = p_path.exists() and p_path.stat().st_size > 0
        keyword_match = False
        if exists:
            content = p_path.read_text(encoding="utf-8")
            keyword_match = any(k in content for k in keywords)
        
        passed = exists and keyword_match
        proof_results.append({
            "name": name,
            "passed": passed,
            "path": str(p_path),
            "exists_and_not_empty": exists,
            "keyword_match": keyword_match,
            "required_keywords": keywords
        })
    
    proofs_ok = all(r["passed"] for r in proof_results)
    checks.append({
        "name": "raw_evidence_proofs",
        "passed": proofs_ok,
        "detail": {"proof_items": proof_results}
    })

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
    parser.add_argument("--report-file", default=None, help="Path to settlement report JSON for integrity lock.")
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
