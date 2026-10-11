#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nexus.research.hybrid_replication_pipeline import (
    ADMISSION_MARKER,
    CAPTURE_MARKER,
    READINESS_CONTROL_DISPOSITION,
    AutomaticReplicationController,
    AutomaticReplicationStore,
    ExternalFrozenStackRunner,
    ExternalGroundTruthResolver,
    parse_admission_comment,
    parse_capture_comment,
)

CANDIDATE_REPOSITORIES = (
    "James3014/Nexus-new",
    "James3014/devspace",
    "James3014/nexus-core",
    "James3014/nexus-learning",
    "James3014/nexus-open-swe-runtime",
    "James3014/repository-intelligence-engine",
    "James3014/nexus-runtime",
    "James3014/nexus-opencli-reviewer",
)


def _gh_json(*args: str) -> Any:
    completed = subprocess.run(  # nosec B603 B607
        ["gh", "api", *args],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"gh_api_failed:{completed.returncode}:{completed.stderr.strip()}")
    return json.loads(completed.stdout)


def _parse_github_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("github_timestamp_missing_timezone")
    return parsed.astimezone(timezone.utc)


def _capture_relevant_since(
    *,
    repository: str,
    issue: dict[str, Any],
    since: str,
) -> bool:
    del repository  # repository identity remains part of the caller contract.
    boundary = _parse_github_timestamp(since)
    created_at = _parse_github_timestamp(str(issue.get("created_at") or ""))
    return created_at >= boundary


def _issues_since(repository: str, since: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, 21):
        batch = _gh_json(
            "-X",
            "GET",
            f"repos/{repository}/issues",
            "-f",
            f"since={since}",
            "-f",
            "state=all",
            "-f",
            "per_page=100",
            "-f",
            f"page={page}",
        )
        if not isinstance(batch, list):
            raise RuntimeError("issues_response_not_list")
        for item in batch:
            if not isinstance(item, dict) or "pull_request" in item:
                continue
            if _capture_relevant_since(repository=repository, issue=item, since=since):
                rows.append(item)
        if len(batch) < 100:
            break
    return rows


def _comments(repository: str, issue_number: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, 11):
        batch = _gh_json(
            "-X",
            "GET",
            f"repos/{repository}/issues/{issue_number}/comments",
            "-f",
            "per_page=100",
            "-f",
            f"page={page}",
        )
        if not isinstance(batch, list):
            raise RuntimeError("comments_response_not_list")
        rows.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            break
    return rows


