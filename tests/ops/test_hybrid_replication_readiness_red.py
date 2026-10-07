from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import scripts.ops.hybrid_replication_daemon as daemon
from nexus.research.hybrid_replication_live import _prepare_shadow_checkout
from nexus.research.hybrid_replication_pipeline import (
    READINESS_CONTROL_DISPOSITION,
    AutomaticReplicationController,
    AutomaticReplicationStore,
    FrozenStackOutcome,
    GroundTruthEvidence,
    RawRouteResult,
    TaskSnapshot,
)

READY = "AUTOMATIC_CAPTURE_READY"


def _require_readiness_evaluator():
    evaluator = getattr(daemon, "_evaluate_automatic_capture_readiness", None)
    assert callable(evaluator), (
        "RED: AUTOMATIC_CAPTURE_READY has no executable end-to-end readiness evaluator; "
        "activation can currently be asserted from partial/vacuous evidence"
    )
    return evaluator


def _healthy_ingest(*, expected_count: int = 1, mirrored_count: int = 1):
    return {
        "schema": "nexus.hybrid_replication.daemon_ingest.v1",
        "expected_count": expected_count,
        "mirrored_count": mirrored_count,
        "missing_capture": [],
        "missing_admission": [],
        "watchdog": {
            "schema": "nexus.hybrid_replication.intake_reconciliation.v1",
            "status": "COMPLETE",
            "missing": [],
            "backfilled": [],
        },
    }


def _healthy_advance():
    return {
        "schema": "nexus.hybrid_replication.daemon_advance.v1",
        "advanced": [],
        "failures": [],
    }


def test_ready_rejects_vacuous_zero_work_cycle() -> None:
    evaluator = _require_readiness_evaluator()

    result = evaluator(
        ingest_report=_healthy_ingest(expected_count=0, mirrored_count=0),
        advance_report=_healthy_advance(),
        launchd_loaded=True,
        control_phase=None,
    )

    assert result["status"] != READY
    assert "NON_VACUOUS_E2E_CONTROL_REQUIRED" in result["blockers"]


def test_ready_rejects_missing_physical_daemon_even_with_scored_control() -> None:
    evaluator = _require_readiness_evaluator()

    result = evaluator(
        ingest_report=_healthy_ingest(),
        advance_report=_healthy_advance(),
        launchd_loaded=False,
        control_phase="SCORED",
    )

    assert result["status"] != READY
    assert "DAEMON_NOT_LOADED" in result["blockers"]


def test_ready_rejects_watchdog_complete_when_advance_failed() -> None:
    evaluator = _require_readiness_evaluator()
    advance_report = {
        "schema": "nexus.hybrid_replication.daemon_advance.v1",
        "advanced": [],
        "failures": [
            {
                "task_key": "James3014/devspace#405",
                "phase": "ADMITTED",
                "error_type": "RuntimeError",
                "error": "shadow_checkout_failed:fatal: unable to read tree",
            }
        ],
    }

    result = evaluator(
        ingest_report=_healthy_ingest(),
        advance_report=advance_report,
        launchd_loaded=True,
        control_phase="SCORED",
    )

    assert result["status"] != READY
    assert "ADVANCE_FAILURE_PRESENT" in result["blockers"]


