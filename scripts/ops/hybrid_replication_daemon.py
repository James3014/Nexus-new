#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess  # nosec B404
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from nexus.research.hybrid_replication_pipeline import (
    ADMISSION_MARKER,
    CAPTURE_MARKER,
    READINESS_CONTROL_DISPOSITION,
    AutomaticReplicationController,
    AutomaticReplicationStore,
    ExternalFrozenStackRunner,
    ExternalGroundTruthResolver,
    TaskSnapshot,
    parse_admission_comment,
    parse_capture_comment,
)
from nexus.research.hybrid_replication_prospective import (
    ProspectiveExecutionGuard,
    ProspectiveProtocolLoss,
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


# Comments are re-read only when the issue's updated_at and listed comment count are unchanged
# and the cached copy is younger than COMMENT_CACHE_TTL_SECONDS. The count catches a comment
# added or deleted within the same updated_at second, or a deletion that does not bump
# updated_at. Ported from the Owner-approved V12 in-place patch (2026-10-15, #1216/#2252) to stop
# exhausting the owner's GitHub API quota without changing what ingest observes.
COMMENT_CACHE_TTL_SECONDS = 600

# Maximum age of this run's issue listing when it is used to skip the ground-truth subprocess.
LISTED_STATE_MAX_AGE_SECONDS = 120


def _write_comment_cache(path: Path, payload: dict[str, Any]) -> None:
    tmp_name: str | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False)
        os.replace(tmp_name, path)
    except OSError:
        # Best effort: the cache is an optimisation, ingest continues with fetched comments.
        _discard_temp(tmp_name)
    except BaseException:
        _discard_temp(tmp_name)
        raise


def _discard_temp(tmp_name: str | None) -> None:
    if tmp_name is None:
        return
    try:
        Path(tmp_name).unlink(missing_ok=True)
    except OSError:
        pass  # a leftover *.tmp is harmless: readers only open <n>.json


def _cached_comments(
    cache_root: Path,
    repository: str,
    issue: dict[str, Any],
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    number = int(issue["number"])
    updated_at = str(issue.get("updated_at") or "")
    listed_count = issue.get("comments")
    count_usable = isinstance(listed_count, int) and not isinstance(listed_count, bool)
    path = cache_root / repository.replace("/", "__") / f"{number}.json"
    now = now or datetime.now(timezone.utc)
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        fetched_at = _parse_github_timestamp(str(cached["fetched_at"]))
        if (
            updated_at
            and count_usable
            and cached.get("updated_at") == updated_at
            and cached.get("comment_count") == listed_count
            and 0 <= (now - fetched_at).total_seconds() < COMMENT_CACHE_TTL_SECONDS
            and isinstance(cached.get("comments"), list)
        ):
            return cached["comments"]
    except (OSError, ValueError, KeyError, TypeError):
        pass  # unreadable or malformed cache: refetch (json errors are ValueError)
    comments = _comments(repository, number)
    _write_comment_cache(
        path,
        {
            "updated_at": updated_at,
            "fetched_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "comment_count": listed_count if count_usable else None,
            "comments": comments,
        },
    )
    return comments


# Issues created with the workflow GITHUB_TOKEN never trigger workflows (GitHub platform
# rule), so the capture workflow never runs for them (e.g. the nightly regression bot's
# issues). The capture workflow itself has no author filter: a bot-authored issue that does
# carry a capture comment is mirrored like any other. REST reports the login as
# "github-actions[bot]"; `gh issue view` shows "app/github-actions".
GITHUB_TOKEN_BOT_LOGINS = frozenset({"github-actions[bot]", "app/github-actions"})


def is_uncaptured_github_token_issue(issue: dict[str, Any], comments: list[dict[str, Any]]) -> bool:
    """True when a GITHUB_TOKEN-authored issue has no capture comment (never expected)."""

    login = str((issue.get("user") or {}).get("login") or "")
    if login not in GITHUB_TOKEN_BOT_LOGINS:
        return False
    return not any(CAPTURE_MARKER in str(item.get("body") or "") for item in comments)


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
    listed_issue_states: dict[tuple[str, int], str] | None = None,
) -> dict[str, Any]:
    expected: list[tuple[str, int]] = []
    missing_capture: list[str] = []
    not_captured_github_token_issue: list[str] = []
    missing_admission: list[str] = []
    mirrored: list[str] = []

    for repository in CANDIDATE_REPOSITORIES:
        for issue in _issues_since(repository, since):
            number = int(issue["number"])
            task_key = f"{repository}#{number}"
            if listed_issue_states is not None:
                listed_issue_states[(repository, number)] = str(issue.get("state") or "")
            comments = _cached_comments(store.root / "comment-cache", repository, issue)
            if is_uncaptured_github_token_issue(issue, comments):
                not_captured_github_token_issue.append(task_key)
                continue
            expected.append((repository, number))
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
        "not_captured_github_token_issue": sorted(not_captured_github_token_issue),
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


