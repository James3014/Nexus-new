"""#2202: the headless Agy dispatcher runs accept-edits Agy inside the #1912 boundary.

* accept-edits runs start only inside a Seatbelt profile that lets Agy write
  the target worktree (minus ``.git``/``.agents``) and a per-run root, with a
  disposable HOME, an exact env and a post-exit descendant sweep;
* a missing ``sandbox-exec`` (or a snapshot without the boundary module)
  refuses the run before any account is leased; there is no unconfined path;
* ``--temp-command-permissions`` and every ``command(...)`` allow rule are
  refused (Owner decision on #1912: no auto-approved commands);
* every production Agy launcher is either wrapped, plan-mode-only, a caller of
  the dispatcher, or an explicitly reviewed exception.

Seatbelt itself only runs on macOS; elsewhere the profile text is evaluated
instead, so every test also passes on Linux.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from nexus.executors import agy_dispatch_boundary as boundary_mod
from nexus.executors import agy_write_admission as admission
from nexus.services import agy_account_pool as agy_pool

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"

os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader("nexus_agy_dispatch_write_boundary", str(DISPATCH_PATH)).load_module()

_spec = importlib.util.spec_from_file_location(
    "agy_write_admission_test_helpers",
    ROOT / "tests" / "nexus" / "executors" / "test_agy_write_admission.py",
)
assert _spec is not None and _spec.loader is not None
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
_effective_write = _helpers._effective_write
_seatbelt_usable = _helpers._seatbelt_usable

TOKEN = Path(".gemini") / "antigravity-cli" / "antigravity-oauth-token"


class _Claim:
    def __init__(self, home: Path) -> None:
        self.account_alias_hash = "boundary"
        self.lease_id_hash = "lease-boundary"
        self.internal_id = "boundary-account"
        self.lease = type(
            "Lease",
            (),
            {
                "execution_env": {
                    "HOME": str(home),
                    "PATH": "/usr/bin:/bin",
                    "ACCOUNT": "boundary-account",
                    "NEXUS_SECRET_PROBE": "must-not-leak",
                }
            },
        )()
        self.released = False

    def release(self) -> None:
        self.released = True


class _Coordinator:
    def __init__(self, home: Path) -> None:
        self.claim = _Claim(home)
        self.acquire_count = 0

    def acquire_claim(self, **_kwargs):
        self.acquire_count += 1
        return self.claim


def _source_home(tmp_path: Path) -> Path:
    home = (tmp_path / "lease-home").resolve()
    token = home / TOKEN
    token.parent.mkdir(parents=True)
    token.write_text("token", encoding="utf-8")
    return home


def _target(tmp_path: Path) -> Path:
    target = (tmp_path / "work").resolve()
    target.mkdir()
    (target / ".git").write_text("gitdir: /expected\n", encoding="utf-8")
    return target


@pytest.fixture
def seatbelt_on(monkeypatch):
    """Let the boundary be prepared off macOS; nothing here runs sandbox-exec."""
    if not admission.seatbelt_available():
        monkeypatch.setattr(boundary_mod, "seatbelt_available", lambda: True)


# ---------------------------------------------------------------------------
# boundary construction
# ---------------------------------------------------------------------------


def test_boundary_profile_env_and_home(tmp_path, seatbelt_on):
    home = _source_home(tmp_path)
    target = _target(tmp_path)
    log = (tmp_path / "ops" / "agy.log").resolve()
    log.parent.mkdir()
    outside = (tmp_path / "canonical").resolve()
    source_env = {
        "HOME": str(home),
        "PATH": "/usr/bin:/bin",
        "NEXUS_SECRET_PROBE": "x",
        "GH_TOKEN": "x",
    }
    boundary = boundary_mod.prepare_accept_edits_boundary(
        source_env=source_env,
        target=target,
        extra_writable_files=[str(log)],
        extra_writable_roots=[log.parent],
    )
    try:
        run_root = boundary.run_root
        assert boundary.target == target
        assert boundary.run_home == run_root / "home"
        assert (boundary.run_home / TOKEN).read_text() == "token"
        settings = json.loads((boundary.run_home / admission.AGY_RUN_HOME_SETTINGS).read_text())
        assert "command(*)" in settings["permissions"]["deny"]
        # exact env: allowlist + disposable HOME/TMPDIR + the sweep tag only
        assert boundary.env["HOME"] == str(boundary.run_home)
        assert boundary.env["TMPDIR"] == str(boundary.run_tmp)
        assert boundary.env["PATH"] == "/usr/bin:/bin"
        assert boundary.env["NEXUS_CLI_WORKER_RUN_TAG"] == boundary.run_tag
        assert "NEXUS_SECRET_PROBE" not in boundary.env
        assert "GH_TOKEN" not in boundary.env
        # argv: sandbox-exec with the profile file, then agy's own argv
        assert boundary.wrap_argv(["agy", "--mode", "accept-edits"]) == [
            admission.SANDBOX_EXEC_PATH,
            "-f",
            str(boundary.profile_path),
            "agy",
            "--mode",
            "accept-edits",
        ]
        assert boundary.profile_path.read_text() == boundary.profile
        assert not admission.path_inside(boundary.profile_path, run_root)
        assert boundary.sweep_roots == (str(target), str(run_root))
        profile = boundary.profile
        lines = profile.splitlines()
        assert lines[:2] == ["(version 1)", "(allow default)"]
        # #2888: the worker-runs deny (a comment line, then the rule) sits right after the head
        assert lines[2].startswith(";; #2888")
        assert lines[3] == (
            f'(deny file-read* file-write* (subpath "{boundary_mod.WORKER_RUNS_DIR}"))'
        )
        assert lines[4] == "(deny file-write*)"
        for path in (target / "src" / "a.py", run_root / "tmp" / "x", log):
            assert _effective_write(profile, path) == "allow", path
        for path in (
            target / ".git",
            target / ".git" / "config",
            target / ".agents" / "hooks.json",
            boundary.run_home / admission.AGY_RUN_HOME_SETTINGS,
            outside / "escape.txt",
            log.parent / "other.log",
            home / TOKEN,
        ):
            assert _effective_write(profile, path) == "deny", path
    finally:
        boundary.cleanup()
    assert not boundary.run_root.exists()
    assert not boundary.profile_path.exists()


def _default_keychain(home: str | None = None) -> str:
    env = dict(os.environ)
    if home is not None:
        env["HOME"] = home
    return subprocess.run(
        ["security", "default-keychain"], env=env, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_run_home_gets_isolated_default_keychain(tmp_path, seatbelt_on):
    """No default keychain in the run HOME makes macOS raise a blocking dialog."""
    home = _source_home(tmp_path)
    target = _target(tmp_path)
    real_default = _default_keychain() if sys.platform == "darwin" else None
    boundary = boundary_mod.prepare_accept_edits_boundary(
        source_env={"HOME": str(home), "PATH": "/usr/bin:/bin"}, target=target
    )
    try:
        keychain = boundary.run_home / agy_pool.AGY_ISOLATED_KEYCHAIN
        if sys.platform == "darwin":
            assert boundary.keychain_state == boundary_mod.KEYCHAIN_ISOLATED
            assert keychain.is_file()
            assert _default_keychain(str(boundary.run_home)) == f'"{keychain}"'
            # created with HOME=<run home>: the real user's default is untouched
            assert _default_keychain() == real_default
        else:
            assert boundary.keychain_state == boundary_mod.KEYCHAIN_NOT_APPLICABLE
            assert not keychain.exists()
        # the sandboxed agy may update the keychain and its preferences (both
        # inside the writable run root); the agy config stays locked
        profile = boundary.profile
        for path in (
            keychain,
            boundary.run_home / "Library" / "Keychains" / "agy.keychain-db.sb-x",
            boundary.run_home / "Library" / "Preferences" / "com.apple.security.plist",
        ):
            assert _effective_write(profile, path) == "allow", path
        assert _effective_write(profile, boundary.run_home / ".gemini" / "config" / "x") == "deny"
    finally:
        boundary.cleanup()
    assert not boundary.run_root.exists()


def test_isolated_keychain_helper_is_not_applicable_off_macos(tmp_path, monkeypatch):
    monkeypatch.setattr(agy_pool.sys, "platform", "linux")
    assert agy_pool.ensure_macos_isolated_keychain(str(tmp_path)) is None
    assert list(tmp_path.iterdir()) == []


def test_keychain_setup_failure_refuses_the_boundary(tmp_path, monkeypatch, seatbelt_on):
    def broken(_home, **_kwargs):
        raise agy_pool.AgyAccountPoolManagerError("AGY_KEYCHAIN_SETUP_FAILED:create-keychain:1:x")

    monkeypatch.setattr(agy_pool, "ensure_macos_isolated_keychain", broken)
    scratch = tmp_path / "tmpdir"
    scratch.mkdir()
    monkeypatch.setattr(boundary_mod.tempfile, "tempdir", str(scratch))
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="AGY_KEYCHAIN_SETUP_FAILED"):
        boundary_mod.prepare_accept_edits_boundary(
            source_env={"HOME": str(_source_home(tmp_path)), "PATH": "/usr/bin:/bin"},
            target=_target(tmp_path),
        )
    assert list(scratch.iterdir()) == []  # run root and profile dir removed


def test_boundary_refuses_without_seatbelt(tmp_path, monkeypatch):
    monkeypatch.setattr(boundary_mod, "seatbelt_available", lambda: False)
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="seatbelt_unavailable"):
        boundary_mod.prepare_accept_edits_boundary(
            source_env={"HOME": str(_source_home(tmp_path))}, target=_target(tmp_path)
        )


def test_boundary_refuses_extra_writable_path_inside_target(tmp_path, seatbelt_on):
    target = _target(tmp_path)
    home = _source_home(tmp_path)
    for extra, reason in (
        (target / ".git" / "config", "extra_path_in_target"),
        (target / "notes.log", "extra_path_in_target"),
        ("relative.log", "relative_extra_path"),
    ):
        with pytest.raises(boundary_mod.AgyWriteBoundaryError, match=reason):
            boundary_mod.prepare_accept_edits_boundary(
                source_env={"HOME": str(home)}, target=target, extra_writable_files=[extra]
            )


# ---------------------------------------------------------------------------
# dispatcher integration
# ---------------------------------------------------------------------------


def test_accept_edits_refused_before_lease_when_boundary_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(dispatch, "_write_boundary_available", lambda: False)
    coordinator = _Coordinator(_source_home(tmp_path))
    target = _target(tmp_path)
    events: list[dict] = []

    def popen_must_not_run(*_args, **_kwargs):
        raise AssertionError("agy launched without the write boundary")

    monkeypatch.setattr(dispatch.subprocess, "Popen", popen_must_not_run)
    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=coordinator,
        operation_hook=events.append,
    )
    assert code == 64
    assert coordinator.acquire_count == 0
    assert any(
        e.get("failure_kind") == "DISPATCH_CONTRACT_REJECTED:AGY_WRITE_BOUNDARY_UNAVAILABLE"
        for e in events
    )


def test_snapshot_without_boundary_module_is_unavailable(monkeypatch):
    def missing(name):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(dispatch, "import_module", missing)
    assert dispatch._write_boundary_available() is False


def test_plan_mode_does_not_require_the_boundary(tmp_path, monkeypatch):
    monkeypatch.setattr(dispatch, "_write_boundary_available", lambda: False)
    home = _source_home(tmp_path)
    coordinator = _Coordinator(home)
    seen: dict = {}

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary=None):
        seen["boundary"] = write_boundary
        seen["home"] = env["HOME"]
        return 0, "ok", "", False, 1

    code = dispatch.dispatch_run(
        prompt="inspect", cwd=str(tmp_path), mode="plan", coordinator=coordinator, run_agy_fn=runner
    )
    assert code == 0
    assert seen == {"boundary": None, "home": str(home)}


def test_accept_edits_attempt_runs_in_disposable_home_with_profile(
    tmp_path, monkeypatch, seatbelt_on
):
    home = _source_home(tmp_path)
    target = _target(tmp_path)
    coordinator = _Coordinator(home)
    log = (tmp_path / "op" / "agy.log").resolve()
    log.parent.mkdir()
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    monkeypatch.setattr(dispatch, "OPERATION_ROOT", log.parent)
    seen: dict = {}

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        settings = write_boundary.run_home / admission.AGY_RUN_HOME_SETTINGS
        seen["boundary"] = write_boundary
        seen["env"] = dict(env)
        seen["permissions"] = json.loads(settings.read_text())["permissions"]
        return 0, "edited", "", False, 1

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=coordinator,
        run_agy_fn=runner,
    )
    assert code == 0
    boundary = seen["boundary"]
    assert seen["env"] == boundary.env
    assert seen["env"]["HOME"] == str(boundary.run_home) != str(home)
    assert "ACCOUNT" not in seen["env"] and "NEXUS_SECRET_PROBE" not in seen["env"]
    # the dispatcher's bounded profile lands in the disposable HOME
    assert f"write_file({target / 'a.py'})" in seen["permissions"]["allow"]
    assert "command(*)" in seen["permissions"]["deny"]
    assert not any(rule.startswith("command") for rule in seen["permissions"]["allow"])
    # the leased account HOME is never touched, and the run root is gone
    assert not (home / admission.AGY_RUN_HOME_SETTINGS).exists()
    assert not boundary.run_root.exists()
    # #2314: the attestation log is relayed by the dispatcher, never granted
    assert _effective_write(boundary.profile, log) == "deny"
    assert _effective_write(boundary.profile, target / ".git") == "deny"
    assert coordinator.claim.released is True


def test_run_agy_refuses_accept_edits_without_boundary(tmp_path, monkeypatch):
    def popen_must_not_run(*_args, **_kwargs):
        raise AssertionError("agy launched without the write boundary")

    monkeypatch.setattr(dispatch.subprocess, "Popen", popen_must_not_run)
    with pytest.raises(RuntimeError, match="AGY_WRITE_BOUNDARY_REQUIRED"):
        dispatch.run_agy(
            env=dict(os.environ),
            prompt="edit",
            cwd=str(tmp_path),
            mode="accept-edits",
            model=None,
            effort=None,
            timeout=5,
        )


# ---------------------------------------------------------------------------
# failure classification under the boundary (2026-10-15 regression)
# ---------------------------------------------------------------------------

# agy.log lines from operation agyop_2bdee3a289264238a3667857302c7fca: agy's own
# startup writes under the locked run-HOME config dir, denied by Seatbelt.
_RUN_HOME_DENIALS = (
    "E1015 14:31:56.935006      32 mcp_manager.go:793] Failed to create mcp config file: "
    "open {home}/.gemini/config/mcp_config.json: operation not permitted\n"
    "E1015 14:31:56.935138      32 server.go:1055] Failed to load MCP config: failed to get "
    "specs from config: failed to create mcp config file: open "
    "{home}/.gemini/config/mcp_config.json: operation not permitted\n"
    "E1015 14:31:56.935414     150 migrate.go:156] Migration: failed to create .migrated "
    "file: open {home}/.gemini/config/.migrated: operation not permitted\n"
)
_AGY_QUOTA_STDERR = (
    "error: Individual quota reached. Please upgrade your subscription to increase your "
    "limits. Resets in 83h48m12s.\n"
    'AGY_ERROR: {"short_error":"RESOURCE_EXHAUSTED (code 429): Individual quota reached. '
    'Please upgrade your subscription to increase your limits. Resets in 83h48m12s.",'
    '"status":"RESOURCE_EXHAUSTED","error_code":429,"code_kind":"http","retryable":true,'
    '"error_id":"59530d02-c4ef-4e9f-87ee-6b2dd626aac9-1"}\n'
)


class _RotatingCoordinator(_Coordinator):
    def __init__(self, home: Path) -> None:
        super().__init__(home)
        self.rotated: list = []
        self.retired: list = []

    def rotate_claim(self, *, current_claim, failure_kind, **_kwargs):
        self.rotated.append(failure_kind)
        return self.claim

    def retire_failed_claim(self, claim, kind, **_kwargs):
        self.retired.append(kind)


def _metas(err: str) -> list[dict]:
    prefix = "NEXUS_AGY_DISPATCH "
    return [json.loads(line[len(prefix) :]) for line in err.splitlines() if line.startswith(prefix)]


def _run_with_log(tmp_path, monkeypatch, attempts):
    """Run accept-edits; each attempt appends its log text and returns (code, stderr)."""
    home = _source_home(tmp_path)
    target = (tmp_path / "work").resolve()
    target.mkdir()
    # a real repository, so each attempt's source baseline proves "no effect"
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    coordinator = _RotatingCoordinator(home)
    log = (tmp_path / "op" / "agy.log").resolve()
    log.parent.mkdir()
    log.write_text("", encoding="utf-8")
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    monkeypatch.setattr(dispatch, "OPERATION_ROOT", log.parent)
    monkeypatch.setenv("NEXUS_AGY_MAX_ACCOUNT_FAILOVERS", "3")
    pending = list(attempts)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        log_text, code, stderr = pending.pop(0)

        def fill(text: str) -> str:
            return text.replace("{home}", str(write_boundary.run_home)).replace(
                "{target}", str(target)
            )

        with log.open("a", encoding="utf-8") as handle:
            handle.write(fill(log_text))
        return code, "", fill(stderr), False, 1

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=coordinator,
        run_agy_fn=runner,
    )
    return code, coordinator, pending


def test_quota_failure_with_run_home_denials_rotates(tmp_path, monkeypatch, seatbelt_on, capsys):
    code, coordinator, pending = _run_with_log(
        tmp_path,
        monkeypatch,
        [(_RUN_HOME_DENIALS, 1, _AGY_QUOTA_STDERR), (_RUN_HOME_DENIALS, 0, "")],
    )
    metas = _metas(capsys.readouterr().err)
    assert code == 0 and pending == []
    assert coordinator.rotated == [dispatch.AccountFailureKind.QUOTA_EXHAUSTED]
    assert metas[-1]["status"] == "completed" and metas[-1]["rotations"] == 1


@pytest.mark.parametrize(
    "genuine",
    [
        # a Seatbelt denial outside the run HOME (the target's .git)
        "E1015 14:31:57.000000      32 tool.go:1] write: open {target}/.git/config: "
        "operation not permitted\n",
        # a tool-permission denial still counts even when it names a run-HOME path
        "I1015 14:31:57.000000      32 tool.go:1] Tool permission denied: "
        "write_file({home}/notes.txt): operation not permitted\n",
        # a denied write to a locked run-HOME file outside the expected allowlist
        "E1015 14:31:57.000000      32 settings.go:1] save: open "
        "{home}/.gemini/antigravity-cli/settings.json: operation not permitted\n",
    ],
)
@pytest.mark.parametrize("stderr", ["", _AGY_QUOTA_STDERR], ids=["no-quota", "with-quota"])
def test_genuine_permission_denial_still_blocks(
    tmp_path, monkeypatch, seatbelt_on, capsys, genuine, stderr
):
    """A genuine permission signal wins even over a provider quota failure."""
    code, coordinator, _ = _run_with_log(
        tmp_path, monkeypatch, [(_RUN_HOME_DENIALS + genuine, 1, stderr)]
    )
    metas = _metas(capsys.readouterr().err)
    assert code != 0
    assert coordinator.rotated == []
    assert metas[-1]["failure_kind"] == "PERMISSION_OR_SCOPE_ERROR"


def test_run_home_denials_alone_do_not_fail_a_clean_run(tmp_path, monkeypatch, seatbelt_on, capsys):
    code, coordinator, _ = _run_with_log(tmp_path, monkeypatch, [(_RUN_HOME_DENIALS, 0, "")])
    metas = _metas(capsys.readouterr().err)
    assert code == 0
    assert coordinator.rotated == []
    assert metas[-1]["status"] == "completed"


# The id is kept for exact-base impact continuity; the assertion is now the
# reverse: a genuine permission signal outranks a quota signal.
def test_classify_failure_quota_outranks_permission_markers():
    """(Id kept.) Quota wins only once no genuine permission signal remains."""
    stdout = "open /elsewhere/file: operation not permitted"
    for stderr in (_AGY_QUOTA_STDERR, "error: boom\n"):
        assert (
            dispatch.classify_failure(1, stdout, stderr, False)
            == dispatch.AccountFailureKind.PERMISSION_OR_SCOPE_ERROR
        )
    assert (
        dispatch.classify_failure(1, "", _AGY_QUOTA_STDERR, False)
        == dispatch.AccountFailureKind.QUOTA_EXHAUSTED
    )
    bare_429 = 'AGY_ERROR: {"status":"UNAVAILABLE_X","error_code":429}\n'
    assert (
        dispatch.classify_failure(1, "", bare_429, False)
        == dispatch.AccountFailureKind.QUOTA_EXHAUSTED
    )


def test_expected_run_home_denial_matches_only_run_home_eperm(tmp_path):
    home = (tmp_path / "run" / "home").resolve()
    line = f"open {home}/.gemini/config/.migrated: operation not permitted"
    assert boundary_mod.is_expected_run_home_denial(line, home)
    assert not boundary_mod.is_expected_run_home_denial(
        f"open {home}/../escape: operation not permitted", home
    )
    assert not boundary_mod.is_expected_run_home_denial(
        f"open {tmp_path}/x: operation not permitted", home
    )
    assert not boundary_mod.is_expected_run_home_denial(f"open {home}/x: permission denied", home)
    assert not boundary_mod.is_expected_run_home_denial("operation not permitted", home)
    assert boundary_mod.is_expected_run_home_denial(
        f"open {home}/.gemini/config/mcp_config.json: operation not permitted", home
    )
    # only the exact startup paths: other run-HOME paths are real signals
    for other in (
        f"{home}/{admission.AGY_RUN_HOME_SETTINGS}",
        f"{home}/.gemini/config",
        f"{home}/.gemini/config/hooks.json",
        f"{home}/x",
    ):
        assert not boundary_mod.is_expected_run_home_denial(
            f"open {other}: operation not permitted", home
        ), other


def test_runner_without_boundary_parameter_is_refused_before_lease(tmp_path, seatbelt_on, capsys):
    coordinator = _Coordinator(_source_home(tmp_path))
    target = _target(tmp_path)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout):
        raise AssertionError("an unconfined accept-edits runner must not start")

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=coordinator,
        run_agy_fn=runner,
    )
    metas = _metas(capsys.readouterr().err)
    assert code == 64
    assert metas[-1]["failure_kind"] == (
        "DISPATCH_CONTRACT_REJECTED:AGY_WRITE_BOUNDARY_RUNNER_UNSUPPORTED"
    )
    assert coordinator.acquire_count == 0


def test_boundary_prepare_failure_is_terminal_and_releases_lease(
    tmp_path, monkeypatch, seatbelt_on, capsys
):
    coordinator = _RotatingCoordinator(_source_home(tmp_path))
    scratch = tmp_path / "tmpdir"
    scratch.mkdir()
    monkeypatch.setattr(boundary_mod.tempfile, "tempdir", str(scratch))
    # an unrepresentable path aborts after the run root exists
    monkeypatch.setattr(
        boundary_mod,
        "build_seatbelt_profile",
        lambda **_kw: (_ for _ in ()).throw(ValueError("unrepresentable")),
    )

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        raise AssertionError("no attempt may start without its boundary")

    target = _target(tmp_path)
    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=coordinator,
        run_agy_fn=runner,
    )
    metas = _metas(capsys.readouterr().err)
    assert code == 64
    assert metas[-1]["status"] == "invalid_contract"
    assert metas[-1]["failure_kind"] == (
        "DISPATCH_CONTRACT_REJECTED:AGY_WRITE_BOUNDARY_PREPARE_FAILED:"
        "AGY_WRITE_BOUNDARY_UNAVAILABLE:profile_unrepresentable"
    )
    assert coordinator.rotated == [] and coordinator.claim.released is True
    assert list(scratch.iterdir()) == []  # run root and profile dir removed


def test_descendant_sweep_failure_is_terminal(tmp_path, monkeypatch, seatbelt_on, capsys):
    code, coordinator, pending = _run_with_log(
        tmp_path,
        monkeypatch,
        [
            ("", 1, _AGY_QUOTA_STDERR + "\nNEXUS_AGY_DESCENDANT_SWEEP_FAILED\n"),
            ("", 0, ""),
        ],
    )
    metas = _metas(capsys.readouterr().err)
    assert code != 0
    assert len(pending) == 1  # no second attempt
    assert coordinator.rotated == []
    assert metas[-1]["status"] == "failed"
    assert metas[-1]["failure_kind"] == "AGY_DESCENDANT_SWEEP_FAILED"
    assert metas[-1]["reconciliation_required"] is True


class _SweepSpy:
    """Records every ``sweep()`` call and, separately, the sweep work done.

    The work is the tracker stop plus the tagged-process sweep; both are fakes
    here, so nothing on the host is signalled.
    """

    def __init__(self, monkeypatch, *, clean: bool = False) -> None:
        self.calls: list[bool] = []
        self.work: list[str] = []
        real_sweep = boundary_mod.AgyDispatchBoundary.sweep

        def sweep(boundary):
            result = real_sweep(boundary)
            self.calls.append(result)
            return result

        monkeypatch.setattr(boundary_mod.AgyDispatchBoundary, "sweep", sweep)
        cli_worker = boundary_mod.cli_worker
        monkeypatch.setattr(
            cli_worker, "_sweep_tagged_processes", lambda _tag: self.work.append("tagged") or True
        )
        monkeypatch.setattr(cli_worker, "_pids_with_cwd_under", lambda *_a: frozenset())
        monkeypatch.setattr(cli_worker, "_sweep_clean", lambda *_a, **_k: clean)

    def launch(self, boundary) -> None:
        """Mark ``boundary`` launched with a fake live tracker (no real pid)."""
        spy = self

        class _Tracker:
            probe_failed = False

            def stop(self):
                spy.work.append("tracker.stop")
                return set()

        boundary._launched = True
        boundary._tracker = _Tracker()
        if boundary._baseline is None:
            boundary._baseline = type("Baseline", (), {"preexisting": frozenset()})()


def test_launch_frame_exception_is_swept_and_terminal(tmp_path, monkeypatch, seatbelt_on, capsys):
    spy = _SweepSpy(monkeypatch)
    coordinator = _RotatingCoordinator(_source_home(tmp_path))
    target = _target(tmp_path)
    calls = []

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        # stands in for run_agy failing after after_launch (e.g. the provider
        # identity hook): launched, never swept
        calls.append(1)
        spy.launch(write_boundary)
        raise RuntimeError("PROVIDER_IDENTITY_PERSIST_FAILED")

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=coordinator,
        run_agy_fn=runner,
    )
    metas = _metas(capsys.readouterr().err)
    # the handler sweeps; cleanup() sees the recorded result and does not, and
    # the verdict record (#2470) reads the same cached result
    assert spy.calls == [False, False]
    assert spy.work == ["tracker.stop", "tagged"]
    assert code != 0 and calls == [1]
    assert coordinator.rotated == []
    assert metas[-1]["failure_kind"] == "AGY_DESCENDANT_SWEEP_FAILED"
    assert coordinator.claim.released is True


def _launched_then_raises(write_boundary):
    write_boundary._launched = True
    raise RuntimeError("PROVIDER_IDENTITY_PERSIST_FAILED")


def test_launch_frame_exception_with_clean_sweep_still_raises(tmp_path, monkeypatch, seatbelt_on):
    monkeypatch.setattr(boundary_mod.AgyDispatchBoundary, "sweep", lambda self: True)
    target = _target(tmp_path)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        _launched_then_raises(write_boundary)

    with pytest.raises(RuntimeError, match="PROVIDER_IDENTITY_PERSIST_FAILED"):
        dispatch.dispatch_run(
            prompt="edit",
            cwd=str(target),
            mode="accept-edits",
            write_paths=[str(target / "a.py")],
            coordinator=_Coordinator(_source_home(tmp_path)),
            run_agy_fn=runner,
        )


@pytest.mark.parametrize("clean", [True, False])
def test_cleanup_sweeps_a_launched_unswept_run_once(tmp_path, monkeypatch, seatbelt_on, clean):
    spy = _SweepSpy(monkeypatch, clean=clean)
    boundary = boundary_mod.prepare_accept_edits_boundary(
        source_env={"HOME": str(_source_home(tmp_path))}, target=_target(tmp_path)
    )
    spy.launch(boundary)
    boundary.cleanup()
    assert spy.calls == [clean]
    assert spy.work == ["tracker.stop", "tagged"]
    # later sweep() calls return the first result (a clean run stays clean)
    # without doing the work again
    assert boundary.sweep() is clean
    assert boundary.sweep() is clean
    assert spy.calls == [clean, clean, clean]
    assert spy.work == ["tracker.stop", "tagged"]


def test_attestation_log_symlink_or_non_regular_is_refused(tmp_path, seatbelt_on):
    home = _source_home(tmp_path)
    target = _target(tmp_path)
    ops = (tmp_path / "ops").resolve()
    ops.mkdir()
    other = ops / "other-operation.json"
    other.write_text("{}", encoding="utf-8")
    link = ops / "agy.log"
    link.symlink_to(other)
    fifo = ops / "fifo.log"
    os.mkfifo(fifo)
    for extra, reason in ((link, "extra_path_is_symlink"), (fifo, "extra_path_not_regular_file")):
        with pytest.raises(boundary_mod.AgyWriteBoundaryError, match=reason):
            boundary_mod.prepare_accept_edits_boundary(
                source_env={"HOME": str(home)},
                target=target,
                extra_writable_files=[extra],
                extra_writable_roots=[ops],
            )
    # a symlinked parent directory (/var -> /private/var) is fine
    ops_alias = tmp_path / "ops-alias"
    ops_alias.symlink_to(ops, target_is_directory=True)
    boundary = boundary_mod.prepare_accept_edits_boundary(
        source_env={"HOME": str(home)},
        target=target,
        extra_writable_files=[ops_alias / "fresh.log"],
        extra_writable_roots=[ops],
    )
    boundary.cleanup()


def test_attestation_log_replaced_by_symlink_refuses_next_attempt(
    tmp_path, monkeypatch, seatbelt_on, capsys
):
    """Attempt 1 swaps its writable log for a symlink; attempt 2 must not follow it."""
    home = _source_home(tmp_path)
    target = (tmp_path / "work").resolve()
    target.mkdir()
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    coordinator = _RotatingCoordinator(home)
    ops = (tmp_path / "ops").resolve()
    ops.mkdir()
    log = ops / "agy.log"
    log.write_text("", encoding="utf-8")
    victim = ops / "victim.json"
    victim.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    monkeypatch.setattr(dispatch, "OPERATION_ROOT", ops)
    attempts = []

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        attempts.append(1)
        log.unlink()
        log.symlink_to(victim)
        return 1, "", _AGY_QUOTA_STDERR, False, 1

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=coordinator,
        run_agy_fn=runner,
    )
    _metas(capsys.readouterr().err)
    # #2314: the log is no longer a Seatbelt grant, so a swapped log cannot
    # redirect the next attempt's grant; the rotation proceeds and the victim
    # is never written.
    assert len(attempts) > 1
    assert code != 0
    assert victim.read_text() == "{}"


def test_extra_writable_file_admitted_only_under_allowed_roots(tmp_path, seatbelt_on):
    home = _source_home(tmp_path)
    target = _target(tmp_path)
    ops = (tmp_path / "ops").resolve()
    ops.mkdir()
    log = ops / "agy.log"
    boundary = boundary_mod.prepare_accept_edits_boundary(
        source_env={"HOME": str(home)},
        target=target,
        extra_writable_files=[log],
        extra_writable_roots=[ops],
    )
    try:
        assert _effective_write(boundary.profile, log) == "allow"
    finally:
        boundary.cleanup()
    real_home = Path(os.path.realpath(Path.home()))
    for extra, roots, reason in (
        (real_home / ".ssh" / "authorized_keys", [ops], "extra_path_outside_allowed_roots"),
        # even a misconfigured root cannot open a real-HOME dotfile dir
        (real_home / ".ssh" / "authorized_keys", [real_home], "extra_path_in_home_dotfiles"),
        (ops, [ops], "extra_path_is_directory"),
        (home / "agy.log", [tmp_path], "extra_path_in_lease_home"),
    ):
        with pytest.raises(boundary_mod.AgyWriteBoundaryError, match=reason):
            boundary_mod.prepare_accept_edits_boundary(
                source_env={"HOME": str(home)},
                target=target,
                extra_writable_files=[extra],
                extra_writable_roots=roots,
            )


class _RecordingBoundary:
    """Routes the launch through a recorder instead of sandbox-exec."""

    def __init__(self, env: dict, recorder: Path, record: Path, *, swept: bool) -> None:
        self.env = env
        self._recorder = recorder
        self._record = record
        self._swept = swept
        self.calls: list[str] = []

    def wrap_argv(self, argv):
        self.calls.append("wrap_argv")
        return [sys.executable, str(self._recorder), str(self._record), *argv]

    def before_launch(self):
        self.calls.append("before_launch")

    def after_launch(self, pid):
        self.calls.append("after_launch")

    def sweep(self):
        self.calls.append("sweep")
        return self._swept


@pytest.mark.parametrize("swept", [True, False])
def test_run_agy_launches_through_boundary_and_fails_unproven_sweep(tmp_path, monkeypatch, swept):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_agy = bin_dir / "agy"
    fake_agy.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_agy.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.delenv("NEXUS_AGY_ATTESTATION_LOG", raising=False)
    recorder = tmp_path / "recorder.py"
    recorder.write_text(
        "import json, os, sys\n"
        "json.dump({'argv': sys.argv[2:], 'home': os.environ.get('HOME'),\n"
        "           'leak': os.environ.get('LEAK_PROBE')}, open(sys.argv[1], 'w'))\n"
        "print('done')\n",
        encoding="utf-8",
    )
    record = tmp_path / "record.json"
    run_env = {"HOME": str(tmp_path / "run-home"), "PATH": "/usr/bin:/bin"}
    boundary = _RecordingBoundary(run_env, recorder, record, swept=swept)
    work = tmp_path / "work"
    work.mkdir()

    code, out, err, timed_out, _ = dispatch.run_agy(
        env={**os.environ, "LEAK_PROBE": "leaked"},
        prompt="edit",
        cwd=str(work),
        mode="accept-edits",
        model=None,
        effort=None,
        timeout=10,
        write_boundary=boundary,
    )
    data = json.loads(record.read_text())
    assert data["argv"][:2] == [str(fake_agy), "--new-project"]
    assert data["argv"][data["argv"].index("--mode") + 1] == "accept-edits"
    assert data["home"] == run_env["HOME"]
    assert data["leak"] is None  # the boundary env replaces the caller env
    assert boundary.calls == ["wrap_argv", "before_launch", "after_launch", "sweep"]
    assert timed_out is False
    if swept:
        assert code == 0 and "done" in out
    else:
        assert code == 1
        assert "NEXUS_AGY_DESCENDANT_SWEEP_FAILED" in err


def test_real_boundary_blocks_writes_outside_target(tmp_path, monkeypatch, seatbelt_on):
    """On macOS a fake agy really runs under sandbox-exec; elsewhere the profile is evaluated."""
    home = _source_home(tmp_path)
    target = _target(tmp_path)
    outside = (tmp_path / "canonical").resolve()
    outside.mkdir()
    log = (tmp_path / "op" / "agy.log").resolve()
    log.parent.mkdir()
    boundary = boundary_mod.prepare_accept_edits_boundary(
        source_env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        target=target,
        extra_writable_files=[log],
        extra_writable_roots=[log.parent],
    )
    settings = boundary.run_home / admission.AGY_RUN_HOME_SETTINGS
    probes = [target / "inside.txt", log, outside / "escape.txt", target / ".git", settings]
    try:
        if not _seatbelt_usable():
            verdicts = [_effective_write(boundary.profile, path) for path in probes]
            assert verdicts == ["allow", "allow", "deny", "deny", "deny"]
            return
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        fake_agy = bin_dir / "agy"
        fake_agy.write_text(
            f"#!{sys.executable}\n"
            "import sys\n"
            "results = []\n"
            f"for path in {[str(p) for p in probes]!r}:\n"
            "    try:\n"
            "        open(path, 'w').write('x')\n"
            "        results.append('WROTE')\n"
            "    except OSError:\n"
            "        results.append('BLOCKED')\n"
            "print(','.join(results))\n",
            encoding="utf-8",
        )
        fake_agy.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
        monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
        monkeypatch.setattr(dispatch, "OPERATION_ROOT", log.parent)
        code, out, err, _timed_out, _ = dispatch.run_agy(
            env={},
            prompt="edit",
            cwd=str(target),
            mode="accept-edits",
            model=None,
            effort=None,
            timeout=30,
            write_boundary=boundary,
        )
        assert code == 0, err
        assert out.strip().splitlines()[-1] == "WROTE,WROTE,BLOCKED,BLOCKED,BLOCKED"
        assert not (outside / "escape.txt").exists()
        assert (target / ".git").read_text() == "gitdir: /expected\n"
    finally:
        boundary.cleanup()


# ---------------------------------------------------------------------------
# command grants (Owner decision on #1912)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["plan", "accept-edits"])
@pytest.mark.parametrize(
    "kwargs, refused",
    [
        ({"temp_command_permissions": True}, "--temp-command-permissions"),
        ({"allow_rules": ["command(*)"]}, "UNSAFE_PERMISSION_RULE:command(*)"),
        ({"allow_rules": ["command(git *)"]}, "command(git *)"),
        ({"allow_rules": ["command(pytest -q)"]}, "command(pytest -q)"),
        ({"allow_rules": ["Command(ls)"]}, "Command(ls)"),
    ],
)
def test_command_grants_are_refused(tmp_path, mode, kwargs, refused):
    with pytest.raises(ValueError, match=re.escape(refused)):
        dispatch.build_effective_permission_profile(
            cwd=str(tmp_path), mode=mode, write_paths=[str(tmp_path / "a.py")], **kwargs
        )


@pytest.mark.parametrize("mode", ["plan", "accept-edits"])
def test_every_profile_denies_commands_and_keeps_narrow_denies(tmp_path, mode):
    perms, _kind, _sha = dispatch.build_effective_permission_profile(
        cwd=str(tmp_path),
        mode=mode,
        write_paths=[str(tmp_path / "a.py")],
        deny_rules=["command(git push)"],
    )
    assert "command(*)" in perms["deny"]
    assert "command(git push)" in perms["deny"]
    assert not any(rule.startswith("command") for rule in perms["allow"])


def test_cli_refuses_temp_command_permissions_before_lease(tmp_path, monkeypatch):
    coordinator = _Coordinator(_source_home(tmp_path))
    events: list[dict] = []
    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(tmp_path),
        mode="plan",
        temp_command_permissions=True,
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (0, "ok", "", False, 1),
        operation_hook=events.append,
    )
    assert code == 64
    assert coordinator.acquire_count == 0
    assert any(
        str(e.get("failure_kind")).endswith("COMMAND_GRANT_REFUSED:--temp-command-permissions")
        for e in events
    )


@pytest.mark.parametrize("mode", ["plan", "accept-edits"])
def test_hybrid_replication_caller_requests_no_command_grant(tmp_path, mode):
    from nexus.research import hybrid_replication_live as live

    args = list(live._agy_permission_args(tmp_path, mode=mode))
    assert "--temp-command-permissions" not in args
    allow = [args[i + 1] for i, a in enumerate(args) if a == "--allow"]
    deny = [args[i + 1] for i, a in enumerate(args) if a == "--deny"]
    assert not any(rule.startswith("command") for rule in allow)
    # the dispatcher admits exactly what the caller sends
    dispatch.build_effective_permission_profile(
        cwd=str(tmp_path), mode=mode, allow_rules=allow, deny_rules=deny
    )


# ---------------------------------------------------------------------------
# launcher inventory
# ---------------------------------------------------------------------------

_JOINED = re.compile(r"""["']\s*\+?\s*\\?\s*["']""")
# Agy argv shapes: a --mode argument, Agy-only flags, or an hcom agy session.
_LAUNCH_MARKERS = (
    re.compile(r'"--mode",\s*"(?:plan|accept-edits)"'),
    re.compile(r'"--mode",\s*[A-Za-z_][\w.]*\s*[,\]]'),
    re.compile(r'"--print-timeout"'),
    re.compile(r'"--new-project"'),
    re.compile(r'"--add-dir"'),
    re.compile(r'"agy",\s*"--terminal"'),
    # a bare print-mode launch: [<agy binary>, "-p" | "--print", ...] (not claude -p)
    re.compile(r'\[\s*(?:"agy"|[\w.]*agy[\w.]*),\s*"(?:-p|--print)"', re.IGNORECASE),
)

WRAPPED_CLI_WORKER = "wrapped: run_cli_worker + build_seatbelt_profile"
WRAPPED_DISPATCH = "wrapped: agy_dispatch_boundary"
PLAN_ONLY = "plan-mode only"
VIA_DISPATCHER = "calls nexus-agy-dispatch, never raw agy"
REVIEWED = "reviewed exception"
READ_ONLY_PROBE = "read-only probe"

# Every file whose source carries an Agy argv shape, with its classification.
AGY_LAUNCHERS: dict[str, tuple[str, str]] = {
    "nexus/executors/worker_registry.py": (WRAPPED_CLI_WORKER, "#1912 production adapter"),
    # scripts/bench/real_world_task_runner.py: no own launcher since #2528; its
    # agy arm runs through worker_registry.AgyWorkerAdapter (listed above).
    "scripts/ops/nexus-agy-dispatch": (WRAPPED_DISPATCH, "#2202 accept-edits runs"),
    "nexus/orchestrator/unified_mcp_gateway.py": (PLAN_ONLY, "#2202 gateway, --sandbox"),
    "scripts/ops/unified_runtime_scenarios.py": (PLAN_ONLY, "#2202 scenarios, --sandbox"),
    "nexus/services/cloud_agent_cli_adapter.py": (PLAN_ONLY, "#2202 no caller in tree"),
    "scripts/bench/agy_provider.py": (PLAN_ONLY, "#2202 bench bare arm, --sandbox"),
    "scripts/bench/experimental/model_workforce_three_arm.py": (
        PLAN_ONLY,
        "#2202 experimental bench, --sandbox",
    ),
    "nexus/research/hybrid_replication_live.py": (VIA_DISPATCHER, "#2202 hybrid replication"),
    "scripts/ops/nexus-agy-review": (VIA_DISPATCHER, "#2202 reviewer profiles"),
    "scripts/ops/nexus-dsh-workflow": (VIA_DISPATCHER, "#2202 DSH classifier"),
    "scripts/ops/nexus-hermes-continuation-controller": (VIA_DISPATCHER, "#2202 Hermes"),
    "scripts/ops/nexus-hermes-soak": (
        REVIEWED,
        "#2202 its --mode is the controller's observe/execute, not an Agy mode",
    ),
    "scripts/ops/nexus-agy-quota": (
        READ_ONLY_PROBE,
        "#2202 `agy -p /usage` quota probe: one slash command, no prompt, no edits",
    ),
    "scripts/ops/nexus-hcom-agy-safe": (
        REVIEWED,
        "#2202 Owner-attended interactive hcom session; not a headless launcher",
    ),
}


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for base in ("nexus", "scripts"):
        for path in sorted((ROOT / base).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix in {".py", ".sh", ".js"}:
                files.append(path)
            elif base == "scripts" and not path.suffix:
                try:
                    with path.open("rb") as handle:
                        if handle.read(2) == b"#!":
                            files.append(path)
                except OSError:
                    continue
    return files


def _agy_launch_sites() -> dict[str, str]:
    sites: dict[str, str] = {}
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if "agy" not in text.lower():
            continue
        joined = _JOINED.sub("", text)
        if any(marker.search(joined) for marker in _LAUNCH_MARKERS):
            sites[path.relative_to(ROOT).as_posix()] = joined
    return sites


def test_every_production_agy_launcher_is_wrapped_or_plan_only():
    sites = _agy_launch_sites()
    # A new launcher must be classified here; a removed one must be dropped.
    assert sorted(sites) == sorted(AGY_LAUNCHERS)
    assert all(re.search(r"#\d+", reason) for _, reason in AGY_LAUNCHERS.values())
    for relative, (kind, _reason) in AGY_LAUNCHERS.items():
        text = sites[relative]
        modes = re.findall(r'"--mode",\s*"([\w-]+)"', text)
        if kind == WRAPPED_CLI_WORKER:
            for needle in (
                "build_seatbelt_profile(",
                "seatbelt_profile=",
                "sweep_descendants_on_exit=True",
                "exact_env=True",
                "materialize_run_home(",
            ):
                assert needle in text, (relative, needle)
        elif kind == WRAPPED_DISPATCH:
            for needle in (
                "write_boundary.wrap_argv(argv)",
                "write_boundary.before_launch()",
                "write_boundary.after_launch(",
                "write_boundary.sweep()",
                'raise RuntimeError("AGY_WRITE_BOUNDARY_REQUIRED")',
                "prepare_accept_edits_boundary(",
            ):
                assert needle in text, (relative, needle)
            # exactly one raw agy Popen site, and it launches launch_argv
            # (#2314: the launch sits in a try that tears down the log relay)
            assert len(re.findall(r"subprocess\.Popen\(\n +launch_argv,", text)) == 1
        elif kind == PLAN_ONLY:
            assert modes and set(modes) == {"plan"}, (relative, modes)
            assert "accept-edits" not in text, relative
            assert not re.search(r'"--mode",\s*[A-Za-z_][\w.]*\s*[,\]]', text), relative
        elif kind == VIA_DISPATCHER:
            assert "nexus-agy-dispatch" in text, relative
        elif kind == READ_ONLY_PROBE:
            # the only Agy argv is the print-mode /usage slash command
            launches = re.findall(r'\[\s*[A-Za-z_][\w.]*,\s*"(?:-p|--print)",\s*"([^"]*)"\]', text)
            assert launches == ["/usage"], (relative, launches)
            assert "accept-edits" not in text and '"--mode"' not in text, relative
            assert '"--print-timeout"' not in text and '"--new-project"' not in text, relative


def test_launcher_scan_detects_new_raw_agy_argv():
    for sample in (
        'cmd = [agy, "--mode", "accept-" "edits", "--print", p]',
        'proc = subprocess.Popen([agy_binary, "-p", prompt], env=env)',
        'subprocess.run(["agy", "-p", prompt])',
        "proc = subprocess.Popen([self.agy, '--print', prompt])".replace("'", '"'),
    ):
        joined = _JOINED.sub("", sample)
        assert any(marker.search(joined) for marker in _LAUNCH_MARKERS), sample
    claude = _JOINED.sub("", 'return [self.claude_bin, "-p", "--model", m]')
    assert not any(marker.search(claude) for marker in _LAUNCH_MARKERS)


def test_gateway_compiles_plan_sandbox_only():
    from nexus.orchestrator.unified_mcp_gateway import _compile_agy_command

    argv = _compile_agy_command(
        executable="/bin/agy", model="gemini-3.8-flash", prompt="p", explicit_effort="low"
    )
    assert argv[1:4] == ["--mode", "plan", "--sandbox"]
    assert "accept-edits" not in argv


def test_scenarios_agy_invoker_is_plan_sandbox_only():
    text = (ROOT / "scripts" / "ops" / "unified_runtime_scenarios.py").read_text(encoding="utf-8")
    assert re.search(r'"--mode",\s*"plan",\s*"--sandbox"', text)


def test_boundary_profile_denies_reading_the_leased_pool_home_credentials(tmp_path, seatbelt_on):
    home = _source_home(tmp_path)
    target = _target(tmp_path)
    boundary = boundary_mod.prepare_accept_edits_boundary(
        source_env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        target=target,
        extra_writable_files=[],
        extra_writable_roots=[],
    )
    try:
        assert f'(subpath "{admission._sbpl_path(home / ".ssh")}")' in boundary.profile
        assert f'(subpath "{admission._sbpl_path(home / ".config" / "gh")}")' in boundary.profile
        # no credential read-deny is emitted under the run HOME (it lives in the run root)
        assert f'(subpath "{admission._sbpl_path(boundary.run_home / ".ssh")}")' not in (
            boundary.profile
        )
    finally:
        boundary.cleanup()


def test_boundary_refuses_a_target_inside_a_credential_path(tmp_path, seatbelt_on):
    home = _source_home(tmp_path)
    target = home / ".codex" / "worktrees" / "repo"
    target.mkdir(parents=True)
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="target_inside_credential_path"):
        boundary_mod.prepare_accept_edits_boundary(
            source_env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
            target=target,
            extra_writable_files=[],
            extra_writable_roots=[],
        )


# ---------------------------------------------------------------------------
# #2470 item 3: a BaseException leaving an attempt keeps the sweep verdict
# ---------------------------------------------------------------------------


def _signal_after_launch(spy, exc_factory):
    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        spy.launch(write_boundary)
        raise exc_factory()

    return runner


@pytest.mark.parametrize(
    "exc_factory",
    [lambda: dispatch._SupervisorSignalError(15), KeyboardInterrupt],
    ids=["supervisor-signal", "keyboard-interrupt"],
)
@pytest.mark.parametrize("clean", [False, True])
def test_base_exception_records_the_sweep_result_through_the_hook(
    tmp_path, monkeypatch, seatbelt_on, exc_factory, clean
):
    spy = _SweepSpy(monkeypatch, clean=clean)
    events: list[dict] = []
    target = _target(tmp_path)
    expected = type(exc_factory())
    with pytest.raises(expected):
        dispatch.dispatch_run(
            prompt="edit",
            cwd=str(target),
            mode="accept-edits",
            write_paths=[str(target / "a.py")],
            coordinator=_Coordinator(_source_home(tmp_path)),
            run_agy_fn=_signal_after_launch(spy, exc_factory),
            operation_hook=events.append,
        )
    recorded = [e["descendant_sweep_clean"] for e in events if "descendant_sweep_clean" in e]
    assert recorded == [None, clean]  # pending marker before launch, then the verdict
    # swept exactly once: cleanup() reused the recorded result
    assert spy.work == ["tracker.stop", "tagged"]


def test_base_exception_with_an_interrupted_sweep_records_unclean(
    tmp_path, monkeypatch, seatbelt_on
):
    def interrupted_sweep(_boundary):
        raise dispatch._SupervisorSignalError(15)  # a second signal mid-sweep

    monkeypatch.setattr(boundary_mod.AgyDispatchBoundary, "sweep", interrupted_sweep)
    monkeypatch.setattr(boundary_mod.AgyDispatchBoundary, "cleanup", lambda _b: None)
    events: list[dict] = []
    target = _target(tmp_path)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        write_boundary._launched = True
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):  # the original exception survives
        dispatch.dispatch_run(
            prompt="edit",
            cwd=str(target),
            mode="accept-edits",
            write_paths=[str(target / "a.py")],
            coordinator=_Coordinator(_source_home(tmp_path)),
            run_agy_fn=runner,
            operation_hook=events.append,
        )
    recorded = [e["descendant_sweep_clean"] for e in events if "descendant_sweep_clean" in e]
    assert recorded == [None, False]


