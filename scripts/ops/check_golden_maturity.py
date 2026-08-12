#!/usr/bin/env python3
"""Project bounded Golden witness maturity from existing evaluator reports."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

REPORT_SCHEMA = "nexus.golden_behavior_eval.v1"
PROJECTION_SCHEMA = "nexus.golden_witness_maturity.v1"
REQUIRED_CLEAN_RUNS = 3
_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_COLLECTION = {"collected", "collection_failed"}
_EXECUTION = {
    "passed",
    "failed",
    "error",
    "skipped",
    "execution_unattributed",
    "not_executed",
    "not_executed_validate_only",
    "not_executed_validation_failed",
    "not_executed_finding_excluded",
}


class InvalidHistory(ValueError):
    """Raised when report history is structurally ambiguous or contradictory."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidHistory(f"duplicate_json_key:{key}")
        result[key] = value
    return result


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise InvalidHistory(code)


def _canonical_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _validate_report(report: object, index: int) -> dict[str, Any]:
    prefix = f"report_{index}"
    _require(isinstance(report, dict), f"{prefix}:not_object")
    row = report
    _require(row.get("schema") == REPORT_SCHEMA, f"{prefix}:wrong_schema")
    _require(bool(_HEX40.fullmatch(str(row.get("source_revision", "")))), f"{prefix}:bad_revision")
    _require(bool(_HEX40.fullmatch(str(row.get("source_tree", "")))), f"{prefix}:bad_tree")
    for field in ("corpus_identity", "evaluator_identity", "dependency_lock_identity"):
        _require(bool(_HEX64.fullmatch(str(row.get(field, "")))), f"{prefix}:bad_{field}")
    errors = row.get("validation_errors")
    _require(isinstance(errors, list), f"{prefix}:bad_validation_errors")
    _require(not errors, f"{prefix}:validation_failed")
    _require(type(row.get("collection_exit_code")) is int, f"{prefix}:bad_collection_exit")
    _require(type(row.get("findings_included_in_eval")) is bool, f"{prefix}:bad_findings_flag")
    cases = row.get("case_evidence")
    _require(isinstance(cases, list) and cases, f"{prefix}:bad_cases")
    _require(row.get("selected_case_count") == len(cases), f"{prefix}:selected_count_mismatch")

    case_ids: set[str] = set()
    all_nodes: set[str] = set()
    covered_nodes: set[str] = set()
    normalized_cases: list[dict[str, Any]] = []
    for case in cases:
        _require(isinstance(case, dict), f"{prefix}:bad_case")
        case_id = case.get("case_id")
        status = case.get("status")
        witnesses = case.get("witnesses")
        _require(isinstance(case_id, str) and case_id, f"{prefix}:bad_case_id")
        _require(case_id not in case_ids, f"{prefix}:duplicate_case:{case_id}")
        _require(status in {"covered", "finding"}, f"{prefix}:bad_status:{case_id}")
        _require(isinstance(witnesses, list) and witnesses, f"{prefix}:bad_witnesses:{case_id}")
        case_ids.add(case_id)
        node_ids: set[str] = set()
        normalized_witnesses: list[dict[str, str]] = []
        for witness in witnesses:
            _require(isinstance(witness, dict), f"{prefix}:bad_witness:{case_id}")
            nodeid = witness.get("nodeid")
            collection = witness.get("collection_status")
            execution = witness.get("execution_status")
            _require(isinstance(nodeid, str) and "::" in nodeid, f"{prefix}:bad_nodeid:{case_id}")
            _require(nodeid not in node_ids, f"{prefix}:duplicate_node:{nodeid}")
            _require(collection in _COLLECTION, f"{prefix}:bad_collection:{nodeid}")
            _require(execution in _EXECUTION, f"{prefix}:bad_execution:{nodeid}")
            node_ids.add(nodeid)
            all_nodes.add(nodeid)
            if status == "covered":
                covered_nodes.add(nodeid)
            normalized_witnesses.append(
                {"nodeid": nodeid, "collection": collection, "execution": execution}
            )
        normalized_cases.append(
            {
                "case_id": case_id,
                "status": status,
                "witnesses": sorted(normalized_witnesses, key=lambda item: item["nodeid"]),
            }
        )
    _require(
        row.get("collection_node_count") == len(all_nodes), f"{prefix}:collection_count_mismatch"
    )
    _require(row.get("test_node_count") == len(covered_nodes), f"{prefix}:test_count_mismatch")
    if covered_nodes:
        _require(type(row.get("pytest_exit_code")) is int, f"{prefix}:missing_pytest_exit")
    return {
        "revision": row["source_revision"],
        "tree": row["source_tree"],
        "identity": {
            "source_revision": row["source_revision"],
            "source_tree": row["source_tree"],
            "corpus_identity": row["corpus_identity"],
            "evaluator_identity": row["evaluator_identity"],
            "dependency_lock_identity": row["dependency_lock_identity"],
            "findings_included_in_eval": row["findings_included_in_eval"],
            "case_map": [
                {
                    "case_id": case["case_id"],
                    "status": case["status"],
                    "witnesses": [w["nodeid"] for w in case["witnesses"]],
                }
                for case in sorted(normalized_cases, key=lambda item: item["case_id"])
            ],
        },
        "collection_exit_code": row["collection_exit_code"],
        "pytest_exit_code": row.get("pytest_exit_code"),
        "cases": normalized_cases,
    }


