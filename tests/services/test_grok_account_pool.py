"""Hostile tests for the Grok account pool provider binding.

The suite pins the repaired contract: isolated allowlist environments with
hash-derived HOME paths, failover that never reuses a profile held by another
consumer, cooldown-and-rotation instead of permanent quarantine, and one
consistent typed exhaustion error on both the initial and failover paths.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
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
    GrokAccountPoolLeaseError,
    GrokAccountPoolManager,
    GrokAttemptLineage,
    build_grok_isolated_env,
    classify_grok_failure,
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
        ],
        isolated_root=str(tmp_path / "neutral-grok-profiles"),
    )


def test_grok_account_alias_hash_is_non_secret_slug():
    account = GrokAccount(
        alias="profile-1",
        home_dir="/tmp/grok-profile-1",  # nosec B108 - literal test fixture path is not executed
    )
    assert len(account.alias_hash) == 12
    assert account.alias_hash != account.alias
    assert account.alias_hash.isalnum()


def test_isolated_env_requires_alias_hash_and_does_not_inherit_ambient_process_secrets(monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret_aws")
    monkeypatch.setenv("MY_SECRET_TOKEN", "secret_token")
    monkeypatch.setenv("CLOUDSQL_PASSWORD", "secret_db")
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("HOME", "/original")

    with pytest.raises(GrokAccountPoolError, match="GROK_ALIAS_HASH_REQUIRED"):
        build_grok_isolated_env(home_dir="/profiles/grok-a")

    isolated = build_grok_isolated_env(
        home_dir="/profiles/grok-a",
        alias_hash="abcdef123456",
        isolated_root="/neutral/grok-profiles",
    )

    assert isolated == {"HOME": "/neutral/grok-profiles/profile-abcdef123456"}
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
        isolated_root="/neutral/grok-profiles",
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
        isolated_root="/neutral/grok-profiles",
    )

    assert isolated["HOME"] == "/neutral/grok-profiles/profile-abcdef123456"
    assert all("grok-a" not in str(value) for value in isolated.values())


def test_isolated_env_rejects_invalid_hash_and_ignores_nested_alias_home(tmp_path):
    for invalid in (None, "raw-alias", "ABCDEF123456", "abcdef12345"):
        with pytest.raises(GrokAccountPoolError, match="GROK_ALIAS_HASH_REQUIRED"):
            build_grok_isolated_env(
                home_dir=str(tmp_path / "raw-alias" / "nested" / "profile"),
                alias_hash=invalid,
                isolated_root=str(tmp_path / "neutral-root"),
            )

    isolated = build_grok_isolated_env(
        home_dir=str(tmp_path / "raw-alias" / "nested" / "profile"),
        alias_hash="abcdef123456",
        isolated_root=str(tmp_path / "neutral-root"),
    )
    assert isolated["HOME"] == str(tmp_path / "neutral-root" / "profile-abcdef123456")
    assert "raw-alias" not in isolated["HOME"]


def test_attempt_lineage_is_immutable_serializable_and_redacted():
    lineage = GrokAttemptLineage(
        provider="grok",
        consumer_id="task-17",
        attempt=2,
        account_alias_hash="abcdef123456",
        failure_kind=AccountFailureKind.QUOTA_EXHAUSTED,
        previous_lease_id="lease_previous",
        previous_account_alias_hash="0123456789ab",
        replacement_lease_id="lease_replacement",
        replacement_account_alias_hash="fedcba654321",
        outcome="ROTATED",
    )
    public = lineage.to_public_dict()
    encoded = lineage.serialize_public()

    assert json.loads(encoded) == public
    assert set(public) == {
        "provider",
        "consumer_id",
        "attempt",
        "account_alias_hash",
        "failure_kind",
        "previous_lease_id",
        "previous_account_alias_hash",
        "replacement_lease_id",
        "replacement_account_alias_hash",
        "outcome",
    }
    assert all(secret not in encoded for secret in ("/home", "raw-alias", "TOKEN", "stderr"))
    public["outcome"] = "TAMPERED"
    assert lineage.outcome == "ROTATED"
    with pytest.raises((AttributeError, TypeError)):
        setattr(lineage, "outcome", "TAMPERED")


def test_real_pool_flows_emit_monotonic_lineage_and_isolated_public_snapshots(tmp_path):
    manager = _make_manager(tmp_path)
    lease_a = manager.acquire("consumer-lineage-a")
    lease_b = manager.acquire("consumer-lineage-b")

    assert manager.report_failure(lease_a, AccountFailureKind.MODEL_OR_TASK_ERROR) is None
    replacement = manager.report_failure(lease_a, AccountFailureKind.QUOTA_EXHAUSTED)
    assert replacement is not None
    manager.release(replacement)

    records_a = manager.get_attempt_lineage(consumer_id="consumer-lineage-a")
    assert [record.attempt for record in records_a] == [1, 2, 3, 4]
    assert [record.outcome for record in records_a] == [
        "ACQUIRED",
        "NO_ROTATION",
        "ROTATED",
        "RELEASED",
    ]
    rotated = records_a[2]
    assert rotated.failure_kind is AccountFailureKind.QUOTA_EXHAUSTED
    assert rotated.previous_lease_id == lease_a.lease_id
    assert rotated.replacement_lease_id == replacement.lease_id
    assert rotated.previous_account_alias_hash == lease_a.account_alias_hash
    assert rotated.replacement_account_alias_hash == replacement.account_alias_hash
    assert manager.get_attempt_lineage(lease_id=replacement.lease_id)[0] is rotated

    records_b = manager.get_attempt_lineage(consumer_id="consumer-lineage-b")
    assert len(records_b) == 1
    assert records_b[0].account_alias_hash == lease_b.account_alias_hash
    public = [
        dict(record)
        for record in manager.get_public_attempt_lineage(consumer_id="consumer-lineage-a")
    ]
    public[0]["outcome"] = "TAMPERED"
    assert manager.get_attempt_lineage("consumer-lineage-a")[0].outcome == "ACQUIRED"
    assert all(
        forbidden not in record.serialize_public()
        for record in records_a
        for forbidden in ("grok-a", "grok-b", "home_dir", "execution_env", "stderr", "TOKEN")
    )


def test_exhaustion_flow_emits_final_lineage_without_replacement(tmp_path):
    root = tmp_path / "neutral-grok-profiles"
    (tmp_path / "grok-a").mkdir()
    (tmp_path / "grok-b").mkdir()
    manager = GrokAccountPoolManager(
        [
            GrokAccount("grok-a", str(tmp_path / "grok-a")),
            GrokAccount("grok-b", str(tmp_path / "grok-b")),
        ],
        isolated_root=str(root),
    )
    lease_a = manager.acquire("consumer-exhaustion-a")
    manager.acquire("consumer-exhaustion-b")
    with pytest.raises(GrokAccountPoolExhaustedError):
        manager.report_failure(lease_a, AccountFailureKind.RATE_LIMITED)

    records = manager.get_attempt_lineage("consumer-exhaustion-a")
    assert [record.outcome for record in records] == ["ACQUIRED", "EXHAUSTED"]
    assert records[-1].replacement_lease_id is None
    assert records[-1].replacement_account_alias_hash is None


def test_acquire_binds_immutable_lease_and_hash_derived_env(tmp_path):
    manager = _make_manager(tmp_path)
    lease = manager.acquire("consumer-1")

    assert lease.provider == "grok"
    assert lease.consumer_id == "consumer-1"
    assert len(lease.account_alias_hash) == 12
    expected_home = str(
        tmp_path / "neutral-grok-profiles" / f"profile-{manager._accounts[0].alias_hash}"
    )
    assert lease.execution_env["HOME"] == expected_home
    assert "grok-a" not in lease.execution_env["HOME"]


def test_acquire_binds_opaque_home_to_configured_profile(tmp_path):
    profile_home = tmp_path / "credential-bearing-grok-a"
    profile_home.mkdir()
    (profile_home / "profile-state.json").write_text("profile-state")
    manager = GrokAccountPoolManager(
        [GrokAccount(alias="grok-a", home_dir=str(profile_home))],
        isolated_root=str(tmp_path / "neutral-grok-profiles"),
    )

    lease = manager.acquire("consumer-profile-binding")
    isolated_home = Path(lease.execution_env["HOME"])

    assert isolated_home.is_symlink()
    assert isolated_home.resolve() == profile_home.resolve()
    assert (isolated_home / "profile-state.json").read_text() == "profile-state"
    assert str(profile_home) not in lease.execution_env["HOME"]
    assert "credential-bearing-grok-a" not in json.dumps(dict(lease.execution_env))


def test_duplicate_configured_profiles_fail_closed(tmp_path):
    profile_home = tmp_path / "shared-profile"
    profile_home.mkdir()
    manager = GrokAccountPoolManager(
        [
            GrokAccount(alias="grok-a", home_dir=str(profile_home)),
            GrokAccount(alias="grok-b", home_dir=str(profile_home)),
        ],
        isolated_root=str(tmp_path / "neutral-grok-profiles"),
    )

    with pytest.raises(GrokAccountPoolError, match="GROK_PROFILE_HOME_BINDING_CONFLICT"):
        manager.acquire("consumer-duplicate-profile")


@pytest.mark.parametrize("source_kind", ["missing", "file"])
def test_invalid_configured_profile_home_fails_closed(tmp_path, source_kind):
    profile_home = tmp_path / "invalid-profile"
    if source_kind == "file":
        profile_home.write_text("not-a-profile-directory")
    manager = GrokAccountPoolManager(
        [GrokAccount(alias="grok-invalid", home_dir=str(profile_home))],
        isolated_root=str(tmp_path / "neutral-grok-profiles"),
    )

    with pytest.raises(GrokAccountPoolError, match="GROK_PROFILE_HOME_NOT_DIRECTORY"):
        manager.acquire("consumer-invalid-profile")


def test_concurrent_consumers_are_isolated(tmp_path):
    manager = _make_manager(tmp_path)
    lease_a = manager.acquire("consumer-A")
    lease_b = manager.acquire("consumer-B")

    assert lease_a.lease_id != lease_b.lease_id
    assert lease_a.account_alias_hash == manager._accounts[0].alias_hash
    assert lease_b.account_alias_hash == manager._accounts[1].alias_hash
    assert lease_a.execution_env["HOME"] == str(
        tmp_path / "neutral-grok-profiles" / f"profile-{manager._accounts[0].alias_hash}"
    )
    assert lease_b.execution_env["HOME"] == str(
        tmp_path / "neutral-grok-profiles" / f"profile-{manager._accounts[1].alias_hash}"
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
    assert manager._pool is not None
    assert lease.lease_id in manager._pool._active_leases


def test_equal_but_unowned_lease_cannot_release_or_rotate(tmp_path):
    manager = _make_manager(tmp_path)
    lease = manager.acquire("consumer-clone")
    clone = replace(lease)

    assert clone == lease
    assert clone is not lease
    with pytest.raises(GrokAccountPoolLeaseError, match="GROK_INVALID_ACCOUNT_LEASE"):
        manager.release(clone)
    with pytest.raises(GrokAccountPoolLeaseError, match="GROK_INVALID_ACCOUNT_LEASE"):
        manager.report_failure(clone, AccountFailureKind.QUOTA_EXHAUSTED)

    assert lease.lease_id in manager._active_leases
    assert manager._accounts[0].is_active is True


def test_released_or_replayed_lease_fails_closed(tmp_path):
    manager = _make_manager(tmp_path)
    lease = manager.acquire("consumer-replay")
    manager.release(lease)

    with pytest.raises(GrokAccountPoolLeaseError, match="GROK_INVALID_ACCOUNT_LEASE"):
        manager.release(lease)
    with pytest.raises(GrokAccountPoolLeaseError, match="GROK_INVALID_ACCOUNT_LEASE"):
        manager.report_failure(lease, AccountFailureKind.QUOTA_EXHAUSTED)


@pytest.mark.parametrize(
    ("status", "exit_code", "output", "expected"),
    [
        (
            "FAILED",
            1,
            "authentication failed; quota exceeded",
            AccountFailureKind.AUTH_OR_SESSION_INVALID,
        ),
        ("FAILED", 1, "session expired", AccountFailureKind.TOKEN_EXPIRED),
        ("FAILED", 1, "token refresh failed", AccountFailureKind.TOKEN_REFRESH_FAILED),
        ("FAILED", 1, "resource_exhausted", AccountFailureKind.QUOTA_EXHAUSTED),
        ("FAILED", 1, "429 rate limit", AccountFailureKind.RATE_LIMITED),
        ("FAILED", 1, "503 service unavailable", AccountFailureKind.ACCOUNT_UNAVAILABLE),
        ("FAILED", 1, "account disabled", AccountFailureKind.ACCOUNT_DISABLED),
        ("TIMED_OUT", 1, "quota exceeded", AccountFailureKind.TIMEOUT),
        ("CANCELLED", 1, "cancelled", AccountFailureKind.CANCELLED),
        ("FAILED", 1, "permission denied", AccountFailureKind.PERMISSION_OR_SCOPE_ERROR),
        ("FAILED", 2, "syntax error", AccountFailureKind.SYNTAX_OR_IMPLEMENTATION_ERROR),
        ("FAILED", 1, "model task malformed", AccountFailureKind.MODEL_OR_TASK_ERROR),
        ("FAILED", 1, "verifier failed", AccountFailureKind.VERIFIER_FAILED),
        ("FAILED", 1, "unrecognized provider output", AccountFailureKind.UNKNOWN),
    ],
)
def test_classifier_precedence_and_nonrotating_failures(status, exit_code, output, expected):
    assert classify_grok_failure(status, exit_code, output, "") is expected


def test_same_consumer_cannot_hold_two_leases_under_threads(tmp_path):
    manager = _make_manager(tmp_path)

    def acquire():
        try:
            return ("ok", manager.acquire("consumer-race").lease_id)
        except GrokAccountPoolError as exc:
            return ("error", str(exc))

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: acquire(), range(2)))

    assert sorted(outcome[0] for outcome in outcomes) == ["error", "ok"]
    assert [outcome[1] for outcome in outcomes if outcome[0] == "error"] == [
        "GROK_CONSUMER_ALREADY_BOUND"
    ]


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
    expected_home = str(
        tmp_path / "neutral-grok-profiles" / f"profile-{manager._accounts[2].alias_hash}"
    )
    assert replacement_a.execution_env["HOME"] == expected_home
    assert manager._accounts[0].is_active is False
    assert manager._accounts[0].cooldown_until is not None
    assert manager._accounts[1].is_active is True
    assert lease_b.account_alias_hash == b_hash_before
    assert dict(lease_b.execution_env) == b_env_before
    assert manager._pool is not None
    assert lease_b.lease_id in manager._pool._active_leases
    assert lease_a.lease_id not in manager._pool._active_leases


def test_failover_never_reuses_profile_held_by_another_consumer(tmp_path):
    h1 = str(tmp_path / "grok-a")
    h2 = str(tmp_path / "grok-b")
    for p in (h1, h2):
        Path(p).mkdir(parents=True)
    manager = GrokAccountPoolManager([
        GrokAccount(alias="grok-a", home_dir=h1),
        GrokAccount(alias="grok-b", home_dir=h2),
    ], isolated_root=str(tmp_path / "neutral-grok-profiles"))
    lease_a = manager.acquire("consumer-A")
    lease_b = manager.acquire("consumer-B")

    with pytest.raises(GrokAccountPoolExhaustedError) as exc_info:
        manager.report_failure(lease_a, AccountFailureKind.QUOTA_EXHAUSTED)

    assert "GROK_ACCOUNT_POOL_EXHAUSTED" in str(exc_info.value)
    assert manager._pool is not None
    assert lease_b.lease_id in manager._pool._active_leases
    assert lease_b.account_alias_hash == manager._accounts[1].alias_hash


def test_released_profile_becomes_eligible_for_failover(tmp_path):
    h1 = str(tmp_path / "grok-a")
    h2 = str(tmp_path / "grok-b")
    for p in (h1, h2):
        Path(p).mkdir(parents=True)
    manager = GrokAccountPoolManager([
        GrokAccount(alias="grok-a", home_dir=h1),
        GrokAccount(alias="grok-b", home_dir=h2),
    ], isolated_root=str(tmp_path / "neutral-grok-profiles"))
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

    assert manager._pool is not None
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

    assert manager._pool is not None
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
    (tmp_path / "home-g1").mkdir()
    monkeypatch.setenv("NEXUS_GROK_ACCOUNT_ALIASES", "g1")
    monkeypatch.setenv("NEXUS_GROK_HOME_G1", str(tmp_path / "home-g1"))
    monkeypatch.setenv("NEXUS_GROK_ISOLATED_ROOT", str(tmp_path / "neutral-grok-profiles"))

    manager = get_grok_account_pool_manager()
    lease = manager.acquire("consumer-env")

    assert lease.execution_env["HOME"] == str(
        tmp_path / "neutral-grok-profiles" / f"profile-{manager._accounts[0].alias_hash}"
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

    assert resolved is not None
    assert resolved == str(tmp_path / ".nexus/grok-account-pool/bin/grok-cli-manager")
    assert "/Users/jameschen/" not in resolved