def _protocol_loss_path(store: AutomaticReplicationStore, task_key: str) -> Path:
    return store._dir(task_key) / "prospective_protocol_loss.json"  # noqa: SLF001


def _loss_entry(
    store: AutomaticReplicationStore, task_key: str, *, newly_recorded: bool
) -> dict[str, Any]:
    reason = ""
    try:
        payload = json.loads(_protocol_loss_path(store, task_key).read_text(encoding="utf-8"))
        reason = str(payload.get("reason") or "")
    except (OSError, ValueError):
        pass
    return {"task_key": task_key, "reason": reason, "newly_recorded": newly_recorded}


def _take_execution_start_fence(store: AutomaticReplicationStore, task_key: str) -> bool:
    """Write execution_start for an ADMITTED task now, without waiting for its stack call.

    Uses a non-blocking flock on the per-task ``execution.lock`` (a per-open-file-description
    lock, exclusive across threads and processes). If another worker already holds the lock the
    task is executing (its subprocess takes the fence itself) and nothing is done. Returns True
    when this call held the lock. The stack subprocess later finds ``execution_start.json`` and
    reuses it (idempotent).
    """
    state = store.load_task(task_key)
    if state is None:
        raise ValueError("task_capture_missing")
    snapshot = TaskSnapshot.from_capture_payload(dict(state["snapshot"]))
    guard = ProspectiveExecutionGuard(store_root=store.root, snapshot=snapshot)
    guard.task_dir.mkdir(parents=True, exist_ok=True)
    with (guard.task_dir / "execution.lock").open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        try:
            guard.ensure_execution_start()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return True


@contextmanager
def ingest_lock(store: AutomaticReplicationStore) -> Iterator[None]:
    """Serialize ingest between overlapping invocations (fence-only and main daemon).

    Blocking flock on ``<root>/ingest.lock`` (per open file, exclusive across threads and
    processes). It is held only for ingest, never across advance or stack calls.
    """
    store.root.mkdir(parents=True, exist_ok=True)
    with (store.root / "ingest.lock").open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def fence_all(
    *,
    store: AutomaticReplicationStore,
    max_workers: int = 8,
) -> dict[str, Any]:
    """Take execution_start for every ADMITTED primary task; never advance or call a stack.

    Safe beside a running main daemon: the per-task flock is non-blocking, so a task that is
    currently executing is reported in ``already_executing`` and left alone.
    """
    fenced: list[str] = []
    already_executing: list[str] = []
    failures: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    keys: list[str] = []
    for state_path in sorted(store.tasks_root.glob("*/state.json")):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        task_key = str(state["task_key"])
        if state.get("admission_disposition") != "ADMITTED_PRIMARY_FRESH_TASK":
            continue
        if state.get("phase") != "ADMITTED":
            continue
        if _protocol_loss_path(store, task_key).is_file():
            excluded.append(_loss_entry(store, task_key, newly_recorded=False))
            continue
        keys.append(task_key)

    def fence(task_key: str) -> tuple[str, bool | Exception]:
        try:
            return task_key, _take_execution_start_fence(store, task_key)
        except Exception as exc:  # noqa: BLE001 - per-task fail-closed isolation
            return task_key, exc

    if keys:
        with ThreadPoolExecutor(max_workers=max(1, min(len(keys), max_workers))) as pool:
            results = list(pool.map(fence, keys))
        for task_key, outcome in results:
            if outcome is True:
                fenced.append(task_key)
            elif outcome is False:
                already_executing.append(task_key)
            elif _protocol_loss_path(store, task_key).is_file():
                excluded.append(_loss_entry(store, task_key, newly_recorded=True))
            else:
                failures.append({
                    "task_key": task_key,
                    "phase": "ADMITTED",
                    "error_type": type(outcome).__name__,
                    "error": str(outcome)[:500],
                })
    return {
        "schema": "nexus.hybrid_replication.daemon_fence.v1",
        "fenced": fenced,
        "already_executing": already_executing,
        "failures": failures,
        "excluded_protocol_loss": sorted(excluded, key=lambda e: e["task_key"]),
    }


