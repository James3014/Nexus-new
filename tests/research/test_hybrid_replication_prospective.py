from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.research import hybrid_replication_prospective as prospective
from nexus.research.hybrid_replication_pipeline import (
    AdmissionReceipt,
    AutomaticReplicationStore,
    TaskSnapshot,
    build_admission_comment,
)
from nexus.research.hybrid_replication_prospective import (
    ProspectiveExecutionGuard,
    ProspectiveProtocolLoss,
)


def _snapshot(issue: int = 1600) -> TaskSnapshot:
    return TaskSnapshot.create(
        repository="James3014/Nexus-new",
        issue_number=issue,
        created_at="2026-10-07T12:00:00Z",
        captured_at="2026-10-07T12:00:01Z",
        issue_updated_at="2026-10-07T12:00:00Z",
        title="Short-lived prospective control",
        body="Implement one bounded shadow-only change.",
        pre_implementation_revision="a" * 40,
        default_branch="main",
        source_event_id=f"control:{issue}",
    )


def _admitted_store(
    root: Path, snapshot: TaskSnapshot
) -> tuple[AutomaticReplicationStore, AdmissionReceipt]:
    store = AutomaticReplicationStore(root)
    store.capture(snapshot, admission_disposition="PRE_AUTOMATION_PROVISIONAL_CAPTURE")
    receipt = AdmissionReceipt.create(
        snapshot=snapshot,
        disposition="ADMITTED_PRIMARY_FRESH_TASK",
        activation_boundary="2026-10-07T11:59:59Z",
        activation_state="AUTOMATIC_CAPTURE_READY",
        exclusion_set_sha256="6" * 64,
        issue_state_at_admission="open",
        implementation_pr_numbers=(),
        tracked_parent_issue_number=None,
        tracked_parent_created_at=None,
        admitted_at="2026-10-07T12:00:02Z",
    )
    store.apply_admission(receipt)
    return store, receipt


def _bind_github(
    monkeypatch: pytest.MonkeyPatch,
    *,
    snapshot: TaskSnapshot,
    receipt: AdmissionReceipt,
    issue_state: str = "open",
    closed_at: str | None = None,
    closed_events: list[dict[str, object]] | None = None,
) -> None:
    admission_comment = build_admission_comment(receipt)

    def fake_list(path: str) -> list[dict[str, object]]:
        if path.endswith("/comments"):
            return [{"body": admission_comment}]
        if path.endswith("/events"):
            return list(closed_events or [])
        raise AssertionError(path)

    def fake_json(*args: str) -> dict[str, object]:
        path = args[-1]
        assert path.endswith(f"/issues/{snapshot.issue_number}")
        return {
            "number": snapshot.issue_number,
            "state": issue_state,
            "closed_at": closed_at,
            "updated_at": closed_at or "2026-10-07T12:00:02Z",
        }

    monkeypatch.setattr(prospective, "_gh_list", fake_list)
    monkeypatch.setattr(prospective, "_gh_json", fake_json)


def test_execution_start_binds_exact_admission_before_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot()
    _, receipt = _admitted_store(tmp_path, snapshot)
    _bind_github(monkeypatch, snapshot=snapshot, receipt=receipt)
    guard = ProspectiveExecutionGuard(store_root=tmp_path, snapshot=snapshot)

    start = guard.ensure_execution_start()
    second = guard.ensure_execution_start()

    assert start == second
    assert start["capture_sha256"] == snapshot.capture_sha256
    assert start["admission_receipt_sha256"] == receipt.receipt_sha256
    assert (guard.task_dir / "execution_start.json").is_file()


def test_terminal_before_execution_start_fails_closed_without_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot(1601)
    _, receipt = _admitted_store(tmp_path, snapshot)
    _bind_github(
        monkeypatch,
        snapshot=snapshot,
        receipt=receipt,
        issue_state="closed",
        closed_at="2026-10-07T12:00:03Z",
        closed_events=[{"event": "closed", "id": 77, "created_at": "2026-10-07T12:00:03Z"}],
    )
    guard = ProspectiveExecutionGuard(store_root=tmp_path, snapshot=snapshot)

    with pytest.raises(ProspectiveProtocolLoss, match="TERMINAL_BEFORE_EXECUTION_START"):
        guard.ensure_execution_start()

    loss = json.loads(guard.protocol_loss_path.read_text(encoding="utf-8"))
    assert loss["reason"] == "TERMINAL_BEFORE_EXECUTION_START"
    assert not (guard.task_dir / "execution_start.json").exists()


def test_provider_started_after_terminal_marks_protocol_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot(1602)
    _, receipt = _admitted_store(tmp_path, snapshot)
    _bind_github(
        monkeypatch,
        snapshot=snapshot,
        receipt=receipt,
        closed_events=[{"event": "closed", "id": 88, "created_at": "2026-10-07T12:00:05Z"}],
    )
    guard = ProspectiveExecutionGuard(store_root=tmp_path, snapshot=snapshot)

    with pytest.raises(ProspectiveProtocolLoss, match="PROVIDER_STARTED_AFTER_TERMINAL"):
        guard.observe_provider_start(
            slot="c",
            record={
                "operation_id": "agyop_late",
                "provider_started_at": "2026-10-07T12:00:06Z",
                "observed_model": "later-filled-field",
            },
        )

    start_receipt = json.loads(guard.provider_start_path("c").read_text(encoding="utf-8"))
    assert start_receipt == {
        "schema": "nexus.hybrid_replication.provider_start.v1",
        "task_key": snapshot.task_key,
        "capture_sha256": snapshot.capture_sha256,
        "slot": "c",
        "operation_id": "agyop_late",
        "provider_started_at": "2026-10-07T12:00:06Z",
    }
    assert json.loads(guard.protocol_loss_path.read_text(encoding="utf-8"))["reason"] == (
        "PROVIDER_STARTED_AFTER_TERMINAL"
    )


