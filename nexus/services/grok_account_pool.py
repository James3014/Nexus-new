"""Cross-process, machine-local Grok account leases for direct CLI execution.

This module owns only account/profile binding and failover. It does not select
routes, models, verification, acceptance, integration, or merge authority.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
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


@dataclass(frozen=True)
class GrokHostBinding:
    """Non-secret machine binding for the local credential pool."""

    status: str
    owner_host_id_hash: str | None
    current_host_id_hash: str
    matches: bool


@dataclass(frozen=True)
class GrokLocalAccount:
    """Machine-local operator view. Never put this object in public receipts."""

    alias: str
    home_path: str
    display_label: str | None
    enabled: bool
    cooldown_until: float
    last_failure_reason: str
    last_failure_timestamp: float
    leased: bool
    home_exists: bool


_ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_HOST_BINDING_SCHEMA = "nexus.grok_pool_host_binding.v1"


def _hash(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _machine_identity() -> str:
    """Return one stable OS machine identity without persisting a second registry."""

    for candidate in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        try:
            value = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return f"machine-id:{value}"

    if sys.platform == "darwin":
        proc = subprocess.run(
            ["/usr/sbin/ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if proc.returncode == 0:
            match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', proc.stdout)
            if match:
                return f"ioplatformuuid:{match.group(1).strip().lower()}"

    raise GrokAccountPoolError("GROK_HOST_IDENTITY_UNAVAILABLE")


def _host_identity_hash(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise GrokAccountPoolError("GROK_HOST_IDENTITY_UNAVAILABLE")
    return hashlib.sha256(f"nexus.grok.host.v1:{normalized}".encode("utf-8")).hexdigest()


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


def build_grok_profile_env(home_path: str | Path) -> dict[str, str]:
    """Build the minimal environment used for local Grok profile probes."""

    source = Path(home_path).expanduser()
    if not source.is_absolute() or not source.is_dir():
        raise GrokAccountPoolError("GROK_PROFILE_HOME_INVALID")
    env = {key: os.environ[key] for key in _NEUTRAL_ENV_KEYS if key in os.environ}
    env["HOME"] = str(source)
    for key in _SENSITIVE_ENV_KEYS:
        env.pop(key, None)
    return env


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
            "not signed in",
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

    def __init__(
        self,
        root: Path | None = None,
        *,
        cooldown_seconds: float = 300.0,
        host_identity: str | None = None,
    ) -> None:
        self.root = Path(root or Path.home() / ".nexus/grok-account-pool").expanduser()
        self.state_path = self.root / "state.json"
        self.lock_path = self.root / "pool.lock"
        self.profile_root = self.root / "profiles"
        self.cooldown_seconds = float(cooldown_seconds)
        self.host_id_hash = _host_identity_hash(
            host_identity if host_identity is not None else _machine_identity()
        )

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

    def _load_state_or_empty(self) -> dict[str, Any]:
        try:
            return self._load_state()
        except GrokAccountPoolExhaustedError as exc:
            if str(exc) != "GROK_ACCOUNT_POOL_STATE_MISSING":
                raise
            return {
                "accounts": {},
                "leases": {},
                "active_alias": None,
                "updated_at": 0.0,
            }

    def _host_binding_from_state(self, state: dict[str, Any]) -> GrokHostBinding:
        raw = state.get("host_binding")
        if raw is None:
            return GrokHostBinding(
                status="UNBOUND",
                owner_host_id_hash=None,
                current_host_id_hash=self.host_id_hash,
                matches=False,
            )
        if (
            not isinstance(raw, dict)
            or raw.get("schema") != _HOST_BINDING_SCHEMA
            or not isinstance(raw.get("host_id_hash"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", str(raw.get("host_id_hash")))
        ):
            raise GrokAccountPoolError("GROK_ACCOUNT_POOL_HOST_BINDING_INVALID")
        owner = str(raw["host_id_hash"])
        matches = owner == self.host_id_hash
        return GrokHostBinding(
            status="BOUND" if matches else "HOST_MISMATCH",
            owner_host_id_hash=owner,
            current_host_id_hash=self.host_id_hash,
            matches=matches,
        )

    def _assert_host_binding(self, state: dict[str, Any]) -> None:
        binding = self._host_binding_from_state(state)
        if binding.owner_host_id_hash is None:
            if state.get("accounts"):
                raise GrokAccountPoolError("GROK_ACCOUNT_POOL_HOST_UNBOUND")
            return
        if not binding.matches:
            raise GrokAccountPoolError("GROK_ACCOUNT_POOL_HOST_MISMATCH")

    def host_binding(self) -> GrokHostBinding:
        """Read host ownership without exposing raw machine identity."""

        lock = self._lock()
        try:
            return self._host_binding_from_state(self._load_state_or_empty())
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    def bind_host(self, *, confirm_existing_pool: bool = False) -> GrokHostBinding:
        """Bind one legacy/unbound pool to this host; never rebind a mismatch."""

        lock = self._lock()
        try:
            state = self._load_state_or_empty()
            binding = self._host_binding_from_state(state)
            if binding.owner_host_id_hash is not None:
                if not binding.matches:
                    raise GrokAccountPoolError("GROK_ACCOUNT_POOL_HOST_MISMATCH")
                return binding
            if state.get("accounts") and not confirm_existing_pool:
                raise GrokAccountPoolError("GROK_ACCOUNT_POOL_HOST_BINDING_CONFIRMATION_REQUIRED")
            state["host_binding"] = {
                "schema": _HOST_BINDING_SCHEMA,
                "host_id_hash": self.host_id_hash,
                "bound_at": time.time(),
            }
            state["updated_at"] = time.time()
            self._write_state(state)
            return self._host_binding_from_state(state)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    def local_accounts(self) -> tuple[GrokLocalAccount, ...]:
        """Read machine-local inventory without reading credential contents."""

        lock = self._lock()
        try:
            state = self._load_state_or_empty()
            self._assert_host_binding(state)
            live_aliases = {
                str(record.get("alias"))
                for record in state.get("leases", {}).values()
                if isinstance(record, dict)
                and record.get("alias")
                and _pid_alive(record.get("pid"))
            }
            result: list[GrokLocalAccount] = []
            for alias, record in sorted(state["accounts"].items()):
                if not isinstance(record, dict):
                    raise GrokAccountPoolError("GROK_ACCOUNT_RECORD_INVALID")
                raw_home = str(record.get("home_path") or "")
                result.append(
                    GrokLocalAccount(
                        alias=str(alias),
                        home_path=raw_home,
                        display_label=(
                            str(record["display_label"]).strip()
                            if record.get("display_label")
                            else None
                        ),
                        enabled=bool(record.get("enabled", True)),
                        cooldown_until=float(record.get("cooldown_until") or 0.0),
                        last_failure_reason=str(record.get("last_failure_reason") or ""),
                        last_failure_timestamp=float(record.get("last_failure_timestamp") or 0.0),
                        leased=str(alias) in live_aliases,
                        home_exists=Path(raw_home).expanduser().is_dir(),
                    )
                )
            return tuple(result)
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    def register_local_profile(
        self,
        *,
        alias: str,
        home_path: str | Path,
        display_label: str | None = None,
    ) -> GrokLocalAccount:
        """Atomically register one already-authenticated local profile."""

        normalized_alias = str(alias).strip()
        if not _ALIAS_RE.fullmatch(normalized_alias):
            raise GrokAccountPoolError("GROK_ACCOUNT_ALIAS_INVALID")
        source = Path(home_path).expanduser()
        if not source.is_absolute() or not source.is_dir():
            raise GrokAccountPoolError("GROK_PROFILE_HOME_INVALID")
        if stat.S_IMODE(source.stat().st_mode) & 0o077:
            raise GrokAccountPoolError("GROK_PROFILE_HOME_PERMISSIONS_TOO_OPEN")
        resolved_home = str(source.resolve())
        normalized_label = str(display_label or "").strip() or None

        lock = self._lock()
        try:
            state = self._load_state_or_empty()
            self._prune_dead_leases(state)
            accounts = state.setdefault("accounts", {})
            binding = self._host_binding_from_state(state)
            if binding.owner_host_id_hash is None:
                if accounts:
                    raise GrokAccountPoolError("GROK_ACCOUNT_POOL_HOST_UNBOUND")
                state["host_binding"] = {
                    "schema": _HOST_BINDING_SCHEMA,
                    "host_id_hash": self.host_id_hash,
                    "bound_at": time.time(),
                }
            elif not binding.matches:
                raise GrokAccountPoolError("GROK_ACCOUNT_POOL_HOST_MISMATCH")
            if normalized_alias in accounts:
                raise GrokAccountPoolError("GROK_ACCOUNT_ALIAS_ALREADY_REGISTERED")
            for record in accounts.values():
                if not isinstance(record, dict):
                    raise GrokAccountPoolError("GROK_ACCOUNT_RECORD_INVALID")
                existing_home = Path(str(record.get("home_path") or "")).expanduser()
                if existing_home.is_absolute() and existing_home.exists():
                    try:
                        if existing_home.resolve() == source.resolve():
                            raise GrokAccountPoolError("GROK_PROFILE_HOME_ALREADY_REGISTERED")
                    except OSError:
                        pass
                existing_label = str(record.get("display_label") or "").strip()
                if (
                    normalized_label
                    and existing_label
                    and existing_label.casefold() == normalized_label.casefold()
                ):
                    raise GrokAccountPoolError("GROK_ACCOUNT_DISPLAY_LABEL_DUPLICATE")
            now = time.time()
            accounts[normalized_alias] = {
                "home_path": resolved_home,
                "enabled": True,
                "cooldown_until": 0.0,
                "last_failure_reason": "",
                "last_failure_timestamp": 0.0,
            }
            if normalized_label:
                accounts[normalized_alias]["display_label"] = normalized_label
            state["updated_at"] = now
            self._write_state(state)
            return GrokLocalAccount(
                alias=normalized_alias,
                home_path=resolved_home,
                display_label=normalized_label,
                enabled=True,
                cooldown_until=0.0,
                last_failure_reason="",
                last_failure_timestamp=0.0,
                leased=False,
                home_exists=True,
            )
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

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
        return build_grok_profile_env(self._opaque_home(alias, raw_home))

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
            self._assert_host_binding(state)
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
            self._assert_host_binding(state)
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
        lock = self._lock()
        try:
            state = self._load_state()
            self._assert_host_binding(state)
            if not is_rotation_eligible(failure_kind):
                return None
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