def test_normal_attempt_replaces_the_pending_marker_with_the_verdict(
    tmp_path, monkeypatch, seatbelt_on
):
    _SweepSpy(monkeypatch, clean=True)
    events: list[dict] = []
    target = _target(tmp_path)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        return 0, '{"status": "SUCCESS", "response": "ok"}', "", False, 5

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=_Coordinator(_source_home(tmp_path)),
        run_agy_fn=runner,
        operation_hook=events.append,
    )
    assert isinstance(code, int)
    recorded = [e["descendant_sweep_clean"] for e in events if "descendant_sweep_clean" in e]
    assert recorded == [None, True]


def _background_operation(tmp_path, monkeypatch, fake_dispatch, *, provider_alive_after=False):
    root = tmp_path / "ops"
    journal = dispatch.AgyOperationJournal(root)
    operation_id = dispatch.new_operation_id()
    prompt_path = journal.prompt_path(operation_id)
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    dispatch._write_private_prompt(prompt_path, "sweep verdict probe")
    monkeypatch.setattr(dispatch, "_runtime_revision", lambda: "a" * 40)
    monkeypatch.setattr(dispatch, "dispatch_run", fake_dispatch)
    stopped: list = []
    monkeypatch.setattr(
        dispatch._agy_operation_journal,
        "_stop_operation_processes",
        lambda *_a, **_k: stopped.append(1) or (True, provider_alive_after, False),
    )
    kwargs = dict(
        operation_id=operation_id,
        prompt_file=str(prompt_path),
        cwd=str(tmp_path),
        mode="accept-edits",
        model="gemini-test",
        effort="medium",
        timeout=30,
        max_calls=1,
        pool_wait_timeout=1.0,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=root,
        heartbeat_interval=0.01,
    )
    return journal, operation_id, kwargs


