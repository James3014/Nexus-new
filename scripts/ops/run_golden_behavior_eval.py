#!/usr/bin/env python3
"""Validate and execute the Nexus Golden Behavior Corpus."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_corpus = importlib.import_module("tests.golden_behavior.corpus")
CASES = _corpus.CASES
FINDINGS = _corpus.FINDINGS


CLASSIFICATIONS = {"invariant", "regression", "compatibility", "security"}
SCENARIOS = {
    "normal",
    "boundary",
    "failure",
    "authority_conflict",
    "partial_state",
    "recovery",
    "idempotency",
    "malformed_input",
    "stale_state",
}
STATUSES = {"covered", "finding"}


PROBES: dict[str, Callable[[], tuple[bool, str]]] = {}


def validate_corpus() -> list[str]:
    errors: list[str] = []
    ids = [case.case_id for case in CASES]
    if not 50 <= len(CASES) <= 100:
        errors.append(f"case_count_out_of_range:{len(CASES)}")
    if len(ids) != len(set(ids)):
        errors.append("duplicate_case_id")
    for case in CASES:
        if case.classification not in CLASSIFICATIONS:
            errors.append(f"{case.case_id}:invalid_classification")
        if case.scenario not in SCENARIOS:
            errors.append(f"{case.case_id}:invalid_scenario")
        if case.status not in STATUSES:
            errors.append(f"{case.case_id}:invalid_status")
        if not case.expected_behavior.strip():
            errors.append(f"{case.case_id}:missing_expected_behavior")
        if not case.authority_sources:
            errors.append(f"{case.case_id}:missing_authority")
        for source in case.authority_sources:
            if source.startswith("http"):
                continue
            path = ROOT / source.split("#", 1)[0].split(":", 1)[0]
            if not path.exists():
                errors.append(f"{case.case_id}:missing_authority_path:{source}")
        if case.status == "covered" and not case.automated_tests:
            errors.append(f"{case.case_id}:covered_without_test")
        if case.status == "finding":
            if not case.finding_id or case.finding_id not in FINDINGS:
                errors.append(f"{case.case_id}:missing_finding")
        if case.finding_probe and case.finding_probe not in PROBES:
            errors.append(f"{case.case_id}:unknown_finding_probe")
        for nodeid in case.automated_tests:
            path = ROOT / nodeid.split("::", 1)[0]
            if not path.exists():
                errors.append(f"{case.case_id}:missing_test_path:{nodeid}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--classification", choices=sorted(CLASSIFICATIONS))
    parser.add_argument("--scenario", choices=sorted(SCENARIOS))
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--include-findings", action="store_true")
    parser.add_argument("--json-report", type=Path)
    args = parser.parse_args()

    errors = validate_corpus()
    selected = [
        case
        for case in CASES
        if (not args.classification or case.classification == args.classification)
        and (not args.scenario or case.scenario == args.scenario)
        and (not args.case_ids or case.case_id in args.case_ids)
    ]
    if args.case_ids:
        unknown = sorted(set(args.case_ids) - {case.case_id for case in CASES})
        errors.extend(f"unknown_case:{case_id}" for case_id in unknown)

    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    source_revision = revision.stdout.strip()
    if revision.returncode != 0 or not source_revision:
        errors.append("source_revision_unavailable")

    executable = [case for case in selected if case.status == "covered" or args.include_findings]
    nodeids = sorted({nodeid for case in executable for nodeid in case.automated_tests})
    result = {
        "schema": "nexus.golden_behavior_eval.v1",
        "source_revision": source_revision,
        "case_count": len(CASES),
        "selected_case_count": len(selected),
        "test_bound_case_count": sum(bool(case.automated_tests) for case in selected),
        "probe_bound_case_count": sum(bool(case.finding_probe) for case in selected),
        "default_automated_case_count": sum(
            case.status == "covered" and bool(case.automated_tests) for case in selected
        ),
        "finding_case_count": sum(case.status == "finding" for case in selected),
        "findings_included_in_eval": args.include_findings,
        "test_node_count": len(nodeids),
        "validation_errors": errors,
        "findings": {
            case.finding_id: FINDINGS[case.finding_id] for case in selected if case.finding_id
        },
    }
    exit_code = 0 if not errors else 2
    if args.include_findings and not errors:
        probe_results = {}
        for case in selected:
            if case.status != "finding":
                continue
            if not case.finding_probe:
                probe_results[case.case_id] = {
                    "passed": False,
                    "detail": "finding_has_no_automated_probe",
                }
                exit_code = 1
                continue
            passed, detail = PROBES[case.finding_probe]()
            probe_results[case.case_id] = {"passed": passed, "detail": detail}
            if not passed:
                exit_code = 1
        result["finding_probe_results"] = probe_results
    if not args.validate_only and not errors and nodeids:
        env = dict(os.environ)
        env["NEXUS_CANONICAL_SOURCE_ROOT"] = str(ROOT)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *nodeids],
            cwd=ROOT,
            env=env,
            check=False,
        )
        result["pytest_exit_code"] = completed.returncode
        if completed.returncode != 0:
            exit_code = completed.returncode

    payload = json.dumps(result, indent=2, sort_keys=True)
    print(payload)
    if args.json_report:
        args.json_report.write_text(payload + "\n", encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
