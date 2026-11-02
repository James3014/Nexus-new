"""#3197: the model sandbox call binds the drone's recorded run root itself.

A drone round checks its root, then hands the path to the sandbox call. The sandbox call now
checks the recorded identity again itself and grants only that directory, so a root swapped in
between (and put back before the round's own post-check) gets no grant. After each confined run
the host puts the root's own flags and mode back, and the profile keeps the root's ACL
unchangeable.

Where an OS barrier exists (macOS sandbox-exec) the run tests use the real sandbox; where none
exists (Linux CI) they assert the documented refusal instead. No test skips. Every "outside"
directory lives in ``tmp_path`` with sentinel content that must stay as it was.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

import nexus.core.contained_write as cw
import nexus.core.drone_engine as drone_engine
import nexus.engine.model_output_sandbox as mos
import nexus.engine.sandboxed_lane as lane
from nexus.core.contained_write import root_identity
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


def _assert_outside_untouched(outside: Path) -> None:
    assert sorted(os.listdir(outside)) == ["victim.txt"]
    assert (outside / "victim.txt").read_text(encoding="utf-8") == _SENTINEL


def _swap_in(sandbox: Path, outside: Path, kind: str) -> Path:
    """Put the outside directory at the root path (as a link, or the directory itself)."""

    moved = sandbox.with_name("moved")
    sandbox.rename(moved)
    if kind == "symlink":
        sandbox.symlink_to(outside)
    else:
        outside.rename(sandbox)
    return moved


def _swap_back(sandbox: Path, outside: Path, moved: Path, kind: str) -> None:
    if kind == "symlink":
        sandbox.unlink()
    else:
        sandbox.rename(outside)
    moved.rename(sandbox)


@pytest.mark.parametrize("kind", ["symlink", "directory"])
def test_a_root_swapped_after_the_round_check_and_restored_gets_no_grant(
    tmp_path, monkeypatch, kind
):
    sandbox, outside = _layout(tmp_path)
    before = root_identity(sandbox)
    box = DroneToolBox(sandbox)

    def swap_then_run(command, *, work_dir, timeout):
        # Outside the sandbox, in the gap between the round's check and the sandbox call; put
        # back before the round's own post-check runs.
        moved = _swap_in(sandbox, outside, kind)
        try:
            return mos.run_model_command_string(command, work_dir=work_dir, timeout=timeout)
        finally:
            _swap_back(sandbox, outside, moved, kind)

    monkeypatch.setattr(drone_engine, "resolve_port", lambda name: swap_then_run)

    out = box.bash_exec("touch planted")

    assert out["exit_code"] == -1
    assert "work_dir_replaced" in out["stderr"]
    _assert_outside_untouched(outside)
    assert os.listdir(sandbox) == []
    assert root_identity(sandbox) == before


def test_a_round_on_the_recorded_root_still_runs_there(tmp_path):
    sandbox, outside = _layout(tmp_path)
    box = DroneToolBox(sandbox)

    out = box.bash_exec("touch made")

    if os_sandbox_available():
        assert out["exit_code"] == 0, out
        assert (sandbox / "made").is_file()
    else:
        assert out["exit_code"] == -1 and "no_os_barrier" in out["stderr"]
        assert os.listdir(sandbox) == []
    _assert_outside_untouched(outside)


def test_a_pinned_root_that_is_another_directory_now_is_refused_before_anything_runs(tmp_path):
    sandbox, outside = _layout(tmp_path)
    pinned = cw.PinnedRoot(sandbox, root_identity(outside))

    with pytest.raises(mos.SandboxError, match="work_dir_replaced"):
        with mos.model_sandbox(pinned):
            pytest.fail("a sandbox was bound for a root that is not the recorded one")


def test_a_pinned_root_reached_through_a_linked_parent_is_refused(tmp_path, monkeypatch):
    # Same directory, but the path no longer resolves to itself: the grant would name a path
    # that is not where the directory is. Refused before the barrier, the same on every host.
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: False)
    sandbox, _ = _layout(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(sandbox.parent)
    pinned = cw.PinnedRoot(alias / sandbox.name, root_identity(sandbox))

    with pytest.raises(mos.SandboxError, match="work_dir_replaced"):
        with mos.model_sandbox(pinned):
            pytest.fail("a sandbox was bound for a path that does not resolve to itself")


def _swap_during_confinement(monkeypatch, sandbox: Path, outside: Path, kind: str, restore: bool):
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    real = mos.confinement

    def swapping(**kwargs):
        moved = _swap_in(sandbox, outside, kind)
        try:
            return real(**kwargs)
        finally:
            if restore:
                _swap_back(sandbox, outside, moved, kind)

    monkeypatch.setattr(mos, "confinement", swapping)


def test_a_root_swapped_while_the_profile_is_built_and_restored_is_refused(tmp_path, monkeypatch):
    # The profile resolved the path while it was a link: it would grant the link's target.
    sandbox, outside = _layout(tmp_path)
    pinned = cw.PinnedRoot(sandbox, root_identity(sandbox))
    _swap_during_confinement(monkeypatch, sandbox, outside, "symlink", restore=True)

    with pytest.raises(mos.SandboxError, match="work_dir_replaced"):
        with mos.model_sandbox(pinned):
            pytest.fail("a profile granting the swapped-in target was handed out")


def test_a_root_replaced_while_the_profile_is_built_is_refused(tmp_path, monkeypatch):
    sandbox, outside = _layout(tmp_path)
    pinned = cw.PinnedRoot(sandbox, root_identity(sandbox))
    _swap_during_confinement(monkeypatch, sandbox, outside, "directory", restore=False)

    with pytest.raises(mos.SandboxError, match="work_dir_replaced"):
        with mos.model_sandbox(pinned):
            pytest.fail("a profile was handed out for a root that is no longer the recorded one")


def test_a_root_replaced_during_the_run_voids_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    sandbox, outside = _layout(tmp_path)
    pinned = cw.PinnedRoot(sandbox, root_identity(sandbox))

    with pytest.raises(mos.SandboxError, match="work_dir_replaced"):
        with mos.model_sandbox(pinned):
            _swap_in(sandbox, outside, "symlink")


# --- the root's own metadata (#3197 comment) -----------------------------------------------


def test_the_roots_own_mode_is_put_back_after_the_run(tmp_path, monkeypatch):
    # Profile and restore logic only, so it holds without sandbox-exec too.
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    work = tmp_path / "work"
    work.mkdir(mode=0o750)
    os.chmod(work, 0o750)

    with mos.model_sandbox(work):
        os.chmod(work, 0o000)  # what a confined `chmod 000 .` leaves behind

    assert stat.S_IMODE(os.stat(work).st_mode) == 0o750


def test_the_profile_keeps_each_roots_acl_unchangeable(tmp_path, monkeypatch):
    monkeypatch.setattr(lane, "os_sandbox_available", lambda: True)
    work = tmp_path / "work"
    work.mkdir()
    extra = tmp_path / "extra"
    extra.mkdir()

    with mos.model_sandbox(work, writable=(extra,)) as (prefix, _env):
        profile = prefix[2]

    for root in (work, extra):
        assert f'(deny file-write-acl (literal "{sbpl_path(root)}"))' in profile
    # Times, mode and flags stay writable: cp -p and archives extracting ./ need them.
    assert f'(deny file-write* (literal "{sbpl_path(work)}"))' not in profile


def _acl_lines(path: Path) -> int:
    listing = subprocess.run(
        ["/bin/ls", "-lde", str(path)], capture_output=True, text=True, check=True
    ).stdout
    return len(listing.splitlines())


_ROOT_METADATA = {
    "immutable_flag": "/usr/bin/chflags uchg .",
    "hidden_flag": "/usr/bin/chflags hidden .",
    "no_access_mode": "/bin/chmod 000 .",
    "open_mode": "/bin/chmod 777 .",
}


@pytest.mark.parametrize("kind", sorted(_ROOT_METADATA))
def test_a_confined_change_to_the_roots_own_metadata_is_put_back(tmp_path, kind):
    work = tmp_path / "work"
    work.mkdir()
    os.chmod(work, 0o755)
    before = os.stat(work, follow_symlinks=False)
    if not os_sandbox_available():
        with pytest.raises(mos.SandboxError, match="no_os_barrier"):
            mos.run_model_command_string(_ROOT_METADATA[kind], work_dir=work, timeout=30)
        return

    out = mos.run_model_command_string(_ROOT_METADATA[kind], work_dir=work, timeout=30)

    assert out.returncode == 0, out.stderr  # the change itself is allowed (#3177)
    after = os.stat(work, follow_symlinks=False)
    assert stat.S_IMODE(after.st_mode) == 0o755
    assert after.st_flags == before.st_flags
    assert (after.st_dev, after.st_ino) == (before.st_dev, before.st_ino)
    (work / "host-write").write_text("ok", encoding="utf-8")  # the host can use it again


def test_a_confined_command_cannot_add_an_acl_to_the_root(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    command = "/bin/chmod +a 'everyone deny add_file' ."
    if not os_sandbox_available():
        with pytest.raises(mos.SandboxError, match="no_os_barrier"):
            mos.run_model_command_string(command, work_dir=work, timeout=30)
        return
    before = _acl_lines(work)

    out = mos.run_model_command_string(command, work_dir=work, timeout=30)

    assert out.returncode != 0
    assert _acl_lines(work) == before
    (work / "host-write").write_text("ok", encoding="utf-8")


_COPY_PRESERVING = {
    # Copies the source dir's own metadata onto the root itself.
    "cp_p_onto_root": (
        "import os,subprocess,sys;t=os.environ['TMPDIR'];os.mkdir(t+'/s');"
        "open(t+'/s/f','w').write('x');"
        "sys.exit(subprocess.run(['/bin/cp','-pR',t+'/s/.','.']).returncode)"
    ),
    # The source dir carries an ACL: the copy still succeeds, the root's ACL stays as it was.
    "cp_p_onto_root_from_acl_source": (
        "import os,subprocess,sys;t=os.environ['TMPDIR'];os.mkdir(t+'/s');"
        "open(t+'/s/f','w').write('x');"
        "subprocess.run(['/bin/chmod','+a','everyone deny delete',t+'/s'],check=True);"
        "sys.exit(subprocess.run(['/bin/cp','-pR',t+'/s/.','.']).returncode)"
    ),
    "cp_p_file_into_root": (
        "import os,subprocess,sys;t=os.environ['TMPDIR'];open(t+'/g','w').write('x');"
        "sys.exit(subprocess.run(['/bin/cp','-p',t+'/g','./g']).returncode)"
    ),
    "archive_dot": (
        "import os,subprocess,sys;t=os.environ['TMPDIR'];os.mkdir(t+'/a');"
        "open(t+'/a/f','w').write('x');"
        "subprocess.run(['/usr/bin/tar','-cf',t+'/a.tar','-C',t+'/a','.'],check=True);"
        "sys.exit(subprocess.run(['/usr/bin/tar','-xpf',t+'/a.tar','-C','.']).returncode)"
    ),
}


@pytest.mark.parametrize("kind", sorted(_COPY_PRESERVING))
def test_copies_preserving_metadata_into_the_root_still_work(tmp_path, kind):
    work = tmp_path / "work"
    work.mkdir()
    argv = [sys.executable, "-I", "-c", _COPY_PRESERVING[kind]]
    roots = mos.interpreter_readable_roots(sys.executable)
    if not os_sandbox_available():
        with pytest.raises(mos.SandboxError, match="no_os_barrier"):
            mos.run_model_argv(argv, work_dir=work, timeout=60, readable=roots)
        return
    before = _acl_lines(work)

    out = mos.run_model_argv(argv, work_dir=work, timeout=60, readable=roots)

    assert out.returncode == 0, out.stderr
    assert (work / ("g" if kind == "cp_p_file_into_root" else "f")).read_text() == "x"
    assert _acl_lines(work) == before


# --- swapping the root from inside the sandbox ------------------------------------------------

_RENAME_SWAP = 0x2  # renamex_np(2)


def _swap_command(direction: str) -> str:
    """A confined command that tries to exchange the root with a fresh dir it owns."""

    src, dst = ("d", "o") if direction == "root_first" else ("o", "d")
    return (
        "import ctypes,os,sys;libc=ctypes.CDLL(None,use_errno=True);"
        "d=os.getcwd().encode();o=(os.environ['TMPDIR']+'/other').encode();os.mkdir(o);"
        f"r=libc.renamex_np({src},{dst},{_RENAME_SWAP});"
        "print(r,ctypes.get_errno());sys.exit(0 if r==0 else 3)"
    )


@pytest.mark.parametrize("direction", ["root_first", "root_second"])
def test_a_confined_command_cannot_swap_the_root(tmp_path, direction):
    sandbox, outside = _layout(tmp_path)
    before = root_identity(sandbox)
    argv = [sys.executable, "-I", "-c", _swap_command(direction)]
    roots = mos.interpreter_readable_roots(sys.executable)
    if not os_sandbox_available():
        with pytest.raises(mos.SandboxError, match="no_os_barrier"):
            mos.run_model_argv(argv, work_dir=sandbox, timeout=60, readable=roots)
        return

    out = mos.run_model_argv(argv, work_dir=sandbox, timeout=60, readable=roots)

    assert out.returncode == 3, (out.stdout, out.stderr)  # renamex_np itself was refused
    assert not sandbox.is_symlink()
    assert root_identity(sandbox) == before
    _assert_outside_untouched(outside)


def test_a_confined_command_cannot_rename_a_directory_onto_the_root(tmp_path):
    sandbox, outside = _layout(tmp_path)
    before = root_identity(sandbox)
    # Unconfined, renaming an empty directory onto the (empty) root replaces it.
    script = (
        "import os,sys;o=os.environ['TMPDIR']+'/other';os.mkdir(o);d=os.getcwd();os.chdir('/')"
        "\ntry:\n os.rename(o,d)\nexcept OSError:\n sys.exit(3)\n"
    )
    argv = [sys.executable, "-I", "-c", script]
    roots = mos.interpreter_readable_roots(sys.executable)
    if not os_sandbox_available():
        with pytest.raises(mos.SandboxError, match="no_os_barrier"):
            mos.run_model_argv(argv, work_dir=sandbox, timeout=60, readable=roots)
        return

    out = mos.run_model_argv(argv, work_dir=sandbox, timeout=60, readable=roots)

    assert out.returncode == 3, (out.stdout, out.stderr)
    assert root_identity(sandbox) == before
    _assert_outside_untouched(outside)


# --- the run's private home/tmp ----------------------------------------------------------------

# Leaves entries in the run's own TMPDIR that a plain removal refuses, plus a link to a host file
# that carries an ACL of its own; prints TMPDIR so the test can check it is gone.
_UNDELETABLE_PRIVATE = (
    "import os,subprocess;t=os.environ['TMPDIR'];os.makedirs(t+'/a/b');"
    "open(t+'/a/b/f','w').write('x');os.symlink('{host}',t+'/a/link');"
    "subprocess.run(['/bin/chmod','+a','everyone deny delete,delete_child',t+'/a',t+'/a/b',"
    "t+'/a/b/f'],check=True);"
    "subprocess.run(['/usr/bin/chflags','uchg',t+'/a/b/f'],check=True);"
    "os.chmod(t+'/a/b',0);print(t)"
)


def test_a_private_dir_left_undeletable_by_the_command_is_still_removed(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    host = outside / "host.txt"
    host.write_text(_SENTINEL, encoding="utf-8")
    argv = [sys.executable, "-I", "-c", _UNDELETABLE_PRIVATE.replace("{host}", str(host))]
    roots = mos.interpreter_readable_roots(sys.executable)
    if not os_sandbox_available():
        with pytest.raises(mos.SandboxError, match="no_os_barrier"):
            mos.run_model_argv(argv, work_dir=work, timeout=60, readable=roots)
        return
    subprocess.run(["/bin/chmod", "+a", "everyone deny delete", str(host)], check=True)
    host_acl = _acl_lines(host)

    out = mos.run_model_argv(argv, work_dir=work, timeout=60, readable=roots)

    assert out.returncode == 0, out.stderr
    private = Path(out.stdout.strip()).parent  # TMPDIR is <private>/tmp
    assert private.name.startswith("nexus-model-exec-")
    assert not private.exists()
    # The link was removed as a link: its target keeps its own ACL and content.
    assert _acl_lines(host) == host_acl
    assert host.read_text(encoding="utf-8") == _SENTINEL
    subprocess.run(["/bin/chmod", "-N", str(host)], check=True)


def test_removing_the_private_dir_undoes_modes_and_never_follows_a_link(tmp_path):
    # Host-side removal only, so it holds without sandbox-exec too.
    private = tmp_path / "private"
    (private / "a" / "b").mkdir(parents=True)
    (private / "a" / "b" / "f").write_text("x", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    os.chmod(outside, 0o500)
    (private / "a" / "link").symlink_to(outside)
    os.chmod(private / "a" / "b", 0)
    os.chmod(private / "a", 0o500)

    mos._remove_private_dir(str(private))

    assert not private.exists()
    assert stat.S_IMODE(os.stat(outside).st_mode) == 0o500
    os.chmod(outside, 0o700)
