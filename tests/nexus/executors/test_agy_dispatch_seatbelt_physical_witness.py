"""Issue #2260 item 2: macOS physical witness for the dispatcher Seatbelt profile.

Builds the real dispatcher boundary through ``prepare_accept_edits_boundary``
(the function ``nexus-agy-dispatch`` calls) and runs real ``sandbox-exec``
children under its profile. The only stub is the run-HOME keychain helper,
which does not touch the profile.

Collection rule (same as the DSH witness, #1607): where Seatbelt cannot run the
witnesses are bound to ``None`` so pytest collects nothing, never a skip that
could be mistaken for evidence. Only the macOS job ``dsh-seatbelt-physical-
witness`` collects them, and ``scripts/ci/verify_physical_witness_junit.py
verify --suite agy-dispatch`` fails closed unless exactly these two nodes PASSED.
"""

from __future__ import annotations

import ast
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from nexus.executors import agy_dispatch_boundary as boundary_mod
from nexus.executors.agy_write_admission import (
    AGY_RUN_HOME_PROJECTS,
    AGY_RUN_HOME_SETTINGS,
    KEYCHAIN_NOT_APPLICABLE,
)

SEATBELT_AVAILABLE = sys.platform == "darwin" and shutil.which("sandbox-exec") is not None
PHYSICAL_WITNESSES = (
    "test_dispatcher_profile_confines_writes_under_real_sandbox_exec",
    "test_dispatcher_sweep_kills_a_tagged_child_left_running",
)
DENIED = "Operation not permitted"


def physical_seatbelt_witness(func, *, available: bool = SEATBELT_AVAILABLE):
    """Expose a physical witness as a test node only where Seatbelt can run."""
    return func if available else None


def test_witness_nodes_are_declared_and_darwin_ci_must_collect_them():
    """Always collected (Linux included), so the impact gate sees a passing node.

    The physical nodes themselves exist only where Seatbelt runs. This keeps
    the declaration pinned and fails, rather than skips, if a CI macOS host
    ends up without them.
    """
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    declared = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(d, ast.Name) and d.id == "physical_seatbelt_witness"
            for d in node.decorator_list
        )
    }
    assert declared == set(PHYSICAL_WITNESSES)
    for name in PHYSICAL_WITNESSES:
        assert (globals().get(name) is not None) is SEATBELT_AVAILABLE
    if os.environ.get("CI") and sys.platform == "darwin":
        assert SEATBELT_AVAILABLE, "macOS CI host has no sandbox-exec"


def _build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The real boundary for a fake target, with the ``--log-file`` literal grant."""
    monkeypatch.setattr(
        boundary_mod, "_prepare_run_home_keychain", lambda run_home: KEYCHAIN_NOT_APPLICABLE
    )
    lease_home = tmp_path / "lease-home"
    lease_home.mkdir()
    target = tmp_path / "worktree"
    (target / ".git").mkdir(parents=True)
    (target / ".agents").mkdir()
    checkout = tmp_path / "canonical-checkout"
    checkout.mkdir()
    (checkout / "tracked.py").write_text("original\n", encoding="utf-8")
    state = tmp_path / "state" / "operation"
    state.mkdir(parents=True)
    log_file = state / "agy.log"
    log_file.write_text("", encoding="utf-8")
    boundary = boundary_mod.prepare_accept_edits_boundary(
        source_env={"HOME": str(lease_home), "PATH": "/usr/bin:/bin"},
        target=target,
        extra_writable_files=[log_file],
        extra_writable_roots=[state.parent],
    )
    return boundary, target, checkout, log_file


def _run(boundary, script: str, *args: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run ``script`` under the dispatcher's exact wrapped argv and env."""
    return subprocess.run(
        boundary.wrap_argv(["/bin/sh", "-c", script, "sh", *map(str, args)]),
        cwd=cwd,
        env=boundary.env,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )


