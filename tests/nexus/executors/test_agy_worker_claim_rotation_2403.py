"""#2403 follow-up: the Agy worker route rotates pool accounts under cross-process claims.

James: 「應該要失敗後會再換帳號」 ("after a failure it should switch to another
account").  Live, the route ran with ``maximum_provider_calls = 1``, so a
quota-exhausted account ended the run.  Now:

* every account is held under the probe's ``CrossProcessLeaseCoordinator`` flock claim;
* a quota / rate-limit / login rejection, or an account without an OAuth token,
  retires that account (quota: model-family cooldown until the reported reset)
  and claims the next one; such rejections are ``account_rotation_attempts`` and
  do not spend ``maximum_provider_calls``;
* the loop is bounded by the pool; an empty pool is ``agy_pool_exhausted`` with
  the earliest known reset.
"""

from __future__ import annotations

import fcntl
import json
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.executors import worker_registry
from nexus.executors.cli_worker import CliWorkerResult, CliWorkerStatus
from nexus.executors.worker_contract import WorkerOutcome
from nexus.executors.worker_registry import (
    AGY_AUTHENTICATION_REQUIRED,
    AGY_POOL_EXHAUSTED,
    AgyWorkerAdapter,
    _agy_attempt_had_model_output,
    _agy_quota_reset_seconds,
)
from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

TOKEN = Path(".gemini") / "antigravity-cli" / "antigravity-oauth-token"


def _envelope(status: str, *, output_tokens: int = 0, error: str = "") -> bytes:
    return json.dumps({
        "conversation_id": "c",
        "status": status,
        "response": "edited" if status == "SUCCESS" else "",
        "error": error,
        "num_turns": 1,
        "usage": {"input_tokens": 0, "output_tokens": output_tokens, "thinking_tokens": 0},
    }).encode()


QUOTA_TEXT = "Individual quota reached. Please upgrade your subscription. Resets in 1h0m0s."
QUOTA_STDOUT = _envelope("ERROR", error=QUOTA_TEXT)
QUOTA_STDERR = (
    f'error: {QUOTA_TEXT}\nAGY_ERROR: {{"status":"RESOURCE_EXHAUSTED","error_code":429}}\n'
).encode()
LOGIN_STDOUT = _envelope("ERROR", error="authentication failed or timed out")
LOGIN_STDERR = (
    b"Authentication required. Please visit the URL to log in:\n"
    b"Waiting for authentication (timeout 60s)...\n"
    b"error: authentication failed or timed out\n"
)
OK_STDOUT = _envelope("SUCCESS", output_tokens=12)


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


def _target(tmp_path: Path) -> Path:
    target = tmp_path / "target"
    target.mkdir()
    return target.resolve()


def _account_home(tmp_path: Path, name: str, behaviour: str | None) -> Path:
    """An account HOME whose token text names how the fake agy behaves for it."""
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


def _install_pool(pool_env, behaviours: dict[str, str | None]) -> AgyAccountPoolManager:
    pool = AgyAccountPoolManager([
        AgyAccount(alias=name, home_dir=str(_account_home(pool_env.tmp_path, name, behaviour)))
        for name, behaviour in behaviours.items()
    ])
    pool_env.monkeypatch.setattr(
        "nexus.services.agy_account_pool.get_account_pool_manager", lambda: pool
    )
    return pool


def _fake_agy(pool_env, seen: list[str]):
    def fake_worker(request, on_process_group=None):
        behaviour = (Path(request.env["HOME"]) / TOKEN).read_text(encoding="utf-8")
        seen.append(behaviour)
        if behaviour == "quota":
            stdout, stderr, code = QUOTA_STDOUT, QUOTA_STDERR, 1
        elif behaviour == "login":
            stdout, stderr, code = LOGIN_STDOUT, LOGIN_STDERR, 1
        elif behaviour == "quota-after-work":
            stdout = _envelope("ERROR", output_tokens=40, error=QUOTA_TEXT)
            stderr, code = QUOTA_STDERR, 1
        elif behaviour == "crash":
            stdout, stderr, code = b"", b"segmentation fault", 1
        else:
            stdout, stderr, code = OK_STDOUT, b"", 0
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


