from __future__ import annotations

from pathlib import Path

import pytest

from nexus.research.hybrid_replication_pipeline import (
    AdmissionReceipt,
    AutomaticReplicationStore,
    TaskSnapshot,
    build_admission_comment,
    build_capture_comment,
)
from scripts.ops import hybrid_replication_daemon as daemon
from scripts.ops import hybrid_replication_watcher as watcher


def _snapshot(issue: int = 1700) -> TaskSnapshot:
    return TaskSnapshot.create(
        repository="James3014/Nexus-new",
        issue_number=issue,
        created_at="2026-10-07T12:00:00Z",
        captured_at="2026-10-07T12:00:01Z",
        issue_updated_at="2026-10-07T12:00:00Z",
        title="Watcher control",
        body="Implement a bounded control.",
        pre_implementation_revision="a" * 40,
        default_branch="main",
        source_event_id=f"control:{issue}",
    )


def _receipt(snapshot: TaskSnapshot) -> AdmissionReceipt:
    return AdmissionReceipt.create(
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


def test_fast_ingest_applies_capture_and_admission_in_same_poll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot()
    receipt = _receipt(snapshot)
    monkeypatch.setattr(
        watcher,
        "_issues_updated_since",
        lambda repository, **_: (
            [{"number": snapshot.issue_number, "created_at": snapshot.created_at}]
            if repository == snapshot.repository
            else []
        ),
    )
    monkeypatch.setattr(
        daemon,
        "_comments",
        lambda repository, number: [
            {"body": build_capture_comment(snapshot)},
            {"body": build_admission_comment(receipt)},
        ],
    )

    store = AutomaticReplicationStore(tmp_path)
    report = watcher.fast_ingest(
        store=store,
        boundary="2026-10-07T11:59:59Z",
        updated_since="2026-10-07T11:59:59Z",
    )

    assert report["rows"] == [
        {"task_key": snapshot.task_key, "capture": "PRESENT", "admission": "PRESENT"}
    ]
    state = store.load_task(snapshot.task_key)
    assert state is not None
    assert state["phase"] == "ADMITTED"
    assert state["admission_receipt_sha256"] == receipt.receipt_sha256


def test_fast_ingest_rechecks_pending_admission_without_waiting_for_issue_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot(1701)
    receipt = _receipt(snapshot)
    store = AutomaticReplicationStore(tmp_path)
    store.capture(snapshot, admission_disposition="PRE_AUTOMATION_PROVISIONAL_CAPTURE")
    monkeypatch.setattr(watcher, "_issues_updated_since", lambda *_, **__: [])
    monkeypatch.setattr(
        daemon,
        "_gh_json",
        lambda *args: {"number": snapshot.issue_number, "created_at": snapshot.created_at},
    )
    monkeypatch.setattr(
        daemon,
        "_comments",
        lambda repository, number: [
            {"body": build_capture_comment(snapshot)},
            {"body": build_admission_comment(receipt)},
        ],
    )

    watcher.fast_ingest(
        store=store,
        boundary="2026-10-07T11:59:59Z",
        updated_since="2026-10-07T12:00:10Z",
    )

    assert store.load_task(snapshot.task_key)["phase"] == "ADMITTED"


def test_ready_task_selection_skips_protocol_loss(tmp_path: Path) -> None:
    store = AutomaticReplicationStore(tmp_path)
    first = _snapshot(1702)
    second = _snapshot(1703)
    for snapshot in (first, second):
        store.capture(snapshot, admission_disposition="PRE_AUTOMATION_PROVISIONAL_CAPTURE")
        store.apply_admission(_receipt(snapshot))
    second_dir = tmp_path / "tasks" / "James3014__Nexus-new--1703"
    (second_dir / "prospective_protocol_loss.json").write_text("{}\n", encoding="utf-8")

    assert watcher._task_keys_ready_for_advance(
        store=store,
        readiness_control_task_key=None,
    ) == [first.task_key]


def test_watcher_requires_prospective_store_binding(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="prospective_stack_command_requires_store_root"):
        watcher.run_watcher(
            root=tmp_path,
            boundary="2026-10-07T12:00:00Z",
            frozen_policy_sha256="5" * 64,
            stack_command="python stack.py",
            ground_truth_command="python gt.py",
            max_loops=1,
        )


def test_fast_ingest_rechecks_pending_missing_capture_each_poll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot = _snapshot(1704)
    receipt = _receipt(snapshot)
    monkeypatch.setattr(watcher, "_issues_updated_since", lambda *_, **__: [])
    monkeypatch.setattr(
        daemon,
        "_gh_json",
        lambda *args: {"number": snapshot.issue_number, "created_at": snapshot.created_at},
    )
    monkeypatch.setattr(
        daemon,
        "_comments",
        lambda repository, number: [
            {"body": build_capture_comment(snapshot)},
            {"body": build_admission_comment(receipt)},
        ],
    )
    store = AutomaticReplicationStore(tmp_path)

    report = watcher.fast_ingest(
        store=store,
        boundary="2026-10-07T11:59:59Z",
        updated_since="2026-10-07T12:01:00Z",
        pending_capture={snapshot.task_key},
    )

    assert report["rows"][0]["capture"] == "PRESENT"
    assert store.load_task(snapshot.task_key)["phase"] == "ADMITTED"
