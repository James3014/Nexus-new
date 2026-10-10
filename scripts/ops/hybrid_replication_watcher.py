#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from nexus.research.hybrid_replication_pipeline import (
    ADMISSION_MARKER,
    CAPTURE_MARKER,
    PRIMARY_ADMISSION_DISPOSITION,
    READINESS_CONTROL_DISPOSITION,
    AutomaticReplicationController,
    AutomaticReplicationStore,
    ExternalFrozenStackRunner,
    ExternalGroundTruthResolver,
    parse_admission_comment,
    parse_capture_comment,
)
from scripts.ops import hybrid_replication_daemon as daemon


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp_missing_timezone")
    return parsed.astimezone(timezone.utc)


def _issues_updated_since(
    repository: str,
    *,
    boundary: str,
    updated_since: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    boundary_time = _parse_timestamp(boundary)
    for page in range(1, 21):
        batch = daemon._gh_json(
            "-X",
            "GET",
            f"repos/{repository}/issues",
            "-f",
            f"since={updated_since}",
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
            created_at = _parse_timestamp(str(item.get("created_at") or ""))
            if created_at >= boundary_time:
                rows.append(item)
        if len(batch) < 100:
            return rows
    raise RuntimeError("issues_pagination_exceeds_bound")


def _mirror_issue(
    *,
    store: AutomaticReplicationStore,
    repository: str,
    issue: dict[str, Any],
) -> dict[str, Any]:
    number = int(issue["number"])
    task_key = f"{repository}#{number}"
    comments = daemon._comments(repository, number)
    capture_body = daemon._single_marker_comment(comments, CAPTURE_MARKER)
    if capture_body is None:
        return {"task_key": task_key, "capture": "MISSING", "admission": "UNKNOWN"}
    snapshot = parse_capture_comment(capture_body)
    state = store.load_task(task_key)
    if state is None:
        store.capture(snapshot, admission_disposition="PRE_AUTOMATION_PROVISIONAL_CAPTURE")
    admission_body = daemon._single_marker_comment(comments, ADMISSION_MARKER)
    if admission_body is None:
        return {"task_key": task_key, "capture": "PRESENT", "admission": "MISSING"}
    admission = parse_admission_comment(admission_body)
    state = store.load_task(task_key)
    if state is None:
        raise RuntimeError("capture_lost_before_admission")
    if not state.get("admission_receipt_sha256"):
        store.apply_admission(admission)
    return {"task_key": task_key, "capture": "PRESENT", "admission": "PRESENT"}


def fast_ingest(
    *,
    store: AutomaticReplicationStore,
    boundary: str,
    updated_since: str,
    pending_capture: set[str] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for repository in daemon.CANDIDATE_REPOSITORIES:
        for issue in _issues_updated_since(
            repository,
            boundary=boundary,
            updated_since=updated_since,
        ):
            row = _mirror_issue(store=store, repository=repository, issue=issue)
            rows.append(row)
            seen.add(str(row["task_key"]))

    for task_key in sorted(pending_capture or set()):
        if task_key in seen:
            continue
        repository, issue_text = task_key.rsplit("#", 1)
        issue = daemon._gh_json("-X", "GET", f"repos/{repository}/issues/{int(issue_text)}")
        if not isinstance(issue, dict):
            raise RuntimeError("issue_response_not_object")
        row = _mirror_issue(store=store, repository=repository, issue=issue)
        rows.append(row)
        seen.add(task_key)

    for state_path in sorted(store.tasks_root.glob("*/state.json")):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("phase") != "CAPTURED_PROVISIONAL":
            continue
        task_key = str(state.get("task_key") or "")
        if not task_key or task_key in seen:
            continue
        snapshot = state.get("snapshot") or {}
        repository = str(snapshot.get("repository") or "")
        issue_number = int(snapshot.get("issue_number") or 0)
        if not repository or not issue_number:
            raise ValueError("pending_admission_task_identity_missing")
        issue = daemon._gh_json("-X", "GET", f"repos/{repository}/issues/{issue_number}")
        if not isinstance(issue, dict):
            raise RuntimeError("issue_response_not_object")
        rows.append(_mirror_issue(store=store, repository=repository, issue=issue))

    return {
        "schema": "nexus.hybrid_replication.fast_ingest.v1",
        "updated_since": updated_since,
        "observed_at": _utc_now(),
        "rows": rows,
    }


def _task_keys_ready_for_advance(
    *,
    store: AutomaticReplicationStore,
    readiness_control_task_key: str | None,
) -> list[str]:
    ready: list[str] = []
    for state_path in sorted(store.tasks_root.glob("*/state.json")):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        task_key = str(state.get("task_key") or "")
        disposition = state.get("admission_disposition")
        is_primary = disposition == PRIMARY_ADMISSION_DISPOSITION
        is_control = (
            disposition == READINESS_CONTROL_DISPOSITION
            and readiness_control_task_key is not None
            and task_key == readiness_control_task_key
        )
        if not (is_primary or is_control):
            continue
        if state_path.parent.joinpath("prospective_protocol_loss.json").exists():
            continue
        if state.get("phase") in {"ADMITTED", "RAW_SEALED", "GROUND_TRUTH_BOUND"}:
            ready.append(task_key)
    return ready


def full_watchdog(
    *,
    store: AutomaticReplicationStore,
    boundary: str,
) -> dict[str, Any]:
    """Read-only full intake census; never blocks or mutates the fast path."""

    expected: list[tuple[str, int]] = []
    for repository in daemon.CANDIDATE_REPOSITORIES:
        for issue in daemon._issues_since(repository, boundary):
            expected.append((repository, int(issue["number"])))
    report = store.reconcile_expected_work_items(expected)
    return {
        "schema": "nexus.hybrid_replication.watcher_full_reconcile.v1",
        "observed_at": _utc_now(),
        "expected_count": len(expected),
        **report,
    }


def _advance_one(
    *,
    store: AutomaticReplicationStore,
    task_key: str,
    frozen_policy_sha256: str,
    stack_command: str,
    ground_truth_command: str,
) -> dict[str, Any]:
    controller = AutomaticReplicationController(
        store=store,
        frozen_policy_sha256=frozen_policy_sha256,
        stack_runner=ExternalFrozenStackRunner(stack_command),
        terminal_resolver=ExternalGroundTruthResolver(ground_truth_command),
        clock=_utc_now,
    )
    before = store.load_task(task_key)
    if before is None:
        raise ValueError("task_state_missing_before_advance")
    after = controller.advance(task_key)
    return {
        "task_key": task_key,
        "before": before.get("phase"),
        "after": after.get("phase"),
    }


def run_watcher(
    *,
    root: Path,
    boundary: str,
    frozen_policy_sha256: str,
    stack_command: str,
    ground_truth_command: str,
    readiness_control_task_key: str | None = None,
    poll_seconds: float = 1.0,
    full_reconcile_seconds: float = 30.0,
    overlap_seconds: float = 3.0,
    max_workers: int = 4,
    max_loops: int | None = None,
) -> int:
    if poll_seconds <= 0 or full_reconcile_seconds <= 0 or overlap_seconds < 0:
        raise ValueError("invalid_watcher_timing")
    if max_workers < 1:
        raise ValueError("watcher_max_workers_required")
    if "--store-root" not in stack_command:
        raise ValueError("prospective_stack_command_requires_store_root")

    store = AutomaticReplicationStore(root)
    last_poll = _parse_timestamp(boundary)
    pending_capture: set[str] = set()
    last_full = 0.0
    active: dict[str, Future[dict[str, Any]]] = {}
    watchdog_future: Future[dict[str, Any]] | None = None
    loops = 0

    with (
        ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="hybrid-task") as pool,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="hybrid-watchdog") as watchdog_pool,
    ):
        while True:
            now = datetime.now(timezone.utc)
            updated_since = (
                (last_poll - timedelta(seconds=overlap_seconds)).isoformat().replace("+00:00", "Z")
            )
            report = fast_ingest(
                store=store,
                boundary=boundary,
                updated_since=updated_since,
                pending_capture=pending_capture,
            )
            for row in report["rows"]:
                task_key = str(row["task_key"])
                if row.get("capture") == "MISSING":
                    pending_capture.add(task_key)
                else:
                    pending_capture.discard(task_key)
            if report["rows"]:
                print(json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)
            last_poll = now

            for task_key, future in list(active.items()):
                if not future.done():
                    continue
                del active[task_key]
                try:
                    result = future.result()
                    print(
                        json.dumps(
                            {"schema": "nexus.hybrid_replication.watcher_advance.v1", **result},
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                except Exception as exc:  # noqa: BLE001 - durable task state remains source of truth
                    print(
                        json.dumps(
                            {
                                "schema": "nexus.hybrid_replication.watcher_failure.v1",
                                "task_key": task_key,
                                "error_type": type(exc).__name__,
                                "error": str(exc)[:1000],
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        flush=True,
                    )

            for task_key in _task_keys_ready_for_advance(
                store=store,
                readiness_control_task_key=readiness_control_task_key,
            ):
                if task_key in active:
                    continue
                active[task_key] = pool.submit(
                    _advance_one,
                    store=store,
                    task_key=task_key,
                    frozen_policy_sha256=frozen_policy_sha256,
                    stack_command=stack_command,
                    ground_truth_command=ground_truth_command,
                )

            if watchdog_future is not None and watchdog_future.done():
                try:
                    print(
                        json.dumps(
                            watchdog_future.result(),
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                except Exception as exc:  # noqa: BLE001 - fast path stays live; report is diagnostic
                    print(
                        json.dumps(
                            {
                                "schema": "nexus.hybrid_replication.watcher_full_reconcile_failure.v1",
                                "error_type": type(exc).__name__,
                                "error": str(exc)[:1000],
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                watchdog_future = None

            monotonic_now = time.monotonic()
            if watchdog_future is None and monotonic_now - last_full >= full_reconcile_seconds:
                watchdog_future = watchdog_pool.submit(
                    full_watchdog,
                    store=store,
                    boundary=boundary,
                )
                last_full = monotonic_now

            loops += 1
            if max_loops is not None and loops >= max_loops:
                return 0
            time.sleep(poll_seconds)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--since", required=True)
    parser.add_argument("--frozen-policy-sha256", required=True)
    parser.add_argument("--stack-command", required=True)
    parser.add_argument("--ground-truth-command", required=True)
    parser.add_argument("--readiness-control-task-key")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--full-reconcile-seconds", type=float, default=30.0)
    parser.add_argument("--overlap-seconds", type=float, default=3.0)
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()
    return run_watcher(
        root=Path(args.root),
        boundary=args.since,
        frozen_policy_sha256=args.frozen_policy_sha256,
        stack_command=args.stack_command,
        ground_truth_command=args.ground_truth_command,
        readiness_control_task_key=args.readiness_control_task_key,
        poll_seconds=args.poll_seconds,
        full_reconcile_seconds=args.full_reconcile_seconds,
        overlap_seconds=args.overlap_seconds,
        max_workers=args.max_workers,
    )


if __name__ == "__main__":
    raise SystemExit(main())
