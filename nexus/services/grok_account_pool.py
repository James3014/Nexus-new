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
import json
import os
import re
import subprocess  # nosec B404 - fixed executable path is invoked without a shell
import threading
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


def classify_grok_failure(
    status: str,
    exit_code: Optional[int],
    stdout: bytes | str = b"",
    stderr: bytes | str = b"",
) -> AccountFailureKind:
    """Classify provider output without treating task failures as account faults."""

    status_text = str(status or "").upper()
    text = "\n".join(
        value.decode("utf-8", errors="replace") if isinstance(value, bytes) else str(value or "")
        for value in (stdout, stderr)
    ).lower()
    normalized_status = status_text.replace("_", " ").lower()
    if "timeout" in normalized_status or "timed out" in normalized_status:
        return AccountFailureKind.TIMEOUT
    if "cancel" in status_text or "cancel" in text:
        return AccountFailureKind.CANCELLED
    if any(
        marker in text
        for marker in ("token refresh failed", "refresh token failed", "refresh failed")
    ):
        return AccountFailureKind.TOKEN_REFRESH_FAILED
    if any(marker in text for marker in ("token expired", "expired token", "session expired")):
        return AccountFailureKind.TOKEN_EXPIRED
    if any(
        marker in text
        for marker in (
            "authentication failed",
            "authentication error",
            "unauthorized",
            "invalid api key",
            "invalid_api_key",
            "session invalid",
            "login required",
            "401",
        )
    ):
        return AccountFailureKind.AUTH_OR_SESSION_INVALID
    if any(marker in text for marker in ("quota", "resource_exhausted", "insufficient_quota")):
        return AccountFailureKind.QUOTA_EXHAUSTED
    if any(marker in text for marker in ("rate limit", "rate_limit", "ratelimit", "429")):
        return AccountFailureKind.RATE_LIMITED
    if any(marker in text for marker in ("account disabled", "account_disabled", "disabled")):
        return AccountFailureKind.ACCOUNT_DISABLED
    if any(
        marker in text
        for marker in ("account unavailable", "service unavailable", "unavailable", "503")
    ):
        return AccountFailureKind.ACCOUNT_UNAVAILABLE
    if "permission" in text or "forbidden" in text or "403" in text:
        return AccountFailureKind.PERMISSION_OR_SCOPE_ERROR
    if "verifier" in text:
        return AccountFailureKind.VERIFIER_FAILED
    if "syntax" in text or "implementation" in text or exit_code == 2:
        return AccountFailureKind.SYNTAX_OR_IMPLEMENTATION_ERROR
    if "model" in text or "task" in text:
        return AccountFailureKind.MODEL_OR_TASK_ERROR
    return AccountFailureKind.UNKNOWN


class GrokAccountPoolError(RuntimeError):
    """Base exception for Grok account pool operations."""


class GrokAccountPoolExhaustedError(GrokAccountPoolError):
    """Raised when no active, isolated Grok profile is available in the pool."""


class GrokAccountPoolLeaseError(GrokAccountPoolError):
    """Raised when a lease is not the active capability issued by this manager."""


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