def _case_outcome(report: Mapping[str, Any], case: Mapping[str, Any]) -> str:
    if case["status"] == "finding":
        return "FINDING"
    witnesses = case["witnesses"]
    if report["collection_exit_code"] != 0 or any(
        witness["collection"] != "collected" for witness in witnesses
    ):
        return "COLLECTION_DRIFT"
    executions = {witness["execution"] for witness in witnesses}
    if "execution_unattributed" in executions or any(
        status.startswith("not_executed") or status == "skipped" for status in executions
    ):
        return "INFRA_FAILURE"
    if executions & {"failed", "error"}:
        return "DETERMINISTIC_FAILURE"
    if report["pytest_exit_code"] != 0:
        return "INFRA_FAILURE"
    return "CLEAN"


def project_maturity(reports: Sequence[object]) -> dict[str, Any]:
    try:
        _require(bool(reports), "history_empty")
        normalized = [_validate_report(report, index) for index, report in enumerate(reports)]
    except InvalidHistory as exc:
        return {
            "schema": PROJECTION_SCHEMA,
            "status": "FAIL_CLOSED",
            "failures": [str(exc)],
            "claim_ceiling": "TEST_GOVERNANCE_CANDIDATE_PR_ONLY",
        }

    identities = [_canonical_hash(report["identity"]) for report in normalized]
    identity_changed = len(set(identities)) > 1
    latest = normalized[-1]
    cases: list[dict[str, Any]] = []
    latest_cases = {case["case_id"]: case for case in latest["cases"]}
    for case_id in sorted(latest_cases):
        case = latest_cases[case_id]
        history_outcomes: list[str] = []
        for report in normalized:
            matching = {item["case_id"]: item for item in report["cases"]}
            if case_id not in matching:
                history_outcomes.append("REQUALIFY")
                continue
            history_outcomes.append(_case_outcome(report, matching[case_id]))

        if case["status"] == "finding":
            maturity = "FINDING"
            clean_count = 0
        elif identity_changed:
            maturity = "REQUALIFY"
            clean_count = 1 if history_outcomes[-1] == "CLEAN" else 0
        elif "COLLECTION_DRIFT" in history_outcomes:
            maturity = "COLLECTION_DRIFT"
            clean_count = 0
        elif "INFRA_FAILURE" in history_outcomes:
            maturity = "INFRA_FAILURE"
            clean_count = 0
        elif "CLEAN" in history_outcomes and "DETERMINISTIC_FAILURE" in history_outcomes:
            maturity = "FLAKY"
            clean_count = 0
        elif "DETERMINISTIC_FAILURE" in history_outcomes:
            maturity = "DETERMINISTIC_FAILURE"
            clean_count = 0
        else:
            clean_count = 0
            for outcome in reversed(history_outcomes):
                if outcome != "CLEAN":
                    break
                clean_count += 1
            maturity = "STABLE" if clean_count >= REQUIRED_CLEAN_RUNS else "CANDIDATE"

        cases.append(
            {
                "case_id": case_id,
                "golden_status": case["status"],
                "maturity": maturity,
                "consecutive_clean_runs": clean_count,
                "required_clean_runs": REQUIRED_CLEAN_RUNS,
                "witnesses": [witness["nodeid"] for witness in case["witnesses"]],
            }
        )
    return {
        "schema": PROJECTION_SCHEMA,
        "status": "PASS",
        "failures": [],
        "required_clean_runs": REQUIRED_CLEAN_RUNS,
        "report_count": len(normalized),
        "source_reports": [
            {"revision": report["revision"], "tree": report["tree"]} for report in normalized
        ],
        "material_identity": identities[-1],
        "cases": cases,
        "claim_ceiling": "TEST_GOVERNANCE_CANDIDATE_PR_ONLY",
    }


def load_and_project(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        _require(isinstance(payload, dict), "history_not_object")
        reports = payload.get("reports")
        _require(isinstance(reports, list), "reports_not_list")
        return project_maturity(reports)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, InvalidHistory) as exc:
        return {
            "schema": PROJECTION_SCHEMA,
            "status": "FAIL_CLOSED",
            "failures": [f"history_unavailable_or_malformed:{exc}"],
            "claim_ceiling": "TEST_GOVERNANCE_CANDIDATE_PR_ONLY",
        }


def render_projection(result: Mapping[str, Any]) -> str:
    return json.dumps(result, indent=2, sort_keys=True) + "\n"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = load_and_project(args.history)
    print(render_projection(result), end="")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
