from __future__ import annotations

import os
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"
os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader("nexus_agy_dispatch_fast_failover", str(DISPATCH_PATH)).load_module()


class FakeClaim:
    def __init__(self, name: str) -> None:
        self.internal_id = name
        self.account_alias_hash = f"hash-{name}"
        self.lease_id_hash = f"lease-{name}"
        self.lease = SimpleNamespace(
            execution_env={"ACCOUNT": name, "HOME": "/tmp"},
            consumer_id="consumer",
        )
        self.released = False

    def release(self) -> None:
        self.released = True


class FakeCoordinator:
    def __init__(self, names: list[str]) -> None:
        self.claims = [FakeClaim(name) for name in names]
        self.index = 0
        self.retired: list[tuple[str, str]] = []

    def acquire_claim(self, **_kwargs):
        return self.claims[self.index]

    def rotate_claim(self, *, current_claim, failure_kind, **_kwargs):
        self.retired.append((current_claim.internal_id, failure_kind.value))
        current_claim.release()
        self.index += 1
        return self.claims[self.index]

    def retire_failed_claim(self, claim, failure_kind, **_kwargs):
        self.retired.append((claim.internal_id, failure_kind.value))
        claim.release()


def _state(*, fresh: bool) -> dict[str, object]:
    return {
        "family": "gemini",
        "snapshot_fresh": fresh,
        "preferred": [],
        "reserve": [],
        "fallback": [],
        "blocked": [],
        "unknown": [],
    }


def test_quota_failover_does_not_consume_model_call_budget(monkeypatch) -> None:
    coordinator = FakeCoordinator(["a", "b", "c"])
    checked_at = datetime.now(timezone.utc).isoformat()
    fresh_snapshot = {
        "checked_at": checked_at,
        "accounts": [
            {
                "account": name,
                "checked_at": checked_at,
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": {
                            "status": "known",
                            "remaining_pct": 100.0,
                            "reset_at": None,
                        }
                    }
                },
            }
            for name in ("a", "b", "c")
        ],
    }
    monkeypatch.setattr(
        dispatch,
        "_apply_dynamic_availability",
        lambda _model: (fresh_snapshot, _state(fresh=True)),
    )
    calls: list[str] = []

    def runner(**kwargs):
        account = kwargs["env"]["ACCOUNT"]
        calls.append(account)
        if account in {"a", "b"}:
            return 1, "", "RESOURCE_EXHAUSTED: quota exhausted", False, 5
        return 0, "done", "", False, 5

    code = dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        model="gemini-3.8-flash-high",
        max_calls=1,
        coordinator=coordinator,
        run_agy_fn=runner,
    )

    assert code == 0
    assert calls == ["a", "b", "c"]
    assert [name for name, _kind in coordinator.retired] == ["a", "b"]


def test_stale_quota_refresh_skips_blocked_account_before_worker(monkeypatch) -> None:
    coordinator = FakeCoordinator(["stale-blocked", "healthy"])
    stale_snapshot = {"checked_at": "2000-01-01T00:00:00+00:00", "accounts": []}
    monkeypatch.setattr(
        dispatch,
        "_apply_dynamic_availability",
        lambda _model: (stale_snapshot, _state(fresh=False)),
    )
    refreshed: list[str] = []

    def refresh(account_name: str, **_kwargs):
        refreshed.append(account_name)
        if account_name == "stale-blocked":
            checked_at = datetime.now(timezone.utc).isoformat()
            return {
                "checked_at": checked_at,
                "accounts": [
                    {
                        "account": account_name,
                        "checked_at": checked_at,
                        "ok": True,
                        "groups": {
                            "Gemini Models": {
                                "5h": {
                                    "status": "known",
                                    "remaining_pct": 0.0,
                                    "reset_at": "2999-01-01T01:00:00Z",
                                }
                            }
                        },
                    }
                ],
            }
        return {}

    monkeypatch.setattr(
        dispatch,
        "_refresh_quota_snapshot_for_account",
        refresh,
        raising=False,
    )
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(kwargs["env"]["ACCOUNT"])
        return 0, "done", "", False, 5

    code = dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        model="gemini-3.8-flash-high",
        max_calls=1,
        coordinator=coordinator,
        run_agy_fn=runner,
    )

    assert code == 0
    assert refreshed[0] == "stale-blocked"
    assert calls == ["healthy"]


def test_model_output_quota_word_is_not_quota_exhaustion() -> None:
    kind = dispatch.classify_failure(
        1,
        "The report says quota exhausted, but this is ordinary model output.",
        "",
        False,
    )
    assert kind is not dispatch.AccountFailureKind.QUOTA_EXHAUSTED


def test_quota_failover_has_separate_bounded_ceiling(monkeypatch) -> None:
    coordinator = FakeCoordinator(["a", "b", "c", "d"])
    checked_at = datetime.now(timezone.utc).isoformat()
    fresh_snapshot = {
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
            for name in ("a", "b", "c", "d")
        ],
    }
    monkeypatch.setattr(
        dispatch,
        "_apply_dynamic_availability",
        lambda _model: (fresh_snapshot, _state(fresh=True)),
    )
    monkeypatch.setenv("NEXUS_AGY_MAX_ACCOUNT_FAILOVERS", "2")
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(kwargs["env"]["ACCOUNT"])
        return 1, "", "RESOURCE_EXHAUSTED: quota exhausted", False, 5

    code = dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        model="gemini-3.8-flash-high",
        max_calls=1,
        coordinator=coordinator,
        run_agy_fn=runner,
    )

    assert code == 75
    assert calls == ["a", "b", "c"]
    assert [name for name, _kind in coordinator.retired] == ["a", "b", "c"]


def test_run_agy_terminates_promptly_on_provider_quota_stderr(tmp_path: Path, monkeypatch) -> None:
    fake_agy = tmp_path / "fake-agy"
    fake_agy.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, time\n"
        "sys.stderr.write('RESOURCE_EXHAUSTED: quota exhausted\\n')\n"
        "sys.stderr.flush()\n"
        "time.sleep(5)\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o755)
    monkeypatch.setattr(dispatch.shutil, "which", lambda _name: str(fake_agy))

    code, out, err, timed_out, wall_ms = dispatch.run_agy(
        env=os.environ.copy(),
        prompt="quota canary",
        cwd=str(tmp_path),
        mode="plan",
        model="gemini-3.8-flash-high",
        effort="low",
        timeout=30,
    )

    assert code not in (None, 0)
    assert out == ""
    assert "RESOURCE_EXHAUSTED" in err
    assert timed_out is False
    assert wall_ms < 2000
    assert (
        dispatch.classify_failure(code, out, err, timed_out)
        is dispatch.AccountFailureKind.QUOTA_EXHAUSTED
    )