def _interrupted(sweep_clean, exc):
    def fake_dispatch(**kwargs):
        hook = kwargs["operation_hook"]
        hook({"phase": "EXECUTING", "attempts": 1, "rotations": 0, "provider_pid": 999999})
        if sweep_clean is not None:
            hook({"descendant_sweep_clean": sweep_clean, "descendant_sweep_attempt": 1})
        raise exc

    return fake_dispatch


@pytest.mark.parametrize(
    "exc,prefix",
    [
        (dispatch._SupervisorSignalError(15), "SUPERVISOR_SIGNAL"),
        (KeyboardInterrupt(), "WRAPPER_EXCEPTION"),
    ],
    ids=["sigterm", "keyboard-interrupt"],
)
def test_signal_with_unclean_sweep_terminalizes_as_reconcile_required(
    tmp_path, monkeypatch, exc, prefix
):
    journal, operation_id, kwargs = _background_operation(
        tmp_path, monkeypatch, _interrupted(False, exc)
    )
    with pytest.raises(type(exc)):
        dispatch._run_background_operation(**kwargs)
    record = journal.read(operation_id)
    assert record["descendant_sweep_clean"] is False
    assert record["status"] == "RUNNING"
    assert record["phase"] == "RECONCILE_REQUIRED"
    assert record["finished_at"] is None
    assert record["failure_kind"].startswith(prefix)
    reconciliation = record["reconciliation"]
    assert reconciliation["result"] == f"{prefix}_DESCENDANT_SWEEP_UNCLEAN"
    assert reconciliation["descendant_sweep_clean"] is False
    # never "provider gone": that would let lease cleanup run
    assert reconciliation["provider_alive_after"] is None
    assert reconciliation["retry_permitted"] is False
    assert dispatch._cleanup_reconciled_lease(record) == {"result": "NOT_SAFE_TO_CLEAN"}


