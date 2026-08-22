from __future__ import annotations

import json
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import nexus.orchestrator.standing_grant_store as standing_grant_store
from nexus.contracts.autonomy_goal import AutonomyActionClass, RepositoryIdentity, StandingGrantContext
from nexus.orchestrator.autonomy_policy import StandingGrantOutcome
from nexus.orchestrator.standing_grant_store import (
    StandingGrantReceipt,
    StandingGrantReceiptError,
    _load_receipt_at,
    _write_standing_grant_receipt_at,
    evaluate_durable_standing_grant,
    evaluate_rehydrated_durable_standing_grant,
    inspect_standing_grant_receipt,
    load_standing_grant_receipt,
    rehydrate_durable_standing_grant_request,
)
from scripts.ops import standing_grant as standing_grant_cli

NOW = datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc)


def _repository() -> RepositoryIdentity:
    return RepositoryIdentity(
        repository_id="James3014/Nexus-new",
        canonical_remote="https://github.com/James3014/Nexus-new.git",
    )


def _receipt(path: Path, **overrides) -> StandingGrantReceipt:
    values = {
        "owner_id": "James3014",
        "coordinator_id": "primary-codex-coordinator",
        "repository": _repository(),
        "thread_id": "durable-coordination-scope",
        "goal_id": "goal-all-issues",
        "allowed_actions": tuple(
            sorted(
                (
                    AutonomyActionClass.TASK_SUBMIT,
                    AutonomyActionClass.TASK_RETRY,
                    AutonomyActionClass.REPOSITORY_PUSH,
                ),
                key=lambda action: action.value,
            )
        ),
        "issued_at": NOW - timedelta(hours=1),
        "expires_at": NOW + timedelta(days=1),
    }
    values.update(overrides)
    context = StandingGrantContext.issue(**values)
    receipt = StandingGrantReceipt.issue(grant_id="grant-515", context=context)
    _write_standing_grant_receipt_at(receipt, path)
    return receipt


def _bind_default(monkeypatch, tmp_path: Path) -> tuple[Path, StandingGrantReceipt]:
    path = tmp_path / "authority" / "standing-grant.json"
    receipt = _receipt(path)
    monkeypatch.setattr(standing_grant_store, "DEFAULT_RECEIPT_PATH", path)
    return path, receipt


def test_strict_evaluator_still_rejects_ephemeral_thread_substitution(monkeypatch, tmp_path):
    _path, receipt = _bind_default(monkeypatch, tmp_path)

    decision = evaluate_durable_standing_grant(
        requested_owner_id=receipt.context.owner_id,
        requested_coordinator_id=receipt.context.coordinator_id,
        repository=receipt.context.repository,
        thread_id="new-chat-session-uuid",
        goal_id=receipt.context.goal_id,
        action=AutonomyActionClass.TASK_SUBMIT,
        requested_at=NOW,
    )

    assert decision.outcome is StandingGrantOutcome.OUT_OF_SCOPE


def test_rehydration_uses_durable_coordination_scope_not_ephemeral_session(monkeypatch, tmp_path):
    _path, receipt = _bind_default(monkeypatch, tmp_path)

    loaded, request = rehydrate_durable_standing_grant_request(
        requested_owner_id="James3014",
        requested_coordinator_id="primary-codex-coordinator",
        repository=_repository(),
        goal_id="goal-all-issues",
        action=AutonomyActionClass.TASK_SUBMIT,
        requested_at=NOW,
    )

    assert loaded.receipt_hash == receipt.receipt_hash
    assert request.thread_id == "durable-coordination-scope"
    assert request.thread_id != "new-chat-session-uuid"
    assert (
        evaluate_rehydrated_durable_standing_grant(
            requested_owner_id="James3014",
            requested_coordinator_id="primary-codex-coordinator",
            repository=_repository(),
            goal_id="goal-all-issues",
            action=AutonomyActionClass.TASK_SUBMIT,
            requested_at=NOW,
        ).outcome
        is StandingGrantOutcome.GRANT_MATCH
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("requested_owner_id", "other-owner"),
        ("requested_coordinator_id", "other-coordinator"),
        ("goal_id", "other-goal"),
    ],
)
def test_rehydration_does_not_widen_other_identity_dimensions(monkeypatch, tmp_path, field, value):
    _bind_default(monkeypatch, tmp_path)
    kwargs = {
        "requested_owner_id": "James3014",
        "requested_coordinator_id": "primary-codex-coordinator",
        "repository": _repository(),
        "goal_id": "goal-all-issues",
        "action": AutonomyActionClass.TASK_SUBMIT,
        "requested_at": NOW,
    }
    kwargs[field] = value

    assert evaluate_rehydrated_durable_standing_grant(**kwargs).outcome is StandingGrantOutcome.OUT_OF_SCOPE


