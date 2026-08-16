"""Hostile tests for the Grok account pool provider binding."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.services.external_account_pool import (
    AccountFailureKind,
    ExternalAccountPoolExhaustedError,
)
from nexus.services.grok_account_pool import (
    GrokAccount,
    GrokAccountPoolError,
    GrokAccountPoolExhaustedError,
    GrokAccountPoolManager,
    build_grok_isolated_env,
    get_grok_account_pool_manager,
    set_grok_account_pool_manager,
)


def _make_manager(tmp_path) -> GrokAccountPoolManager:
    h1 = str(tmp_path / "grok-a")
    h2 = str(tmp_path / "grok-b")
    h3 = str(tmp_path / "grok-c")
    for p in (h1, h2, h3):
        Path(p).mkdir(parents=True)
    return GrokAccountPoolManager([
        GrokAccount(alias="grok-a", home_dir=h1),
        GrokAccount(alias="grok-b", home_dir=h2),
        GrokAccount(alias="grok-c", home_dir=h3),
    ])


def test_grok_account_alias_hash_is_non_secret_slug():
    account = GrokAccount(alias="profile-1", home_dir="/tmp/grok-profile-1")
    assert len(account.alias_hash) == 12
    assert account.alias_hash != account.alias
    assert account.alias_hash.isalnum()


def test_build_grok_isolated_env_removes_sensitive_keys(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "secret_xai")
    monkeypatch.setenv("GROK_API_KEY", "secret_grok")
    monkeypatch.setenv("NEXUS_GROK_API_KEY", "secret_nexus_grok")
    monkeypatch.setenv("HOME", "/original")

    isolated = build_grok_isolated_env(home_dir="/profiles/grok-a")

    assert isolated["HOME"] == "/profiles/grok-a"
    assert "XAI_API_KEY" not in isolated
    assert "GROK_API_KEY" not in isolated
    assert "NEXUS_GROK_API_KEY" not in isolated


def test_acquire_binds_immutable_lease_and_env(tmp_path):
    manager = _make_manager(tmp_path)
    lease = manager.acquire("consumer-1")
    assert lease.provider == "grok"
    assert lease.consumer_id == "consumer-1"
    assert len(lease.account_alias_hash) == 12
    # Lease must carry the exact profile binding, not a global active state.
    assert lease.execution_env["HOME"] == str(tmp_path / "grok-a")


def test_concurrent_consumers_are_isolated(tmp_path):
    manager = _make_manager(tmp_path)
    lease_a = manager.acquire("consumer-A")
    lease_b = manager.acquire("consumer-B")

    assert lease_a.lease_id != lease_b.lease_id
    assert lease_a.account_alias_hash == manager._accounts[0].alias_hash
    assert lease_b.account_alias_hash == manager._accounts[1].alias_hash
    assert lease_a.execution_env["HOME"] == str(tmp_path / "grok-a")
    assert lease_b.execution_env["HOME"] == str(tmp_path / "grok-b")


def test_eligible_failure_failover_does_not_change_other_lease(tmp_path):
    manager = _make_manager(tmp_path)
    lease_a = manager.acquire("consumer-A")
    lease_b = manager.acquire("consumer-B")
    b_hash_before = lease_b.account_alias_hash
    b_env_before = dict(lease_b.execution_env)

    replacement_a = manager.report_failure(
        lease_a,
        AccountFailureKind.QUOTA_EXHAUSTED,
    )

    assert replacement_a is not None
    assert replacement_a.account_alias_hash == manager._accounts[2].alias_hash
    assert replacement_a.execution_env["HOME"] == str(tmp_path / "grok-c")
    assert replacement_a.lease_id != lease_b.lease_id
    # Exact failed identity is marked unavailable and does not affect B.
    assert manager._accounts[0].is_active is False
    assert manager._accounts[1].is_active is True
    assert lease_b.account_alias_hash == b_hash_before
    assert dict(lease_b.execution_env) == b_env_before
    assert lease_b.lease_id in manager._pool._active_leases


def test_release_only_affects_supplied_lease(tmp_path):
    manager = _make_manager(tmp_path)
    lease_a = manager.acquire("consumer-A")
    lease_b = manager.acquire("consumer-B")
    b_hash_before = lease_b.account_alias_hash

    manager.release(lease_a)

    assert lease_a.lease_id not in manager._pool._active_leases
    assert lease_b.lease_id in manager._pool._active_leases
    assert lease_b.account_alias_hash == b_hash_before
    manager.release(lease_b)


def test_rotating_a_leaves_b_binding_unchanged(tmp_path):
    manager = _make_manager(tmp_path)
    lease_a = manager.acquire("consumer-A")
    lease_b = manager.acquire("consumer-B")
    b_hash_before = lease_b.account_alias_hash

    replacement_a = manager.report_failure(
        lease_a,
        AccountFailureKind.AUTH_OR_SESSION_INVALID,
    )

    assert replacement_a is not None
    assert replacement_a.account_alias_hash != lease_a.account_alias_hash
    assert lease_b.account_alias_hash == b_hash_before


def test_non_eligible_failure_does_not_rotate(tmp_path):
    manager = _make_manager(tmp_path)
    lease = manager.acquire("consumer-A")
    original_hash = lease.account_alias_hash

    for kind in (
        AccountFailureKind.MODEL_OR_TASK_ERROR,
        AccountFailureKind.SYNTAX_OR_IMPLEMENTATION_ERROR,
        AccountFailureKind.VERIFIER_FAILED,
        AccountFailureKind.CANCELLED,
        AccountFailureKind.TIMEOUT,
        AccountFailureKind.PERMISSION_OR_SCOPE_ERROR,
        AccountFailureKind.UNKNOWN,
    ):
        result = manager.report_failure(lease, kind)
        assert result is None
        assert manager._accounts[0].is_active is True
    assert lease.account_alias_hash == original_hash
    assert lease.lease_id in manager._pool._active_leases


def test_exact_failed_identity_is_marked_unavailable(tmp_path):
    manager = _make_manager(tmp_path)
    lease_a = manager.acquire("consumer-A")
    lease_b = manager.acquire("consumer-B")

    replacement_a = manager.report_failure(
        lease_a,
        AccountFailureKind.TOKEN_EXPIRED,
    )

    assert replacement_a is not None
    assert manager._accounts[0].is_active is False
    assert manager._accounts[1].is_active is True
    assert manager._accounts[2].is_active is True
    assert lease_b.account_alias_hash == manager._accounts[1].alias_hash


def test_unrelated_profile_unaffected_by_rotation(tmp_path):
    manager = _make_manager(tmp_path)
    lease_a = manager.acquire("consumer-A")
    unrelated = GrokAccount(alias="unrelated", home_dir=str(tmp_path / "unrelated"))
    manager._accounts.append(unrelated)

    replacement_a = manager.report_failure(
        lease_a,
        AccountFailureKind.ACCOUNT_UNAVAILABLE,
    )

    assert replacement_a is not None
    assert unrelated.is_active is True


def test_pool_exhaustion_fails_closed():
    manager = GrokAccountPoolManager([])
    with pytest.raises(
        ExternalAccountPoolExhaustedError, match="EXTERNAL_ACCOUNT_POOL_EXHAUSTED:grok"
    ):
        manager.acquire("consumer-1")


def test_remaining_exhaustion_raises_typed_grok_error(tmp_path):
    h1 = str(tmp_path / "grok-a")
    h2 = str(tmp_path / "grok-b")
    for p in (h1, h2):
        Path(p).mkdir(parents=True)
    manager = GrokAccountPoolManager([
        GrokAccount(alias="grok-a", home_dir=h1),
        GrokAccount(alias="grok-b", home_dir=h2),
    ])
    lease_a = manager.acquire("consumer-A")
    lease_b = manager.acquire("consumer-B")

    # A fails -> rotates onto B (the only remaining healthy profile).
    replacement_a = manager.report_failure(lease_a, AccountFailureKind.QUOTA_EXHAUSTED)
    assert replacement_a is not None
    assert replacement_a.account_alias_hash == manager._accounts[1].alias_hash

    # B now fails too; no replacement remains -> exact typed exhaustion.
    with pytest.raises(GrokAccountPoolExhaustedError):
        manager.report_failure(lease_b, AccountFailureKind.QUOTA_EXHAUSTED)


def test_no_secret_or_raw_alias_in_lease(tmp_path):
    manager = _make_manager(tmp_path)
    lease = manager.acquire("consumer-secret")

    public = {
        "provider": lease.provider,
        "consumer_id": lease.consumer_id,
        "alias_hash": lease.account_alias_hash,
    }
    serialized = json.dumps(public)
    assert "grok-a" not in serialized
    assert "grok-b" not in serialized
    assert "XAI_API_KEY" not in serialized
    assert "GROK_API_KEY" not in serialized
    assert "secret_xai" not in serialized
    assert "secret_grok" not in serialized
    assert "token" not in serialized


def test_get_grok_account_pool_manager_env_binding(monkeypatch, tmp_path):
    set_grok_account_pool_manager(None)
    monkeypatch.setenv("NEXUS_GROK_ACCOUNT_ALIASES", "g1,g2")
    monkeypatch.setenv("NEXUS_GROK_HOME_G1", str(tmp_path / "home-g1"))
    monkeypatch.setenv("NEXUS_GROK_HOME_G2", str(tmp_path / "home-g2"))

    manager = get_grok_account_pool_manager()
    assert manager._accounts[0].alias == "g1"
    assert manager._accounts[0].home_dir == str(tmp_path / "home-g1")
    set_grok_account_pool_manager(None)


def test_manager_cli_exit_error_is_redacted(tmp_path):
    manager_script = tmp_path / "mock-grok-cli-manager"
    secret_text = "secret_email=user@example.com_token_12345"
    manager_script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        f"sys.stderr.write('ERROR: {secret_text}\\n')\n"
        "sys.exit(1)\n"
    )
    manager_script.chmod(0o755)

    manager = GrokAccountPoolManager(
        manager_path=str(manager_script),
        manager_root=str(tmp_path / "mgr_root"),
    )

    with pytest.raises(GrokAccountPoolError) as exc_info:
        manager._call_manager_cli(["ensure-active"])

    err_msg = str(exc_info.value)
    assert "token_12345" not in err_msg
    assert "user@example.com" not in err_msg
    assert secret_text not in err_msg
    assert "exit code 1" in err_msg


def test_manager_path_resolution_uses_home_without_user_specific_absolute_path(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("NEXUS_GROK_ACCOUNT_POOL_MANAGER_PATH", raising=False)

    resolved = GrokAccountPoolManager.resolve_manager_path()

    assert resolved == str(tmp_path / ".nexus/grok-account-pool/bin/grok-cli-manager")
    assert "/Users/jameschen/" not in resolved