def test_signal_with_unclean_sweep_and_live_provider_keeps_the_orphan_result(tmp_path, monkeypatch):
    journal, operation_id, kwargs = _background_operation(
        tmp_path,
        monkeypatch,
        _interrupted(False, dispatch._SupervisorSignalError(15)),
        provider_alive_after=True,
    )
    with pytest.raises(dispatch._SupervisorSignalError):
        dispatch._run_background_operation(**kwargs)
    record = journal.read(operation_id)
    assert record["phase"] == "RECONCILE_REQUIRED"
    assert record["reconciliation"]["result"] == "SUPERVISOR_SIGNAL_ORPHAN_PROVIDER_STILL_RUNNING"
    assert record["reconciliation"]["descendant_sweep_clean"] is False


@pytest.mark.parametrize("sweep_clean", [True, None], ids=["clean-sweep", "no-boundary"])
def test_signal_with_clean_or_absent_sweep_keeps_the_terminal_outcome(
    tmp_path, monkeypatch, sweep_clean
):
    journal, operation_id, kwargs = _background_operation(
        tmp_path, monkeypatch, _interrupted(sweep_clean, dispatch._SupervisorSignalError(15))
    )
    with pytest.raises(dispatch._SupervisorSignalError):
        dispatch._run_background_operation(**kwargs)
    record = journal.read(operation_id)
    assert record["status"] == "OUTCOME_UNKNOWN"
    assert record["phase"] == "TERMINAL"
    assert record["failure_kind"] == "SUPERVISOR_SIGNAL:SIGTERM"
    assert record["reconciliation"]["result"] == "SUPERVISOR_SIGNAL_WITH_UNKNOWN_PROVIDER_EFFECT"
    assert record.get("descendant_sweep_clean") is sweep_clean


