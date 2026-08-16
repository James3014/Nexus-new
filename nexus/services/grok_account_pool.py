"""Grok account pool manager for provider-scoped credential/profile failover.

This module reuses the provider-neutral request-scoped
:class:`~nexus.services.external_account_pool.ExternalAccountPool` substrate.
It owns Grok-specific account/profile binding only; it does not select route,
provider, or capability and does not introduce a second pool framework.

Public leases expose only a non-secret alias hash and immutable execution
binding data. Raw profile names and any credential material stay machine-local;
lease environments never inherit the ambient process environment.
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from nexus.services.external_account_pool import (
    AccountFailureKind,
    AccountLease,
    ExternalAccountPool,
    ExternalAccountPoolExhaustedError,
    InternalAccountRecord,
    is_rotation_eligible,
)

GROK_SENSITIVE_ENV_KEYS = ("XAI_API_KEY", "GROK_API_KEY", "NEXUS_GROK_API_KEY")

# Only these neutral keys may pass from a caller-supplied base environment into
# an isolated lease environment. The ambient process environment is never
# copied, so unrelated inherited tokens or cloud credentials cannot leak into a
# public lease.
GROK_NEUTRAL_ENV_KEYS = (
    "PATH",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LC_MESSAGES",
    "LC_NUMERIC",
    "LC_TIME",
    "TZ",
    "TERM",
)

GROK_ACCOUNT_POOL_PROVIDER = "grok"


class GrokAccountPoolError(RuntimeError):
    """Base exception for Grok account pool operations."""


class GrokAccountPoolExhaustedError(GrokAccountPoolError):
    """Raised when no active, isolated Grok profile is available in the pool."""


@dataclass
class GrokAccount:
    """One machine-local Grok profile binding.

    ``alias`` is the local profile alias, not a credential. The public lease
    surface carries only ``alias_hash`` derived from the alias. ``cooldown_until``
    is a monotonic-clock deadline; until it elapses, the profile stays
    unavailable after an eligible failure instead of being permanently
    quarantined.
    """

    alias: str
    home_dir: str
    is_active: bool = True
    cooldown_until: Optional[float] = None

    @property
    def alias_hash(self) -> str:
        return hashlib.sha256(self.alias.encode("utf-8")).hexdigest()[:12]


def _isolated_home_dir(home_dir: str, alias_hash: str) -> str:
    """Return a HOME path that never embeds the raw profile alias."""

    home = Path(home_dir)
    return str(home.parent / f"profile-{alias_hash}")


def build_grok_isolated_env(
    home_dir: Optional[str] = None,
    base_env: Optional[Mapping[str, str]] = None,
    alias_hash: Optional[str] = None,
) -> dict[str, str]:
    """Build an isolated environment scoped to one Grok profile.

    Only the explicit neutral allowlist passes through from ``base_env`` (or an
    empty environment when ``base_env`` is omitted), so a swapped profile cannot
    inherit another profile's credential material or arbitrary process secrets.
    When ``alias_hash`` is supplied, ``HOME`` is rewritten to a hash-derived
    binding directory so the raw profile alias never appears in the environment.
    """

    source = {} if base_env is None else dict(base_env)
    env: dict[str, str] = {}
    for key in GROK_NEUTRAL_ENV_KEYS:
        if key in source:
            env[key] = source[key]
    if home_dir:
        if alias_hash:
            env["HOME"] = _isolated_home_dir(home_dir, alias_hash)
        else:
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
        cooldown_seconds: float = 60.0,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._accounts: list[GrokAccount] = list(accounts or [])
        self._manager_path: Optional[str] = manager_path
        self._manager_root: Optional[str] = manager_root
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._pool: Optional[ExternalAccountPool] = None
        self._lease_to_raw_alias: dict[str, str] = {}

    def _now(self) -> float:
        if self._clock is not None:
            return self._clock()
        return time.monotonic()

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
            env = build_grok_isolated_env(
                home_dir=acc.home_dir,
                alias_hash=acc.alias_hash,
            )
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
        now = self._now()
        for acc in self._accounts:
            if not acc.is_active and acc.cooldown_until is not None and now >= acc.cooldown_until:
                acc.is_active = True
                acc.cooldown_until = None
            record = self._pool._accounts.get(acc.alias)
            if record is not None:
                record.is_available = acc.is_active

    def _acquire_from_account(
        self,
        consumer_id: str,
        account: GrokAccount,
    ) -> AccountLease:
        """Acquire a lease pinned to one account without load-based repick."""

        pool = self._ensure_pool()
        record = pool._accounts[account.alias]
        lease_id = f"lease_{uuid.uuid4().hex}"
        lease = AccountLease(
            lease_id=lease_id,
            provider=GROK_ACCOUNT_POOL_PROVIDER,
            consumer_id=str(consumer_id),
            account_alias_hash=account.alias_hash,
            execution_env=record.execution_env,
        )
        record.active_lease_ids.add(lease_id)
        pool._lease_to_account_id[lease_id] = account.alias
        pool._active_leases[lease_id] = lease
        self._lease_to_raw_alias[lease_id] = account.alias
        return lease

    def acquire(self, consumer_id: str) -> AccountLease:
        self._refresh_pool_health()
        pool = self._ensure_pool()
        try:
            lease = pool.acquire(consumer_id)
        except ExternalAccountPoolExhaustedError as exc:
            raise GrokAccountPoolExhaustedError(f"GROK_ACCOUNT_POOL_EXHAUSTED: {exc}") from exc
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
                acc.cooldown_until = self._now() + self._cooldown_seconds
        self._refresh_pool_health()
        pool.release(lease)
        self._lease_to_raw_alias.pop(lease.lease_id, None)

        held_aliases = set(self._lease_to_raw_alias.values())
        candidates = [
            acc
            for acc in self._accounts
            if acc.is_active and acc.alias in pool._accounts and acc.alias not in held_aliases
        ]
        if not candidates:
            raise GrokAccountPoolExhaustedError(
                "GROK_ACCOUNT_POOL_EXHAUSTED: no isolated Grok profile available for failover"
            )
        candidates.sort(key=lambda acc: pool._accounts[acc.alias].load)
        chosen = candidates[0]
        return self._acquire_from_account(lease.consumer_id, chosen)


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
