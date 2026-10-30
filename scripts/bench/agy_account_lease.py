"""Account lease, 5-hour quota admission and observed-model identity for bench Agy calls (#1932).

Bench Agy calls used to run on the default HOME account with no ``--model``, so a run could
neither prove which account paid for it nor which model answered. This module supplies the
three pieces a requalification needs:

* **Permission posture.** :func:`assert_contained_agy_argv` rejects any argv that is not
  ``--mode plan --sandbox`` or that carries a permission-bypass flag.
* **Observed model.** Agy logs ``Resolving model <id>`` (and ``model alias "<a>" resolved to
  "<id>"``) plus the backend label it actually propagates
  (``Propagating selected model override to backend: label="Gemini 3.8 Flash (Medium)"``).
  The ``Resolving`` line only echoes the request: Agy has been seen to log
  ``Resolving model claude-sonnet-5-5-medium`` and then propagate ``Gemini 3.8 Flash (High)``.
  :func:`model_identity_verdict` therefore requires every resolved id *and* every backend
  label to match the requested id, and fails closed with ``MODEL_IDENTITY_MISMATCH`` or
  ``MODEL_IDENTITY_UNOBSERVED``.
* **Account lease.** :func:`run_with_account_lease` claims one account through the shared
  :class:`CrossProcessLeaseCoordinator` (the same leases directory the dispatcher and #1216 V11
  use, so an account another process holds is skipped), restricted to an explicit allowlist and
  to accounts whose 5-hour quota window is available in the quota snapshot. A quota error before
  any provider effect retires the account for the model family and rotates; after an effect the
  run is retired, never retried (``PROVIDER_QUOTA_EXHAUSTED_AFTER_EFFECT``). The lease is always
  released.

The quota snapshot (``~/.nexus/agy-account-pool/quota-snapshot.json``) is read only.
"""

from __future__ import annotations

import contextlib
import json
import re
import signal
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from nexus.services.agy_account_pool import (
    AccountLeaseClaim,
    AgyAccount,
    AgyAccountPoolBusyError,
    AgyAccountPoolError,
    AgyAccountPoolExhaustedError,
    AgyAccountPoolManager,
    CrossProcessLeaseCoordinator,
    agy_pool_stopped,
    build_isolated_env,
)
from nexus.services.external_account_pool import AccountFailureKind

# ---------------------------------------------------------------------------
# Permission posture
# ---------------------------------------------------------------------------

AGY_REQUIRED_MODE = "plan"
AGY_BYPASS_FLAGS = frozenset({
    "--dangerously-skip-permissions",
    "--auto-approve",
    "--yolo",
})
AGY_POSTURE_VIOLATION = "AGY_PERMISSION_POSTURE_VIOLATION"


def assert_contained_agy_argv(argv: Sequence[str]) -> None:
    """Raise unless argv is ``--mode plan --sandbox`` with ``--model`` and no bypass flag."""
    args = [str(item) for item in argv]
    flags = args[: args.index("--print")] if "--print" in args else args
    for item in flags:
        if item.split("=", 1)[0] in AGY_BYPASS_FLAGS:
            raise ValueError(f"{AGY_POSTURE_VIOLATION}:bypass_flag:{item}")
    modes = [flags[i + 1] for i, item in enumerate(flags[:-1]) if item == "--mode"]
    if modes != [AGY_REQUIRED_MODE]:
        raise ValueError(f"{AGY_POSTURE_VIOLATION}:mode:{modes}")
    if "--sandbox" not in flags:
        raise ValueError(f"{AGY_POSTURE_VIOLATION}:sandbox_missing")
    models = [flags[i + 1] for i, item in enumerate(flags[:-1]) if item == "--model"]
    if len(models) != 1 or not models[0].strip():
        raise ValueError(f"{AGY_POSTURE_VIOLATION}:model:{models}")


# ---------------------------------------------------------------------------
# Observed model identity
# ---------------------------------------------------------------------------

MODEL_IDENTITY_OK = "MODEL_IDENTITY_OK"
MODEL_IDENTITY_MISMATCH = "MODEL_IDENTITY_MISMATCH"
MODEL_IDENTITY_UNOBSERVED = "MODEL_IDENTITY_UNOBSERVED"

