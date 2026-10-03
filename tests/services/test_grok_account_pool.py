from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.services.external_account_pool import AccountFailureKind
from nexus.services.external_worker_runtime import GrokAccountAdapter
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
    GrokAccountPoolManager(root).bind_host(confirm_existing_pool=True)


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


def test_register_local_profile_creates_private_state_and_inventory(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    home = tmp_path / "profile"
    home.mkdir(mode=0o700)
    manager = GrokAccountPoolManager(root)

    registered = manager.register_local_profile(
        alias="grok-02",
        home_path=home,
        display_label="owner@example.invalid",
    )

    assert registered.alias == "grok-02"
    assert registered.display_label == "owner@example.invalid"
    state = json.loads((root / "state.json").read_text())
    assert state["accounts"]["grok-02"]["home_path"] == str(home.resolve())
    assert state["accounts"]["grok-02"]["display_label"] == "owner@example.invalid"
    assert (root / "state.json").stat().st_mode & 0o077 == 0
    inventory = manager.local_accounts()
    assert len(inventory) == 1
    assert inventory[0].home_exists is True
    assert inventory[0].leased is False


def test_register_local_profile_rejects_duplicate_alias_home_and_label(
    tmp_path: Path,
) -> None:
    root = tmp_path / "pool"
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir(mode=0o700)
    second.mkdir(mode=0o700)
    manager = GrokAccountPoolManager(root)
    manager.register_local_profile(
        alias="grok-02",
        home_path=first,
        display_label="same@example.invalid",
    )

    with pytest.raises(GrokAccountPoolError, match="ALIAS_ALREADY_REGISTERED"):
        manager.register_local_profile(alias="grok-02", home_path=second)
    with pytest.raises(GrokAccountPoolError, match="PROFILE_HOME_ALREADY_REGISTERED"):
        manager.register_local_profile(alias="grok-03", home_path=first)
    with pytest.raises(GrokAccountPoolError, match="DISPLAY_LABEL_DUPLICATE"):
        manager.register_local_profile(
            alias="grok-03",
            home_path=second,
            display_label="SAME@example.invalid",
        )


def test_register_local_profile_rejects_open_permissions(tmp_path: Path) -> None:
    home = tmp_path / "profile"
    home.mkdir(mode=0o755)
    manager = GrokAccountPoolManager(tmp_path / "pool")

    with pytest.raises(GrokAccountPoolError, match="PERMISSIONS_TOO_OPEN"):
        manager.register_local_profile(alias="grok-02", home_path=home)


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
        ("Error: Not signed in.", AccountFailureKind.AUTH_OR_SESSION_INVALID),
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


def test_legacy_existing_pool_requires_explicit_host_binding_confirmation(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    home = tmp_path / "a"
    root.mkdir(parents=True)
    home.mkdir()
    (root / "state.json").write_text(
        json.dumps({
            "accounts": {
                "acct-0": {
                    "home_path": str(home),
                    "enabled": True,
                    "cooldown_until": 0.0,
                    "last_failure_reason": "",
                    "last_failure_timestamp": 0.0,
                }
            },
            "leases": {},
            "updated_at": 0.0,
        }),
        encoding="utf-8",
    )
    manager = GrokAccountPoolManager(root, host_identity="owner-host")

    with pytest.raises(GrokAccountPoolError, match="HOST_UNBOUND"):
        manager.local_accounts()
    with pytest.raises(GrokAccountPoolError, match="CONFIRMATION_REQUIRED"):
        manager.bind_host()

    binding = manager.bind_host(confirm_existing_pool=True)
    assert binding.status == "BOUND"
    assert binding.matches is True
    assert len(manager.local_accounts()) == 1


def test_copied_pool_fails_closed_on_wrong_host_before_lease(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    home = tmp_path / "a"
    home.mkdir(mode=0o700)
    owner = GrokAccountPoolManager(root, host_identity="owner-host")
    owner.register_local_profile(alias="acct-0", home_path=home)

    copied = GrokAccountPoolManager(root, host_identity="other-host")
    binding = copied.host_binding()
    assert binding.status == "HOST_MISMATCH"
    assert binding.matches is False
    assert binding.owner_host_id_hash != binding.current_host_id_hash

    with pytest.raises(GrokAccountPoolError, match="HOST_MISMATCH"):
        copied.local_accounts()
    with pytest.raises(GrokAccountPoolError, match="HOST_MISMATCH"):
        copied.acquire("consumer")


def test_host_binding_stores_only_non_secret_hash(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    manager = GrokAccountPoolManager(root, host_identity="physical-machine-secret-source")
    binding = manager.bind_host()

    state = json.loads((root / "state.json").read_text())
    raw = json.dumps(state)
    assert binding.status == "BOUND"
    assert len(binding.owner_host_id_hash or "") == 64
    assert "physical-machine-secret-source" not in raw
    assert state["host_binding"]["schema"] == "nexus.grok_pool_host_binding.v1"


def test_worker_account_adapter_fails_on_wrong_host_before_provider_binding(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    home = tmp_path / "a"
    home.mkdir(mode=0o700)
    owner = GrokAccountPoolManager(root, host_identity="owner-host")
    owner.register_local_profile(alias="acct-0", home_path=home)

    adapter = GrokAccountAdapter()
    adapter.manager = GrokAccountPoolManager(root, host_identity="other-host")

    with pytest.raises(GrokAccountPoolError, match="HOST_MISMATCH"):
        adapter.acquire("grokop_" + "a" * 32)
    assert adapter._leases == {}


def test_wrong_host_nonrotation_failure_still_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    home = tmp_path / "a"
    home.mkdir(mode=0o700)
    owner = GrokAccountPoolManager(root, host_identity="owner-host")
    owner.register_local_profile(alias="acct-0", home_path=home)
    lease = owner.acquire("consumer")

    copied = GrokAccountPoolManager(root, host_identity="other-host")
    with pytest.raises(GrokAccountPoolError, match="HOST_MISMATCH"):
        copied.report_failure(lease, AccountFailureKind.TIMEOUT)

    owner.release(lease)