def _single_marker_comment(comments: list[dict[str, Any]], marker: str) -> str | None:
    matches = [
        str(item.get("body") or "") for item in comments if marker in str(item.get("body") or "")
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError(f"ambiguous_marker:{marker}")
    return matches[0]


def ingest(
    *,
    store: AutomaticReplicationStore,
    since: str,
) -> dict[str, Any]:
    expected: list[tuple[str, int]] = []
    missing_capture: list[str] = []
    missing_admission: list[str] = []
    mirrored: list[str] = []

    for repository in CANDIDATE_REPOSITORIES:
        for issue in _issues_since(repository, since):
            number = int(issue["number"])
            task_key = f"{repository}#{number}"
            expected.append((repository, number))
            comments = _comments(repository, number)
            capture_body = _single_marker_comment(comments, CAPTURE_MARKER)
            if capture_body is None:
                missing_capture.append(task_key)
                continue
            snapshot = parse_capture_comment(capture_body)
            state = store.load_task(task_key)
            if state is None:
                store.capture(
                    snapshot,
                    admission_disposition="PRE_AUTOMATION_PROVISIONAL_CAPTURE",
                )
            admission_body = _single_marker_comment(comments, ADMISSION_MARKER)
            if admission_body is None:
                missing_admission.append(task_key)
            else:
                admission = parse_admission_comment(admission_body)
                current = store.load_task(task_key)
                if current is None:
                    raise RuntimeError("capture_lost_before_admission")
                if not current.get("admission_receipt_sha256"):
                    store.apply_admission(admission)
            mirrored.append(task_key)

    watchdog = store.reconcile_expected_work_items(expected)
    return {
        "schema": "nexus.hybrid_replication.daemon_ingest.v1",
        "expected_count": len(expected),
        "mirrored_count": len(mirrored),
        "missing_capture": sorted(missing_capture),
        "missing_admission": sorted(missing_admission),
        "watchdog": watchdog,
    }


def _partition_missing_admission_for_mode(
    *,
    store: AutomaticReplicationStore,
    missing_admission: list[str],
    control_task_key: str | None = None,
) -> tuple[list[str], list[str]]:
    missing = sorted(str(item) for item in missing_admission)
    if control_task_key is None:
        return missing, []

    control_state = store.load_task(control_task_key)
    if (
        control_state is None
        or control_state.get("admission_disposition") != READINESS_CONTROL_DISPOSITION
    ):
        return missing, []

    for state_path in sorted(store.tasks_root.glob("*/state.json")):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("admission_disposition") == "ADMITTED_PRIMARY_FRESH_TASK":
            return missing, []

    blockers = [item for item in missing if item == control_task_key]
    deferred = [item for item in missing if item != control_task_key]
    return blockers, deferred


def advance_all(
    *,
    store: AutomaticReplicationStore,
    frozen_policy_sha256: str,
    stack_command: str,
    ground_truth_command: str,
    readiness_control_task_key: str | None = None,
) -> dict[str, Any]:
    stack_runner = ExternalFrozenStackRunner(stack_command)
    ground_truth_resolver = ExternalGroundTruthResolver(ground_truth_command)

    def terminal_resolver(state: dict[str, Any]):
        return ground_truth_resolver(state)

    controller = AutomaticReplicationController(
        store=store,
        frozen_policy_sha256=frozen_policy_sha256,
        stack_runner=stack_runner,
        terminal_resolver=terminal_resolver,
        clock=lambda: (
            __import__("datetime")
            .datetime.now(__import__("datetime").timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        ),
    )
    advanced: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for state_path in sorted(store.tasks_root.glob("*/state.json")):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        task_key = str(state["task_key"])
        disposition = state.get("admission_disposition")
        is_primary = disposition == "ADMITTED_PRIMARY_FRESH_TASK"
        is_readiness_control = (
            disposition == READINESS_CONTROL_DISPOSITION
            and readiness_control_task_key is not None
            and task_key == readiness_control_task_key
        )
        if not (is_primary or is_readiness_control):
            continue
        before = str(state.get("phase"))
        try:
            after = controller.advance(task_key)
        except Exception as exc:  # noqa: BLE001 - per-task fail-closed isolation
            failures.append({
                "task_key": task_key,
                "phase": before,
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            })
            continue
        advanced.append({
            "task_key": task_key,
            "before": before,
            "after": after.get("phase"),
        })
    return {
        "schema": "nexus.hybrid_replication.daemon_advance.v1",
        "advanced": advanced,
        "failures": failures,
    }


def _evaluate_automatic_capture_readiness(
    *,
    ingest_report: dict[str, Any],
    advance_report: dict[str, Any],
    launchd_loaded: bool,
    control_phase: str | None,
) -> dict[str, Any]:
    blockers: list[str] = []
    if (
        int(ingest_report.get("expected_count") or 0) <= 0
        or int(ingest_report.get("mirrored_count") or 0) <= 0
    ):
        blockers.append("NON_VACUOUS_E2E_CONTROL_REQUIRED")
    if ingest_report.get("missing_capture"):
        blockers.append("MISSING_CAPTURE")
    if ingest_report.get("missing_admission"):
        blockers.append("MISSING_ADMISSION")
    watchdog = ingest_report.get("watchdog") or {}
    if watchdog.get("status") != "COMPLETE":
        blockers.append("WATCHDOG_INCOMPLETE")
    if advance_report.get("failures"):
        blockers.append("ADVANCE_FAILURE_PRESENT")
    if not launchd_loaded:
        blockers.append("DAEMON_NOT_LOADED")
    if control_phase != "SCORED":
        blockers.append("CONTROL_NOT_SCORED")
    return {
        "schema": "nexus.hybrid_replication.automatic_capture_readiness.v1",
        "status": "AUTOMATIC_CAPTURE_READY" if not blockers else "NOT_READY",
        "blockers": blockers,
        "expected_count": int(ingest_report.get("expected_count") or 0),
        "mirrored_count": int(ingest_report.get("mirrored_count") or 0),
        "control_phase": control_phase,
        "launchd_loaded": bool(launchd_loaded),
    }


_DETERMINISTIC_CLOSURE_SCHEMA = "nexus.hybrid_replication.deterministic_dependency_closure.v1"


def _control_reached_dm1(raw: dict[str, Any]) -> bool:
    """True when the sealed control raw proves the DM1 intercept was reached.

    Route B/C raw (``run_frozen_stack``) carries ``raw_response.dm1_decision`` with an
    applicable decision and a choice (accepted, escalated, or fallback). Route A raw is
    acceptable only with the deterministic closure receipt.
    """
    response = raw.get("raw_response")
    if not isinstance(response, dict):
        return False
    if raw.get("route") == "A":
        return bool(
            response.get("schema") == _DETERMINISTIC_CLOSURE_SCHEMA
            and response.get("receipt_sha256")
        )
    decision = response.get("dm1_decision")
    if not isinstance(decision, dict):
        return False
    choice = decision.get("choice")
    return decision.get("applicable") is True and isinstance(choice, str) and bool(choice)


def evaluate_readiness_from_store(
    *,
    store: AutomaticReplicationStore,
    ingest_report: dict[str, Any],
    advance_report: dict[str, Any],
    control_task_key: str,
    launchd_label: str,
    service_observation: dict[str, Any],
    allow_control_without_dm1: bool = False,
) -> dict[str, Any]:
    control_state = store.load_task(control_task_key)
    control_phase = str(control_state.get("phase")) if control_state else None
    control_score_valid = False
    control_score_error: str | None = None
    control_raw_valid = False
    control_raw_failures: list[str] = []
    control_raw_error: str | None = None
    control_dm1_reached = False
    if control_phase == "SCORED":
        try:
            store.score_task(control_task_key)
            control_score_valid = True
        except (OSError, ValueError) as exc:
            control_score_error = f"{type(exc).__name__}:{exc}"
        if control_score_valid:
            try:
                raw = store.load_sealed_raw(control_task_key)
                control_raw_failures = [str(item) for item in raw.get("failures") or []]
                control_raw_valid = not control_raw_failures
                control_dm1_reached = _control_reached_dm1(raw)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                control_raw_error = f"{type(exc).__name__}:{exc}"

    if service_observation.get("schema") != "nexus.hybrid_replication.service_observation.v1":
        raise ValueError("service_observation_schema_mismatch")
    if service_observation.get("label") != launchd_label:
        raise ValueError("service_observation_label_mismatch")
    if not isinstance(service_observation.get("loaded"), bool):
        raise ValueError("service_observation_loaded_required")
    if not str(service_observation.get("observed_at") or ""):
        raise ValueError("service_observation_timestamp_required")

    readiness_ingest_report = dict(ingest_report)
    missing_admission_blockers, deferred_non_control_missing_admission = (
        _partition_missing_admission_for_mode(
            store=store,
            missing_admission=[str(item) for item in ingest_report.get("missing_admission") or []],
            control_task_key=control_task_key,
        )
    )
    readiness_ingest_report["missing_admission"] = missing_admission_blockers
    result = _evaluate_automatic_capture_readiness(
        ingest_report=readiness_ingest_report,
        advance_report=advance_report,
        launchd_loaded=bool(service_observation["loaded"]),
        control_phase=control_phase,
    )
    result["deferred_non_control_missing_admission"] = deferred_non_control_missing_admission
    blockers = list(result["blockers"])
    if control_phase == "SCORED" and not control_score_valid:
        blockers.append("CONTROL_SCORE_INVALID")
    if control_phase == "SCORED" and control_score_valid:
        if control_raw_error is not None:
            blockers.append("CONTROL_RAW_INVALID")
        elif control_raw_failures:
            blockers.append("CONTROL_RAW_FAILURE_PRESENT")
        if control_raw_error is None and not control_dm1_reached and not allow_control_without_dm1:
            blockers.append("CONTROL_DM1_NOT_REACHED")
    result["blockers"] = blockers
    result["status"] = "AUTOMATIC_CAPTURE_READY" if not blockers else "NOT_READY"
    result["control_task_key"] = control_task_key
    result["control_score_valid"] = control_score_valid
    result["control_score_error"] = control_score_error
    result["control_raw_valid"] = control_raw_valid
    result["control_raw_failures"] = control_raw_failures
    result["control_raw_error"] = control_raw_error
    result["control_dm1_reached"] = control_dm1_reached
    result["control_dm1_requirement"] = "WAIVED" if allow_control_without_dm1 else "REQUIRED"
    result["launchd_label"] = launchd_label
    result["service_observation"] = dict(service_observation)
    result["claim_ceiling"] = "READINESS_CONTROL_ONLY_NOT_PRIMARY_COHORT"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--since", required=True)
    parser.add_argument("--frozen-policy-sha256")
    parser.add_argument("--stack-command")
    parser.add_argument("--ground-truth-command")
    parser.add_argument("--ingest-only", action="store_true")
    parser.add_argument("--readiness-control-task-key")
    parser.add_argument("--deferred-admission-control-task-key")
    parser.add_argument("--launchd-label", default="com.nexus.hybrid-replication")
    parser.add_argument("--service-observation")
    parser.add_argument(
        "--allow-control-without-dm1",
        action="store_true",
        help="Owner waiver: accept a readiness control that never reached the DM1 intercept.",
    )
    args = parser.parse_args()
    if (
        args.readiness_control_task_key
        and args.deferred_admission_control_task_key
        and args.readiness_control_task_key != args.deferred_admission_control_task_key
    ):
        raise SystemExit("readiness and deferred-admission control task keys must match")

    store = AutomaticReplicationStore(Path(args.root))
    ingest_report = ingest(store=store, since=args.since)
    print(json.dumps(ingest_report, ensure_ascii=False, sort_keys=True, indent=2))

    if args.ingest_only:
        if ingest_report["missing_capture"]:
            return 3
        if ingest_report["missing_admission"]:
            return 4
        return 0
    if not (args.frozen_policy_sha256 and args.stack_command and args.ground_truth_command):
        raise SystemExit(
            "advance mode requires frozen policy, stack command, and ground-truth command"
        )
    advance_report = advance_all(
        store=store,
        frozen_policy_sha256=args.frozen_policy_sha256,
        stack_command=args.stack_command,
        ground_truth_command=args.ground_truth_command,
        readiness_control_task_key=args.readiness_control_task_key,
    )
    print(json.dumps(advance_report, ensure_ascii=False, sort_keys=True, indent=2))
    if args.readiness_control_task_key:
        if not args.service_observation:
            raise SystemExit("readiness mode requires --service-observation")
        service_observation = json.loads(Path(args.service_observation).read_text(encoding="utf-8"))
        readiness_report = evaluate_readiness_from_store(
            store=store,
            ingest_report=ingest_report,
            advance_report=advance_report,
            control_task_key=args.readiness_control_task_key,
            launchd_label=args.launchd_label,
            service_observation=service_observation,
            allow_control_without_dm1=args.allow_control_without_dm1,
        )
        print(json.dumps(readiness_report, ensure_ascii=False, sort_keys=True, indent=2))
        if readiness_report["status"] != "AUTOMATIC_CAPTURE_READY":
            return 6
    if advance_report["failures"]:
        return 5
    if ingest_report["missing_capture"]:
        return 3
    missing_admission_blockers, _ = _partition_missing_admission_for_mode(
        store=store,
        missing_admission=[str(item) for item in ingest_report.get("missing_admission") or []],
        control_task_key=(
            args.readiness_control_task_key or args.deferred_admission_control_task_key
        ),
    )
    if missing_admission_blockers:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