# Same patterns as scripts/ops/nexus-agy-dispatch (_parse_agy_attestation), plus the backend label.
_AGY_ALIAS_RESOLUTION_RE = re.compile(
    r'model alias "(?P<alias>[^"\n]+)" resolved to "(?P<resolved>[^"\n]+)"'
)
_AGY_RESOLVING_MODEL_RE = re.compile(r"Resolving model (?P<resolved>[^\s]+)")
_AGY_BACKEND_LABEL_RE = re.compile(
    r'Propagating selected model override to backend: label="(?P<label>[^"\n]+)"'
)
_AGY_CONVERSATION_RE = re.compile(r"Created conversation (?P<conversation>[0-9a-fA-F-]{36})")


def _identity_token(value: str) -> str:
    """``gemini-3.8-flash-medium`` and ``Gemini 3.8 Flash (Medium)`` share one token."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def parse_agy_model_observation(log_text: str) -> dict[str, Any]:
    aliases = {
        m.group("alias"): m.group("resolved") for m in _AGY_ALIAS_RESOLUTION_RE.finditer(log_text)
    }
    resolving = [m.group("resolved") for m in _AGY_RESOLVING_MODEL_RE.finditer(log_text)]
    resolved_ids = sorted({aliases.get(item, item) for item in resolving} | set(aliases.values()))
    labels = sorted({m.group("label") for m in _AGY_BACKEND_LABEL_RE.finditer(log_text)})
    conversations = [m.group("conversation") for m in _AGY_CONVERSATION_RE.finditer(log_text)]
    return {
        "resolved_model_ids": resolved_ids,
        "backend_labels": labels,
        "provider_session_id": conversations[-1] if conversations else None,
    }


def read_agy_model_observation(log_path: Path | None) -> dict[str, Any]:
    text = ""
    if log_path is not None:
        try:
            text = Path(log_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
    return parse_agy_model_observation(text)


def model_identity_verdict(requested_model: str, observation: Mapping[str, Any]) -> dict[str, Any]:
    """Compare the requested id with what Agy resolved *and* propagated to the backend."""
    ids = [str(item) for item in observation.get("resolved_model_ids") or []]
    labels = [str(item) for item in observation.get("backend_labels") or []]
    wanted = _identity_token(requested_model)
    record: dict[str, Any] = {
        "requested_model": requested_model,
        "observed_model": ids[0] if len(ids) == 1 else (",".join(ids) or None),
        "observed_model_label": labels[0] if len(labels) == 1 else (",".join(labels) or None),
        "provider_session_id": observation.get("provider_session_id"),
    }
    if not ids or not labels:
        missing = [
            name
            for name, values in (("resolved_model", ids), ("backend_label", labels))
            if not values
        ]
        return {
            **record,
            "model_identity_status": MODEL_IDENTITY_UNOBSERVED,
            "model_identity_reason": "missing:" + ",".join(missing),
        }
    if ids != [requested_model]:
        return {
            **record,
            "model_identity_status": MODEL_IDENTITY_MISMATCH,
            "model_identity_reason": "resolved_model_differs",
        }
    if any(_identity_token(label) != wanted for label in labels):
        return {
            **record,
            "model_identity_status": MODEL_IDENTITY_MISMATCH,
            "model_identity_reason": "backend_label_differs",
        }
    return {**record, "model_identity_status": MODEL_IDENTITY_OK, "model_identity_reason": ""}


# ---------------------------------------------------------------------------
# 5-hour quota window admission (read-only snapshot)
# ---------------------------------------------------------------------------

QUOTA_SNAPSHOT_ENV = "NEXUS_AGY_QUOTA_SNAPSHOT"
QUOTA_MAX_AGE_ENV = "NEXUS_AGY_QUOTA_MAX_AGE_SECONDS"
DEFAULT_QUOTA_MAX_AGE_SECONDS = 300.0  # same default as nexus-agy-dispatch
ACCOUNT_ALLOWLIST_ENV = "NEXUS_AGY_ACCOUNT_ALLOWLIST"
ALLOW_UNKNOWN_QUOTA_WINDOW_ENV = "NEXUS_AGY_ALLOW_UNKNOWN_QUOTA_WINDOW"

FIVE_HOUR_AVAILABLE = "FIVE_HOUR_AVAILABLE"
QUOTA_5H_EXHAUSTED = "QUOTA_5H_EXHAUSTED"
QUOTA_WEEKLY_EXHAUSTED = "QUOTA_WEEKLY_EXHAUSTED"
QUOTA_WINDOW_UNKNOWN = "QUOTA_WINDOW_UNKNOWN"
QUOTA_SNAPSHOT_STALE = "QUOTA_SNAPSHOT_STALE"
NOT_IN_ALLOWLIST = "NOT_IN_ALLOWLIST"
_OVERRIDABLE_QUOTA_STATES = frozenset({QUOTA_WINDOW_UNKNOWN, QUOTA_SNAPSHOT_STALE})

QUOTA_GROUPS = {"gemini": "Gemini Models", "claude_gpt": "Claude and GPT models"}

NO_ELIGIBLE_ACCOUNT = "AGY_NO_ELIGIBLE_ACCOUNT"
POOL_BUSY = "AGY_ACCOUNT_POOL_BUSY"
POOL_EXHAUSTED = "AGY_ACCOUNT_POOL_EXHAUSTED"
POOL_RUNTIME_MISSING = "AGY_ACCOUNT_POOL_RUNTIME_MISSING"
# #2998: the Agy pool is stopped (NEXUS_AGY_POOL_STOPPED_OVERRIDE not "1").
POOL_STOPPED = "AGY_ACCOUNT_POOL_STOPPED"
QUOTA_EXHAUSTED_PRE_EFFECT = "PROVIDER_QUOTA_EXHAUSTED_PRE_EFFECT"
QUOTA_EXHAUSTED_AFTER_EFFECT = "PROVIDER_QUOTA_EXHAUSTED_AFTER_EFFECT"
QUOTA_EXHAUSTED_UNKNOWN_EFFECT = "PROVIDER_QUOTA_EXHAUSTED_UNKNOWN_EFFECT"
QUOTA_ROTATIONS_EXHAUSTED = "PROVIDER_QUOTA_ROTATIONS_EXHAUSTED"
# Failures decided before any Agy process starts: no model call happened.
PRE_CALL_LEASE_FAILURES = frozenset({
    NO_ELIGIBLE_ACCOUNT,
    QUOTA_WINDOW_UNKNOWN,
    POOL_BUSY,
    POOL_EXHAUSTED,
    POOL_RUNTIME_MISSING,
    POOL_STOPPED,
})


def agy_model_family(model: str) -> str | None:
    value = str(model or "").strip().lower()
    if value.startswith("gemini-"):
        return "gemini"
    if value.startswith(("claude-", "gpt-")):
        return "claude_gpt"
    return None


def _parse_ts(value: object) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _window_state(window: object, *, now_ts: float) -> str:
    """``available`` / ``exhausted`` / ``unknown`` for one quota window (dispatcher semantics)."""
    if not isinstance(window, Mapping):
        return "unknown"
    status = window.get("status")
    if status == "disabled":
        return "exhausted"
    if status != "known":
        return "unknown"
    remaining = window.get("remaining_pct")
    reset_ts = _parse_ts(window.get("reset_at"))
    if isinstance(remaining, (int, float)) and float(remaining) > 0.0:
        return "available"
    if reset_ts is not None and reset_ts <= now_ts:
        return "available"  # the window rolled over after the row was checked
    if isinstance(remaining, (int, float)):
        return "exhausted"
    return "unknown"


def classify_account_quota(
    row: Mapping[str, Any] | None,
    *,
    snapshot_checked_at: object,
    family: str,
    now_ts: float,
    max_age_seconds: float,
) -> dict[str, Any]:
    """Classify one snapshot row by its **5-hour** window for the model family's quota group.

    Representation: ``row["groups"][<group>]["5h"]`` = ``{status, remaining_pct, reset_at}``
    next to a ``"weekly"`` window of the same shape. When the weekly window is spent the
    snapshot omits ``"5h"``; a missing ``"5h"`` is never treated as available.
    """
    if not isinstance(row, Mapping):
        return {"state": QUOTA_WINDOW_UNKNOWN, "detail": "account_not_in_snapshot"}
    checked_ts = _parse_ts(row.get("checked_at") or snapshot_checked_at)
    if checked_ts is None or not (-60.0 <= now_ts - checked_ts <= max(0.0, max_age_seconds)):
        return {
            "state": QUOTA_SNAPSHOT_STALE,
            "detail": "row_checked_at",
            "checked_at": row.get("checked_at") or snapshot_checked_at,
        }
    if row.get("ok") is not True:
        return {"state": QUOTA_WINDOW_UNKNOWN, "detail": "row_not_ok"}
    groups = row.get("groups")
    group = groups.get(QUOTA_GROUPS.get(family, "")) if isinstance(groups, Mapping) else None
    if not isinstance(group, Mapping):
        return {"state": QUOTA_WINDOW_UNKNOWN, "detail": "quota_group_missing"}
    if _window_state(group.get("weekly"), now_ts=now_ts) == "exhausted":
        return {"state": QUOTA_WEEKLY_EXHAUSTED, "detail": "weekly"}
    five_hour = group.get("5h")
    if five_hour is None:
        return {"state": QUOTA_WINDOW_UNKNOWN, "detail": "five_hour_window_missing"}
    state = _window_state(five_hour, now_ts=now_ts)
    detail = {
        "five_hour_remaining_pct": five_hour.get("remaining_pct")
        if isinstance(five_hour, Mapping)
        else None,
        "five_hour_reset_at": five_hour.get("reset_at") if isinstance(five_hour, Mapping) else None,
    }
    if state == "available":
        return {"state": FIVE_HOUR_AVAILABLE, **detail}
    if state == "exhausted":
        return {"state": QUOTA_5H_EXHAUSTED, **detail}
    return {"state": QUOTA_WINDOW_UNKNOWN, "detail": "five_hour_window_unknown", **detail}


def load_quota_snapshot(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def account_eligibility(
    account_names: Sequence[str],
    snapshot: Mapping[str, Any],
    *,
    family: str,
    allowlist: Sequence[str] = (),
    allow_unknown_quota_window: bool = False,
    now_ts: float | None = None,
    max_age_seconds: float = DEFAULT_QUOTA_MAX_AGE_SECONDS,
) -> dict[str, dict[str, Any]]:
    """Per account: quota state and whether the bench may lease it."""
    current = time.time() if now_ts is None else float(now_ts)
    rows = {
        str(row.get("account")): row
        for row in snapshot.get("accounts") or []
        if isinstance(row, Mapping) and isinstance(row.get("account"), str)
    }
    allowed = {str(item).strip() for item in allowlist if str(item).strip()}
    result: dict[str, dict[str, Any]] = {}
    for name in account_names:
        if allowed and name not in allowed:
            result[name] = {"state": NOT_IN_ALLOWLIST, "eligible": False}
            continue
        info = classify_account_quota(
            rows.get(name),
            snapshot_checked_at=snapshot.get("checked_at"),
            family=family,
            now_ts=current,
            max_age_seconds=max_age_seconds,
        )
        eligible = info["state"] == FIVE_HOUR_AVAILABLE or (
            allow_unknown_quota_window and info["state"] in _OVERRIDABLE_QUOTA_STATES
        )
        result[name] = {**info, "eligible": eligible}
    return result


# ---------------------------------------------------------------------------
# Lease configuration and coordinator
# ---------------------------------------------------------------------------

POOL_FIXTURE_ENV = "NEXUS_AGY_BENCH_POOL_FIXTURE"


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _split_names(value: object) -> tuple[str, ...]:
    return tuple(item.strip() for item in str(value or "").split(",") if item.strip())


@dataclass(frozen=True)
class BenchLeaseConfig:
    allowlist: tuple[str, ...] = ()
    allow_unknown_quota_window: bool = False
    quota_snapshot_path: Path = Path.home() / ".nexus/agy-account-pool/quota-snapshot.json"
    quota_max_age_seconds: float = DEFAULT_QUOTA_MAX_AGE_SECONDS
    wait_timeout: float = 15.0
    max_quota_rotations: int = 4

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str],
        *,
        allowlist: Sequence[str] | None = None,
        allow_unknown_quota_window: bool | None = None,
    ) -> BenchLeaseConfig:
        try:
            max_age = max(0.0, float(env.get(QUOTA_MAX_AGE_ENV) or DEFAULT_QUOTA_MAX_AGE_SECONDS))
        except ValueError:
            max_age = DEFAULT_QUOTA_MAX_AGE_SECONDS
        try:
            wait = max(0.0, float(env.get("NEXUS_AGY_BENCH_POOL_WAIT_SECONDS") or 15.0))
        except ValueError:
            wait = 15.0
        snapshot = str(env.get(QUOTA_SNAPSHOT_ENV) or "").strip()
        return cls(
            allowlist=tuple(allowlist)
            if allowlist is not None
            else _split_names(env.get(ACCOUNT_ALLOWLIST_ENV)),
            allow_unknown_quota_window=(
                bool(allow_unknown_quota_window)
                if allow_unknown_quota_window is not None
                else _truthy(env.get(ALLOW_UNKNOWN_QUOTA_WINDOW_ENV))
            ),
            quota_snapshot_path=Path(snapshot).expanduser()
            if snapshot
            else cls.quota_snapshot_path,
            quota_max_age_seconds=max_age,
            wait_timeout=wait,
        )


def build_bench_lease_coordinator(
    env: Mapping[str, str],
) -> tuple[CrossProcessLeaseCoordinator, str]:
    """The shared pool coordinator; ``(coordinator, pool_source)``.

    ``NEXUS_AGY_BENCH_POOL_FIXTURE`` names a JSON fixture (accounts, leases dir, allocator lock)
    for offline tests; every result records ``account_pool_source`` so a fixture run can never
    pass for a real one. Otherwise the real ``agy-cli-manager`` pool is used, as in
    ``nexus-agy-dispatch``.
    """
    fixture = str(env.get(POOL_FIXTURE_ENV) or "").strip()
    if fixture:
        spec = json.loads(Path(fixture).read_text(encoding="utf-8"))
        manager = AgyAccountPoolManager(
            accounts=[
                AgyAccount(alias=str(a["alias"]), home_dir=str(a["home"])) for a in spec["accounts"]
            ],
            use_real_manager=False,
        )
        return (
            CrossProcessLeaseCoordinator(
                manager=manager,
                allocator_lock_path=Path(spec["allocator_lock_path"]),
                leases_dir=Path(spec["leases_dir"]),
            ),
            "fixture",
        )
    manager_path = AgyAccountPoolManager.resolve_manager_path()
    manager_root = AgyAccountPoolManager.resolve_manager_root(manager_path=manager_path)
    if not manager_path or not Path(manager_path).is_file() or not Path(manager_root).is_dir():
        raise AgyAccountPoolError(POOL_RUNTIME_MISSING)
    manager = AgyAccountPoolManager(
        manager_path=manager_path, manager_root=manager_root, use_real_manager=True
    )
    return CrossProcessLeaseCoordinator(manager=manager), "agy_cli_manager"


def _pool_inventory(coordinator: CrossProcessLeaseCoordinator) -> dict[str, str]:
    """``internal_id -> alias_hash`` for every account the pool knows."""
    pool = coordinator.manager._ensure_pool()
    return {str(rec.internal_id): str(rec.alias_hash) for rec in pool._accounts.values()}


# ---------------------------------------------------------------------------
# Leased execution
# ---------------------------------------------------------------------------


@dataclass
class AgyAttemptOutcome:
    """What one Agy attempt reports back to the lease loop."""

    result: Any
    quota_exhausted: bool = False
    # True: the provider produced output/tokens or touched the workdir; None: unknown.
    provider_effect: bool | None = False


@dataclass
class LeasedRunResult:
    status: str  # "completed" | "failed"
    result: Any = None
    failure_kind: str = ""
    run_retired: bool = False
    attempts: int = 0
    rotations: int = 0
    lease_records: list[dict[str, Any]] = field(default_factory=list)
    eligibility: dict[str, dict[str, Any]] = field(default_factory=dict)
    pool_source: str = ""

    def public_fields(self) -> dict[str, Any]:
        """Identity-safe receipt fields (alias hashes only, never account names)."""
        final = self.lease_records[-1] if self.lease_records else {}
        return {
            "account_pool_source": self.pool_source,
            "account_alias_hash": final.get("account_alias_hash", ""),
            "lease_id_hash": final.get("lease_id_hash", ""),
            "account_quota_state": final.get("quota_state", ""),
            "account_attempts": self.attempts,
            "account_rotations": self.rotations,
            "account_lease_records": list(self.lease_records),
            "run_retired": self.run_retired,
            "account_failure_kind": self.failure_kind,
            "eligible_account_count": sum(
                1 for info in self.eligibility.values() if info.get("eligible")
            ),
        }


QUOTA_FAILURE_MARKERS = (  # mirrors nexus-agy-dispatch _QUOTA_FAILURE_MARKERS
    "resource_exhausted",
    "exceeded your current quota",
    "insufficient_quota",
    "quota exhausted",
    "quota_exhausted",
    "quota exceeded",
    "quota limit reached",
    "quota limit exceeded",
)


def has_quota_failure_signal(text: str) -> bool:
    lowered = str(text or "").lower()
    return any(marker in lowered for marker in QUOTA_FAILURE_MARKERS)


# Only an error/fatal agent-executor line is terminal (nexus-agy-dispatch semantics).
_AGY_TERMINAL_EXECUTOR_ERROR_RE = re.compile(
    r"(?m)^[EF]\d{4}\s+\S+\s+\d+\s+errorreport\.go:\d+\]\s+"
    r"agent executor error:(?P<detail>[^\n]*)$"
)


def has_terminal_quota_log_signal(log_text: str) -> bool:
    return any(
        has_quota_failure_signal(match.group("detail"))
        for match in _AGY_TERMINAL_EXECUTOR_ERROR_RE.finditer(str(log_text or ""))
    )


def run_with_account_lease(
    *,
    model: str,
    attempt: Callable[[dict[str, str]], AgyAttemptOutcome],
    base_env: Mapping[str, str],
    config: BenchLeaseConfig,
    coordinator: CrossProcessLeaseCoordinator,
    pool_source: str = "",
    now_ts: float | None = None,
) -> LeasedRunResult:
    """Run ``attempt`` under one leased, allowlisted, 5h-available account; always release."""
    family = agy_model_family(model)
    run = LeasedRunResult(status="failed", pool_source=pool_source)
    if agy_pool_stopped():
        # #2998: refuse before reading the pool; acquire_claim refuses too.
        run.failure_kind = POOL_STOPPED
        return run
    try:
        inventory = _pool_inventory(coordinator)
    except AgyAccountPoolError as exc:
        run.failure_kind = (
            POOL_RUNTIME_MISSING if POOL_RUNTIME_MISSING in str(exc) else POOL_EXHAUSTED
        )
        return run
    if family is None:
        run.failure_kind = QUOTA_WINDOW_UNKNOWN
        run.eligibility = {
            name: {
                "state": QUOTA_WINDOW_UNKNOWN,
                "detail": "model_family_unknown",
                "eligible": False,
            }
            for name in inventory
        }
        return run
    run.eligibility = account_eligibility(
        sorted(inventory),
        load_quota_snapshot(config.quota_snapshot_path),
        family=family,
        allowlist=config.allowlist,
        allow_unknown_quota_window=config.allow_unknown_quota_window,
        now_ts=now_ts,
        max_age_seconds=config.quota_max_age_seconds,
    )
    eligible = {name for name, info in run.eligibility.items() if info.get("eligible")}
    if not eligible:
        considered = [
            info["state"] for info in run.eligibility.values() if info["state"] != NOT_IN_ALLOWLIST
        ]
        run.failure_kind = (
            QUOTA_WINDOW_UNKNOWN
            if considered and all(state in _OVERRIDABLE_QUOTA_STATES for state in considered)
            else NO_ELIGIBLE_ACCOUNT
        )
        return run
    # Never lease outside the eligible set: everything else is excluded up front.
    exclude = {alias_hash for name, alias_hash in inventory.items() if name not in eligible}
    consumer_id = "bench-agy-" + uuid.uuid4().hex
    while True:
        try:
            claim = coordinator.acquire_claim(
                consumer_id=consumer_id,
                exclude_hashes=set(exclude),
                wait_timeout=config.wait_timeout,
                model_family=family,
            )
        except AgyAccountPoolBusyError:
            run.failure_kind = POOL_BUSY
            return run
        except AgyAccountPoolExhaustedError:
            run.failure_kind = run.failure_kind or POOL_EXHAUSTED
            return run
        if claim.internal_id not in eligible:  # account registered after the inventory read
            claim.release()
            exclude.add(claim.account_alias_hash)
            continue
        outcome = _attempt_under_claim(run, claim, attempt, base_env, family)
        if not outcome.quota_exhausted:
            claim.release()
            run.status, run.result, run.failure_kind = "completed", outcome.result, ""
            return run
        run.result = outcome.result
        _retire(coordinator, claim, family)
        if outcome.provider_effect is False:
            exclude.add(claim.account_alias_hash)
            run.lease_records[-1]["outcome"] = QUOTA_EXHAUSTED_PRE_EFFECT
            if run.rotations >= config.max_quota_rotations:
                run.failure_kind = QUOTA_ROTATIONS_EXHAUSTED
                return run
            run.rotations += 1
            run.failure_kind = QUOTA_EXHAUSTED_PRE_EFFECT
            continue
        run.failure_kind = (
            QUOTA_EXHAUSTED_AFTER_EFFECT
            if outcome.provider_effect
            else QUOTA_EXHAUSTED_UNKNOWN_EFFECT
        )
        run.lease_records[-1]["outcome"] = run.failure_kind
        run.run_retired = True
        return run


@contextlib.contextmanager
def _sigterm_releases_claim() -> Iterator[None]:
    """Turn SIGTERM into SystemExit while an attempt holds a claim.

    A provider timeout terminates the leaseholder's whole process group (nexus-runtime
    transport). Python's default SIGTERM action exits without unwinding, which left the
    durable claim receipt behind and blocked the account (online A/B 20261013b). Raising
    SystemExit lets the ``except BaseException`` path below release the claim first.
    Signal handlers can only be set from the main thread; elsewhere this is a no-op.
    """
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def _raise_exit(signum: int, _frame: Any) -> None:
        raise SystemExit(128 + signum)

    previous = signal.signal(signal.SIGTERM, _raise_exit)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)


def _attempt_under_claim(
    run: LeasedRunResult,
    claim: AccountLeaseClaim,
    attempt: Callable[[dict[str, str]], AgyAttemptOutcome],
    base_env: Mapping[str, str],
    family: str,
) -> AgyAttemptOutcome:
    run.attempts += 1
    run.lease_records.append({
        "account_alias_hash": claim.account_alias_hash,
        "lease_id_hash": claim.lease_id_hash,
        "quota_state": run.eligibility.get(claim.internal_id, {}).get("state", ""),
        "model_family": family,
        "outcome": "",
    })
    try:
        home = str(claim.lease.execution_env.get("HOME") or "").strip()
        if not home:
            raise AgyAccountPoolError("LEASE_HOME_MISSING")
        # The leased account's HOME (its Agy credentials/config); sensitive API keys stripped.
        env = build_isolated_env(home_dir=home, base_env=dict(base_env))
        with _sigterm_releases_claim():
            outcome = attempt(env)
    except BaseException:
        claim.release()
        raise
    run.lease_records[-1]["outcome"] = "quota_exhausted" if outcome.quota_exhausted else "completed"
    return outcome


def _retire(
    coordinator: CrossProcessLeaseCoordinator, claim: AccountLeaseClaim, family: str
) -> None:
    try:
        coordinator.retire_failed_claim(
            claim, AccountFailureKind.QUOTA_EXHAUSTED, model_family=family
        )
    finally:
        claim.release()
