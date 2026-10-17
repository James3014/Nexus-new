"""#2415: the Gateway Agy worker route retires accounts only on agy's structured errors.

* A host-wide outage (every attempt ``UNAVAILABLE (code 503)``, zero tokens)
  retires at most ``NEXUS_AGY_MAX_ACCOUNT_RETIREMENTS`` accounts and fails as
  ``agy_upstream_unavailable``, instead of marking the whole pool bad.
* A model reply that mentions "401", "quota" or "unavailable" retires nothing.
* Diagnostics: a rotation that ends on a token-less account keeps the receipt's
  ``account_alias_hash`` on the account whose output tails are kept, and a run
  ending ``agy_pool_busy`` after quota failures says so.

stdout/stderr are real agy outputs captured on the Mac mini (redacted).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.executors import worker_registry
from nexus.executors.cli_worker import CliWorkerResult, CliWorkerStatus
from nexus.executors.worker_contract import WorkerOutcome
from nexus.executors.worker_registry import AGY_POOL_BUSY, AgyWorkerAdapter
from nexus.services.agy_account_pool import (
    AgyAccount,
    AgyAccountPoolBusyError,
    AgyAccountPoolManager,
    CrossProcessLeaseCoordinator,
)
from nexus.services.agy_failure_signals import AGY_UPSTREAM_UNAVAILABLE

TOKEN = Path(".gemini") / "antigravity-cli" / "antigravity-oauth-token"


def _envelope(*, status: str, response: str = "", error: str = "", output_tokens: int = 0) -> bytes:
    return (
        json.dumps({
            "conversation_id": "00000000-0000-0000-0000-000000000000",
            "status": status,
            "response": response,
            "error": error,
            "duration_seconds": 0,
            "num_turns": 1,
            "usage": {
                "input_tokens": 0,
                "output_tokens": output_tokens,
                "thinking_tokens": 0,
                "cache_read_tokens": 0,
                "total_tokens": output_tokens,
            },
        })
        + "\n"
    ).encode()


# agyop_19b888c7… (2026-10-03): upstream capacity outage.
OUTAGE_TEXT = (
    "Our servers are experiencing high traffic right now, please try again in a minute. "
    "(UNAVAILABLE (code 503): No capacity available for model gemini-3.8-flash-medium "
    "on the server)"
)
OUTAGE_STDOUT = _envelope(status="ERROR", error=OUTAGE_TEXT)
OUTAGE_STDERR = (
    f"error: {OUTAGE_TEXT}\n"
    'AGY_ERROR: {"short_error":"UNAVAILABLE (code 503): No capacity available for model '
    'gemini-3.8-flash-medium on the server","status":"UNAVAILABLE","error_code":503,'
    '"code_kind":"http","retryable":true,"error_id":"9427d4ac-40fa-49a9-9370-f97746474be9-33-2010"}\n'
).encode()

# probe-e60a20c4…: quota, JSON envelope + AGY_ERROR.
QUOTA_TEXT = (
    "Individual quota reached. Please upgrade your subscription to increase your limits. "
    "Resets in 22h3m37s."
)
QUOTA_STDOUT = _envelope(status="ERROR", error=QUOTA_TEXT)
QUOTA_STDERR = (
    f"error: {QUOTA_TEXT}\n"
    f'AGY_ERROR: {{"short_error":"RESOURCE_EXHAUSTED (code 429): {QUOTA_TEXT}",'
    '"status":"RESOURCE_EXHAUSTED","error_code":429,"code_kind":"http","retryable":true,'
    '"error_id":"d9e1423b-4fe8-4f7c-8626-0e405ac2b88f-1"}\n'
).encode()

# A real Agy review reply (transcript PLANNER_RESPONSE) quoting error tokens,
# returned by a run that did model work and then failed.
MODEL_REPLY = (
    "A provider quota failure (AGY_ERROR RESOURCE_EXHAUSTED / 429) became "
    "PERMISSION_OR_SCOPE_ERROR. The endpoint returns 401 Unauthorized when the token "
    "expired and 503 Service Unavailable otherwise; Authentication required."
)
REPLY_FAILURE_STDOUT = _envelope(status="ERROR", response=MODEL_REPLY, output_tokens=640)
REPLY_EXIT1_SUCCESS_STDOUT = _envelope(status="SUCCESS", response=MODEL_REPLY, output_tokens=640)
OK_STDOUT = _envelope(status="SUCCESS", response="edited", output_tokens=12)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "canonical"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return root.resolve()


def _account_home(tmp_path: Path, name: str, behaviour: str | None) -> Path:
    home = tmp_path / "accounts" / name
    cli = home / ".gemini" / "antigravity-cli"
    cli.mkdir(parents=True)
    (cli / "installation_id").write_text(name, encoding="utf-8")
    if behaviour is not None:
        (home / TOKEN).write_text(behaviour, encoding="utf-8")
    return home


@pytest.fixture
def pool_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    for name in (
        "NEXUS_AGY_WORKER_MODEL",
        "NEXUS_AGY_ACCOUNT_POOL_ENABLED",
        "NEXUS_AGY_ACCOUNT_ALIASES",
        "NEXUS_AGY_BLOCKED_ACCOUNTS",
        "NEXUS_AGY_PREFERRED_ACCOUNTS",
        "NEXUS_AGY_RESERVE_ACCOUNTS",
        "NEXUS_AGY_FALLBACK_ACCOUNTS",
        "NEXUS_AGY_MAX_ACCOUNT_RETIREMENTS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")
    leases = tmp_path / "leases"
    monkeypatch.setenv("NEXUS_AGY_LEASES_DIR", str(leases))
    monkeypatch.setenv("NEXUS_AGY_ALLOCATOR_LOCK_PATH", str(tmp_path / "allocator.lock"))
    gateway_home = tmp_path / "gateway-home"
    gateway_home.mkdir()
    monkeypatch.setenv("HOME", str(gateway_home))
    manager = tmp_path / "pool" / "bin" / "agy-cli-manager"
    manager.parent.mkdir(parents=True)
    manager.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("NEXUS_AGY_ACCOUNT_POOL_MANAGER_PATH", str(manager))
    return SimpleNamespace(leases=leases, tmp_path=tmp_path, monkeypatch=monkeypatch)


def _install_pool(pool_env, behaviours: dict[str, str | None]) -> None:
    pool = AgyAccountPoolManager([
        AgyAccount(alias=name, home_dir=str(_account_home(pool_env.tmp_path, name, behaviour)))
        for name, behaviour in behaviours.items()
    ])
    pool_env.monkeypatch.setattr(
        "nexus.services.agy_account_pool.get_account_pool_manager", lambda: pool
    )
    pool_env.monkeypatch.setenv("NEXUS_AGY_PREFERRED_ACCOUNTS", ",".join(behaviours))


_OUTPUTS = {
    "outage": (OUTAGE_STDOUT, OUTAGE_STDERR, 1),
    "quota": (QUOTA_STDOUT, QUOTA_STDERR, 1),
    "reply-failure": (REPLY_FAILURE_STDOUT, b"", 1),
    "reply-exit1": (REPLY_EXIT1_SUCCESS_STDOUT, b"", 1),
    "ok": (OK_STDOUT, b"", 0),
}


def _fake_agy(pool_env, seen: list[str]) -> None:
    def fake_worker(request, on_process_group=None):
        behaviour = (Path(request.env["HOME"]) / TOKEN).read_text(encoding="utf-8")
        seen.append(behaviour)
        stdout, stderr, code = _OUTPUTS[behaviour]
        return CliWorkerResult(
            status=CliWorkerStatus.COMPLETED,
            executable_identity=request.executable,
            argv=request.argv,
            cwd=request.cwd,
            exit_code=code,
            stdout=stdout,
            stderr=stderr,
            wall_time_ms=3,
            process_group_id=None,
            timed_out=False,
            descendants_swept=True,
        )

    pool_env.monkeypatch.setattr(worker_registry, "run_cli_worker", fake_worker)


def _invoke(pool_env, *, calls: int = 1):
    target = pool_env.tmp_path / "target"
    target.mkdir(exist_ok=True)
    adapter = AgyWorkerAdapter(
        use_installed_account_pool=True, canonical_root=_repo(pool_env.tmp_path)
    )
    return adapter.invoke(
        SimpleNamespace(task_id="agy-2415", maximum_provider_calls=calls),
        SimpleNamespace(target_worktree=str(target.resolve())),
        prompt="bounded task",
        worker_role="implementation",
        timeout_seconds=120.0,
    )


def _hash(name: str) -> str:
    return AgyAccount(alias=name, home_dir="/").alias_hash


def _retired(pool_env) -> set[str]:
    return {path.name.split(".")[0] for path in pool_env.leases.glob("*.quarantine.json")}


def test_outage_retires_at_most_the_cap_and_fails_as_upstream_unavailable(pool_env):
    names = [f"acc{i}" for i in range(6)]
    _install_pool(pool_env, {name: "outage" for name in names})
    seen: list[str] = []
    _fake_agy(pool_env, seen)

    receipt = _invoke(pool_env)

    assert len(seen) == 3
    assert _retired(pool_env) == {_hash(name) for name in names[:3]}
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason is not None
    assert receipt.failure_reason.startswith(f"{AGY_UPSTREAM_UNAVAILABLE}: 3 accounts")
    assert "ACCOUNT_UNAVAILABLE" in receipt.failure_reason
    assert receipt.provider_calls == 0
    assert receipt.account_rotation_attempts == 3
    assert receipt.account_alias_hash == _hash("acc2")


def test_outage_cap_follows_the_setting(pool_env):
    pool_env.monkeypatch.setenv("NEXUS_AGY_MAX_ACCOUNT_RETIREMENTS", "2")
    _install_pool(pool_env, {"o1": "outage", "o2": "outage", "o3": "outage", "o4": "ok"})
    seen: list[str] = []
    _fake_agy(pool_env, seen)

    receipt = _invoke(pool_env)

    assert seen == ["outage", "outage"]
    assert _retired(pool_env) == {_hash("o1"), _hash("o2")}
    assert receipt.failure_reason is not None
    assert receipt.failure_reason.startswith(AGY_UPSTREAM_UNAVAILABLE)


def test_one_unavailable_account_still_rotates_to_a_healthy_one(pool_env):
    _install_pool(pool_env, {"down": "outage", "up": "ok"})
    seen: list[str] = []
    _fake_agy(pool_env, seen)

    receipt = _invoke(pool_env)

    assert seen == ["outage", "ok"]
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert _retired(pool_env) == {_hash("down")}


def test_quota_cooldowns_do_not_count_toward_the_cap(pool_env):
    _install_pool(pool_env, {f"q{i}": "quota" for i in range(5)} | {"ok": "ok"})
    seen: list[str] = []
    _fake_agy(pool_env, seen)

    receipt = _invoke(pool_env)

    assert seen == ["quota"] * 5 + ["ok"]
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert _retired(pool_env) == set()
    assert len(list(pool_env.leases.glob("*.family-unavailable.gemini.json"))) == 5


@pytest.mark.parametrize("behaviour", ["reply-failure", "reply-exit1"])
def test_model_reply_with_401_and_quota_retires_nothing(pool_env, behaviour):
    _install_pool(pool_env, {"healthy": behaviour, "other": "ok"})
    seen: list[str] = []
    _fake_agy(pool_env, seen)

    receipt = _invoke(pool_env)

    assert seen == [behaviour]
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == "non-eligible account failure: UNKNOWN"
    assert _retired(pool_env) == set()
    assert list(pool_env.leases.glob("*.family-unavailable.*.json")) == []


def test_classifier_reads_only_agy_error_channels():
    classify = AgyWorkerAdapter._classify_failure_static
    status = CliWorkerStatus.COMPLETED
    assert classify(status, 1, REPLY_FAILURE_STDOUT, b"").value == "UNKNOWN"
    assert classify(status, 1, OUTAGE_STDOUT, OUTAGE_STDERR).value == "ACCOUNT_UNAVAILABLE"
    assert classify(status, 1, QUOTA_STDOUT, b"").value == "QUOTA_EXHAUSTED"
    assert classify(status, 2, REPLY_FAILURE_STDOUT, b"").value == "SYNTAX_OR_IMPLEMENTATION_ERROR"
    reply = CliWorkerResult(
        status=status,
        executable_identity="/bin/agy",
        argv=(),
        cwd="/",
        exit_code=1,
        stdout=_envelope(status="ERROR", response="Resets in 999h."),
        stderr=b"",
        wall_time_ms=1,
        process_group_id=None,
    )
    assert worker_registry._agy_quota_reset_seconds(reply) is None
    assert worker_registry._agy_login_required(reply) is False


def test_rotation_ending_on_a_tokenless_account_keeps_the_tails_owner(pool_env):
    _install_pool(pool_env, {"spent": "quota", "no-token": None})
    seen: list[str] = []
    _fake_agy(pool_env, seen)

    receipt = _invoke(pool_env)

    assert seen == ["quota"]
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.stderr_tail is not None and "Resets in" in receipt.stderr_tail
    # The kept tails are the quota account's; the hash names that account.
    assert receipt.account_alias_hash == _hash("spent")


def test_pool_busy_after_quota_mentions_the_quota(pool_env):
    _install_pool(pool_env, {"spent": "quota", "busy": "ok"})
    real_acquire = CrossProcessLeaseCoordinator.acquire_claim
    calls = {"n": 0}

    def acquire(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] > 1:
            raise AgyAccountPoolBusyError("all remaining accounts are claimed")
        return real_acquire(self, *args, **kwargs)

    pool_env.monkeypatch.setattr(CrossProcessLeaseCoordinator, "acquire_claim", acquire)
    seen: list[str] = []
    _fake_agy(pool_env, seen)

    receipt = _invoke(pool_env)

    assert seen == ["quota"]
    assert receipt.failure_reason == (
        f"{AGY_POOL_BUSY}: after quota exhaustion on 1 account(s), earliest reset in 22h03m37s"
    )


def test_token_less_accounts_do_not_count_toward_the_cap(pool_env):
    """#2433 (N1): a token-less account is a local fact, not a provider outage.

    With a cap of 2, one provider-reported outage plus token-less accounts
    before and after it must still rotate to the healthy account.  A mutant
    that counts token-less refusals reaches the cap and stops as upstream
    unavailable.
    """
    pool_env.monkeypatch.setenv("NEXUS_AGY_MAX_ACCOUNT_RETIREMENTS", "2")
    _install_pool(
        pool_env,
        {"no-token-a": None, "down": "outage", "no-token-b": None, "up": "ok"},
    )
    seen: list[str] = []
    _fake_agy(pool_env, seen)

    receipt = _invoke(pool_env)

    assert seen == ["outage", "ok"]
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert receipt.failure_reason is None
    assert _retired(pool_env) == {_hash("no-token-a"), _hash("down"), _hash("no-token-b")}