def test_normal_path_completes_without_a_sweep_verdict(tmp_path, monkeypatch):
    def fake_dispatch(**kwargs):
        kwargs["operation_hook"]({"phase": "EXECUTING", "attempts": 1, "rotations": 0})
        return 0

    journal, operation_id, kwargs = _background_operation(tmp_path, monkeypatch, fake_dispatch)
    assert dispatch._run_background_operation(**kwargs) == 0
    record = journal.read(operation_id)
    assert record["status"] == "COMPLETED"
    assert record["phase"] == "TERMINAL"
    assert "descendant_sweep_clean" not in record


# ---------------------------------------------------------------------------
# #2470 round 2: end-to-end through the real dispatch_run and completion path
# ---------------------------------------------------------------------------


def _background_accept_edits(tmp_path, monkeypatch, runner):
    import functools

    target = _target(tmp_path)
    real = functools.partial(
        dispatch.dispatch_run,
        coordinator=_Coordinator(_source_home(tmp_path)),
        run_agy_fn=runner,
    )
    journal, operation_id, kwargs = _background_operation(tmp_path, monkeypatch, real)
    kwargs.update(cwd=str(target), write_paths=[str(target / "a.py")])
    return journal, operation_id, kwargs


def test_unclean_sweep_without_exception_is_reconcile_required_not_terminal(
    tmp_path, monkeypatch, seatbelt_on
):
    """An env-cleared double fork the sweep could only report: dispatch returns normally."""
    spy = _SweepSpy(monkeypatch, clean=False)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        spy.launch(write_boundary)
        assert write_boundary.sweep() is False  # run_agy's own post-exit sweep
        return 0, "", f"\n{dispatch.DESCENDANT_SWEEP_FAILED_MARKER}\n", False, 5

    journal, operation_id, kwargs = _background_accept_edits(tmp_path, monkeypatch, runner)
    code = dispatch._run_background_operation(**kwargs)
    assert code != 0
    record = journal.read(operation_id)
    assert record["status"] == "RUNNING"
    assert record["phase"] == "RECONCILE_REQUIRED"
    assert record["finished_at"] is None
    assert record["failure_kind"] == "AGY_DESCENDANT_SWEEP_FAILED"
    assert record["descendant_sweep_clean"] is False
    reconciliation = record["reconciliation"]
    assert reconciliation["result"] == "DESCENDANT_SWEEP_UNCLEAN_AFTER_DISPATCH"
    assert reconciliation["provider_alive_after"] is None
    assert reconciliation["descendant_sweep_clean"] is False
    assert reconciliation["retry_permitted"] is False
    assert dispatch._cleanup_reconciled_lease(record) == {"result": "NOT_SAFE_TO_CLEAN"}


