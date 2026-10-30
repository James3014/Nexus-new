"""#2998 F1: the bench lease path refuses while the Agy pool is stopped.

``run_with_account_lease`` (reached by the workforce model auto-update
``attest()`` via ``ask_direct_agy_patch``) used to lease a pool account
without the #2990 stop check.  Offline: the in-memory pool fixture from
conftest.py, a fake agy executable, no real account.
"""

from __future__ import annotations

import pytest

from scripts.bench import agy_account_lease as lease
from scripts.bench.agy_provider import ask_direct_agy_patch

OVERRIDE = "NEXUS_AGY_POOL_STOPPED_OVERRIDE"


class _NoLeaseCoordinator:
    def __getattr__(self, name: str):
        raise AssertionError(f"coordinator touched while stopped: {name}")


def test_run_with_account_lease_refuses_before_reading_or_leasing_the_pool(monkeypatch):
    monkeypatch.delenv(OVERRIDE, raising=False)
    attempts: list[object] = []

    run = lease.run_with_account_lease(
        model="gemini-3.8-flash-medium",
        attempt=lambda env: attempts.append(env),  # type: ignore[arg-type,return-value]
        base_env={},
        config=lease.BenchLeaseConfig(),
        coordinator=_NoLeaseCoordinator(),  # type: ignore[arg-type]
    )

    assert run.status == "failed"
    assert run.failure_kind == lease.POOL_STOPPED == "AGY_ACCOUNT_POOL_STOPPED"
    assert run.result is None
    assert attempts == []
    assert lease.POOL_STOPPED in lease.PRE_CALL_LEASE_FAILURES


def test_ask_direct_agy_patch_makes_no_call_and_takes_no_lease_while_stopped(agy_pool, monkeypatch):
    monkeypatch.delenv(OVERRIDE, raising=False)

    out, _raw = ask_direct_agy_patch(prompt="p", timeout_sec=30, env=agy_pool.env())

    assert out["status"] == "FAIL"
    assert out["error_category"] == lease.POOL_STOPPED
    assert out["provider_call_attempted"] is False
    assert agy_pool.calls() == []
    assert not agy_pool.leases_dir.exists() or not any(agy_pool.leases_dir.iterdir())


def test_workforce_attest_fails_closed_while_stopped(agy_pool, monkeypatch):
    """The issue's F1 path: attest() -> live_attest_call -> ask_direct_agy_patch."""
    from scripts.ops import workforce_model_autoupdate as autoupdate

    monkeypatch.delenv(OVERRIDE, raising=False)
    for key, value in agy_pool.env(**{lease.ACCOUNT_ALLOWLIST_ENV: "acc-a,acc-b"}).items():
        monkeypatch.setenv(key, value)

    result = autoupdate.attest("gemini-3.8-flash-medium", "Gemini 3.8 Flash (Medium)")

    assert result.ok is False
    assert result.reason == f"IDENTITY_NOT_OK:{lease.POOL_STOPPED}"
    assert result.receipt.get("provider_call_attempted") is False
    assert agy_pool.calls() == []


def test_stopped_pool_is_infra_invalid_not_a_model_failure():
    from scripts.bench.benchmark_eligibility import classify_infra_invalid_reason

    row = {"baseline_gateway_error_category": lease.POOL_STOPPED, "model_calls": 1}
    reason = classify_infra_invalid_reason(row, model_required=True, nexus_required=False)
    assert reason == lease.POOL_STOPPED.lower()


def test_bench_lease_still_works_with_the_override(agy_pool):
    # tests/conftest.py sets NEXUS_AGY_POOL_STOPPED_OVERRIDE=1 for every test.
    out, _raw = ask_direct_agy_patch(prompt="p", timeout_sec=30, env=agy_pool.env())
    assert out["model_identity_status"] == lease.MODEL_IDENTITY_OK
    assert len(agy_pool.calls()) == 1


@pytest.mark.parametrize("value", ["0", "true", ""])
def test_only_exact_one_overrides(agy_pool, monkeypatch, value):
    monkeypatch.setenv(OVERRIDE, value)
    out, _raw = ask_direct_agy_patch(prompt="p", timeout_sec=30, env=agy_pool.env())
    assert out["error_category"] == lease.POOL_STOPPED
    assert agy_pool.calls() == []
