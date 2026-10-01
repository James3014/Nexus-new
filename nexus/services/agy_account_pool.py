"""AGY Account Pool Manager for governed multi-account failover and isolation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

from nexus.services.external_account_pool import (
    AccountFailureKind,
    AccountLease,
    ExternalAccountPool,
    InternalAccountRecord,
    InvalidAccountLeaseError,
    is_rotation_eligible,
)

# GitHub credential keys are stripped from every worker execution environment
# so a delegated worker never inherits a broad Owner GitHub credential that
# could be interpreted as external-publication authority.
AGY_ACCOUNT_PREFERENCE_TIERS_VERSION = 3

GITHUB_CREDENTIAL_KEYS = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN",
    "GITHUB_PAT",
    "GITHUB_ACTIONS_TOKEN",
)

SENSITIVE_API_KEYS = (
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENAI_API_KEY",
) + GITHUB_CREDENTIAL_KEYS


SUPPORTED_AGY_MODEL_FAMILIES = frozenset({"gemini", "claude_gpt"})
MODEL_FAMILY_SCOPED_FAILURES = frozenset({
    AccountFailureKind.QUOTA_EXHAUSTED,
})
DEFAULT_FAMILY_UNAVAILABLE_TTL_SECONDS = 300.0


class AgyAccountPoolError(RuntimeError):
    """Base exception for AGY Account Pool operations."""


class AgyAccountPoolExhaustedError(AgyAccountPoolError):
    """Raised when no active account is available in the pool."""


class AgyAccountPoolBusyError(AgyAccountPoolError):
    """Raised when all active accounts are currently locked/leased across processes."""


class AgyAccountPoolManagerError(AgyAccountPoolError):
    """Raised when the account pool manager CLI fails or returns invalid data."""


def is_agy_rotation_eligible(failure_kind: AccountFailureKind) -> bool:
    """Agy provider timeouts cool down the current account before another attempt."""
    return failure_kind == AccountFailureKind.TIMEOUT or is_rotation_eligible(failure_kind)


@dataclass
class AccountLeaseClaim:
    """Exclusive cross-process lease claim on one account.

    Maintains an exclusive OS-level flock on the account's lock file
    for the entire duration of the worker's execution.
    """

    lease: AccountLease
    lock_file_obj: Any
    lock_path: Path
    receipt_path: Path
    account_alias_hash: str
    lease_id_hash: str
    manager: Any
    internal_id: str
    released: bool = False

    def release(self) -> None:
        """Release the per-account exclusive lock, durable receipt, and manager lease."""
        if self.released:
            return
        self.released = True
        try:
            if self.receipt_path.exists():
                self.receipt_path.unlink()
        except OSError:
            pass
        try:
            if self.lock_file_obj:
                import fcntl

                fcntl.flock(self.lock_file_obj.fileno(), fcntl.LOCK_UN)
                self.lock_file_obj.close()
        except OSError:
            pass
        try:
            self.manager.release(self.lease)
        except Exception:
            pass

    def __enter__(self) -> AccountLeaseClaim:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


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


def _ensure_macos_isolated_keychain(home_dir: str) -> None:
    """Give an isolated AGY HOME its own default keychain on macOS."""
    if sys.platform != "darwin":
        return
    security = shutil.which("security")
    if not security:
        raise AgyAccountPoolManagerError("AGY_KEYCHAIN_SECURITY_TOOL_MISSING")

    home = Path(home_dir)
    if not home.is_dir():
        raise AgyAccountPoolManagerError(f"AGY_KEYCHAIN_HOME_MISSING:{home}")

    keychains_dir = home / "Library" / "Keychains"
    prefs_dir = home / "Library" / "Preferences"
    keychains_dir.mkdir(parents=True, exist_ok=True)
    prefs_dir.mkdir(parents=True, exist_ok=True)
    keychain = keychains_dir / "agy.keychain-db"
    env = dict(os.environ)
    env["HOME"] = str(home)

    def run(*args: str) -> None:
        proc = subprocess.run(
            [security, *args],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or "").strip().replace("\n", " ")[:240]
            raise AgyAccountPoolManagerError(
                f"AGY_KEYCHAIN_SETUP_FAILED:{args[0]}:{proc.returncode}:{detail}"
            )

    if not keychain.exists():
        run("create-keychain", "-p", "", str(keychain))
        try:
            keychain.chmod(0o600)
        except OSError:
            pass
    run("unlock-keychain", "-p", "", str(keychain))
    run("set-keychain-settings", str(keychain))
    run("default-keychain", "-s", str(keychain))
    run("list-keychains", "-s", str(keychain), "/Library/Keychains/System.keychain")


def _is_populated_runtime(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    state_json = path / "state.json"
    if state_json.exists() and state_json.is_file():
        try:
            data = json.loads(state_json.read_text(encoding="utf-8"))
            accounts = data.get("accounts")
            if isinstance(accounts, dict) and len(accounts) > 0:
                return True
            if isinstance(accounts, list) and len(accounts) > 0:
                return True
        except Exception:
            pass
    accounts_dir = path / "accounts"
    if accounts_dir.exists() and accounts_dir.is_dir():
        try:
            subdirs = [x for x in accounts_dir.iterdir() if x.is_dir()]
            if len(subdirs) > 0:
                return True
        except Exception:
            pass
    return False


class AgyAccountPoolManager:
    """Manages rotation, active account state, and isolated HOME environments for AGY workers."""

    def __init__(
        self,
        accounts: Optional[Sequence[AgyAccount]] = None,
        manager_path: Optional[str] = None,
        manager_root: Optional[str] = None,
        use_real_manager: Optional[bool] = None,
    ):
        self._accounts: list[AgyAccount] = list(accounts or [])
        self._active_index: int = 0 if self._accounts else -1
        self._manager_path: Optional[str] = manager_path
        self._manager_root: Optional[str] = manager_root

        if use_real_manager is not None:
            self._use_real_manager = use_real_manager
        else:
            resolved_mgr = self.resolve_manager_path(manager_path)
            self._use_real_manager = bool(
                resolved_mgr and Path(resolved_mgr).is_file() and accounts is None
            )

        if self._use_real_manager:
            if not self._manager_path:
                self._manager_path = self.resolve_manager_path(manager_path)
            if not self._manager_root:
                self._manager_root = self.resolve_manager_root(manager_root, self._manager_path)

        self._pool: Optional[ExternalAccountPool] = None
        self._lease_to_raw_alias: dict[str, str] = {}

    @staticmethod
    def resolve_manager_path(override_path: Optional[str] = None) -> Optional[str]:
        if override_path:
            p = Path(override_path).expanduser()
            return str(p.resolve()) if p.exists() else str(p)
        env_path = os.getenv("NEXUS_AGY_ACCOUNT_POOL_MANAGER_PATH", "").strip()
        if env_path:
            p = Path(env_path).expanduser()
            return str(p.resolve()) if p.exists() else str(p)

        # Resolve the manager from the current process HOME.  The AGY
        # credential HOME is only applied to the provider subprocess; it must
        # never make a user-specific host path part of the source contract.
        default_path = Path.home() / ".nexus/agy-account-pool/bin/agy-cli-manager"
        return str(default_path.resolve()) if default_path.exists() else str(default_path)

    @staticmethod
    def resolve_manager_root(
        override_root: Optional[str] = None, manager_path: Optional[str] = None
    ) -> str:
        if override_root:
            p = Path(override_root).expanduser()
            return str(p.resolve()) if p.exists() else str(p)
        env_root = os.getenv("NEXUS_AGY_ACCOUNT_POOL_ROOT", "").strip()
        if env_root:
            p = Path(env_root).expanduser()
            return str(p.resolve()) if p.exists() else str(p)

        derived_from_mgr: Optional[Path] = None
        mgr_p = manager_path or AgyAccountPoolManager.resolve_manager_path()
        if mgr_p:
            p = Path(mgr_p).expanduser()
            if p.name == "agy-cli-manager" and p.parent.name == "bin":
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
            if _is_populated_runtime(derived_from_mgr) or manager_path is not None:
                return (
                    str(derived_from_mgr.resolve())
                    if derived_from_mgr.exists()
                    else str(derived_from_mgr)
                )

        candidates = [Path.home() / ".nexus/agy-account-pool/runtime"]

        for cand in candidates:
            if _is_populated_runtime(cand):
                return str(cand.resolve())

        for cand in candidates:
            if cand.exists():
                return str(cand.resolve())

        if derived_from_mgr:
            return (
                str(derived_from_mgr.resolve())
                if derived_from_mgr.exists()
                else str(derived_from_mgr)
            )

        fallback_root = Path.home() / ".nexus/agy-account-pool/runtime"
        return str(fallback_root.resolve()) if fallback_root.exists() else str(fallback_root)

    def _call_manager_cli(self, args: list[str], expect_json: bool = True) -> Any:
        mgr = self._manager_path or self.resolve_manager_path()
        if not mgr or not Path(mgr).is_file():
            raise AgyAccountPoolManagerError("AGY account pool manager binary not found")
        root = self._manager_root or self.resolve_manager_root(manager_path=mgr)
        import subprocess

        cmd = [mgr, "--root", root] + args
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30.0)
        except Exception as exc:
            raise AgyAccountPoolManagerError("Failed to execute agy-cli-manager") from exc

        if res.returncode != 0:
            raise AgyAccountPoolManagerError(
                f"agy-cli-manager failed with exit code {res.returncode}"
            )
        if not expect_json:
            return res.stdout
        try:
            return json.loads(res.stdout)
        except json.JSONDecodeError as exc:
            raise AgyAccountPoolManagerError("Invalid JSON returned by agy-cli-manager") from exc

    def _sync_real_active_account(self) -> AgyAccount:
        data = self._call_manager_cli(["ensure-active", "--json"])
        active_name = data.get("active") or data.get("switched_to")
        if not active_name:
            raise AgyAccountPoolExhaustedError(
                "AGY_ACCOUNT_POOL_EXHAUSTED: No active AGY account available"
            )

        status = self._call_manager_cli(["status", "--json"])
        if not active_name:
            active_name = status.get("active")
        if not active_name:
            raise AgyAccountPoolExhaustedError(
                "AGY_ACCOUNT_POOL_EXHAUSTED: No active AGY account available"
            )

        live_dir_str = status.get("live_dir")
        if not live_dir_str:
            raise AgyAccountPoolManagerError(
                "Active account live_dir is missing from manager status"
            )

        live_dir_path = Path(live_dir_str)
        if not live_dir_path.is_absolute() or not live_dir_path.is_dir():
            raise AgyAccountPoolManagerError(
                "Active account live_dir is not an absolute existing directory"
            )

        # Resolve request lease using provider-owned immutable account snapshot HOME
        mgr_root = self._manager_root or status.get("root")
        if mgr_root:
            snapshot_home = Path(mgr_root) / "accounts" / active_name
            if snapshot_home.is_dir():
                account_home = snapshot_home.resolve()
            else:
                account_home = live_dir_path.parent.resolve()
        else:
            account_home = live_dir_path.parent.resolve()

        if not account_home.is_dir():
            raise AgyAccountPoolManagerError("Active account HOME does not exist")

        acc = AgyAccount(alias=active_name, home_dir=str(account_home))
        self._accounts = [acc]
        self._active_index = 0
        return acc

    @property
    def active_account(self) -> Optional[AgyAccount]:
        if 0 <= self._active_index < len(self._accounts):
            return self._accounts[self._active_index]
        if self._use_real_manager:
            try:
                return self.ensure_active()
            except AgyAccountPoolError:
                return None
        return None

    @property
    def active_account_alias_hash(self) -> Optional[str]:
        account = self.active_account
        return account.alias_hash if account else None

    def ensure_active(self, target_worktree: Optional[str] = None) -> AgyAccount:
        if self._use_real_manager:
            return self._sync_real_active_account()

        account = self.active_account
        if account is None or not account.is_active:
            raise AgyAccountPoolExhaustedError("No active AGY account available")
        return account

    def get_active_account(self) -> Optional[AgyAccount]:
        return self.active_account

    def rotate_account(
        self,
        reason: str = "failover",
        failed_account_hash: Optional[str] = None,
    ) -> AgyAccount:
        if self._use_real_manager:
            failed_alias = None
            if failed_account_hash and self._accounts:
                for acc in self._accounts:
                    if acc.alias_hash == failed_account_hash:
                        failed_alias = acc.alias
                        break

            if failed_alias:
                # Mark only the exact failed account as bad
                self._call_manager_cli(["mark-bad", failed_alias, "--reason", reason])
                data = self._call_manager_cli(["ensure-active", "--json"])
            else:
                data = self._call_manager_cli([
                    "rotate-after-failure",
                    "--reason",
                    reason,
                    "--json",
                ])

            new_active = data.get("switched_to") or data.get("active")
            outcome = data.get("outcome")
            if not new_active or outcome in ("no_active_account", "marked_bad_no_standby"):
                self._accounts = []
                self._active_index = -1
                raise AgyAccountPoolExhaustedError(
                    "AGY_ACCOUNT_POOL_EXHAUSTED: No available AGY accounts remaining in pool"
                )
            return self._sync_real_active_account()

        if not self._accounts:
            raise AgyAccountPoolExhaustedError("No AGY accounts registered in pool")

        if failed_account_hash:
            for acc in self._accounts:
                if acc.alias_hash == failed_account_hash:
                    acc.is_active = False
        else:
            start_idx = self._active_index
            if 0 <= start_idx < len(self._accounts):
                self._accounts[start_idx].is_active = False

        start_idx = self._active_index
        next_idx = (start_idx + 1) % len(self._accounts) if start_idx >= 0 else 0
        visited = 0
        while visited < len(self._accounts):
            if self._accounts[next_idx].is_active:
                self._active_index = next_idx
                return self._accounts[next_idx]
            next_idx = (next_idx + 1) % len(self._accounts)
            visited += 1

        self._active_index = -1
        raise AgyAccountPoolExhaustedError("No available AGY accounts remaining in pool")

    def build_isolated_env(self, base_env: Optional[dict[str, str]] = None) -> dict[str, str]:
        account = self.active_account
        home_dir = account.home_dir if account else None
        return build_isolated_env(home_dir=home_dir, base_env=base_env)

    def _ensure_pool(self) -> ExternalAccountPool:
        if self._pool is not None:
            return self._pool

        records = []
        if self._use_real_manager:
            mgr = self._manager_path or self.resolve_manager_path()
            root = self._manager_root or self.resolve_manager_root(manager_path=mgr)
            try:
                self._call_manager_cli(["ensure-active", "--json"])
                status = self._call_manager_cli(["status", "--json"])
            except Exception as exc:
                raise AgyAccountPoolError(f"Failed to get manager status: {exc}")

            accounts_data = status.get("accounts") or {}

            # Support both dict and list response schema
            accounts_list = []
            if isinstance(accounts_data, dict):
                for name, info in accounts_data.items():
                    accounts_list.append((name, info))
            elif isinstance(accounts_data, list):
                for info in accounts_data:
                    name = info.get("name")
                    if name:
                        accounts_list.append((name, info))

            for name, info in accounts_list:
                if info.get("enabled") is True:
                    snapshot_dir = Path(root) / "accounts" / name
                    is_avail = False
                    if snapshot_dir.is_dir():
                        cooldown_val = info.get("cooldown_until")
                        is_cooldown = False
                        if cooldown_val:
                            try:
                                from datetime import datetime, timezone

                                cooldown_str = str(cooldown_val).replace("Z", "+00:00")
                                dt = datetime.fromisoformat(cooldown_str)
                                if dt > datetime.now(timezone.utc):
                                    is_cooldown = True
                            except Exception:
                                is_cooldown = True
                        if not is_cooldown:
                            if "identity" not in info:
                                is_avail = True
                            else:
                                ident = info.get("identity") or {}
                                if (
                                    ident.get("account_name")
                                    and ident.get("source") != "unavailable"
                                ):
                                    is_avail = True

                    _ensure_macos_isolated_keychain(str(snapshot_dir))
                    env = build_isolated_env(home_dir=str(snapshot_dir))
                    h = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
                    records.append(
                        InternalAccountRecord(
                            internal_id=name,
                            alias_hash=h,
                            execution_env=env,
                            is_available=is_avail,
                        )
                    )
        else:
            for acc in self._accounts:
                env = build_isolated_env(home_dir=acc.home_dir)
                records.append(
                    InternalAccountRecord(
                        internal_id=acc.alias,
                        alias_hash=acc.alias_hash,
                        execution_env=env,
                        is_available=acc.is_active,
                    )
                )

        self._pool = ExternalAccountPool(provider="agy", accounts=records)
        return self._pool

    def _refresh_pool_health(self) -> None:
        if self._pool is None:
            self._ensure_pool()
            return

        if not self._use_real_manager:
            for acc in self._accounts:
                record = self._pool._accounts.get(acc.alias)
                if record is not None:
                    record.is_available = acc.is_active
            return

        mgr = self._manager_path or self.resolve_manager_path()
        root = self._manager_root or self.resolve_manager_root(manager_path=mgr)
        try:
            self._call_manager_cli(["ensure-active", "--json"])
            status = self._call_manager_cli(["status", "--json"])
        except Exception as exc:
            raise AgyAccountPoolError(f"Failed to get manager status during refresh: {exc}")

        accounts_data = status.get("accounts") or {}
        accounts_list = []
        if isinstance(accounts_data, dict):
            for name, info in accounts_data.items():
                accounts_list.append((name, info))
        elif isinstance(accounts_data, list):
            for info in accounts_data:
                name = info.get("name")
                if name:
                    accounts_list.append((name, info))

        for name, info in accounts_list:
            record = self._pool._accounts.get(name)
            snapshot_dir = Path(root) / "accounts" / name
            is_avail = False
            if info.get("enabled") is True and snapshot_dir.is_dir():
                cooldown_val = info.get("cooldown_until")
                is_cooldown = False
                if cooldown_val:
                    try:
                        from datetime import datetime, timezone

                        cooldown_str = str(cooldown_val).replace("Z", "+00:00")
                        dt = datetime.fromisoformat(cooldown_str)
                        if dt > datetime.now(timezone.utc):
                            is_cooldown = True
                    except Exception:
                        is_cooldown = True
                if not is_cooldown:
                    if "identity" not in info:
                        is_avail = True
                    else:
                        ident = info.get("identity") or {}
                        if ident.get("account_name") and ident.get("source") != "unavailable":
                            is_avail = True

            if record is not None:
                record.is_available = is_avail
            else:
                _ensure_macos_isolated_keychain(str(snapshot_dir))
                env = build_isolated_env(home_dir=str(snapshot_dir))
                h = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
                new_rec = InternalAccountRecord(
                    internal_id=name,
                    alias_hash=h,
                    execution_env=env,
                    is_available=is_avail,
                )
                self._pool.register_account(new_rec)

    def acquire(self, consumer_id: str) -> AccountLease:
        # Trigger ensure_active and build_isolated_env to respect subclass overrides
        try:
            self.ensure_active()
            self.build_isolated_env()
        except Exception:
            pass
        self._refresh_pool_health()
        pool = self._ensure_pool()
        lease = pool.acquire(consumer_id)
        self._lease_to_raw_alias[lease.lease_id] = pool._require_active_lease(lease)
        return lease

    def release(self, lease: AccountLease) -> None:
        # Releasing an already-issued request lease is local lifecycle cleanup.
        # Do not make it depend on a provider control-plane refresh: a transient
        # manager outage must not leak the neutral lease or its private binding.
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
        failed_alias = self._lease_to_raw_alias.get(lease.lease_id)
        if failed_alias is None:
            try:
                failed_alias = pool._require_active_lease(lease)
            except InvalidAccountLeaseError:
                return None

        if is_rotation_eligible(failure_kind):
            if self._use_real_manager:
                # Execute mark-bad without parsing as JSON and propagate errors
                self._call_manager_cli(
                    ["mark-bad", failed_alias, "--reason", failure_kind.value], expect_json=False
                )
            else:
                for acc in self._accounts:
                    if acc.alias == failed_alias:
                        acc.is_active = False

            # Refresh local pool health after mutating vendor status to ensure status updates are reflected
            self._refresh_pool_health()

            next_lease = pool.report_failure(lease, failure_kind)
            # Remove old mapping from mapping database
            self._lease_to_raw_alias.pop(lease.lease_id, None)
            if next_lease is not None:
                new_alias = pool._require_active_lease(next_lease)
                self._lease_to_raw_alias[next_lease.lease_id] = new_alias
            return next_lease
        return None

    def mark_account_bad(
        self,
        lease: AccountLease,
        failure_kind: AccountFailureKind,
    ) -> bool:
        """Mark one account unavailable and report whether provider-manager state was durably persisted.

        In-memory managers return False so cross-process callers know they still need a
        host-local durable quarantine. Real-manager success returns True.
        """
        failed_alias = self._lease_to_raw_alias.get(lease.lease_id)
        if failed_alias is None and self._pool:
            try:
                failed_alias = self._pool._require_active_lease(lease)
            except Exception:
                pass

        if failed_alias is None and self._pool:
            for acc_id, record in self._pool._accounts.items():
                if record.alias_hash == lease.account_alias_hash:
                    failed_alias = acc_id
                    break

        if failed_alias is None and self._accounts:
            for acc in self._accounts:
                if acc.alias_hash == lease.account_alias_hash:
                    failed_alias = acc.alias
                    break

        for acc in self._accounts:
            if (
                failed_alias and acc.alias == failed_alias
            ) or acc.alias_hash == lease.account_alias_hash:
                acc.is_active = False

        if self._pool:
            for acc_id, record in self._pool._accounts.items():
                if (
                    failed_alias and acc_id == failed_alias
                ) or record.alias_hash == lease.account_alias_hash:
                    record.is_available = False

        manager_persisted = False
        if self._use_real_manager:
            if not failed_alias:
                raise AgyAccountPoolManagerError(
                    f"Cannot mark account bad: alias for hash {lease.account_alias_hash} not found"
                )
            self._call_manager_cli(
                ["mark-bad", failed_alias, "--reason", failure_kind.value], expect_json=False
            )
            manager_persisted = True

        try:
            self._refresh_pool_health()
        except Exception:
            pass
        return manager_persisted


class CrossProcessLeaseCoordinator:
    """Coordinates cross-process exclusive account leases.

    Implements the two-tier lock topology:
    1. Short-lived allocator lock (~/.nexus/agy-account-pool/allocator.lock):
       held ONLY during health refresh, inspecting claimed accounts, selecting one free healthy
       account, atomically claiming the per-account lock, and recording the durable lease receipt.
       Immediately unlocked.
    2. Per-account exclusive lock (~/.nexus/agy-account-pool/leases/<account_alias_hash>.lock):
       held exclusively by the worker process while running Agy. Released upon completion/error.
    """

    def __init__(
        self,
        manager: AgyAccountPoolManager,
        allocator_lock_path: Optional[Path] = None,
        leases_dir: Optional[Path] = None,
        poll_interval: float = 0.2,
        default_wait_timeout: float = 15.0,
    ):
        self.manager = manager

        env_alloc = os.getenv("NEXUS_AGY_ALLOCATOR_LOCK_PATH")
        if allocator_lock_path is not None:
            self.allocator_lock_path = Path(allocator_lock_path).resolve()
        elif env_alloc:
            self.allocator_lock_path = Path(env_alloc).expanduser().resolve()
        else:
            mgr_root = Path(manager._manager_root or AgyAccountPoolManager.resolve_manager_root())
            base_dir = mgr_root.parent if mgr_root.name == "runtime" else mgr_root
            self.allocator_lock_path = base_dir / "allocator.lock"

        env_leases = os.getenv("NEXUS_AGY_LEASES_DIR")
        if leases_dir is not None:
            self.leases_dir = Path(leases_dir).resolve()
        elif env_leases:
            self.leases_dir = Path(env_leases).expanduser().resolve()
        else:
            mgr_root = Path(manager._manager_root or AgyAccountPoolManager.resolve_manager_root())
            base_dir = mgr_root.parent if mgr_root.name == "runtime" else mgr_root
            self.leases_dir = base_dir / "leases"

        self.poll_interval = poll_interval
        self.default_wait_timeout = default_wait_timeout

    def _family_unavailable_path(self, account_alias_hash: str, model_family: str) -> Path:
        if model_family not in SUPPORTED_AGY_MODEL_FAMILIES:
            raise ValueError(f"Unsupported Agy model family: {model_family}")
        return self.leases_dir / (f"{account_alias_hash}.family-unavailable.{model_family}.json")

    def mark_family_unavailable(
        self,
        account_alias_hash: str,
        *,
        model_family: str,
        reason: str,
        unavailable_until: float | None = None,
        claim: Optional[AccountLeaseClaim] = None,
    ) -> Path:
        """Durably block one account only for one model family across processes."""
        import time

        self.leases_dir.mkdir(parents=True, exist_ok=True)
        now = time.time()
        until = (
            float(unavailable_until)
            if unavailable_until is not None and float(unavailable_until) > now
            else now + DEFAULT_FAMILY_UNAVAILABLE_TTL_SECONDS
        )
        path = self._family_unavailable_path(account_alias_hash, model_family)
        payload = {
            "account_alias_hash": account_alias_hash,
            "model_family": model_family,
            "reason": reason,
            "unavailable_at": now,
            "unavailable_until": until,
            "lease_id_hash": claim.lease_id_hash if claim else "none",
            "consumer_id": claim.lease.consumer_id if claim else "unknown",
            "pid": os.getpid(),
        }
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
        try:
            tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
        return path

    def get_family_unavailable_hashes(
        self,
        model_family: str | None,
        *,
        now_ts: float | None = None,
    ) -> set[str]:
        """Return active family-scoped blocks, pruning expired markers."""
        import time

        if model_family not in SUPPORTED_AGY_MODEL_FAMILIES:
            return set()
        if not self.leases_dir.exists():
            return set()

        current = time.time() if now_ts is None else float(now_ts)
        suffix = f".family-unavailable.{model_family}.json"
        blocked: set[str] = set()
        for path in self.leases_dir.glob(f"*{suffix}"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                until = float(payload.get("unavailable_until"))
                alias_hash = str(payload.get("account_alias_hash") or "")
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                # A malformed durable block fails closed for the encoded account hash.
                alias_hash = path.name[: -len(suffix)]
                if alias_hash:
                    blocked.add(alias_hash)
                continue

            if until <= current:
                try:
                    path.unlink()
                except OSError:
                    blocked.add(alias_hash or path.name[: -len(suffix)])
                continue
            if alias_hash:
                blocked.add(alias_hash)
        return blocked

    def is_family_unavailable(
        self,
        account_alias_hash: str,
        model_family: str | None,
        *,
        now_ts: float | None = None,
    ) -> bool:
        return account_alias_hash in self.get_family_unavailable_hashes(
            model_family,
            now_ts=now_ts,
        )

    def quarantine_account(
        self,
        account_alias_hash: str,
        reason: str,
        claim: Optional[AccountLeaseClaim] = None,
    ) -> Path:
        """Durably quarantine an account across processes by alias hash only.

        Writes an atomic quarantine marker in leases_dir. No raw alias/email/credentials
        are exposed in the filename or content.
        """
        import json
        import time

        self.leases_dir.mkdir(parents=True, exist_ok=True)
        q_path = self.leases_dir / f"{account_alias_hash}.quarantine.json"
        data: dict[str, Any] = {
            "account_alias_hash": account_alias_hash,
            "lease_id_hash": claim.lease_id_hash if claim else "none",
            "consumer_id": claim.lease.consumer_id if claim else "unknown",
            "reason": reason,
            "quarantined_at": time.time(),
            "pid": os.getpid(),
        }

        tmp_path = (
            self.leases_dir / f".{account_alias_hash}.quarantine.{os.getpid()}.{time.time_ns()}.tmp"
        )
        try:
            tmp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            os.replace(tmp_path, q_path)
        except Exception:
            try:
                q_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            finally:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
        return q_path

    def unquarantine_account(self, account_alias_hash: str) -> bool:
        """Explicit conservative unquarantine for recovery paths only.

        Requires explicit target hash; no automatic unquarantine is performed.
        """
        removed = False
        for suffix in (".quarantine.json", ".quarantine"):
            p = self.leases_dir / f"{account_alias_hash}{suffix}"
            if p.exists():
                try:
                    p.unlink()
                    removed = True
                except OSError:
                    pass
        return removed

    def is_quarantined(self, account_alias_hash: str) -> bool:
        """Check whether an account hash is currently quarantined."""
        q_json = self.leases_dir / f"{account_alias_hash}.quarantine.json"
        if q_json.exists():
            return True
        q_raw = self.leases_dir / f"{account_alias_hash}.quarantine"
        if q_raw.exists():
            return True
        return False

    def get_quarantined_hashes(self) -> set[str]:
        """Return the set of all quarantined account alias hashes."""
        quarantined = set()
        if not self.leases_dir.exists():
            return quarantined
        try:
            for p in self.leases_dir.iterdir():
                if p.name.endswith(".quarantine.json"):
                    quarantined.add(p.name[: -len(".quarantine.json")])
                elif p.name.endswith(".quarantine"):
                    quarantined.add(p.name[: -len(".quarantine")])
        except OSError:
            pass
        return quarantined

    def retire_failed_claim(
        self,
        claim: AccountLeaseClaim,
        failure_kind: AccountFailureKind,
        *,
        model_family: str | None = None,
        unavailable_until: float | None = None,
    ) -> None:
        """Retire a failed claim at the narrowest durable availability scope.

        Quota exhaustion with a known model family is isolated to
        account x model_family. Rate limits and authentication/session/account failures remain
        account-global and keep the provider manager's normal cooldown semantics.
        """
        if not is_agy_rotation_eligible(failure_kind):
            return

        if claim.released:
            return

        if (
            failure_kind in MODEL_FAMILY_SCOPED_FAILURES
            and model_family in SUPPORTED_AGY_MODEL_FAMILIES
        ):
            try:
                self.mark_family_unavailable(
                    claim.account_alias_hash,
                    model_family=model_family,
                    reason=failure_kind.value,
                    unavailable_until=unavailable_until,
                    claim=claim,
                )
            except Exception as exc:
                raise AgyAccountPoolManagerError(
                    "AGY_FAMILY_RETIREMENT_UNSAFE: family availability state was not persisted"
                ) from exc
            claim.release()
            return

        # Account-global failures keep the provider-manager bad/cooldown state.
        manager_persisted = False
        manager_error: Exception | None = None
        try:
            manager_persisted = bool(self.manager.mark_account_bad(claim.lease, failure_kind))
        except Exception as exc:
            manager_error = exc

        quarantine_persisted = False
        quarantine_error: Exception | None = None
        if not manager_persisted:
            try:
                self.quarantine_account(
                    claim.account_alias_hash,
                    reason=failure_kind.value,
                    claim=claim,
                )
                quarantine_persisted = True
            except Exception as exc:
                quarantine_error = exc

        if not manager_persisted and not quarantine_persisted:
            detail = manager_error or quarantine_error
            raise AgyAccountPoolManagerError(
                "AGY_ACCOUNT_RETIREMENT_UNSAFE: no durable manager or local quarantine state"
            ) from detail

        claim.release()

    def acquire_claim(
        self,
        consumer_id: str,
        exclude_hashes: Optional[set[str]] = None,
        wait_timeout: Optional[float] = None,
        *,
        model_family: str | None = None,
    ) -> AccountLeaseClaim:
        import fcntl
        import time

        timeout = wait_timeout if wait_timeout is not None else self.default_wait_timeout
        deadline = time.monotonic() + max(0.0, timeout)

        self.allocator_lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.leases_dir.mkdir(parents=True, exist_ok=True)

        excluded = set(exclude_hashes or ())

        while True:
            claimed: Optional[AccountLeaseClaim] = None
            has_healthy_candidates = False

            with self.allocator_lock_path.open("a+") as alloc_f:
                fcntl.flock(alloc_f.fileno(), fcntl.LOCK_EX)
                try:
                    self.manager._refresh_pool_health()
                    pool = self.manager._ensure_pool()

                    quarantined_hashes = self.get_quarantined_hashes()
                    family_unavailable_hashes = self.get_family_unavailable_hashes(model_family)
                    blocked_accounts = {
                        name.strip()
                        for name in os.getenv("NEXUS_AGY_BLOCKED_ACCOUNTS", "").split(",")
                        if name.strip()
                    }

                    available_accounts = [
                        acc
                        for acc in pool._accounts.values()
                        if acc.is_available
                        and acc.alias_hash not in excluded
                        and acc.alias_hash not in quarantined_hashes
                        and acc.alias_hash not in family_unavailable_hashes
                        and acc.internal_id not in blocked_accounts
                    ]

                    if available_accounts:
                        has_healthy_candidates = True

                        def _ordered_rank(env_name: str, excluded: set[str]) -> dict[str, int]:
                            ranks: dict[str, int] = {}
                            for raw_name in os.getenv(env_name, "").split(","):
                                name = raw_name.strip()
                                if not name or name in excluded or name in ranks:
                                    continue
                                ranks[name] = len(ranks)
                            return ranks

                        preferred_ranks = _ordered_rank(
                            "NEXUS_AGY_PREFERRED_ACCOUNTS",
                            set(),
                        )
                        reserve_ranks = _ordered_rank(
                            "NEXUS_AGY_RESERVE_ACCOUNTS",
                            set(preferred_ranks),
                        )
                        fallback_ranks = _ordered_rank(
                            "NEXUS_AGY_FALLBACK_ACCOUNTS",
                            set(preferred_ranks) | set(reserve_ranks),
                        )

                        def _candidate_sort_key(
                            account: InternalAccountRecord,
                        ) -> tuple[object, ...]:
                            if account.internal_id in preferred_ranks:
                                tier = 0
                                drain_rank = preferred_ranks[account.internal_id]
                            elif account.internal_id in reserve_ranks:
                                tier = 1
                                drain_rank = reserve_ranks[account.internal_id]
                            elif account.internal_id in fallback_ranks:
                                tier = 2
                                drain_rank = fallback_ranks[account.internal_id]
                            else:
                                tier = 3
                                drain_rank = 0
                            # Model-family availability establishes the tier. Within a tier,
                            # dispatcher-provided order drains quota that is both abundant and
                            # near reset before load/session spread breaks remaining ties.
                            spread = hashlib.sha256(
                                f"{consumer_id}\0{account.internal_id}".encode("utf-8")
                            ).hexdigest()
                            return (
                                tier,
                                drain_rank,
                                account.load,
                                spread,
                                account.alias_hash,
                            )

                        candidates = sorted(available_accounts, key=_candidate_sort_key)

                        for candidate in candidates:
                            if candidate.alias_hash in quarantined_hashes:
                                continue

                            lock_path = self.leases_dir / f"{candidate.alias_hash}.lock"
                            receipt_path = self.leases_dir / f"{candidate.alias_hash}.receipt.json"

                            lock_obj = None
                            try:
                                lock_obj = lock_path.open("a+")
                                fcntl.flock(lock_obj.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            except (BlockingIOError, OSError):
                                if lock_obj is not None:
                                    try:
                                        lock_obj.close()
                                    except Exception:
                                        pass
                                continue

                            assert lock_obj is not None

                            # Atomically claimed per-account lock
                            lease = pool.acquire(
                                consumer_id, preferred_account_id=candidate.internal_id
                            )
                            self.manager._lease_to_raw_alias[lease.lease_id] = candidate.internal_id

                            lease_id_hash = hashlib.sha256(
                                lease.lease_id.encode("utf-8")
                            ).hexdigest()[:12]
                            receipt_data = {
                                "account_alias_hash": candidate.alias_hash,
                                "lease_id_hash": lease_id_hash,
                                "consumer_id": consumer_id,
                                "claimed_at": time.time(),
                                "pid": os.getpid(),
                            }
                            receipt_path.write_text(
                                json.dumps(receipt_data) + "\n", encoding="utf-8"
                            )

                            claimed = AccountLeaseClaim(
                                lease=lease,
                                lock_file_obj=lock_obj,
                                lock_path=lock_path,
                                receipt_path=receipt_path,
                                account_alias_hash=candidate.alias_hash,
                                lease_id_hash=lease_id_hash,
                                manager=self.manager,
                                internal_id=candidate.internal_id,
                            )
                            break
                finally:
                    fcntl.flock(alloc_f.fileno(), fcntl.LOCK_UN)

            if claimed is not None:
                return claimed

            if not has_healthy_candidates:
                raise AgyAccountPoolExhaustedError(
                    "AGY_ACCOUNT_POOL_EXHAUSTED: No available healthy accounts"
                )

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AgyAccountPoolBusyError(
                    "AGY_ACCOUNT_POOL_BUSY: All healthy accounts currently leased"
                )

            time.sleep(min(self.poll_interval, max(0.01, remaining)))

    def rotate_claim(
        self,
        current_claim: AccountLeaseClaim,
        failure_kind: AccountFailureKind,
        exclude_hashes: set[str],
        wait_timeout: Optional[float] = None,
        *,
        model_family: str | None = None,
        unavailable_until: float | None = None,
    ) -> AccountLeaseClaim:
        old_hash = current_claim.account_alias_hash
        old_lease = current_claim.lease
        consumer_id = old_lease.consumer_id

        # 1. Safely retire the failed claim at account or model-family scope.
        self.retire_failed_claim(
            current_claim,
            failure_kind,
            model_family=model_family,
            unavailable_until=unavailable_until,
        )
        exclude_hashes.add(old_hash)

        # 2. Briefly acquire allocator lock and claim another healthy account.
        return self.acquire_claim(
            consumer_id=consumer_id,
            exclude_hashes=exclude_hashes,
            wait_timeout=wait_timeout,
            model_family=model_family,
        )


_GLOBAL_POOL_MANAGER: Optional[AgyAccountPoolManager] = None


def get_account_pool_manager() -> AgyAccountPoolManager:
    global _GLOBAL_POOL_MANAGER
    if _GLOBAL_POOL_MANAGER is not None:
        return _GLOBAL_POOL_MANAGER

    manager_path = AgyAccountPoolManager.resolve_manager_path()
    use_real = bool(
        manager_path
        and Path(manager_path).is_file()
        and os.getenv("NEXUS_AGY_ACCOUNT_ALIASES", "") == ""
    )

    if use_real:
        _GLOBAL_POOL_MANAGER = AgyAccountPoolManager(
            use_real_manager=True, manager_path=manager_path
        )
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

    _GLOBAL_POOL_MANAGER = AgyAccountPoolManager(accounts)
    return _GLOBAL_POOL_MANAGER


def set_global_account_pool_manager(manager: Optional[AgyAccountPoolManager]) -> None:
    global _GLOBAL_POOL_MANAGER
    _GLOBAL_POOL_MANAGER = manager
