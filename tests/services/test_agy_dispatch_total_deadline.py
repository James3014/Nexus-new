"""#1216 V12: --timeout is ONE wall-clock budget across attempts and rotations."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"
os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader("nexus_agy_dispatch_total_deadline", str(DISPATCH_PATH)).load_module()

NAMES = ("a", "b", "c", "d")


class FakeClaim:
    def __init__(self, name: str) -> None:
        self.internal_id = name
        self.account_alias_hash = f"hash-{name}"
        self.lease_id_hash = f"lease-{name}"
        self.lease = SimpleNamespace(
            execution_env={"ACCOUNT": name, "HOME": tempfile.mkdtemp(prefix="agy-td-home-")},
            consumer_id="consumer",
        )
        self.released = False

    def release(self) -> None:
        self.released = True


class FakeCoordinator:
    def __init__(self) -> None:
        self.claims = [FakeClaim(n) for n in NAMES]
        self.index = 0

    def acquire_claim(self, **_kwargs):
        return self.claims[self.index]

    def rotate_claim(self, *, current_claim, **_kwargs):
        current_claim.release()
        self.index += 1
        return self.claims[self.index]

    def retire_failed_claim(self, claim, *_args, **_kwargs):
        claim.release()


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def harness(monkeypatch):
    checked_at = datetime.now(timezone.utc).isoformat()
    snapshot = {
        "checked_at": checked_at,
        "accounts": [
            {
                "account": n,
                "checked_at": checked_at,
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": {"status": "known", "remaining_pct": 100.0, "reset_at": None}
                    }
                },
            }
            for n in NAMES
        ],
    }
    state = {
        "family": "gemini",
        "snapshot_fresh": True,
        "preferred": [],
        "reserve": [],
        "fallback": [],
        "blocked": [],
        "unknown": [],
    }
    monkeypatch.setattr(dispatch, "_apply_dynamic_availability", lambda _m: (snapshot, state))
    clock = Clock()
    monkeypatch.setattr(dispatch, "_monotonic", clock)
    metas: list[dict] = []
    monkeypatch.setattr(dispatch, "emit_meta", metas.append)
    return clock, metas


def _run(coordinator, runner, timeout):
    return dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        model="gemini-3.8-flash-high",
        timeout=timeout,
        max_calls=1,
        coordinator=coordinator,
        run_agy_fn=runner,
    )


def test_remaining_budget_is_passed_to_each_rotation_attempt(harness) -> None:
    clock, metas = harness
    seen: list[int] = []

    def runner(**kwargs):
        seen.append(kwargs["timeout"])
        clock.now += 100
        if len(seen) == 1:
            return 1, "", "RESOURCE_EXHAUSTED: quota exhausted", False, 100_000
        return 0, "done", "", False, 100_000

    coordinator = FakeCoordinator()
    assert _run(coordinator, runner, 150) == 0
    assert seen == [150, 50]


def test_no_rotation_attempt_after_budget_exhausted(harness) -> None:
    clock, metas = harness
    seen: list[int] = []

    def runner(**kwargs):
        seen.append(kwargs["timeout"])
        clock.now += kwargs["timeout"]
        return 1, "", "", True, kwargs["timeout"] * 1000  # timed out

    coordinator = FakeCoordinator()
    code = _run(coordinator, runner, 120)

    assert code != 0
    assert seen == [120]  # a timeout consumed the whole budget: no further attempt
    assert metas[-1]["failure_kind"] == "TIMEOUT"


def test_attempt_not_started_below_floor(harness) -> None:
    clock, metas = harness
    seen: list[int] = []

    def runner(**kwargs):
        seen.append(kwargs["timeout"])
        clock.now += 98  # leaves 2s, below the 5s floor
        return 1, "", "RESOURCE_EXHAUSTED: quota exhausted", False, 98_000

    coordinator = FakeCoordinator()
    assert _run(coordinator, runner, 100) == 124
    assert seen == [100]
    assert metas[-1]["failure_kind"] == "TIMEOUT"
    assert metas[-1]["attempts"] == 1
