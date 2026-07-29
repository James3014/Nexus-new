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