@dataclass(frozen=True)
class GrokAttemptLineage:
    """Immutable, pool-only public evidence for one Grok account attempt."""

    provider: str
    consumer_id: str
    attempt: int
    account_alias_hash: Optional[str]
    failure_kind: Optional[AccountFailureKind]
    previous_lease_id: Optional[str]
    previous_account_alias_hash: Optional[str]
    replacement_lease_id: Optional[str]
    replacement_account_alias_hash: Optional[str]
    outcome: str

    def __post_init__(self) -> None:
        if self.provider != GROK_ACCOUNT_POOL_PROVIDER:
            raise GrokAccountPoolError("GROK_LINEAGE_PROVIDER_MISMATCH")
        if self.attempt < 1:
            raise GrokAccountPoolError("GROK_LINEAGE_ATTEMPT_INVALID")
        for value in (
            self.account_alias_hash,
            self.previous_account_alias_hash,
            self.replacement_account_alias_hash,
        ):
            if value is not None and _ALIAS_HASH_RE.fullmatch(value) is None:
                raise GrokAccountPoolError("GROK_LINEAGE_ALIAS_HASH_INVALID")

    def to_public_dict(self) -> dict[str, Any]:
        """Project only non-secret pool evidence; no environment or raw output."""

        return {
            "provider": self.provider,
            "consumer_id": self.consumer_id,
            "attempt": self.attempt,
            "account_alias_hash": self.account_alias_hash,
            "failure_kind": self.failure_kind.value if self.failure_kind is not None else None,
            "previous_lease_id": self.previous_lease_id,
            "previous_account_alias_hash": self.previous_account_alias_hash,
            "replacement_lease_id": self.replacement_lease_id,
            "replacement_account_alias_hash": self.replacement_account_alias_hash,
            "outcome": self.outcome,
        }

    def serialize_public(self) -> str:
        return json.dumps(self.to_public_dict(), sort_keys=True, separators=(",", ":"))


_ALIAS_HASH_RE = re.compile(r"^[0-9a-f]{12}$")


def _isolated_home_dir(
    home_dir: Optional[str],
    alias_hash: str,
    isolated_root: Optional[str] = None,
) -> str:
    """Return a hash-only HOME under a neutral configured root.

    ``home_dir`` is intentionally ignored for derivation: profile paths may
    contain raw aliases in any parent component. The configured root is the
    only path authority for the public environment binding.
    """

    if not isinstance(alias_hash, str) or _ALIAS_HASH_RE.fullmatch(alias_hash) is None:
        raise GrokAccountPoolError("GROK_ALIAS_HASH_REQUIRED")
    configured_root = isolated_root or os.getenv("NEXUS_GROK_ISOLATED_ROOT", "").strip()
    root = (
        Path(configured_root).expanduser()
        if configured_root
        else Path.home() / ".nexus/grok-account-pool/profiles"
    )
    if not root.is_absolute():
        raise GrokAccountPoolError("GROK_ISOLATED_ROOT_MUST_BE_ABSOLUTE")
    return str(root / f"profile-{alias_hash}")