def test_clean_sweep_without_exception_terminalizes_as_before(tmp_path, monkeypatch, seatbelt_on):
    spy = _SweepSpy(monkeypatch, clean=True)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        spy.launch(write_boundary)
        write_boundary.sweep()
        return 1, "", "provider failed\n", False, 5

    journal, operation_id, kwargs = _background_accept_edits(tmp_path, monkeypatch, runner)
    dispatch._run_background_operation(**kwargs)
    record = journal.read(operation_id)
    assert record["phase"] == "TERMINAL"
    assert record["descendant_sweep_clean"] is True


def test_foreground_unclean_sweep_envelope_says_reconcile_required(
    tmp_path, monkeypatch, seatbelt_on, capsys
):
    spy = _SweepSpy(monkeypatch, clean=False)
    target = _target(tmp_path)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        spy.launch(write_boundary)
        write_boundary.sweep()
        return 0, "", f"\n{dispatch.DESCENDANT_SWEEP_FAILED_MARKER}\n", False, 5

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=_Coordinator(_source_home(tmp_path)),
        run_agy_fn=runner,
    )
    metas = _metas(capsys.readouterr().err)
    assert code != 0
    assert metas[-1]["status"] == "failed"
    assert metas[-1]["failure_kind"] == "AGY_DESCENDANT_SWEEP_FAILED"
    assert metas[-1]["reconciliation_required"] is True