def test_shadow_checkout_hydrates_captured_remote_tracking_default_branch(
    tmp_path: Path,
) -> None:
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=upstream,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=upstream, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=upstream, check=True)

    (upstream / "file.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=upstream, check=True)
    subprocess.run(
        ["git", "commit", "-m", "base"],
        cwd=upstream,
        check=True,
        capture_output=True,
    )
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=upstream,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    (upstream / "file.txt").write_text("target\n", encoding="utf-8")
    subprocess.run(
        ["git", "commit", "-am", "target"],
        cwd=upstream,
        check=True,
        capture_output=True,
    )
    target = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=upstream,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    repo = tmp_path / "repo"
    subprocess.run(["git", "clone", str(upstream), str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "switch", "-c", "feature", base],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "branch", "-D", "main"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    assert (
        subprocess.run(
            ["git", "rev-parse", "refs/remotes/origin/main"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == target
    )

    shadow = tmp_path / "shadow"
    _prepare_shadow_checkout(repo=repo, revision=target, source=shadow)

    assert (
        subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=shadow,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        == target
    )


def _snapshot(issue: int = 9001) -> TaskSnapshot:
    return TaskSnapshot.create(
        repository="James3014/Nexus-new",
        issue_number=issue,
        created_at="2026-10-07T00:00:00Z",
        captured_at="2026-10-07T00:00:01Z",
        issue_updated_at="2026-10-07T00:00:00Z",
        title="Synthetic state-machine control",
        body="Exercise the automatic replication state machine without cohort admission.",
        pre_implementation_revision="1" * 40,
        default_branch="main",
        source_event_id=f"readiness-control:{issue}",
    )


def _c_outcome() -> FrozenStackOutcome:
    return FrozenStackOutcome(
        stratum="C",
        deterministic_receipt={"status": "INSUFFICIENT"},
        candidate_packet=None,
        jev_raw_response=None,
        dm1_decision=None,
        strong_online_raw_response={"answer": "control result"},
        raw_result=RawRouteResult.create(
            route="C",
            provider="agy",
            requested_model="gemini-3.8-flash-medium",
            resolved_model="gemini-3.8-flash-medium",
            model_call_count=1,
            input_tokens=1,
            uncached_input_tokens=1,
            output_tokens=1,
            wall_time_seconds=0.1,
            failures=(),
            retries=0,
            fallbacks=(),
            raw_response={"answer": "control result"},
        ),
    )


def test_automatic_control_path_reaches_scored_terminal_state(tmp_path: Path) -> None:
    store = AutomaticReplicationStore(tmp_path)
    snapshot = _snapshot()
    store.capture(snapshot, admission_disposition=READINESS_CONTROL_DISPOSITION)
    terminal = GroundTruthEvidence(
        terminal_state="PASS",
        terminal_at="2026-10-07T00:10:00Z",
        evidence_refs=("control:terminal",),
    )
    controller = AutomaticReplicationController(
        store=store,
        frozen_policy_sha256="5" * 64,
        stack_runner=lambda _: _c_outcome(),
        terminal_resolver=lambda _: terminal,
        clock=lambda: "2026-10-07T00:00:02Z",
    )

    state = controller.advance(snapshot.task_key)
    state = controller.advance(snapshot.task_key)

    assert state["phase"] == "SCORED"
    assert state["score"] is not None
    assert state["raw_seal"] is not None
    assert state["ground_truth"] is not None


def test_readiness_store_seam_rejects_tampered_score_receipt(tmp_path: Path, monkeypatch) -> None:
    store = AutomaticReplicationStore(tmp_path)
    snapshot = _snapshot(9002)
    store.capture(snapshot, admission_disposition=READINESS_CONTROL_DISPOSITION)
    terminal = GroundTruthEvidence(
        terminal_state="PASS",
        terminal_at="2026-10-07T00:10:00Z",
        evidence_refs=("control:terminal",),
    )
    controller = AutomaticReplicationController(
        store=store,
        frozen_policy_sha256="5" * 64,
        stack_runner=lambda _: _c_outcome(),
        terminal_resolver=lambda _: terminal,
        clock=lambda: "2026-10-07T00:00:02Z",
    )
    state = controller.advance(snapshot.task_key)
    assert state["phase"] == "SCORED"
    service_observation = {
        "schema": "nexus.hybrid_replication.service_observation.v1",
        "label": "com.nexus.hybrid-replication",
        "loaded": True,
        "observed_at": "2026-10-07T00:10:01Z",
    }

    ready = daemon.evaluate_readiness_from_store(
        store=store,
        ingest_report=_healthy_ingest(),
        advance_report=_healthy_advance(),
        control_task_key=snapshot.task_key,
        launchd_label="com.nexus.hybrid-replication",
        service_observation=service_observation,
    )
    assert ready["status"] == READY
    assert ready["control_score_valid"] is True
    assert ready["claim_ceiling"] == "READINESS_CONTROL_ONLY_NOT_PRIMARY_COHORT"

    score_path = store.tasks_root / "James3014__Nexus-new--9002" / "score.json"
    score_path.write_text("{}\n", encoding="utf-8")
    blocked = daemon.evaluate_readiness_from_store(
        store=store,
        ingest_report=_healthy_ingest(),
        advance_report=_healthy_advance(),
        control_task_key=snapshot.task_key,
        launchd_label="com.nexus.hybrid-replication",
        service_observation=service_observation,
    )
    assert blocked["status"] == "NOT_READY"
    assert "CONTROL_SCORE_INVALID" in blocked["blockers"]


def test_readiness_defers_non_control_admission_until_primary_activation(tmp_path: Path) -> None:
    store = AutomaticReplicationStore(tmp_path)
    snapshot = _snapshot(9006)
    store.capture(snapshot, admission_disposition=READINESS_CONTROL_DISPOSITION)
    terminal = GroundTruthEvidence(
        terminal_state="PASS",
        terminal_at="2026-10-07T00:10:00Z",
        evidence_refs=("control:terminal",),
    )
    controller = AutomaticReplicationController(
        store=store,
        frozen_policy_sha256="5" * 64,
        stack_runner=lambda _: _c_outcome(),
        terminal_resolver=lambda _: terminal,
        clock=lambda: "2026-10-07T00:00:02Z",
    )
    assert controller.advance(snapshot.task_key)["phase"] == "SCORED"
    ingest = _healthy_ingest(expected_count=3, mirrored_count=3)
    ingest["missing_admission"] = [
        "James3014/Nexus-new#9100",
        "James3014/devspace#9101",
    ]

    ready = daemon.evaluate_readiness_from_store(
        store=store,
        ingest_report=ingest,
        advance_report=_healthy_advance(),
        control_task_key=snapshot.task_key,
        launchd_label="com.nexus.hybrid-replication",
        service_observation={
            "schema": "nexus.hybrid_replication.service_observation.v1",
            "label": "com.nexus.hybrid-replication",
            "loaded": True,
            "observed_at": "2026-10-07T00:10:01Z",
        },
    )

    assert ready["status"] == READY
    assert "MISSING_ADMISSION" not in ready["blockers"]
    assert ready["deferred_non_control_missing_admission"] == [
        "James3014/Nexus-new#9100",
        "James3014/devspace#9101",
    ]


def test_readiness_still_rejects_missing_control_admission(tmp_path: Path) -> None:
    store = AutomaticReplicationStore(tmp_path)
    snapshot = _snapshot(9007)
    store.capture(snapshot, admission_disposition=READINESS_CONTROL_DISPOSITION)
    terminal = GroundTruthEvidence(
        terminal_state="PASS",
        terminal_at="2026-10-07T00:10:00Z",
        evidence_refs=("control:terminal",),
    )
    controller = AutomaticReplicationController(
        store=store,
        frozen_policy_sha256="5" * 64,
        stack_runner=lambda _: _c_outcome(),
        terminal_resolver=lambda _: terminal,
        clock=lambda: "2026-10-07T00:00:02Z",
    )
    assert controller.advance(snapshot.task_key)["phase"] == "SCORED"
    ingest = _healthy_ingest()
    ingest["missing_admission"] = [snapshot.task_key]

    blocked = daemon.evaluate_readiness_from_store(
        store=store,
        ingest_report=ingest,
        advance_report=_healthy_advance(),
        control_task_key=snapshot.task_key,
        launchd_label="com.nexus.hybrid-replication",
        service_observation={
            "schema": "nexus.hybrid_replication.service_observation.v1",
            "label": "com.nexus.hybrid-replication",
            "loaded": True,
            "observed_at": "2026-10-07T00:10:01Z",
        },
    )

    assert blocked["status"] == "NOT_READY"
    assert "MISSING_ADMISSION" in blocked["blockers"]
    assert blocked["deferred_non_control_missing_admission"] == []


def test_normal_daemon_defers_non_control_missing_admission_in_single_control_store(
    tmp_path: Path,
) -> None:
    store = AutomaticReplicationStore(tmp_path)
    control = _snapshot(9008)
    store.capture(control, admission_disposition=READINESS_CONTROL_DISPOSITION)

    blockers, deferred = daemon._partition_missing_admission_for_mode(
        store=store,
        missing_admission=[
            "James3014/Nexus-new#9100",
            "James3014/devspace#9101",
        ],
    )

    assert blockers == []
    assert deferred == [
        "James3014/Nexus-new#9100",
        "James3014/devspace#9101",
    ]


def test_normal_daemon_missing_admission_is_strict_without_unique_control_store(
    tmp_path: Path,
) -> None:
    missing = ["James3014/devspace#9101"]
    empty_store = AutomaticReplicationStore(tmp_path / "empty")

    blockers, deferred = daemon._partition_missing_admission_for_mode(
        store=empty_store,
        missing_admission=missing,
    )
    assert blockers == missing
    assert deferred == []

    multi_store = AutomaticReplicationStore(tmp_path / "multi")
    multi_store.capture(_snapshot(9009), admission_disposition=READINESS_CONTROL_DISPOSITION)
    multi_store.capture(_snapshot(9010), admission_disposition=READINESS_CONTROL_DISPOSITION)
    blockers, deferred = daemon._partition_missing_admission_for_mode(
        store=multi_store,
        missing_admission=missing,
    )
    assert blockers == missing
    assert deferred == []


def test_normal_daemon_missing_admission_is_strict_once_primary_is_admitted(
    tmp_path: Path,
) -> None:
    store = AutomaticReplicationStore(tmp_path)
    store.capture(_snapshot(9011), admission_disposition=READINESS_CONTROL_DISPOSITION)
    store.capture(_snapshot(9012), admission_disposition="ADMITTED_PRIMARY_FRESH_TASK")
    missing = ["James3014/devspace#9101"]

    blockers, deferred = daemon._partition_missing_admission_for_mode(
        store=store,
        missing_admission=missing,
    )

    assert blockers == missing
    assert deferred == []


def test_daemon_main_readiness_mode_consumes_store_and_launchd(tmp_path: Path, monkeypatch) -> None:
    store = AutomaticReplicationStore(tmp_path)
    snapshot = _snapshot(9003)
    store.capture(snapshot, admission_disposition=READINESS_CONTROL_DISPOSITION)
    terminal = GroundTruthEvidence(
        terminal_state="PASS",
        terminal_at="2026-10-07T00:10:00Z",
        evidence_refs=("control:terminal",),
    )
    controller = AutomaticReplicationController(
        store=store,
        frozen_policy_sha256="5" * 64,
        stack_runner=lambda _: _c_outcome(),
        terminal_resolver=lambda _: terminal,
        clock=lambda: "2026-10-07T00:00:02Z",
    )
    assert controller.advance(snapshot.task_key)["phase"] == "SCORED"

    monkeypatch.setattr(daemon, "ingest", lambda **_: _healthy_ingest())
    observation_path = tmp_path / "service-observation.json"
    observation_path.write_text(
        json.dumps({
            "schema": "nexus.hybrid_replication.service_observation.v1",
            "label": "com.nexus.hybrid-replication",
            "loaded": True,
            "observed_at": "2026-10-07T00:10:01Z",
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "hybrid_replication_daemon.py",
            "--root",
            str(tmp_path),
            "--since",
            "2026-10-07T00:00:00Z",
            "--frozen-policy-sha256",
            "5" * 64,
            "--stack-command",
            "unused",
            "--ground-truth-command",
            "unused",
            "--readiness-control-task-key",
            snapshot.task_key,
            "--service-observation",
            str(observation_path),
        ],
    )
    assert daemon.main() == 0


def test_readiness_store_seam_requires_bound_service_observation(tmp_path: Path) -> None:
    store = AutomaticReplicationStore(tmp_path)
    snapshot = _snapshot(9004)
    store.capture(snapshot, admission_disposition=READINESS_CONTROL_DISPOSITION)
    with pytest.raises(ValueError, match="service_observation_schema_mismatch"):
        daemon.evaluate_readiness_from_store(
            store=store,
            ingest_report=_healthy_ingest(),
            advance_report=_healthy_advance(),
            control_task_key=snapshot.task_key,
            launchd_label="com.nexus.hybrid-replication",
            service_observation={},
        )


def test_readiness_rejects_scored_control_with_failed_raw_outcome(tmp_path: Path) -> None:
    store = AutomaticReplicationStore(tmp_path)
    snapshot = _snapshot(9005)
    store.capture(snapshot, admission_disposition=READINESS_CONTROL_DISPOSITION)
    terminal = GroundTruthEvidence(
        terminal_state="PASS",
        terminal_at="2026-10-07T00:10:00Z",
        evidence_refs=("control:terminal",),
    )
    failed_outcome = FrozenStackOutcome(
        stratum="C",
        deterministic_receipt={"status": "INSUFFICIENT"},
        candidate_packet=None,
        jev_raw_response=None,
        dm1_decision=None,
        strong_online_raw_response={
            "status": "OUTCOME_UNKNOWN",
            "valid": False,
            "changed_files": [],
        },
        raw_result=RawRouteResult.create(
            route="C",
            provider="agy",
            requested_model="gemini-3.8-flash-medium",
            resolved_model="gemini-3.8-flash-medium",
            model_call_count=1,
            input_tokens=None,
            uncached_input_tokens=None,
            output_tokens=None,
            wall_time_seconds=307.5,
            failures=("OUTCOME_UNKNOWN",),
            retries=0,
            fallbacks=(),
            raw_response={
                "status": "OUTCOME_UNKNOWN",
                "valid": False,
                "changed_files": [],
            },
        ),
    )
    controller = AutomaticReplicationController(
        store=store,
        frozen_policy_sha256="5" * 64,
        stack_runner=lambda _: failed_outcome,
        terminal_resolver=lambda _: terminal,
        clock=lambda: "2026-10-07T00:00:02Z",
    )
    assert controller.advance(snapshot.task_key)["phase"] == "SCORED"

    ready = daemon.evaluate_readiness_from_store(
        store=store,
        ingest_report=_healthy_ingest(),
        advance_report=_healthy_advance(),
        control_task_key=snapshot.task_key,
        launchd_label="com.nexus.hybrid-replication",
        service_observation={
            "schema": "nexus.hybrid_replication.service_observation.v1",
            "label": "com.nexus.hybrid-replication",
            "loaded": True,
            "observed_at": "2026-10-07T00:10:01Z",
        },
    )

    assert ready["status"] == "NOT_READY"
    assert "CONTROL_RAW_FAILURE_PRESENT" in ready["blockers"]
    assert ready["control_raw_valid"] is False
    assert ready["control_raw_failures"] == ["OUTCOME_UNKNOWN"]
