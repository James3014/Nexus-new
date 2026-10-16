"""Cross-process, machine-local Claude Code account leases for direct CLI execution.

This module owns only account/profile binding, identity verification and
failover. It does not select routes, models, verification, acceptance,
integration, or merge authority. Each profile is a separate CLAUDE_CONFIG_DIR
whose interactive login was performed by its owner; this module never reads,
copies, or stores credentials. Only non-secret hashes are persisted.
"""

from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import shutil
import stat
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from nexus.services.external_account_pool import AccountFailureKind, is_rotation_eligible
from nexus.services.grok_account_pool import GrokAccountPoolError, _machine_identity, _pid_alive

_NEUTRAL_ENV_KEYS = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LC_MESSAGES",
    "LC_NUMERIC",
    "LC_TIME",
    "TZ",
    "TERM",
)
_SENSITIVE_ENV_KEYS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_PAT",
    "OPENAI_API_KEY",
    "XAI_API_KEY",
    "GROK_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "OPENROUTER_API_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)
_AUTH_METHOD_MARKERS = ("claude.ai", "oauth")
_NO_ROTATION_KINDS = frozenset({
    AccountFailureKind.QUOTA_EXHAUSTED,
    AccountFailureKind.RATE_LIMITED,
})
_ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_HOST_BINDING_SCHEMA = "nexus.claude_pool_host_binding.v1"

IdentityObserver = Callable[[Path], "str | None"]


class ClaudeAccountPoolError(RuntimeError):
    """Machine-local Claude account pool failure."""


class ClaudeAccountPoolExhaustedError(ClaudeAccountPoolError):
    """No eligible Claude profile is available."""


class ClaudeAccountIdentityError(ClaudeAccountPoolError):
    """Observed profile identity is missing or not the approved identity (fail closed)."""

    failure_kind = AccountFailureKind.AUTH_OR_SESSION_INVALID


@dataclass(frozen=True)
class ClaudeLease:
    lease_id: str
    consumer_id: str
    account_alias_hash: str
    execution_env: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True)
class ClaudeHostBinding:
    status: str
    owner_host_id_hash: str | None
    current_host_id_hash: str
    matches: bool


@dataclass(frozen=True)
class ClaudeLocalAccount:
    """Machine-local operator view. Never put this object in public receipts."""

    alias: str
    config_dir: str
    approved_identity_fingerprint: str
    enabled: bool
    cooldown_until: float
    last_failure_reason: str
    last_failure_timestamp: float
    last_used_at: float
    leased: bool
    config_dir_exists: bool


