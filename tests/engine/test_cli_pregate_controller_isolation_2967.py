"""The pregate capability never runs a caller's verifier in the controller worktree (#2967)."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

import nexus.engine.model_output_sandbox as sandbox_module
import nexus.executors.cli_worker as cli_worker
from nexus.core import capability_executor_registry as registry
from nexus.engine import cli_pregate
from nexus.engine.model_output_sandbox import SANDBOX_EXEC, SandboxError, model_sandbox
from nexus.services.local_heal.pipeline_isolation import verifier_input_files

_WRITE_AND_IMPORT = (
    "import pathlib, oracle_mod; "
    "pathlib.Path('probe.txt').write_text('x'); "
    "import py_compile; py_compile.compile('oracle_mod.py', doraise=True); "
    "print('CWD=' + str(pathlib.Path.cwd()))"
)


def _controller(tmp_path: Path) -> Path:
    root = tmp_path / "controller"
    (root / "tasks").mkdir(parents=True)
    (root / "oracle_mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    return root


def _tree(root: Path) -> set[str]:
    return {str(path.relative_to(root)) for path in root.rglob("*")}


def _os_barrier(tmp_path: Path) -> bool:
    probe = tmp_path / "barrier-probe"
    probe.mkdir()
    try:
        with model_sandbox(probe):
            return True
    except SandboxError:
        return False


@pytest.fixture
def unconfined_worker(monkeypatch):
    """Run the confined request without Seatbelt so the copy logic is testable on Linux."""

    seen = []
    real = cli_worker.run_cli_worker

    @contextmanager
    def fake_sandbox(work_dir, *, readable=()):
        yield [SANDBOX_EXEC, "-p", "(version 1)"], {"HOME": str(work_dir)}

    def run(request, **kwargs):
        seen.append(request)
        return real(replace(request, seatbelt_profile=None), **kwargs)

    monkeypatch.setattr(sandbox_module, "model_sandbox", fake_sandbox)
    monkeypatch.setattr(cli_worker, "run_cli_worker", run)
    return seen


def test_isolated_pregate_writes_land_in_a_disposable_copy(tmp_path, unconfined_worker):
    root = _controller(tmp_path)
    before = _tree(root)
    command = f'{sys.executable} -c "{_WRITE_AND_IMPORT}"'

    passed, results = cli_pregate.run_cli_pregate(
        root, [command], timeout_per_cmd=60, isolate_workspace=True
    )

    assert passed, results
    assert _tree(root) == before
    (request,) = unconfined_worker
    cwd = Path(request.cwd)
    assert cwd != root.resolve() and not cwd.is_relative_to(root.resolve())
    assert not cwd.exists()  # the copy is removed after the run
    assert f"CWD={cwd}" in results[0]["stdout_tail"]
    assert request.exact_env is True
    assert request.seatbelt_profile == "(version 1)"
    assert request.sweep_descendants_on_exit is True and request.sweep_roots == (str(cwd),)
    assert request.env["PYTHONPATH"] == str(cwd)
    assert request.env["HOME"] == str(cwd)


def test_isolated_pregate_copy_skips_git_and_venv(tmp_path, unconfined_worker):
    root = _controller(tmp_path)
    (root / ".git").mkdir()
    (root / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (root / ".venv").mkdir()
    command = (
        f'{sys.executable} -c "import pathlib, sys; '
        "sys.exit(1 if pathlib.Path('.git').exists() or pathlib.Path('.venv').exists() else 0)\""
    )

    passed, results = cli_pregate.run_cli_pregate(root, [command], isolate_workspace=True)

    assert passed, results


def test_isolated_pregate_without_os_barrier_still_runs_only_in_the_copy(tmp_path, monkeypatch):
    """No OS barrier (Linux, kill switch): the verifier runs unconfined but in the copy."""

    root = _controller(tmp_path)
    before = _tree(root)

    def no_barrier(work_dir, *, readable=()):
        raise SandboxError("no_os_barrier")

    seen = []
    real = cli_worker.run_cli_worker
    monkeypatch.setattr(sandbox_module, "model_sandbox", no_barrier)
    monkeypatch.setenv("NEXUS_DISABLE_OS_SANDBOX", "1")  # the operator's explicit kill switch
    monkeypatch.setattr(
        cli_worker,
        "run_cli_worker",
        lambda request, **kw: seen.append(request) or real(request, **kw),
    )
    command = f"{sys.executable} -c \"import pathlib; pathlib.Path('probe.txt').write_text('x'); print('CWD=' + str(pathlib.Path.cwd()))\""

    passed, results = cli_pregate.run_cli_pregate(root, [command], isolate_workspace=True)

    assert passed, results
    assert results[0]["confinement"] == "copy_only"
    assert f"CWD={root.resolve()}" not in results[0]["stdout_tail"]
    assert _tree(root) == before
    (request,) = seen
    assert request.seatbelt_profile is None
    assert request.sweep_descendants_on_exit is True and request.sweep_roots == (request.cwd,)


def test_isolated_pregate_on_macos_fails_closed_without_barrier_unless_kill_switch(
    tmp_path, monkeypatch
):
    """A broken sandbox-exec on macOS must not silently unconfine the controller's pregate."""

    root = _controller(tmp_path)

    def no_barrier(work_dir, *, readable=()):
        raise SandboxError("no_os_barrier")

    calls = []
    monkeypatch.setattr(sandbox_module, "model_sandbox", no_barrier)
    monkeypatch.setattr(cli_worker, "run_cli_worker", lambda request, **kw: calls.append(request))
    monkeypatch.setattr(cli_pregate.sys, "platform", "darwin")
    monkeypatch.delenv("NEXUS_DISABLE_OS_SANDBOX", raising=False)
    monkeypatch.setenv("NEXUS_ULTRA_REVIEW_DISABLE_OS_SANDBOX", "1")  # another lane's switch

    passed, results = cli_pregate.run_cli_pregate(root, ["python3 -c pass"], isolate_workspace=True)

    assert passed is False and calls == []
    assert results[0]["exit_code"] == -1 and "no_os_barrier" in results[0]["stderr_tail"]


