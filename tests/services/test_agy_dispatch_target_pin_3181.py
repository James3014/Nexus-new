"""#3181: the accept-edits Agy boundary keeps its target directory's identity.

* The Seatbelt profile pins the target's (and the run root's) own entry, so a
  confined process cannot move, replace or relink the target; the protected
  entries inside it stay as they were.
* The dispatcher records the target bound by the first boundary.  A later
  attempt and the host's post-attempt git steps use that directory or refuse;
  they never resolve the requested path again.

Where Seatbelt runs (macOS) the profile tests run real ``sandbox-exec``; where
it does not, they assert that the boundary refuses to start.  No test skips.
Dispatcher tests use an unconfined stub runner (and the operation hook) to
change the target; a marker shows whether the host ran git in the replacement.
"""

from __future__ import annotations

import json
import os
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from nexus.executors import agy_dispatch_boundary as boundary_mod
from nexus.executors import agy_write_admission as admission
from nexus.executors.agy_write_admission import KEYCHAIN_NOT_APPLICABLE

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"

os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader("nexus_agy_dispatch_target_pin_3181", str(DISPATCH_PATH)).load_module()

_ORIGINAL_GIT_CONFIG = "[core]\n\trepositoryformatversion = 0\n"
_QUOTA_STDERR = (
    "error: Individual quota reached. Please upgrade your subscription to increase your "
    "limits. Resets in 83h48m12s.\n"
)


def _identity(path: Path) -> tuple[int, int]:
    info = os.stat(path, follow_symlinks=False)
    return info.st_dev, info.st_ino


def _git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, capture_output=True)


def _repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git("init", "-q", str(path))
    _git("-C", str(path), "config", "user.name", "Nexus Test")
    _git("-C", str(path), "config", "user.email", "nexus-test@example.invalid")
    return path


def _planted_repo(path: Path, marker: Path) -> Path:
    """A repository whose fsmonitor hook writes ``marker`` when git runs in it."""
    _repo(path)
    hook = path.parent / f"{path.name}-fsmonitor.sh"
    hook.write_text(f'#!/bin/sh\ntouch "{marker}"\n', encoding="utf-8")
    hook.chmod(0o755)
    _git("-C", str(path), "config", "core.fsmonitor", str(hook))
    return path


def _no_keychain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        boundary_mod, "_prepare_run_home_keychain", lambda run_home: KEYCHAIN_NOT_APPLICABLE
    )


def _lease_home(tmp_path: Path) -> Path:
    home = (tmp_path / "lease-home").resolve()
    home.mkdir()
    return home


def _deny_write_block(profile: str) -> list[str]:
    lines = profile.splitlines()
    start = lines.index("(deny file-write*")
    end = lines.index(")", start)
    return lines[start + 1 : end]


# ---------------------------------------------------------------------------
# profile builder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("with_run_home", [False, True])
def test_profile_pins_the_target_and_run_root_entries(tmp_path, with_run_home):
    target = (tmp_path / "work").resolve()
    run_root = (tmp_path / "run").resolve()
    target.mkdir()
    run_root.mkdir()
    profile = admission.build_seatbelt_profile(
        run_root=run_root,
        writable_target=target,
        run_home=run_root / "home" if with_run_home else None,
        source_home=_lease_home(tmp_path),
    )
    denied = _deny_write_block(profile)
    assert f'  (literal "{target}")' in denied
    assert f'  (literal "{run_root}")' in denied
    assert len(denied) == len(set(denied))