def test_failing_verdict_hook_keeps_the_pending_marker_and_the_original_exception(
    tmp_path, monkeypatch, seatbelt_on
):
    spy = _SweepSpy(monkeypatch, clean=True)
    events: list[dict] = []

    def hook(event):
        if event.get("descendant_sweep_clean") is not None:
            raise RuntimeError("journal write failed")
        events.append(event)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        spy.launch(write_boundary)
        raise KeyboardInterrupt

    target = _target(tmp_path)
    with pytest.raises(KeyboardInterrupt):
        dispatch.dispatch_run(
            prompt="edit",
            cwd=str(target),
            mode="accept-edits",
            write_paths=[str(target / "a.py")],
            coordinator=_Coordinator(_source_home(tmp_path)),
            run_agy_fn=runner,
            operation_hook=hook,
        )
    recorded = [e["descendant_sweep_clean"] for e in events if "descendant_sweep_clean" in e]
    assert recorded == [None]
    assert dispatch._descendant_sweep_unproven({"descendant_sweep_clean": None}) is True
    assert dispatch._descendant_sweep_unproven({}) is False


def test_second_signal_during_the_verdict_heartbeat_fails_closed(
    tmp_path, monkeypatch, seatbelt_on
):
    """SIGTERM mid-run, then a second SIGTERM while the verdict is being journaled."""
    import threading

    spy = _SweepSpy(monkeypatch, clean=True)  # even a clean sweep must not read as clean
    real_heartbeat = dispatch.AgyOperationJournal.heartbeat
    fired: list[bool] = []

    def heartbeat(self, operation_id, **changes):
        main = threading.current_thread() is threading.main_thread()
        if main and changes.get("descendant_sweep_clean") is not None and not fired:
            fired.append(True)
            raise dispatch._SupervisorSignalError(15)
        if not main:
            changes.pop("descendant_sweep_clean", None)  # only the main thread's write counts
        return real_heartbeat(self, operation_id, **changes)

    monkeypatch.setattr(dispatch.AgyOperationJournal, "heartbeat", heartbeat)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        spy.launch(write_boundary)
        raise dispatch._SupervisorSignalError(15)

    journal, operation_id, kwargs = _background_accept_edits(tmp_path, monkeypatch, runner)
    with pytest.raises(dispatch._SupervisorSignalError):
        dispatch._run_background_operation(**kwargs)
    assert fired == [True]
    record = journal.read(operation_id)
    assert record["descendant_sweep_clean"] is None  # the pending marker survived
    assert record["status"] == "RUNNING"
    assert record["phase"] == "RECONCILE_REQUIRED"
    assert record["reconciliation"]["result"] == "SUPERVISOR_SIGNAL_DESCENDANT_SWEEP_UNCLEAN"
    assert record["reconciliation"]["provider_alive_after"] is None
    assert dispatch._cleanup_reconciled_lease(record) == {"result": "NOT_SAFE_TO_CLEAN"}


def test_pending_marker_alone_makes_the_signal_guard_reconcile(tmp_path, monkeypatch):
    def pending_then_signal(**kw):
        kw["operation_hook"]({"phase": "EXECUTING", "attempts": 1, "rotations": 0})
        kw["operation_hook"]({"descendant_sweep_clean": None})
        raise dispatch._SupervisorSignalError(15)

    journal, operation_id, kwargs = _background_operation(
        tmp_path, monkeypatch, pending_then_signal
    )
    with pytest.raises(dispatch._SupervisorSignalError):
        dispatch._run_background_operation(**kwargs)
    record = journal.read(operation_id)
    assert record["phase"] == "RECONCILE_REQUIRED"
    assert record["reconciliation"]["result"] == "SUPERVISOR_SIGNAL_DESCENDANT_SWEEP_UNCLEAN"


# ---------------------------------------------------------------------------
# #2470 round 3: a stale heartbeat cannot resurrect an earlier attempt's verdict
# ---------------------------------------------------------------------------


class _CleanBoundary:
    def sweep(self):
        return True


def test_stale_heartbeat_after_next_pending_marker_cannot_prove_the_sweep(tmp_path, monkeypatch):
    """Attempt 1 records True; a heartbeat snapshot taken before attempt 2's pending
    marker is written after it; attempt 2's verdict write fails. Must reconcile."""
    import threading

    real_heartbeat = dispatch.AgyOperationJournal.heartbeat
    hold = threading.Event()
    pending2_written = threading.Event()
    stale_written = threading.Event()
    held_changes: list[dict] = []

    def heartbeat(self, operation_id, **changes):
        main = threading.current_thread() is threading.main_thread()
        if not main and hold.is_set() and not stale_written.is_set():
            # This periodic snapshot was taken before attempt 2's marker.
            pending2_written.wait(timeout=10)
            held_changes.append(dict(changes))
            try:
                return real_heartbeat(self, operation_id, **changes)
            finally:
                stale_written.set()
        if (
            main
            and changes.get("descendant_sweep_attempt") == 2
            and changes.get("descendant_sweep_clean") is not None
        ):
            raise dispatch._SupervisorSignalError(15)  # the verdict write is interrupted
        return real_heartbeat(self, operation_id, **changes)

    monkeypatch.setattr(dispatch.AgyOperationJournal, "heartbeat", heartbeat)

    def racing_dispatch(**kw):
        hook = kw["operation_hook"]
        hook({"phase": "EXECUTING", "attempts": 1, "rotations": 0})
        hook({"descendant_sweep_clean": None, "descendant_sweep_attempt": 1})
        hook({"descendant_sweep_clean": True, "descendant_sweep_attempt": 1})
        hold.set()  # the next periodic heartbeat snapshot is now "stale"
        time.sleep(1.5)  # let the heartbeat thread take that snapshot and block
        hook({"phase": "EXECUTING", "attempts": 2, "rotations": 1})
        hook({"descendant_sweep_clean": None, "descendant_sweep_attempt": 2})
        pending2_written.set()
        assert stale_written.wait(timeout=10)
        dispatch._record_descendant_sweep(hook, _CleanBoundary(), 2)  # write fails
        raise dispatch._SupervisorSignalError(15)

    journal, operation_id, kwargs = _background_operation(tmp_path, monkeypatch, racing_dispatch)
    with pytest.raises(dispatch._SupervisorSignalError):
        dispatch._run_background_operation(**kwargs)
    assert held_changes, "the stale heartbeat write never happened"
    assert all("descendant_sweep_clean" not in c for c in held_changes)
    record = journal.read(operation_id)
    assert record["descendant_sweep_clean"] is None
    assert record["descendant_sweep_attempt"] == 2
    assert record["status"] == "RUNNING"
    assert record["phase"] == "RECONCILE_REQUIRED"
    assert record["reconciliation"]["result"] == "SUPERVISOR_SIGNAL_DESCENDANT_SWEEP_UNCLEAN"
    assert dispatch._cleanup_reconciled_lease(record) == {"result": "NOT_SAFE_TO_CLEAN"}


@pytest.mark.parametrize(
    "record,unproven",
    [
        ({}, False),
        ({"descendant_sweep_clean": None, "descendant_sweep_attempt": 2, "attempts": 2}, True),
        ({"descendant_sweep_clean": False, "descendant_sweep_attempt": 2, "attempts": 2}, True),
        ({"descendant_sweep_clean": True, "descendant_sweep_attempt": 2, "attempts": 2}, False),
        ({"descendant_sweep_clean": True, "descendant_sweep_attempt": 1, "attempts": 2}, True),
        ({"descendant_sweep_clean": True, "attempts": 1}, True),
        ({"descendant_sweep_clean": True, "descendant_sweep_attempt": True, "attempts": 1}, True),
    ],
)
def test_sweep_verdict_counts_only_for_the_latest_attempt(record, unproven):
    assert dispatch._descendant_sweep_unproven(record) is unproven