def test_isolated_pregate_fails_closed_on_any_other_sandbox_error(tmp_path, monkeypatch):
    root = _controller(tmp_path)
    before = _tree(root)

    def unsafe(work_dir, *, readable=()):
        raise SandboxError("sandbox_path_unsafe")

    calls = []
    monkeypatch.setattr(sandbox_module, "model_sandbox", unsafe)
    monkeypatch.setattr(cli_worker, "run_cli_worker", lambda request, **kw: calls.append(request))
    command = f"{sys.executable} -c \"open('probe.txt', 'w').write('x')\""

    passed, results = cli_pregate.run_cli_pregate(root, [command], isolate_workspace=True)

    assert passed is False
    assert calls == []
    assert results[0]["exit_code"] == -1 and "sandbox_path_unsafe" in results[0]["stderr_tail"]
    assert _tree(root) == before


def test_isolated_pregate_repoints_root_arguments_at_the_copy(tmp_path, unconfined_worker):
    root = _controller(tmp_path)
    venv_python = root / ".venv" / "bin" / "python3"
    command = (
        f"{sys.executable} -c pass --rootdir={root.resolve()} {root.resolve()}/oracle_mod.py {root} "
        f"{root.resolve()}/build/junit.xml -o={root.resolve()}/out.json {venv_python} "
        f"{root.resolve()}/.git/config {root.resolve()}2/x.py"
    )

    passed, results = cli_pregate.run_cli_pregate(root, [command], isolate_workspace=True)

    assert passed, results
    (request,) = unconfined_worker
    copy = request.cwd
    assert request.argv[2:] == (
        f"--rootdir={copy}",
        f"{copy}/oracle_mod.py",
        copy,
        f"{copy}/build/junit.xml",  # an output that does not exist yet moves too
        f"-o={copy}/out.json",
        str(venv_python),  # the root's .venv is not copied: left as is
        f"{root.resolve()}/.git/config",
        f"{root.resolve()}2/x.py",  # a sibling path is not the root
    )
    assert results[0]["cmd"] == command


