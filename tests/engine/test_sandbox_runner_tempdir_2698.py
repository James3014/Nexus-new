"""#2698: SandboxRunner keeps its working copy in a system temp dir, not the project tree.

On the live Gateway ``project_root`` is the per-deploy directory, so the working copy
must not land under it.  The run record (sandbox_result.json, artifacts) stays readable
after ``run_task`` returns and follows ``NEXUS_STATE_ROOT`` (#2688).
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

from nexus.core import state_root
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
    # cleanup=True removes the whole temp dir, network guard included.
    assert not workspace.parent.exists()
    # Nothing but the run record was written under the project.
    written = sorted(
        p.relative_to(root).as_posix() for p in (root / ".nexus").rglob("*") if p.is_file()
    )
    assert written == [f".nexus/sandbox/runs/{result['run_id']}/sandbox_result.json"]


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