def _invoke(pool_env, *, calls: int = 1, timeout: float = 120.0):
    adapter = AgyWorkerAdapter(
        use_installed_account_pool=True, canonical_root=_repo(pool_env.tmp_path)
    )
    return adapter.invoke(
        SimpleNamespace(task_id="agy-rotation", maximum_provider_calls=calls),
        SimpleNamespace(target_worktree=str(_target(pool_env.tmp_path))),
        prompt="bounded task",
        worker_role="implementation",
        timeout_seconds=timeout,
    )


def _hash(name: str) -> str:
    return AgyAccount(alias=name, home_dir="/").alias_hash


# ---------------------------------------------------------------------------
# rotation under a budget of one
# ---------------------------------------------------------------------------


def test_quota_account_rotates_to_a_healthy_one_under_budget_one(pool_env):
    _install_pool(pool_env, {"acc-quota": "quota", "acc-ok": "ok"})
    pool_env.monkeypatch.setenv("NEXUS_AGY_PREFERRED_ACCOUNTS", "acc-quota,acc-ok")
    seen: list[str] = []
    _fake_agy(pool_env, seen)
    before = time.time()

    receipt = _invoke(pool_env, calls=1)

    assert seen == ["quota", "ok"]
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert receipt.provider_calls == 1
    assert receipt.account_rotation_attempts == 1
    assert receipt.provider_attempt_count == 2
    assert receipt.account_alias_hash == _hash("acc-ok")
    marker = pool_env.leases / f"{_hash('acc-quota')}.family-unavailable.gemini.json"
    payload = json.loads(marker.read_text(encoding="utf-8"))
    # Cooldown until agy's reported reset (1 h), not the 5-minute default.
    assert payload["unavailable_until"] >= before + 3500


def test_every_quota_account_is_tried_once_then_pool_exhausted(pool_env):
    _install_pool(pool_env, {"a1": "quota", "a2": "quota", "a3": "quota"})
    seen: list[str] = []
    _fake_agy(pool_env, seen)

    receipt = _invoke(pool_env, calls=1)

    assert seen == ["quota", "quota", "quota"]
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == f"{AGY_POOL_EXHAUSTED}: earliest reset in 1h00m00s"
    assert receipt.provider_calls == 0
    assert receipt.account_rotation_attempts == 3
    assert receipt.stderr_tail is not None and "Resets in" in receipt.stderr_tail


def test_account_without_token_rotates_without_spawning(pool_env):
    _install_pool(pool_env, {"no-token": None, "acc-ok": "ok"})
    pool_env.monkeypatch.setenv("NEXUS_AGY_PREFERRED_ACCOUNTS", "no-token,acc-ok")
    seen: list[str] = []
    _fake_agy(pool_env, seen)

    receipt = _invoke(pool_env, calls=1)

    assert seen == ["ok"]
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert receipt.account_alias_hash == _hash("acc-ok")
    assert receipt.provider_calls == 1
    assert receipt.account_rotation_attempts == 1
    assert (pool_env.leases / f"{_hash('no-token')}.quarantine.json").is_file()


def test_login_prompt_account_rotates_and_is_retired(pool_env):
    _install_pool(pool_env, {"acc-login": "login", "acc-ok": "ok"})
    pool_env.monkeypatch.setenv("NEXUS_AGY_PREFERRED_ACCOUNTS", "acc-login,acc-ok")
    seen: list[str] = []
    _fake_agy(pool_env, seen)

    receipt = _invoke(pool_env, calls=1)

    assert seen == ["login", "ok"]
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert receipt.account_rotation_attempts == 1
    # Account-global failure: the in-memory manager cannot persist it, so the
    # coordinator quarantines the account durably.
    assert (pool_env.leases / f"{_hash('acc-login')}.quarantine.json").is_file()