def test_isolated_pregate_fails_closed_when_copy_fails(tmp_path):
    missing = tmp_path / "missing-controller"
    passed, results = cli_pregate.run_cli_pregate(
        missing, ["python3 -c pass"], isolate_workspace=True
    )
    assert passed is False
    assert results[0]["exit_code"] == -1 and "copy failed" in results[0]["stderr_tail"]


def test_isolated_pregate_fails_closed_over_the_copy_size_cap(tmp_path, monkeypatch):
    root = _controller(tmp_path)
    for index in range(40):
        (root / f"big{index:02d}.bin").write_bytes(b"x" * 100)
    monkeypatch.setattr(cli_pregate, "_PREGATE_COPY_MAX_BYTES", 150)
    copies = []
    real_copy2 = cli_pregate.shutil.copy2
    monkeypatch.setattr(
        cli_pregate.shutil, "copy2", lambda *a, **kw: copies.append(a[0]) or real_copy2(*a, **kw)
    )
    passed, results = cli_pregate.run_cli_pregate(root, ["python3 -c pass"], isolate_workspace=True)
    assert passed is False
    assert results[0]["exit_code"] == -1 and "size cap" in results[0]["stderr_tail"]
    assert len(copies) <= 2  # the walk stops at the first file over the cap
    assert len(results[0]["stderr_tail"]) <= 500


def test_isolated_pregate_real_barrier_leaves_controller_clean(tmp_path):
    """With an OS barrier the verifier runs confined, without one only in the copy. Either way
    the controller worktree stays exactly as it was."""

    root = _controller(tmp_path)
    before = _tree(root)
    command = f"{sys.executable} -c \"import pathlib; pathlib.Path('probe.txt').write_text('x'); print('WROTE')\""

    passed, results = cli_pregate.run_cli_pregate(root, [command], isolate_workspace=True)

    assert passed, results
    assert "WROTE" in results[0]["stdout_tail"]
    assert _tree(root) == before
    expected = "os_sandbox" if _os_barrier(tmp_path) else "copy_only"
    assert results[0]["confinement"] == expected


def test_isolated_pregate_real_barrier_refuses_absolute_writes_network_and_home(tmp_path):
    """Under the real OS barrier, an absolute write into the root, the network and $HOME are
    refused. Without a barrier (Linux CI) the run is labelled copy_only instead."""

    root = _controller(tmp_path)
    home_probe = Path.home() / f".nexus-pregate-2967-{tmp_path.name}"
    code = (
        "import pathlib, socket\n"
        "def t(fn):\n"
        "    try:\n"
        "        fn()\n"
        "        return 'ALLOWED'\n"
        "    except OSError as e:\n"
        "        return type(e).__name__\n"
        f"r = [t(lambda: pathlib.Path({str(root.resolve() / 'abs.txt')!r}).write_text('x')),\n"
        f"     t(lambda: pathlib.Path({str(home_probe)!r}).write_text('x')),\n"
        "     t(lambda: socket.create_connection(('127.0.0.1', 9), timeout=2).close())]\n"
        "print('R=' + ','.join(r))\n"
    )
    script = tmp_path / "probe_2967.py"
    script.write_text(code, encoding="utf-8")
    if not _os_barrier(tmp_path):
        passed, results = cli_pregate.run_cli_pregate(
            root, ["python3 -c pass"], isolate_workspace=True
        )
        assert results[0].get("confinement") == "copy_only" or results[0]["exit_code"] == -1
        return
    before = _tree(root)
    try:
        passed, results = cli_pregate.run_cli_pregate(
            root, [f"{sys.executable} {script}"], isolate_workspace=True
        )
        assert results[0]["confinement"] == "os_sandbox", results
        assert "R=PermissionError,PermissionError,PermissionError" in results[0]["stdout_tail"], (
            results
        )
        assert _tree(root) == before
        assert not home_probe.exists()
    finally:
        home_probe.unlink(missing_ok=True)


