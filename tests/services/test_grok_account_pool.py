from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.services.external_account_pool import AccountFailureKind
from nexus.services.grok_account_pool import (
    GrokAccountPoolError,
    GrokAccountPoolExhaustedError,
    GrokAccountPoolManager,
    classify_grok_failure,
)


def _state(root: Path, homes: list[Path]) -> None:
    root.mkdir(parents=True)
    accounts = {}
    for index, home in enumerate(homes):
        home.mkdir()
        accounts[f"acct-{index}"] = {
            "home_path": str(home),
            "enabled": True,
            "cooldown_until": 0.0,
            "last_failure_reason": "",
            "last_failure_timestamp": 0.0,
        }
    (root / "state.json").write_text(
        json.dumps({"accounts": accounts, "active_alias": "acct-0", "updated_at": 0.0}),
        encoding="utf-8",
    )


def test_existing_state_schema_is_upgraded_with_cross_process_lease(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    _state(root, [tmp_path / "a", tmp_path / "b"])
    manager = GrokAccountPoolManager(root)

    lease = manager.acquire("grokop_" + "a" * 32)

    data = json.loads((root / "state.json").read_text())
    assert len(data["leases"]) == 1
    assert lease.lease_id in data["leases"]
    assert lease.account_alias_hash not in {"acct-0", "acct-1"}
    assert "acct-" not in lease.execution_env["HOME"]
    assert Path(lease.execution_env["HOME"]).is_symlink()
    manager.release(lease)


def test_two_live_leases_get_distinct_profiles(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    _state(root, [tmp_path / "a", tmp_path / "b"])
    manager = GrokAccountPoolManager(root)

    first = manager.acquire("one")
    second = manager.acquire("two")

    assert first.lease_id != second.lease_id
    assert first.account_alias_hash != second.account_alias_hash
    assert first.execution_env["HOME"] != second.execution_env["HOME"]
    manager.release(first)
    manager.release(second)


def test_rotation_cools_failed_profile_and_returns_replacement(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    _state(root, [tmp_path / "a", tmp_path / "b"])
    manager = GrokAccountPoolManager(root, cooldown_seconds=60)
    first = manager.acquire("one")

    replacement = manager.report_failure(first, AccountFailureKind.AUTH_OR_SESSION_INVALID)

    assert replacement is not None
    assert replacement.account_alias_hash != first.account_alias_hash
    state = json.loads((root / "state.json").read_text())
    failed = [v for v in state["accounts"].values() if v["last_failure_reason"]]
    assert len(failed) == 1
    assert failed[0]["last_failure_reason"] == "AUTH_OR_SESSION_INVALID"
    manager.release(replacement)


def test_noneligible_failure_never_rotates(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    _state(root, [tmp_path / "a", tmp_path / "b"])
    manager = GrokAccountPoolManager(root)
    lease = manager.acquire("one")

    assert manager.report_failure(lease, AccountFailureKind.TIMEOUT) is None
    manager.release(lease)


def test_pool_exhaustion_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    _state(root, [tmp_path / "a"])
    manager = GrokAccountPoolManager(root)
    lease = manager.acquire("one")
    with pytest.raises(GrokAccountPoolExhaustedError):
        manager.acquire("two")
    manager.release(lease)


def test_replayed_lease_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    _state(root, [tmp_path / "a"])
    manager = GrokAccountPoolManager(root)
    lease = manager.acquire("one")
    manager.release(lease)

    with pytest.raises(GrokAccountPoolError, match="GROK_INVALID_ACCOUNT_LEASE"):
        manager.release(lease)


def test_lease_environment_does_not_inherit_secret_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "pool"
    _state(root, [tmp_path / "a"])
    monkeypatch.setenv("GROK_API_KEY", "secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "other-secret")
    manager = GrokAccountPoolManager(root)
    lease = manager.acquire("one")

    assert "GROK_API_KEY" not in lease.execution_env
    assert "AWS_SECRET_ACCESS_KEY" not in lease.execution_env
    assert "secret" not in json.dumps(dict(lease.execution_env))
    manager.release(lease)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("You are not authenticated.", AccountFailureKind.AUTH_OR_SESSION_INVALID),
        ("429 rate limit", AccountFailureKind.RATE_LIMITED),
        ("quota exhausted", AccountFailureKind.QUOTA_EXHAUSTED),
        ("service unavailable 503", AccountFailureKind.ACCOUNT_UNAVAILABLE),
        ("permission denied", AccountFailureKind.PERMISSION_OR_SCOPE_ERROR),
        ("unknown provider output", AccountFailureKind.UNKNOWN),
    ],
)
def test_failure_classifier(text: str, expected: AccountFailureKind) -> None:
    assert classify_grok_failure(text) is expected


def test_timeout_precedes_quota_for_no_blind_retry() -> None:
    assert classify_grok_failure("quota exhausted", timed_out=True) is AccountFailureKind.TIMEOUT