def test_rehydration_rejects_wrong_repository_and_ungranted_action(monkeypatch, tmp_path):
    _bind_default(monkeypatch, tmp_path)
    wrong_repo = RepositoryIdentity(
        repository_id="James3014/Other",
        canonical_remote="https://github.com/James3014/Other.git",
    )
    assert (
        evaluate_rehydrated_durable_standing_grant(
            requested_owner_id="James3014",
            requested_coordinator_id="primary-codex-coordinator",
            repository=wrong_repo,
            goal_id="goal-all-issues",
            action=AutonomyActionClass.TASK_SUBMIT,
            requested_at=NOW,
        ).outcome
        is StandingGrantOutcome.OUT_OF_SCOPE
    )
    assert (
        evaluate_rehydrated_durable_standing_grant(
            requested_owner_id="James3014",
            requested_coordinator_id="primary-codex-coordinator",
            repository=_repository(),
            goal_id="goal-all-issues",
            action=AutonomyActionClass.PRODUCTION_RELEASE,
            requested_at=NOW,
        ).outcome
        is StandingGrantOutcome.OUT_OF_SCOPE
    )


def test_inspection_distinguishes_missing_valid_expired_revoked_and_invalid(monkeypatch, tmp_path):
    missing = tmp_path / "missing" / "standing-grant.json"
    monkeypatch.setattr(standing_grant_store, "DEFAULT_RECEIPT_PATH", missing)
    assert inspect_standing_grant_receipt(now=NOW)["status"] == "MISSING"

    valid = tmp_path / "valid" / "standing-grant.json"
    _receipt(valid)
    monkeypatch.setattr(standing_grant_store, "DEFAULT_RECEIPT_PATH", valid)
    result = inspect_standing_grant_receipt(now=NOW)
    assert result["status"] == "VALID"
    assert result["coordination_scope_id"] == "durable-coordination-scope"

    expired = tmp_path / "expired" / "standing-grant.json"
    _receipt(expired, expires_at=NOW - timedelta(minutes=1))
    monkeypatch.setattr(standing_grant_store, "DEFAULT_RECEIPT_PATH", expired)
    assert inspect_standing_grant_receipt(now=NOW)["status"] == "EXPIRED"

    revoked = tmp_path / "revoked" / "standing-grant.json"
    _receipt(
        revoked,
        revoked_at=NOW - timedelta(minutes=1),
        revocation_reason="owner-revoked",
    )
    monkeypatch.setattr(standing_grant_store, "DEFAULT_RECEIPT_PATH", revoked)
    assert inspect_standing_grant_receipt(now=NOW)["status"] == "REVOKED"

    invalid = tmp_path / "invalid" / "standing-grant.json"
    _receipt(invalid)
    invalid.chmod(0o644)
    monkeypatch.setattr(standing_grant_store, "DEFAULT_RECEIPT_PATH", invalid)
    assert inspect_standing_grant_receipt(now=NOW)["status"] == "INVALID"


