#!/usr/bin/env python3
"""Validate and execute the Nexus Golden Behavior Corpus."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_corpus = importlib.import_module("tests.golden_behavior.corpus")
CASES = _corpus.CASES
FINDINGS = _corpus.FINDINGS


CLASSIFICATIONS = {"invariant", "regression", "compatibility", "security"}
SCENARIOS = {"normal", "boundary", "failure", "authority_conflict", "partial_state", "recovery", "idempotency", "malformed_input", "stale_state"}
STATUSES = {"covered", "finding"}


def _probe_workforce_wording() -> tuple[bool, str]:
    text = (ROOT / "docs/arch/MODEL_WORKFORCE_POLICY.md").read_text(encoding="utf-8")
    forbidden = [
        phrase for phrase in ("## 6. Routing policy", "Nexus must route in this order:")
        if phrase in text
    ]
    return not forbidden, "forbidden_phrases=" + ",".join(forbidden)


def _probe_manifest_updater_idempotency() -> tuple[bool, str]:
    source_manifest = ROOT / "docs/reports/policy-manifest.v2.json"
    updater = ROOT / "scripts/ops/update_manifest_drills.py"
    with tempfile.TemporaryDirectory(prefix="nexus-golden-manifest-") as temp:
        temp_root = Path(temp)
        target = temp_root / "docs/reports/policy-manifest.v2.json"
        target.parent.mkdir(parents=True)
        shutil.copy2(source_manifest, target)
        first_run = subprocess.run(
            [sys.executable, str(updater)], cwd=temp_root, capture_output=True, text=True, check=False,
        )
        first_bytes = target.read_bytes()
        second_run = subprocess.run(
            [sys.executable, str(updater)], cwd=temp_root, capture_output=True, text=True, check=False,
        )
        second_bytes = target.read_bytes()
        data = json.loads(second_bytes)
    policies = data.get("policies", [])
    policy_ids = [policy.get("policy_id") for policy in policies]
    lane_members = {
        lane: sorted(policy["policy_id"] for policy in policies if policy.get("lane") == lane)
        for lane in ("hard", "soft", "shadow")
    }
    summary = data.get("summary", {})
    distribution = summary.get("lane_distribution", {})
    projection_ok = all(
        distribution.get(lane, {}).get("count") == len(ids)
        and sorted(distribution.get(lane, {}).get("policies", [])) == ids
        for lane, ids in lane_members.items()
    )
    checks = {
        "first_exit_zero": first_run.returncode == 0,
        "second_exit_zero": second_run.returncode == 0,
        "byte_identical_after_first": first_bytes == second_bytes,
        "unique_policy_ids": len(policy_ids) == len(set(policy_ids)),
        "single_no_drill_fixture": Counter(policy_ids)["P-TEST-NODRILL-01"] == 1,
        "total_projection": summary.get("total_policies") == len(policies),
        "lane_projection": projection_ok,
    }
    return all(checks.values()), json.dumps(checks, sort_keys=True)


PROBES = {
    "workforce_wording": _probe_workforce_wording,
    "manifest_updater_idempotency": _probe_manifest_updater_idempotency,
}


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
        case for case in CASES
        if (not args.classification or case.classification == args.classification)
        and (not args.scenario or case.scenario == args.scenario)
        and (not args.case_ids or case.case_id in args.case_ids)
    ]
    if args.case_ids:
        unknown = sorted(set(args.case_ids) - {case.case_id for case in CASES})
        errors.extend(f"unknown_case:{case_id}" for case_id in unknown)

    executable = [
        case for case in selected
        if case.status == "covered" or args.include_findings
    ]
    nodeids = sorted({nodeid for case in executable for nodeid in case.automated_tests})
    result = {
        "schema": "nexus.golden_behavior_eval.v1",
        "source_revision": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip(),
        "case_count": len(CASES),
        "selected_case_count": len(selected),
        "test_bound_case_count": sum(bool(case.automated_tests) for case in selected),
        "probe_bound_case_count": sum(bool(case.finding_probe) for case in selected),
        "default_automated_case_count": sum(case.status == "covered" and bool(case.automated_tests) for case in selected),
        "finding_case_count": sum(case.status == "finding" for case in selected),
        "findings_included_in_eval": args.include_findings,
        "test_node_count": len(nodeids),
        "validation_errors": errors,
        "findings": {case.finding_id: FINDINGS[case.finding_id] for case in selected if case.finding_id},
    }
    exit_code = 0 if not errors else 2
    if args.include_findings and not errors:
        probe_results = {}
        for case in selected:
            if not case.finding_probe:
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
        completed = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *nodeids], cwd=ROOT, env=env, check=False)
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
