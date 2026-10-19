"""#2698: SandboxRunner keeps its working copy in a system temp dir, not the project tree.

On the live Gateway ``project_root`` is the per-deploy directory, so the working copy
must not land under it.  The run record (sandbox_result.json, artifacts) stays readable
after ``run_task`` returns and follows ``NEXUS_STATE_ROOT`` (#2688).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from nexus.core import state_root
from nexus.engine import sandbox_runner as sandbox_runner_mod
from nexus.engine.sandbox_runner import SandboxRunner


@pytest.fixture(autouse=True)
def _no_state_root(monkeypatch):
    for name in (
        state_root.STATE_ROOT_ENV,
        state_root.CANONICAL_SOURCE_ROOT_ENV,
        state_root.TARGET_ROOT_OVERRIDE_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "probe.py").write_text("print('probe-ok')\n", encoding="utf-8")
    return root


def _cmd() -> list[str]:
    return [sys.executable, "probe.py"]


def test_constructing_runner_writes_nothing(tmp_path):
    root = _project(tmp_path)
    SandboxRunner(root)
    assert not (root / ".nexus").exists()


def test_working_copy_is_outside_project_and_removed(tmp_path):
    root = _project(tmp_path)
    result = SandboxRunner(root).run_task("probe", command=_cmd(), timeout_sec=30)
    assert result["exit_code"] == 0, result["stderr"]
    assert "probe-ok" in result["stdout"]
    workspace = Path(result["workspace_path"])
    root_real = root.resolve()
    assert root_real not in workspace.resolve().parents
    assert workspace.parent.name.startswith("nexus-sandbox-run_")
    assert Path(tempfile.gettempdir()).resolve() in workspace.resolve().parents
    # cleanup=True removes the whole temp dir.
    assert not workspace.parent.exists()
    # Nothing but the run record (report + network guard) was written under the project.
    # Without sandbox-exec (Linux) the child may cache the guard's bytecode next to it.
    written = sorted(
        p.relative_to(root).as_posix()
        for p in (root / ".nexus").rglob("*")
        if p.is_file() and "__pycache__" not in p.parts
    )
    run = f".nexus/sandbox/runs/{result['run_id']}"
    assert written == [f"{run}/python_network_guard/sitecustomize.py", f"{run}/sandbox_result.json"]


def test_run_record_stays_at_old_path_without_state_root(tmp_path):
    # scripts/ops/capability_wiring_audit.py reads <root>/.nexus/sandbox/runs/<id>/sandbox_result.json.
    root = _project(tmp_path)
    result = SandboxRunner(root).run_task("probe", command=_cmd(), timeout_sec=30)
    report = root / ".nexus" / "sandbox" / "runs" / result["run_id"] / "sandbox_result.json"
    assert Path(result["report_path"]) == report
    assert json.loads(report.read_text(encoding="utf-8"))["stdout"].strip() == "probe-ok"


def test_cleanup_false_keeps_working_copy_in_temp(tmp_path):
    root = _project(tmp_path)
    result = SandboxRunner(root).run_task("probe", command=_cmd(), timeout_sec=30, cleanup=False)
    workspace = Path(result["workspace_path"])
    try:
        assert (workspace / "probe.py").is_file()
        assert root.resolve() not in workspace.resolve().parents
    finally:
        shutil.rmtree(workspace.parent, ignore_errors=True)


def test_per_deploy_root_writes_run_record_to_state_root(tmp_path, monkeypatch):
    root = _project(tmp_path)
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv(state_root.STATE_ROOT_ENV, str(state))
    monkeypatch.setenv(state_root.CANONICAL_SOURCE_ROOT_ENV, str(root))
    result = SandboxRunner(root).run_task("probe", command=_cmd(), timeout_sec=30)
    assert result["exit_code"] == 0, result["stderr"]
    report = Path(result["report_path"])
    assert report.is_file()
    assert state.resolve() in report.resolve().parents
    assert not (root / ".nexus").exists()
    assert not Path(result["workspace_path"]).parent.exists()


def test_temp_dir_inside_project_fails_closed(tmp_path, monkeypatch):
    root = _project(tmp_path)
    inner_tmp = root / "tmp"
    inner_tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(inner_tmp))
    with pytest.raises(RuntimeError, match="inside the project root"):
        SandboxRunner(root).run_task("probe", command=_cmd(), timeout_sec=30)
    assert list(inner_tmp.iterdir()) == []


_WRITE_RULE = re.compile(r'\((allow|deny) file-write\* \(subpath "([^"]+)"\)\)')


def _write_allowed(profile: str, path: Path) -> bool:
    """sandbox-exec semantics: deny by default, the last matching subpath rule wins."""
    allowed = False
    for verb, base in _WRITE_RULE.findall(profile):
        if str(path) == base or str(path).startswith(base.rstrip("/") + "/"):
            allowed = verb == "allow"
    return allowed


def test_network_guard_is_not_writable_by_the_sandboxed_process(tmp_path, monkeypatch):
    # Worst case from the #2781 review: the run record dir and the scratch dir both sit
    # under /tmp, which the default profile lets the process write.
    tmp_root = Path(tempfile.mkdtemp(prefix="nexus-guard-2698-", dir="/tmp"))
    try:
        root = _project(tmp_root)
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_root))
        runner = SandboxRunner(root)
        monkeypatch.setattr(runner, "has_sandbox_exec", True)
        captured: dict = {}

        class _Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs["env"]
            captured["cwd"] = kwargs["cwd"]
            return _Proc()

        monkeypatch.setattr(sandbox_runner_mod.subprocess, "run", fake_run)
        result = runner.run_task("guard", command=_cmd(), timeout_sec=5)
        assert captured["cmd"][:2] == ["sandbox-exec", "-p"]
        profile = captured["cmd"][2]
        guard_dir = Path(captured["env"]["PYTHONPATH"].split(":")[0])
        # The guard lives with the run record, not in the removable scratch dir.
        assert guard_dir.parent == Path(result["report_path"]).parent
        assert (guard_dir / "sitecustomize.py").is_file()
        for path in (guard_dir, guard_dir / "sitecustomize.py"):
            for form in (path, path.resolve()):
                assert not _write_allowed(profile, form), form
        # The parser is meaningful: the workspace itself is writable.
        assert _write_allowed(profile, Path(captured["cwd"]))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


@pytest.mark.parametrize(
    "failure",
    [subprocess.TimeoutExpired(cmd="probe", timeout=1), OSError("spawn failed")],
    ids=["timeout", "exception"],
)
def test_scratch_dir_removed_when_subprocess_fails(tmp_path, monkeypatch, failure):
    root = _project(tmp_path)
    sys_tmp = tmp_path / "sys_tmp"
    sys_tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(sys_tmp))
    runner = SandboxRunner(root)

    def fake_run(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(sandbox_runner_mod.subprocess, "run", fake_run)
    if isinstance(failure, subprocess.TimeoutExpired):
        result = runner.run_task("probe", command=_cmd(), timeout_sec=1)
        assert result["timed_out"] is True and result["error"] == "timeout"
    else:
        with pytest.raises(OSError, match="spawn failed"):
            runner.run_task("probe", command=_cmd(), timeout_sec=1)
    assert list(sys_tmp.glob("nexus-sandbox-*")) == []
