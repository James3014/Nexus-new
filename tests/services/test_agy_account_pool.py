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
    assert manager._use_real_manager is False
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
    live_home = manager_root / "live-home"
    live_dir = live_home / ".gemini"
    live_dir.mkdir(parents=True)

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
    print(json.dumps({{"active": curr, "live_dir": "{live_dir}", "runtime_dir": "{manager_root / 'runtime'}", "root": "{manager_root}"}}))
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
    assert acc.home_dir == str(live_home.resolve())
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


def test_manager_root_derivation(tmp_path, monkeypatch):
    mgr_bin = tmp_path / "pool_root" / "bin" / "agy-cli-manager"
    mgr_bin.parent.mkdir(parents=True)
    mgr_bin.write_text("#!/bin/sh\nexit 0")
    mgr_bin.chmod(0o755)

    root = AgyAccountPoolManager.resolve_manager_root(manager_path=str(mgr_bin))
    assert root == str((tmp_path / "pool_root" / "runtime").resolve())

    monkeypatch.setenv("NEXUS_AGY_ACCOUNT_POOL_ROOT", str(tmp_path / "override_root"))
    assert AgyAccountPoolManager.resolve_manager_root(manager_path=str(mgr_bin)) == str((tmp_path / "override_root").resolve())


def test_live_dir_parent_home(tmp_path):
    from nexus.services.agy_account_pool import AgyAccountPoolManagerError

    manager_script = tmp_path / "mock-agy-cli-manager"
    manager_root = tmp_path / "mgr_root"
    account_home = manager_root / "acc_home"
    live_dir = account_home / ".gemini"
    live_dir.mkdir(parents=True)

    script_content = f"""#!/usr/bin/env python3
import json, sys
if "ensure-active" in sys.argv:
    print(json.dumps({{"active": "acc1", "switched_to": None}}))
elif "status" in sys.argv:
    print(json.dumps({{"active": "acc1", "live_dir": "{live_dir}"}}))
"""
    manager_script.write_text(script_content)
    manager_script.chmod(0o755)

    manager = AgyAccountPoolManager(
        manager_path=str(manager_script),
        manager_root=str(manager_root),
        use_real_manager=True,
    )
    acc = manager.ensure_active()
    assert acc.home_dir == str(account_home.resolve())

    # Invalid live_dir (non-existent)
    bad_script = tmp_path / "mock-bad-live"
    bad_script.write_text(f"""#!/usr/bin/env python3
import json, sys
if "ensure-active" in sys.argv:
    print(json.dumps({{"active": "acc1"}}))
else:
    print(json.dumps({{"active": "acc1", "live_dir": "{tmp_path / "nonexistent" / ".gemini"}"}}))
""")
    bad_script.chmod(0o755)
    mgr_bad = AgyAccountPoolManager(manager_path=str(bad_script), use_real_manager=True)
    with pytest.raises(AgyAccountPoolManagerError, match="live_dir"):
        mgr_bad.ensure_active()


def test_malformed_json_and_manager_failure_redaction(tmp_path):
    from nexus.services.agy_account_pool import AgyAccountPoolManagerError

    manager_script = tmp_path / "mock-secret-leak-manager"
    secret_text = "secret_email=user@example.com_token_12345"
    script_content = f"""#!/usr/bin/env python3
import sys
sys.stderr.write("ERROR: {secret_text}\\n")
sys.exit(1)
"""
    manager_script.write_text(script_content)
    manager_script.chmod(0o755)

    manager = AgyAccountPoolManager(
        manager_path=str(manager_script),
        use_real_manager=True,
    )

    with pytest.raises(AgyAccountPoolManagerError) as exc_info:
        manager._call_manager_cli(["ensure-active"])

    err_msg = str(exc_info.value)
    assert secret_text not in err_msg
    assert "user@example.com" not in err_msg
    assert "token_12345" not in err_msg
    assert "exit code 1" in err_msg


def test_physical_manager_smoke():
    from pathlib import Path
    manager_path = Path("/Users/jameschen/.nexus/agy-account-pool/bin/agy-cli-manager")
    if not manager_path.exists():
        pytest.skip("Real manager binary not found at default location")

    manager = AgyAccountPoolManager(use_real_manager=True, manager_path=str(manager_path))

    assert manager.resolve_manager_path() == str(manager_path.resolve())
    assert manager._manager_root == str(Path("/Users/jameschen/.nexus/agy-account-pool/runtime").resolve())

    status_res = manager._call_manager_cli(["status", "--json"])
    assert status_res.get("active") is not None
    assert status_res.get("live_dir") is not None
    assert len(status_res.get("accounts", {})) == 12

    active_acc = manager.ensure_active()
    assert active_acc.alias == status_res.get("active")
    assert len(active_acc.alias_hash) == 12

    sanitized_evidence = {
        "active": active_acc.alias,
        "alias_hash": active_acc.alias_hash,
        "account_count": len(status_res.get("accounts", {})),
        "root": status_res.get("root"),
    }
    assert sanitized_evidence["account_count"] == 12
    assert sanitized_evidence["active"] is not None
