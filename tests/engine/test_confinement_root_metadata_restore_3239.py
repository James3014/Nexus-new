"""#3239: a confined command that changes the run root's mode or flags must not leave the host
unable to write into or clean up the root; the root's recorded mode and flags are restored."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

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
