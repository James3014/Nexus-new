from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus.evidence.claim_boundary import evaluate_claim_boundary


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
    require_test_evidence: bool
    require_nexus_command_evidence: bool
    require_worktree_delta: bool
    report_newer_than: str | None


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


def _is_ignored_path(path: str, ignore_paths: set[str]) -> bool:
    normalized = path.strip()
    if not normalized:
        return False
    for ignore in ignore_paths:
        token = ignore.strip()
        if not token:
            continue
        if normalized == token:
            return True
        if token.endswith("/"):
            if normalized.startswith(token):
                return True
        elif normalized.startswith(f"{token}/"):
            return True
    return False


def evaluate_report_integrity_lock(
    project_root: Path,
    report_file_rel: str | None,
    run_git: Any,
    *,
    require_test_evidence: bool = False,
    require_nexus_command_evidence: bool = False,
    require_worktree_delta: bool = False,
    report_newer_than: str | None = None,
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

    tests_ok = True
    test_detail: dict[str, Any] = {"required": require_test_evidence}
    tests_run_entries: list[dict[str, Any]] = []
    if require_test_evidence:
        tests_run = report.get("tests_run")
        if not isinstance(tests_run, list) or not tests_run:
            tests_ok = False
            test_detail["error"] = "missing_tests_run"
            tests_run = []
        else:
            invalid_rows: list[int] = []
            nonzero_rows: list[dict[str, Any]] = []
            for idx, item in enumerate(tests_run):
                if not isinstance(item, dict):
                    invalid_rows.append(idx)
                    continue
                command = str(item.get("command", "")).strip()
                if not command:
                    invalid_rows.append(idx)
                    continue
                try:
                    exit_code = int(item.get("exit_code", 1))
                except Exception:
                    invalid_rows.append(idx)
                    continue
                if exit_code != 0:
                    nonzero_rows.append({"index": idx, "command": command, "exit_code": exit_code})
            if invalid_rows:
                tests_ok = False
                test_detail["error"] = "invalid_tests_run_entry"
                test_detail["invalid_indices"] = invalid_rows
            elif nonzero_rows:
                tests_ok = False
                test_detail["error"] = "tests_with_nonzero_exit"
                test_detail["failed_tests"] = nonzero_rows
            else:
                test_detail["count"] = len(tests_run)
                test_detail["passed"] = True
        tests_run_entries = [item for item in tests_run if isinstance(item, dict)]
    elif isinstance(report.get("tests_run"), list):
        tests_run_entries = [item for item in report.get("tests_run", []) if isinstance(item, dict)]
    detail["test_evidence"] = test_detail

    nexus_cmd_ok = True
    nexus_cmd_detail: dict[str, Any] = {"required": require_nexus_command_evidence}
    if require_nexus_command_evidence:
        commands = [str(item.get("command", "")).strip() for item in tests_run_entries]
        matched_commands = [cmd for cmd in commands if "nexus_cli.py nexus" in cmd.lower()]
        nexus_cmd_ok = len(matched_commands) > 0
        nexus_cmd_detail["matched_count"] = len(matched_commands)
        nexus_cmd_detail["matched_commands"] = matched_commands
        if not nexus_cmd_ok:
            nexus_cmd_detail["error"] = "missing_nexus_command_evidence"
    detail["nexus_command_evidence"] = nexus_cmd_detail

    worktree_ok = True
    worktree_detail: dict[str, Any] = {"required": require_worktree_delta}
    if require_worktree_delta:
        reported_worktree = sorted(
            [str(v).strip() for v in report.get("worktree_changed_files", []) if str(v).strip()]
        )
        report_rel = str(report_file_rel or "").strip()
        ignore_paths: set[str] = set()
        if report_rel:
            report_rel_path = Path(report_rel)
            ignore_paths.add(report_rel)
            for parent in report_rel_path.parents:
                parent_str = str(parent).strip()
                if parent_str and parent_str != ".":
                    ignore_paths.add(parent_str)
                    ignore_paths.add(f"{parent_str}/")

        reported_worktree = [p for p in reported_worktree if not _is_ignored_path(p, ignore_paths)]
        actual_worktree = sorted(parse_porcelain_paths(run_git(project_root, ["status", "--porcelain"])))
        actual_worktree = [p for p in actual_worktree if not _is_ignored_path(p, ignore_paths)]
        worktree_ok = reported_worktree == actual_worktree
        worktree_detail["reported_worktree"] = reported_worktree
        worktree_detail["actual_worktree"] = actual_worktree
        if not worktree_ok:
            worktree_detail["error"] = "worktree_delta_mismatch"
    detail["worktree_delta_integrity"] = worktree_detail

    freshness_ok = True
    freshness_detail: dict[str, Any] = {"reference_required": bool(report_newer_than)}
    if report_newer_than:
        reference_path = Path(report_newer_than)
        if not reference_path.is_absolute():
            reference_path = (project_root / reference_path).resolve()
        freshness_detail["reference_path"] = str(reference_path)
        freshness_detail["reference_exists"] = reference_path.exists()
        if not reference_path.exists():
            freshness_ok = False
            freshness_detail["error"] = "reference_file_not_found"
        else:
            report_mtime = report_path.stat().st_mtime
            reference_mtime = reference_path.stat().st_mtime
            freshness_detail["report_mtime"] = report_mtime
            freshness_detail["reference_mtime"] = reference_mtime
            freshness_ok = report_mtime >= reference_mtime
            if not freshness_ok:
                freshness_detail["error"] = "report_older_than_reference"
    detail["freshness"] = freshness_detail

    return {
        "name": "report_integrity_lock",
        "passed": head_ok and commit_ok and delta_ok and tests_ok and nexus_cmd_ok and worktree_ok and freshness_ok,
        "detail": detail,
    }


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

    checks.append(
        evaluate_report_integrity_lock(
            project_root,
            options.report_file_rel,
            run_git,
            require_test_evidence=options.require_test_evidence,
            require_nexus_command_evidence=options.require_nexus_command_evidence,
            require_worktree_delta=options.require_worktree_delta,
            report_newer_than=options.report_newer_than,
        )
    )

    passed = all(bool(c.get("passed", False)) for c in checks)

    # P0.1b: Inject claim boundary header
    claim_boundary = evaluate_claim_boundary(
        simulated=False,
        claim_eligible=passed,
        receipt_present=True,
        model_calls=0,
        visible_tests_passed=0,
        hidden_tests_passed=0,
    )

    return {
        "passed": passed,
        "project_root": str(project_root),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "claim_boundary": claim_boundary.to_dict(),
    }