# ---------------------------------------------------------------------------
# #2470 review: --reconcile / --finalize-no-effect keep an unproven sweep held
# ---------------------------------------------------------------------------


_REAL_CWD_SCAN = boundary_mod.cli_worker._pids_with_cwd_under


def _held_operation(tmp_path, monkeypatch):
    spy = _SweepSpy(monkeypatch, clean=False)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        spy.launch(write_boundary)
        write_boundary.sweep()
        return 0, "", f"\n{dispatch.DESCENDANT_SWEEP_FAILED_MARKER}\n", False, 5

    journal, operation_id, kwargs = _background_accept_edits(tmp_path, monkeypatch, runner)
    dispatch._run_background_operation(**kwargs)
    # The background supervisor ran in this process; a real one has exited.
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait(timeout=10)
    journal.update(operation_id, pid=gone.pid)
    return journal, operation_id, kwargs


def test_reconcile_keeps_an_unproven_sweep_reconcile_required(tmp_path, monkeypatch, seatbelt_on):
    journal, operation_id, _ = _held_operation(tmp_path, monkeypatch)
    for _ in range(2):  # repeated automatic reconciles never wash it out
        record = dispatch._reconcile_operation(journal, operation_id)
        assert record["status"] == "RUNNING"
        assert record["phase"] == "RECONCILE_REQUIRED"
        assert record["finished_at"] is None
        reconciliation = record["reconciliation"]
        assert reconciliation["result"] == "DESCENDANT_SWEEP_UNPROVEN_RECONCILE_HELD"
        assert reconciliation["provider_alive_after"] is None
        assert reconciliation["descendant_sweep_clean"] is False
        assert reconciliation["lease_cleanup"] == {"result": "NOT_SAFE_TO_CLEAN"}


def test_finalize_no_effect_refuses_an_unproven_sweep(tmp_path, monkeypatch, seatbelt_on):
    journal, operation_id, _ = _held_operation(tmp_path, monkeypatch)
    with pytest.raises(
        dispatch.AgyOperationJournalError, match="NO_EFFECT_DESCENDANT_SWEEP_UNPROVEN"
    ):
        dispatch._finalize_no_effect_operation(journal, operation_id)
    assert journal.read(operation_id)["phase"] == "RECONCILE_REQUIRED"


def test_reconcile_does_not_hold_a_live_wrapper_with_a_pending_marker(tmp_path):
    journal = dispatch.AgyOperationJournal(tmp_path / "ops")
    operation_id = dispatch.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    journal.mark_started(operation_id, pid=os.getpid())  # the wrapper is alive
    journal.heartbeat(operation_id, descendant_sweep_clean=None, descendant_sweep_attempt=1)
    record = journal.reconcile(operation_id)
    result = (record.get("reconciliation") or {}).get("result")
    assert result != "DESCENDANT_SWEEP_UNPROVEN_RECONCILE_HELD"


def test_ack_unclean_sweep_refuses_while_a_process_lives_in_the_target(
    tmp_path, monkeypatch, seatbelt_on
):
    journal, operation_id, kwargs = _held_operation(tmp_path, monkeypatch)
    target = kwargs["cwd"]
    # _SweepSpy faked the cwd scan for the run; the operator re-check is real.
    monkeypatch.setattr(boundary_mod.cli_worker, "_pids_with_cwd_under", _REAL_CWD_SCAN)
    resident = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=target,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        time.sleep(0.3)
        with pytest.raises(dispatch.AgyOperationJournalError, match="ACK_UNCLEAN_SWEEP_RESIDENTS"):
            dispatch._ack_unclean_sweep_operation(journal, operation_id)
        assert resident.poll() is None  # the ack only checks, never kills
        assert journal.read(operation_id)["descendant_sweep_clean"] is False
    finally:
        os.kill(resident.pid, 9)
        resident.wait(timeout=5)
    record = dispatch._ack_unclean_sweep_operation(journal, operation_id)
    _assert_acknowledged_not_proven(record)
    # reconcile accepts the operator ack for the latest attempt
    assert record["reconciliation"]["result"] != "DESCENDANT_SWEEP_UNPROVEN_RECONCILE_HELD"
    record = dispatch._reconcile_operation(journal, operation_id)
    assert record["reconciliation"]["result"] != "DESCENDANT_SWEEP_UNPROVEN_RECONCILE_HELD"
    _assert_acknowledged_not_proven(record)


def _assert_acknowledged_not_proven(record):
    assert record["descendant_sweep_clean"] is not True  # never proven by an ack
    ack = record["descendant_sweep_operator_ack"]
    assert ack["attempt"] == record["attempts"]
    assert ack["kind"] == "OPERATOR_ATTESTATION_NOT_PROOF"
    assert ack["operator_check"]["open_file_holders"] == []
    assert ack["operator_check"]["cwd_residents"] == []
    assert dispatch._descendant_sweep_unproven(record) is False
    # an ack for an earlier attempt would not count
    stale = {**record, "attempts": record["attempts"] + 1}
    assert dispatch._descendant_sweep_unproven(stale) is True


def test_ack_unclean_sweep_refuses_an_open_file_in_the_target_from_elsewhere(
    tmp_path, monkeypatch, seatbelt_on
):
    """An escaped writer whose cwd is elsewhere but holds a file in the target."""
    journal, operation_id, kwargs = _held_operation(tmp_path, monkeypatch)
    monkeypatch.setattr(boundary_mod.cli_worker, "_pids_with_cwd_under", _REAL_CWD_SCAN)
    victim = Path(kwargs["cwd"]) / "a.py"
    writer = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys, time; f = open(sys.argv[1], 'a'); time.sleep(60)",
            str(victim),
        ],
        cwd="/",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not victim.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        time.sleep(0.2)
        with pytest.raises(
            dispatch.AgyOperationJournalError, match=f"ACK_UNCLEAN_SWEEP_OPEN_FILES:{writer.pid}"
        ):
            dispatch._ack_unclean_sweep_operation(journal, operation_id)
        assert writer.poll() is None  # only checked, never killed
        record = journal.read(operation_id)
        assert "descendant_sweep_operator_ack" not in record
        assert record["phase"] == "RECONCILE_REQUIRED"
    finally:
        os.kill(writer.pid, 9)
        writer.wait(timeout=5)


def test_ack_unclean_sweep_refuses_when_an_unreadable_subdir_hides_a_writer(
    tmp_path, monkeypatch, seatbelt_on
):
    """A chmod-000 subdirectory makes lsof skip it; its warning must refuse the ack."""
    journal, operation_id, kwargs = _held_operation(tmp_path, monkeypatch)
    monkeypatch.setattr(boundary_mod.cli_worker, "_pids_with_cwd_under", _REAL_CWD_SCAN)
    hidden_dir = Path(kwargs["cwd"]) / "hidden"
    hidden_dir.mkdir()
    victim = hidden_dir / "hidden.log"
    writer = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys, time; f = open(sys.argv[1], 'a'); time.sleep(60)",
            str(victim),
        ],
        cwd="/",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not victim.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        time.sleep(0.2)
        hidden_dir.chmod(0)
        with pytest.raises(dispatch.AgyOperationJournalError, match="ACK_UNCLEAN_SWEEP_"):
            dispatch._ack_unclean_sweep_operation(journal, operation_id)
        record = journal.read(operation_id)
        assert "descendant_sweep_operator_ack" not in record
        assert record["phase"] == "RECONCILE_REQUIRED"
    finally:
        hidden_dir.chmod(0o755)
        os.kill(writer.pid, 9)
        writer.wait(timeout=5)


def test_ack_unclean_sweep_refuses_when_the_open_file_scan_cannot_run(
    tmp_path, monkeypatch, seatbelt_on
):
    journal, operation_id, _ = _held_operation(tmp_path, monkeypatch)
    monkeypatch.setattr(boundary_mod.cli_worker, "_pids_with_cwd_under", _REAL_CWD_SCAN)
    monkeypatch.setattr(dispatch, "_open_file_holders", lambda roots, exclude: None)
    with pytest.raises(
        dispatch.AgyOperationJournalError, match="ACK_UNCLEAN_SWEEP_SCAN_UNAVAILABLE"
    ):
        dispatch._ack_unclean_sweep_operation(journal, operation_id)
    assert "descendant_sweep_operator_ack" not in journal.read(operation_id)


def test_finalize_no_effect_accepts_the_operator_ack(tmp_path, monkeypatch, seatbelt_on):
    journal, operation_id, _ = _held_operation(tmp_path, monkeypatch)
    monkeypatch.setattr(boundary_mod.cli_worker, "_pids_with_cwd_under", _REAL_CWD_SCAN)
    dispatch._ack_unclean_sweep_operation(journal, operation_id)
    try:
        dispatch._finalize_no_effect_operation(journal, operation_id)
    except dispatch.AgyOperationJournalError as exc:
        # later, unrelated proofs may still refuse; the sweep hold does not
        assert "DESCENDANT_SWEEP" not in str(exc)


def test_ack_unclean_sweep_is_refused_when_not_needed(tmp_path, monkeypatch):
    journal, operation_id, kwargs = _background_operation(tmp_path, monkeypatch, lambda **_kw: 0)
    with pytest.raises(dispatch.AgyOperationJournalError, match="ACK_UNCLEAN_SWEEP_NOT_REQUIRED"):
        dispatch._ack_unclean_sweep_operation(journal, operation_id)
