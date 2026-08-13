"""AGY Account Pool Manager for governed multi-account failover and isolation."""

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
    InternalAccountRecord,
    InvalidAccountLeaseError,
    is_rotation_eligible,
)

SENSITIVE_API_KEYS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_API_KEY")


class AgyAccountPoolError(RuntimeError):
    """Base exception for AGY Account Pool operations."""


class AgyAccountPoolExhaustedError(AgyAccountPoolError):
    """Raised when no active account is available in the pool."""


class AgyAccountPoolManagerError(AgyAccountPoolError):
    """Raised when the account pool manager CLI fails or returns invalid data."""


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


def _is_populated_runtime(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    state_json = path / "state.json"
    if state_json.exists() and state_json.is_file():
        try:
            import json
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
            self._use_real_manager = bool(resolved_mgr and Path(resolved_mgr).is_file() and accounts is None)

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
    def resolve_manager_root(override_root: Optional[str] = None, manager_path: Optional[str] = None) -> str:
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
                return str(derived_from_mgr.resolve()) if derived_from_mgr.exists() else str(derived_from_mgr)

        candidates = [Path.home() / ".nexus/agy-account-pool/runtime"]

        for cand in candidates:
            if _is_populated_runtime(cand):
                return str(cand.resolve())

        for cand in candidates:
            if cand.exists():
                return str(cand.resolve())

        if derived_from_mgr:
            return str(derived_from_mgr.resolve()) if derived_from_mgr.exists() else str(derived_from_mgr)

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
            import json
            return json.loads(res.stdout)
        except json.JSONDecodeError as exc:
            raise AgyAccountPoolManagerError(
                "Invalid JSON returned by agy-cli-manager"
            ) from exc

    def _sync_real_active_account(self) -> AgyAccount:
        data = self._call_manager_cli(["ensure-active", "--json"])
        active_name = data.get("active") or data.get("switched_to")
        if not active_name:
            raise AgyAccountPoolExhaustedError("AGY_ACCOUNT_POOL_EXHAUSTED: No active AGY account available")

        status = self._call_manager_cli(["status", "--json"])
        if not active_name:
            active_name = status.get("active")
        if not active_name:
            raise AgyAccountPoolExhaustedError("AGY_ACCOUNT_POOL_EXHAUSTED: No active AGY account available")

        live_dir_str = status.get("live_dir")
        if not live_dir_str:
            raise AgyAccountPoolManagerError("Active account live_dir is missing from manager status")

        live_dir_path = Path(live_dir_str)
        if not live_dir_path.is_absolute() or not live_dir_path.is_dir():
            raise AgyAccountPoolManagerError("Active account live_dir is not an absolute existing directory")

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
                data = self._call_manager_cli(["rotate-after-failure", "--reason", reason, "--json"])

            new_active = data.get("switched_to") or data.get("active")
            outcome = data.get("outcome")
            if not new_active or outcome in ("no_active_account", "marked_bad_no_standby"):
                self._accounts = []
                self._active_index = -1
                raise AgyAccountPoolExhaustedError("AGY_ACCOUNT_POOL_EXHAUSTED: No available AGY accounts remaining in pool")
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
                            is_avail = True

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
                    is_avail = True

            if record is not None:
                record.is_available = is_avail
            else:
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
        self._refresh_pool_health()
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
                self._call_manager_cli(["mark-bad", failed_alias, "--reason", failure_kind.value], expect_json=False)
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


_GLOBAL_POOL_MANAGER: Optional[AgyAccountPoolManager] = None


def get_account_pool_manager() -> AgyAccountPoolManager:
    global _GLOBAL_POOL_MANAGER
    if _GLOBAL_POOL_MANAGER is not None:
        return _GLOBAL_POOL_MANAGER

    manager_path = AgyAccountPoolManager.resolve_manager_path()
    use_real = bool(manager_path and Path(manager_path).is_file() and os.getenv("NEXUS_AGY_ACCOUNT_ALIASES", "") == "")

    if use_real:
        _GLOBAL_POOL_MANAGER = AgyAccountPoolManager(use_real_manager=True, manager_path=manager_path)
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
