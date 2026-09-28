"""Tests for content-addressed multi-host Nexus software generation sync."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOST_SYNC = ROOT / "scripts" / "ops" / "nexus-host-sync"
MANIFEST = ROOT / "scripts" / "ops" / "nexus-host-runtime-manifest.json"
DISPATCH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"
DISPATCH_INSTALLER = ROOT / "scripts" / "ops" / "install_nexus_agy_dispatch.sh"
MANAGER_SHA = "4c0e326fc72ea98f9d6d80957055a4e8a2d7387f681dea903f2a072942d2e31c"
LAUNCHD_INSTALLER = ROOT / "scripts" / "ops" / "install_nexus_host_sync_launchd.sh"
BOOTSTRAP_INSTALLER = ROOT / "scripts" / "ops" / "install_nexus_host_sync.sh"


def _run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _git(repo: Path, *args: str) -> str:
    proc = _run(["git", "-C", str(repo), *args])
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _write_fake_manager(path: Path, *, version: str = "0.2.1") -> None:
    payload = json.dumps({"version": version, "archive_sha256": MANAGER_SHA})
    path.write_text(f"#!/bin/sh\nprintf '%s\\n' '{payload}'\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _make_source_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "source"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "host-sync-test@example.invalid")
    _git(repo, "config", "user.name", "Host Sync Test")

    for source, relative in [
        (HOST_SYNC, "scripts/ops/nexus-host-sync"),
        (MANIFEST, "scripts/ops/nexus-host-runtime-manifest.json"),
        (DISPATCH, "scripts/ops/nexus-agy-dispatch"),
        (DISPATCH_INSTALLER, "scripts/ops/install_nexus_agy_dispatch.sh"),
        (ROOT / "nexus/services/agy_account_pool.py", "nexus/services/agy_account_pool.py"),
        (
            ROOT / "nexus/services/external_account_pool.py",
            "nexus/services/external_account_pool.py",
        ),
    ]:
        dest = repo / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)

    (repo / "README.md").write_text("unrelated source\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "generation one")
    return repo


def _invoke(
    source_repo: Path,
    runtime_root: Path,
    manager_python: Path,
    dispatch_target: Path,
    sync_target: Path,
    command: str,
    *,
    revision: str | None = None,
    desired_bundle: str | None = None,
) -> subprocess.CompletedProcess[str]:
    argv = [
        sys.executable,
        str(HOST_SYNC),
        "--runtime-root",
        str(runtime_root),
        "--dispatch-target",
        str(dispatch_target),
        "--sync-target",
        str(sync_target),
        "--manager-python",
        str(manager_python),
        command,
    ]
    if command in {"sync", "desired"}:
        assert revision
        argv += [
            "--revision",
            revision,
            "--source-repo",
            str(source_repo),
            "--no-fetch",
        ]
    elif command in {"status", "verify"} and desired_bundle:
        argv += ["--desired-bundle-sha256", desired_bundle]
    return _run(argv, cwd=ROOT)


def test_sync_materializes_exact_generation_and_entrypoints(tmp_path: Path) -> None:
    source_repo = _make_source_repo(tmp_path)
    revision = _git(source_repo, "rev-parse", "HEAD")
    runtime_root = tmp_path / "runtime"
    manager_python = tmp_path / "manager-python"
    dispatch_target = tmp_path / "bin" / "nexus-agy-dispatch"
    sync_target = tmp_path / "bin" / "nexus-host-sync"
    _write_fake_manager(manager_python)

    sync = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "sync",
        revision=revision,
    )

    assert sync.returncode == 0, sync.stderr + sync.stdout
    payload = json.loads(sync.stdout)
    bundle = payload["installed_bundle_sha256"]
    assert payload["state"] == "ALIGNED"
    assert payload["installed_revision"] == revision
    assert payload["desired_bundle_sha256"] == bundle
    assert payload["components"]["agy_dispatch"]["status"] == "VERIFIED"
    assert payload["components"]["agy_account_manager"]["status"] == "VERIFIED"
    assert dispatch_target.is_symlink()
    assert sync_target.is_symlink()

    receipt = json.loads(
        (runtime_root / "releases" / bundle / "host-generation.json").read_text()
    )
    assert receipt["source_revision"] == revision
    assert receipt["bundle_sha256"] == bundle
    assert receipt["schema"] == "nexus.host_generation.v1"

    observation = json.loads((runtime_root / "last-sync.json").read_text())
    assert observation["state"] == "ALIGNED"
    assert observation["desired_bundle_sha256"] == bundle

    verify = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "verify",
        desired_bundle=bundle,
    )
    assert verify.returncode == 0
    assert json.loads(verify.stdout)["state"] == "ALIGNED"


def test_second_generation_and_rollback_are_atomic_and_reversible(tmp_path: Path) -> None:
    source_repo = _make_source_repo(tmp_path)
    first_revision = _git(source_repo, "rev-parse", "HEAD")
    runtime_root = tmp_path / "runtime"
    manager_python = tmp_path / "manager-python"
    dispatch_target = tmp_path / "bin" / "nexus-agy-dispatch"
    sync_target = tmp_path / "bin" / "nexus-host-sync"
    _write_fake_manager(manager_python)

    one = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "sync",
        revision=first_revision,
    )
    assert one.returncode == 0
    first_bundle = json.loads(one.stdout)["installed_bundle_sha256"]

    dispatch = source_repo / "scripts" / "ops" / "nexus-agy-dispatch"
    dispatch.write_text(dispatch.read_text() + "\n# generation-two\n", encoding="utf-8")
    _git(source_repo, "add", "scripts/ops/nexus-agy-dispatch")
    _git(source_repo, "commit", "-m", "generation two")
    second_revision = _git(source_repo, "rev-parse", "HEAD")

    two = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "sync",
        revision=second_revision,
    )
    assert two.returncode == 0
    second_bundle = json.loads(two.stdout)["installed_bundle_sha256"]
    assert first_bundle != second_bundle
    assert (runtime_root / "current").resolve().name == second_bundle
    assert (runtime_root / "previous").resolve().name == first_bundle

    rollback = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "rollback",
    )
    assert rollback.returncode == 0, rollback.stderr + rollback.stdout
    assert (runtime_root / "current").resolve().name == first_bundle
    assert (runtime_root / "previous").resolve().name == second_bundle

    verified = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "verify",
        desired_bundle=first_bundle,
    )
    assert verified.returncode == 0
    assert json.loads(verified.stdout)["state"] == "ALIGNED"


def test_manager_dependency_drift_blocks_activation(tmp_path: Path) -> None:
    source_repo = _make_source_repo(tmp_path)
    revision = _git(source_repo, "rev-parse", "HEAD")
    runtime_root = tmp_path / "runtime"
    manager_python = tmp_path / "manager-python"
    dispatch_target = tmp_path / "bin" / "nexus-agy-dispatch"
    sync_target = tmp_path / "bin" / "nexus-host-sync"
    _write_fake_manager(manager_python, version="0.1.0")

    proc = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "sync",
        revision=revision,
    )

    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["state"] == "ERROR"
    assert payload["error"] == "AGY_ACCOUNT_MANAGER_DRIFT"
    assert not (runtime_root / "current").exists()


def test_status_detects_stale_desired_bundle(tmp_path: Path) -> None:
    source_repo = _make_source_repo(tmp_path)
    revision = _git(source_repo, "rev-parse", "HEAD")
    runtime_root = tmp_path / "runtime"
    manager_python = tmp_path / "manager-python"
    dispatch_target = tmp_path / "bin" / "nexus-agy-dispatch"
    sync_target = tmp_path / "bin" / "nexus-host-sync"
    _write_fake_manager(manager_python)

    synced = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "sync",
        revision=revision,
    )
    assert synced.returncode == 0

    other = "0" * 64
    status = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "status",
        desired_bundle=other,
    )
    assert status.returncode == 2
    payload = json.loads(status.stdout)
    assert payload["state"] == "STALE"
    assert payload["desired_bundle_sha256"] == other


def test_unrelated_main_movement_does_not_create_new_host_generation(tmp_path: Path) -> None:
    source_repo = _make_source_repo(tmp_path)
    first_revision = _git(source_repo, "rev-parse", "HEAD")
    runtime_root = tmp_path / "runtime"
    manager_python = tmp_path / "manager-python"
    dispatch_target = tmp_path / "bin" / "nexus-agy-dispatch"
    sync_target = tmp_path / "bin" / "nexus-host-sync"
    _write_fake_manager(manager_python)

    first = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "sync",
        revision=first_revision,
    )
    assert first.returncode == 0
    first_payload = json.loads(first.stdout)
    first_bundle = first_payload["installed_bundle_sha256"]

    readme = source_repo / "README.md"
    readme.write_text(readme.read_text() + "main moved\n", encoding="utf-8")
    _git(source_repo, "add", "README.md")
    _git(source_repo, "commit", "-m", "unrelated main movement")
    second_revision = _git(source_repo, "rev-parse", "HEAD")

    second = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "sync",
        revision=second_revision,
    )
    assert second.returncode == 0
    second_payload = json.loads(second.stdout)
    assert second_payload["state"] == "ALIGNED"
    assert second_payload["installed_bundle_sha256"] == first_bundle
    assert second_payload["desired_bundle_sha256"] == first_bundle
    assert second_payload["installed_revision"] == first_revision
    assert second_payload["source_revision_match"] is False
    assert len(list((runtime_root / "releases").iterdir())) == 1


def test_launchd_installer_writes_periodic_reconcile_job_without_loading(
    tmp_path: Path,
) -> None:
    import plistlib

    home = tmp_path / "home"
    plist = home / "Library" / "LaunchAgents" / "com.nexus.host-sync.plist"
    state_dir = home / ".local" / "state" / "nexus-host-sync"
    env = dict(os.environ)
    env.update(
        {
            "HOME": str(home),
            "NEXUS_HOST_REPO_ROOT": str(ROOT),
            "NEXUS_HOST_SYNC_BIN": str(home / ".local/bin/nexus-host-sync"),
            "NEXUS_HOST_SOURCE_REPO": str(home / ".cache/nexus-host-sync/Nexus-new.git"),
            "NEXUS_HOST_SYNC_PLIST": str(plist),
            "NEXUS_HOST_SYNC_STATE_DIR": str(state_dir),
            "NEXUS_HOST_SYNC_LAUNCHD_LOAD": "0",
        }
    )

    proc = subprocess.run(
        ["bash", str(LAUNCHD_INSTALLER)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    with plist.open("rb") as fh:
        data = plistlib.load(fh)
    assert data["Label"] == "com.nexus.host-sync"
    assert data["RunAtLoad"] is True
    assert data["StartInterval"] == 900
    assert data["ProgramArguments"][1:] == [
        "sync",
        "--track-ref",
        "main",
        "--source-repo",
        str(home / ".cache/nexus-host-sync/Nexus-new.git"),
    ]


def test_manager_venv_symlink_identity_is_preserved(tmp_path: Path) -> None:
    source_repo = _make_source_repo(tmp_path)
    revision = _git(source_repo, "rev-parse", "HEAD")
    runtime_root = tmp_path / "runtime"
    real_manager = tmp_path / "manager-real"
    manager_link = tmp_path / "venv" / "bin" / "python"
    manager_link.parent.mkdir(parents=True)
    _write_fake_manager(real_manager)
    manager_link.symlink_to(real_manager)
    dispatch_target = tmp_path / "bin" / "nexus-agy-dispatch"
    sync_target = tmp_path / "bin" / "nexus-host-sync"

    proc = _invoke(
        source_repo,
        runtime_root,
        manager_link,
        dispatch_target,
        sync_target,
        "sync",
        revision=revision,
    )

    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(proc.stdout)
    observed = payload["components"]["agy_account_manager"]["observed"]
    assert observed["python"] == str(manager_link)
    assert payload["state"] == "ALIGNED"


def test_bootstrap_installer_deploys_exact_host_sync_bytes(tmp_path: Path) -> None:
    target = tmp_path / "bin" / "nexus-host-sync"
    env = dict(os.environ)
    env.update(
        {
            "NEXUS_HOST_REPO_ROOT": str(ROOT),
            "NEXUS_HOST_SYNC_TARGET": str(target),
        }
    )

    proc = subprocess.run(
        ["bash", str(BOOTSTRAP_INSTALLER)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert target.read_bytes() == HOST_SYNC.read_bytes()
    mode = target.stat().st_mode
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH
