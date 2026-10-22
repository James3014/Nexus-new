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
from nexus.executors import agy_write_admission as admission
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
        # Run-root round trip (nexus-agy-dispatch layout): rename the root away,
        # plant a settings file, rename it back. Must fail at the first step.
        rr_moved = target / "rr"
        attack = (
            'mv "$1" "$2" && echo PLANTED > "$2/home/.gemini/antigravity-cli/settings.json"'
            ' && mv "$2" "$1"'
        )
        before = (run_home / AGY_RUN_HOME_SETTINGS).read_bytes()
        result = _run(boundary, attack, boundary.run_root, rr_moved, cwd=target)
        print("WITNESS run-root round trip rc=", result.returncode, result.stderr.strip())
        assert result.returncode != 0 and DENIED in result.stderr
        assert boundary.run_root.is_dir() and not rr_moved.exists()
        assert (run_home / AGY_RUN_HOME_SETTINGS).read_bytes() == before
        # Sibling swap (worker_registry layout: run_tmp/attempt-XXX/home).
        reg_root = Path(os.path.realpath(tmp_path)) / "reg-run"
        reg_home = reg_root / "attempt-x" / "home"
        reg_settings = reg_home / AGY_RUN_HOME_SETTINGS
        reg_settings.parent.mkdir(parents=True)
        reg_settings.write_text("orig", encoding="utf-8")
        stage = reg_root / "stage"
        (stage / "home" / AGY_RUN_HOME_SETTINGS.parent).mkdir(parents=True)
        (stage / "home" / AGY_RUN_HOME_SETTINGS).write_text("PLANTED", encoding="utf-8")
        reg_profile = tmp_path / "reg.sb"
        reg_profile.write_text(
            admission.build_seatbelt_profile(
                run_root=reg_root, writable_target=None, run_home=reg_home
            ),
            encoding="utf-8",
        )
        swap = subprocess.run(
            [
                boundary_mod.SANDBOX_EXEC_PATH,
                "-f",
                str(reg_profile),
                "/bin/sh",
                "-c",
                'mv "$1/attempt-x" "$1/old" && mv "$1/stage" "$1/attempt-x"',
                "sh",
                str(reg_root),
            ],
            cwd=target,
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        print("WITNESS sibling swap rc=", swap.returncode, swap.stderr.strip())
        assert swap.returncode != 0 and DENIED in swap.stderr
        assert reg_settings.read_text(encoding="utf-8") == "orig"
        # Normal agy state writes under those parents still work.
        brain = gemini / "antigravity-cli" / "brain" / "b.txt"
        brain.parent.mkdir(parents=True, exist_ok=True)
        assert _write_attempt(boundary, brain, cwd=target).returncode == 0
        # #2863: Launch Services is closed, so a confined shell cannot start an
        # app (Terminal, via ``open -a Terminal x.command``) outside the profile.
        # ``-g -j`` keeps any app hidden should the deny ever regress.
        opened = _run(
            boundary, '/usr/bin/open -g -j -a TextEdit "$1"', checkout / "tracked.py", cwd=target
        )
        print("WITNESS open -a TextEdit (full profile) rc=", opened.returncode, opened.stderr.strip())
        assert opened.returncode != 0 and DENIED in opened.stderr
        # Independent of the exec rules: the mach-lookup deny alone must stop
        # LSOpen.  A control profile without it must LAUNCH the app, so the
        # failure is the Launch Services denial and not a missing app.
        ls_lines = list(admission.LAUNCH_SERVICES_DENY_LINES)
        mach_lines = ls_lines[:4]
        assert mach_lines[0].startswith("(deny mach-lookup") and mach_lines[-1].endswith("))")
        profile_lines = boundary.profile.splitlines()
        without_ls = [line for line in profile_lines if line not in ls_lines]
        assert len(without_ls) == len(profile_lines) - len(ls_lines)
        document = target / "ls-probe.txt"
        document.write_text("probe\n", encoding="utf-8")

        def _open_under(name: str, lines: list[str]) -> subprocess.CompletedProcess[str]:
            sb = tmp_path / f"{name}.sb"
            sb.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return subprocess.run(
                [
                    boundary_mod.SANDBOX_EXEC_PATH,
                    "-f",
                    str(sb),
                    "/usr/bin/open",
                    "-g",
                    "-j",
                    "-a",
                    "TextEdit",
                    str(document),
                ],
                cwd=target,
                text=True,
                capture_output=True,
                check=False,
                timeout=20,
            )

        def _textedit_pids() -> set[int]:
            out = subprocess.run(
                ["/usr/bin/pgrep", "-x", "TextEdit"], capture_output=True, text=True, check=False
            ).stdout
            return {int(x) for x in out.split()}

        preexisting = _textedit_pids()
        via_lsd = _open_under("mach-only", without_ls + mach_lines)
        print(
            "WITNESS open -a TextEdit (mach-lookup deny only) rc=",
            via_lsd.returncode,
            via_lsd.stderr.strip(),
        )
        assert via_lsd.returncode != 0
        assert "Unable to find application" in via_lsd.stderr
        assert _textedit_pids() <= preexisting, "TextEdit launched despite the mach deny"
        control = _open_under("control", without_ls)
        launched = _textedit_pids() - preexisting
        print("WITNESS open -a TextEdit (control, no Launch Services deny) rc=", control.returncode)
        for pid in launched:
            os.kill(pid, signal.SIGTERM)
        assert control.returncode == 0, control.stderr
        assert launched or preexisting, "control open did not reach TextEdit"
        # Apple Events route: osascript is not executable and fails fast.
        started = time.monotonic()
        osa = _run(boundary, '/usr/bin/osascript -e "return 1"', cwd=target)
        print("WITNESS osascript (full profile) rc=", osa.returncode, osa.stderr.strip())
        assert osa.returncode != 0 and DENIED in osa.stderr
        assert time.monotonic() - started < 10
        # Normal Python still runs and writes under the profile.
        py_out = target / "py-ok.txt"
        py = _run(
            boundary,
            'exec "$2" -c "import sys, pathlib; pathlib.Path(sys.argv[1]).write_text(\'ok\')" "$1"',
            py_out,
            Path(sys.executable),
            cwd=target,
        )
        assert py.returncode == 0, py.stderr
        assert py_out.read_text(encoding="utf-8") == "ok"
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
