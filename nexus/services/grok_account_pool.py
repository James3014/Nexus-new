"""Grok account pool manager for provider-scoped credential/profile failover.

This module reuses the provider-neutral request-scoped
:class:`~nexus.services.external_account_pool.ExternalAccountPool` substrate.
It owns Grok-specific account/profile binding only; it does not select route,
provider, or capability and does not introduce a second pool framework.

Public leases expose only a non-secret alias hash and immutable execution
binding data. Raw profile names and any credential material stay machine-local.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

from nexus.services.external_account_pool import (
    AccountFailureKind,
    AccountLease,
    ExternalAccountPool,
    ExternalAccountPoolExhaustedError,
    InternalAccountRecord,
    is_rotation_eligible,
)

GROK_SENSITIVE_ENV_KEYS = ("XAI_API_KEY", "GROK_API_KEY", "NEXUS_GROK_API_KEY")

GROK_ACCOUNT_POOL_PROVIDER = "grok"


class GrokAccountPoolError(RuntimeError):
    """Base exception for Grok account pool operations."""


class GrokAccountPoolExhaustedError(GrokAccountPoolError):
    """Raised when no active Grok profile is available in the pool."""


@dataclass
class GrokAccount:
    """One machine-local Grok profile binding.

    ``alias`` is the local profile alias, not a credential. The public lease
    surface carries only ``alias_hash`` derived from the alias.
    """

    alias: str
    home_dir: str
    is_active: bool = True

    @property
    def alias_hash(self) -> str:
        return hashlib.sha256(self.alias.encode("utf-8")).hexdigest()[:12]


def build_grok_isolated_env(
    home_dir: Optional[str] = None,
    base_env: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """Build an isolated environment scoped to one Grok profile HOME.

    Sensitive Grok API-key variants are removed so a swapped profile cannot
    inherit another profile's credential material.
    """

    env = dict(os.environ if base_env is None else base_env)
    if home_dir:
        env["HOME"] = str(home_dir)
    for key in GROK_SENSITIVE_ENV_KEYS:
        env.pop(key, None)
    return env


class GrokAccountPoolManager:
    """Binds Grok execution to one immutable account lease at a time."""

    def __init__(
        self,
        accounts: Optional[Sequence[GrokAccount]] = None,
        manager_path: Optional[str] = None,
        manager_root: Optional[str] = None,
    ) -> None:
        self._accounts: list[GrokAccount] = list(accounts or [])
        self._manager_path: Optional[str] = manager_path
        self._manager_root: Optional[str] = manager_root
        self._pool: Optional[ExternalAccountPool] = None
        self._lease_to_raw_alias: dict[str, str] = {}

    @staticmethod
    def resolve_manager_path(override_path: Optional[str] = None) -> Optional[str]:
        if override_path:
            p = Path(override_path).expanduser()
            return str(p.resolve()) if p.exists() else str(p)
        env_path = os.getenv("NEXUS_GROK_ACCOUNT_POOL_MANAGER_PATH", "").strip()
        if env_path:
            p = Path(env_path).expanduser()
            return str(p.resolve()) if p.exists() else str(p)
        default_path = Path.home() / ".nexus/grok-account-pool/bin/grok-cli-manager"
        return str(default_path.resolve()) if default_path.exists() else str(default_path)

    @staticmethod
    def resolve_manager_root(
        override_root: Optional[str] = None,
        manager_path: Optional[str] = None,
    ) -> str:
        if override_root:
            p = Path(override_root).expanduser()
            return str(p.resolve()) if p.exists() else str(p)
        env_root = os.getenv("NEXUS_GROK_ACCOUNT_POOL_ROOT", "").strip()
        if env_root:
            p = Path(env_root).expanduser()
            return str(p.resolve()) if p.exists() else str(p)
        derived_from_mgr: Optional[Path] = None
        mgr_p = manager_path or GrokAccountPoolManager.resolve_manager_path()
        if mgr_p:
            p = Path(mgr_p).expanduser()
            if p.name == "grok-cli-manager" and p.parent.name == "bin":
                base = p.parent.parent
                if base.name.startswith("manager-venv") or base.name in ("venv", ".venv"):
                    base = base.parent
                derived_from_mgr = base / "runtime"
            elif p.exists():
                base = p.parent
                if base.name.startswith("manager-venv") or base.name in ("venv", ".venv"):
                    base = base.parent
                derived_from_mgr = base / "runtime"
        if derived_from_mgr:
            return (
                str(derived_from_mgr.resolve())
                if derived_from_mgr.exists()
                else str(derived_from_mgr)
            )
        fallback_root = Path.home() / ".nexus/grok-account-pool/runtime"
        return str(fallback_root.resolve()) if fallback_root.exists() else str(fallback_root)

    def _call_manager_cli(self, args: list[str], expect_json: bool = True) -> Any:
        mgr = self._manager_path or self.resolve_manager_path()
        if not mgr or not Path(mgr).is_file():
            raise GrokAccountPoolError("Grok account pool manager binary not found")
        root = self._manager_root or self.resolve_manager_root(manager_path=mgr)
        import subprocess

        cmd = [mgr, "--root", root] + args
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30.0)
        except Exception as exc:
            raise GrokAccountPoolError("Failed to execute grok-cli-manager") from exc
        if res.returncode != 0:
            raise GrokAccountPoolError(f"grok-cli-manager failed with exit code {res.returncode}")
        if not expect_json:
            return res.stdout
        try:
            import json

            return json.loads(res.stdout)
        except json.JSONDecodeError as exc:
            raise GrokAccountPoolError("Invalid JSON returned by grok-cli-manager") from exc

    def _ensure_pool(self) -> ExternalAccountPool:
        if self._pool is not None:
            return self._pool
        records: list[InternalAccountRecord] = []
        for acc in self._accounts:
            env = build_grok_isolated_env(home_dir=acc.home_dir)
            records.append(
                InternalAccountRecord(
                    internal_id=acc.alias,
                    alias_hash=acc.alias_hash,
                    execution_env=env,
                    is_available=acc.is_active,
                )
            )
        self._pool = ExternalAccountPool(
            provider=GROK_ACCOUNT_POOL_PROVIDER,
            accounts=records,
        )
        return self._pool

    def _refresh_pool_health(self) -> None:
        if self._pool is None:
            self._ensure_pool()
            return
        for acc in self._accounts:
            record = self._pool._accounts.get(acc.alias)
            if record is not None:
                record.is_available = acc.is_active

    def acquire(self, consumer_id: str) -> AccountLease:
        self._refresh_pool_health()
        pool = self._ensure_pool()
        lease = pool.acquire(consumer_id)
        self._lease_to_raw_alias[lease.lease_id] = pool._require_active_lease(lease)
        return lease

    def release(self, lease: AccountLease) -> None:
        pool = self._ensure_pool()
        pool.release(lease)
        self._lease_to_raw_alias.pop(lease.lease_id, None)

    def report_failure(
        self,
        lease: AccountLease,
        failure_kind: AccountFailureKind,
    ) -> Optional[AccountLease]:
        self._refresh_pool_health()
        pool = self._ensure_pool()
        if not is_rotation_eligible(failure_kind):
            return None
        failed_alias = self._lease_to_raw_alias.get(lease.lease_id)
        if failed_alias is None:
            try:
                failed_alias = pool._require_active_lease(lease)
            except Exception:
                return None
        for acc in self._accounts:
            if acc.alias == failed_alias:
                acc.is_active = False
        self._refresh_pool_health()
        try:
            next_lease = pool.report_failure(lease, failure_kind)
        except ExternalAccountPoolExhaustedError as exc:
            raise GrokAccountPoolExhaustedError(
                f"GROK_ACCOUNT_POOL_EXHAUSTED: No available Grok account: {exc}"
            ) from exc
        self._lease_to_raw_alias.pop(lease.lease_id, None)
        if next_lease is not None:
            self._lease_to_raw_alias[next_lease.lease_id] = pool._require_active_lease(next_lease)
        return next_lease


_GLOBAL_GROK_POOL_MANAGER: Optional[GrokAccountPoolManager] = None


def get_grok_account_pool_manager() -> GrokAccountPoolManager:
    """Return a process-global Grok pool manager bound from machine-local env.

    Raw profile aliases and credential/API keys are never part of the source
    contract; they are read from the local process environment only.
    """

    global _GLOBAL_GROK_POOL_MANAGER
    if _GLOBAL_GROK_POOL_MANAGER is not None:
        return _GLOBAL_GROK_POOL_MANAGER
    accounts: list[GrokAccount] = []
    aliases_str = os.getenv("NEXUS_GROK_ACCOUNT_ALIASES", "").strip()
    if aliases_str:
        for alias in aliases_str.split(","):
            alias = alias.strip()
            if alias:
                home_env_key = f"NEXUS_GROK_HOME_{alias.upper()}"
                home = os.getenv(
                    home_env_key,
                    str(Path.home() / f".grok/profiles/{alias}"),
                )
                accounts.append(GrokAccount(alias=alias, home_dir=home))
    _GLOBAL_GROK_POOL_MANAGER = GrokAccountPoolManager(accounts)
    return _GLOBAL_GROK_POOL_MANAGER


def set_grok_account_pool_manager(
    manager: Optional[GrokAccountPoolManager],
) -> None:
    """Override the process-global manager for tests or bounded local use."""

    global _GLOBAL_GROK_POOL_MANAGER
    _GLOBAL_GROK_POOL_MANAGER = manager