def test_default_pregate_still_runs_in_the_root(tmp_path):
    """Callers that verify inside repair worktrees keep the old cwd (``isolate_workspace`` off)."""

    root = _controller(tmp_path)
    command = f"{sys.executable} -c \"import pathlib; print('CWD=' + str(pathlib.Path.cwd()))\""
    passed, results = cli_pregate.run_cli_pregate(root, [command])
    assert passed, results
    assert f"CWD={root.resolve()}" in results[0]["stdout_tail"]


def _exec_pregate_isolation(monkeypatch, workspace_root: Path) -> list:
    calls = []

    def fake_run(project_root, commands, timeout_per_cmd=60, *, isolate_workspace=False):
        calls.append(isolate_workspace)
        return True, []

    ports = {
        "pregate.run_cli_pregate": fake_run,
        "pregate.detect_project_language": lambda _root: {"python"},
    }
    monkeypatch.setattr(registry, "resolve_port", ports.__getitem__)
    plan = registry.CapabilityExecutionPlan(
        task_id="t2967",
        plan_id="p2967",
        constraints={"workspace_root": str(workspace_root), "verify_commands": ["python3 -c pass"]},
    )
    assert registry._exec_pregate(plan, "task").gate_passed is True
    return calls


@pytest.mark.parametrize("relative", ["", "tasks"])
def test_exec_pregate_capability_isolates_the_controller(tmp_path, monkeypatch, relative):
    root = _controller(tmp_path)
    monkeypatch.setenv("NEXUS_CANONICAL_SOURCE_ROOT", str(root))
    assert _exec_pregate_isolation(monkeypatch, root / relative) == [True]
    # A parent of the controller would contain it too.
    assert _exec_pregate_isolation(monkeypatch, tmp_path) == [True]


def test_exec_pregate_overlap_check_uses_inode_identity(tmp_path, monkeypatch):
    """A case-insensitive volume names one directory two ways; samefile still matches."""

    controller = _controller(tmp_path)
    alias = tmp_path / "CONTROLLER"
    real_samefile = registry.os.path.samefile

    def samefile(a, b):
        names = {str(Path(a)), str(Path(b))}
        return names == {str(alias), str(controller)} or real_samefile(a, b)

    monkeypatch.setattr(registry.os.path, "samefile", samefile)
    assert registry._paths_overlap(alias, controller) is True
    assert registry._paths_overlap(alias / "tasks", controller) is True
    assert registry._paths_overlap(tmp_path / "other", controller) is False


def test_exec_pregate_capability_leaves_other_workspaces_in_place(tmp_path, monkeypatch):
    """A research sprint workspace is not the controller; its pregate keeps the old cwd."""

    controller = _controller(tmp_path)
    monkeypatch.setenv("NEXUS_CANONICAL_SOURCE_ROOT", str(controller))
    sprint = tmp_path / "sprint-ws"
    sprint.mkdir()
    assert _exec_pregate_isolation(monkeypatch, sprint) == [False]


def test_verifier_input_files_treats_overlong_argument_as_not_a_file(tmp_path):
    (tmp_path / "repro.py").write_text("", encoding="utf-8")
    long_body = "x" * 5000
    assert verifier_input_files(tmp_path, ("python3", "-c", long_body)) == ()
    assert verifier_input_files(tmp_path, ("python3", long_body, "repro.py")) == ("repro.py",)


def test_verifier_input_files_survives_enametoolong_from_path_checks(tmp_path, monkeypatch):
    """Python 3.12 (the live Gateway) raises ENAMETOOLONG from ``is_symlink``/``is_file``."""

    import errno
    import pathlib

    (tmp_path / "repro.py").write_text("", encoding="utf-8")
    real = pathlib.Path.is_symlink

    def is_symlink(self):
        if len(self.name) > 255:
            raise OSError(errno.ENAMETOOLONG, "File name too long", str(self))
        return real(self)

    monkeypatch.setattr(pathlib.Path, "is_symlink", is_symlink)
    assert verifier_input_files(tmp_path, ("python3", "-c", "y" * 1200, "repro.py")) == (
        "repro.py",
    )
