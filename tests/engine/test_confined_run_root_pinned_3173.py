"""#3173: pin the confined run root's identity across rounds.

A drone's later rounds (and every confined run) keep using the directory bound at setup. Where an
OS barrier exists (macOS sandbox-exec) the two-round tests run the real sandbox; where none exists
(Linux CI) the first round is refused and the second still lands in the original root. No test
skips. Every "outside" directory lives in ``tmp_path`` with sentinel content that must stay as it
was.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

import nexus.core.drone_engine as drone_engine
import nexus.engine.sandboxed_lane as lane
from nexus.core.drone_engine import DroneToolBox
from nexus.engine.sandboxed_lane import os_sandbox_available, sbpl_path

_SENTINEL = "ORIGINAL\n"


def _layout(tmp_path: Path) -> tuple[Path, Path]:
    sandbox = tmp_path / "project" / ".nexus" / "tmp" / "drone-x"
    sandbox.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "victim.txt").write_text(_SENTINEL, encoding="utf-8")
    return sandbox, outside


def _identity(path: Path) -> tuple[int, int]:
    info = os.stat(path, follow_symlinks=False)
    return info.st_dev, info.st_ino


def _assert_outside_untouched(outside: Path) -> None:
    assert sorted(os.listdir(outside)) == ["victim.txt"]
    assert (outside / "victim.txt").read_text(encoding="utf-8") == _SENTINEL


def _round_one(outside: Path, kind: str) -> str:
    py = Path(sys.executable).name
    away = "os.rmdir(d)" if kind == "removed" else 'os.rename(d,os.environ["TMPDIR"]+"/moved")'
    return f'{py} -I -c \'import os;d=os.getcwd();os.chdir("/");{away};os.symlink("{outside}",d)\''


@pytest.mark.parametrize("kind", ["removed", "renamed"])
def test_a_two_round_drone_run_keeps_the_edit_inside_the_original_root(tmp_path, monkeypatch, kind):
    # A model command names its interpreter by bare name, resolved on the trusted PATH.
    monkeypatch.setenv("PATH", f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}")
    sandbox, outside = _layout(tmp_path)
    before = _identity(sandbox)
    box = DroneToolBox(sandbox)

    first = box.bash_exec(_round_one(outside, kind))
    second = box.file_edit("victim.txt", "MODEL CONTENT\n")

    _assert_outside_untouched(outside)
    if os_sandbox_available():
        assert first["exit_code"] != 0
    else:
        assert first["exit_code"] == -1 and "no_os_barrier" in first["stderr"]
    assert not sandbox.is_symlink()
    assert _identity(sandbox) == before
    assert second == {"status": "SUCCESS"}
    assert (sandbox / "victim.txt").read_text(encoding="utf-8") == "MODEL CONTENT\n"


def _replace_root(sandbox: Path, outside: Path, kind: str) -> Path:
    moved = sandbox.parent / "moved"
    sandbox.rename(moved)
    if kind == "symlink":
        sandbox.symlink_to(outside)
    else:
        sandbox.mkdir()
    return moved


@pytest.mark.parametrize("kind", ["symlink", "directory"])
def test_a_host_write_after_the_root_is_replaced_stays_inside_the_original_root(tmp_path, kind):
    sandbox, outside = _layout(tmp_path)
    box = DroneToolBox(sandbox)
    moved = _replace_root(sandbox, outside, kind)

    out = box.file_edit("victim.txt", "MODEL CONTENT\n")

    assert out["status"] == "FAIL"
    _assert_outside_untouched(outside)
    assert os.listdir(moved) == []
    if kind == "directory":
        assert os.listdir(sandbox) == []


def test_a_host_write_checks_the_pinned_root_even_when_the_path_check_saw_the_old_one(
    tmp_path, monkeypatch
):
    # The root may change between the path check and the write: the write itself refuses a
    # root that is no longer the pinned directory. Simulate a check that follows nothing.
    sandbox, outside = _layout(tmp_path)
    box = DroneToolBox(sandbox)
    _replace_root(sandbox, outside, "symlink")
    monkeypatch.setattr(Path, "resolve", lambda self, strict=False: Path(os.path.abspath(self)))

    out = box.file_edit("victim.txt", "MODEL CONTENT\n")

    assert out["status"] == "FAIL"
    assert "root_replaced" in out["error"]
    _assert_outside_untouched(outside)


@pytest.mark.parametrize("kind", ["symlink", "directory"])
def test_a_bash_round_after_the_root_is_replaced_is_not_started(tmp_path, monkeypatch, kind):
    sandbox, outside = _layout(tmp_path)
    box = DroneToolBox(sandbox)
    started: list[str] = []
    monkeypatch.setattr(
        drone_engine, "resolve_port", lambda name: lambda *a, **k: started.append(name)
    )
    _replace_root(sandbox, outside, kind)

    out = box.bash_exec("true")

    assert out["exit_code"] == -1
    assert started == []
    _assert_outside_untouched(outside)


def test_a_drone_root_that_is_a_link_at_setup_is_refused(tmp_path):
    _, outside = _layout(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(outside)
    with pytest.raises(OSError, match="root_not_a_directory"):
        DroneToolBox(alias)


def test_confinement_keeps_every_writable_root_entry_fixed(tmp_path, monkeypatch):
    # Checked from the profile text, so it holds on hosts without sandbox-exec too.
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    work = tmp_path / "work"
    work.mkdir()

    bound = lane.confinement(sandbox=sandbox, extra_writable=(work,))

    for root in (sandbox, work):
        assert (
            f'(deny file-write-unlink file-write-create (literal "{sbpl_path(root)}"))'
            in bound.profile
        )
    # What is inside each root stays writable.
    assert f'(allow file-write* (subpath "{sbpl_path(sandbox)}")' in bound.profile


# --- #3177 follow-ups -------------------------------------------------------------------------


def test_confinement_leaves_each_root_entrys_own_metadata_writable(tmp_path, monkeypatch):
    # Profile text, so it holds without sandbox-exec too: only removal/rename/re-creation of the
    # root entry is denied, not every write to it.
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    work = tmp_path / "work"
    work.mkdir()

    bound = lane.confinement(sandbox=sandbox, extra_writable=(work,))

    for root in (sandbox, work):
        assert f'(deny file-write* (literal "{sbpl_path(root)}"))' not in bound.profile


_METADATA_COMMANDS = {
    "times": "import os;os.utime('.')",
    "mode": "import os;os.chmod('.',0o750)",
    "copy_preserving": (
        "import os,subprocess,sys;os.mkdir(os.environ['TMPDIR']+'/s');"
        "open(os.environ['TMPDIR']+'/s/f','w').write('x');"
        "sys.exit(subprocess.run(['/bin/cp','-pR',os.environ['TMPDIR']+'/s/.','.']).returncode)"
    ),
    "archive_dot": (
        "import os,subprocess,sys;t=os.environ['TMPDIR'];os.mkdir(t+'/a');"
        "open(t+'/a/f','w').write('x');"
        "subprocess.run(['/usr/bin/tar','-cf',t+'/a.tar','-C',t+'/a','.'],check=True);"
        "sys.exit(subprocess.run(['/usr/bin/tar','-xpf',t+'/a.tar','-C','.']).returncode)"
    ),
}


@pytest.mark.parametrize("kind", sorted(_METADATA_COMMANDS))
def test_a_confined_command_can_set_the_roots_own_metadata(tmp_path, kind):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    before = _identity(work)
    if not os_sandbox_available():
        with pytest.raises(lane.SandboxError, match="no_os_barrier"):
            lane.confinement(sandbox=sandbox, extra_writable=(work,))
        return
    bound = lane.confinement(sandbox=sandbox, extra_writable=(work,))

    out = bound.run([sys.executable, "-I", "-c", _METADATA_COMMANDS[kind]], cwd=work, timeout=60)

    assert out.returncode == 0, out.stderr
    assert _identity(work) == before and not work.is_symlink()


class _FakeRun:
    returncode = 0
    stdout = "ok"
    stderr = ""


def test_a_bash_round_hands_the_sandbox_the_path_it_checked(tmp_path, monkeypatch):
    # The drone dir is reached through a linked parent: the round checks, and the sandbox gets,
    # one already resolved path, so the two cannot name different entries.
    sandbox, _ = _layout(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(sandbox.parent)
    box = DroneToolBox(alias / sandbox.name)
    seen: list[object] = []

    def run(command, *, work_dir, timeout):
        seen.append(work_dir)
        return _FakeRun()

    monkeypatch.setattr(drone_engine, "resolve_port", lambda name: run)

    out = box.bash_exec("true")

    assert out["exit_code"] == 0
    assert [str(path) for path in seen] == [os.path.realpath(sandbox)]


def test_a_bash_round_whose_root_changed_during_the_call_is_refused(tmp_path, monkeypatch):
    # Something outside the sandbox replaces the root while the round runs: the round's result
    # is not reported as a success.
    sandbox, outside = _layout(tmp_path)
    box = DroneToolBox(sandbox)

    def run(command, *, work_dir, timeout):
        _replace_root(sandbox, outside, "symlink")
        return _FakeRun()

    monkeypatch.setattr(drone_engine, "resolve_port", lambda name: run)

    out = box.bash_exec("true")

    assert out == {"exit_code": -1, "stderr": "sandbox_root_replaced"}
    _assert_outside_untouched(outside)


class _NoModel:
    def ask_structured(self, messages):  # pragma: no cover - must never be reached
        raise AssertionError("model called for a refused drone root")


@pytest.mark.parametrize("kind", ["link_to_dir", "dangling_link"])
def test_a_drone_run_whose_root_is_a_link_at_setup_returns_a_refusal(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(
        drone_engine.TacticalDrone, "save_evolution_crystal", lambda self, path: None
    )
    project = tmp_path / "project"
    (project / ".nexus" / "tmp").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "victim.txt").write_text(_SENTINEL, encoding="utf-8")
    target = outside if kind == "link_to_dir" else tmp_path / "missing"
    (project / ".nexus" / "tmp" / "drone-x").symlink_to(target)
    drone = drone_engine.TacticalDrone("drone-x", project)
    drone.local_brain = _NoModel()

    result = drone.sense_think_act("edit victim.txt")

    assert result["outcome"] == "FAIL"
    assert "drone_sandbox_root_refused" in result["error"]
    _assert_outside_untouched(outside)


def test_a_bash_round_is_not_started_when_the_checked_path_no_longer_resolves_to_itself(
    tmp_path, monkeypatch
):
    # A parent became a link: the root is still the same directory, but the sandbox would
    # resolve the path to a different one than the check saw, so the round does not start.
    sandbox, outside = _layout(tmp_path)
    box = DroneToolBox(sandbox)
    started: list[str] = []
    monkeypatch.setattr(
        drone_engine, "resolve_port", lambda name: lambda *a, **k: started.append(name)
    )
    parent = sandbox.parent
    parent.rename(parent.with_name("tmp-real"))
    parent.symlink_to(parent.with_name("tmp-real"))
    assert _identity(sandbox) == _identity(parent.with_name("tmp-real") / sandbox.name)

    out = box.bash_exec("true")

    assert out == {"exit_code": -1, "stderr": "sandbox_root_replaced"}
    assert started == []
    _assert_outside_untouched(outside)


def test_setup_refuses_a_root_that_changed_while_it_was_recorded(tmp_path, monkeypatch):
    sandbox, _ = _layout(tmp_path)
    real = drone_engine.root_identity
    calls: list[str] = []

    def changing(root):
        calls.append(str(root))
        dev, ino = real(root)
        return (dev, ino + len(calls) - 1)

    monkeypatch.setattr(drone_engine, "root_identity", changing)

    with pytest.raises(OSError, match="root_replaced"):
        DroneToolBox(sandbox)
