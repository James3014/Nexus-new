"""AGY Account Pool Manager for governed multi-account failover and isolation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Optional, Sequence


SENSITIVE_API_KEYS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY")


class AgyAccountPoolError(RuntimeError):
    """Base exception for AGY Account Pool operations."""


@dataclass
class AgyAccount:
    alias: str
    home_dir: str
    is_active: bool = True

    @property
    def alias_hash(self) -> str:
        return hashlib.sha256(self.alias.encode("utf-8")).hexdigest()[:12]


def build_isolated_env(
    home_dir: Optional[str] = None,
    base_env: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Build an isolated environment with HOME configured and sensitive API keys absent."""
    env = dict(os.environ if base_env is None else base_env)
    if home_dir:
        env["HOME"] = str(home_dir)
    for key in SENSITIVE_API_KEYS:
        env.pop(key, None)
    return env


class AgyAccountPoolManager:
    """Manages rotation, active account state, and isolated HOME environments for AGY workers."""

    def __init__(self, accounts: Optional[Sequence[AgyAccount]] = None):
        self._accounts: list[AgyAccount] = list(accounts or [])
        self._active_index: int = 0 if self._accounts else -1

    @property
    def active_account(self) -> Optional[AgyAccount]:
        if 0 <= self._active_index < len(self._accounts):
            return self._accounts[self._active_index]
        return None

    @property
    def active_account_alias_hash(self) -> Optional[str]:
        account = self.active_account
        return account.alias_hash if account else None

    def ensure_active(self, target_worktree: Optional[str] = None) -> AgyAccount:
        account = self.active_account
        if account is None or not account.is_active:
            raise AgyAccountPoolError("No active AGY account available")
        return account

    def get_active_account(self) -> Optional[AgyAccount]:
        return self.active_account

    def rotate_account(
        self,
        reason: str = "failover",
        failed_account_hash: Optional[str] = None,
    ) -> AgyAccount:
        if not self._accounts:
            raise AgyAccountPoolError("No AGY accounts registered in pool")

        start_idx = self._active_index
        if 0 <= start_idx < len(self._accounts):
            self._accounts[start_idx].is_active = False

        next_idx = (start_idx + 1) % len(self._accounts) if start_idx >= 0 else 0
        visited = 0
        while visited < len(self._accounts):
            if self._accounts[next_idx].is_active:
                self._active_index = next_idx
                return self._accounts[next_idx]
            next_idx = (next_idx + 1) % len(self._accounts)
            visited += 1

        self._active_index = -1
        raise AgyAccountPoolError("No available AGY accounts remaining in pool")

    def build_isolated_env(self, base_env: Optional[dict[str, str]] = None) -> dict[str, str]:
        account = self.active_account
        home_dir = account.home_dir if account else None
        return build_isolated_env(home_dir=home_dir, base_env=base_env)


_GLOBAL_POOL_MANAGER: Optional[AgyAccountPoolManager] = None


def get_account_pool_manager() -> AgyAccountPoolManager:
    global _GLOBAL_POOL_MANAGER
    if _GLOBAL_POOL_MANAGER is not None:
        return _GLOBAL_POOL_MANAGER

    accounts: list[AgyAccount] = []
    aliases_str = os.getenv("NEXUS_AGY_ACCOUNT_ALIASES", "").strip()
    if aliases_str:
        for alias in aliases_str.split(","):
            alias = alias.strip()
            if alias:
                home_env_key = f"NEXUS_AGY_HOME_{alias.upper()}"
                home = os.getenv(home_env_key, str(Path.home() / f".gemini/antigravity-{alias}"))
                accounts.append(AgyAccount(alias=alias, home_dir=home))

    if not accounts:
        accounts.append(AgyAccount(alias="default", home_dir=str(Path.home())))

    _GLOBAL_POOL_MANAGER = AgyAccountPoolManager(accounts)
    return _GLOBAL_POOL_MANAGER


def set_global_account_pool_manager(manager: Optional[AgyAccountPoolManager]) -> None:
    global _GLOBAL_POOL_MANAGER
    _GLOBAL_POOL_MANAGER = manager