def build_grok_isolated_env(
    home_dir: Optional[str] = None,
    base_env: Optional[Mapping[str, str]] = None,
    alias_hash: Optional[str] = None,
    isolated_root: Optional[str] = None,
) -> dict[str, str]:
    """Build an isolated environment scoped to one Grok profile.

    Only the explicit neutral allowlist passes through from ``base_env`` (or an
    empty environment when ``base_env`` is omitted), so a swapped profile cannot
    inherit another profile's credential material or arbitrary process secrets.
    ``alias_hash`` is mandatory whenever a profile HOME is requested. HOME is
    always derived under a neutral configured root; the raw profile path is
    never used as a fallback.
    """

    source = {} if base_env is None else dict(base_env)
    env: dict[str, str] = {}
    for key in GROK_NEUTRAL_ENV_KEYS:
        if key in source:
            env[key] = source[key]
    if home_dir is not None or alias_hash is not None:
        env["HOME"] = _isolated_home_dir(home_dir, alias_hash or "", isolated_root)
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
        isolated_root: Optional[str] = None,
    ) -> None:
        self._accounts: list[GrokAccount] = list(accounts or [])
        self._manager_path: Optional[str] = manager_path
        self._manager_root: Optional[str] = manager_root
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._isolated_root = isolated_root
        self._lock = threading.RLock()
        self._pool: Optional[ExternalAccountPool] = None
        self._lease_to_raw_alias: dict[str, str] = {}
        self._active_leases: dict[str, AccountLease] = {}
        self._consumer_to_lease: dict[str, str] = {}
        self._lineage_by_consumer: dict[str, list[GrokAttemptLineage]] = {}

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
        cmd = [mgr, "--root", root] + args
        try:
            # ``mgr`` is an existing file; argv is a list and shell execution
            # is disabled, with a bounded timeout.
            res = subprocess.run(  # nosec B603 - validated executable and argv list
                cmd,
                capture_output=True,
                text=True,
                timeout=30.0,
                shell=False,
            )
        except Exception as exc:
            raise GrokAccountPoolError("Failed to execute grok-cli-manager") from exc
        if res.returncode != 0:
            raise GrokAccountPoolError(f"grok-cli-manager failed with exit code {res.returncode}")
        if not expect_json:
            return res.stdout
        try:
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
                isolated_root=self._isolated_root,
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
        self._active_leases[lease_id] = lease
        self._consumer_to_lease[str(consumer_id)] = lease_id
        return lease

    def _require_owned_active_lease(self, lease: AccountLease) -> None:
        lease_id = getattr(lease, "lease_id", None)
        if not isinstance(lease_id, str):
            raise GrokAccountPoolLeaseError(
                "GROK_INVALID_ACCOUNT_LEASE: lease is not the active capability "
                "issued by this manager"
            )
        owned = self._active_leases.get(lease_id)
        if owned is not lease:
            raise GrokAccountPoolLeaseError(
                "GROK_INVALID_ACCOUNT_LEASE: lease is not the active capability "
                "issued by this manager"
            )

    def _record_lineage(
        self,
        *,
        consumer_id: str,
        account_alias_hash: Optional[str],
        failure_kind: Optional[AccountFailureKind],
        previous_lease_id: Optional[str],
        previous_account_alias_hash: Optional[str],
        replacement_lease_id: Optional[str],
        replacement_account_alias_hash: Optional[str],
        outcome: str,
    ) -> GrokAttemptLineage:
        records = self._lineage_by_consumer.setdefault(str(consumer_id), [])
        record = GrokAttemptLineage(
            provider=GROK_ACCOUNT_POOL_PROVIDER,
            consumer_id=str(consumer_id),
            attempt=len(records) + 1,
            account_alias_hash=account_alias_hash,
            failure_kind=failure_kind,
            previous_lease_id=previous_lease_id,
            previous_account_alias_hash=previous_account_alias_hash,
            replacement_lease_id=replacement_lease_id,
            replacement_account_alias_hash=replacement_account_alias_hash,
            outcome=outcome,
        )
        records.append(record)
        return record

    def get_attempt_lineage(
        self,
        consumer_id: Optional[str] = None,
        lease_id: Optional[str] = None,
    ) -> tuple[GrokAttemptLineage, ...]:
        """Return immutable snapshots filtered by consumer and/or lease."""

        with self._lock:
            consumers = (
                [str(consumer_id)] if consumer_id is not None else sorted(self._lineage_by_consumer)
            )
            records = [
                record
                for consumer in consumers
                for record in self._lineage_by_consumer.get(consumer, ())
            ]
            if lease_id is not None:
                records = [
                    record
                    for record in records
                    if lease_id
                    in {
                        record.previous_lease_id,
                        record.replacement_lease_id,
                    }
                ]
            return tuple(records)

    def get_public_attempt_lineage(
        self,
        consumer_id: Optional[str] = None,
        lease_id: Optional[str] = None,
    ) -> tuple[Mapping[str, Any], ...]:
        """Return detached public projections, never manager-owned mappings."""

        return tuple(
            record.to_public_dict() for record in self.get_attempt_lineage(consumer_id, lease_id)
        )

    def acquire(self, consumer_id: str) -> AccountLease:
        with self._lock:
            consumer = str(consumer_id)
            if consumer in self._consumer_to_lease:
                raise GrokAccountPoolError("GROK_CONSUMER_ALREADY_BOUND")
            self._refresh_pool_health()
            pool = self._ensure_pool()
            try:
                lease = pool.acquire(consumer)
            except ExternalAccountPoolExhaustedError as exc:
                self._record_lineage(
                    consumer_id=consumer,
                    account_alias_hash=None,
                    failure_kind=None,
                    previous_lease_id=None,
                    previous_account_alias_hash=None,
                    replacement_lease_id=None,
                    replacement_account_alias_hash=None,
                    outcome="EXHAUSTED",
                )
                raise GrokAccountPoolExhaustedError(f"GROK_ACCOUNT_POOL_EXHAUSTED: {exc}") from exc
            self._lease_to_raw_alias[lease.lease_id] = pool._require_active_lease(lease)
            self._active_leases[lease.lease_id] = lease
            self._consumer_to_lease[consumer] = lease.lease_id
            self._record_lineage(
                consumer_id=consumer,
                account_alias_hash=lease.account_alias_hash,
                failure_kind=None,
                previous_lease_id=None,
                previous_account_alias_hash=None,
                replacement_lease_id=None,
                replacement_account_alias_hash=None,
                outcome="ACQUIRED",
            )
            return lease

    def release(self, lease: AccountLease) -> None:
        with self._lock:
            self._require_owned_active_lease(lease)
            pool = self._ensure_pool()
            pool.release(lease)
            self._lease_to_raw_alias.pop(lease.lease_id, None)
            self._active_leases.pop(lease.lease_id, None)
            if self._consumer_to_lease.get(lease.consumer_id) == lease.lease_id:
                self._consumer_to_lease.pop(lease.consumer_id, None)
            self._record_lineage(
                consumer_id=lease.consumer_id,
                account_alias_hash=lease.account_alias_hash,
                failure_kind=None,
                previous_lease_id=lease.lease_id,
                previous_account_alias_hash=lease.account_alias_hash,
                replacement_lease_id=None,
                replacement_account_alias_hash=None,
                outcome="RELEASED",
            )

    def report_failure(
        self,
        lease: AccountLease,
        failure_kind: AccountFailureKind,
    ) -> Optional[AccountLease]:
        with self._lock:
            self._require_owned_active_lease(lease)
            self._refresh_pool_health()
            pool = self._ensure_pool()
            if not is_rotation_eligible(failure_kind):
                self._record_lineage(
                    consumer_id=lease.consumer_id,
                    account_alias_hash=lease.account_alias_hash,
                    failure_kind=failure_kind,
                    previous_lease_id=lease.lease_id,
                    previous_account_alias_hash=lease.account_alias_hash,
                    replacement_lease_id=None,
                    replacement_account_alias_hash=None,
                    outcome="NO_ROTATION",
                )
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
            self._active_leases.pop(lease.lease_id, None)
            self._consumer_to_lease.pop(lease.consumer_id, None)

            held_aliases = set(self._lease_to_raw_alias.values())
            candidates = [
                acc
                for acc in self._accounts
                if acc.is_active and acc.alias in pool._accounts and acc.alias not in held_aliases
            ]
            if not candidates:
                self._record_lineage(
                    consumer_id=lease.consumer_id,
                    account_alias_hash=lease.account_alias_hash,
                    failure_kind=failure_kind,
                    previous_lease_id=lease.lease_id,
                    previous_account_alias_hash=lease.account_alias_hash,
                    replacement_lease_id=None,
                    replacement_account_alias_hash=None,
                    outcome="EXHAUSTED",
                )
                raise GrokAccountPoolExhaustedError(
                    "GROK_ACCOUNT_POOL_EXHAUSTED: no isolated Grok profile available for failover"
                )
            candidates.sort(key=lambda acc: pool._accounts[acc.alias].load)
            chosen = candidates[0]
            replacement = self._acquire_from_account(lease.consumer_id, chosen)
            self._record_lineage(
                consumer_id=lease.consumer_id,
                account_alias_hash=replacement.account_alias_hash,
                failure_kind=failure_kind,
                previous_lease_id=lease.lease_id,
                previous_account_alias_hash=lease.account_alias_hash,
                replacement_lease_id=replacement.lease_id,
                replacement_account_alias_hash=replacement.account_alias_hash,
                outcome="ROTATED",
            )
            return replacement


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
