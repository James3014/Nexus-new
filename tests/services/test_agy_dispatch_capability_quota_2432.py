"""#2432: rotate on MODEL_CAPABILITY_UNAVAILABLE; retry read-only runs that hit quota mid-run.

Found in the #2412 trial (2026-10-16):

1. Pool accounts expose different model lists (only one offers Claude 5.5).
   A leased account without the fixed model failed the dispatch instead of
   rotating to an account that has it.
2. Seven READ_ONLY_RESEARCH reviews (cwd outside git, so no change
   observation) hit quota mid-run and were classified
   PROVIDER_QUOTA_EXHAUSTED_UNKNOWN_EFFECT, so they were not rotated.  Those
   profiles have no write and no command tool.

Runs against the real ``CrossProcessLeaseCoordinator`` (per-account flocks in a
temp leases dir).  The quota stderr is a real agy sample (redacted).
"""

from __future__ import annotations

import hashlib
import os
import threading
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"
os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader(
    "nexus_agy_dispatch_capability_quota_2432", str(DISPATCH_PATH)
).load_module()

from nexus.services.agy_account_pool import (  # noqa: E402
    AgyAccount,
    AgyAccountPoolManager,
    CrossProcessLeaseCoordinator,
)

SONNET_55 = "claude-sonnet-5-5"

# agyop_0dcd1b7e… (#2412 trial): quota mid-run on a read-only review.
QUOTA_STDERR = (
    "error: Individual quota reached. Please upgrade your subscription to increase your "
    "limits. Resets in 160h28m18s.\n"
    'AGY_ERROR: {"short_error":"RESOURCE_EXHAUSTED (code 429): Individual quota reached. '
    'Please upgrade your subscription to increase your limits. Resets in 160h28m18s.",'
    '"status":"RESOURCE_EXHAUSTED","error_code":429,"code_kind":"http","retryable":true,'
    '"error_id":"a4c59559-7682-4683-8d64-16c4ea55ae11-407"}\n'
)
PARTIAL_REVIEW = "## Review of PR #2370\n\n1. The first finding is"

# The seven #2412 trial operations lost to UNKNOWN_EFFECT (operation.json
# fields; cwd was a non-git review directory, so the change observation was
# unavailable).
TRIAL_2412_QUOTA_OPERATIONS = [
    # (operation id, recorded permission_profile_kind, effective_permissions,
    #  recorded failure_kind, model); cwd redacted to <review>.
    (
        op,
        "READ_ONLY_RESEARCH",
        {"allow": ["read_file(<review>/**)"], "deny": ["command(*)"]},
        "PROVIDER_QUOTA_EXHAUSTED_UNKNOWN_EFFECT",
        model,
    )
    for op, model in (
        ("agyop_0dcd1b7e60364aa4bf1c740d3817405c", "claude-opus-4-6-thinking"),
        ("agyop_17a5c1ec4d32464c9ebb4b4a10dbd72f", "claude-opus-4-6-thinking"),
        ("agyop_8a7edd87433747478bae0964b07df4f7", "claude-opus-4-6-thinking"),
        ("agyop_99fdad0e8b1f4b9dbf6e5a507574b3ce", "claude-opus-4-6-thinking"),
        ("agyop_a9892537c54c4e2287f33f002ffb9ae6", "claude-opus-5-5-high"),
        ("agyop_d4bc75d6b8e5406c87bd372f20b55c9d", "claude-opus-4-6-thinking"),
        ("agyop_ebf65ece2ba44000bf1964f7458a6202", "claude-opus-4-6-thinking"),
    )
]


def _state() -> dict[str, object]:
    return {
        "family": "claude_gpt",
        "snapshot_fresh": False,
        "preferred": [],
        "reserve": [],
        "fallback": [],
        "blocked": [],
        "unknown": [],
    }


