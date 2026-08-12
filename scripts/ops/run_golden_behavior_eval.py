#!/usr/bin/env python3
"""Validate and execute the Nexus Golden Behavior Corpus."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

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


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _pytest_env() -> dict[str, str]:
    env = dict(os.environ)
    env["NEXUS_CANONICAL_SOURCE_ROOT"] = str(ROOT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _output_tail(completed: subprocess.CompletedProcess[str], *, limit: int = 1200) -> str:
    combined = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    return combined[-limit:]


def collect_witness(nodeid: str) -> dict[str, Any]:
    """Compatibility single-node collection probe used by focused evaluator tests."""
    evidence, _ = collect_witnesses([nodeid])
    return evidence[nodeid]


def collect_witnesses(nodeids: Iterable[str]) -> tuple[dict[str, dict[str, Any]], int]:
    """Prove exact pytest node IDs collect without executing their test bodies."""
    ordered = sorted(set(nodeids))
    if not ordered:
        return {}, 0
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *ordered,
        ],
        cwd=ROOT,
        env=_pytest_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    collected_lines = {line.strip() for line in completed.stdout.splitlines() if "::" in line}
    detail = _output_tail(completed)
    evidence: dict[str, dict[str, Any]] = {}
    for nodeid in ordered:
        collected = nodeid in collected_lines or completed.returncode == 0
        row: dict[str, Any] = {
            "collection_status": "collected" if collected else "collection_failed",
            "collection_exit_code": 0 if collected else completed.returncode,
        }
        if not collected:
            row["collection_detail"] = detail
        evidence[nodeid] = row
    return evidence, completed.returncode


def _expected_junit_identity(nodeid: str) -> tuple[str, str]:
    path, *parts = nodeid.split("::")
    module = path.removesuffix(".py").replace("/", ".")
    if len(parts) > 1:
        module = ".".join((module, *parts[:-1]))
    return module, parts[-1]


def _junit_rows(path: Path) -> list[ET.Element]:
    root = ET.parse(path).getroot()
    if root.tag == "testsuite":
        return list(root.findall("testcase"))
    return list(root.findall("testsuite/testcase"))


def execute_witnesses(nodeids: Iterable[str]) -> tuple[dict[str, dict[str, Any]], int]:
    """Run exact witnesses in one pytest batch and attribute each JUnit outcome exactly."""
    ordered = sorted(set(nodeids))
    if not ordered:
        return {}, 0
    with tempfile.TemporaryDirectory(prefix="nexus-golden-") as tmpdir:
        junit_path = Path(tmpdir) / "witnesses.xml"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                f"--junitxml={junit_path}",
                *ordered,
            ],
            cwd=ROOT,
            env=_pytest_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        rows = _junit_rows(junit_path) if junit_path.exists() else []

    by_identity: dict[tuple[str, str], list[ET.Element]] = {}
    for row in rows:
        key = (row.attrib.get("classname", ""), row.attrib.get("name", ""))
        by_identity.setdefault(key, []).append(row)

    evidence: dict[str, dict[str, Any]] = {}
    batch_detail = _output_tail(completed)
    for nodeid in ordered:
        identity = _expected_junit_identity(nodeid)
        matches = by_identity.get(identity, [])
        if len(matches) != 1:
            evidence[nodeid] = {
                "execution_status": "execution_unattributed",
                "execution_exit_code": completed.returncode,
                "execution_detail": batch_detail,
            }
            continue
        row = matches[0]
        if row.find("failure") is not None:
            status = "failed"
        elif row.find("error") is not None:
            status = "error"
        elif row.find("skipped") is not None:
            status = "skipped"
        else:
            status = "passed"
        item: dict[str, Any] = {
            "execution_status": status,
            "execution_exit_code": 0 if status in {"passed", "skipped"} else completed.returncode,
        }
        if status in {"failed", "error"}:
            item["execution_detail"] = batch_detail
        evidence[nodeid] = item
    return evidence, completed.returncode


def validate_corpus() -> list[str]:
    errors: list[str] = []
    ids = [case.case_id for case in CASES]
    if len(CASES) < 50:
        errors.append(f"case_count_below_minimum:{len(CASES)}")
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


def _provenance(errors: list[str]) -> dict[str, Any]:
    revision = _git("rev-parse", "HEAD")
    source_revision = revision.stdout.strip()
    if revision.returncode != 0 or not source_revision:
        errors.append("source_revision_unavailable")

    tree = _git("rev-parse", "HEAD^{tree}")
    source_tree = tree.stdout.strip()
    if tree.returncode != 0 or not source_tree:
        errors.append("source_tree_unavailable")

    status = _git("status", "--porcelain")
    if status.returncode != 0:
        errors.append("workspace_status_unavailable")

    corpus_path = ROOT / "tests/golden_behavior/corpus.py"
    lock_path = ROOT / "uv.lock"
    if not corpus_path.is_file():
        errors.append("corpus_identity_unavailable")
    if not lock_path.is_file():
        errors.append("dependency_lock_identity_unavailable")

    return {
        "source_revision": source_revision,
        "source_tree": source_tree,
        "workspace_dirty": bool(status.stdout.strip()) if status.returncode == 0 else None,
        "corpus_identity": _sha256(corpus_path) if corpus_path.is_file() else None,
        "evaluator_identity": _sha256(Path(__file__)),
        "dependency_lock_identity": _sha256(lock_path) if lock_path.is_file() else None,
        "python_version": sys.version.split()[0],
        "pytest_version": importlib.metadata.version("pytest"),
    }


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

    provenance = _provenance(errors)
    selected_nodeids = sorted({nodeid for case in selected for nodeid in case.automated_tests})
    executable_cases = [
        case for case in selected if case.status == "covered" or args.include_findings
    ]
    executable_nodeids = sorted({
        nodeid for case in executable_cases for nodeid in case.automated_tests
    })

    collection_evidence, collection_exit_code = collect_witnesses(selected_nodeids)
    for nodeid, evidence in collection_evidence.items():
        if evidence["collection_status"] != "collected":
            errors.append(f"uncollectable_node:{nodeid}")

    execution_evidence: dict[str, dict[str, Any]] = {}
    pytest_exit_code: int | None = None
    if not args.validate_only and not errors:
        execution_evidence, pytest_exit_code = execute_witnesses(executable_nodeids)

    case_evidence = []
    for case in selected:
        witnesses = []
        for nodeid in case.automated_tests:
            witness = {"nodeid": nodeid, **collection_evidence[nodeid]}
            if nodeid in execution_evidence:
                witness.update(execution_evidence[nodeid])
            elif args.validate_only:
                witness["execution_status"] = "not_executed_validate_only"
            elif errors:
                witness["execution_status"] = "not_executed_validation_failed"
            elif case.status == "finding" and not args.include_findings:
                witness["execution_status"] = "not_executed_finding_excluded"
            else:
                witness["execution_status"] = "not_executed"
            witnesses.append(witness)
        case_evidence.append({
            "case_id": case.case_id,
            "status": case.status,
            "witnesses": witnesses,
            "finding_probe": case.finding_probe,
        })

    result: dict[str, Any] = {
        "schema": "nexus.golden_behavior_eval.v1",
        **provenance,
        "case_count": len(CASES),
        "selected_case_count": len(selected),
        "test_bound_case_count": sum(bool(case.automated_tests) for case in selected),
        "probe_bound_case_count": sum(bool(case.finding_probe) for case in selected),
        "default_automated_case_count": sum(
            case.status == "covered" and bool(case.automated_tests) for case in selected
        ),
        "finding_case_count": sum(case.status == "finding" for case in selected),
        "findings_included_in_eval": args.include_findings,
        "test_node_count": len(executable_nodeids),
        "collection_node_count": len(selected_nodeids),
        "collection_exit_code": collection_exit_code,
        "validation_errors": errors,
        "case_evidence": case_evidence,
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

    if pytest_exit_code is not None:
        result["pytest_exit_code"] = pytest_exit_code
        unattributed_or_failed = [
            evidence
            for evidence in execution_evidence.values()
            if evidence["execution_status"] not in {"passed", "skipped"}
        ]
        if pytest_exit_code != 0 or unattributed_or_failed:
            exit_code = pytest_exit_code or 1

    payload = json.dumps(result, indent=2, sort_keys=True)
    print(payload)
    if args.json_report:
        args.json_report.write_text(payload + "\n", encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
