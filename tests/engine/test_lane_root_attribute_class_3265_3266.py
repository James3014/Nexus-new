"""#3265/#3266: the lane denies one more root attribute class to a confined command, and a
round's recorded isolation shows the root restorations. Every test passes on every platform:
without an OS barrier (Linux CI) the real-sandbox test asserts that nothing runs."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from nexus.engine import sandboxed_lane as lane


def test_profile_denies_the_extra_attribute_class_on_each_pinned_root(tmp_path):
    root = tmp_path / "round"
    profile = lane.build_sandbox_profile(
        writable=[str(root)], read_roots=[str(root)], pinned_entries=[str(root)]
    )
    assert f'(deny file-write-acl (literal "{lane.sbpl_path(str(root))}"))' in profile
    other = lane.build_sandbox_profile(writable=[str(root)], read_roots=[str(root)])
    assert "file-write-acl" not in other  # only pinned roots get it


def test_describe_reports_restorations_and_failures(tmp_path, monkeypatch):
    root = tmp_path / "round"
    root.mkdir()
    os.chmod(root, 0o750)
    conf = lane.Confinement(profile="(version 1)", env={}, roots=(root,))
    before = conf.describe()
    assert before["root_restorations"] == [] and before["root_restore_failures"] == []

    def fake_run_confined(argv, **kwargs):
        os.chmod(root, 0o000)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(lane, "run_confined", fake_run_confined)
    conf.run(["true"], cwd=root, timeout=5)
    after = conf.describe()
    assert after["root_restorations"] == [str(root)]
    assert after["barrier"] == "macos_sandbox_exec"  # existing fields unchanged
    conf.root_restore_failures.append("x: OSError: boom")
    assert conf.describe()["root_restore_failures"] == ["x: OSError: boom"]


def test_confined_command_cannot_change_root_attribute_class(tmp_path: Path):
    if not lane.os_sandbox_available():
        # No OS barrier (Linux CI): nothing confined can be built, so nothing runs.
        with pytest.raises(lane.SandboxError, match="no_os_barrier"):
            lane.confinement(sandbox=tmp_path)
        return
    # The system temp dir supports the attribute class; a pytest basetemp elsewhere may not,
    # and the command would then fail for an unrelated reason.
    top = Path(tempfile.mkdtemp()).resolve()
    try:
        sandbox = top / "sandbox"
        for name in ("home", "tmp"):
            (sandbox / name).mkdir(parents=True)
        conf = lane.confinement(sandbox=sandbox)
        proc = conf.run(
            ["/bin/chmod", "+a", "everyone deny delete", str(sandbox)], cwd=sandbox, timeout=10
        )
        assert proc.returncode != 0
        assert "not permitted" in proc.stderr
        (sandbox / "host-write.txt").write_text("ok")  # host-side write still works
        assert conf.describe()["root_restorations"] == []
    finally:
        shutil.rmtree(top, ignore_errors=True)
