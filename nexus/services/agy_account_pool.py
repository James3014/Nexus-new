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
            self._use_real_manager = bool(resolved_mgr and Path(resolved_mgr).is_file() and not accounts)

        if self._use_real_manager:
            if not self._manager_path:
                self._manager_path = self.resolve_manager_path(manager_path)
            if not self._manager_root:
                self._manager_root = self.resolve_manager_root(manager_root, self._manager_path)

    @staticmethod
    def resolve_manager_path(override_path: Optional[str] = None) -> Optional[str]:
        if override_path:
            p = Path(override_path).expanduser()
            return str(p.resolve()) if p.exists() else str(p)
        env_path = os.getenv("NEXUS_AGY_ACCOUNT_POOL_MANAGER_PATH", "").strip()
        if env_path:
            p = Path(env_path).expanduser()
            return str(p.resolve()) if p.exists() else str(p)

        installed_path = Path("/Users/jameschen/.nexus/agy-account-pool/bin/agy-cli-manager")
        if installed_path.exists():
            return str(installed_path.resolve())

        home = Path.home()
        home_str = str(home)
        if "live-home" not in home_str and "agy-account-pool" not in home_str:
            default_path = home / ".nexus/agy-account-pool/bin/agy-cli-manager"
            if default_path.exists():
                return str(default_path.resolve())
            return str(default_path)

        return str(installed_path)

    @staticmethod
    def resolve_manager_root(override_root: Optional[str] = None, manager_path: Optional[str] = None) -> str:
        if override_root:
            p = Path(override_root).expanduser()
            return str(p.resolve()) if p.exists() else str(p)
        env_root = os.getenv("NEXUS_AGY_ACCOUNT_POOL_ROOT", "").strip()
        if env_root:
            p = Path(env_root).expanduser()
            return str(p.resolve()) if p.exists() else str(p)

        mgr_p = manager_path or AgyAccountPoolManager.resolve_manager_path()
        if mgr_p:
            p = Path(mgr_p).expanduser()
            if p.name == "agy-cli-manager" and p.parent.name == "bin":
                runtime_dir = p.parent.parent / "runtime"
                return str(runtime_dir.resolve()) if runtime_dir.exists() else str(runtime_dir)
            elif p.exists():
                runtime_dir = p.parent / "runtime"
                return str(runtime_dir.resolve()) if runtime_dir.exists() else str(runtime_dir)

        installed_root = Path("/Users/jameschen/.nexus/agy-account-pool/runtime")
        if installed_root.exists():
            return str(installed_root.resolve())
        return str(Path.home() / ".nexus/agy-account-pool/runtime")

    def _call_manager_cli(self, args: list[str]) -> dict:
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
        raise AgyAccountPoolExhaustedError("No available AGY accounts remaining in pool")

    def build_isolated_env(self, base_env: Optional[dict[str, str]] = None) -> dict[str, str]:
        account = self.active_account
        home_dir = account.home_dir if account else None
        return build_isolated_env(home_dir=home_dir, base_env=base_env)


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

    if not accounts:
        accounts.append(AgyAccount(alias="default", home_dir=str(Path.home())))

    _GLOBAL_POOL_MANAGER = AgyAccountPoolManager(accounts)
    return _GLOBAL_POOL_MANAGER


def set_global_account_pool_manager(manager: Optional[AgyAccountPoolManager]) -> None:
    global _GLOBAL_POOL_MANAGER
    _GLOBAL_POOL_MANAGER = manager