def _sandbox_run(profile_path: Path, script: str, *args: Path, cwd: Path, env=None):
    return subprocess.run(
        [admission.SANDBOX_EXEC_PATH, "-f", str(profile_path), "/bin/sh", "-c", script, "sh"]
        + [str(arg) for arg in args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def test_builder_roots_cannot_be_moved_under_real_seatbelt(tmp_path):
    """The shared builder (also the worker adapters' profile) without a run HOME."""
    target = (tmp_path / "work").resolve()
    run_root = (tmp_path / "run").resolve()
    (target / ".git").mkdir(parents=True)
    run_root.mkdir()
    profile = admission.build_seatbelt_profile(
        run_root=run_root, writable_target=target, source_home=_lease_home(tmp_path)
    )
    if not admission.seatbelt_available():
        # No OS barrier here: the dispatcher boundary refuses to start at all
        # (see the boundary tests below); the profile still pins both entries.
        assert f'  (literal "{target}")' in _deny_write_block(profile)
        assert f'  (literal "{run_root}")' in _deny_write_block(profile)
        return
    profile_path = tmp_path / "profile.sb"
    profile_path.write_text(profile, encoding="utf-8")
    before = {path: _identity(path) for path in (target, run_root)}
    for root in (target, run_root):
        moved = _sandbox_run(profile_path, 'mv "$1" "$2"', root, run_root / "x", cwd=tmp_path)
        assert moved.returncode != 0, moved
    inside = _sandbox_run(profile_path, 'printf ok > "$1/a.py"', target, cwd=tmp_path)
    assert inside.returncode == 0, inside
    assert {path: _identity(path) for path in (target, run_root)} == before


# ---------------------------------------------------------------------------
# the dispatcher boundary under real Seatbelt
# ---------------------------------------------------------------------------

_MOVE_OUT_SCRIPTS = {
    # move the target out, write its .git under the new name, move it back
    "move_back": (
        'mv "$1" "$TMPDIR/moved" || exit 3; '
        'printf planted > "$TMPDIR/moved/.git/config"; '
        'mv "$TMPDIR/moved" "$1"'
    ),
    # move the target out and leave a fresh directory with a planted .git
    "replace": (
        'mv "$1" "$TMPDIR/moved" || exit 3; mkdir -p "$1/.git" && printf planted > "$1/.git/config"'
    ),
    # move the target out and leave a link to another directory at the path
    "link": ('mv "$1" "$TMPDIR/moved" || exit 3; ln -s "$2" "$1"'),
}


@pytest.mark.parametrize("variant", sorted(_MOVE_OUT_SCRIPTS))
def test_target_cannot_be_moved_out_under_real_seatbelt(tmp_path, monkeypatch, variant):
    _no_keychain(monkeypatch)
    target = (tmp_path / "work").resolve()
    (target / ".git").mkdir(parents=True)
    (target / ".git" / "config").write_text(_ORIGINAL_GIT_CONFIG, encoding="utf-8")
    elsewhere = (tmp_path / "elsewhere").resolve()
    elsewhere.mkdir()
    before = _identity(target)
    source_env = {"HOME": str(_lease_home(tmp_path)), "PATH": "/usr/bin:/bin"}
    if not admission.seatbelt_available():
        with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="seatbelt_unavailable"):
            boundary_mod.prepare_accept_edits_boundary(source_env=source_env, target=target)
        return
    boundary = boundary_mod.prepare_accept_edits_boundary(source_env=source_env, target=target)
    try:
        assert boundary.target_pin == boundary_mod.TargetPin(target, before)
        attack = subprocess.run(
            boundary.wrap_argv([
                "/bin/sh",
                "-c",
                _MOVE_OUT_SCRIPTS[variant],
                "sh",
                str(target),
                str(elsewhere),
            ]),
            cwd=target,
            env=boundary.env,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        assert attack.returncode == 3, attack
        assert not (boundary.run_tmp / "moved").exists()
        assert boundary_mod.target_pin_intact(boundary.target_pin)
        # Ordinary edits inside the target still work.
        edit = subprocess.run(
            boundary.wrap_argv(["/bin/sh", "-c", 'printf ok > "$1/a.py"', "sh", str(target)]),
            cwd=target,
            env=boundary.env,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        assert edit.returncode == 0, edit
    finally:
        boundary.cleanup()
    assert _identity(target) == before
    assert (target / ".git" / "config").read_text(encoding="utf-8") == _ORIGINAL_GIT_CONFIG
    assert (target / "a.py").read_text(encoding="utf-8") == "ok"
    assert sorted(os.listdir(elsewhere)) == []


# ---------------------------------------------------------------------------
# retry binding (no sandbox-exec runs here)
# ---------------------------------------------------------------------------


@pytest.fixture
def seatbelt_on(monkeypatch):
    """Let the boundary be prepared off macOS; nothing here runs sandbox-exec."""
    if not admission.seatbelt_available():
        monkeypatch.setattr(boundary_mod, "seatbelt_available", lambda: True)
    _no_keychain(monkeypatch)


def _change_target(target: Path, elsewhere: Path, kind: str) -> None:
    target.rename(target.parent / "moved-away")
    if kind == "replaced":
        target.mkdir()
    elif kind == "link":
        target.symlink_to(elsewhere, target_is_directory=True)


@pytest.mark.parametrize("kind", ["replaced", "link", "gone"])
def test_retry_refuses_a_target_whose_identity_changed(tmp_path, seatbelt_on, kind):
    target = (tmp_path / "work").resolve()
    target.mkdir()
    elsewhere = (tmp_path / "elsewhere").resolve()
    elsewhere.mkdir()
    source_env = {"HOME": str(_lease_home(tmp_path)), "PATH": "/usr/bin:/bin"}
    first = boundary_mod.prepare_accept_edits_boundary(source_env=source_env, target=target)
    first.cleanup()
    pin = first.target_pin
    assert pin == boundary_mod.TargetPin(target, _identity(target))

    again = boundary_mod.prepare_accept_edits_boundary(
        source_env=source_env, target=target, pinned_target=pin
    )
    again.cleanup()
    assert again.target == target and again.target_pin == pin

    _change_target(target, elsewhere, kind)
    assert not boundary_mod.target_pin_intact(pin)
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="target_replaced"):
        boundary_mod.prepare_accept_edits_boundary(
            source_env=source_env, target=target, pinned_target=pin
        )


def test_a_pin_for_another_path_is_refused(tmp_path, seatbelt_on):
    target = (tmp_path / "work").resolve()
    other = (tmp_path / "other").resolve()
    target.mkdir()
    other.mkdir()
    source_env = {"HOME": str(_lease_home(tmp_path)), "PATH": "/usr/bin:/bin"}
    pin = boundary_mod.TargetPin(other, _identity(other))
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="target_replaced"):
        boundary_mod.prepare_accept_edits_boundary(
            source_env=source_env, target=target, pinned_target=pin
        )


# ---------------------------------------------------------------------------
# the dispatcher
# ---------------------------------------------------------------------------


class _Claim:
    def __init__(self, home: Path) -> None:
        self.account_alias_hash = "pin"
        self.lease_id_hash = "lease-pin"
        self.internal_id = "pin-account"
        self.lease = type(
            "Lease",
            (),
            {"execution_env": {"HOME": str(home), "PATH": "/usr/bin:/bin"}},
        )()
        self.released = False

    def release(self) -> None:
        self.released = True


class _RotatingCoordinator:
    def __init__(self, home: Path) -> None:
        self.claim = _Claim(home)
        self.rotated: list = []

    def acquire_claim(self, **_kwargs):
        return self.claim

    def rotate_claim(self, *, current_claim, failure_kind, **_kwargs):
        self.rotated.append(failure_kind)
        return self.claim

    def retire_failed_claim(self, claim, kind, **_kwargs):
        pass


def _metas(err: str) -> list[dict]:
    prefix = "NEXUS_AGY_DISPATCH "
    return [json.loads(line[len(prefix) :]) for line in err.splitlines() if line.startswith(prefix)]


def _dispatch_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = _lease_home(tmp_path)
    target = _repo((tmp_path / "work").resolve())
    ops = (tmp_path / "ops").resolve()
    ops.mkdir()
    log = ops / "agy.log"
    log.write_text("", encoding="utf-8")
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    monkeypatch.setenv("NEXUS_AGY_MAX_ACCOUNT_FAILOVERS", "3")
    monkeypatch.setattr(dispatch, "OPERATION_ROOT", ops)
    return _RotatingCoordinator(home), target


def _replace_with_planted(target: Path, marker: Path, kind: str) -> None:
    target.rename(target.parent / "moved-away")
    if kind == "replaced":
        _planted_repo(target, marker)
    else:
        planted = _planted_repo(target.parent / "planted", marker)
        target.symlink_to(planted, target_is_directory=True)


@pytest.mark.parametrize("kind", ["replaced", "link"])
def test_attempt_that_replaces_the_target_ends_without_host_git_or_retry(
    tmp_path, monkeypatch, seatbelt_on, capsys, kind
):
    coordinator, target = _dispatch_env(tmp_path, monkeypatch)
    marker = tmp_path / "host-ran-git-in-replacement"
    calls = []

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        calls.append(write_boundary.target)
        _replace_with_planted(target, marker, kind)
        return 1, "", _QUOTA_STDERR, False, 1

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=coordinator,
        run_agy_fn=runner,
    )
    metas = _metas(capsys.readouterr().err)
    assert code != 0
    assert len(calls) == 1
    assert metas[-1]["status"] == "failed"
    assert metas[-1]["failure_kind"] == dispatch.AGY_TARGET_REPLACED
    assert metas[-1]["reconciliation_required"] is True
    assert coordinator.rotated == []
    assert not marker.exists()


