"""#3239: a confined command that changes the run root's mode or flags must not leave the host
unable to write into or clean up the root; the root's recorded mode and flags are restored."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

from nexus.engine import sandboxed_lane as lane


def _confinement(root: Path) -> lane.Confinement:
    return lane.Confinement(profile="(version 1)", env={}, roots=(root,))


def test_root_mode_changed_by_command_is_restored_and_reported(tmp_path, monkeypatch):
    root = tmp_path / "round"
    root.mkdir()
    os.chmod(root, 0o750)
    conf = _confinement(root)

    def fake_run_confined(argv, **kwargs):
        os.chmod(root, 0o000)  # what a confined `chmod 000 .` does
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(lane, "run_confined", fake_run_confined)
    conf.run(["true"], cwd=root, timeout=5)

    assert stat.S_IMODE(root.stat().st_mode) == 0o750
    (root / "host-write.txt").write_text("ok")  # host-side write still works
    assert conf.root_restorations == [str(root)]


def test_untouched_root_reports_no_restoration(tmp_path, monkeypatch):
    root = tmp_path / "round"
    root.mkdir()
    conf = _confinement(root)
    monkeypatch.setattr(
        lane, "run_confined", lambda argv, **kw: subprocess.CompletedProcess(argv, 0, "", "")
    )
    conf.run(["true"], cwd=root, timeout=5)
    assert conf.root_restorations == []


class _FlaggedRoot:
    """A stand-in for a root carrying an immutable flag: chmod is refused while the flag is
    set, so the restore must clear the flag first. Runs on Linux CI too (no real chflags)."""

    def __init__(self, path: Path, mode: int) -> None:
        self.path, self.mode, self.flags = path, mode, 0
        self.calls: list[str] = []
        # The real functions, captured before os.lstat / os.chmod are replaced by the fakes.
        self._lstat, self._chmod = os.lstat, os.chmod

    def lstat(self, p, *a, **k):
        info = self._lstat(p, *a, **k)
        if Path(p) == self.path:
            # Only the two fields the restore reads; st_flags does not exist on Linux's
            # stat_result, so a plain namespace stands in for it.
            return SimpleNamespace(
                st_mode=(info.st_mode & ~0o7777) | self.mode, st_flags=self.flags
            )
        return info

    def chflags(self, p, flags, *a, **k):
        assert Path(p) == self.path
        self.calls.append(f"chflags:{flags}")
        self.flags = flags

    def chmod(self, p, mode, *a, **k):
        if Path(p) == self.path:
            self.calls.append(f"chmod:{mode:o}")
            if self.flags:
                raise PermissionError(1, "Operation not permitted")  # immutable flag set
            self.mode = mode
            return
        self._chmod(p, mode, *a, **k)


def test_flags_are_cleared_before_the_mode_is_restored(tmp_path, monkeypatch):
    root = tmp_path / "round"
    root.mkdir()
    fake = _FlaggedRoot(root, 0o750)
    monkeypatch.setattr(os, "lstat", fake.lstat)
    monkeypatch.setattr(os, "chflags", fake.chflags, raising=False)
    monkeypatch.setattr(os, "chmod", fake.chmod)
    conf = _confinement(root)  # records mode 0o750, flags 0

    def fake_run_confined(argv, **kwargs):
        fake.mode, fake.flags = 0o000, 0x2  # what `chmod 000 .` plus `chflags uchg .` do
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(lane, "run_confined", fake_run_confined)
    conf.run(["true"], cwd=root, timeout=5)

    assert (fake.mode, fake.flags) == (0o750, 0)
    assert fake.calls == ["chflags:0", "chmod:750"]  # flags first, then mode
    assert conf.root_restorations == [str(root)]
    assert conf.root_restore_failures == []


def test_a_restore_that_fails_is_recorded_not_hidden(tmp_path, monkeypatch):
    root = tmp_path / "round"
    root.mkdir()
    os.chmod(root, 0o750)
    conf = _confinement(root)
    real_chmod = os.chmod

    def fake_run_confined(argv, **kwargs):
        real_chmod(root, 0o000)
        return subprocess.CompletedProcess(argv, 0, "", "")

    def chmod_refused(p, mode, *a, **k):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(lane, "run_confined", fake_run_confined)
    monkeypatch.setattr(os, "chmod", chmod_refused)
    try:
        conf.run(["true"], cwd=root, timeout=5)
    finally:
        real_chmod(root, 0o750)  # let pytest clean the directory

    assert conf.root_restorations == []
    assert len(conf.root_restore_failures) == 1
    assert conf.root_restore_failures[0].startswith(f"{root}: PermissionError")
