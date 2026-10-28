"""#2970: the model sandbox grants reads for the interpreter that actually starts.

The sandbox env drops PATH entries inside the work dir, so a bare ``python3`` found first in
the work dir (an activated venv there, or a planted binary) is not the one the sandboxed run
starts. The read grant used to follow that host lookup, and the interpreter that did start could
not load (exit -6). Where an OS barrier exists the run now succeeds with the trusted
interpreter; where none exists nothing runs. No test skips.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from nexus.engine import model_output_sandbox as mos
from nexus.engine.sandboxed_lane import os_sandbox_available


@pytest.fixture
def split_path(tmp_path, monkeypatch):
    """A work dir whose ``bin/python3`` comes first on PATH, then a trusted ``python3``."""

    work = tmp_path / "work"
    (work / "bin").mkdir(parents=True)
    planted = work / "bin" / "python3"
    planted.write_text("#!/bin/sh\necho PLANTED\nexit 7\n")
    planted.chmod(0o755)
    trusted = tmp_path / "trusted" / "bin"
    trusted.mkdir(parents=True)
    (trusted / "python3").symlink_to(Path(sys.executable).resolve())
    monkeypatch.setenv("PATH", f"{work / 'bin'}:{trusted}:/usr/bin:/bin")
    return work


def _expect_ran_trusted(run):
    if not os_sandbox_available():
        with pytest.raises(mos.SandboxError, match="no_os_barrier"):
            run()
        return
    res = run()
    assert res.returncode == 0, res.stderr
    assert "TRUSTED" in res.stdout and "PLANTED" not in res.stdout


def test_run_model_argv_grants_the_interpreter_it_starts(split_path):
    # Callers grant ``interpreter_readable_roots(argv[0])`` from the host PATH, as the local_heal
    # verifiers do; that names the work-dir python3 here.
    _expect_ran_trusted(
        lambda: mos.run_model_argv(
            ["python3", "-I", "-c", "print('TRUSTED')"],
            work_dir=split_path,
            timeout=20,
            readable=mos.interpreter_readable_roots("python3"),
        )
    )


def test_run_model_command_string_grants_the_interpreter_it_starts(split_path):
    _expect_ran_trusted(
        lambda: mos.run_model_command_string(
            "python3 -I -c \"print('TRUSTED')\"", work_dir=split_path, timeout=20
        )
    )


def test_a_bare_name_only_inside_the_work_dir_is_not_found(tmp_path, monkeypatch):
    work = tmp_path / "work"
    (work / "bin").mkdir(parents=True)
    tool = work / "bin" / "only-here-2970"
    tool.write_text("#!/bin/sh\necho PLANTED\n")
    tool.chmod(0o755)
    monkeypatch.setenv("PATH", f"{work / 'bin'}:/usr/bin:/bin")
    if not os_sandbox_available():
        with pytest.raises(mos.SandboxError, match="no_os_barrier"):
            mos.run_model_argv(["only-here-2970"], work_dir=work, timeout=20)
        return
    with pytest.raises(FileNotFoundError):
        mos.run_model_argv(["only-here-2970"], work_dir=work, timeout=20)