@pytest.mark.parametrize("kind", ["replaced", "link"])
def test_retry_after_the_target_changed_between_attempts_is_refused(
    tmp_path, monkeypatch, seatbelt_on, capsys, kind
):
    coordinator, target = _dispatch_env(tmp_path, monkeypatch)
    marker = tmp_path / "host-ran-git-in-replacement"
    calls = []

    def hook(event):
        if event.get("phase") == "EXECUTING" and event.get("attempts") == 2:
            _replace_with_planted(target, marker, kind)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        calls.append(write_boundary.target)
        return 1, "", _QUOTA_STDERR, False, 1

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=coordinator,
        run_agy_fn=runner,
        operation_hook=hook,
    )
    metas = _metas(capsys.readouterr().err)
    assert len(calls) == 1
    assert code == 64
    assert metas[-1]["status"] == "invalid_contract"
    assert metas[-1]["failure_kind"].endswith(":target_replaced")
    assert not marker.exists()


# ---------------------------------------------------------------------------
# host reads are observed directly (the fsmonitor marker above cannot fire:
# the journal runs git through the hardened runner)
# ---------------------------------------------------------------------------


def _watch_host_reads(monkeypatch: pytest.MonkeyPatch, original: Path) -> list[str]:
    """Record every journal git entry point called outside the original directory."""
    journal = dispatch.direct_operation_journal
    original_identity = _identity(original)
    seen: list[str] = []

    def wrap(name: str):
        real = getattr(journal, name)

        def inner(cwd, *args, **kwargs):
            try:
                same = _identity(Path(os.path.realpath(cwd))) == original_identity
            except OSError:
                same = False
            if not same:
                seen.append(name)
            return real(cwd, *args, **kwargs)

        return inner

    for name in ("capture_source_baseline", "observed_changed_paths_since"):
        monkeypatch.setattr(journal, name, wrap(name))
    return seen