def advance_all(
    *,
    store: AutomaticReplicationStore,
    frozen_policy_sha256: str,
    stack_command: str,
    ground_truth_command: str,
    readiness_control_task_key: str | None = None,
    max_concurrent_tasks: int = 1,
    listed_issue_states: Mapping[tuple[str, int], str] | None = None,
    listed_at_monotonic: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Advance every executable task.

    ``max_concurrent_tasks == 1`` keeps the historical serial behaviour. With N > 1 the
    execution_start fence is first taken for every ADMITTED primary task (so a task never
    waits behind another task's long provider call), then up to N tasks advance concurrently.

    Tasks with an existing ``prospective_protocol_loss.json`` (D2 exclusion) are skipped and
    listed in ``excluded_protocol_loss``; they never count as failures. A loss first recorded
    during this run is also reported there with ``newly_recorded: true`` and does not make the
    run fail: it is a recorded, non-counting exclusion, not an operational error.
    """
    if max_concurrent_tasks < 1:
        raise ValueError("max_concurrent_tasks_must_be_positive")
    stack_runner = ExternalFrozenStackRunner(stack_command)
    ground_truth_resolver = ExternalGroundTruthResolver(ground_truth_command)

    def terminal_resolver(state: dict[str, Any]):
        # V12 patch (#1216/#2252): skip the ground-truth subprocess for a task whose issue this
        # run's listing shows open, while that listing is at most LISTED_STATE_MAX_AGE_SECONDS
        # old at call time (a long stack run earlier in this advance makes it stale). The
        # subprocess would only return "not closed" (see _resolve_ground_truth_from_state in
        # nexus/research/hybrid_replication_live.py, which returns None for a non-closed issue).
        # A close between listing and resolution is picked up on the next tick; closed_at is
        # unchanged.
        if listed_issue_states is not None and listed_at_monotonic is not None:
            snapshot = state.get("snapshot") or {}
            key = (str(snapshot.get("repository") or ""), int(snapshot.get("issue_number") or 0))
            fresh = monotonic() - listed_at_monotonic <= LISTED_STATE_MAX_AGE_SECONDS
            if fresh and listed_issue_states.get(key) == "open":
                return None
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
    excluded: list[dict[str, Any]] = []
    # (task_key, phase_before, is_readiness_control)
    work: list[tuple[str, str, bool]] = []
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
        if _protocol_loss_path(store, task_key).is_file():
            excluded.append(_loss_entry(store, task_key, newly_recorded=False))
            continue
        work.append((task_key, str(state.get("phase")), is_readiness_control))

    advanced_by_key: dict[str, dict[str, Any]] = {}
    failures_by_key: dict[str, dict[str, Any]] = {}

    def record_failure(task_key: str, before: str, exc: Exception) -> None:
        if _protocol_loss_path(store, task_key).is_file():
            excluded.append(_loss_entry(store, task_key, newly_recorded=True))
            return
        failures_by_key[task_key] = {
            "task_key": task_key,
            "phase": before,
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }

    runnable = list(work)
    if max_concurrent_tasks > 1:
        fence_keys = [
            (key, before)
            for key, before, is_control in work
            if before == "ADMITTED" and not is_control
        ]

        def fence(item: tuple[str, str]) -> tuple[str, str, Exception | None]:
            try:
                _take_execution_start_fence(store, item[0])
            except ProspectiveProtocolLoss as exc:
                return item[0], item[1], exc
            except Exception as exc:  # noqa: BLE001 - per-task fail-closed isolation
                return item[0], item[1], exc
            return item[0], item[1], None

        if fence_keys:
            with ThreadPoolExecutor(max_workers=min(len(fence_keys), 8)) as pool:
                fence_results = list(pool.map(fence, fence_keys))
            fenced_out = set()
            for key, before, exc in fence_results:
                if exc is not None:
                    fenced_out.add(key)
                    record_failure(key, before, exc)
            runnable = [item for item in work if item[0] not in fenced_out]

    def run_one(item: tuple[str, str, bool]) -> tuple[str, str, dict[str, Any] | Exception]:
        task_key, before, _ = item
        try:
            return task_key, before, controller.advance(task_key)
        except Exception as exc:  # noqa: BLE001 - per-task fail-closed isolation
            return task_key, before, exc

    if runnable:
        with ThreadPoolExecutor(max_workers=max_concurrent_tasks) as pool:
            results = list(pool.map(run_one, runnable))
        for task_key, before, outcome in results:
            if isinstance(outcome, Exception):
                record_failure(task_key, before, outcome)
            else:
                advanced_by_key[task_key] = {
                    "task_key": task_key,
                    "before": before,
                    "after": outcome.get("phase"),
                }

    order = [item[0] for item in work]
    advanced = [advanced_by_key[k] for k in order if k in advanced_by_key]
    failures = [failures_by_key[k] for k in order if k in failures_by_key]
    return {
        "schema": "nexus.hybrid_replication.daemon_advance.v1",
        "advanced": advanced,
        "failures": failures,
        "excluded_protocol_loss": sorted(excluded, key=lambda e: e["task_key"]),
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
    parser.add_argument(
        "--fence-only",
        action="store_true",
        help="Ingest, take execution_start for ADMITTED primary tasks, print and exit. "
        "No advance, no stack or ground-truth calls.",
    )
    parser.add_argument(
        "--max-concurrent-tasks",
        type=int,
        default=1,
        help="Advance up to N tasks concurrently (default 1 = serial).",
    )
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
    if args.max_concurrent_tasks < 1:
        raise SystemExit("--max-concurrent-tasks must be >= 1")
    if (
        args.readiness_control_task_key
        and args.deferred_admission_control_task_key
        and args.readiness_control_task_key != args.deferred_admission_control_task_key
    ):
        raise SystemExit("readiness and deferred-admission control task keys must match")

    store = AutomaticReplicationStore(Path(args.root))
    listed_issue_states: dict[tuple[str, int], str] = {}
    listed_at = time.monotonic()
    with ingest_lock(store):
        ingest_report = ingest(
            store=store, since=args.since, listed_issue_states=listed_issue_states
        )
    print(json.dumps(ingest_report, ensure_ascii=False, sort_keys=True, indent=2))

    if args.fence_only:
        fence_report = fence_all(store=store)
        print(json.dumps(fence_report, ensure_ascii=False, sort_keys=True, indent=2))
        if fence_report["failures"]:
            return 5
        if ingest_report["missing_capture"]:
            return 3
        if ingest_report["missing_admission"]:
            return 4
        return 0

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
        max_concurrent_tasks=args.max_concurrent_tasks,
        listed_issue_states=listed_issue_states,
        listed_at_monotonic=listed_at,
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
