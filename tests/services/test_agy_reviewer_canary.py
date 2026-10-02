"""Contract tests for durable interrupted-resume Agy reviewer canaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.services.agy_reviewer_canary import (
    AgyReviewCanaryError,
    canary_id_for_effect,
    create_canary,
    load_canary,
    load_canary_receipt,
    observe_canary,
)

EFFECT = "a" * 64
OPERATION_ID = "agyop_" + ("a" * 32)
RUNTIME = "b" * 40
CLI_SHA = "c" * 64


def _start_result() -> dict:
    return {
        "action": "DISPATCHED",
        "operation": {
            "operation_id": OPERATION_ID,
            "attempt_id": "attempt_" + ("d" * 32),
            "pid": 4242,
            "model": "claude-sonnet-4-6",
            "review_effect_id": EFFECT,
            "review_launch_profile_id": "claude-sonnet-4-6.packet-review.v1",
        },
    }


def _create(tmp_path: Path) -> tuple[Path, Path, Path, dict]:
    canary_root = tmp_path / "canaries"
    operation_root = tmp_path / "operations-root"
    lease_root = tmp_path / "leases"
    state = create_canary(
        start_result=_start_result(),
        canary_root=canary_root,
        operation_root=operation_root,
        lease_root=lease_root,
        expected_runtime_revision=RUNTIME,
        review_cli_sha256=CLI_SHA,
    )
    return canary_root, operation_root, lease_root, state


def _operation(
    operation_root: Path,
    *,
    operation_id: str = OPERATION_ID,
    effect_id: str = EFFECT,
    runtime_revision: str = RUNTIME,
) -> dict:
    row = {
        "operation_id": operation_id,
        "review_effect_id": effect_id,
        "status": "COMPLETED",
        "runtime_revision": runtime_revision,
        "provider_session_id": "session-1",
        "account_alias_hash": "accthash",
        "lease_id_hash": "leasehash",
    }
    target = operation_root / "operations" / operation_id / "operation.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return row


def _completed_status(operation_root: Path, **overrides) -> dict:
    operation = _operation(operation_root)
    operation.update(overrides)
    return {
        "action": "STATUS",
        "operation": operation,
        "receipt": {
            "review_effect_id": EFFECT,
            "review_applicable": True,
            "subject_stable": True,
            "receipt_sha256": "e" * 64,
            "verdict": "ACCEPT",
        },
    }


def test_canary_state_is_durable_and_hash_bound(tmp_path: Path) -> None:
    canary_root, _, _, state = _create(tmp_path)
    canary_id = canary_id_for_effect(EFFECT)

    loaded = load_canary(canary_id, canary_root=canary_root)

    assert loaded["state_sha256"] == state["state_sha256"]
    assert loaded["phase"] == "INTERRUPTIBLE"
    assert loaded["review_effect_id"] == EFFECT
    assert loaded["operation_id"] == OPERATION_ID
    assert loaded["expected_runtime_revision"] == RUNTIME
    assert loaded["review_cli_sha256"] == CLI_SHA


def test_active_resume_waits_without_new_effect(tmp_path: Path) -> None:
    canary_root, _, _, _ = _create(tmp_path)
    result = observe_canary(
        canary_id=canary_id_for_effect(EFFECT),
        canary_root=canary_root,
        review_status={
            "action": "STATUS",
            "operation": {
                "operation_id": OPERATION_ID,
                "review_effect_id": EFFECT,
                "status": "RUNNING",
            },
            "receipt": None,
        },
        current_review_cli_sha256=CLI_SHA,
    )

    assert result["action"] == "WAIT"
    assert result["receipt"] is None
    assert result["state"]["phase"] == "WAITING"
    assert result["state"]["resume_observations"] == 1


def test_outcome_unknown_requires_reconciliation_not_retry(tmp_path: Path) -> None:
    canary_root, _, _, _ = _create(tmp_path)
    result = observe_canary(
        canary_id=canary_id_for_effect(EFFECT),
        canary_root=canary_root,
        review_status={
            "action": "STATUS",
            "operation": {
                "operation_id": OPERATION_ID,
                "review_effect_id": EFFECT,
                "status": "OUTCOME_UNKNOWN",
            },
            "receipt": None,
        },
        current_review_cli_sha256=CLI_SHA,
    )

    assert result["action"] == "RECONCILE"
    assert result["state"]["phase"] == "RECONCILE_REQUIRED"


def test_terminal_canary_requires_one_semantic_operation_and_clean_lease(
    tmp_path: Path,
) -> None:
    canary_root, operation_root, lease_root, _ = _create(tmp_path)
    status = _completed_status(operation_root)

    result = observe_canary(
        canary_id=canary_id_for_effect(EFFECT),
        canary_root=canary_root,
        review_status=status,
        current_review_cli_sha256=CLI_SHA,
    )

    assert result["action"] == "PASSED"
    assert result["receipt"]["semantic_operation_count"] == 1
    assert result["receipt"]["subject_stable"] is True
    assert result["receipt"]["review_applicable"] is True
    assert result["receipt"]["lease_cleanup"]["lease_receipt_absent"] is True
    loaded = load_canary_receipt(
        canary_id_for_effect(EFFECT),
        canary_root=canary_root,
    )
    assert loaded["receipt_sha256"] == result["receipt"]["receipt_sha256"]


def test_duplicate_semantic_operation_fails_canary(tmp_path: Path) -> None:
    canary_root, operation_root, _, _ = _create(tmp_path)
    status = _completed_status(operation_root)
    duplicate = operation_root / "operations" / "agyop_duplicate" / "operation.json"
    duplicate.parent.mkdir(parents=True)
    duplicate.write_text(
        json.dumps({
            "operation_id": "agyop_duplicate",
            "review_effect_id": EFFECT,
            "status": "COMPLETED",
        })
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        AgyReviewCanaryError,
        match="CANARY_SEMANTIC_OPERATION_COUNT_INVALID:2",
    ):
        observe_canary(
            canary_id=canary_id_for_effect(EFFECT),
            canary_root=canary_root,
            review_status=status,
            current_review_cli_sha256=CLI_SHA,
        )


def test_runtime_or_cli_drift_fails_closed(tmp_path: Path) -> None:
    canary_root, operation_root, _, _ = _create(tmp_path)
    status = _completed_status(operation_root)

    with pytest.raises(AgyReviewCanaryError, match="CANARY_REVIEW_CLI_DRIFT"):
        observe_canary(
            canary_id=canary_id_for_effect(EFFECT),
            canary_root=canary_root,
            review_status=status,
            current_review_cli_sha256="f" * 64,
        )

    status["operation"]["runtime_revision"] = "9" * 40
    with pytest.raises(AgyReviewCanaryError, match="CANARY_RUNTIME_REVISION_MISMATCH"):
        observe_canary(
            canary_id=canary_id_for_effect(EFFECT),
            canary_root=canary_root,
            review_status=status,
            current_review_cli_sha256=CLI_SHA,
        )


def test_stale_review_receipt_cannot_pass_canary(tmp_path: Path) -> None:
    canary_root, operation_root, _, _ = _create(tmp_path)
    status = _completed_status(operation_root)
    status["receipt"]["review_applicable"] = False

    with pytest.raises(AgyReviewCanaryError, match="CANARY_REVIEW_NOT_APPLICABLE"):
        observe_canary(
            canary_id=canary_id_for_effect(EFFECT),
            canary_root=canary_root,
            review_status=status,
            current_review_cli_sha256=CLI_SHA,
        )


def test_tampered_state_is_rejected(tmp_path: Path) -> None:
    canary_root, _, _, state = _create(tmp_path)
    path = canary_root / f"{state['canary_id']}.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["phase"] = "PASSED"
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    with pytest.raises(AgyReviewCanaryError, match="CANARY_STATE_HASH_MISMATCH"):
        load_canary(state["canary_id"], canary_root=canary_root)
