"""Hostile tests for the Grok account pool provider binding.

The suite pins the repaired contract: isolated allowlist environments with
hash-derived HOME paths, failover that never reuses a profile held by another
consumer, cooldown-and-rotation instead of permanent quarantine, and one
consistent typed exhaustion error on both the initial and failover paths.
"""

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
    return GrokAccountPoolManager(
        [
            GrokAccount(alias="grok-a", home_dir=h1),
            GrokAccount(alias="grok-b", home_dir=h2),
            GrokAccount(alias="grok-c", home_dir=h3),
        ]
    )


def test_grok_account_alias_hash_is_non_secret_slug():
    account = GrokAccount(alias="profile-1", home_dir="/tmp/grok-profile-1")
    assert len(account.alias_hash) == 12
    assert account.alias_hash != account.alias
    assert account.alias_hash.isalnum()


def test_isolated_env_does_not_inherit_ambient_process_secrets(monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret_aws")
    monkeypatch.setenv("MY_SECRET_TOKEN", "secret_token")
    monkeypatch.setenv("CLOUDSQL_PASSWORD", "secret_db")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/original")

    isolated = build_grok_isolated_env(home_dir="/profiles/grok-a")

    assert isolated == {"HOME": "/profiles/grok-a"}
    assert "AWS_SECRET_ACCESS_KEY" not in isolated
    assert "MY_SECRET_TOKEN" not in isolated
    assert "CLOUDSQL_PASSWORD" not in isolated
    assert "PATH" not in isolated


def test_isolated_env_allowlist_passes_only_neutral_base_env_keys():
    base = {
        "PATH": "/custom/bin",
        "LANG": "en_US.UTF-8",
        "AWS_SECRET_ACCESS_KEY": "secret_aws",
        "XAI_API_KEY": "secret_xai",
        "GROK_API_KEY": "secret_grok",
        "NEXUS_GROK_API_KEY": "secret_nexus_grok",
        "ARBITRARY_VAR": "keep_out",
    }

    isolated = build_grok_isolated_env(
        home_dir="/profiles/grok-a",
        base_env=base,
        alias_hash="abcdef123456",
    )

    assert isolated["PATH"] == "/custom/bin"
    assert isolated["LANG"] == "en_US.UTF-8"
    assert "AWS_SECRET_ACCESS_KEY" not in isolated
    assert "XAI_API_KEY" not in isolated
    assert "GROK_API_KEY" not in isolated
    assert "NEXUS_GROK_API_KEY" not in isolated
    assert "ARBITRARY_VAR" not in isolated


def test_isolated_env_home_is_hash_derived_and_raw_alias_absent():
    isolated = build_grok_isolated_env(
        home_dir="/profiles/grok-a",
        alias_hash="abcdef123456",
    )

    assert isolated["HOME"] == "/profiles/profile-abcdef123456"
    assert all("grok-a" not in str(value) for value in isolated.values())


def test_acquire_binds_immutable_lease_and_hash_derived_env(tmp_path):
    manager = _make_manager(tmp_path)
    lease = manager.acquire("consumer-1")

    assert lease.provider == "grok"
    assert lease.consumer_id == "consumer-1"
    assert len(lease.account_alias_hash) == 12
    expected_home = str(tmp_path / f"profile-{manager._accounts[0].alias_hash}")
    assert lease.execution_env["HOME"] == expected_home
    assert "grok-a" not in lease.execution_env["HOME"]


def test_concurrent_consumers_are_isolated(tmp_path):
    manager = _make_manager(tmp_path)
    lease_a = manager.acquire("consumer-A")
    lease_b = manager.acquire("consumer-B")

    assert lease_a.lease_id != lease_b.lease_id
    assert lease_a.account_alias_hash == manager._accounts[0].alias_hash
    assert lease_b.account_alias_hash == manager._accounts[1].alias_hash
    assert lease_a.execution_env["HOME"] == str(
        tmp_path / f"profile-{manager._accounts[0].alias_hash}"
    )
    assert lease_b.execution_env["HOME"] == str(
        tmp_path / f"profile-{manager._accounts[1].alias_hash}"
    )
    assert lease_a.execution_env["HOME"] != lease_b.execution_env["HOME"]


def test_lease_env_contains_no_raw_alias_or_secret_material(tmp_path, monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret_aws")
    monkeypatch.setenv("MY_SECRET_TOKEN", "secret_token")
    manager = _make_manager(tmp_path)
    lease = manager.acquire("consumer-secret")

    public = {
        "provider": lease.provider,
        "consumer_id": lease.consumer_id,
        "alias_hash": lease.account_alias_hash,
        "execution_env": dict(lease.execution_env),
    }
    serialized = json.dumps(public)
    assert "grok-a" not in serialized
    assert "grok-b" not in serialized
    assert "grok-c" not in serialized
    assert "AWS_SECRET_ACCESS_KEY" not in serialized
    assert "MY_SECRET_TOKEN" not in serialized
    assert "secret_aws" not in serialized
    assert "secret_token" not in serialized
    assert all("grok-a" not in str(v) for v in lease.execution_env.values())


def test_non_eligible_failure_does_not_rotate_or_cooldown(tmp_path):
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
        assert manager._accounts[0].cooldown_until is None
    assert lease.account_alias_hash == original_hash
    assert lease.lease_id in manager._pool._active_leases


def test_eligible_failure_failover_rotates_to_unheld_profile(tmp_path):
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
    assert replacement_a.account_alias_hash != lease_a.account_alias_hash
    assert replacement_a.lease_id != lease_b.lease_id
    expected_home = str(tmp_path / f"profile-{manager._accounts[2].alias_hash}")
    assert replacement_a.execution_env["HOME"] == expected_home
    assert manager._accounts[0].is_active is False
    assert manager._accounts[0].cooldown_until is not None
    assert manager._accounts[1].is_active is True
    assert lease_b.account_alias_hash == b_hash_before
    assert dict(lease_b.execution_env) == b_env_before
    assert lease_b.lease_id in manager._pool._active_leases
    assert lease_a.lease_id not in manager._pool._active_leases


def test_failover_never_reuses_profile_held_by_another_consumer(tmp_path):
    h1 = str(tmp_path / "grok-a")
    h2 = str(tmp_path / "grok-b")
    for p in (h1, h2):
        Path(p).mkdir(parents=True)
    manager = GrokAccountPoolManager(
        [
            GrokAccount(alias="grok-a", home_dir=h1),
            GrokAccount(alias="grok-b", home_dir=h2),
        ]
    )
    lease_a = manager.acquire("consumer-A")
    lease_b = manager.acquire("consumer-B")

    with pytest.raises(GrokAccountPoolExhaustedError) as exc_info:
        manager.report_failure(lease_a, AccountFailureKind.QUOTA_EXHAUSTED)

    assert "GROK_ACCOUNT_POOL_EXHAUSTED" in str(exc_info.value)
    assert lease_b.lease_id in manager._pool._active_leases
    assert lease_b.account_alias_hash == manager._accounts[1].alias_hash


def test_released_profile_becomes_eligible_for_failover(tmp_path):
    h1 = str(tmp_path / "grok-a")
    h2 = str(tmp_path / "grok-b")
    for p in (h1, h2):
        Path(p).mkdir(parents=True)
    manager = GrokAccountPoolManager(
        [
            GrokAccount(alias="grok-a", home_dir=h1),
            GrokAccount(alias="grok-b", home_dir=h2),
        ]
    )
    lease_a = manager.acquire("consumer-A")
    lease_b = manager.acquire("consumer-B")
    manager.release(lease_b)

    replacement_a = manager.report_failure(
        lease_a,
        AccountFailureKind.AUTH_OR_SESSION_INVALID,
    )

    assert replacement_a is not None
    assert replacement_a.account_alias_hash == manager._accounts[1].alias_hash
    assert replacement_a.lease_id != lease_b.lease_id


def test_cooldown_expiry_reenables_profile_for_new_consumers(tmp_path):
    state = {"now": 100.0}
    manager = _make_manager(tmp_path)
    manager._cooldown_seconds = 60.0
    manager._clock = lambda: state["now"]
    lease_a = manager.acquire("consumer-A")
    lease_b = manager.acquire("consumer-B")

    replacement_a = manager.report_failure(
        lease_a,
        AccountFailureKind.QUOTA_EXHAUSTED,
    )
    assert replacement_a is not None
    assert manager._accounts[0].is_active is False
    assert manager._accounts[0].cooldown_until == 160.0

    state["now"] = 161.0
    manager._refresh_pool_health()

    assert manager._accounts[0].is_active is True
    assert manager._accounts[0].cooldown_until is None
    manager.release(lease_b)
    manager.release(replacement_a)
    new_lease = manager.acquire("consumer-C")
    assert new_lease.account_alias_hash == manager._accounts[0].alias_hash


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


def test_failover_exhaustion_when_all_remaining_profiles_held(tmp_path):
    manager = _make_manager(tmp_path)
    lease_a = manager.acquire("consumer-A")
    lease_b = manager.acquire("consumer-B")

    replacement_a = manager.report_failure(
        lease_a,
        AccountFailureKind.TOKEN_EXPIRED,
    )
    assert replacement_a is not None
    assert replacement_a.account_alias_hash == manager._accounts[2].alias_hash

    with pytest.raises(GrokAccountPoolExhaustedError):
        manager.report_failure(replacement_a, AccountFailureKind.TOKEN_EXPIRED)

    assert lease_b.lease_id in manager._pool._active_leases
    assert lease_b.account_alias_hash == manager._accounts[1].alias_hash


def test_initial_acquire_exhaustion_raises_typed_grok_error():
    manager = GrokAccountPoolManager([])
    with pytest.raises(GrokAccountPoolExhaustedError) as exc_info:
        manager.acquire("consumer-1")
    assert "GROK_ACCOUNT_POOL_EXHAUSTED" in str(exc_info.value)


def test_initial_acquire_wraps_substrate_exhaustion():
    manager = GrokAccountPoolManager([])
    try:
        manager.acquire("consumer-1")
    except GrokAccountPoolExhaustedError as exc:
        assert isinstance(exc.__cause__, ExternalAccountPoolExhaustedError)
    else:  # pragma: no cover - guard against false-green pass
        raise AssertionError("expected GrokAccountPoolExhaustedError")


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


def test_get_grok_account_pool_manager_env_binding(monkeypatch, tmp_path):
    set_grok_account_pool_manager(None)
    monkeypatch.setenv("NEXUS_GROK_ACCOUNT_ALIASES", "g1,g2")
    monkeypatch.setenv("NEXUS_GROK_HOME_G1", str(tmp_path / "home-g1"))
    monkeypatch.setenv("NEXUS_GROK_HOME_G2", str(tmp_path / "home-g2"))

    manager = get_grok_account_pool_manager()
    assert manager._accounts[0].alias == "g1"
    assert manager._accounts[0].home_dir == str(tmp_path / "home-g1")
    set_grok_account_pool_manager(None)


def test_env_bound_manager_lease_home_is_hash_derived(monkeypatch, tmp_path):
    set_grok_account_pool_manager(None)
    monkeypatch.setenv("NEXUS_GROK_ACCOUNT_ALIASES", "g1")
    monkeypatch.setenv("NEXUS_GROK_HOME_G1", str(tmp_path / "home-g1"))

    manager = get_grok_account_pool_manager()
    lease = manager.acquire("consumer-env")

    assert lease.execution_env["HOME"] == str(
        tmp_path / f"profile-{manager._accounts[0].alias_hash}"
    )
    assert "g1" not in lease.execution_env["HOME"]
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