@pytest.fixture
def pool_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEXUS_AGY_MODEL_CATALOG_CHECK", "1")
    monkeypatch.setenv("NEXUS_AGY_POOL_QUEUE_POLL_SECONDS", "0.05")
    monkeypatch.setenv("NEXUS_AGY_POOL_WAIT_TIMEOUT", "0.2")
    for name in (
        "NEXUS_AGY_MAX_ACCOUNT_RETIREMENTS",
        "NEXUS_AGY_MAX_ACCOUNT_FAILOVERS",
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
    monkeypatch.setattr(dispatch, "_load_quota_snapshot", lambda *_a, **_kw: {})
    monkeypatch.setattr(dispatch, "_apply_dynamic_availability", lambda _m: ({}, _state()))
    # Keep the test's account order (the quota preflight republishes it).
    monkeypatch.setattr(dispatch, "_publish_dynamic_availability", lambda _state: None)
    catalogs: dict[str, list[str]] = {}
    catalog_checks: list[str] = []

    def snapshot(*, env, account_alias_hash, now=None, max_fetch_seconds=None):
        name = Path(env["HOME"]).name.removeprefix("home-")
        catalog_checks.append(name)
        ids = catalogs[name]
        return {
            "catalog_status": "OK",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "checked_at_epoch": 0.0,
            "catalog_sha256": hashlib.sha256(",".join(ids).encode()).hexdigest(),
            "ids": ids,
            "source": "FRESH",
            "reason": None,
        }

    monkeypatch.setattr(dispatch, "_agy_model_catalog_snapshot", snapshot)

    def make(spec: dict[str, list[str]]) -> CrossProcessLeaseCoordinator:
        catalogs.update(spec)
        accounts = [AgyAccount(alias=n, home_dir=str(tmp_path / f"home-{n}")) for n in spec]
        for account in accounts:
            Path(account.home_dir).mkdir(parents=True, exist_ok=True)
        state = dict(_state(), preferred=list(spec))
        monkeypatch.setattr(dispatch, "_apply_dynamic_availability", lambda _m: ({}, state))
        monkeypatch.setenv("NEXUS_AGY_PREFERRED_ACCOUNTS", ",".join(spec))
        return CrossProcessLeaseCoordinator(
            manager=AgyAccountPoolManager(accounts=accounts, use_real_manager=False),
            allocator_lock_path=tmp_path / "allocator.lock",
            leases_dir=tmp_path / "leases",
            poll_interval=0.02,
        )

    review_dir = tmp_path / "review-not-git"
    review_dir.mkdir()
    return SimpleNamespace(
        make=make,
        metas=metas,
        tmp_path=tmp_path,
        catalog_checks=catalog_checks,
        review_dir=review_dir,
    )


def _account_of(env: dict) -> str:
    return Path(env["HOME"]).name.removeprefix("home-")


def _retirements(pool_env) -> list[str]:
    leases = pool_env.tmp_path / "leases"
    return sorted(
        path.name
        for pattern in ("*.quarantine.json", "*.family-unavailable.*.json")
        for path in leases.glob(pattern)
    )


def _dispatch(pool_env, coordinator, runner, *, model=SONNET_55, allow=None, events=None, **extra):
    return dispatch.dispatch_run(
        prompt="review the PR",
        cwd=str(pool_env.review_dir),
        mode="plan",
        model=model,
        timeout=60,
        max_calls=1,
        allow=allow,
        coordinator=coordinator,
        run_agy_fn=runner,
        operation_hook=events.append if events is not None else None,
        **extra,
    )


# --- (1) MODEL_CAPABILITY_UNAVAILABLE rotates to a capable account -----------


def test_capability_miss_rotates_to_the_account_that_offers_the_model(pool_env) -> None:
    coordinator = pool_env.make({
        "g1": ["claude-sonnet-4-6", "gemini-3.8-flash-high"],
        "g2": ["claude-sonnet-4-6"],
        "primary": ["claude-sonnet-4-6", SONNET_55],
    })
    calls: list[str] = []
    events: list[dict] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        return 0, "review done", "", False, 5

    code = _dispatch(pool_env, coordinator, runner, events=events)

    assert code == 0
    assert calls == ["primary"]  # no provider call on an account without the model
    checks = pool_env.catalog_checks
    assert checks == ["g1", "g2", "primary"]  # preference order, each account once
    rotated = [e for e in events if e.get("phase") == "ACCOUNT_ROTATED"]
    assert [e["failure_kind"] for e in rotated] == ["MODEL_CAPABILITY_UNAVAILABLE"] * (
        len(checks) - 1
    )
    final = pool_env.metas[-1]
    assert final["status"] == "completed"
    assert final["rotations"] == 0  # capability skips do not spend failover budget
    # The accounts without the model are healthy: nothing is retired.
    assert _retirements(pool_env) == []


def test_no_account_offers_the_model_fails_with_a_clear_reason(pool_env) -> None:
    coordinator = pool_env.make({
        "g1": ["claude-sonnet-4-6"],
        "g2": ["claude-sonnet-4-6"],
        "g3": ["gemini-3.8-flash-high"],
    })
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        return 0, "unexpected", "", False, 5

    code = _dispatch(pool_env, coordinator, runner)

    assert code == 64
    assert calls == []
    final = pool_env.metas[-1]
    assert final["status"] == "invalid_model"
    assert final["failure_kind"] == "MODEL_CAPABILITY_UNAVAILABLE"
    assert final["failure_detail"] == (
        "DISPATCH_MODEL_CONTRACT_REJECTED:MODEL_CAPABILITY_UNAVAILABLE:claude-sonnet-5-5"
    )
    assert final["capability_checked_accounts"] == 3
    assert sorted(pool_env.catalog_checks) == ["g1", "g2", "g3"]
    assert _retirements(pool_env) == []
    # Every claim was released: a fresh claim on each account succeeds.
    for _ in range(3):
        coordinator.acquire_claim(consumer_id="after", wait_timeout=0.0)


def test_capability_rotation_never_returns_to_an_account_that_already_ran(pool_env) -> None:
    coordinator = pool_env.make({
        "primary": [SONNET_55],
        "g1": ["claude-sonnet-4-6"],
        "g2": ["claude-sonnet-4-6"],
    })
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        return 1, "", QUOTA_STDERR, False, 5

    code = _dispatch(pool_env, coordinator, runner)

    # primary ran and hit quota; g1 and g2 lack the model; the run ends there.
    assert calls == ["primary"]
    assert code == 64
    assert pool_env.metas[-1]["failure_kind"] == "MODEL_CAPABILITY_UNAVAILABLE"


# --- (2) read-only quota mid-run is no-effect and rotates --------------------


@pytest.mark.parametrize(
    ("allow", "profile_kind"),
    [
        (lambda review_dir: [f"read_file({review_dir}/**)"], "READ_ONLY_RESEARCH"),
        (lambda review_dir: None, "NO_TOOL_PACKET"),
    ],
)
def test_read_only_quota_mid_run_rotates_and_reruns(pool_env, allow, profile_kind) -> None:
    coordinator = pool_env.make({"a": [SONNET_55], "b": [SONNET_55]})
    calls: list[str] = []
    events: list[dict] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        if len(calls) == 1:
            return 1, PARTIAL_REVIEW, QUOTA_STDERR, False, 5
        return 0, "review done", "", False, 5

    code = _dispatch(
        pool_env, coordinator, runner, allow=allow(pool_env.review_dir.resolve()), events=events
    )

    assert code == 0
    assert calls == ["a", "b"]
    classified = [e for e in events if e.get("phase") == "CLASSIFYING_FAILURE"]
    assert classified[0]["failure_kind"] == "PROVIDER_QUOTA_EXHAUSTED_NO_WRITE_PROFILE"
    assert classified[0]["provider_effect"] is False
    assert classified[0]["reconciliation_required"] is False
    final = pool_env.metas[-1]
    assert final["status"] == "completed"
    assert final["rotations"] == 1
    assert final["permission_profile_kind"] == profile_kind


def test_quota_effect_rules() -> None:
    effect = dispatch._quota_failure_effect
    for kind in ("READ_ONLY_RESEARCH", "NO_TOOL_PACKET"):
        assert effect(None, mode="plan", permission_profile_kind=kind) == (
            "PROVIDER_QUOTA_EXHAUSTED_NO_WRITE_PROFILE",
            False,
            False,
        )
        # An observed change still means reconciliation.
        assert effect(["x.py"], mode="plan", permission_profile_kind=kind)[0] == (
            "PROVIDER_QUOTA_EXHAUSTED_AFTER_EFFECT"
        )
    # Write-capable or unclassified profiles keep UNKNOWN_EFFECT.
    for mode, kind in (
        ("accept-edits", "CODING_BOUNDED"),
        ("accept-edits", "READ_ONLY_RESEARCH"),
        ("plan", "CUSTOM"),
        ("plan", None),
    ):
        assert effect(None, mode=mode, permission_profile_kind=kind) == (
            "PROVIDER_QUOTA_EXHAUSTED_UNKNOWN_EFFECT",
            None,
            True,
        )
    assert effect([], mode="accept-edits", permission_profile_kind="CODING_BOUNDED")[0] == (
        "PROVIDER_QUOTA_EXHAUSTED_PRE_EFFECT"
    )


def test_2412_trial_operations_would_have_rotated(tmp_path: Path) -> None:
    """Replay the seven lost trial reviews from their recorded operation.json fields."""
    review_dir = tmp_path / "pr2370-review"
    review_dir.mkdir()
    assert len(TRIAL_2412_QUOTA_OPERATIONS) == 7
    for _op, recorded_kind, recorded_perms, recorded_failure, _model in TRIAL_2412_QUOTA_OPERATIONS:
        assert recorded_failure == "PROVIDER_QUOTA_EXHAUSTED_UNKNOWN_EFFECT"
        allow = [rule.replace("<review>", str(review_dir)) for rule in recorded_perms["allow"]]
        # The recorded grants rebuild to the recorded profile (plan mode).
        permissions, kind, _sha = dispatch.build_effective_permission_profile(
            cwd=str(review_dir), mode="plan", allow_rules=allow
        )
        assert kind == recorded_kind
        assert permissions["deny"] == recorded_perms["deny"]
        # cwd was not a git repo: no change observation (None).
        assert dispatch._quota_failure_effect(
            None, mode="plan", permission_profile_kind=kind, allow_rules=permissions["allow"]
        ) == ("PROVIDER_QUOTA_EXHAUSTED_NO_WRITE_PROFILE", False, False)


# --- Codex r1 on #2435 --------------------------------------------------------


def test_read_only_packet_with_a_write_grant_keeps_unknown_effect() -> None:
    effect = dispatch._quota_failure_effect
    for extra in ("write_file(/repo/**)", "command(git status)"):
        assert effect(
            None,
            mode="plan",
            permission_profile_kind="READ_ONLY_RESEARCH",
            allow_rules=["read_file(/repo/**)", extra],
        ) == ("PROVIDER_QUOTA_EXHAUSTED_UNKNOWN_EFFECT", None, True)
    assert (
        effect(
            None,
            mode="plan",
            permission_profile_kind="READ_ONLY_RESEARCH",
            allow_rules=["read_file(/repo/**)"],
        )[0]
        == "PROVIDER_QUOTA_EXHAUSTED_NO_WRITE_PROFILE"
    )


def test_read_only_dispatch_with_write_grant_does_not_rotate_on_quota(pool_env) -> None:
    coordinator = pool_env.make({"a": [SONNET_55], "b": [SONNET_55]})
    calls: list[str] = []
    review_dir = pool_env.review_dir.resolve()

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        return 1, PARTIAL_REVIEW, QUOTA_STDERR, False, 5

    code = _dispatch(
        pool_env,
        coordinator,
        runner,
        allow=[f"read_file({review_dir}/**)", f"write_file({review_dir}/notes.md)"],
    )

    assert calls == ["a"]
    assert code != 0
    final = pool_env.metas[-1]
    assert final["failure_kind"] == "PROVIDER_QUOTA_EXHAUSTED_UNKNOWN_EFFECT"
    assert final["reconciliation_required"] is True


def test_capable_account_busy_elsewhere_is_pool_busy_not_invalid_model(pool_env) -> None:
    coordinator = pool_env.make({"g1": ["claude-sonnet-4-6"], "primary": [SONNET_55]})
    holder = CrossProcessLeaseCoordinator(
        manager=coordinator.manager,
        allocator_lock_path=pool_env.tmp_path / "allocator.lock",
        leases_dir=pool_env.tmp_path / "leases",
    )
    held = holder.acquire_claim(
        consumer_id="other-task",
        exclude_hashes={hashlib.sha256(b"g1").hexdigest()[:12]},
        wait_timeout=0.0,
    )
    calls: list[str] = []
    try:
        code = _dispatch(
            pool_env,
            coordinator,
            lambda **kw: calls.append(_account_of(kw["env"])) or (0, "x", "", False, 1),
            pool_wait_timeout=0.3,
        )
    finally:
        held.release()

    assert calls == []
    assert code == 75
    final = pool_env.metas[-1]
    assert final["status"] == "pool_busy"
    assert final["failure_kind"] == "AGY_ACCOUNT_POOL_BUSY"
    assert final["capability_checked_accounts"] == 1


def test_capability_skips_stop_at_the_total_deadline(pool_env, monkeypatch) -> None:
    coordinator = pool_env.make({
        "g1": ["claude-sonnet-4-6"],
        "g2": ["claude-sonnet-4-6"],
        "primary": [SONNET_55],
    })
    clock = [1000.0]
    monkeypatch.setattr(dispatch, "_monotonic", lambda: clock[0])
    real_snapshot = dispatch._agy_model_catalog_snapshot

    def slow_snapshot(**kwargs):
        clock[0] += 58.0  # each catalog check eats most of a 60 s budget
        return real_snapshot(**kwargs)

    monkeypatch.setattr(dispatch, "_agy_model_catalog_snapshot", slow_snapshot)
    calls: list[str] = []

    code = _dispatch(
        pool_env, coordinator, lambda **kw: calls.append("ran") or (0, "x", "", False, 1)
    )

    assert calls == []
    assert code == 124
    assert pool_env.catalog_checks == ["g1"]
    assert pool_env.metas[-1]["total_deadline_exhausted"] is True


def test_slow_admitting_catalog_after_a_skip_stops_at_the_deadline(pool_env, monkeypatch) -> None:
    coordinator = pool_env.make({"g1": ["claude-sonnet-4-6"], "primary": [SONNET_55]})
    clock = [1000.0]
    monkeypatch.setattr(dispatch, "_monotonic", lambda: clock[0])
    real_snapshot = dispatch._agy_model_catalog_snapshot

    def snapshot(**kwargs):
        result = real_snapshot(**kwargs)
        if pool_env.catalog_checks[-1] == "primary":
            clock[0] += 58.0  # the admitting check is the slow one
        return result

    monkeypatch.setattr(dispatch, "_agy_model_catalog_snapshot", snapshot)
    calls: list[str] = []

    code = _dispatch(
        pool_env, coordinator, lambda **kw: calls.append("ran") or (0, "x", "", False, 1)
    )

    assert pool_env.catalog_checks == ["g1", "primary"]
    assert calls == []
    assert code == 124
    assert pool_env.metas[-1]["total_deadline_exhausted"] is True