def test_cli_inspect_is_non_mutating(monkeypatch, tmp_path, capsys):
    path, _receipt_value = _bind_default(monkeypatch, tmp_path)
    before = path.read_bytes()

    assert standing_grant_cli.main(["inspect", "--requested-at", NOW.isoformat()]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "VALID"
    assert result["coordination_scope_id"] == "durable-coordination-scope"
    assert path.read_bytes() == before


def test_cli_issue_renew_revoke_preserves_scope_and_actions(monkeypatch, tmp_path, capsys):
    path = tmp_path / "operator" / "standing-grant.json"
    monkeypatch.setattr(standing_grant_store, "DEFAULT_RECEIPT_PATH", path)

    assert standing_grant_cli.main(
        [
            "issue",
            "--grant-id",
            "grant-issue",
            "--owner-id",
            "James3014",
            "--coordinator-id",
            "primary-codex-coordinator",
            "--repository-id",
            "James3014/Nexus-new",
            "--canonical-remote",
            "https://github.com/James3014/Nexus-new.git",
            "--coordination-scope-id",
            "durable-coordination-scope",
            "--goal-id",
            "goal-all-issues",
            "--action",
            "TASK_SUBMIT",
            "--action",
            "REPOSITORY_PUSH",
            "--issued-at",
            (NOW - timedelta(minutes=5)).isoformat(),
            "--expires-at",
            (NOW + timedelta(hours=1)).isoformat(),
        ]
    ) == 0
    capsys.readouterr()
    issued = load_standing_grant_receipt(now=NOW)
    assert issued is not None
    assert tuple(action.value for action in issued.context.allowed_actions) == (
        "REPOSITORY_PUSH",
        "TASK_SUBMIT",
    )
    issued_hash = issued.receipt_hash

    assert standing_grant_cli.main(
        [
            "renew",
            "--grant-id",
            "grant-renew",
            "--requested-at",
            NOW.isoformat(),
            "--issued-at",
            NOW.isoformat(),
            "--expires-at",
            (NOW + timedelta(hours=2)).isoformat(),
        ]
    ) == 0
    capsys.readouterr()
    renewed = load_standing_grant_receipt(now=NOW + timedelta(minutes=1))
    assert renewed is not None
    assert renewed.supersedes_grant_hash == issued_hash
    assert renewed.context.owner_id == issued.context.owner_id
    assert renewed.context.coordinator_id == issued.context.coordinator_id
    assert renewed.context.repository == issued.context.repository
    assert renewed.context.thread_id == issued.context.thread_id
    assert renewed.context.goal_id == issued.context.goal_id
    assert renewed.context.allowed_actions == issued.context.allowed_actions
    renewed_hash = renewed.receipt_hash

    assert standing_grant_cli.main(
        [
            "revoke",
            "--grant-id",
            "grant-revoke",
            "--requested-at",
            (NOW + timedelta(minutes=1)).isoformat(),
            "--revoked-at",
            (NOW + timedelta(minutes=1)).isoformat(),
            "--reason",
            "owner-request",
        ]
    ) == 0
    capsys.readouterr()
    inspection = inspect_standing_grant_receipt(now=NOW + timedelta(minutes=2))
    assert inspection["status"] == "REVOKED"
    assert inspection["allowed_actions"] == ["REPOSITORY_PUSH", "TASK_SUBMIT"]
    with pytest.raises(StandingGrantReceiptError, match="REVOKED"):
        load_standing_grant_receipt(now=NOW + timedelta(minutes=2))

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["supersedes_grant_hash"] == renewed_hash


def test_structural_loader_keeps_revocation_and_expiry_out_of_authorization(monkeypatch, tmp_path):
    path = tmp_path / "revoked" / "standing-grant.json"
    _receipt(
        path,
        revoked_at=NOW - timedelta(minutes=1),
        revocation_reason="owner-revoked",
    )
    monkeypatch.setattr(standing_grant_store, "DEFAULT_RECEIPT_PATH", path)
    assert inspect_standing_grant_receipt(now=NOW)["status"] == "REVOKED"
    with pytest.raises(StandingGrantReceiptError, match="REVOKED"):
        _load_receipt_at(path, now=NOW)


def test_receipt_file_mode_remains_restrictive(tmp_path):
    path = tmp_path / "authority" / "standing-grant.json"
    _receipt(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
