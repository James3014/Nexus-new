#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

EXPECTED_SCHEMA = "ultra-review.v1"
BLOCKING_SEVERITIES = {"high", "critical"}
REQUIRED_TOP_LEVEL_FIELDS = (
    "schema_version",
    "run_id",
    "status",
    "gate_passed",
    "mode",
    "project_root",
    "sandbox_path",
    "artifacts",
    "diff",
    "fleet",
    "findings",
    "verification",
    "created_at",
    "report_path",
)


def load_report(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"missing report: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}") from exc


def evaluate_report(
    payload: dict[str, Any],
    *,
    allow_findings: bool = False,
    check_artifacts: bool = False,
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in payload:
            failures.append(f"missing_field:{field}")

    if payload.get("schema_version") != EXPECTED_SCHEMA:
        failures.append("schema_version_mismatch")
    if payload.get("gate_passed") is not True:
        failures.append("gate_not_passed")
    if payload.get("mode") != "dry-run":
        failures.append("unsupported_mode")
    if not payload.get("sandbox_path"):
        failures.append("missing_sandbox_path")

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, dict):
        failures.append("invalid_artifacts")
    else:
        for field in ("diff", "git_status"):
            artifact_path = artifacts.get(field)
            if not artifact_path:
                failures.append(f"missing_artifact:{field}")
            elif check_artifacts and not Path(str(artifact_path)).exists():
                failures.append(f"missing_artifact_file:{field}")

    diff = payload.get("diff")
    if not isinstance(diff, dict):
        failures.append("invalid_diff")
    else:
        if not isinstance(diff.get("changed_files"), list):
            failures.append("invalid_diff_changed_files")

    verification = payload.get("verification")
    if not isinstance(verification, dict):
        failures.append("invalid_verification")
    elif verification.get("reproduction_required") is not True:
        failures.append("reproduction_not_required")

    ghost_regression = payload.get("ghost_regression", {})
    if isinstance(ghost_regression, dict) and ghost_regression.get("passed") is False:
        failures.append("ghost_regression_failed")

    logic_breaker = payload.get("logic_breaker", {})
    if isinstance(logic_breaker, dict) and logic_breaker.get("passed") is False:
        failures.append("logic_breaker_failed")

    security_sentry = payload.get("security_sentry", {})
    if isinstance(security_sentry, dict) and security_sentry.get("passed") is False:
        failures.append("security_sentry_failed")

    fleet = payload.get("fleet")
    if not isinstance(fleet, list) or not fleet:
        failures.append("missing_fleet")
    else:
        lanes = {str(item.get("lane", "")) for item in fleet if isinstance(item, dict)}
        for required in ("security_sentry", "logic_breaker", "ghost_regression"):
            if required not in lanes:
                failures.append(f"missing_lane:{required}")

    findings = payload.get("findings", [])
    if not isinstance(findings, list):
        failures.append("invalid_findings")
        findings = []

    if not allow_findings:
        for finding in findings:
            if not isinstance(finding, dict):
                failures.append("invalid_finding_entry")
                continue
            state = str(finding.get("state", "")).upper()
            severity = str(finding.get("severity", "")).lower()
            if state == "VERIFIED_FINDING" and severity in BLOCKING_SEVERITIES:
                failures.append(f"blocking_verified_finding:{finding.get('id', 'unknown')}")

    return not failures, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed parser for Nexus ultra-review reports.")
    parser.add_argument("--report", default=".nexus/reports/ultra_review_report.json")
    parser.add_argument("--allow-findings", action="store_true")
    parser.add_argument("--check-artifacts", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        payload = load_report(Path(args.report))
        passed, failures = evaluate_report(
            payload,
            allow_findings=args.allow_findings,
            check_artifacts=args.check_artifacts,
        )
    except ValueError as exc:
        passed = False
        failures = [str(exc)]
        payload = {}

    result = {
        "gate": "ultra-review",
        "passed": passed,
        "failures": failures,
        "report": args.report,
        "run_id": payload.get("run_id"),
    }
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"[ultra-gate] passed={str(passed).lower()} report={args.report}")
        if failures:
            print("[ultra-gate] failures=" + ",".join(failures), file=sys.stderr)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