@pytest.mark.parametrize("kind", ["replaced", "link"])
def test_no_host_read_runs_in_a_target_replaced_during_the_attempt(
    tmp_path, monkeypatch, seatbelt_on, capsys, kind
):
    coordinator, target = _dispatch_env(tmp_path, monkeypatch)
    marker = tmp_path / "unused-marker"
    seen = _watch_host_reads(monkeypatch, target)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        _replace_with_planted(target, marker, kind)
        return 1, "", _QUOTA_STDERR, False, 1

    dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=coordinator,
        run_agy_fn=runner,
    )
    capsys.readouterr()
    assert seen == []


@pytest.mark.parametrize("kind", ["replaced", "link"])
def test_no_host_read_runs_before_an_attempt_on_a_target_replaced_between_attempts(
    tmp_path, monkeypatch, seatbelt_on, capsys, kind
):
    coordinator, target = _dispatch_env(tmp_path, monkeypatch)
    marker = tmp_path / "unused-marker"
    seen = _watch_host_reads(monkeypatch, target)

    def hook(event):
        if event.get("phase") == "EXECUTING" and event.get("attempts") == 2:
            _replace_with_planted(target, marker, kind)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        return 1, "", _QUOTA_STDERR, False, 1

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=coordinator,
        run_agy_fn=runner,
        operation_hook=hook,
    )
    metas = _metas(capsys.readouterr().err)
    assert code == 64
    assert metas[-1]["failure_kind"].endswith(":target_replaced")
    assert seen == []


@pytest.mark.parametrize("kind", ["replaced", "link"])
def test_successful_provider_exit_over_a_replaced_target_is_not_completed(
    tmp_path, monkeypatch, seatbelt_on, capsys, kind
):
    coordinator, target = _dispatch_env(tmp_path, monkeypatch)
    marker = tmp_path / "unused-marker"

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        _replace_with_planted(target, marker, kind)
        return 0, "done\n", "", False, 1

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=coordinator,
        run_agy_fn=runner,
    )
    metas = _metas(capsys.readouterr().err)
    assert code != 0
    assert metas[-1]["status"] != "completed"
    assert metas[-1]["status"] == "failed"
    assert metas[-1]["failure_kind"] == dispatch.AGY_TARGET_REPLACED
    assert metas[-1]["reconciliation_required"] is True