def test_all_accounts_need_login_names_both_reasons(pool_env):
    _install_pool(pool_env, {"l1": "login", "l2": "login"})
    seen: list[str] = []
    _fake_agy(pool_env, seen)

    receipt = _invoke(pool_env, calls=1)

    assert seen == ["login", "login"]
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason is not None
    assert receipt.failure_reason.startswith(AGY_AUTHENTICATION_REQUIRED)
    assert AGY_POOL_EXHAUSTED in receipt.failure_reason


def test_quota_after_model_work_spends_the_budget(pool_env):
    _install_pool(pool_env, {"w1": "quota-after-work", "w2": "quota-after-work"})
    seen: list[str] = []
    _fake_agy(pool_env, seen)

    receipt = _invoke(pool_env, calls=1)

    assert seen == ["quota-after-work"]
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.provider_calls == 1
    assert receipt.account_rotation_attempts == 0


def test_non_rotatable_failure_does_not_rotate(pool_env):
    _install_pool(pool_env, {"c1": "crash", "c2": "crash"})
    seen: list[str] = []
    _fake_agy(pool_env, seen)

    receipt = _invoke(pool_env, calls=1)

    assert seen == ["crash"]
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason is not None
    assert receipt.failure_reason.startswith("non-eligible account failure")


def test_an_account_claimed_by_another_process_is_not_used(pool_env):
    _install_pool(pool_env, {"held": "ok", "free": "ok"})
    pool_env.monkeypatch.setenv("NEXUS_AGY_PREFERRED_ACCOUNTS", "held,free")
    pool_env.leases.mkdir(parents=True, exist_ok=True)
    lock = (pool_env.leases / f"{_hash('held')}.lock").open("a+")
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    seen: list[str] = []
    _fake_agy(pool_env, seen)
    try:
        receipt = _invoke(pool_env, calls=1)
    finally:
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        lock.close()

    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert receipt.account_alias_hash == _hash("free")
    # The claim is released afterwards: no durable receipt survives.
    assert not (pool_env.leases / f"{_hash('free')}.receipt.json").exists()


def test_claim_is_released_after_a_successful_run(pool_env):
    _install_pool(pool_env, {"only": "ok"})
    _fake_agy(pool_env, [])

    first = _invoke(pool_env, calls=1)
    assert first.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    lock = (pool_env.leases / f"{_hash('only')}.lock").open("a+")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        lock.close()
    assert not (pool_env.leases / f"{_hash('only')}.receipt.json").exists()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _result(stdout: bytes, stderr: bytes = b"") -> CliWorkerResult:
    return CliWorkerResult(
        status=CliWorkerStatus.COMPLETED,
        executable_identity="/bin/agy",
        argv=(),
        cwd="/",
        exit_code=1,
        stdout=stdout,
        stderr=stderr,
        wall_time_ms=1,
        process_group_id=None,
    )


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("Resets in 64h23m29s.", 64 * 3600 + 23 * 60 + 29),
        ("Resets in 5m", 300),
        ("resets in 1d2h", 86400 + 7200),
        ("no reset here", None),
    ],
)
def test_quota_reset_is_parsed(text, seconds):
    assert _agy_quota_reset_seconds(_result(b"", text.encode())) == seconds


def test_model_output_detection():
    assert _agy_attempt_had_model_output(_result(QUOTA_STDOUT)) is False
    assert _agy_attempt_had_model_output(_result(LOGIN_STDOUT)) is False
    assert _agy_attempt_had_model_output(_result(_envelope("ERROR", output_tokens=3))) is True
    # Unparseable output counts as model work (it spends the budget).
    assert _agy_attempt_had_model_output(_result(b"garbage")) is True


def test_pool_where_no_account_has_a_token_is_credentials_unavailable(pool_env):
    _install_pool(pool_env, {"n1": None, "n2": None})
    seen: list[str] = []
    _fake_agy(pool_env, seen)

    receipt = _invoke(pool_env, calls=1)

    assert seen == []
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == "agy_credentials_unavailable"
    assert receipt.provider_calls == 0
    assert receipt.account_rotation_attempts == 2