def _write_attempt(boundary, path: Path, *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return _run(boundary, 'printf x >> "$1"', path, cwd=cwd)


@physical_seatbelt_witness
def test_dispatcher_profile_confines_writes_under_real_sandbox_exec(tmp_path, monkeypatch):
    boundary, target, checkout, log_file = _build(tmp_path, monkeypatch)
    try:
        run_home = boundary.run_home
        # Control: the profile text is the one the dispatcher would execute.
        assert boundary.profile_path.read_text(encoding="utf-8") == boundary.profile

        allowed = _write_attempt(boundary, target / "edit.py", cwd=target)
        assert allowed.returncode == 0, allowed.stderr
        assert (target / "edit.py").read_text(encoding="utf-8") == "x"

        projects = run_home / AGY_RUN_HOME_PROJECTS / "record.json"
        assert _write_attempt(boundary, projects, cwd=target).returncode == 0
        assert _write_attempt(boundary, log_file, cwd=target).returncode == 0
        assert log_file.read_text(encoding="utf-8") == "x"

        denied = {
            "canonical checkout": checkout / "tracked.py",
            "canonical checkout (new file)": checkout / "planted.py",
            "target .git": target / ".git" / "config",
            "target .agents": target / ".agents" / "hook.json",
            "run HOME .gemini/config": run_home / ".gemini" / "config" / "mcp_config.json",
            "run HOME permission settings": run_home / AGY_RUN_HOME_SETTINGS,
            "--log-file sibling": log_file.parent / "forged.log",
        }
        for label, path in denied.items():
            before = path.read_bytes() if path.exists() else None
            result = _write_attempt(boundary, path, cwd=target)
            assert result.returncode != 0, f"{label} was writable: {path}"
            assert DENIED in result.stderr, f"{label}: {result.stderr!r}"
            after = path.read_bytes() if path.exists() else None
            assert after == before, f"{label} changed on disk"
        assert (checkout / "tracked.py").read_text(encoding="utf-8") == "original\n"
        assert not (checkout / "planted.py").exists()
        # #2470 item 2: a parent of a protected entry cannot be renamed away
        # (which would let a worker plant a fresh settings.json/config).
        gemini = run_home / ".gemini"
        for label, parent in {
            "run HOME": run_home,
            ".gemini": gemini,
            ".gemini/antigravity-cli": gemini / "antigravity-cli",
        }.items():
            moved = parent.with_name(parent.name + ".moved")
            result = _run(boundary, 'mv "$1" "$2"', parent, moved, cwd=target)
            assert result.returncode != 0, f"{label} was renamable: {parent}"
            assert DENIED in result.stderr, f"{label}: {result.stderr!r}"
            assert parent.is_dir() and not moved.exists(), f"{label} moved on disk"
        # Normal agy state writes under those parents still work.
        brain = gemini / "antigravity-cli" / "brain" / "b.txt"
        brain.parent.mkdir(parents=True, exist_ok=True)
        assert _write_attempt(boundary, brain, cwd=target).returncode == 0
    finally:
        boundary.cleanup()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A killed child may linger unreaped; ps reports it as Z.
    state = subprocess.run(
        ["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return bool(state) and not state.startswith("Z")


class _BlindTracker:
    probe_failed = False

    def stop(self) -> set[int]:
        return set()


@physical_seatbelt_witness
def test_dispatcher_sweep_kills_a_tagged_child_left_running(tmp_path, monkeypatch):
    boundary, target, _checkout, _log = _build(tmp_path, monkeypatch)
    pidfile = target / "child.pid"
    child_pid = None
    try:
        # The sleeper is a Python process, not /bin/sleep: ``ps -E`` hides the
        # environment of SIP-protected system binaries. The sandboxed shell
        # starts it, records its pid and exits, leaving it running with the
        # run tag in its environment.
        boundary.before_launch()
        process = subprocess.Popen(
            boundary.wrap_argv([
                "/bin/sh",
                "-c",
                '(cd / && exec "$2" -c "import time; time.sleep(300)" </dev/null >/dev/null 2>&1) & echo $! > "$1"',
                "sh",
                str(pidfile),
                sys.executable,
            ]),
            cwd=target,
            env=boundary.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        boundary.after_launch(process.pid)
        # Isolate the run-tag path: the child sits outside the sweep roots (cd /)
        # and the descendant tracker is replaced by one that saw nothing, so only
        # the tag in the child's environment can find it.
        boundary._tracker.stop()
        boundary._tracker = _BlindTracker()
        _out, err = process.communicate(timeout=20)
        assert process.returncode == 0, err
        child_pid = int(pidfile.read_text(encoding="utf-8").strip())
        assert _alive(child_pid), "control: the tagged child must still be running before the sweep"
        assert boundary.sweep() is True
        deadline = time.monotonic() + 5
        while _alive(child_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not _alive(child_pid), "the sweep left the tagged child running"
    finally:
        boundary.cleanup()
        if child_pid is not None and _alive(child_pid):
            os.kill(child_pid, signal.SIGKILL)
