"""Tests for AGY account pool manager and isolated environment creation."""

from __future__ import annotations

import os

import pytest

from nexus.services.agy_account_pool import (
    AgyAccount,
    AgyAccountPoolError,
    AgyAccountPoolManager,
    build_isolated_env,
    get_account_pool_manager,
    set_global_account_pool_manager,
)


def test_agy_account_alias_hash():
    account = AgyAccount(alias="test_user", home_dir="/tmp/test_user")
    assert len(account.alias_hash) == 12
    assert isinstance(account.alias_hash, str)


def test_build_isolated_env_removes_sensitive_api_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret_gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "secret_google")
    monkeypatch.setenv("GOOGLE_GENAI_API_KEY", "secret_genai")
    monkeypatch.setenv("OTHER_VAR", "keep_me")

    isolated = build_isolated_env(home_dir="/isolated/home")

    assert isolated["HOME"] == "/isolated/home"
    assert isolated["OTHER_VAR"] == "keep_me"
    assert "GEMINI_API_KEY" not in isolated
    assert "GOOGLE_API_KEY" not in isolated
    assert "GOOGLE_GENAI_API_KEY" not in isolated


def test_account_pool_manager_active_and_rotation():
    acc1 = AgyAccount(alias="acc1", home_dir="/home/acc1")
    acc2 = AgyAccount(alias="acc2", home_dir="/home/acc2")
    manager = AgyAccountPoolManager([acc1, acc2])

    assert manager.ensure_active().alias == "acc1"
    assert manager.active_account_alias_hash == acc1.alias_hash

    rotated = manager.rotate_account(reason="quota")
    assert rotated.alias == "acc2"
    assert manager.ensure_active().alias == "acc2"

    with pytest.raises(AgyAccountPoolError, match="No available AGY accounts"):
        manager.rotate_account(reason="quota")


def test_account_pool_manager_ensure_active_fails_when_empty():
    manager = AgyAccountPoolManager([])
    with pytest.raises(AgyAccountPoolError, match="No active AGY account"):
        manager.ensure_active()


def test_get_account_pool_manager_global(monkeypatch):
    set_global_account_pool_manager(None)
    monkeypatch.setenv("NEXUS_AGY_ACCOUNT_ALIASES", "u1,u2")
    manager = get_account_pool_manager()

    assert manager.ensure_active().alias == "u1"
    set_global_account_pool_manager(None)


def test_real_manager_cli_integration(tmp_path):
    manager_script = tmp_path / "mock-agy-cli-manager"
    manager_root = tmp_path / "mgr_root"
    runtime_dir = manager_root / "runtime"
    runtime_dir.mkdir(parents=True)

    state_file = manager_root / "mock_state.txt"
    script_content = f"""#!/usr/bin/env python3
import json, sys, pathlib
sf = pathlib.Path("{state_file}")
curr = sf.read_text().strip() if sf.exists() else "mock_acc_1"
if "rotate-after-failure" in sys.argv:
    curr = "mock_acc_2"
    sf.write_text(curr)
    print(json.dumps({{"active": "mock_acc_2", "switched_to": "mock_acc_2", "outcome": "rotated"}}))
elif "ensure-active" in sys.argv:
    print(json.dumps({{"active": curr, "switched_to": None, "reason": "ok"}}))
elif "status" in sys.argv:
    print(json.dumps({{"active": curr, "runtime_dir": "{runtime_dir}", "root": "{manager_root}"}}))
else:
    print(json.dumps({{}}))
"""
    manager_script.write_text(script_content)
    manager_script.chmod(0o755)

    manager = AgyAccountPoolManager(
        manager_path=str(manager_script),
        manager_root=str(manager_root),
        use_real_manager=True,
    )

    acc = manager.ensure_active()
    assert acc.alias == "mock_acc_1"
    assert acc.home_dir == str(runtime_dir.resolve())
    assert len(acc.alias_hash) == 12

    rotated = manager.rotate_account(reason="quota_test")
    assert rotated.alias == "mock_acc_2"


def test_real_manager_exhausted_raises_typed_error(tmp_path):
    from nexus.services.agy_account_pool import AgyAccountPoolExhaustedError

    manager_script = tmp_path / "mock-agy-cli-manager-empty"
    manager_root = tmp_path / "mgr_root_empty"
    manager_root.mkdir(parents=True)

    script_content = """#!/usr/bin/env python3
import json, sys
if "ensure-active" in sys.argv or "status" in sys.argv:
    print(json.dumps({"active": None, "reason": "no_active_account"}))
else:
    print(json.dumps({"active": None, "outcome": "no_active_account"}))
"""
    manager_script.write_text(script_content)
    manager_script.chmod(0o755)

    manager = AgyAccountPoolManager(
        manager_path=str(manager_script),
        manager_root=str(manager_root),
        use_real_manager=True,
    )

    with pytest.raises(AgyAccountPoolExhaustedError, match="AGY_ACCOUNT_POOL_EXHAUSTED"):
        manager.ensure_active()


def test_physical_manager_smoke():
    from pathlib import Path
    manager_path = Path.home() / ".nexus/agy-account-pool/bin/agy-cli-manager"
    if not manager_path.exists():
        pytest.skip("Real manager binary not found at default location")

    manager = AgyAccountPoolManager(use_real_manager=True, manager_path=str(manager_path))

    assert manager.resolve_manager_path() is not None

    status_res = manager._call_manager_cli(["status", "--json"])
    assert "active" in status_res
    assert "runtime_dir" in status_res
    assert "root" in status_res

    active_res = manager._call_manager_cli(["ensure-active", "--json"])
    assert "active" in active_res
    assert "switch_mode" in active_res
