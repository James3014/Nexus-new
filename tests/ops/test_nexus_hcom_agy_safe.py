"""Focused tests for the canonical hcom/Agy collaborative launcher."""

from __future__ import annotations

import fcntl
import importlib.machinery
import importlib.util
import json
import os
import signal
import stat
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts" / "ops" / "nexus-hcom-agy-safe"


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_launcher_uses_full_active_account_home_and_cleans_ephemeral_copy(tmp_path: Path) -> None:
    original_home = tmp_path / "owner-home"
    manager_root = original_home / ".nexus" / "agy-account-pool" / "runtime"
    profile = manager_root / "accounts" / "google-active"
    (profile / ".gemini").mkdir(parents=True)
    (profile / "Library" / "Keychains").mkdir(parents=True)
    (profile / ".gemini" / "auth.json").write_text("active-auth", encoding="utf-8")
    (profile / "Library" / "Keychains" / "agy.keychain-db").write_text(
        "keychain-sentinel", encoding="utf-8"
    )
    (profile / "profile-marker.txt").write_text("active-profile", encoding="utf-8")

    # Negative identity control: the owner HOME contains a conflicting .gemini
    # identity. The launcher must still copy the canonical account snapshot HOME.
    (original_home / ".gemini").mkdir(parents=True, exist_ok=True)
    (original_home / ".gemini" / "auth.json").write_text("stale-owner-auth", encoding="utf-8")

    stale = manager_root.parent / "live-home"
    (stale / ".gemini").mkdir(parents=True)
    (stale / "profile-marker.txt").write_text("stale-live-home", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    manager = bin_dir / "agy-cli-manager"
    _write_executable(
        manager,
        """#!/usr/bin/env python3
import json, sys
if "ensure-active" in sys.argv:
    print(json.dumps({"active": "google-active"}))
elif "current" in sys.argv:
    print("google-active")
else:
    raise SystemExit(2)
""",
    )

    security = bin_dir / "security"
    _write_executable(security, "#!/bin/sh\nexit 0\n")

    record_path = tmp_path / "record.json"
    config_log = tmp_path / "config.log"
    hcom = bin_dir / "hcom"
    _write_executable(
        hcom,
        """#!/usr/bin/env python3
import json, os, pathlib, sys
if len(sys.argv) >= 4 and sys.argv[1] == "config":
    with open(os.environ["HCOM_TEST_CONFIG_LOG"], "a", encoding="utf-8") as fh:
        fh.write(f"{sys.argv[2]}={sys.argv[3]}\\n")
    raise SystemExit(0)
if len(sys.argv) >= 2 and sys.argv[1] == "agy":
    home = pathlib.Path(os.environ["HOME"])
    payload = {
        "args": sys.argv[2:],
        "home": str(home),
        "gemini_home": os.environ.get("GEMINI_CLI_HOME"),
        "hcom_dir": os.environ.get("HCOM_DIR"),
        "profile_marker": (home / "profile-marker.txt").read_text(),
        "auth_present": (home / ".gemini" / "auth.json").is_file(),
        "auth_value": (home / ".gemini" / "auth.json").read_text(),
        "keychain_present": (home / "Library" / "Keychains" / "agy.keychain-db").is_file(),
        "lease_fd_open": bool(os.fstat(int(os.environ["NEXUS_HCOM_AGY_LEASE_FD"]))),
        "stale_marker": (home / "stale-marker.txt").exists(),
        "sensitive_present": any(
            key in os.environ
            for key in (
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "GOOGLE_GENAI_API_KEY",
                "GH_TOKEN",
                "GITHUB_TOKEN",
                "GH_ENTERPRISE_TOKEN",
                "GITHUB_ENTERPRISE_TOKEN",
                "GITHUB_PAT",
                "GITHUB_ACTIONS_TOKEN",
            )
        ),
    }
    pathlib.Path(os.environ["HCOM_TEST_RECORD"]).write_text(json.dumps(payload))
    raise SystemExit(0)
raise SystemExit(2)
""",
    )

    hcom_dir = original_home / ".hcom"
    hcom_dir.mkdir()
    (hcom_dir / "env").write_text(
        "GEMINI_MODEL=gemini-safe-model\nGITHUB_TOKEN=\n",
        encoding="utf-8",
    )

    state_root = original_home / ".local" / "state" / "hcom-agy-safe"
    env = os.environ.copy()
    env.update({
        "HOME": str(original_home),
        "PATH": f"{bin_dir}{os.pathsep}{env.get('PATH', '')}",
        "NEXUS_AGY_MANAGER": str(manager),
        "NEXUS_AGY_MANAGER_ROOT": str(manager_root),
        "NEXUS_HCOM_AGY_STATE_ROOT": str(state_root),
        "NEXUS_HCOM_BIN": str(hcom),
        "HCOM_TEST_RECORD": str(record_path),
        "HCOM_TEST_CONFIG_LOG": str(config_log),
        "GEMINI_API_KEY": "must-not-leak",
        "GOOGLE_API_KEY": "must-not-leak",
        "GOOGLE_GENAI_API_KEY": "must-not-leak",
        "GH_TOKEN": "must-not-leak",
        "GITHUB_TOKEN": "must-not-leak",
        "GH_ENTERPRISE_TOKEN": "must-not-leak",
        "GITHUB_ENTERPRISE_TOKEN": "must-not-leak",
        "GITHUB_PAT": "must-not-leak",
        "GITHUB_ACTIONS_TOKEN": "must-not-leak",
        "NEXUS_HCOM_AGY_LEASE_ACCOUNT": "google-active",
        "NEXUS_HCOM_AGY_PROFILE_HOME": str(profile),
        "NEXUS_HCOM_AGY_LEASE_ID_HASH": "lease-hash",
        "NEXUS_HCOM_AGY_ACCOUNT_ALIAS_HASH": "alias-hash",
    })

    lease_path = tmp_path / "lease.lock"
    status_read_fd, status_write_fd = os.pipe()
    env["NEXUS_HCOM_AGY_STATUS_FD"] = str(status_write_fd)
    try:
        with lease_path.open("a+") as lease_fh:
            lease_fd = lease_fh.fileno()
            env["NEXUS_HCOM_AGY_LEASE_FD"] = str(lease_fd)
            proc = subprocess.run(
                [sys.executable, str(LAUNCHER), "--model", "gpt-oss-120b-medium"],
                env=env,
                pass_fds=(lease_fd, status_write_fd),
                capture_output=True,
                text=True,
                check=False,
            )
    finally:
        os.close(status_write_fd)
    with os.fdopen(status_read_fd, "r", encoding="utf-8") as status_stream:
        status_records = [json.loads(line) for line in status_stream if line.strip()]

    assert proc.returncode == 0, proc.stderr
    assert [record["event"] for record in status_records] == [
        "provider_started",
        "provider_terminal",
    ]
    assert status_records[0]["pid"] == status_records[1]["pid"]
    assert status_records[1]["exit_code"] == 0
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert payload["args"] == ["--terminal", "here", "--model", "gpt-oss-120b-medium"]
    assert payload["profile_marker"] == "active-profile"
    assert payload["auth_present"] is True
    assert payload["auth_value"] == "active-auth"
    assert payload["keychain_present"] is True
    assert payload["lease_fd_open"] is True
    assert payload["sensitive_present"] is False
    assert payload["gemini_home"] == payload["home"]
    assert payload["hcom_dir"] == str((original_home / ".hcom").resolve())
    assert Path(payload["home"]).parent == state_root.resolve()
    assert not Path(payload["home"]).exists()
    assert list(state_root.glob("session.*")) == []
    assert stat.S_IMODE(state_root.stat().st_mode) == 0o700

    config_lines = config_log.read_text(encoding="utf-8").splitlines()
    assert config_lines == [
        "auto_approve=0",
        "auto_trust_workspace=0",
        "relay_enabled=0",
    ]


def test_launcher_rejects_headless_before_creating_ephemeral_home(
    tmp_path: Path,
) -> None:
    for forwarded_args in (
        ["--headless"],
        ["--terminal", "iterm"],
        ["--terminal=iterm"],
        ["--device", "other-mac"],
        ["--device=other-mac"],
    ):
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        proc = subprocess.run(
            [sys.executable, str(LAUNCHER), *forwarded_args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 2
        assert "DETACHED_LAUNCH_DISABLED:" in proc.stderr
        assert not (tmp_path / ".local" / "state" / "hcom-agy-safe").exists()


def test_launcher_rejects_sensitive_hcom_passthrough_before_account_copy(tmp_path: Path) -> None:
    original_home = tmp_path / "owner-home"
    hcom_dir = original_home / ".hcom"
    hcom_dir.mkdir(parents=True)
    (hcom_dir / "env").write_text(
        "GEMINI_MODEL=allowed\nGITHUB_TOKEN=must-not-reenter\n",
        encoding="utf-8",
    )

    manager = tmp_path / "agy-cli-manager"
    _write_executable(manager, "#!/bin/sh\nexit 99\n")
    hcom = tmp_path / "hcom"
    _write_executable(hcom, "#!/bin/sh\nexit 99\n")

    env = os.environ.copy()
    env.update({
        "HOME": str(original_home),
        "NEXUS_AGY_MANAGER": str(manager),
        "NEXUS_AGY_MANAGER_ROOT": str(tmp_path / "runtime"),
        "NEXUS_HCOM_BIN": str(hcom),
    })
    proc = subprocess.run(
        [sys.executable, str(LAUNCHER)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 2
    assert "HCOM_ENV_FORBIDDEN_KEY:GITHUB_TOKEN" in proc.stderr
    assert not (original_home / ".local" / "state" / "hcom-agy-safe").exists()


def test_unleased_launcher_delegates_to_canonical_dispatcher(tmp_path: Path) -> None:
    original_home = tmp_path / "owner-home"
    original_home.mkdir()
    dispatcher_record = tmp_path / "dispatcher.json"
    dispatcher = tmp_path / "nexus-agy-dispatch"
    _write_executable(
        dispatcher,
        """#!/usr/bin/env python3
import json, os, pathlib, sys
pathlib.Path(os.environ["DISPATCHER_RECORD"]).write_text(json.dumps(sys.argv[1:]))
raise SystemExit(0)
""",
    )
    env = os.environ.copy()
    env.update({
        "HOME": str(original_home),
        "NEXUS_AGY_DISPATCH_BIN": str(dispatcher),
        "DISPATCHER_RECORD": str(dispatcher_record),
    })
    proc = subprocess.run(
        [sys.executable, str(LAUNCHER), "--model", "gemini-3.8-flash-high"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    argv = json.loads(dispatcher_record.read_text(encoding="utf-8"))
    assert argv[:3] == ["--hcom-collab", "--cwd", str(tmp_path.resolve())]
    assert "--hcom-args-json" in argv
    forwarded = json.loads(argv[argv.index("--hcom-args-json") + 1])
    assert forwarded == ["--model", "gemini-3.8-flash-high"]
    assert argv[-2:] == ["--model", "gemini-3.8-flash-high"]


def test_stale_lock_free_receipt_fails_closed(tmp_path: Path) -> None:
    from nexus.services.agy_account_pool import (
        AgyAccount,
        AgyAccountPoolBusyError,
        AgyAccountPoolManager,
        CrossProcessLeaseCoordinator,
    )

    home = tmp_path / "account-home"
    home.mkdir()
    manager = AgyAccountPoolManager(
        accounts=[AgyAccount(alias="google-a", home_dir=str(home))],
        use_real_manager=False,
    )
    leases = tmp_path / "leases"
    coordinator = CrossProcessLeaseCoordinator(
        manager=manager,
        allocator_lock_path=tmp_path / "allocator.lock",
        leases_dir=leases,
        default_wait_timeout=0,
    )
    alias_hash = manager._accounts[0].alias_hash
    leases.mkdir()
    receipt = leases / f"{alias_hash}.receipt.json"
    receipt.write_text('{"unresolved": true}\n', encoding="utf-8")

    try:
        coordinator.acquire_claim("consumer-new", wait_timeout=0)
    except AgyAccountPoolBusyError:
        pass
    else:
        raise AssertionError("stale receipt must block account reuse")
    assert receipt.read_text(encoding="utf-8") == '{"unresolved": true}\n'


def test_abandoned_parent_reference_keeps_inherited_flock_and_receipt(tmp_path: Path) -> None:
    from nexus.services.agy_account_pool import (
        AgyAccount,
        AgyAccountPoolManager,
        CrossProcessLeaseCoordinator,
    )

    home = tmp_path / "account-home"
    home.mkdir()
    manager = AgyAccountPoolManager(
        accounts=[AgyAccount(alias="google-a", home_dir=str(home))],
        use_real_manager=False,
    )
    coordinator = CrossProcessLeaseCoordinator(
        manager=manager,
        allocator_lock_path=tmp_path / "allocator.lock",
        leases_dir=tmp_path / "leases",
    )
    claim = coordinator.acquire_claim("consumer-a")
    inherited_fd = os.dup(claim.lock_file_obj.fileno())
    receipt = claim.receipt_path
    try:
        claim.abandon_parent_reference()
        assert receipt.exists()
        contender = claim.lock_path.open("a+")
        try:
            try:
                fcntl.flock(contender.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                raise AssertionError("inherited descriptor must keep the account flock held")
        finally:
            contender.close()
    finally:
        os.close(inherited_fd)
    assert receipt.exists()


def _load_dispatch_module(monkeypatch) -> types.ModuleType:
    monkeypatch.setenv("NEXUS_AGY_SNAPSHOT", str(ROOT))
    path = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"
    loader = importlib.machinery.SourceFileLoader("nexus_agy_dispatch_phase_a_test", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class _FakeClaim:
    def __init__(self, profile: Path, lock_fh, alias_hash="alias-hash", internal_id=None) -> None:
        self.internal_id = internal_id or profile.name
        self.account_alias_hash = alias_hash
        self.lease_id_hash = "lease-hash"
        self.lease = types.SimpleNamespace(execution_env={"HOME": str(profile)})
        self.lock_file_obj = lock_fh
        self.lock_path = profile.parent.parent / "leases" / f"{alias_hash}.lock"
        self.receipt_path = profile.parent.parent / "leases" / f"{alias_hash}.receipt.json"
        self.released = False
        self.abandoned = False

    def release(self) -> None:
        self.released = True
        if self.receipt_path.exists():
            try:
                self.receipt_path.unlink()
            except OSError:
                pass

    def abandon_parent_reference(self) -> None:
        self.abandoned = True


class _FakeCoordinator:
    def __init__(self, claim: _FakeClaim) -> None:
        self.claim = claim
        self.calls = []

    def acquire_claim(self, **kwargs):
        self.calls.append(kwargs)
        return self.claim


def test_dispatcher_binds_exact_claim_to_hcom_child_and_releases_cleanly(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_dispatch_module(monkeypatch)
    manager_root = tmp_path / "runtime"
    profile = manager_root / "accounts" / "google-a"
    profile.mkdir(parents=True)
    module.MANAGER_ROOT = manager_root
    monkeypatch.setattr(
        module,
        "_apply_dynamic_availability",
        lambda _model: ({}, {"family": "other"}),
    )

    launcher = tmp_path / "hcom-agy-safe"
    launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    launcher.chmod(0o755)
    lock_fh = (tmp_path / "lease.lock").open("a+")
    claim = _FakeClaim(profile, lock_fh)
    coordinator = _FakeCoordinator(claim)
    captured = {}

    class Child:
        def __init__(self):
            self.pid = 42424

        def wait(self):
            return 0

        def poll(self):
            return 0

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        status_fd = int(kwargs["env"]["NEXUS_HCOM_AGY_STATUS_FD"])
        base = {
            "schema": "nexus.hcom_collab_status.v1",
            "account_alias_hash": "alias-hash",
            "lease_id_hash": "lease-hash",
            "pid": 51515,
        }
        os.write(
            status_fd,
            (json.dumps({**base, "event": "provider_started"}) + "\n").encode(),
        )
        os.write(
            status_fd,
            (json.dumps({**base, "event": "provider_terminal", "exit_code": 0}) + "\n").encode(),
        )
        return Child()

    try:
        code = module.dispatch_hcom_collab(
            cwd=str(tmp_path),
            hcom_args=["--model", "gemini-3.8-flash-high"],
            model="gemini-3.8-flash-high",
            coordinator=coordinator,
            popen_factory=fake_popen,
            launcher_path=launcher,
        )
    finally:
        lock_fh.close()

    assert code == 0
    assert claim.released is True
    assert claim.abandoned is False
    assert captured["env"]["NEXUS_HCOM_AGY_LEASE_ACCOUNT"] == "google-a"
    assert captured["env"]["NEXUS_HCOM_AGY_PROFILE_HOME"] == str(profile.resolve())
    assert captured["env"]["NEXUS_HCOM_AGY_LEASE_ID_HASH"] == "lease-hash"
    assert captured["pass_fds"]


def test_dispatcher_abandons_parent_reference_when_live_child_terminality_is_unknown(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_dispatch_module(monkeypatch)
    manager_root = tmp_path / "runtime"
    profile = manager_root / "accounts" / "google-a"
    profile.mkdir(parents=True)
    module.MANAGER_ROOT = manager_root
    monkeypatch.setattr(
        module,
        "_apply_dynamic_availability",
        lambda _model: ({}, {"family": "other"}),
    )

    launcher = tmp_path / "hcom-agy-safe"
    launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    launcher.chmod(0o755)
    lock_fh = (tmp_path / "lease.lock").open("a+")
    claim = _FakeClaim(profile, lock_fh)
    coordinator = _FakeCoordinator(claim)

    class Child:
        def __init__(self):
            self.pid = 42425

        def wait(self):
            raise KeyboardInterrupt

        def poll(self):
            return None

    try:
        try:
            module.dispatch_hcom_collab(
                cwd=str(tmp_path),
                hcom_args=[],
                model=None,
                coordinator=coordinator,
                popen_factory=lambda *_args, **_kwargs: Child(),
                launcher_path=launcher,
            )
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("expected simulated parent interruption")
    finally:
        lock_fh.close()

    assert claim.abandoned is True
    assert claim.released is False


def test_launcher_crash_with_surviving_provider_preserves_receipt_and_blocks_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_dispatch_module(monkeypatch)
    from nexus.services.agy_account_pool import (
        AgyAccount,
        AgyAccountPoolBusyError,
        AgyAccountPoolManager,
        CrossProcessLeaseCoordinator,
    )

    manager_root = tmp_path / "runtime"
    profile = manager_root / "accounts" / "google-a"
    (profile / ".gemini").mkdir(parents=True)
    module.MANAGER_ROOT = manager_root
    leases = tmp_path / "leases"
    module.LEASES_DIR = leases
    monkeypatch.setattr(
        module,
        "_apply_dynamic_availability",
        lambda _model: ({}, {"family": "other"}),
    )
    manager = AgyAccountPoolManager(
        accounts=[AgyAccount(alias="google-a", home_dir=str(profile))],
        use_real_manager=False,
    )
    coordinator = CrossProcessLeaseCoordinator(
        manager=manager,
        allocator_lock_path=tmp_path / "allocator.lock",
        leases_dir=leases,
        default_wait_timeout=0.1,
    )

    pidfile = tmp_path / "provider.pid"
    launcher = tmp_path / "crashing-launcher.py"
    launcher.write_text(
        """#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys
lease_fd = int(os.environ["NEXUS_HCOM_AGY_LEASE_FD"])
status_fd = int(os.environ["NEXUS_HCOM_AGY_STATUS_FD"])
provider = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(60)"],
    pass_fds=(lease_fd,),
)
pathlib.Path(os.environ["TEST_PROVIDER_PIDFILE"]).write_text(str(provider.pid))
payload = {
    "schema": "nexus.hcom_collab_status.v1",
    "event": "provider_started",
    "account_alias_hash": os.environ["NEXUS_HCOM_AGY_ACCOUNT_ALIAS_HASH"],
    "lease_id_hash": os.environ["NEXUS_HCOM_AGY_LEASE_ID_HASH"],
    "pid": provider.pid,
}
os.write(status_fd, (json.dumps(payload) + "\\n").encode())
raise SystemExit(42)
""",
        encoding="utf-8",
    )
    launcher.chmod(0o755)
    monkeypatch.setenv("TEST_PROVIDER_PIDFILE", str(pidfile))
    events: list[dict[str, Any]] = []

    with pytest.raises(RuntimeError, match="HCOM_COLLAB_TERMINALITY_UNPROVEN"):
        module.dispatch_hcom_collab(
            cwd=str(tmp_path),
            hcom_args=[],
            model=None,
            pool_wait_timeout=0.1,
            coordinator=coordinator,
            launcher_path=launcher,
            operation_hook=events.append,
        )

    provider_pid = int(pidfile.read_text(encoding="utf-8"))
    try:
        os.kill(provider_pid, 0)
        assert any(event.get("provider_pid") == provider_pid for event in events)
        receipt_files = list(leases.glob("*.receipt.json"))
        assert len(receipt_files) == 1
        with pytest.raises(AgyAccountPoolBusyError):
            coordinator.acquire_claim(
                "dispatcher-after-launcher-crash",
                wait_timeout=0.1,
            )
    finally:
        try:
            os.kill(provider_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def test_reconcile_preserves_collab_receipt_when_provider_identity_was_never_observed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_dispatch_module(monkeypatch)
    operation_root = tmp_path / "operations"
    leases = tmp_path / "leases"
    leases.mkdir()
    module.LEASES_DIR = leases
    journal = module.AgyOperationJournal(operation_root)
    operation_id = module.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=module.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model=None,
        effort=None,
        prompt_sha256="status-marker-race",
        runtime_revision="test",
        initial_fields={
            "mode": "hcom_collab",
            "account_alias_hash": "alias-a",
            "lease_id_hash": "lease-a",
        },
    )
    journal.update(operation_id, pid=999999)
    journal.mark_terminal(
        operation_id,
        status="OUTCOME_UNKNOWN",
        exit_code=None,
        failure_kind="HCOM_COLLAB_PARENT_ABORT:RuntimeError",
        cwd=str(tmp_path),
        reconciliation={
            "result": "HCOM_COLLAB_TERMINALITY_UNPROVEN",
            "retry_permitted": False,
        },
    )
    receipt = leases / "alias-a.receipt.json"
    receipt.write_text(
        json.dumps({
            "account_alias_hash": "alias-a",
            "lease_id_hash": "lease-a",
            "pid": 999999,
        }),
        encoding="utf-8",
    )
    (leases / "alias-a.lock").touch()
    monkeypatch.setattr(module._agy_operation_journal, "_process_alive", lambda _pid: False)
    monkeypatch.setattr(
        module._agy_operation_journal,
        "_process_group_alive",
        lambda _pgid: False,
    )

    record = module._reconcile_operation(journal, operation_id)
    assert record["phase"] == "RECONCILE_REQUIRED"
    assert record["reconciliation"]["result"] == "HCOM_COLLAB_PROVIDER_IDENTITY_UNPROVEN"
    assert (
        record["reconciliation"]["lease_cleanup"]["result"]
        == "COLLAB_PROVIDER_IDENTITY_UNPROVEN_PRESERVED"
    )
    assert record["reconciliation"]["retry_permitted"] is False
    assert receipt.exists()


def test_dispatcher_pool_busy_returns_canonical_75_without_launch(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_dispatch_module(monkeypatch)
    monkeypatch.setattr(
        module,
        "_apply_dynamic_availability",
        lambda _model: ({}, {"family": "other"}),
    )

    class BusyCoordinator:
        def acquire_claim(self, **_kwargs):
            raise module.AgyAccountPoolBusyError("busy")

    code = module.dispatch_hcom_collab(
        cwd=str(tmp_path),
        hcom_args=[],
        model=None,
        coordinator=BusyCoordinator(),
        popen_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("child must not launch")
        ),
        launcher_path=tmp_path / "unused-launcher",
    )
    assert code == 75


def test_foreground_collaborative_operation_journals_clean_completion(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_dispatch_module(monkeypatch)
    operation_root = tmp_path / "operations"

    def fake_dispatch(**kwargs):
        hook = kwargs["operation_hook"]
        hook({
            "phase": "ACCOUNT_LEASED",
            "attempts": 1,
            "rotations": 0,
            "account_alias_hash": "alias-hash",
            "lease_id_hash": "lease-hash",
        })
        hook({
            "phase": "EXECUTING",
            "attempts": 1,
            "rotations": 0,
            "account_alias_hash": "alias-hash",
            "lease_id_hash": "lease-hash",
            "provider_pid": 5555,
        })
        return 0

    monkeypatch.setattr(module, "dispatch_hcom_collab", fake_dispatch)
    code = module._run_foreground_hcom_operation(
        cwd=str(tmp_path),
        hcom_args=["--model", "gemini-3.8-flash-high"],
        model="gemini-3.8-flash-high",
        pool_wait_timeout=1,
        operation_root=operation_root,
    )
    assert code == 0
    operation_ids = [path.name for path in (operation_root / "operations").iterdir()]
    assert len(operation_ids) == 1
    record = module.AgyOperationJournal(operation_root).read(operation_ids[0])
    assert record["status"] == "COMPLETED"
    assert record["phase"] == "TERMINAL"
    assert record["account_alias_hash"] == "alias-hash"
    assert record["lease_id_hash"] == "lease-hash"
    assert record["provider_pid"] == 5555


def test_foreground_collaborative_operation_marks_preprovider_abort_failed(
    tmp_path: Path, monkeypatch
) -> None:
    module = _load_dispatch_module(monkeypatch)
    operation_root = tmp_path / "operations"

    def fail_before_provider(**_kwargs):
        raise RuntimeError("pre-provider")

    monkeypatch.setattr(module, "dispatch_hcom_collab", fail_before_provider)
    try:
        module._run_foreground_hcom_operation(
            cwd=str(tmp_path),
            hcom_args=[],
            model=None,
            pool_wait_timeout=1,
            operation_root=operation_root,
        )
    except RuntimeError as exc:
        assert str(exc) == "pre-provider"
    else:
        raise AssertionError("expected pre-provider failure")

    operation_ids = [path.name for path in (operation_root / "operations").iterdir()]
    assert len(operation_ids) == 1
    record = module.AgyOperationJournal(operation_root).read(operation_ids[0])
    assert record["status"] == "FAILED"
    assert record["reconciliation"]["result"] == "HCOM_COLLAB_ABORT_BEFORE_PROVIDER"
    assert record["reconciliation"]["retry_permitted"] is False


def test_foreground_collaborative_launching_gap_is_outcome_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_dispatch_module(monkeypatch)
    operation_root = tmp_path / "operations"

    def ambiguous_before_provider_identity(**kwargs: Any) -> int:
        kwargs["operation_hook"]({
            "phase": "LAUNCHING",
            "attempts": 1,
            "rotations": 0,
            "account_alias_hash": "alias-a",
            "lease_id_hash": "lease-a",
            "failure_kind": "HCOM_COLLAB_TERMINALITY_UNPROVEN",
        })
        raise RuntimeError("HCOM_COLLAB_TERMINALITY_UNPROVEN")

    monkeypatch.setattr(module, "dispatch_hcom_collab", ambiguous_before_provider_identity)
    with pytest.raises(RuntimeError, match="HCOM_COLLAB_TERMINALITY_UNPROVEN"):
        module._run_foreground_hcom_operation(
            cwd=str(tmp_path),
            hcom_args=[],
            model=None,
            pool_wait_timeout=1,
            operation_root=operation_root,
        )

    operation_ids = [path.name for path in (operation_root / "operations").iterdir()]
    assert len(operation_ids) == 1
    record = module.AgyOperationJournal(operation_root).read(operation_ids[0])
    assert record["status"] == "OUTCOME_UNKNOWN"
    assert record["reconciliation"]["result"] == "HCOM_COLLAB_TERMINALITY_UNPROVEN"
    assert record["reconciliation"]["retry_permitted"] is False


def test_collaborative_and_dispatcher_bidirectional_mutual_exclusion(tmp_path: Path) -> None:
    """Prove collaborative A holding account A blocks dispatcher from A, and vice-versa."""
    from nexus.services.agy_account_pool import (
        AgyAccount,
        AgyAccountPoolBusyError,
        AgyAccountPoolManager,
        CrossProcessLeaseCoordinator,
    )

    home_a = tmp_path / "account-a"
    home_a.mkdir()
    manager = AgyAccountPoolManager(
        accounts=[AgyAccount(alias="google-a", home_dir=str(home_a))],
        use_real_manager=False,
    )
    leases = tmp_path / "leases"
    coordinator = CrossProcessLeaseCoordinator(
        manager=manager,
        allocator_lock_path=tmp_path / "allocator.lock",
        leases_dir=leases,
        default_wait_timeout=0.1,
    )

    # Leg 1: collaborative holds account A -> dispatcher cannot claim A
    collab_claim = coordinator.acquire_claim("hcom_collab:1234:abc", wait_timeout=0.1)
    assert collab_claim.internal_id == "google-a"
    try:
        coordinator.acquire_claim("dispatcher-consumer", wait_timeout=0.1)
    except AgyAccountPoolBusyError:
        pass
    else:
        raise AssertionError("dispatcher must be blocked when collaborative holds account A")
    collab_claim.release()

    # Leg 2: dispatcher holds account A -> collaborative cannot claim A
    dispatch_claim = coordinator.acquire_claim("dispatcher-consumer", wait_timeout=0.1)
    assert dispatch_claim.internal_id == "google-a"
    try:
        coordinator.acquire_claim("hcom_collab:5678:def", wait_timeout=0.1)
    except AgyAccountPoolBusyError:
        pass
    else:
        raise AssertionError("collaborative must be blocked when dispatcher holds account A")
    dispatch_claim.release()


def test_collaborative_and_dispatcher_distinct_account_parallelism(tmp_path: Path) -> None:
    """Prove collaborative holding account A permits dispatcher to select eligible B."""
    from nexus.services.agy_account_pool import (
        AgyAccount,
        AgyAccountPoolManager,
        CrossProcessLeaseCoordinator,
    )

    home_a = tmp_path / "account-a"
    home_a.mkdir()
    home_b = tmp_path / "account-b"
    home_b.mkdir()
    manager = AgyAccountPoolManager(
        accounts=[
            AgyAccount(alias="google-a", home_dir=str(home_a)),
            AgyAccount(alias="google-b", home_dir=str(home_b)),
        ],
        use_real_manager=False,
    )
    leases = tmp_path / "leases"
    coordinator = CrossProcessLeaseCoordinator(
        manager=manager,
        allocator_lock_path=tmp_path / "allocator.lock",
        leases_dir=leases,
        default_wait_timeout=0.5,
    )

    # Collaborative acquires account A
    collab_claim = coordinator.acquire_claim("hcom_collab:1234:abc", wait_timeout=0.5)
    assert collab_claim.internal_id in {"google-a", "google-b"}
    held_id = collab_claim.internal_id
    expected_other = "google-b" if held_id == "google-a" else "google-a"

    # Dispatcher acquires parallel claim -> must receive distinct eligible account B
    dispatch_claim = coordinator.acquire_claim("dispatcher-consumer", wait_timeout=0.5)
    assert dispatch_claim.internal_id == expected_other
    assert dispatch_claim.internal_id != collab_claim.internal_id

    # Clean release of both
    dispatch_claim.release()
    collab_claim.release()


def test_hcom_registry_disappearance_with_surviving_agy_process_requires_reconcile(
    tmp_path: Path, monkeypatch
) -> None:
    """hcom list == [] does NOT prove Agy absence.

    When metadata is reset/lost while provider process survives, reconciliation
    must return RECONCILE_REQUIRED, not free/absent, and must preserve the lease.
    """
    module = _load_dispatch_module(monkeypatch)
    op_root = tmp_path / "operations"
    journal = module.AgyOperationJournal(op_root)
    op_id = module.new_operation_id()
    journal.create(
        operation_id=op_id,
        attempt_id=module.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-3.8-flash-high",
        effort=None,
        prompt_sha256="dummy",
        runtime_revision="rev1",
        initial_fields={
            "mode": "hcom_collab",
            "account_alias_hash": "alias-a",
            "lease_id_hash": "lease-a",
        },
    )
    parent_pid = 999999
    surviving_pid = 888888
    journal.mark_started(op_id, pid=parent_pid)

    # Create dummy leases dir and receipt for account alias-a
    leases_dir = tmp_path / "leases"
    leases_dir.mkdir(parents=True)
    module.LEASES_DIR = leases_dir
    receipt_file = leases_dir / "alias-a.receipt.json"
    receipt_file.write_text(
        json.dumps({
            "account_alias_hash": "alias-a",
            "lease_id_hash": "lease-a",
            "pid": parent_pid,
        }),
        encoding="utf-8",
    )
    lock_file = leases_dir / "alias-a.lock"
    lock_file.touch()

    # Simulate surviving child process while parent is dead
    journal.update(op_id, provider_pid=surviving_pid, phase="EXECUTING")

    # Simulate hcom registry loss: hcom list returns empty []
    # Even with hcom list == [], reconcile MUST NOT declare FREE
    monkeypatch.setattr(
        module._agy_operation_journal,
        "_process_alive",
        lambda p: p == surviving_pid,
    )
    monkeypatch.setattr(
        module._agy_operation_journal,
        "_stop_operation_processes",
        lambda *a, **k: (True, True, False),
    )

    # Reconcile operation
    rec = module._reconcile_operation(journal, op_id)
    assert rec["phase"] == "RECONCILE_REQUIRED"
    assert rec["reconciliation"]["provider_alive_after"] is True
    assert rec["reconciliation"]["retry_permitted"] is False
    assert rec["reconciliation"].get("lease_cleanup", {}).get("result") == "NOT_SAFE_TO_CLEAN"
    # Lease receipt must be preserved!
    assert receipt_file.exists()


def test_foreground_collaborative_operation_journals_failure_on_nonzero_child_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When child exits non-zero, journal records FAILED and lease receipt is cleanly released."""
    module = _load_dispatch_module(monkeypatch)
    leases = tmp_path / "leases"
    home_a = tmp_path / "accounts" / "google-a"
    home_a.mkdir(parents=True)
    (home_a / ".gemini").mkdir()

    class FakeClaim:
        internal_id = "google-a"
        account_alias_hash = "alias-a"
        lease_id_hash = "lease-a"
        released = False

        def __init__(self, lock_obj: Any) -> None:
            self.lock_file_obj = lock_obj
            self.lease = type("Lease", (), {"execution_env": {"HOME": str(home_a)}})()

        def release(self) -> None:
            self.released = True
            if self.lock_file_obj is not None:
                self.lock_file_obj.close()
                self.lock_file_obj = None

        def abandon_parent_reference(self) -> None:
            pass

    lock_file = tmp_path / "google-a.lock"
    lock_obj = lock_file.open("w")
    fake_claim = FakeClaim(lock_obj)

    class FakeCoordinator:
        def acquire_claim(self, *args: Any, **kwargs: Any) -> Any:
            return fake_claim

    operation_root = tmp_path / "ops"
    launcher_file = tmp_path / "fake-launcher"
    launcher_file.write_text("#!/bin/sh\nexit 42\n")
    launcher_file.chmod(0o755)

    class FakeChild:
        pid = 99991

        def wait(self) -> int:
            return 42

        def poll(self) -> int:
            return 42

    monkeypatch.setattr(module, "MANAGER_ROOT", tmp_path)
    monkeypatch.setattr(module, "LEASES_DIR", leases)

    def fake_nonzero_popen(*_args: Any, **kwargs: Any) -> FakeChild:
        status_fd = int(kwargs["env"]["NEXUS_HCOM_AGY_STATUS_FD"])
        base = {
            "schema": "nexus.hcom_collab_status.v1",
            "account_alias_hash": "alias-a",
            "lease_id_hash": "lease-a",
            "pid": 99992,
        }
        os.write(
            status_fd,
            (json.dumps({**base, "event": "provider_started"}) + "\n").encode(),
        )
        os.write(
            status_fd,
            (json.dumps({**base, "event": "provider_terminal", "exit_code": 42}) + "\n").encode(),
        )
        return FakeChild()

    # 1. Verify dispatch_hcom_collab returns child exit code and releases claim
    code = module.dispatch_hcom_collab(
        cwd=str(tmp_path),
        hcom_args=["--fast"],
        model=None,
        pool_wait_timeout=1.0,
        coordinator=FakeCoordinator(),
        popen_factory=fake_nonzero_popen,
        launcher_path=launcher_file,
    )
    assert code == 42
    assert fake_claim.released is True

    # 2. Verify _run_foreground_hcom_operation journals failure when child exits non-zero
    monkeypatch.setattr(module, "dispatch_hcom_collab", lambda **kw: 42)
    code2 = module._run_foreground_hcom_operation(
        cwd=str(tmp_path),
        hcom_args=["--fast"],
        model=None,
        pool_wait_timeout=1.0,
        operation_root=operation_root,
    )
    assert code2 == 42
    operation_ids = [path.name for path in (operation_root / "operations").iterdir()]
    assert len(operation_ids) == 1
    record = module.AgyOperationJournal(operation_root).read(operation_ids[0])
    assert record["status"] == "FAILED"
    assert record["exit_code"] == 42
    assert record["failure_kind"] == "HCOM_COLLAB_EXIT_NONZERO"


def test_dispatch_hcom_collab_rejects_forbidden_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """_parse_hcom_args and dispatch_hcom_collab strictly reject headless/detached flags."""
    module = _load_dispatch_module(monkeypatch)

    # Rejection in _parse_hcom_args
    for flag in ["--headless", "--no-terminal", "--detach", "--daemon", "-d", "--background"]:
        with pytest.raises(ValueError, match="HCOM_COLLAB_FORBIDDEN_FLAG"):
            module._parse_hcom_args(json.dumps([flag]))

    # Rejection in dispatch_hcom_collab
    with pytest.raises(ValueError, match="HCOM_COLLAB_FORBIDDEN_FLAG"):
        module.dispatch_hcom_collab(
            cwd="/tmp",
            hcom_args=["--headless"],
            model=None,
        )


def test_dispatch_hcom_collab_fails_closed_if_sensitive_api_keys_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fails closed with RuntimeError if SENSITIVE_API_KEYS is missing from pool module."""
    module = _load_dispatch_module(monkeypatch)
    home_a = tmp_path / "accounts" / "google-a"
    home_a.mkdir(parents=True)

    class FakeClaim:
        internal_id = "google-a"
        account_alias_hash = "alias-a"
        lease_id_hash = "lease-a"

        def __init__(self, lock_obj: Any) -> None:
            self.lock_file_obj = lock_obj
            self.lease = type("Lease", (), {"execution_env": {"HOME": str(home_a)}})()

        def release(self) -> None:
            pass

    lock_file = tmp_path / "google-a.lock"
    lock_obj = lock_file.open("w")
    fake_claim = FakeClaim(lock_obj)

    class FakeCoordinator:
        def acquire_claim(self, *args: Any, **kwargs: Any) -> Any:
            return fake_claim

    monkeypatch.setattr(module, "MANAGER_ROOT", tmp_path)
    monkeypatch.delattr(module._agy_account_pool, "SENSITIVE_API_KEYS", raising=False)
    with pytest.raises(RuntimeError, match="SENSITIVE_API_KEYS_CONFIG_MISSING"):
        module.dispatch_hcom_collab(
            cwd=str(tmp_path),
            hcom_args=[],
            model=None,
            coordinator=FakeCoordinator(),
        )
