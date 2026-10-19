"""#2785: the sandboxed child must not be able to swap run_dir for a symlink.

When ``run_dir`` sits under a write-allowed profile path (/tmp, /private/tmp) the
child could rename ``run_dir`` (or a parent) and put a symlink in its place.  A later
Python child would then load a ``sitecustomize.py`` the child wrote, and the parent's
``_write_result`` would follow the symlink.

These tests run on any platform: ``subprocess.run`` is replaced by a fake that does
the swap between the parent's pre-run and post-run checks.  The real ``sandbox-exec``
witnesses live in ``test_sandbox_runner_rundir_seatbelt_witness_2785.py``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from nexus.core import state_root
from nexus.engine import sandbox_runner as sandbox_runner_mod
from nexus.engine.sandbox_runner import (
    RUN_DIR_REPLACED,
    SandboxRunner,
    _capture_run_dir_identity,
    _run_dir_write_deny_rule,
)


@pytest.fixture(autouse=True)
def _no_state_root(monkeypatch):
    for name in (
        state_root.STATE_ROOT_ENV,
        state_root.CANONICAL_SOURCE_ROOT_ENV,
        state_root.TARGET_ROOT_OVERRIDE_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


def _project(base: Path) -> Path:
    root = base / "proj"
    root.mkdir()
    (root / "probe.py").write_text("print('probe-ok')\n", encoding="utf-8")
    return root


def _cmd() -> list[str]:
    return [sys.executable, "probe.py"]


class _Proc:
    returncode = 0
    stdout = "child-stdout"
    stderr = ""


def _run_dir_from_env(env: dict) -> Path:
    # The network guard is the first PYTHONPATH entry and lives in run_dir.
    return Path(env["PYTHONPATH"].split(os.pathsep)[0]).parent


def _swap_run_dir(run_dir: Path, attacker: Path) -> None:
    """What the child does: rename run_dir away and symlink the name to its own dir."""
    run_dir.rename(run_dir.with_name(run_dir.name + ".moved"))
    (attacker / "python_network_guard").mkdir(parents=True, exist_ok=True)
    (attacker / "python_network_guard" / "sitecustomize.py").write_text(
        "# child-written guard\n", encoding="utf-8"
    )
    run_dir.symlink_to(attacker, target_is_directory=True)


def _swap_parent(run_dir: Path) -> None:
    """Rename the parent and symlink its name to the renamed tree.

    run_dir then has the same device/inode at the end of the path, but its guard no
    longer sits at the path the profile denies.
    """
    runs = run_dir.parent
    moved = runs.with_name(runs.name + ".moved")
    runs.rename(moved)
    runs.symlink_to(moved, target_is_directory=True)


def test_run_dir_swapped_for_symlink_between_pre_and_post_marks_run_failed(tmp_path, monkeypatch):
    root = _project(tmp_path)
    attacker = tmp_path / "attacker"
    attacker.mkdir()
    runner = SandboxRunner(root)
    seen: dict = {}

    def fake_run(cmd, **kwargs):
        run_dir = _run_dir_from_env(kwargs["env"])
        seen["run_dir"] = run_dir
        _swap_run_dir(run_dir, attacker)
        return _Proc()

    monkeypatch.setattr(sandbox_runner_mod.subprocess, "run", fake_run)
    result = runner.run_task("swap", command=_cmd(), timeout_sec=5)

    assert result["success"] is False
    assert result["error"] == RUN_DIR_REPLACED
    assert result["exit_code"] == 126
    assert result["report_path"] is None
    assert "symlink" in result["run_dir_mismatch"]
    # The child's output is kept for diagnosis.
    assert result["stdout"] == "child-stdout"
    # Nothing was written into the child-controlled directory.
    assert not (attacker / "sandbox_result.json").exists()
    assert sorted(p.name for p in attacker.iterdir()) == ["python_network_guard"]
    assert seen["run_dir"].is_symlink()


def test_renamed_parent_with_symlink_is_detected_even_with_same_inode(tmp_path, monkeypatch):
    root = _project(tmp_path)
    runner = SandboxRunner(root)
    seen: dict = {}

    def fake_run(cmd, **kwargs):
        run_dir = _run_dir_from_env(kwargs["env"])
        seen["ino"] = os.lstat(run_dir).st_ino
        _swap_parent(run_dir)
        seen["run_dir"] = run_dir
        return _Proc()

    monkeypatch.setattr(sandbox_runner_mod.subprocess, "run", fake_run)
    result = runner.run_task("swap-parent", command=_cmd(), timeout_sec=5)

    # Control: the end of the path is still the same directory.
    assert os.lstat(seen["run_dir"]).st_ino == seen["ino"]
    assert result["success"] is False
    assert result["error"] == RUN_DIR_REPLACED
    assert result["run_dir_mismatch"] == "run_dir resolves to a different path"
    assert result["report_path"] is None
    assert not (seen["run_dir"] / "sandbox_result.json").exists()


def test_swap_during_timed_out_run_is_also_refused(tmp_path, monkeypatch):
    root = _project(tmp_path)
    attacker = tmp_path / "attacker"
    attacker.mkdir()
    runner = SandboxRunner(root)

    def fake_run(cmd, **kwargs):
        _swap_run_dir(_run_dir_from_env(kwargs["env"]), attacker)
        raise subprocess.TimeoutExpired(cmd="probe", timeout=1)

    monkeypatch.setattr(sandbox_runner_mod.subprocess, "run", fake_run)
    result = runner.run_task("swap-timeout", command=_cmd(), timeout_sec=1)

    assert result["success"] is False
    assert result["error"] == RUN_DIR_REPLACED
    assert result["original_error"] == "timeout"
    assert result["report_path"] is None
    assert not (attacker / "sandbox_result.json").exists()


def test_untouched_run_dir_still_gets_its_report(tmp_path, monkeypatch):
    root = _project(tmp_path)
    runner = SandboxRunner(root)
    monkeypatch.setattr(sandbox_runner_mod.subprocess, "run", lambda cmd, **kw: _Proc())
    result = runner.run_task("ok", command=_cmd(), timeout_sec=5)
    assert result["success"] is True
    report = Path(result["report_path"])
    assert report.is_file() and not report.is_symlink()
    assert json.loads(report.read_text(encoding="utf-8"))["stdout"] == "child-stdout"


def test_write_result_never_writes_through_a_symlinked_run_dir(tmp_path):
    runner = SandboxRunner(tmp_path)
    run_dir = tmp_path / "runs" / "run_1"
    run_dir.mkdir(parents=True)
    identity = _capture_run_dir_identity(run_dir)
    attacker = tmp_path / "attacker"
    attacker.mkdir()
    _swap_run_dir(run_dir, attacker)

    result = runner._write_result(run_dir, {"success": True, "error": None}, identity)

    assert result["success"] is False
    assert result["error"] == RUN_DIR_REPLACED
    assert result["report_path"] is None
    assert not (attacker / "sandbox_result.json").exists()


def test_write_result_without_identity_refuses_a_symlinked_run_dir(tmp_path):
    # Legacy two-argument callers: run_dir already a symlink when _write_result runs.
    runner = SandboxRunner(tmp_path)
    attacker = tmp_path / "attacker"
    attacker.mkdir()
    run_dir = tmp_path / "run_link"
    run_dir.symlink_to(attacker, target_is_directory=True)

    result = runner._write_result(run_dir, {"success": True, "error": None})

    assert result["success"] is False
    assert result["error"] == RUN_DIR_REPLACED
    assert list(attacker.iterdir()) == []


def test_write_result_never_follows_a_symlinked_report_file(tmp_path):
    runner = SandboxRunner(tmp_path)
    run_dir = tmp_path / "runs" / "run_1"
    run_dir.mkdir(parents=True)
    identity = _capture_run_dir_identity(run_dir)
    victim = tmp_path / "victim.txt"
    victim.write_text("original\n", encoding="utf-8")
    (run_dir / "sandbox_result.json").symlink_to(victim)

    result = runner._write_result(run_dir, {"success": True, "error": None}, identity)

    assert result["success"] is False
    assert result["error"] == RUN_DIR_REPLACED
    assert result["report_path"] is None
    assert victim.read_text(encoding="utf-8") == "original\n"


def test_write_result_writes_a_regular_file_in_the_recorded_dir(tmp_path):
    runner = SandboxRunner(tmp_path)
    run_dir = tmp_path / "runs" / "run_1"
    run_dir.mkdir(parents=True)
    identity = _capture_run_dir_identity(run_dir)
    (run_dir / "sandbox_result.json").write_text("stale", encoding="utf-8")

    result = runner._write_result(run_dir, {"success": True, "error": None}, identity)

    report = run_dir / "sandbox_result.json"
    assert result["report_path"] == str(report)
    assert json.loads(report.read_text(encoding="utf-8"))["success"] is True


_RULE = re.compile(r'^\((allow|deny) file-write\* \((subpath|literal) "([^"]+)"\)\)$')


def _rules(profile: str) -> list[tuple[str, str, str]]:
    return [(m[1], m[2], m[3]) for m in map(_RULE.match, profile.splitlines()) if m]


def _write_allowed(profile: str, path: Path) -> bool:
    """sandbox-exec semantics: deny by default, the last matching rule wins."""
    allowed = False
    text = str(path)
    for verb, kind, base in _rules(profile):
        if kind == "literal":
            hit = text == base
        else:
            hit = text == base or text.startswith(base.rstrip("/") + "/")
        if hit:
            allowed = verb == "allow"
    return allowed


def _captured_profile(tmp_root: Path, monkeypatch, elastic_profile: str | None = None):
    root = _project(tmp_root)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_root))
    runner = SandboxRunner(root)
    monkeypatch.setattr(runner, "has_sandbox_exec", True)
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        captured["cwd"] = kwargs["cwd"]
        return _Proc()

    monkeypatch.setattr(sandbox_runner_mod.subprocess, "run", fake_run)
    result = runner.run_task(
        "profile", command=_cmd(), timeout_sec=5, elastic_profile=elastic_profile
    )
    assert captured["cmd"][:2] == ["sandbox-exec", "-p"]
    return captured, result


@pytest.mark.parametrize("elastic", [None, "(version 1)\n(allow default)"], ids=["auto", "caller"])
def test_run_dir_deny_is_the_last_block_of_the_profile(monkeypatch, elastic):
    tmp_root = Path(tempfile.mkdtemp(prefix="nexus-rundir-2785-", dir="/tmp"))
    try:
        captured, result = _captured_profile(tmp_root, monkeypatch, elastic)
        profile = captured["cmd"][2]
        run_dir = _run_dir_from_env(captured["env"])
        assert Path(result["report_path"]).parent == run_dir

        tail = _run_dir_write_deny_rule(run_dir)
        assert profile.endswith("\n" + tail)
        lines = profile.splitlines()
        tail_lines = tail.splitlines()
        # Only deny rules after the run_dir block starts; it follows the guard deny.
        start = len(lines) - len(tail_lines)
        assert all(line.startswith("(deny file-write*") for line in lines[start:])
        assert lines[start - 1].startswith('(deny file-write* (subpath "') and lines[
            start - 1
        ].endswith('python_network_guard"))')
        for form in {str(run_dir), os.path.realpath(run_dir)}:
            assert f'(deny file-write* (subpath "{form}"))' in tail_lines
            for parent in Path(form).parents:
                assert f'(deny file-write* (literal "{parent}"))' in tail_lines

        if elastic is None:
            for form in (run_dir, Path(os.path.realpath(run_dir))):
                # run_dir and everything in it, and every parent dir, is read-only.
                assert not _write_allowed(profile, form)
                assert not _write_allowed(profile, form / "sandbox_result.json")
                assert not _write_allowed(profile, form / "python_network_guard" / "x.py")
                for parent in form.parents:
                    assert not _write_allowed(profile, parent), parent
                # Siblings of run_dir under /tmp stay writable (literal, not subpath).
                assert _write_allowed(profile, form.parent / "sibling.txt")
            # The workspace stays writable.
            assert _write_allowed(profile, Path(captured["cwd"]))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_run_dir_deny_rule_lists_literal_and_resolved_forms(tmp_path):
    real = tmp_path / "real"
    (real / "runs" / "run_1").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    run_dir = link / "runs" / "run_1"
    rules = _run_dir_write_deny_rule(run_dir).splitlines()
    subpaths = [r for r in rules if "(subpath " in r]
    assert subpaths == [
        f'(deny file-write* (subpath "{run_dir}"))',
        f'(deny file-write* (subpath "{os.path.realpath(run_dir)}"))',
    ]
    assert f'(deny file-write* (literal "{link}"))' in rules
    assert f'(deny file-write* (literal "{os.path.realpath(real)}"))' in rules
    assert len(rules) == len(set(rules))
