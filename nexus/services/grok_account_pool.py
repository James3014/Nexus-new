"""Cross-process, machine-local Grok account leases for direct CLI execution.

This module owns only account/profile binding and failover. It does not select
routes, models, verification, acceptance, integration, or merge authority.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from nexus.services.external_account_pool import AccountFailureKind, is_rotation_eligible

_NEUTRAL_ENV_KEYS = (
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
_SENSITIVE_ENV_KEYS = ("XAI_API_KEY", "GROK_API_KEY", "NEXUS_GROK_API_KEY")


class GrokAccountPoolError(RuntimeError):
    """Machine-local Grok account pool failure."""


class GrokAccountPoolExhaustedError(GrokAccountPoolError):
    """No eligible Grok profile is available."""


@dataclass(frozen=True)
class GrokLease:
    lease_id: str
    consumer_id: str
    account_alias_hash: str
    execution_env: Mapping[str, str]


def _hash(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _pid_alive(pid: object) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def classify_grok_failure(text: str, *, timed_out: bool = False) -> AccountFailureKind:
    value = str(text or "").lower()
    if timed_out:
        return AccountFailureKind.TIMEOUT
    if any(x in value for x in ("token refresh failed", "refresh token failed")):
        return AccountFailureKind.TOKEN_REFRESH_FAILED
    if any(x in value for x in ("token expired", "session expired", "expired token")):
        return AccountFailureKind.TOKEN_EXPIRED
    if any(
        x in value
        for x in (
            "not authenticated",
            "authentication failed",
            "authentication error",
            "unauthorized",
            "invalid api key",
            "login required",
            "401",
        )
    ):
        return AccountFailureKind.AUTH_OR_SESSION_INVALID
    if any(x in value for x in ("quota", "resource_exhausted", "insufficient_quota")):
        return AccountFailureKind.QUOTA_EXHAUSTED
    if any(x in value for x in ("rate limit", "rate_limit", "ratelimit", "429")):
        return AccountFailureKind.RATE_LIMITED
    if "account disabled" in value:
        return AccountFailureKind.ACCOUNT_DISABLED
    if any(x in value for x in ("account unavailable", "service unavailable", "503")):
        return AccountFailureKind.ACCOUNT_UNAVAILABLE
    if any(x in value for x in ("permission denied", "forbidden", "403")):
        return AccountFailureKind.PERMISSION_OR_SCOPE_ERROR
    if "cancel" in value:
        return AccountFailureKind.CANCELLED
    return AccountFailureKind.UNKNOWN


class GrokAccountPoolManager:
    """File-lock-backed allocator shared by local external-worker processes."""

    def __init__(self, root: Path | None = None, *, cooldown_seconds: float = 300.0) -> None:
        self.root = Path(root or Path.home() / ".nexus/grok-account-pool").expanduser()
        self.state_path = self.root / "state.json"
        self.lock_path = self.root / "pool.lock"
        self.profile_root = self.root / "profiles"
        self.cooldown_seconds = float(cooldown_seconds)

    def _load_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise GrokAccountPoolExhaustedError("GROK_ACCOUNT_POOL_STATE_MISSING") from exc
        except json.JSONDecodeError as exc:
            raise GrokAccountPoolError("GROK_ACCOUNT_POOL_STATE_INVALID") from exc
        if not isinstance(value, dict) or not isinstance(value.get("accounts"), dict):
            raise GrokAccountPoolError("GROK_ACCOUNT_POOL_STATE_INVALID")
        if value.get("leases") is None:
            value["leases"] = {}
        elif not isinstance(value.get("leases"), dict):
            raise GrokAccountPoolError("GROK_ACCOUNT_POOL_LEASES_INVALID")
        return value

    def _write_state(self, state: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        tmp = self.root / f".state.tmp.{os.getpid()}.{uuid.uuid4().hex}"
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=2, sort_keys=True)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.state_path)
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    def _lock(self):
        self.root.mkdir(parents=True, mode=0o700, exist_ok=True)
        fh = self.lock_path.open("a+")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        return fh

    @staticmethod
    def _prune_dead_leases(state: dict[str, Any]) -> None:
        leases = state.setdefault("leases", {})
        for lease_id, record in list(leases.items()):
            if not isinstance(record, dict) or not _pid_alive(record.get("pid")):
                leases.pop(lease_id, None)

    def _opaque_home(self, alias: str, raw_home: str) -> str:
        source = Path(raw_home).expanduser()
        if not source.is_absolute() or not source.is_dir():
            raise GrokAccountPoolError("GROK_PROFILE_HOME_INVALID")
        opaque = self.profile_root / f"profile-{_hash(alias)}"
        self.profile_root.mkdir(parents=True, mode=0o700, exist_ok=True)
        source_resolved = source.resolve()
        if opaque.is_symlink():
            if opaque.resolve() != source_resolved:
                raise GrokAccountPoolError("GROK_PROFILE_HOME_BINDING_CONFLICT")
        elif opaque.exists():
            raise GrokAccountPoolError("GROK_PROFILE_HOME_BINDING_CONFLICT")
        else:
            opaque.symlink_to(source_resolved, target_is_directory=True)
        return str(opaque)

    def _execution_env(self, alias: str, raw_home: str) -> dict[str, str]:
        env = {key: os.environ[key] for key in _NEUTRAL_ENV_KEYS if key in os.environ}
        env["HOME"] = self._opaque_home(alias, raw_home)
        for key in _SENSITIVE_ENV_KEYS:
            env.pop(key, None)
        return env

    @staticmethod
    def _eligible(state: dict[str, Any], now: float) -> list[tuple[str, dict[str, Any]]]:
        held = {
            str(record.get("alias"))
            for record in state.get("leases", {}).values()
            if isinstance(record, dict) and record.get("alias")
        }
        result = []
        for alias, record in state["accounts"].items():
            if not isinstance(record, dict) or not bool(record.get("enabled", True)):
                continue
            if float(record.get("cooldown_until") or 0.0) > now or alias in held:
                continue
            if not Path(str(record.get("home_path") or "")).expanduser().is_dir():
                continue
            result.append((str(alias), record))
        return result

    def _acquire_locked(
        self,
        state: dict[str, Any],
        consumer_id: str,
        *,
        exclude_alias: str | None = None,
    ) -> GrokLease:
        candidates = [
            item for item in self._eligible(state, time.time()) if item[0] != exclude_alias
        ]
        if not candidates:
            raise GrokAccountPoolExhaustedError("GROK_ACCOUNT_POOL_EXHAUSTED")
        candidates.sort(
            key=lambda item: (
                float(item[1].get("last_failure_timestamp") or 0.0),
                item[0],
            )
        )
        alias, record = candidates[0]
        lease_id = "groklease_" + uuid.uuid4().hex
        now = time.time()
        state.setdefault("leases", {})[lease_id] = {
            "alias": alias,
            "consumer_id": consumer_id,
            "pid": os.getpid(),
            "acquired_at": now,
        }
        state["active_alias"] = alias
        state["updated_at"] = now
        self._write_state(state)
        return GrokLease(
            lease_id=lease_id,
            consumer_id=consumer_id,
            account_alias_hash=_hash(alias),
            execution_env=self._execution_env(alias, str(record["home_path"])),
        )

    def acquire(self, consumer_id: str) -> GrokLease:
        consumer = str(consumer_id).strip()
        if not consumer:
            raise GrokAccountPoolError("GROK_CONSUMER_ID_REQUIRED")
        lock = self._lock()
        try:
            state = self._load_state()
            self._prune_dead_leases(state)
            if any(
                isinstance(record, dict) and record.get("consumer_id") == consumer
                for record in state["leases"].values()
            ):
                raise GrokAccountPoolError("GROK_CONSUMER_ALREADY_BOUND")
            return self._acquire_locked(state, consumer)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    def release(self, lease: GrokLease) -> None:
        lock = self._lock()
        try:
            state = self._load_state()
            self._prune_dead_leases(state)
            record = state["leases"].get(lease.lease_id)
            if (
                not isinstance(record, dict)
                or record.get("consumer_id") != lease.consumer_id
                or _hash(str(record.get("alias") or "")) != lease.account_alias_hash
            ):
                raise GrokAccountPoolError("GROK_INVALID_ACCOUNT_LEASE")
            state["leases"].pop(lease.lease_id, None)
            state["updated_at"] = time.time()
            self._write_state(state)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    def report_failure(
        self,
        lease: GrokLease,
        failure_kind: AccountFailureKind,
    ) -> GrokLease | None:
        if not is_rotation_eligible(failure_kind):
            return None
        lock = self._lock()
        try:
            state = self._load_state()
            self._prune_dead_leases(state)
            record = state["leases"].get(lease.lease_id)
            if not isinstance(record, dict) or record.get("consumer_id") != lease.consumer_id:
                raise GrokAccountPoolError("GROK_INVALID_ACCOUNT_LEASE")
            alias = str(record.get("alias") or "")
            if _hash(alias) != lease.account_alias_hash:
                raise GrokAccountPoolError("GROK_INVALID_ACCOUNT_LEASE")
            account = state["accounts"].get(alias)
            if not isinstance(account, dict):
                raise GrokAccountPoolError("GROK_ACCOUNT_RECORD_MISSING")
            now = time.time()
            account["cooldown_until"] = now + self.cooldown_seconds
            account["last_failure_timestamp"] = now
            account["last_failure_reason"] = failure_kind.value
            state["leases"].pop(lease.lease_id, None)
            try:
                return self._acquire_locked(state, lease.consumer_id, exclude_alias=alias)
            except GrokAccountPoolExhaustedError:
                state["updated_at"] = now
                self._write_state(state)
                raise
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()


_GLOBAL_MANAGER: GrokAccountPoolManager | None = None


def get_grok_account_pool_manager() -> GrokAccountPoolManager:
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        configured = os.getenv("NEXUS_GROK_ACCOUNT_POOL_ROOT", "").strip()
        _GLOBAL_MANAGER = GrokAccountPoolManager(
            Path(configured).expanduser() if configured else None
        )
    return _GLOBAL_MANAGER


def set_grok_account_pool_manager(manager: GrokAccountPoolManager | None) -> None:
    global _GLOBAL_MANAGER
    _GLOBAL_MANAGER = manager
