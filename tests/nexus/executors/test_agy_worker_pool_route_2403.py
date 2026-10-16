"""#2403: the Gateway Agy worker route takes credentials from the account pool.

Live, every ``nexus_worker_candidate`` on the Agy route exited 1 after ~61 s:
without ``NEXUS_AGY_ACCOUNT_POOL_ENABLED`` the worker copied OAuth files the
Gateway HOME no longer has, so agy printed its interactive login prompt,
waited 60 s for a pasted code and gave up.  The receipt kept only hashes.

* the production registry's Agy adapter uses the installed pool manager (as
  ``nexus_model_probe`` does) without an env switch; ``=0`` still opts out;
* with no pool and no OAuth token it refuses before spawning agy;
* a login prompt is named ``agy_authentication_required``;
* receipts carry a bounded, redacted stdout/stderr tail.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.executors import worker_registry
from nexus.executors.cli_worker import CliWorkerResult, CliWorkerStatus
from nexus.executors.worker_contract import (
    OUTPUT_TAIL_MAX_BYTES,
    WorkerExecutionReceipt,
    WorkerOutcome,
    redacted_output_tail,
)
from nexus.executors.worker_registry import (
    AGY_AUTHENTICATION_REQUIRED,
    AGY_CREDENTIALS_UNAVAILABLE,
    AgyWorkerAdapter,
    WorkerRegistry,
)

# The stdout/stderr agy printed in the live failure (#2403), shortened.
LOGIN_STDOUT = (
    b'{"conversation_id":"","status":"ERROR","response":"",'
    b'"error":"authentication failed or timed out","duration_seconds":0}\n'
)
LOGIN_STDERR = (
    b"Authentication required. Please visit the URL to log in:\n"
    b"  https://accounts.google.com/o/oauth2/auth?access_type=offline&client_id=1071-x"
    b"&code_challenge=QfGpH9ZfUP_jo1Nc3SnQws8O8ructrvoIV8TqqNjYnc&state=cxfBBxdvF6oc71kw\n\n"
    b"Waiting for authentication (timeout 60s)...\n"
    b"Error: authentication timed out.\n"
    b"error: authentication failed or timed out\n"
)
OK_STDOUT = json.dumps({"status": "SUCCESS", "response": "edited"}).encode()


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


def _home(tmp_path: Path, monkeypatch, *, token: bool) -> Path:
    home = tmp_path / "home"
    cli = home / ".gemini" / "antigravity-cli"
    cli.mkdir(parents=True)
    if token:
        (cli / "antigravity-oauth-token").write_text("token", encoding="utf-8")
    (cli / "installation_id").write_text("install", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    return home.resolve()


def _ready(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.delenv("NEXUS_AGY_WORKER_MODEL", raising=False)
    monkeypatch.delenv("NEXUS_AGY_ACCOUNT_POOL_ENABLED", raising=False)
    monkeypatch.delenv("NEXUS_AGY_ACCOUNT_ALIASES", raising=False)
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")


def _result(request, *, stdout: bytes, stderr: bytes = b"", exit_code: int = 0):
    return CliWorkerResult(
        status=CliWorkerStatus.COMPLETED,
        executable_identity=request.executable,
        argv=request.argv,
        cwd=request.cwd,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        wall_time_ms=3,
        process_group_id=None,
        timed_out=False,
        descendants_swept=True,
    )


def _invoke(adapter: AgyWorkerAdapter, target: Path, *, calls: int = 1):
    return adapter.invoke(
        SimpleNamespace(task_id="agy-2403", maximum_provider_calls=calls),
        SimpleNamespace(target_worktree=str(target)),
        prompt="bounded task",
        worker_role="implementation",
    )


def _installed_manager(tmp_path: Path, monkeypatch, sentinel) -> None:
    manager = tmp_path / "pool" / "bin" / "agy-cli-manager"
    manager.parent.mkdir(parents=True)
    manager.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("NEXUS_AGY_ACCOUNT_POOL_MANAGER_PATH", str(manager))
    monkeypatch.setattr(
        "nexus.services.agy_account_pool.get_account_pool_manager", lambda: sentinel
    )


# ---------------------------------------------------------------------------
# pool selection
# ---------------------------------------------------------------------------


def test_default_registry_agy_adapter_uses_installed_pool_without_env(monkeypatch, tmp_path):
    _ready(monkeypatch)
    sentinel = object()
    _installed_manager(tmp_path, monkeypatch, sentinel)

    adapter = WorkerRegistry.default().adapter("agy")

    assert isinstance(adapter, AgyWorkerAdapter)
    assert adapter._get_account_pool() is sentinel


@pytest.mark.parametrize("value", ["0", "false", "no"])
def test_explicit_pool_opt_out_still_wins(monkeypatch, tmp_path, value):
    _ready(monkeypatch)
    _installed_manager(tmp_path, monkeypatch, object())
    monkeypatch.setenv("NEXUS_AGY_ACCOUNT_POOL_ENABLED", value)

    assert AgyWorkerAdapter(use_installed_account_pool=True)._get_account_pool() is None


def test_no_installed_manager_means_no_pool(monkeypatch, tmp_path):
    _ready(monkeypatch)
    monkeypatch.setenv("NEXUS_AGY_ACCOUNT_POOL_MANAGER_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(
        "nexus.services.agy_account_pool.get_account_pool_manager",
        lambda: pytest.fail("no manager is installed"),
    )

    assert AgyWorkerAdapter(use_installed_account_pool=True)._get_account_pool() is None


def test_bare_adapter_keeps_env_gated_pool(monkeypatch, tmp_path):
    _ready(monkeypatch)
    _installed_manager(tmp_path, monkeypatch, object())

    assert AgyWorkerAdapter()._get_account_pool() is None


def test_production_adapter_runs_with_a_pool_lease(monkeypatch, tmp_path):
    _ready(monkeypatch)
    _home(tmp_path, monkeypatch, token=False)
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool_home = tmp_path / "pool-home"
    cli = pool_home / ".gemini" / "antigravity-cli"
    cli.mkdir(parents=True)
    (cli / "antigravity-oauth-token").write_text("pool-token", encoding="utf-8")
    (cli / "installation_id").write_text("pool-install", encoding="utf-8")
    pool = AgyAccountPoolManager([AgyAccount(alias="acc1", home_dir=str(pool_home))])
    _installed_manager(tmp_path, monkeypatch, pool)
    seen = {}

    def fake_worker(request, on_process_group=None):
        token = (
            Path(request.env["HOME"]) / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
        )
        seen["token"] = token.read_text(encoding="utf-8")
        return _result(request, stdout=OK_STDOUT)

    monkeypatch.setattr(worker_registry, "run_cli_worker", fake_worker)
    adapter = AgyWorkerAdapter(use_installed_account_pool=True, canonical_root=_repo(tmp_path))
    receipt = _invoke(adapter, _target(tmp_path))

    assert seen["token"] == "pool-token"
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert receipt.account_alias_hash is not None
    assert receipt.stdout_tail == OK_STDOUT.decode()


# ---------------------------------------------------------------------------
# fail fast and name the login prompt
# ---------------------------------------------------------------------------


def test_no_pool_and_no_token_refuses_before_spawning(monkeypatch, tmp_path):
    _ready(monkeypatch)
    _home(tmp_path, monkeypatch, token=False)
    monkeypatch.setenv("NEXUS_AGY_ACCOUNT_POOL_MANAGER_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(
        worker_registry,
        "run_cli_worker",
        lambda request, on_process_group=None: pytest.fail("must not start agy"),
    )
    adapter = AgyWorkerAdapter(use_installed_account_pool=True, canonical_root=_repo(tmp_path))

    receipt = _invoke(adapter, _target(tmp_path))

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.provider_calls == 0
    assert receipt.failure_reason == AGY_CREDENTIALS_UNAVAILABLE


def test_login_prompt_without_pool_is_named_and_kept_redacted(monkeypatch, tmp_path):
    _ready(monkeypatch)
    _home(tmp_path, monkeypatch, token=True)
    monkeypatch.setattr(
        worker_registry,
        "run_cli_worker",
        lambda request, on_process_group=None: _result(
            request, stdout=LOGIN_STDOUT, stderr=LOGIN_STDERR, exit_code=1
        ),
    )
    receipt = _invoke(AgyWorkerAdapter(canonical_root=_repo(tmp_path)), _target(tmp_path))

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == AGY_AUTHENTICATION_REQUIRED
    assert receipt.stdout_tail == LOGIN_STDOUT.decode()
    assert receipt.stderr_tail is not None
    assert "Authentication required" in receipt.stderr_tail
    assert "QfGpH9ZfUP_jo1Nc3SnQws8O8ructrvoIV8TqqNjYnc" not in receipt.stderr_tail
    assert "cxfBBxdvF6oc71kw" not in receipt.stderr_tail


def test_login_prompt_with_pool_lease_is_named(monkeypatch, tmp_path):
    _ready(monkeypatch)
    _home(tmp_path, monkeypatch, token=True)
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1"))])
    monkeypatch.setattr(
        worker_registry,
        "run_cli_worker",
        lambda request, on_process_group=None: _result(
            request, stdout=LOGIN_STDOUT, stderr=LOGIN_STDERR, exit_code=1
        ),
    )
    adapter = AgyWorkerAdapter(account_pool=pool, canonical_root=_repo(tmp_path))
    receipt = _invoke(adapter, _target(tmp_path))

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == AGY_AUTHENTICATION_REQUIRED
    assert receipt.stderr_tail is not None and "Waiting for authentication" in receipt.stderr_tail


# ---------------------------------------------------------------------------
# redacted tail
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "secret",
    [
        "ya" + "29.a0AfH6SMBexampleexampleexample",
        "1/" + "/0gExampleRefreshToken123",
        "AI" + "zaSyExampleExampleExample1234",
        "ey" + "JhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl",
        "gh" + "p_abcdefghijklmnop1234567890",
        "sk" + "-exampleexampleexample1234",
        "AK" + "IA1234567890ABCDEF",
        "Q" * 48,
    ],
)
def test_output_tail_redacts_credential_shapes(secret):
    text = f'before {secret} after\n{{"access_token": "plainvalue"}}\n'.encode()

    tail = redacted_output_tail(text)

    assert tail is not None
    assert secret not in tail
    assert "plainvalue" not in tail
    assert tail.startswith("before ") and "after" in tail


def test_output_tail_keeps_hex_digests_and_bounds_size():
    digest = "7ef5ac64ad6e830550cfb17b7921ef565a67aba4ab53bd829de704a10397a0e8"
    assert redacted_output_tail(f"sha {digest}".encode()) == f"sha {digest}"

    tail = redacted_output_tail(b"line ok\n" * 2000)
    assert tail is not None
    assert len(tail.encode("utf-8")) <= OUTPUT_TAIL_MAX_BYTES
    assert tail.endswith("line ok\n")
    assert redacted_output_tail(None) is None
    assert redacted_output_tail(b"") == ""


def test_output_tail_redacts_before_cutting():
    secret = "ya" + "29." + "A" * 40
    # The cut lands inside the secret: the kept text starts mid-token.
    data = secret.encode() + b" " + b"x " * (OUTPUT_TAIL_MAX_BYTES // 2 - 5)
    assert len(data) - OUTPUT_TAIL_MAX_BYTES < len(secret)

    tail = redacted_output_tail(data)

    assert tail is not None
    assert len(tail.encode("utf-8")) == OUTPUT_TAIL_MAX_BYTES
    # Not a single byte of the secret survives, even the part after the cut.
    assert "A" not in tail.replace("REDACTED", "")


@pytest.mark.parametrize(
    "line",
    [
        "AWS_SECRET_ACCESS_KEY=abc/def+ghi",
        "GEMINI_API_KEY: plainvalue",
        "MY_SERVICE_TOKEN=plainvalue",
        "client_secret=plainvalue",
    ],
)
def test_output_tail_redacts_env_style_credentials(line):
    tail = redacted_output_tail(line.encode())

    assert tail is not None
    assert tail.endswith("<REDACTED>")
    assert line.split("=")[-1].split(": ")[-1] not in tail


def test_receipt_without_tails_still_loads():
    receipt = WorkerExecutionReceipt(
        provider="agy",
        task_id="t",
        target_worktree="/x",
        worker_status="COMPLETED",
        outcome="FAILED",
        exit_code=1,
        executable_identity="/bin/agy",
        argv=(),
        stdout_sha256="0",
        stderr_sha256="0",
        wall_time_ms=1,
        process_group_id=None,
        process_group_killed=False,
        timed_out=False,
        provider_calls=1,
        evidence_complete=False,
        commit_created=False,
        merge_performed=False,
        push_performed=False,
    )
    assert receipt.stdout_tail is None and receipt.stderr_tail is None


def test_pool_account_without_token_refuses_before_spawning(monkeypatch, tmp_path):
    _ready(monkeypatch)
    _home(tmp_path, monkeypatch, token=True)
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    empty_home = tmp_path / "pool-empty"
    cli = empty_home / ".gemini" / "antigravity-cli"
    cli.mkdir(parents=True)
    # Only the OAuth token is missing.
    (cli / "installation_id").write_text("pool-install", encoding="utf-8")
    pool = AgyAccountPoolManager([AgyAccount(alias="acc1", home_dir=str(empty_home))])
    _installed_manager(tmp_path, monkeypatch, pool)
    monkeypatch.setattr(
        worker_registry,
        "run_cli_worker",
        lambda request, on_process_group=None: pytest.fail("must not start agy"),
    )
    adapter = AgyWorkerAdapter(use_installed_account_pool=True, canonical_root=_repo(tmp_path))

    receipt = _invoke(adapter, _target(tmp_path))

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.provider_calls == 0
    assert receipt.failure_reason == AGY_CREDENTIALS_UNAVAILABLE


def test_login_prompt_stays_named_when_rotation_has_no_replacement(monkeypatch, tmp_path):
    _ready(monkeypatch)
    _home(tmp_path, monkeypatch, token=True)
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1"))])
    monkeypatch.setattr(pool, "report_failure", lambda lease, kind: None)
    monkeypatch.setattr(
        worker_registry,
        "run_cli_worker",
        lambda request, on_process_group=None: _result(
            request, stdout=LOGIN_STDOUT, stderr=LOGIN_STDERR, exit_code=1
        ),
    )
    adapter = AgyWorkerAdapter(account_pool=pool, canonical_root=_repo(tmp_path))

    receipt = _invoke(adapter, _target(tmp_path), calls=3)

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason is not None
    assert receipt.failure_reason.startswith(AGY_AUTHENTICATION_REQUIRED)
    assert "no replacement lease" in receipt.failure_reason
