#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404
from pathlib import Path
from typing import Any

from nexus.research.hybrid_replication_pipeline import (
    ADMISSION_MARKER,
    CAPTURE_MARKER,
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
            if isinstance(item, dict) and "pull_request" not in item:
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


def advance_all(
    *,
    store: AutomaticReplicationStore,
    frozen_policy_sha256: str,
    stack_command: str,
    ground_truth_command: str,
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
        if state.get("admission_disposition") != "ADMITTED_PRIMARY_FRESH_TASK":
            continue
        task_key = str(state["task_key"])
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--since", required=True)
    parser.add_argument("--frozen-policy-sha256")
    parser.add_argument("--stack-command")
    parser.add_argument("--ground-truth-command")
    parser.add_argument("--ingest-only", action="store_true")
    args = parser.parse_args()

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
    )
    print(json.dumps(advance_report, ensure_ascii=False, sort_keys=True, indent=2))
    if advance_report["failures"]:
        return 5
    if ingest_report["missing_capture"]:
        return 3
    if ingest_report["missing_admission"]:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