def _hash(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def _host_identity_hash(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ClaudeAccountPoolError("CLAUDE_HOST_IDENTITY_UNAVAILABLE")
    return hashlib.sha256(f"nexus.claude.host.v1:{normalized}".encode("utf-8")).hexdigest()


def identity_fingerprint(account_id: str, organization_id: str = "") -> str:
    """Non-secret fingerprint of an account (+ organization) identifier pair."""

    payload = f"nexus.claude.identity.v1:{str(account_id).strip()}|{str(organization_id).strip()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def is_default_profile_path(path: str | Path) -> bool:
    """True if path is $HOME, ~/.claude, or inside ~/.claude (inode comparison, so
    case-insensitive filesystems and symlinks cannot disguise it)."""

    home = Path.home()
    default = home / ".claude"
    candidate = Path(os.path.realpath(Path(path).expanduser()))
    if _same_file(candidate, home):
        return True
    if not default.exists():
        # Nothing to compare by inode; fall back to the resolved path (incl. case-folding).
        resolved = Path(os.path.realpath(default))
        return any(
            str(p).casefold() == str(resolved).casefold() for p in (candidate, *candidate.parents)
        )
    return any(_same_file(p, default) for p in (candidate, *candidate.parents))


def build_claude_profile_env(config_dir: str | Path) -> dict[str, str]:
    """Build the minimal environment for one Claude profile; never the default profile."""

    source = Path(config_dir).expanduser()
    if not source.is_absolute() or not source.is_dir():
        raise ClaudeAccountPoolError("CLAUDE_PROFILE_CONFIG_DIR_INVALID")
    env = {key: os.environ[key] for key in _NEUTRAL_ENV_KEYS if key in os.environ}
    for key in _SENSITIVE_ENV_KEYS:
        env.pop(key, None)
    env["CLAUDE_CONFIG_DIR"] = str(source)
    return env


def _first_str(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def default_identity_observer(config_dir: Path) -> str | None:
    """Observe a profile via `claude auth status --json`; return only a hash or None."""

    executable = os.getenv("NEXUS_CLAUDE_BIN", "").strip() or shutil.which("claude")
    if not executable:
        return None
    try:
        proc = subprocess.run(
            [executable, "auth", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env=build_claude_profile_env(config_dir),
            stdin=subprocess.DEVNULL,
        )
        payload = json.loads(proc.stdout or "")
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ClaudeAccountPoolError):
        return None
    if proc.returncode != 0 or not isinstance(payload, dict):
        return None
    if payload.get("loggedIn") is not True:
        return None
    reported_dir = payload.get("configDirectory")
    if not isinstance(reported_dir, str) or not reported_dir.strip():
        return None
    if os.path.realpath(reported_dir) != os.path.realpath(config_dir):
        return None
    # Accept only subscription/OAuth logins (Claude.ai); API-key/other methods fail closed.
    method = payload.get("authMethod")
    if not isinstance(method, str) or not any(
        marker in method.lower() for marker in _AUTH_METHOD_MARKERS
    ):
        return None
    account = _first_str(payload, ("accountUuid", "account_uuid", "userId", "email"))
    if not account:
        return None
    org = _first_str(payload, ("organizationUuid", "organizationId", "orgId", "orgName"))
    return identity_fingerprint(account, org)


def classify_claude_failure(text: str, *, timed_out: bool = False) -> AccountFailureKind:
    value = str(text or "").lower()
    if timed_out:
        return AccountFailureKind.TIMEOUT
    if any(x in value for x in ("token expired", "session expired", "expired token")):
        return AccountFailureKind.TOKEN_EXPIRED
    if any(
        x in value
        for x in (
            "not logged in",
            "please run /login",
            "invalid api key",
            "authentication_error",
            "authentication failed",
            "unauthorized",
            "login required",
            "oauth token",
            "401",
        )
    ):
        return AccountFailureKind.AUTH_OR_SESSION_INVALID
    if any(
        x in value
        for x in (
            "quota",
            "usage limit",
            "limit reached",
            "rate limit",
            "rate_limit",
            "ratelimit",
            "429",
            "overloaded_error",
        )
    ):
        return AccountFailureKind.QUOTA_EXHAUSTED
    if "account disabled" in value or "organization has been disabled" in value:
        return AccountFailureKind.ACCOUNT_DISABLED
    if "cancel" in value:
        return AccountFailureKind.CANCELLED
    return AccountFailureKind.UNKNOWN


class ClaudeAccountPoolManager:
    """File-lock-backed allocator shared by local external-worker processes."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        cooldown_seconds: float = 300.0,
        host_identity: str | None = None,
        identity_observer: IdentityObserver | None = None,
    ) -> None:
        self.root = Path(root or Path.home() / ".nexus/claude-account-pool").expanduser()
        self.state_path = self.root / "state.json"
        self.lock_path = self.root / "pool.lock"
        self.cooldown_seconds = float(cooldown_seconds)
        self.identity_observer = identity_observer or default_identity_observer
        if host_identity is None:
            try:
                host_identity = _machine_identity()
            except GrokAccountPoolError as exc:
                raise ClaudeAccountPoolError("CLAUDE_HOST_IDENTITY_UNAVAILABLE") from exc
        self.host_id_hash = _host_identity_hash(host_identity)

    # -- state ----------------------------------------------------------
    def _load_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ClaudeAccountPoolExhaustedError("CLAUDE_ACCOUNT_POOL_STATE_MISSING") from exc
        except json.JSONDecodeError as exc:
            raise ClaudeAccountPoolError("CLAUDE_ACCOUNT_POOL_STATE_INVALID") from exc
        if not isinstance(value, dict) or not isinstance(value.get("accounts"), dict):
            raise ClaudeAccountPoolError("CLAUDE_ACCOUNT_POOL_STATE_INVALID")
        if value.get("leases") is None:
            value["leases"] = {}
        elif not isinstance(value.get("leases"), dict):
            raise ClaudeAccountPoolError("CLAUDE_ACCOUNT_POOL_LEASES_INVALID")
        return value

    def _load_state_or_empty(self) -> dict[str, Any]:
        try:
            return self._load_state()
        except ClaudeAccountPoolExhaustedError as exc:
            if str(exc) != "CLAUDE_ACCOUNT_POOL_STATE_MISSING":
                raise
            return {"accounts": {}, "leases": {}, "updated_at": 0.0}

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
    def _unlock(fh) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()

    # -- host binding ---------------------------------------------------
    def _host_binding_from_state(self, state: dict[str, Any]) -> ClaudeHostBinding:
        raw = state.get("host_binding")
        if raw is None:
            return ClaudeHostBinding("UNBOUND", None, self.host_id_hash, False)
        if (
            not isinstance(raw, dict)
            or raw.get("schema") != _HOST_BINDING_SCHEMA
            or not _FINGERPRINT_RE.fullmatch(str(raw.get("host_id_hash")))
        ):
            raise ClaudeAccountPoolError("CLAUDE_ACCOUNT_POOL_HOST_BINDING_INVALID")
        owner = str(raw["host_id_hash"])
        matches = owner == self.host_id_hash
        return ClaudeHostBinding(
            "BOUND" if matches else "HOST_MISMATCH", owner, self.host_id_hash, matches
        )

    def _assert_host_binding(self, state: dict[str, Any]) -> None:
        binding = self._host_binding_from_state(state)
        if binding.owner_host_id_hash is None:
            if state.get("accounts"):
                raise ClaudeAccountPoolError("CLAUDE_ACCOUNT_POOL_HOST_UNBOUND")
            return
        if not binding.matches:
            raise ClaudeAccountPoolError("CLAUDE_ACCOUNT_POOL_HOST_MISMATCH")

    def host_binding(self) -> ClaudeHostBinding:
        lock = self._lock()
        try:
            return self._host_binding_from_state(self._load_state_or_empty())
        finally:
            self._unlock(lock)

    def bind_host(self, *, confirm_existing_pool: bool = False) -> ClaudeHostBinding:
        lock = self._lock()
        try:
            state = self._load_state_or_empty()
            binding = self._host_binding_from_state(state)
            if binding.owner_host_id_hash is not None:
                if not binding.matches:
                    raise ClaudeAccountPoolError("CLAUDE_ACCOUNT_POOL_HOST_MISMATCH")
                return binding
            if state.get("accounts") and not confirm_existing_pool:
                raise ClaudeAccountPoolError(
                    "CLAUDE_ACCOUNT_POOL_HOST_BINDING_CONFIRMATION_REQUIRED"
                )
            state["host_binding"] = {
                "schema": _HOST_BINDING_SCHEMA,
                "host_id_hash": self.host_id_hash,
                "bound_at": time.time(),
            }
            state["updated_at"] = time.time()
            self._write_state(state)
            return self._host_binding_from_state(state)
        finally:
            self._unlock(lock)

    # -- inventory ------------------------------------------------------
    @staticmethod
    def _account_view(alias: str, record: dict[str, Any], leased: bool) -> ClaudeLocalAccount:
        raw = str(record.get("config_dir") or "")
        return ClaudeLocalAccount(
            alias=str(alias),
            config_dir=raw,
            approved_identity_fingerprint=str(record.get("approved_identity_fingerprint") or ""),
            enabled=bool(record.get("enabled", True)),
            cooldown_until=float(record.get("cooldown_until") or 0.0),
            last_failure_reason=str(record.get("last_failure_reason") or ""),
            last_failure_timestamp=float(record.get("last_failure_timestamp") or 0.0),
            last_used_at=float(record.get("last_used_at") or 0.0),
            leased=leased,
            config_dir_exists=Path(raw).expanduser().is_dir(),
        )

    def local_accounts(self) -> tuple[ClaudeLocalAccount, ...]:
        lock = self._lock()
        try:
            state = self._load_state_or_empty()
            self._assert_host_binding(state)
            held = {
                str(r.get("alias"))
                for r in state["leases"].values()
                if isinstance(r, dict) and r.get("alias") and self._lease_live(r)
            }
            result = []
            for alias, record in sorted(state["accounts"].items()):
                if not isinstance(record, dict):
                    raise ClaudeAccountPoolError("CLAUDE_ACCOUNT_RECORD_INVALID")
                result.append(self._account_view(alias, record, str(alias) in held))
            return tuple(result)
        finally:
            self._unlock(lock)

    def register_local_profile(
        self,
        *,
        alias: str,
        config_dir: str | Path,
        approved_identity_fingerprint: str,
    ) -> ClaudeLocalAccount:
        """Register one already-logged-in profile directory with its approved identity hash."""

        normalized_alias = str(alias).strip()
        if not _ALIAS_RE.fullmatch(normalized_alias):
            raise ClaudeAccountPoolError("CLAUDE_ACCOUNT_ALIAS_INVALID")
        fingerprint = str(approved_identity_fingerprint).strip().lower()
        if not _FINGERPRINT_RE.fullmatch(fingerprint):
            raise ClaudeAccountPoolError("CLAUDE_APPROVED_IDENTITY_FINGERPRINT_INVALID")
        source = Path(config_dir).expanduser()
        if not source.is_absolute() or not source.is_dir():
            raise ClaudeAccountPoolError("CLAUDE_PROFILE_CONFIG_DIR_INVALID")
        if stat.S_IMODE(source.stat().st_mode) & 0o077:
            raise ClaudeAccountPoolError("CLAUDE_PROFILE_CONFIG_DIR_PERMISSIONS_TOO_OPEN")
        resolved = source.resolve()
        if is_default_profile_path(resolved):
            raise ClaudeAccountPoolError("CLAUDE_DEFAULT_PROFILE_NOT_ALLOWED")

        lock = self._lock()
        try:
            state = self._load_state_or_empty()
            self._prune_dead_leases(state)
            accounts = state.setdefault("accounts", {})
            binding = self._host_binding_from_state(state)
            if binding.owner_host_id_hash is None:
                if accounts:
                    raise ClaudeAccountPoolError("CLAUDE_ACCOUNT_POOL_HOST_UNBOUND")
                state["host_binding"] = {
                    "schema": _HOST_BINDING_SCHEMA,
                    "host_id_hash": self.host_id_hash,
                    "bound_at": time.time(),
                }
            elif not binding.matches:
                raise ClaudeAccountPoolError("CLAUDE_ACCOUNT_POOL_HOST_MISMATCH")
            if normalized_alias in accounts:
                raise ClaudeAccountPoolError("CLAUDE_ACCOUNT_ALIAS_ALREADY_REGISTERED")
            for record in accounts.values():
                if not isinstance(record, dict):
                    raise ClaudeAccountPoolError("CLAUDE_ACCOUNT_RECORD_INVALID")
                if str(record.get("config_dir") or "") == str(resolved):
                    raise ClaudeAccountPoolError("CLAUDE_PROFILE_CONFIG_DIR_ALREADY_REGISTERED")
                if record.get("approved_identity_fingerprint") == fingerprint:
                    raise ClaudeAccountPoolError("CLAUDE_APPROVED_IDENTITY_ALREADY_REGISTERED")
            record = {
                "config_dir": str(resolved),
                "approved_identity_fingerprint": fingerprint,
                "enabled": True,
                "cooldown_until": 0.0,
                "last_failure_reason": "",
                "last_failure_timestamp": 0.0,
                "last_used_at": 0.0,
            }
            accounts[normalized_alias] = record
            state["updated_at"] = time.time()
            self._write_state(state)
            return self._account_view(normalized_alias, record, False)
        finally:
            self._unlock(lock)

    # -- leases ---------------------------------------------------------
    @staticmethod
    def _pgid_alive(pgid: object) -> bool:
        if not isinstance(pgid, int) or pgid <= 0:
            return False
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @classmethod
    def _lease_live(cls, record: dict[str, Any]) -> bool:
        """A lease is reclaimable only if dispatcher AND provider process are both dead."""

        if record.get("unknown_outcome") or _pid_alive(record.get("pid")):
            return True
        if _pid_alive(record.get("provider_pid")) or cls._pgid_alive(record.get("provider_pgid")):
            # Dispatcher died but the provider may still be producing effects.
            record["unknown_outcome"] = True
            record["unknown_outcome_at"] = time.time()
            return True
        return False

    @classmethod
    def _prune_dead_leases(cls, state: dict[str, Any]) -> None:
        leases = state.setdefault("leases", {})
        for lease_id, record in list(leases.items()):
            if not isinstance(record, dict) or not cls._lease_live(record):
                leases.pop(lease_id, None)

    def _prune_and_persist(self, state: dict[str, Any]) -> None:
        """Prune, persisting any reclaim/unknown-outcome marking even if the caller fails."""

        before = json.dumps(state.get("leases", {}), sort_keys=True)
        self._prune_dead_leases(state)
        if json.dumps(state["leases"], sort_keys=True) != before:
            state["updated_at"] = time.time()
            self._write_state(state)

    def attach_provider(self, lease: ClaudeLease, provider_pid: int) -> None:
        """Record the provider pid/pgid (provider runs in its own session)."""

        if not isinstance(provider_pid, int) or provider_pid <= 0:
            raise ClaudeAccountPoolError("CLAUDE_PROVIDER_PID_INVALID")
        lock = self._lock()
        try:
            state = self._load_state()
            self._assert_host_binding(state)
            record = self._record_for(state, lease)
            record["provider_pid"] = provider_pid
            try:
                record["provider_pgid"] = os.getpgid(provider_pid)
            except OSError:
                record["provider_pgid"] = provider_pid
            state["updated_at"] = time.time()
            self._write_state(state)
        finally:
            self._unlock(lock)

    @staticmethod
    def _eligible(state: dict[str, Any], now: float) -> list[tuple[str, dict[str, Any]]]:
        held = {
            str(r.get("alias"))
            for r in state.get("leases", {}).values()
            if isinstance(r, dict) and r.get("alias")
        }
        result = []
        for alias, record in state["accounts"].items():
            if not isinstance(record, dict) or not bool(record.get("enabled", True)):
                continue
            if float(record.get("cooldown_until") or 0.0) > now or alias in held:
                continue
            if not Path(str(record.get("config_dir") or "")).expanduser().is_dir():
                continue
            if not _FINGERPRINT_RE.fullmatch(str(record.get("approved_identity_fingerprint"))):
                continue
            result.append((str(alias), record))
        return result

    def _acquire_locked(
        self,
        state: dict[str, Any],
        consumer_id: str,
        *,
        exclude_alias: str | None = None,
    ) -> tuple[ClaudeLease, str]:
        candidates = [
            item for item in self._eligible(state, time.time()) if item[0] != exclude_alias
        ]
        if not candidates:
            raise ClaudeAccountPoolExhaustedError("CLAUDE_ACCOUNT_POOL_EXHAUSTED")
        candidates.sort(key=lambda item: (float(item[1].get("last_used_at") or 0.0), item[0]))
        alias, record = candidates[0]
        env = build_claude_profile_env(str(record["config_dir"]))
        lease_id = "claudelease_" + uuid.uuid4().hex
        now = time.time()
        state.setdefault("leases", {})[lease_id] = {
            "alias": alias,
            "consumer_id": consumer_id,
            "pid": os.getpid(),
            "acquired_at": now,
            "unknown_outcome": False,
        }
        record["last_used_at"] = now
        state["updated_at"] = now
        self._write_state(state)
        lease = ClaudeLease(lease_id, consumer_id, _hash(alias), env)
        return lease, alias

    def _verify_identity(self, lease: ClaudeLease, alias: str) -> None:
        """Fail closed: drop the lease and cool the account unless identity matches approval."""

        lock = self._lock()
        try:
            state = self._load_state()
            account = state["accounts"].get(alias)
            approved = (
                str(account.get("approved_identity_fingerprint") or "")
                if isinstance(account, dict)
                else ""
            )
            config_dir = Path(lease.execution_env.get("CLAUDE_CONFIG_DIR", ""))
        finally:
            self._unlock(lock)
        observed: str | None
        try:
            observed = self.identity_observer(config_dir)
        except Exception:
            observed = None
        error: str | None = None
        if is_default_profile_path(config_dir):
            error = "CLAUDE_DEFAULT_PROFILE_NOT_ALLOWED"
        elif not approved or not _FINGERPRINT_RE.fullmatch(approved):
            error = "CLAUDE_ACCOUNT_IDENTITY_UNAPPROVED"
        elif not isinstance(observed, str) or not observed:
            error = "CLAUDE_ACCOUNT_IDENTITY_MISSING"
        elif not hmac.compare_digest(observed.strip().lower(), approved):
            error = "CLAUDE_ACCOUNT_IDENTITY_MISMATCH"
        if error is None:
            return
        lock = self._lock()
        try:
            state = self._load_state()
            state["leases"].pop(lease.lease_id, None)
            account = state["accounts"].get(alias)
            if isinstance(account, dict):
                now = time.time()
                account["cooldown_until"] = now + self.cooldown_seconds
                account["last_failure_timestamp"] = now
                account["last_failure_reason"] = error
            state["updated_at"] = time.time()
            self._write_state(state)
        finally:
            self._unlock(lock)
        raise ClaudeAccountIdentityError(error)

    def acquire(self, consumer_id: str) -> ClaudeLease:
        consumer = str(consumer_id).strip()
        if not consumer:
            raise ClaudeAccountPoolError("CLAUDE_CONSUMER_ID_REQUIRED")
        lock = self._lock()
        try:
            state = self._load_state()
            self._assert_host_binding(state)
            self._prune_and_persist(state)
            if any(
                isinstance(r, dict) and r.get("consumer_id") == consumer
                for r in state["leases"].values()
            ):
                raise ClaudeAccountPoolError("CLAUDE_CONSUMER_ALREADY_BOUND")
            lease, alias = self._acquire_locked(state, consumer)
        finally:
            self._unlock(lock)
        self._verify_identity(lease, alias)
        return lease

    def _record_for(self, state: dict[str, Any], lease: ClaudeLease) -> dict[str, Any]:
        record = state["leases"].get(lease.lease_id)
        if (
            not isinstance(record, dict)
            or record.get("consumer_id") != lease.consumer_id
            or _hash(str(record.get("alias") or "")) != lease.account_alias_hash
        ):
            raise ClaudeAccountPoolError("CLAUDE_INVALID_ACCOUNT_LEASE")
        return record

    def release(self, lease: ClaudeLease) -> None:
        """Release on a known terminal outcome. A lease marked UNKNOWN_OUTCOME is kept."""

        lock = self._lock()
        try:
            state = self._load_state()
            self._assert_host_binding(state)
            self._prune_dead_leases(state)
            record = self._record_for(state, lease)
            if record.get("unknown_outcome"):
                return
            state["leases"].pop(lease.lease_id, None)
            state["updated_at"] = time.time()
            self._write_state(state)
        finally:
            self._unlock(lock)

    def mark_unknown_outcome(self, lease: ClaudeLease) -> None:
        """Keep the account blocked until `reconcile_release` (effects may have occurred)."""

        lock = self._lock()
        try:
            state = self._load_state()
            self._assert_host_binding(state)
            record = self._record_for(state, lease)
            record["unknown_outcome"] = True
            record["unknown_outcome_at"] = time.time()
            state["updated_at"] = time.time()
            self._write_state(state)
        finally:
            self._unlock(lock)

    def unknown_outcome_leases(self) -> tuple[str, ...]:
        lock = self._lock()
        try:
            state = self._load_state_or_empty()
            return tuple(
                sorted(
                    lease_id
                    for lease_id, r in state["leases"].items()
                    if isinstance(r, dict) and r.get("unknown_outcome")
                )
            )
        finally:
            self._unlock(lock)

    def reconcile_release(self, lease_id: str) -> None:
        """Explicit operator reconciliation of one UNKNOWN_OUTCOME lease."""

        lock = self._lock()
        try:
            state = self._load_state()
            self._assert_host_binding(state)
            record = state["leases"].get(str(lease_id))
            if not isinstance(record, dict) or not record.get("unknown_outcome"):
                raise ClaudeAccountPoolError("CLAUDE_LEASE_NOT_UNKNOWN_OUTCOME")
            state["leases"].pop(str(lease_id), None)
            state["updated_at"] = time.time()
            self._write_state(state)
        finally:
            self._unlock(lock)

    def report_failure(
        self,
        lease: ClaudeLease,
        failure_kind: AccountFailureKind,
    ) -> ClaudeLease | None:
        """Rotate only for known account-scoped failures; never for timeout/unknown."""

        lock = self._lock()
        replacement: tuple[ClaudeLease, str] | None = None
        try:
            state = self._load_state()
            self._assert_host_binding(state)
            if failure_kind in _NO_ROTATION_KINDS:
                # Never rotate around a per-person limit; cool the account so new
                # tasks stop picking it. The caller releases its own lease.
                self._prune_dead_leases(state)
                record = self._record_for(state, lease)
                account = state["accounts"].get(str(record.get("alias") or ""))
                if isinstance(account, dict):
                    now = time.time()
                    account["cooldown_until"] = now + self.cooldown_seconds
                    account["last_failure_timestamp"] = now
                    account["last_failure_reason"] = failure_kind.value
                    state["updated_at"] = now
                    self._write_state(state)
                return None
            if not is_rotation_eligible(failure_kind):
                return None
            self._prune_dead_leases(state)
            record = self._record_for(state, lease)
            if record.get("unknown_outcome"):
                return None
            alias = str(record.get("alias") or "")
            account = state["accounts"].get(alias)
            if not isinstance(account, dict):
                raise ClaudeAccountPoolError("CLAUDE_ACCOUNT_RECORD_MISSING")
            now = time.time()
            account["cooldown_until"] = now + self.cooldown_seconds
            account["last_failure_timestamp"] = now
            account["last_failure_reason"] = failure_kind.value
            state["leases"].pop(lease.lease_id, None)
            try:
                replacement = self._acquire_locked(state, lease.consumer_id, exclude_alias=alias)
            except ClaudeAccountPoolExhaustedError:
                state["updated_at"] = now
                self._write_state(state)
                raise
        finally:
            self._unlock(lock)
        new_lease, new_alias = replacement
        self._verify_identity(new_lease, new_alias)
        return new_lease


_GLOBAL_MANAGER: ClaudeAccountPoolManager | None = None


def get_claude_account_pool_manager() -> ClaudeAccountPoolManager:
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        configured = os.getenv("NEXUS_CLAUDE_ACCOUNT_POOL_DIR", "").strip()
        _GLOBAL_MANAGER = ClaudeAccountPoolManager(
            Path(configured).expanduser() if configured else None
        )
    return _GLOBAL_MANAGER


def set_claude_account_pool_manager(manager: ClaudeAccountPoolManager | None) -> None:
    global _GLOBAL_MANAGER
    _GLOBAL_MANAGER = manager
