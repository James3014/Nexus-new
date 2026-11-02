"""#3130: writes into sandbox and scratch copies land in the checked directory, not through a link.

Every link and every replaced directory here lives under ``tmp_path``; the system temp dir is
pointed into ``tmp_path`` too, so the copies the code under test makes stay inside it.
"""

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

import nexus.engine.model_output_sandbox as model_sandbox_module
import nexus.executors.cli_worker as cli_worker
from nexus.core import state_root
from nexus.core.contained_write import drop_escaping_links
from nexus.engine import cli_pregate
from nexus.engine import sandbox_runner as sandbox_runner_mod
from nexus.engine.model_output_sandbox import SANDBOX_EXEC
from nexus.engine.sandbox_runner import (
    RUN_DIR_REPLACED,
    RunDirUnsafe,
    SandboxRunner,
    _capture_run_dir_identity,
)
from nexus.health import sandbox as health_sandbox
from nexus.health.sandbox import SpeculativeSandbox
from nexus.research.flow.capability_evidence import augment_local_msa_bench_evidence


@pytest.fixture(autouse=True)
def _temp_inside_tmp_path(tmp_path, monkeypatch):
    system_tmp = tmp_path / "system-tmp"
    system_tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(system_tmp))
    for name in (
        state_root.STATE_ROOT_ENV,
        state_root.CANONICAL_SOURCE_ROOT_ENV,
        state_root.TARGET_ROOT_OVERRIDE_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


def _outside(tmp_path: Path) -> Path:
    outside = tmp_path / "outside"
    outside.mkdir()
    return outside


def _source_with_links(tmp_path: Path, outside: Path) -> Path:
    src = tmp_path / "src"
    (src / "pkg").mkdir(parents=True)
    (src / "pkg" / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    # Dangling, towards a file outside the copy.
    (src / "escape.txt").symlink_to(outside / "escaped.txt")
    # Existing directory outside the copy.
    (src / "pkg" / "outdir").symlink_to(outside, target_is_directory=True)
    # Inside links stay.
    (src / "inner.py").symlink_to("pkg/mod.py")
    (src / "pkgdir").symlink_to("pkg", target_is_directory=True)
    return src


# --- shared helper -------------------------------------------------------------------------


def test_drop_escaping_links_keeps_inside_links_and_removes_the_rest(tmp_path):
    outside = _outside(tmp_path)
    src = _source_with_links(tmp_path, outside)

    dropped = drop_escaping_links(src)

    assert dropped == ("escape.txt", os.path.join("pkg", "outdir"))
    assert not os.path.lexists(src / "escape.txt")
    assert not os.path.lexists(src / "pkg" / "outdir")
    assert (src / "inner.py").is_symlink() and (src / "inner.py").read_text() == "VALUE = 1\n"
    assert (src / "pkgdir").is_symlink()
    assert list(outside.iterdir()) == []


def test_drop_escaping_links_dangling_only_keeps_links_to_existing_targets(tmp_path):
    outside = _outside(tmp_path)
    src = _source_with_links(tmp_path, outside)

    dropped = drop_escaping_links(src, dangling_only=True)

    assert dropped == ("escape.txt",)
    assert (src / "pkg" / "outdir").is_symlink()
    assert (src / "inner.py").is_symlink() and (src / "pkgdir").is_symlink()


# --- item 1: health sandbox copy --------------------------------------------------------------


def test_health_sandbox_copy_drops_dangling_links_that_leave_it(tmp_path):
    outside = _outside(tmp_path)
    src = _source_with_links(tmp_path, outside)
    sandbox = SpeculativeSandbox(src, mode="tmpdir")
    try:
        copy = sandbox.fork()
        # A relative write by path in the copy, as a runner would do.
        (copy / "escape.txt").write_text("x", encoding="utf-8")
        (copy / "inner.py").read_text(encoding="utf-8")
        assert not (outside / "escaped.txt").exists()
        assert (copy / "escape.txt").is_file() and not (copy / "escape.txt").is_symlink()
        # Links to existing targets outside are kept (tests/health/test_sandbox_safety.py).
        assert (copy / "pkg" / "outdir").is_symlink()
        assert (copy / "inner.py").is_symlink() and (copy / "pkgdir").is_symlink()
    finally:
        sandbox.cleanup()


def test_health_sandbox_docker_file_is_not_written_through_a_dangling_link(tmp_path, monkeypatch):
    outside = _outside(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (src / "Dockerfile.nexus").symlink_to(outside / "Dockerfile")
    calls = []

    class _Done:
        returncode = 0

    monkeypatch.setattr(
        health_sandbox.subprocess, "run", lambda argv, **kw: calls.append(argv) or _Done()
    )
    sandbox = SpeculativeSandbox(src, mode="docker")
    try:
        copy = sandbox.fork()
        assert not (outside / "Dockerfile").exists()
        assert (copy / "Dockerfile.nexus").is_file()
        assert not (copy / "Dockerfile.nexus").is_symlink()
    finally:
        sandbox.cleanup()
    assert calls and calls[0][:2] == ["docker", "build"]


# --- item 3: CLI pre-gate copy_only mode -------------------------------------------------------


@pytest.fixture
def unconfined_worker(monkeypatch):
    """Run the confined request without Seatbelt, as copy_only mode does on Linux."""

    real = cli_worker.run_cli_worker

    @contextmanager
    def fake_sandbox(work_dir, *, readable=()):
        yield [SANDBOX_EXEC, "-p", "(version 1)"], {"HOME": str(work_dir)}

    monkeypatch.setattr(model_sandbox_module, "model_sandbox", fake_sandbox)
    monkeypatch.setattr(
        cli_worker,
        "run_cli_worker",
        lambda request, **kw: real(replace(request, seatbelt_profile=None), **kw),
    )


def test_pregate_copy_relative_write_stays_in_the_copy(tmp_path, unconfined_worker):
    outside = _outside(tmp_path)
    root = _source_with_links(tmp_path, outside)
    command = (
        f'{sys.executable} -c "import pathlib; '
        "pathlib.Path('escape.txt').write_text('x'); "
        "pathlib.Path('pkg/outdir/planted.txt').parent.mkdir(exist_ok=True); "
        "pathlib.Path('pkg/outdir/planted.txt').write_text('x'); "
        "print(pathlib.Path('inner.py').read_text())\""
    )

    passed, results = cli_pregate.run_cli_pregate(root, [command], isolate_workspace=True)

    assert passed, results
    assert "VALUE = 1" in results[0]["stdout_tail"]
    assert list(outside.iterdir()) == []
    # The source keeps its links; only the copy lost the escaping ones.
    assert (root / "escape.txt").is_symlink() and (root / "pkg" / "outdir").is_symlink()


# --- item 2: sandbox runner run record -------------------------------------------------------


class _Proc:
    returncode = 0
    stdout = "child-stdout"
    stderr = ""


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "probe.py").write_text("print('probe-ok')\n", encoding="utf-8")
    return root


def _run_dir_from_env(env: dict) -> Path:
    return Path(env["PYTHONPATH"].split(os.pathsep)[0]).parent


def test_network_guard_is_not_written_through_a_planted_link(tmp_path):
    outside = _outside(tmp_path)
    run_dir = tmp_path / "runs" / "run_1"
    run_dir.mkdir(parents=True)
    (run_dir / "python_network_guard").symlink_to(outside, target_is_directory=True)
    runner = SandboxRunner(tmp_path)

    with pytest.raises(RunDirUnsafe):
        runner._write_python_network_guard(run_dir)

    assert list(outside.iterdir()) == []


def test_network_guard_is_written_into_a_fresh_run_dir(tmp_path):
    run_dir = tmp_path / "runs" / "run_1"
    run_dir.mkdir(parents=True)
    runner = SandboxRunner(tmp_path)

    guard_dir = runner._write_python_network_guard(run_dir, _capture_run_dir_identity(run_dir))

    guard = guard_dir / "sitecustomize.py"
    assert guard_dir == run_dir / "python_network_guard"
    assert guard.is_file() and not guard.is_symlink()
    assert "_guarded_create_connection" in guard.read_text(encoding="utf-8")


def test_output_replaced_by_link_is_not_copied_into_the_run_record(tmp_path, monkeypatch):
    outside = _outside(tmp_path)
    secret = outside / "secret.txt"
    secret.write_text("host-secret", encoding="utf-8")
    runner = SandboxRunner(_project(tmp_path))

    def fake_run(cmd, **kwargs):
        workspace = Path(kwargs["env"]["NEXUS_SANDBOX_WORKSPACE"])
        (workspace / "out.txt").symlink_to(secret)
        return _Proc()

    monkeypatch.setattr(sandbox_runner_mod, "run_reaping_process_group", fake_run)
    result = runner.run_task(
        "link-out", command=[sys.executable, "probe.py"], output_file="out.txt"
    )

    assert result["success"] is False
    assert result["error"] == "output_file_missing"
    assert result["output_artifact"] is None
    assert "output_file_refused" in result
    run_dir = Path(result["report_path"]).parent
    assert not (run_dir / "artifacts").exists()


def test_artifact_is_not_written_through_a_linked_artifacts_dir(tmp_path, monkeypatch):
    outside = _outside(tmp_path)
    runner = SandboxRunner(_project(tmp_path))

    def fake_run(cmd, **kwargs):
        workspace = Path(kwargs["env"]["NEXUS_SANDBOX_WORKSPACE"])
        (workspace / "out.txt").write_text("result", encoding="utf-8")
        (_run_dir_from_env(kwargs["env"]) / "artifacts").symlink_to(
            outside, target_is_directory=True
        )
        return _Proc()

    monkeypatch.setattr(sandbox_runner_mod, "run_reaping_process_group", fake_run)
    result = runner.run_task(
        "link-dir", command=[sys.executable, "probe.py"], output_file="out.txt"
    )

    assert result["success"] is False
    assert result["error"] == RUN_DIR_REPLACED
    assert "artifacts" in result["run_dir_mismatch"]
    assert list(outside.iterdir()) == []


def test_artifact_still_recorded_for_a_plain_output(tmp_path, monkeypatch):
    runner = SandboxRunner(_project(tmp_path))

    def fake_run(cmd, **kwargs):
        workspace = Path(kwargs["env"]["NEXUS_SANDBOX_WORKSPACE"])
        (workspace / "sub").mkdir()
        (workspace / "sub" / "out.txt").write_text("result", encoding="utf-8")
        return _Proc()

    monkeypatch.setattr(sandbox_runner_mod, "run_reaping_process_group", fake_run)
    result = runner.run_task(
        "plain", command=[sys.executable, "probe.py"], output_file="sub/out.txt"
    )

    assert result["success"] is True, result
    artifact = Path(result["output_artifact_path"])
    assert artifact.read_text(encoding="utf-8") == "result"
    assert result["output_artifact"]["size_bytes"] == len("result")


# --- item 5: capability evidence drone artifact -----------------------------------------------


def _augment(repo_root: Path, monkeypatch) -> dict:
    monkeypatch.setenv("NEXUS_ENABLE_LOCAL_SWARM_EXECUTOR", "1")
    return augment_local_msa_bench_evidence(
        repo_root,
        task_id="drone-001",
        task_desc="drone task",
        task_type="bug",
        evidence={},
        artifact_verified=True,
    )


def test_drone_artifact_is_not_written_through_a_link(tmp_path, monkeypatch):
    outside = _outside(tmp_path)
    repo = tmp_path / "repo"
    drones = repo / ".nexus" / "reports" / "drones"
    drones.mkdir(parents=True)
    (drones / "drone-001_local_msa_crystal.json").symlink_to(outside / "planted.json")

    out = _augment(repo, monkeypatch)

    assert list(outside.iterdir()) == []
    assert "drone_used" not in out


def test_drone_artifact_is_not_written_through_a_linked_directory(tmp_path, monkeypatch):
    outside = _outside(tmp_path)
    repo = tmp_path / "repo"
    (repo / ".nexus").mkdir(parents=True)
    (repo / ".nexus" / "reports").symlink_to(outside, target_is_directory=True)

    out = _augment(repo, monkeypatch)

    assert list(outside.iterdir()) == []
    assert "drone_used" not in out


def test_drone_artifact_written_for_a_plain_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()

    out = _augment(repo, monkeypatch)

    artifact = Path(out["drone_artifact_path"])
    assert out["drone_used"] is True
    assert artifact.is_file() and not artifact.is_symlink()
    assert artifact == repo / ".nexus" / "reports" / "drones" / "drone-001_local_msa_crystal.json"