def test_provider_start_receipt_is_stable_when_journal_later_fills_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot(1603)
    _, receipt = _admitted_store(tmp_path, snapshot)
    _bind_github(monkeypatch, snapshot=snapshot, receipt=receipt)
    guard = ProspectiveExecutionGuard(store_root=tmp_path, snapshot=snapshot)

    guard.observe_provider_start(
        slot="c",
        record={"operation_id": "agyop_same", "provider_started_at": "2026-10-07T12:00:04Z"},
    )
    first = guard.provider_start_path("c").read_bytes()
    guard.observe_provider_start(
        slot="c",
        record={
            "operation_id": "agyop_same",
            "provider_started_at": "2026-10-07T12:00:04Z",
            "observed_provider": "agy",
            "observed_model": "gemini-3.8-flash-medium",
        },
    )
    assert guard.provider_start_path("c").read_bytes() == first


def test_lost_ack_recovers_same_journal_operation_without_identity_drift(tmp_path: Path) -> None:
    snapshot = _snapshot(1604)
    _admitted_store(tmp_path / "store", snapshot)
    guard = ProspectiveExecutionGuard(store_root=tmp_path / "store", snapshot=snapshot)
    operation_root = tmp_path / "ops"
    cwd = guard.shadow_source("c")
    cwd.mkdir(parents=True)
    op = operation_root / "operations" / "agyop_existing"
    op.mkdir(parents=True)
    record = {
        "operation_id": "agyop_existing",
        "provider": "agy",
        "model": "gemini-3.8-flash-medium",
        "prompt_sha256": "1" * 64,
        "cwd": str(cwd.resolve()),
        "created_at": "2026-10-07T12:00:03Z",
        "status": "RUNNING",
    }
    (op / "operation.json").write_text(json.dumps(record), encoding="utf-8")

    recovered = guard.recover_provider_operation(
        slot="c",
        operation_root=operation_root,
        prompt_sha256="1" * 64,
        cwd=cwd,
        model="gemini-3.8-flash-medium",
        mode="accept-edits",
    )

    assert recovered is not None
    assert recovered["operation_id"] == "agyop_existing"
    receipt = json.loads(guard.provider_operation_path("c").read_text(encoding="utf-8"))
    assert receipt["operation_id"] == "agyop_existing"
    assert "started_at" not in receipt
    assert "recovered_from_journal" not in receipt


def test_ambiguous_lost_ack_recovery_fails_closed(tmp_path: Path) -> None:
    snapshot = _snapshot(1605)
    _admitted_store(tmp_path / "store", snapshot)
    guard = ProspectiveExecutionGuard(store_root=tmp_path / "store", snapshot=snapshot)
    operation_root = tmp_path / "ops"
    cwd = guard.shadow_source("c")
    cwd.mkdir(parents=True)
    for op_id in ("agyop_one", "agyop_two"):
        op = operation_root / "operations" / op_id
        op.mkdir(parents=True)
        (op / "operation.json").write_text(
            json.dumps({
                "operation_id": op_id,
                "provider": "agy",
                "model": "gemini-3.8-flash-medium",
                "prompt_sha256": "2" * 64,
                "cwd": str(cwd.resolve()),
            }),
            encoding="utf-8",
        )

    with pytest.raises(ValueError, match="ambiguous_provider_operation_recovery"):
        guard.recover_provider_operation(
            slot="c",
            operation_root=operation_root,
            prompt_sha256="2" * 64,
            cwd=cwd,
            model="gemini-3.8-flash-medium",
            mode="accept-edits",
        )


def test_synchronous_provider_start_is_fenced_before_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot(1606)
    _, receipt = _admitted_store(tmp_path, snapshot)
    _bind_github(monkeypatch, snapshot=snapshot, receipt=receipt)
    guard = ProspectiveExecutionGuard(store_root=tmp_path, snapshot=snapshot)

    started = guard.ensure_synchronous_effect_start(
        slot="jev",
        effect_identity_sha256="3" * 64,
        provider="typesafe",
        model="jev-latest",
    )

    assert started["effect_identity_sha256"] == "3" * 64
    assert started["provider"] == "typesafe"
    assert (guard.effect_root("jev") / "synchronous_effect_start.json").is_file()


def test_synchronous_effect_restart_never_replays_unreconcilable_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot(1607)
    _, receipt = _admitted_store(tmp_path, snapshot)
    _bind_github(monkeypatch, snapshot=snapshot, receipt=receipt)
    guard = ProspectiveExecutionGuard(store_root=tmp_path, snapshot=snapshot)
    guard.ensure_synchronous_effect_start(
        slot="jev",
        effect_identity_sha256="4" * 64,
        provider="typesafe",
        model="jev-latest",
    )

    with pytest.raises(
        ProspectiveProtocolLoss,
        match="UNRECONCILABLE_SYNCHRONOUS_EFFECT_RESTART",
    ):
        guard.ensure_synchronous_effect_start(
            slot="jev",
            effect_identity_sha256="4" * 64,
            provider="typesafe",
            model="jev-latest",
        )

    loss = json.loads(guard.protocol_loss_path.read_text(encoding="utf-8"))
    assert loss["reason"] == "UNRECONCILABLE_SYNCHRONOUS_EFFECT_RESTART"
