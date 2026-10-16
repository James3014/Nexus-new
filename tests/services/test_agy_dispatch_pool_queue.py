"""#2410: a busy pool queues, quota/auth failures rotate, exhaustion is real.

Covers the three Done-when cases of the Issue against the real
``CrossProcessLeaseCoordinator`` (per-account flocks in a temp leases dir):
a burst bigger than the pool completes by queueing, a quota failure on the
first account rotates and completes, and an all-cooling pool reports
``pool_exhausted`` with the earliest recovery time.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"
os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader("nexus_agy_dispatch_pool_queue", str(DISPATCH_PATH)).load_module()

from nexus.services.agy_account_pool import (  # noqa: E402
    AgyAccount,
    AgyAccountPoolManager,
    CrossProcessLeaseCoordinator,
)

GEMINI = "gemini-3.8-flash-high"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _fresh_snapshot(names: list[str]) -> dict:
    checked_at = datetime.now(timezone.utc).isoformat()
    return {
        "checked_at": checked_at,
        "accounts": [
            {
                "account": name,
                "checked_at": checked_at,
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": {"status": "known", "remaining_pct": 100.0, "reset_at": None}
                    }
                },
            }
            for name in names
        ],
    }


def _state() -> dict[str, object]:
    return {
        "family": "gemini",
        "snapshot_fresh": True,
        "preferred": [],
        "reserve": [],
        "fallback": [],
        "blocked": [],
        "unknown": [],
    }


@pytest.fixture
def pool_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEXUS_AGY_MODEL_CATALOG_CHECK", "0")
    monkeypatch.setenv("NEXUS_AGY_POOL_QUEUE_POLL_SECONDS", "0.1")
    monkeypatch.delenv("NEXUS_AGY_POOL_WAIT_TIMEOUT", raising=False)
    for name in (
        "NEXUS_AGY_PREFERRED_ACCOUNTS",
        "NEXUS_AGY_RESERVE_ACCOUNTS",
        "NEXUS_AGY_FALLBACK_ACCOUNTS",
        "NEXUS_AGY_BLOCKED_ACCOUNTS",
    ):
        monkeypatch.delenv(name, raising=False)
    metas: list[dict] = []
    lock = threading.Lock()

    def collect(meta: dict) -> None:
        with lock:
            metas.append(dict(meta))

    monkeypatch.setattr(dispatch, "emit_meta", collect)

    def make(names: list[str]):
        accounts = [
            AgyAccount(alias=name, home_dir=str(tmp_path / f"home-{name}")) for name in names
        ]
        for account in accounts:
            Path(account.home_dir).mkdir(parents=True, exist_ok=True)
        snapshot = _fresh_snapshot(names)
        monkeypatch.setattr(
            dispatch, "_apply_dynamic_availability", lambda _m: (snapshot, _state())
        )

        def coordinator() -> CrossProcessLeaseCoordinator:
            return CrossProcessLeaseCoordinator(
                manager=AgyAccountPoolManager(accounts=accounts, use_real_manager=False),
                allocator_lock_path=tmp_path / "allocator.lock",
                leases_dir=tmp_path / "leases",
                poll_interval=0.02,
            )

        return coordinator

    return SimpleNamespace(make=make, metas=metas, tmp_path=tmp_path)


def _account_of(env: dict) -> str:
    return Path(env["HOME"]).name.removeprefix("home-")


def test_burst_larger_than_pool_queues_and_all_complete(pool_env) -> None:
    make_coordinator = pool_env.make(["a", "b"])
    started = threading.Barrier(2, timeout=10)
    seen: list[str] = []
    seen_lock = threading.Lock()

    def runner(**kwargs):
        with seen_lock:
            seen.append(_account_of(kwargs["env"]))
            first_two = len(seen) <= 2
        if first_two:
            started.wait()  # both accounts are leased at once: the pool is busy
        threading.Event().wait(0.2)
        return 0, "done", "", False, 200

    codes: list[int] = []
    codes_lock = threading.Lock()

    def one() -> None:
        code = dispatch.dispatch_run(
            prompt="work",
            cwd=str(ROOT),
            mode="plan",
            model=GEMINI,
            timeout=60,
            max_calls=1,
            coordinator=make_coordinator(),
            run_agy_fn=runner,
        )
        with codes_lock:
            codes.append(code)

    threads = [threading.Thread(target=one) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert codes == [0] * 6
    assert len(seen) == 6 and set(seen) == {"a", "b"}
    terminal = [meta for meta in pool_env.metas if "status" in meta]
    assert [meta["status"] for meta in terminal] == ["completed"] * 6
    assert not any(meta.get("failure_kind") for meta in terminal)
    # At least the four dispatches beyond the pool size waited for a running
    # task (each holds its account for 200 ms) rather than a millisecond pass.
    assert sum(1 for meta in terminal if meta.get("pool_queue_wait_ms", 0) >= 100) >= 4


def test_quota_on_first_account_rotates_and_completes(pool_env) -> None:
    make_coordinator = pool_env.make(["a", "b"])
    events: list[dict] = []
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        if len(calls) == 1:
            return 1, "", "RESOURCE_EXHAUSTED: quota exhausted", False, 5
        return 0, "done", "", False, 5

    code = dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        mode="plan",
        model=GEMINI,
        timeout=60,
        max_calls=1,
        coordinator=make_coordinator(),
        run_agy_fn=runner,
        operation_hook=events.append,
    )

    assert code == 0
    assert len(calls) == 2 and calls[0] != calls[1]
    final = pool_env.metas[-1]
    assert final["status"] == "completed"
    assert final["rotations"] == 1
    assert final["attempts"] == 2  # the quota failure did not use the max_calls=1 budget
    rotated = [event for event in events if event.get("phase") == "ACCOUNT_ROTATED"]
    assert len(rotated) == 1
    # The quota-failed account is durably blocked for the Gemini family only.
    markers = list((pool_env.tmp_path / "leases").glob("*.family-unavailable.gemini.json"))
    failed_hash = hashlib.sha256(calls[0].encode()).hexdigest()[:12]
    assert [marker.name.split(".")[0] for marker in markers] == [failed_hash]


def test_auth_failure_marks_account_and_rotates(pool_env) -> None:
    make_coordinator = pool_env.make(["a", "b"])
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        if len(calls) == 1:
            return 1, "", "401 unauthorized: login required", False, 5
        return 0, "done", "", False, 5

    code = dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        mode="plan",
        model=GEMINI,
        timeout=60,
        max_calls=1,
        coordinator=make_coordinator(),
        run_agy_fn=runner,
    )

    assert code == 0
    assert pool_env.metas[-1]["rotations"] == 1
    failed_hash = hashlib.sha256(calls[0].encode()).hexdigest()[:12]
    assert (pool_env.tmp_path / "leases" / f"{failed_hash}.quarantine.json").is_file()


def test_timeout_cools_the_account_briefly_not_for_an_hour(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_AGY_TIMEOUT_COOLDOWN_MINUTES", raising=False)
    accounts = [AgyAccount(alias=n, home_dir=str(tmp_path / n)) for n in ("a", "b")]
    manager = AgyAccountPoolManager(accounts=accounts, use_real_manager=False)
    coordinator = CrossProcessLeaseCoordinator(
        manager=manager,
        allocator_lock_path=tmp_path / "allocator.lock",
        leases_dir=tmp_path / "leases",
    )
    first = coordinator.acquire_claim("w1", wait_timeout=0.0)
    second = coordinator.acquire_claim("w2", wait_timeout=0.0)
    calls: list[list[str]] = []

    def manager_cli(args: list[str], expect_json: bool = True):
        calls.append(list(args))
        return {}

    manager._use_real_manager = True
    manager._call_manager_cli = manager_cli  # type: ignore[method-assign]

    coordinator.retire_failed_claim(first, dispatch.AccountFailureKind.TIMEOUT)
    coordinator.retire_failed_claim(second, dispatch.AccountFailureKind.AUTH_OR_SESSION_INVALID)

    marks = [args for args in calls if args[:1] == ["mark-bad"]]
    assert marks == [
        ["mark-bad", first.internal_id, "--reason", "TIMEOUT", "--cooldown-minutes", "5"],
        ["mark-bad", second.internal_id, "--reason", "AUTH_OR_SESSION_INVALID"],
    ]
    assert first.released and second.released
    assert not list((tmp_path / "leases").glob("*.quarantine.json"))


def test_timeout_cooldown_is_configurable(monkeypatch) -> None:
    from nexus.services import agy_account_pool

    monkeypatch.setenv("NEXUS_AGY_TIMEOUT_COOLDOWN_MINUTES", "12")
    assert agy_account_pool.timeout_cooldown_minutes() == 12
    monkeypatch.setenv("NEXUS_AGY_TIMEOUT_COOLDOWN_MINUTES", "0")
    assert agy_account_pool.timeout_cooldown_minutes() == 1
    monkeypatch.setenv("NEXUS_AGY_TIMEOUT_COOLDOWN_MINUTES", "junk")
    assert agy_account_pool.timeout_cooldown_minutes() == 5


class _CoolingCoordinator:
    """An exhausted pool whose manager reports per-account cooldown ends."""

    def __init__(self, tmp_path: Path, cooldowns: dict[str, float], recover_after: int | None):
        self.leases_dir = tmp_path / "leases"
        self.leases_dir.mkdir(parents=True, exist_ok=True)
        self.passes = 0
        self.recover_after = recover_after
        status = {
            "accounts": {
                name: {"enabled": True, "cooldown_until": _iso(until)}
                for name, until in cooldowns.items()
            }
        }
        self.manager = SimpleNamespace(_call_manager_cli=lambda _args, **_kw: status)

    def get_quarantined_hashes(self) -> set[str]:
        return set()

    def acquire_claim(self, **_kwargs):
        self.passes += 1
        if self.recover_after is None or self.passes <= self.recover_after:
            raise dispatch.AgyAccountPoolExhaustedError("all cooling")
        return _FakeClaim("late")

    def retire_failed_claim(self, claim, *_args, **_kwargs):
        claim.release()


class _FakeClaim:
    def __init__(self, name: str) -> None:
        self.internal_id = name
        self.account_alias_hash = hashlib.sha256(name.encode()).hexdigest()[:12]
        self.lease_id_hash = "lease-" + name
        self.lease = SimpleNamespace(
            execution_env={"HOME": tempfile.mkdtemp(prefix=f"agy-pq-{name}-")}, consumer_id="c"
        )
        self.released = False

    def release(self) -> None:
        self.released = True


def test_all_accounts_cooling_past_deadline_is_pool_exhausted_with_reset_time(
    pool_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool_env.make(["a", "b"])
    now = datetime.now(timezone.utc).timestamp()
    soonest = now + 3600
    coordinator = _CoolingCoordinator(
        pool_env.tmp_path, {"a": soonest, "b": now + 7200}, recover_after=None
    )
    events: list[dict] = []

    def runner(**_kwargs):
        raise AssertionError("no provider call may start on an exhausted pool")

    code = dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        mode="plan",
        model=GEMINI,
        timeout=60,
        max_calls=1,
        coordinator=coordinator,
        run_agy_fn=runner,
        operation_hook=events.append,
    )

    assert code == 75
    meta = pool_env.metas[-1]
    assert meta["status"] == "pool_exhausted"
    assert meta["failure_kind"] == "ACCOUNT_UNAVAILABLE"
    assert abs(datetime.fromisoformat(meta["earliest_reset_at"]).timestamp() - soonest) < 1
    assert meta["pool_recovery"]["accounts_cooling"] == 2
    assert coordinator.passes == 1  # recovery is past the deadline: no pointless queue
    claim_failed = [e for e in events if e.get("phase") == "ACCOUNT_CLAIM_FAILED"]
    assert (
        claim_failed[-1]["failure_history_entry"]["earliest_reset_at"]
        == (meta["earliest_reset_at"])
    )


def test_cooldown_ending_before_deadline_queues_instead_of_failing(
    pool_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool_env.make(["a"])
    sleeps: list[float] = []
    monkeypatch.setattr(dispatch, "_sleep", sleeps.append)
    now = datetime.now(timezone.utc).timestamp()
    coordinator = _CoolingCoordinator(pool_env.tmp_path, {"late": now + 20}, recover_after=1)

    def runner(**_kwargs):
        return 0, "done", "", False, 5

    code = dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        mode="plan",
        model=GEMINI,
        timeout=300,
        max_calls=1,
        coordinator=coordinator,
        run_agy_fn=runner,
    )

    assert code == 0
    assert pool_env.metas[-1]["status"] == "completed"
    assert coordinator.passes == 2
    # It slept toward the cooldown end (capped per pass), not a fixed 15 s timeout.
    assert len(sleeps) == 1 and 19.0 <= sleeps[0] <= dispatch.POOL_QUEUE_MAX_SLEEP_SECONDS


def test_unexplained_exhaustion_does_not_spin(pool_env) -> None:
    pool_env.make(["a"])
    coordinator = _CoolingCoordinator(pool_env.tmp_path, {}, recover_after=None)
    coordinator.manager = SimpleNamespace(
        _call_manager_cli=lambda _a, **_k: {"accounts": {"a": {"enabled": True}}}
    )

    code = dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        mode="plan",
        model=GEMINI,
        timeout=60,
        max_calls=1,
        coordinator=coordinator,
        run_agy_fn=lambda **_k: (0, "", "", False, 1),
    )

    assert code == 75
    assert coordinator.passes == 1
    meta = pool_env.metas[-1]
    assert meta["earliest_reset_at"] is None
    assert meta["pool_recovery"]["accounts_without_known_recovery"] == 1


def test_pool_wait_budget_follows_total_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dispatch, "_monotonic", lambda: 1000.0)
    floor = dispatch.TOTAL_DEADLINE_MIN_ATTEMPT_SECONDS
    assert dispatch._pool_wait_budget(total_deadline=1900.0, explicit=None) == 900.0 - floor
    # An explicit wait only shortens the queue and never outlives the deadline.
    assert dispatch._pool_wait_budget(total_deadline=1900.0, explicit=15.0) == 15.0
    assert dispatch._pool_wait_budget(total_deadline=1010.0, explicit=600.0) == 10.0 - floor
    assert dispatch._pool_wait_budget(total_deadline=1001.0, explicit=None) == 0.0


def test_cli_default_pool_wait_is_derived(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEXUS_AGY_POOL_WAIT_TIMEOUT", raising=False)
    assert dispatch._env_pool_wait_timeout() is None
    monkeypatch.setenv("NEXUS_AGY_POOL_WAIT_TIMEOUT", "42")
    assert dispatch._env_pool_wait_timeout() == 42.0


def test_explicit_pool_wait_still_caps_a_busy_queue(pool_env, monkeypatch) -> None:
    pool_env.make(["a"])
    sleeps: list[float] = []
    clock = {"now": 0.0}

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(dispatch, "_sleep", fake_sleep)
    monkeypatch.setattr(dispatch, "_queue_monotonic", lambda: clock["now"])

    class Busy:
        def acquire_claim(self, **_kwargs):
            raise dispatch.AgyAccountPoolBusyError("leased")

    code = dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        mode="plan",
        model=GEMINI,
        timeout=600,
        max_calls=1,
        pool_wait_timeout=1.0,
        coordinator=Busy(),
        run_agy_fn=lambda **_k: (0, "", "", False, 1),
    )

    assert code == 75
    meta = pool_env.metas[-1]
    assert meta["status"] == "pool_busy"
    assert meta["pool_wait_budget_seconds"] == 1.0
    assert sum(sleeps) == pytest.approx(1.0, abs=0.05)


def test_default_queue_outlasts_the_old_fixed_15_seconds(pool_env, monkeypatch) -> None:
    pool_env.make(["a"])
    clock = {"now": 0.0}

    def fake_sleep(seconds: float) -> None:
        clock["now"] += 10.0  # every queue pass costs ten seconds of wall time

    monkeypatch.setattr(dispatch, "_sleep", fake_sleep)
    monkeypatch.setattr(dispatch, "_queue_monotonic", lambda: clock["now"])

    class BusyThenFree:
        passes = 0

        def acquire_claim(self, **_kwargs):
            self.passes += 1
            if self.passes <= 4:  # busy for 40 s: past the old 15 s pool wait
                raise dispatch.AgyAccountPoolBusyError("leased")
            return _FakeClaim("a")

        def retire_failed_claim(self, claim, *_args, **_kwargs):
            claim.release()

    coordinator = BusyThenFree()
    code = dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        mode="plan",
        model=GEMINI,
        timeout=600,
        max_calls=1,
        coordinator=coordinator,
        run_agy_fn=lambda **_k: (0, "done", "", False, 1),
    )

    assert code == 0
    assert coordinator.passes == 5
    assert pool_env.metas[-1]["status"] == "completed"
    assert pool_env.metas[-1]["pool_queue_wait_ms"] == 40_000


def test_rotation_cap_is_bounded_by_pool_size(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_AGY_MAX_ACCOUNT_FAILOVERS", raising=False)
    accounts = [AgyAccount(alias=n, home_dir=str(tmp_path / n)) for n in ("a", "b", "c")]
    coordinator = CrossProcessLeaseCoordinator(
        manager=AgyAccountPoolManager(accounts=accounts, use_real_manager=False),
        allocator_lock_path=tmp_path / "allocator.lock",
        leases_dir=tmp_path / "leases",
    )
    assert dispatch._rotation_cap(coordinator) == 2
    assert dispatch._rotation_cap(SimpleNamespace()) == dispatch.DEFAULT_MAX_ACCOUNT_FAILOVERS


def test_five_hour_pressure_is_capped_by_weekly_remaining() -> None:
    now = 2_000_000_000.0

    def row(name: str, five_h: float, weekly: float) -> dict:
        return {
            "account": name,
            "ok": True,
            "groups": {
                "Gemini Models": {
                    "5h": {
                        "status": "known",
                        "remaining_pct": five_h,
                        "reset_at": _iso(now + 2 * 3600),
                    },
                    "weekly": {
                        "status": "known",
                        "remaining_pct": weekly,
                        "reset_at": _iso(now + 100 * 3600),
                    },
                }
            },
        }

    snapshot = {
        "checked_at": _iso(now),
        "accounts": [
            row("full-5h-weekly-nearly-gone", 100.0, 3.0),
            row("most-remaining", 80.0, 80.0),
            row("weekly-gone", 100.0, 0.0),
        ],
    }
    state = dispatch._dynamic_availability_state(GEMINI, snapshot, now_ts=now, max_age_seconds=900)
    assert state["preferred"] == [
        "most-remaining",
        "full-5h-weekly-nearly-gone",
        "weekly-gone",
    ]


def test_unknown_pressure_prefers_most_remaining() -> None:
    order = dispatch._order_accounts_by_drain_pressure([
        ("low", None, 10.0),
        ("high", None, 90.0),
        ("pressured", 5.0, 1.0),
    ])
    assert order == ["pressured", "high", "low"]


def test_background_record_keeps_pool_failure_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(dispatch, "_load_quota_snapshot", lambda *_a, **_k: {})
    monkeypatch.setattr(dispatch, "_sleep", lambda _s: None)
    root = tmp_path / "ops"
    journal = dispatch.AgyOperationJournal(root)
    operation_id = dispatch.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model=GEMINI,
        effort=None,
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    prompt_path = journal.prompt_path(operation_id)
    dispatch._write_private_prompt(prompt_path, "reply")
    now = datetime.now(timezone.utc).timestamp()
    coordinator = _CoolingCoordinator(tmp_path, {"a": now + 7200}, recover_after=None)
    real_dispatch_run = dispatch.dispatch_run
    monkeypatch.setattr(
        dispatch,
        "dispatch_run",
        lambda **kwargs: real_dispatch_run(**kwargs, coordinator=coordinator),
    )

    code = dispatch._run_background_operation(
        operation_id=operation_id,
        prompt_file=str(prompt_path),
        cwd=str(tmp_path),
        mode="plan",
        model=GEMINI,
        effort=None,
        timeout=60,
        max_calls=1,
        pool_wait_timeout=None,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=root,
        heartbeat_interval=60,
    )

    record = json.loads((root / "operations" / operation_id / "operation.json").read_text())
    assert code == 75
    assert record["failure_kind"] == "ACCOUNT_UNAVAILABLE"
    history = record["failure_history"]
    assert len(history) == 1
    assert history[0]["failure_kind"] == "ACCOUNT_UNAVAILABLE"
    assert history[0]["earliest_reset_at"] is not None
    assert record["pool_queue"]["state"] == "POOL_EXHAUSTED"
    assert record["pool_queue"]["earliest_reset_at"] == history[0]["earliest_reset_at"]


class _ImmediateCoordinator:
    def __init__(self, tmp_path: Path) -> None:
        self.leases_dir = tmp_path / "leases"
        self.leases_dir.mkdir(parents=True, exist_ok=True)
        self.passes = 0

    def acquire_claim(self, **_kwargs):
        self.passes += 1
        return _FakeClaim("a")


def _older_ticket(queue_dir: Path, pid: int, kind: str = "u") -> Path:
    queue_dir.mkdir(parents=True, exist_ok=True)
    path = queue_dir / f"{1:020d}-{pid}-deadbeef.gemini.{kind}.ticket"
    path.write_text(f"{pid}\n", encoding="utf-8")
    return path


def test_new_dispatch_waits_behind_an_older_live_waiter(tmp_path: Path, monkeypatch) -> None:
    coordinator = _ImmediateCoordinator(tmp_path)
    older = _older_ticket(coordinator.leases_dir / "queue", os.getpid())
    passes_when_slept: list[int] = []

    def fake_sleep(_seconds: float) -> None:
        passes_when_slept.append(coordinator.passes)
        older.unlink()  # the older waiter leased and left the queue

    monkeypatch.setattr(dispatch, "_sleep", fake_sleep)
    claim, _waited = dispatch._acquire_claim_queued(
        coordinator,
        consumer_id="c",
        exclude_hashes=set(),
        wait_budget=60.0,
        model_family="gemini",
        quota_snapshot={},
    )

    assert claim.internal_id == "a"
    assert passes_when_slept == [0]  # no allocator pass while the older waiter was ahead
    assert coordinator.passes == 1
    assert list((coordinator.leases_dir / "queue").iterdir()) == []


def test_dead_waiter_ticket_is_pruned_and_never_blocks(tmp_path: Path, monkeypatch) -> None:
    coordinator = _ImmediateCoordinator(tmp_path)
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    stale = _older_ticket(coordinator.leases_dir / "queue", child.pid)
    monkeypatch.setattr(dispatch, "_sleep", lambda _s: pytest.fail("must not wait"))

    claim, _waited = dispatch._acquire_claim_queued(
        coordinator,
        consumer_id="c",
        exclude_hashes=set(),
        wait_budget=60.0,
        model_family="gemini",
        quota_snapshot={},
    )

    assert claim.internal_id == "a"
    assert not stale.exists()


def test_restricted_older_waiter_does_not_block(tmp_path: Path, monkeypatch) -> None:
    # An older waiter with --exclude-account may have excluded the free
    # account; it must not hold up unrestricted dispatches (head-of-line).
    coordinator = _ImmediateCoordinator(tmp_path)
    _older_ticket(coordinator.leases_dir / "queue", os.getpid(), kind="r")
    monkeypatch.setattr(dispatch, "_sleep", lambda _s: pytest.fail("must not wait"))

    claim, _waited = dispatch._acquire_claim_queued(
        coordinator,
        consumer_id="c",
        exclude_hashes=set(),
        wait_budget=60.0,
        model_family="gemini",
        quota_snapshot={},
    )
    assert claim.internal_id == "a"


def test_other_model_family_does_not_block(tmp_path: Path, monkeypatch) -> None:
    coordinator = _ImmediateCoordinator(tmp_path)
    _older_ticket(coordinator.leases_dir / "queue", os.getpid())
    monkeypatch.setattr(dispatch, "_sleep", lambda _s: pytest.fail("must not wait"))

    claim, _waited = dispatch._acquire_claim_queued(
        coordinator,
        consumer_id="c",
        exclude_hashes=set(),
        wait_budget=60.0,
        model_family="claude_gpt",
        quota_snapshot={},
    )
    assert claim.internal_id == "a"


def test_waiters_are_served_oldest_first(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_AGY_POOL_QUEUE_POLL_SECONDS", "0.05")
    accounts = [AgyAccount(alias="solo", home_dir=str(tmp_path / "solo"))]

    def coordinator() -> CrossProcessLeaseCoordinator:
        return CrossProcessLeaseCoordinator(
            manager=AgyAccountPoolManager(accounts=accounts, use_real_manager=False),
            allocator_lock_path=tmp_path / "allocator.lock",
            leases_dir=tmp_path / "leases",
        )

    holder = coordinator().acquire_claim("holder", wait_timeout=0.0)
    order: list[str] = []
    order_lock = threading.Lock()

    def waiter(name: str) -> None:
        claim, _waited = dispatch._acquire_claim_queued(
            coordinator(),
            consumer_id=name,
            exclude_hashes=set(),
            wait_budget=20.0,
            model_family="gemini",
            quota_snapshot={},
        )
        with order_lock:
            order.append(name)
        threading.Event().wait(0.2)
        claim.release()

    queue_dir = tmp_path / "leases" / "queue"
    first = threading.Thread(target=waiter, args=("older",))
    first.start()
    for _ in range(100):
        if queue_dir.is_dir() and list(queue_dir.glob("*.ticket")):
            break
        threading.Event().wait(0.02)
    second = threading.Thread(target=waiter, args=("newer",))
    second.start()
    for _ in range(100):
        if len(list(queue_dir.glob("*.ticket"))) == 2:
            break
        threading.Event().wait(0.02)
    threading.Event().wait(0.2)  # both are polling a busy pool now
    holder.release()
    first.join(timeout=20)
    second.join(timeout=20)

    assert order == ["older", "newer"]
    assert list(queue_dir.glob("*.ticket")) == []


def test_no_allocator_pass_starts_after_the_wait_deadline(pool_env, monkeypatch) -> None:
    clock = {"now": 0.0}

    def fake_sleep(seconds: float) -> None:
        clock["now"] += 10.0  # each wait overshoots: passes at t=0 and t=10 only

    monkeypatch.setattr(dispatch, "_sleep", fake_sleep)
    monkeypatch.setattr(dispatch, "_queue_monotonic", lambda: clock["now"])

    class Busy:
        passes = 0

        def acquire_claim(self, **_kwargs):
            self.passes += 1
            raise dispatch.AgyAccountPoolBusyError("leased")

    busy = Busy()
    with pytest.raises(dispatch._PoolClaimFailure) as failure:
        dispatch._acquire_claim_queued(
            busy,
            consumer_id="c",
            exclude_hashes=set(),
            wait_budget=15.0,
            model_family="gemini",
            quota_snapshot={},
        )
    assert failure.value.busy is True
    assert busy.passes == 2


def test_quota_availability_is_republished_after_waiting_for_a_reset(
    pool_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool_env.make(["late"])
    applied: list[str | None] = []
    snapshot = _fresh_snapshot(["late"])

    def apply(model):
        applied.append(model)
        return snapshot, _state()

    monkeypatch.setattr(dispatch, "_apply_dynamic_availability", apply)
    monkeypatch.setattr(dispatch, "_sleep", lambda _s: None)
    now = datetime.now(timezone.utc).timestamp()
    coordinator = _CoolingCoordinator(pool_env.tmp_path, {"late": now + 20}, recover_after=1)

    code = dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        mode="plan",
        model=GEMINI,
        timeout=300,
        max_calls=1,
        coordinator=coordinator,
        run_agy_fn=lambda **_k: (0, "done", "", False, 5),
    )

    assert code == 0
    assert applied == [GEMINI, GEMINI]  # once at start, once before the post-reset pass


def test_rotation_pass_is_never_queued_behind_new_dispatches(tmp_path: Path, monkeypatch) -> None:
    coordinator = _ImmediateCoordinator(tmp_path)
    _older_ticket(coordinator.leases_dir / "queue", os.getpid())
    monkeypatch.setattr(dispatch, "_sleep", lambda _s: pytest.fail("must not wait"))
    rotated: list[str] = []

    def rotation_pass():
        rotated.append("retired-and-claimed")
        return _FakeClaim("b")

    claim, _waited = dispatch._acquire_claim_queued(
        coordinator,
        consumer_id="c",
        exclude_hashes=set(),
        wait_budget=60.0,
        model_family="gemini",
        quota_snapshot={},
        first_pass=rotation_pass,
    )
    assert claim.internal_id == "b" and rotated == ["retired-and-claimed"]


class _CountingCoordinator:
    def __init__(self, names: list[str]) -> None:
        self.claims = [_FakeClaim(name) for name in names]
        self.index = 0
        self.rotations = 0
        self.retired: list[tuple[str, str]] = []

    def acquire_claim(self, **_kwargs):
        return self.claims[self.index]

    def rotate_claim(self, *, current_claim, failure_kind, **_kwargs):
        self.rotations += 1
        self.retire_failed_claim(current_claim, failure_kind)
        self.index += 1
        return self.claims[self.index]

    def retire_failed_claim(self, claim, failure_kind, **_kwargs):
        self.retired.append((claim.internal_id, failure_kind.value))
        claim.release()


def test_no_new_lease_when_no_budget_is_left_for_another_attempt(
    pool_env, monkeypatch: pytest.MonkeyPatch
) -> None:
    pool_env.make(["a", "b"])
    clock = {"now": 1000.0}
    monkeypatch.setattr(dispatch, "_monotonic", lambda: clock["now"])
    coordinator = _CountingCoordinator(["a", "b"])

    def runner(**kwargs):
        clock["now"] += kwargs["timeout"] - 2  # leaves 2 s, below the 5 s floor
        return 1, "", "RESOURCE_EXHAUSTED: quota exhausted", False, 1

    code = dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        mode="plan",
        model=GEMINI,
        timeout=100,
        max_calls=1,
        coordinator=coordinator,
        run_agy_fn=runner,
    )

    assert code == 124
    assert coordinator.rotations == 0  # nothing new was leased
    assert coordinator.retired == [("a", "QUOTA_EXHAUSTED")]  # but quota is still recorded


def test_dispatch_rotations_are_capped_by_pool_size(pool_env, monkeypatch) -> None:
    monkeypatch.delenv("NEXUS_AGY_MAX_ACCOUNT_FAILOVERS", raising=False)
    make_coordinator = pool_env.make(["a", "b"])
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        return 1, "", "RESOURCE_EXHAUSTED: quota exhausted", False, 1

    code = dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        mode="plan",
        model=GEMINI,
        timeout=60,
        max_calls=1,
        coordinator=make_coordinator(),
        run_agy_fn=runner,
    )

    assert code == 75
    assert len(calls) == 2
    final = pool_env.metas[-1]
    assert final["failure_kind"] == "ACCOUNT_FAILOVER_LIMIT"
    assert final["rotations"] == 1


def test_known_quota_rotation_is_recorded_in_failure_history(pool_env, monkeypatch) -> None:
    pool_env.make(["a", "b"])
    checked_at = datetime.now(timezone.utc).isoformat()
    reset_at = _iso(datetime.now(timezone.utc).timestamp() + 3600)

    def row(name: str, remaining: float) -> dict:
        return {
            "account": name,
            "checked_at": checked_at,
            "ok": True,
            "groups": {
                "Gemini Models": {
                    "5h": {"status": "known", "remaining_pct": remaining, "reset_at": reset_at}
                }
            },
        }

    snapshot = {"checked_at": checked_at, "accounts": [row("a", 0.0), row("b", 90.0)]}
    monkeypatch.setattr(dispatch, "_apply_dynamic_availability", lambda _m: (snapshot, _state()))
    coordinator = _CountingCoordinator(["a", "b"])
    events: list[dict] = []
    calls: list[str] = []

    def runner(**kwargs):
        calls.append("run")
        return 0, "done", "", False, 1

    code = dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        mode="plan",
        model=GEMINI,
        timeout=60,
        max_calls=1,
        coordinator=coordinator,
        run_agy_fn=runner,
        operation_hook=events.append,
    )

    assert code == 0 and calls == ["run"]
    entries = [e["failure_history_entry"] for e in events if "failure_history_entry" in e]
    assert entries == [
        {
            "attempts": 0,
            "rotations": 0,
            "failure_kind": "QUOTA_EXHAUSTED_KNOWN_PRE_ATTEMPT",
            "account_alias_hash": coordinator.claims[0].account_alias_hash,
            "lease_id_hash": coordinator.claims[0].lease_id_hash,
        }
    ]


def test_recovery_estimate_ignores_an_in_memory_pool(tmp_path: Path) -> None:
    manager = SimpleNamespace(
        _use_real_manager=False,
        _call_manager_cli=lambda *_a, **_k: pytest.fail("must not read the real manager"),
    )
    estimate = dispatch._pool_recovery_estimate(
        SimpleNamespace(manager=manager, leases_dir=tmp_path),
        model_family="gemini",
        exclude_hashes=set(),
        quota_snapshot={},
    )
    assert estimate["earliest_reset_ts"] is None


def test_restricted_waiters_with_the_same_exclusions_are_ordered(tmp_path: Path) -> None:
    queue_dir = tmp_path / "queue"
    excluded = {"0123456789ab"}
    older = dispatch._PoolQueueTicket(
        queue_dir, model_family="gemini", restricted=True, exclude_hashes=excluded
    )
    other = dispatch._PoolQueueTicket(
        queue_dir, model_family="gemini", restricted=True, exclude_hashes={"ba9876543210"}
    )
    newer = dispatch._PoolQueueTicket(
        queue_dir, model_family="gemini", restricted=True, exclude_hashes=excluded
    )
    assert older.is_head() and other.is_head()
    assert not newer.is_head()
    older.close()
    assert newer.is_head()
    for ticket in (other, newer):
        ticket.close()


def test_queue_poll_stays_below_ticket_staleness(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_AGY_POOL_QUEUE_POLL_SECONDS", "600")
    assert dispatch._pool_queue_poll_seconds() == dispatch.POOL_QUEUE_MAX_POLL_SECONDS
    assert dispatch.POOL_QUEUE_MAX_POLL_SECONDS < dispatch.POOL_QUEUE_TICKET_STALE_SECONDS
    assert dispatch.POOL_QUEUE_MAX_SLEEP_SECONDS < dispatch.POOL_QUEUE_TICKET_STALE_SECONDS


def test_busy_wait_rereads_quota_availability(tmp_path: Path, monkeypatch) -> None:
    clock = {"now": 0.0}

    def fake_sleep(seconds: float) -> None:
        clock["now"] += seconds

    monkeypatch.setattr(dispatch, "_sleep", fake_sleep)
    monkeypatch.setattr(dispatch, "_queue_monotonic", lambda: clock["now"])
    monkeypatch.setenv("NEXUS_AGY_POOL_QUEUE_POLL_SECONDS", "10")
    refreshes: list[float] = []

    class BusyUntilRefreshed:
        leases_dir = tmp_path / "leases"

        def acquire_claim(self, **_kwargs):
            if not refreshes:  # the quota-blocked account is hidden until republished
                raise dispatch.AgyAccountPoolBusyError("the other account is leased")
            return _FakeClaim("reset")

    def refresh() -> dict:
        refreshes.append(clock["now"])
        return {}

    claim, waited = dispatch._acquire_claim_queued(
        BusyUntilRefreshed(),
        consumer_id="c",
        exclude_hashes=set(),
        wait_budget=300.0,
        model_family="gemini",
        quota_snapshot={},
        refresh_availability=refresh,
    )
    assert claim.internal_id == "reset"
    assert refreshes == [dispatch.POOL_QUEUE_REFRESH_SECONDS]
    assert waited == dispatch.POOL_QUEUE_REFRESH_SECONDS
