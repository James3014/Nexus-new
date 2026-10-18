"""Bench Agy calls: exact model, observed identity, contained posture, leased 5h-quota accounts (#1932).

Offline: a fake agy executable, a temp leases dir and an in-memory pool fixture (conftest.py).
"""

from __future__ import annotations

import fcntl
import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.bench import agy_account_lease as lease
from scripts.bench.agy_provider import AGY_DEFAULT_MODEL, AGY_NO_TOOLS_PREFIX, ask_direct_agy_patch

MODEL = AGY_DEFAULT_MODEL  # gemini-3.8-flash-medium
# Same window shape as ~/.nexus/agy-account-pool/quota-snapshot.json (see conftest.py).
FIVE_HOUR_OK = {"status": "known", "remaining_pct": 80.0, "reset_at": "2099-01-01T00:00:00Z"}
WEEKLY_OK = {"status": "known", "remaining_pct": 60.0, "reset_at": "2099-01-01T00:00:00Z"}
SPENT = {"status": "known", "remaining_pct": 0.0, "reset_at": "2099-01-01T00:00:00Z"}


def _argv(call: dict) -> list[str]:
    return call["argv"]


def _flag(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


# --- fix 1 + shared: model in argv, contained posture, observed identity -------------------------


def test_requested_model_is_passed_and_posture_is_plan_sandbox_without_bypass(agy_pool):
    out, _raw = ask_direct_agy_patch(prompt="fix it", timeout_sec=30, env=agy_pool.env())
    assert out["patch"] == "x = 1\n"
    [call] = agy_pool.calls()
    argv = _argv(call)
    assert _flag(argv, "--model") == MODEL
    assert _flag(argv, "--mode") == "plan"
    assert "--sandbox" in argv[: argv.index("--print")]
    assert not set(argv) & lease.AGY_BYPASS_FLAGS
    assert _flag(argv, "--print") == AGY_NO_TOOLS_PREFIX + "fix it"
    assert out["requested_model"] == MODEL
    assert out["observed_model"] == MODEL
    assert out["observed_model_label"] == "Gemini 3.8 Flash (Medium)"
    assert out["model_identity_status"] == lease.MODEL_IDENTITY_OK


@pytest.mark.parametrize(
    "argv",
    [
        ["agy", "--mode", "plan", "--sandbox", "--model", "m", "--dangerously-skip-permissions"],
        ["agy", "--mode", "plan", "--sandbox", "--model", "m", "--auto-approve"],
        ["agy", "--mode", "accept-edits", "--sandbox", "--model", "m"],
        ["agy", "--mode", "plan", "--model", "m"],
        ["agy", "--mode", "plan", "--sandbox"],
    ],
)
def test_posture_guard_rejects_bypass_wrong_mode_missing_sandbox_or_model(argv):
    with pytest.raises(ValueError, match=lease.AGY_POSTURE_VIOLATION):
        lease.assert_contained_agy_argv([*argv, "--print", "p"])


def test_prompt_text_after_print_is_not_mistaken_for_a_flag():
    lease.assert_contained_agy_argv([
        "agy",
        "--mode",
        "plan",
        "--sandbox",
        "--model",
        "m",
        "--print",
        "--auto-approve",
    ])


def test_backend_label_mismatch_fails_closed_and_is_never_scored(agy_pool):
    agy_pool.set_behaviour('{"status": "ok", "patch": "x = 1\\n"}', default="mismatch")
    out, raw = ask_direct_agy_patch(prompt="p", timeout_sec=30, env=agy_pool.env())
    assert out["status"] == "FAIL"
    assert out["error_category"] == lease.MODEL_IDENTITY_MISMATCH
    assert out["observed_model_label"] == "Gemini 3.8 Flash (High)"
    assert "patch" not in out
    assert raw.startswith(lease.MODEL_IDENTITY_MISMATCH)


def test_missing_model_observation_fails_closed(agy_pool):
    agy_pool.set_behaviour('{"status": "ok", "patch": "x = 1\\n"}', default="nolog")
    out, _ = ask_direct_agy_patch(prompt="p", timeout_sec=30, env=agy_pool.env())
    assert out["error_category"] == lease.MODEL_IDENTITY_UNOBSERVED
    assert out["observed_model"] is None
    assert "patch" not in out


def test_identity_verdict_catches_silent_substitution_seen_in_real_agy_logs():
    # Real Agy log: the request is echoed on the Resolving line, a different model is served.
    log = (
        "I1011 model_resolver.go:93] Resolving model claude-sonnet-5-5-medium\n"
        'I1011 model_config_manager.go:327] Propagating selected model override to backend: label="Gemini 3.8 Flash (High)"\n'
    )
    verdict = lease.model_identity_verdict(
        "claude-sonnet-5-5-medium", lease.parse_agy_model_observation(log)
    )
    assert verdict["model_identity_status"] == lease.MODEL_IDENTITY_MISMATCH
    alias = (
        'model_resolver.go:116] model alias "gemini-3.8-flash" resolved to "gemini-3.8-flash-low"\n'
        "model_resolver.go:93] Resolving model gemini-3.8-flash\n"
        'Propagating selected model override to backend: label="Gemini 3.8 Flash (Low)"\n'
    )
    verdict = lease.model_identity_verdict(MODEL, lease.parse_agy_model_observation(alias))
    assert verdict["model_identity_status"] == lease.MODEL_IDENTITY_MISMATCH
    assert verdict["observed_model"] == "gemini-3.8-flash-low"


def test_three_arm_agy_command_carries_model_and_contained_posture(tmp_path: Path, monkeypatch):
    import importlib.util

    path = (
        Path(__file__).resolve().parents[2]
        / "scripts/bench/experimental/model_workforce_three_arm.py"
    )
    spec = importlib.util.spec_from_file_location("three_arm_1932", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["three_arm_1932"] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "_binary_for", lambda _spec: "/bin/agy")
    model_spec = mod.ModelSpec(
        model_id="agy_flash_38",
        cohort="required",
        provider="agy",
        transport="agy_cli",
        model=MODEL,
        timeout_sec=240,
        resource_tier="cloud_subscription",
    )
    isolated = tmp_path / "iso"
    isolated.mkdir()
    argv = mod._subprocess_command(model_spec, "prompt", isolated)
    assert _flag(argv, "--model") == MODEL
    assert _flag(argv, "--mode") == "plan" and "--sandbox" in argv
    assert not set(argv) & lease.AGY_BYPASS_FLAGS
    log_path = Path(_flag(argv, "--log-file"))
    assert isolated not in log_path.parents

    # Observed identity is recorded and a mismatch fails closed.
    def fake_run(command, **kwargs):
        log_path.write_text(
            f"Resolving model {MODEL}\n"
            'Propagating selected model override to backend: label="Gemini 3.8 Flash (High)"\n'
        )
        return subprocess.CompletedProcess(command, 0, stdout='{"accounting": {}}', stderr="")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    invocation = mod.invoke_subprocess(model_spec, "prompt", isolated)
    assert invocation.error == lease.MODEL_IDENTITY_MISMATCH
    assert invocation.delivered is False
    payload = mod._invocation_payload(invocation, {})
    assert payload["model_identity"]["requested_model"] == MODEL
    assert payload["model_identity"]["observed_model_label"] == "Gemini 3.8 Flash (High)"


# --- fix 2: lease lifecycle -----------------------------------------------------------------------


def _lock_is_free(pool, name: str) -> bool:
    from nexus.services.agy_account_pool import AgyAccount

    alias_hash = AgyAccount(alias=name, home_dir="").alias_hash
    with (pool.leases_dir / f"{alias_hash}.lock").open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return not (pool.leases_dir / f"{alias_hash}.receipt.json").exists()


def test_lease_is_acquired_runs_agy_under_the_leased_home_and_is_released(agy_pool):
    out, _ = ask_direct_agy_patch(prompt="p", timeout_sec=30, env=agy_pool.env())
    [call] = agy_pool.calls()
    account = agy_pool.account_for_home(call["home"])  # HOME is the leased account's
    assert out["account_pool_source"] == "fixture"
    assert out["account_alias_hash"] and out["lease_id_hash"]
    assert out["account_quota_state"] == lease.FIVE_HOUR_AVAILABLE
    assert account not in out["account_alias_hash"]  # only hashes are recorded
    assert all(_lock_is_free(agy_pool, name) for name in agy_pool.accounts)


def test_lease_is_released_when_the_attempt_raises(agy_pool):
    def boom(*args, **kwargs):
        raise RuntimeError("runner exploded")

    with pytest.raises(RuntimeError, match="runner exploded"):
        ask_direct_agy_patch(prompt="p", timeout_sec=30, env=agy_pool.env(), runner=boom)
    assert all(_lock_is_free(agy_pool, name) for name in agy_pool.accounts)


def test_account_leased_by_another_process_is_skipped(agy_pool):
    from nexus.services.agy_account_pool import AgyAccount

    held = {"acc-a", "acc-b"}
    agy_pool.leases_dir.mkdir(parents=True, exist_ok=True)
    locks = " ".join(
        repr(str(agy_pool.leases_dir / f"{AgyAccount(alias=n, home_dir='').alias_hash}.lock"))
        for n in sorted(held)
    )
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl, sys, time\n"
            f"fs = [open(p, 'a+') for p in [{locks.replace(' ', ', ')}]]\n"
            "[fcntl.flock(f.fileno(), fcntl.LOCK_EX) for f in fs]\n"
            "print('ready', flush=True)\n"
            "sys.stdin.read()\n",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == "ready"
        out, _ = ask_direct_agy_patch(prompt="p", timeout_sec=30, env=agy_pool.env())
        [call] = agy_pool.calls()
        assert agy_pool.account_for_home(call["home"]) == "acc-c"
        assert out["model_identity_status"] == lease.MODEL_IDENTITY_OK

        # With every allowlisted account held elsewhere, the bench waits and fails closed.
        out, _ = ask_direct_agy_patch(
            prompt="p",
            timeout_sec=30,
            env=agy_pool.env(NEXUS_AGY_ACCOUNT_ALLOWLIST="acc-a,acc-b"),
        )
        assert out["error_category"] == lease.POOL_BUSY
        assert out["provider_call_attempted"] is False
        assert len(agy_pool.calls()) == 1
    finally:
        holder.communicate("")


def test_allowlist_is_honored(agy_pool):
    for _ in range(3):
        out, _ = ask_direct_agy_patch(
            prompt="p", timeout_sec=30, env=agy_pool.env(NEXUS_AGY_ACCOUNT_ALLOWLIST="acc-b")
        )
        assert out["model_identity_status"] == lease.MODEL_IDENTITY_OK
    assert {agy_pool.account_for_home(c["home"]) for c in agy_pool.calls()} == {"acc-b"}

    # An explicit allowlist argument overrides the env.
    config = lease.BenchLeaseConfig.from_env(agy_pool.env(), allowlist=["acc-c"])
    out, _ = ask_direct_agy_patch(
        prompt="p",
        timeout_sec=30,
        env=agy_pool.env(),
        lease_config=config,
        coordinator=agy_pool.coordinator(),
    )
    assert agy_pool.account_for_home(agy_pool.calls()[-1]["home"]) == "acc-c"
    assert out["account_pool_source"] == "injected"


def test_allowlist_naming_no_known_account_makes_no_call(agy_pool):
    out, raw = ask_direct_agy_patch(
        prompt="p", timeout_sec=30, env=agy_pool.env(NEXUS_AGY_ACCOUNT_ALLOWLIST="acc-zzz")
    )
    assert out["error_category"] == lease.NO_ELIGIBLE_ACCOUNT
    assert out["provider_call_attempted"] is False
    assert agy_pool.calls() == []


# --- 5-hour quota window --------------------------------------------------------------------------


def test_only_accounts_with_available_five_hour_window_are_leased(agy_pool):
    agy_pool.write_snapshot({
        "acc-a": {"weekly": SPENT},  # weekly spent: the snapshot omits the 5h window
        "acc-b": {"weekly": WEEKLY_OK, "5h": SPENT},
        "acc-c": {"weekly": WEEKLY_OK, "5h": FIVE_HOUR_OK},
    })
    for _ in range(3):
        ask_direct_agy_patch(prompt="p", timeout_sec=30, env=agy_pool.env())
    assert {agy_pool.account_for_home(c["home"]) for c in agy_pool.calls()} == {"acc-c"}


def test_classification_of_five_hour_window_states():
    now = 4_000_000_000.0
    checked = "2096-10-02T07:06:40+00:00"  # == now
    common = {
        "snapshot_checked_at": checked,
        "family": "gemini",
        "now_ts": now,
        "max_age_seconds": 300,
    }

    def row(gemini):
        return {
            "account": "x",
            "ok": True,
            "checked_at": checked,
            "groups": {"Gemini Models": gemini},
        }

    assert (
        lease.classify_account_quota(row({"weekly": WEEKLY_OK, "5h": FIVE_HOUR_OK}), **common)[
            "state"
        ]
        == lease.FIVE_HOUR_AVAILABLE
    )
    assert (
        lease.classify_account_quota(row({"weekly": WEEKLY_OK, "5h": SPENT}), **common)["state"]
        == lease.QUOTA_5H_EXHAUSTED
    )
    assert (
        lease.classify_account_quota(row({"weekly": SPENT, "5h": FIVE_HOUR_OK}), **common)["state"]
        == lease.QUOTA_WEEKLY_EXHAUSTED
    )
    assert (
        lease.classify_account_quota(row({"weekly": WEEKLY_OK}), **common)["state"]
        == lease.QUOTA_WINDOW_UNKNOWN
    )
    assert (
        lease.classify_account_quota(
            row({"weekly": WEEKLY_OK, "5h": {"status": "unknown"}}), **common
        )["state"]
        == lease.QUOTA_WINDOW_UNKNOWN
    )
    rolled = {"status": "known", "remaining_pct": 0.0, "reset_at": "2000-01-01T00:00:00Z"}
    assert (
        lease.classify_account_quota(row({"weekly": WEEKLY_OK, "5h": rolled}), **common)["state"]
        == lease.FIVE_HOUR_AVAILABLE
    )
    assert lease.classify_account_quota(None, **common)["state"] == lease.QUOTA_WINDOW_UNKNOWN
    stale = {
        **row({"weekly": WEEKLY_OK, "5h": FIVE_HOUR_OK}),
        "checked_at": "2096-10-02T06:00:00+00:00",
    }
    assert lease.classify_account_quota(stale, **common)["state"] == lease.QUOTA_SNAPSHOT_STALE


def test_unknown_five_hour_window_fails_closed_unless_overridden(agy_pool):
    agy_pool.write_snapshot({name: {"weekly": WEEKLY_OK} for name in agy_pool.accounts})
    out, raw = ask_direct_agy_patch(prompt="p", timeout_sec=30, env=agy_pool.env())
    assert out["error_category"] == lease.QUOTA_WINDOW_UNKNOWN == raw
    assert out["provider_call_attempted"] is False
    assert agy_pool.calls() == []

    out, _ = ask_direct_agy_patch(
        prompt="p", timeout_sec=30, env=agy_pool.env(NEXUS_AGY_ALLOW_UNKNOWN_QUOTA_WINDOW="1")
    )
    assert out["model_identity_status"] == lease.MODEL_IDENTITY_OK
    assert out["account_quota_state"] == lease.QUOTA_WINDOW_UNKNOWN


def test_stale_snapshot_fails_closed_and_override_never_admits_exhausted(agy_pool):
    agy_pool.write_snapshot(
        {name: {"weekly": WEEKLY_OK, "5h": FIVE_HOUR_OK} for name in agy_pool.accounts},
        age_seconds=3600,
    )
    out, _ = ask_direct_agy_patch(prompt="p", timeout_sec=30, env=agy_pool.env())
    assert out["error_category"] == lease.QUOTA_WINDOW_UNKNOWN
    assert out["account_eligibility_states"] == [lease.QUOTA_SNAPSHOT_STALE]

    agy_pool.write_snapshot({
        name: {"weekly": WEEKLY_OK, "5h": SPENT} for name in agy_pool.accounts
    })
    out, _ = ask_direct_agy_patch(
        prompt="p", timeout_sec=30, env=agy_pool.env(NEXUS_AGY_ALLOW_UNKNOWN_QUOTA_WINDOW="1")
    )
    assert out["error_category"] == lease.NO_ELIGIBLE_ACCOUNT
    assert agy_pool.calls() == []


# --- quota errors: rotate before effect, retire after effect -----------------------------------


def test_quota_error_before_any_effect_rotates_to_another_allowed_account(agy_pool, monkeypatch):
    # Deterministic order through the coordinator's own preference tier.
    monkeypatch.setenv("NEXUS_AGY_PREFERRED_ACCOUNTS", "acc-a,acc-b,acc-c")
    agy_pool.set_behaviour(
        '{"status": "ok", "patch": "x = 1\\n"}', **{"acc-a": "quota_pre", "acc-b": "quota_pre"}
    )
    out, _ = ask_direct_agy_patch(prompt="p", timeout_sec=30, env=agy_pool.env())
    homes = [agy_pool.account_for_home(c["home"]) for c in agy_pool.calls()]
    assert homes == ["acc-a", "acc-b", "acc-c"]
    assert out["patch"] == "x = 1\n"
    assert out["account_rotations"] == 2 and out["run_retired"] is False
    outcomes = [r["outcome"] for r in out["account_lease_records"]]
    assert outcomes == [lease.QUOTA_EXHAUSTED_PRE_EFFECT] * 2 + ["completed"]
    # The exhausted accounts are retired for the gemini family in the shared leases dir.
    assert len(list(agy_pool.leases_dir.glob("*.family-unavailable.gemini.json"))) == 2
    assert all(_lock_is_free(agy_pool, name) for name in agy_pool.accounts)


def test_quota_error_after_a_provider_effect_retires_the_run_without_retry(agy_pool):
    agy_pool.set_behaviour("", default="quota_after")
    out, _ = ask_direct_agy_patch(prompt="p", timeout_sec=30, env=agy_pool.env())
    assert len(agy_pool.calls()) == 1
    assert out["status"] == "FAIL"
    assert out["error_category"] == lease.QUOTA_EXHAUSTED_AFTER_EFFECT
    assert out["run_retired"] is True and out["account_rotations"] == 0
    assert out["provider_call_attempted"] is True
    assert all(_lock_is_free(agy_pool, name) for name in agy_pool.accounts)


def test_quota_rotation_stops_when_every_allowed_account_is_spent(agy_pool):
    agy_pool.set_behaviour("", default="quota_pre")
    out, _ = ask_direct_agy_patch(
        prompt="p", timeout_sec=30, env=agy_pool.env(NEXUS_AGY_ACCOUNT_ALLOWLIST="acc-a,acc-b")
    )
    assert len(agy_pool.calls()) == 2
    assert out["error_category"] == lease.QUOTA_EXHAUSTED_PRE_EFFECT
    assert out["run_retired"] is False


def test_lease_failures_and_identity_failures_are_infra_invalid_not_model_failures():
    from scripts.bench.benchmark_eligibility import classify_infra_invalid_reason

    for category in (
        lease.MODEL_IDENTITY_MISMATCH,
        lease.QUOTA_WINDOW_UNKNOWN,
        lease.QUOTA_EXHAUSTED_AFTER_EFFECT,
    ):
        row = {"baseline_gateway_error_category": category, "model_calls": 1}
        reason = classify_infra_invalid_reason(row, model_required=True, nexus_required=False)
        assert reason == category.lower()


def test_eligible_accounts_from_a_snapshot_shape_like_the_live_one():
    snapshot = json.loads(
        json.dumps({
            "checked_at": "2096-10-02T07:06:40+00:00",
            "accounts": [
                {
                    "account": "a",
                    "ok": True,
                    "checked_at": "2096-10-02T07:06:00+00:00",
                    "groups": {"Gemini Models": {"weekly": WEEKLY_OK, "5h": FIVE_HOUR_OK}},
                },
                {
                    "account": "b",
                    "ok": True,
                    "checked_at": "2096-10-02T07:06:00+00:00",
                    "groups": {"Gemini Models": {"weekly": SPENT}},
                },
            ],
        })
    )
    result = lease.account_eligibility(
        ["a", "b", "c"],
        snapshot,
        family="gemini",
        allowlist=["a", "b", "c"],
        now_ts=4_000_000_000.0,
    )
    assert {n for n, info in result.items() if info["eligible"]} == {"a"}
    assert result["b"]["state"] == lease.QUOTA_WEEKLY_EXHAUSTED
    assert result["c"]["state"] == lease.QUOTA_WINDOW_UNKNOWN


def test_2619_stale_row_after_failed_refresh_is_not_eligible(tmp_path: Path):
    """#2619: the bench lease reader treats a writer-demoted stale row as unknown."""
    from importlib.machinery import SourceFileLoader

    root = Path(__file__).resolve().parents[2]
    quota = SourceFileLoader(
        "nexus_agy_quota_canonical_bench_2619", str(root / "scripts" / "ops" / "nexus-agy-quota")
    ).load_module()
    checked = "2096-10-02T07:06:00+00:00"
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(
        json.dumps({
            "checked_at": checked,
            "accounts": [
                {
                    "account": "a",
                    "ok": True,
                    "checked_at": checked,
                    "groups": {"Gemini Models": {"weekly": WEEKLY_OK, "5h": FIVE_HOUR_OK}},
                }
            ],
        }),
        encoding="utf-8",
    )
    snapshot = quota.merge_snapshot(
        snapshot_path=snapshot_path,
        current_names={"a"},
        refreshed_rows=[
            {
                "account": "a",
                "ok": False,
                "error": "quota_exhausted",
                "checked_at": "2096-10-02T07:06:40+00:00",
            }
        ],
        partial=True,
        checked_at="2096-10-02T07:06:40+00:00",
    )
    row = snapshot["accounts"][0]
    info = lease.classify_account_quota(
        row,
        snapshot_checked_at=snapshot["checked_at"],
        family="gemini",
        now_ts=4_000_000_000.0,
        max_age_seconds=300,
    )
    assert info["state"] == lease.QUOTA_WINDOW_UNKNOWN
    assert info["five_hour_remaining_pct"] is None
    result = lease.account_eligibility(
        ["a"], snapshot, family="gemini", allowlist=["a"], now_ts=4_000_000_000.0
    )
    assert result["a"]["eligible"] is False
