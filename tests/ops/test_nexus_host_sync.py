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
QUOTA = ROOT / "scripts" / "ops" / "nexus-agy-quota"
QUOTA_INSTALLER = ROOT / "scripts" / "ops" / "install_nexus_agy_quota.sh"
AGY_REVIEW = ROOT / "scripts" / "ops" / "nexus-agy-review"
AGY_REVIEW_CANARY = ROOT / "scripts" / "ops" / "nexus-agy-review-canary"
AGY_REVIEWER_RUNTIME = ROOT / "nexus" / "services" / "agy_reviewer_runtime.py"
AGY_REVIEWER_PROFILES = ROOT / "nexus" / "services" / "agy_reviewer_profiles.py"
AGY_REVIEWER_CANARY = ROOT / "nexus" / "services" / "agy_reviewer_canary.py"
WORKFLOW_DOCTOR = ROOT / "scripts" / "ops" / "nexus-workflow-doctor"
WORKFLOW_DOCTOR_INSTALLER = ROOT / "scripts" / "ops" / "install_nexus_workflow_doctor.sh"
CANONICAL_SOURCE_ROOT = ROOT / "nexus" / "orchestrator" / "canonical_source_root.py"
EXTERNAL_DISPATCH = ROOT / "scripts" / "ops" / "nexus-external-worker-dispatch"
EXTERNAL_DISPATCH_INSTALLER = ROOT / "scripts" / "ops" / "install_nexus_external_worker_dispatch.sh"
GROK_ACCOUNTS = ROOT / "scripts" / "ops" / "nexus-grok-accounts"
HCOM_AGY_SAFE = ROOT / "scripts" / "ops" / "nexus-hcom-agy-safe"
HERMES_CONTROLLER_GUARD = ROOT / "scripts" / "ops" / "nexus-hermes-controller-guard"
HERMES_CONTINUATION_CONTROLLER = ROOT / "scripts" / "ops" / "nexus-hermes-continuation-controller"
HERMES_LAUNCHD = ROOT / "scripts" / "ops" / "nexus-hermes-launchd"
HERMES_LAUNCHD = ROOT / "scripts" / "ops" / "nexus-hermes-launchd"
MANAGER_SHA = "4c0e326fc72ea98f9d6d80957055a4e8a2d7387f681dea903f2a072942d2e31c"
LAUNCHD_INSTALLER = ROOT / "scripts" / "ops" / "install_nexus_host_sync_launchd.sh"
BOOTSTRAP_INSTALLER = ROOT / "scripts" / "ops" / "install_nexus_host_sync.sh"


def _run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _git(repo: Path, *args: str) -> str:
    proc = _run(["git", "-C", str(repo), *args])
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _write_fake_manager(
    path: Path,
    *,
    version: str = "0.2.1",
    module_integrity: str = "VERIFIED",
) -> None:
    payload = json.dumps({
        "version": version,
        "archive_sha256": MANAGER_SHA,
        "module_integrity": module_integrity,
    })
    path.write_text(f"#!/bin/sh\nprintf '%s\\n' '{payload}'\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _make_source_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "source"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "host-sync-test@example.invalid")
    _git(repo, "config", "user.name", "Host Sync Test")
    _git(repo, "remote", "add", "origin", "https://github.com/James3014/Nexus-new.git")

    for source, relative in [
        (HOST_SYNC, "scripts/ops/nexus-host-sync"),
        (MANIFEST, "scripts/ops/nexus-host-runtime-manifest.json"),
        (DISPATCH, "scripts/ops/nexus-agy-dispatch"),
        (DISPATCH_INSTALLER, "scripts/ops/install_nexus_agy_dispatch.sh"),
        (QUOTA, "scripts/ops/nexus-agy-quota"),
        (QUOTA_INSTALLER, "scripts/ops/install_nexus_agy_quota.sh"),
        (AGY_REVIEW, "scripts/ops/nexus-agy-review"),
        (AGY_REVIEW_CANARY, "scripts/ops/nexus-agy-review-canary"),
        (AGY_REVIEWER_RUNTIME, "nexus/services/agy_reviewer_runtime.py"),
        (AGY_REVIEWER_PROFILES, "nexus/services/agy_reviewer_profiles.py"),
        (AGY_REVIEWER_CANARY, "nexus/services/agy_reviewer_canary.py"),
        (WORKFLOW_DOCTOR, "scripts/ops/nexus-workflow-doctor"),
        (
            WORKFLOW_DOCTOR_INSTALLER,
            "scripts/ops/install_nexus_workflow_doctor.sh",
        ),
        (EXTERNAL_DISPATCH, "scripts/ops/nexus-external-worker-dispatch"),
        (GROK_ACCOUNTS, "scripts/ops/nexus-grok-accounts"),
        (HCOM_AGY_SAFE, "scripts/ops/nexus-hcom-agy-safe"),
        (
            HERMES_CONTROLLER_GUARD,
            "scripts/ops/nexus-hermes-controller-guard",
        ),
        (
            HERMES_CONTINUATION_CONTROLLER,
            "scripts/ops/nexus-hermes-continuation-controller",
        ),
        (HERMES_LAUNCHD, "scripts/ops/nexus-hermes-launchd"),
        (HERMES_LAUNCHD, "scripts/ops/nexus-hermes-launchd"),
        (
            EXTERNAL_DISPATCH_INSTALLER,
            "scripts/ops/install_nexus_external_worker_dispatch.sh",
        ),
        (ROOT / "nexus/services/agy_account_pool.py", "nexus/services/agy_account_pool.py"),
        (
            ROOT / "nexus/services/external_account_pool.py",
            "nexus/services/external_account_pool.py",
        ),
        (
            ROOT / "nexus/services/agy_operation_journal.py",
            "nexus/services/agy_operation_journal.py",
        ),
        (
            ROOT / "nexus/services/direct_operation_journal.py",
            "nexus/services/direct_operation_journal.py",
        ),
        (
            ROOT / "nexus/services/workflow_doctor.py",
            "nexus/services/workflow_doctor.py",
        ),
        (
            CANONICAL_SOURCE_ROOT,
            "nexus/orchestrator/canonical_source_root.py",
        ),
        (
            ROOT / "nexus/services/external_worker_runtime.py",
            "nexus/services/external_worker_runtime.py",
        ),
        (
            ROOT / "nexus/services/grok_account_pool.py",
            "nexus/services/grok_account_pool.py",
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
    canonical_source_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    quota_target = dispatch_target.parent / "nexus-agy-quota"
    workflow_doctor_target = dispatch_target.parent / "nexus-workflow-doctor"
    external_dispatch_target = dispatch_target.parent / "nexus-external-worker-dispatch"
    grok_accounts_target = dispatch_target.parent / "nexus-grok-accounts"
    argv = [
        sys.executable,
        str(HOST_SYNC),
        "--runtime-root",
        str(runtime_root),
        "--dispatch-target",
        str(dispatch_target),
        "--quota-target",
        str(quota_target),
        "--workflow-doctor-target",
        str(workflow_doctor_target),
        "--sync-target",
        str(sync_target),
        "--external-dispatch-target",
        str(external_dispatch_target),
        "--grok-accounts-target",
        str(grok_accounts_target),
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
        ]
        if command == "sync":
            argv += [
                "--canonical-source-root",
                str(canonical_source_root or source_repo),
            ]
        argv += ["--no-fetch"]
    elif command in {"status", "verify"} and desired_bundle:
        argv += ["--desired-bundle-sha256", desired_bundle]
    env = os.environ.copy()
    env["NEXUS_HCOM_AGY_TARGET"] = str(dispatch_target.parent / "hcom-agy-safe")
    env["NEXUS_HERMES_CONTROLLER_GUARD_TARGET"] = str(
        dispatch_target.parent / "nexus-hermes-controller-guard"
    )
    env["NEXUS_HERMES_CONTINUATION_CONTROLLER_TARGET"] = str(
        dispatch_target.parent / "nexus-hermes-continuation-controller"
    )
    env["NEXUS_HERMES_LAUNCHD_TARGET"] = str(
        dispatch_target.parent / "nexus-hermes-launchd"
    )
    return _run(argv, cwd=ROOT, env=env)


def test_workflow_doctor_manifest_requires_canonical_source_root(tmp_path: Path) -> None:
    source_repo = _make_source_repo(tmp_path)
    manifest_path = source_repo / "scripts/ops/nexus-host-runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["runtime_files"] = [
        entry
        for entry in manifest["runtime_files"]
        if entry["path"] != "nexus/orchestrator/canonical_source_root.py"
    ]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _git(source_repo, "add", "scripts/ops/nexus-host-runtime-manifest.json")
    _git(source_repo, "commit", "-m", "omit workflow doctor dependency")
    revision = _git(source_repo, "rev-parse", "HEAD")

    manager_python = tmp_path / "manager-python"
    _write_fake_manager(manager_python)
    proc = _invoke(
        source_repo,
        tmp_path / "runtime",
        manager_python,
        tmp_path / "bin" / "nexus-agy-dispatch",
        tmp_path / "bin" / "nexus-host-sync",
        "desired",
        revision=revision,
    )

    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["state"] == "ERROR"
    assert payload["error"] == "HOST_MANIFEST_REQUIRED_RUNTIME_PATH_MISSING"


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
    assert payload["components"]["agy_quota"]["status"] == "VERIFIED"
    assert payload["components"]["workflow_doctor"]["status"] == "VERIFIED"
    assert payload["components"]["workflow_source_binding"]["status"] == "VERIFIED"
    assert payload["components"]["workflow_source_binding"]["repo_root"] == str(
        source_repo.resolve()
    )
    assert payload["components"]["external_worker_dispatch"]["status"] == "VERIFIED"
    assert payload["components"]["grok_accounts"]["status"] == "VERIFIED"
    assert payload["components"]["agy_account_manager"]["status"] == "VERIFIED"
    assert payload["components"]["hcom_agy_safe"]["status"] == "VERIFIED"
    assert payload["components"]["hermes_controller_guard"]["status"] == "VERIFIED"
    assert payload["components"]["hermes_continuation_controller"]["status"] == "VERIFIED"
    assert payload["components"]["hermes_launchd"]["status"] == "VERIFIED"
    hcom_target = dispatch_target.parent / "hcom-agy-safe"
    assert hcom_target.is_symlink()
    assert hcom_target.resolve().read_bytes() == HCOM_AGY_SAFE.read_bytes()
    hermes_guard_target = dispatch_target.parent / "nexus-hermes-controller-guard"
    hermes_controller_target = dispatch_target.parent / "nexus-hermes-continuation-controller"
    hermes_launchd_target = dispatch_target.parent / "nexus-hermes-launchd"
    assert hermes_guard_target.is_symlink()
    assert hermes_guard_target.resolve().read_bytes() == HERMES_CONTROLLER_GUARD.read_bytes()
    assert hermes_controller_target.is_symlink()
    assert (
        hermes_controller_target.resolve().read_bytes()
        == HERMES_CONTINUATION_CONTROLLER.read_bytes()
    )
    hermes_launchd_target = dispatch_target.parent / "nexus-hermes-launchd"
    assert hermes_launchd_target.is_symlink()
    assert hermes_launchd_target.resolve().read_bytes() == HERMES_LAUNCHD.read_bytes()
    assert dispatch_target.is_symlink()
    assert (dispatch_target.parent / "nexus-agy-quota").is_symlink()
    assert (dispatch_target.parent / "nexus-workflow-doctor").is_symlink()
    assert (dispatch_target.parent / "nexus-external-worker-dispatch").is_symlink()
    grok_accounts_target = dispatch_target.parent / "nexus-grok-accounts"
    assert grok_accounts_target.is_symlink()
    assert grok_accounts_target.resolve().read_bytes() == GROK_ACCOUNTS.read_bytes()
    assert sync_target.is_symlink()

    snapshot = runtime_root / "releases" / bundle / "snapshot"
    for source, relative in [
        (AGY_REVIEW, "scripts/ops/nexus-agy-review"),
        (AGY_REVIEW_CANARY, "scripts/ops/nexus-agy-review-canary"),
        (AGY_REVIEWER_RUNTIME, "nexus/services/agy_reviewer_runtime.py"),
        (AGY_REVIEWER_PROFILES, "nexus/services/agy_reviewer_profiles.py"),
        (AGY_REVIEWER_CANARY, "nexus/services/agy_reviewer_canary.py"),
        (CANONICAL_SOURCE_ROOT, "nexus/orchestrator/canonical_source_root.py"),
    ]:
        deployed = snapshot / relative
        assert deployed.read_bytes() == source.read_bytes()
    assert (snapshot / "scripts/ops/nexus-agy-review").stat().st_mode & stat.S_IXUSR
    assert (snapshot / "scripts/ops/nexus-agy-review-canary").stat().st_mode & stat.S_IXUSR

    doctor_env = dict(os.environ)
    doctor_env["NEXUS_HOST_RUNTIME_ROOT"] = str(runtime_root)
    doctor_env["NEXUS_WORKFLOW_DOCTOR_SNAPSHOT"] = str(snapshot)
    doctor_help = subprocess.run(
        [str(dispatch_target.parent / "nexus-workflow-doctor"), "--help"],
        cwd=tmp_path,
        env=doctor_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert doctor_help.returncode == 0, doctor_help.stderr + doctor_help.stdout
    assert "--repo-root" in doctor_help.stdout

    receipt = json.loads((runtime_root / "releases" / bundle / "host-generation.json").read_text())
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


def test_status_detects_missing_workflow_source_binding(tmp_path: Path) -> None:
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
    assert sync.returncode == 0
    (runtime_root / "source-binding.json").unlink()

    status = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "status",
    )
    assert status.returncode == 2
    payload = json.loads(status.stdout)
    assert payload["state"] == "DEPENDENCY_DRIFT"
    assert payload["components"]["workflow_source_binding"]["status"] == "MISSING"


def test_sync_rejects_wrong_canonical_source_remote(tmp_path: Path) -> None:
    source_repo = _make_source_repo(tmp_path)
    revision = _git(source_repo, "rev-parse", "HEAD")
    wrong_root = tmp_path / "wrong-root"
    wrong_root.mkdir()
    _git(wrong_root, "init")
    _git(wrong_root, "remote", "add", "origin", "https://github.com/Other/Repo.git")

    manager_python = tmp_path / "manager-python"
    _write_fake_manager(manager_python)
    proc = _invoke(
        source_repo,
        tmp_path / "runtime",
        manager_python,
        tmp_path / "bin" / "nexus-agy-dispatch",
        tmp_path / "bin" / "nexus-host-sync",
        "sync",
        revision=revision,
        canonical_source_root=wrong_root,
    )

    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["state"] == "ERROR"
    assert payload["error"] == "CANONICAL_SOURCE_ROOT_REMOTE_MISMATCH"


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


def test_manager_module_integrity_drift_blocks_activation(tmp_path: Path) -> None:
    source_repo = _make_source_repo(tmp_path)
    revision = _git(source_repo, "rev-parse", "HEAD")
    runtime_root = tmp_path / "runtime"
    manager_python = tmp_path / "manager-python"
    dispatch_target = tmp_path / "bin" / "nexus-agy-dispatch"
    sync_target = tmp_path / "bin" / "nexus-host-sync"
    _write_fake_manager(manager_python, module_integrity="DRIFT")

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
    env.update({
        "HOME": str(home),
        "NEXUS_HOST_REPO_ROOT": str(ROOT),
        "NEXUS_HOST_SYNC_BIN": str(home / ".local/bin/nexus-host-sync"),
        "NEXUS_HOST_SOURCE_REPO": str(home / ".cache/nexus-host-sync/Nexus-new.git"),
        "NEXUS_HOST_SYNC_PLIST": str(plist),
        "NEXUS_HOST_SYNC_STATE_DIR": str(state_dir),
        "NEXUS_HOST_SYNC_LAUNCHD_LOAD": "0",
    })

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
        "--canonical-source-root",
        str(ROOT),
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
    env.update({
        "NEXUS_HOST_REPO_ROOT": str(ROOT),
        "NEXUS_HOST_SYNC_TARGET": str(target),
    })

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


def test_sync_repairs_incomplete_bootstrap_generation_via_verified_legacy_fallback(
    tmp_path: Path,
) -> None:
    source_repo = _make_source_repo(tmp_path)
    manifest_path = source_repo / "scripts/ops/nexus-host-runtime-manifest.json"
    current_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    legacy_manifest = json.loads(json.dumps(current_manifest))
    legacy_manifest["runtime_files"] = [
        entry
        for entry in legacy_manifest["runtime_files"]
        if entry["path"]
        not in {
            "scripts/ops/nexus-external-worker-dispatch",
            "scripts/ops/install_nexus_external_worker_dispatch.sh",
        }
    ]
    legacy_manifest["components"].pop("external_worker_dispatch", None)
    manifest_path.write_text(json.dumps(legacy_manifest, indent=2) + "\n", encoding="utf-8")
    _git(source_repo, "add", "scripts/ops/nexus-host-runtime-manifest.json")
    _git(source_repo, "commit", "-m", "legacy generation")
    legacy_revision = _git(source_repo, "rev-parse", "HEAD")

    runtime_root = tmp_path / "runtime"
    manager_python = tmp_path / "manager-python"
    dispatch_target = tmp_path / "bin" / "nexus-agy-dispatch"
    sync_target = tmp_path / "bin" / "nexus-host-sync"
    external_target = tmp_path / "bin" / "nexus-external-worker-dispatch"
    _write_fake_manager(manager_python)

    legacy = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "sync",
        revision=legacy_revision,
    )
    assert legacy.returncode == 0, legacy.stderr + legacy.stdout
    legacy_payload = json.loads(legacy.stdout)
    legacy_bundle = legacy_payload["installed_bundle_sha256"]
    assert legacy_payload["state"] == "ALIGNED"
    assert "external_worker_dispatch" not in legacy_payload["components"]
    assert not external_target.exists()
    assert not external_target.is_symlink()

    manifest_path.write_text(json.dumps(current_manifest, indent=2) + "\n", encoding="utf-8")
    _git(source_repo, "add", "scripts/ops/nexus-host-runtime-manifest.json")
    _git(source_repo, "commit", "-m", "external worker generation")
    new_revision = _git(source_repo, "rev-parse", "HEAD")

    fresh = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "sync",
        revision=new_revision,
    )
    assert fresh.returncode == 0, fresh.stderr + fresh.stdout
    fresh_payload = json.loads(fresh.stdout)
    new_bundle = fresh_payload["installed_bundle_sha256"]
    assert new_bundle != legacy_bundle

    broken_release = runtime_root / "releases" / new_bundle
    (broken_release / "bin" / "nexus-external-worker-dispatch").unlink()
    generation_path = broken_release / "host-generation.json"
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    generation.pop("external_dispatcher_sha256", None)
    generation_path.write_text(json.dumps(generation, indent=2, sort_keys=True) + "\n")
    if external_target.is_symlink():
        external_target.unlink()

    repaired = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "sync",
        revision=new_revision,
    )
    assert repaired.returncode == 0, repaired.stderr + repaired.stdout
    repaired_payload = json.loads(repaired.stdout)
    assert repaired_payload["state"] == "ALIGNED"
    assert repaired_payload["installed_bundle_sha256"] == new_bundle
    assert repaired_payload["components"]["external_worker_dispatch"]["status"] == "VERIFIED"
    assert external_target.is_symlink()
    assert (runtime_root / "current").resolve().name == new_bundle
    assert (runtime_root / "previous").resolve().name == legacy_bundle
    assert not any(
        child.name.startswith(".invalid-") for child in (runtime_root / "releases").iterdir()
    )

    rollback = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "rollback",
    )
    assert rollback.returncode == 0, rollback.stderr + rollback.stdout
    rollback_payload = json.loads(rollback.stdout)
    assert rollback_payload["state"] == "INSTALLED"
    assert rollback_payload["installed_bundle_sha256"] == legacy_bundle
    assert "external_worker_dispatch" not in rollback_payload["components"]
    assert not external_target.exists()
    assert not external_target.is_symlink()


def test_manifest_missing_canonical_source_root_fails_closed(tmp_path: Path) -> None:
    source_repo = _make_source_repo(tmp_path)
    manifest_path = source_repo / "scripts/ops/nexus-host-runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["runtime_files"] = [
        entry
        for entry in manifest["runtime_files"]
        if entry.get("path") != "nexus/orchestrator/canonical_source_root.py"
    ]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    _git(source_repo, "add", "scripts/ops/nexus-host-runtime-manifest.json")
    _git(source_repo, "commit", "-m", "remove canonical_source_root from manifest")
    revision = _git(source_repo, "rev-parse", "HEAD")

    runtime_root = tmp_path / "runtime"
    manager_python = tmp_path / "manager-python"
    dispatch_target = tmp_path / "bin" / "nexus-agy-dispatch"
    sync_target = tmp_path / "bin" / "nexus-host-sync"
    _write_fake_manager(manager_python)

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
    assert payload["error"] == "HOST_MANIFEST_REQUIRED_RUNTIME_PATH_MISSING"
    assert not (runtime_root / "current").exists()


def test_hermes_runtime_components_rollback_to_generation_without_entrypoints(
    tmp_path: Path,
) -> None:
    source_repo = _make_source_repo(tmp_path)
    manifest_path = source_repo / "scripts/ops/nexus-host-runtime-manifest.json"
    current_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    legacy_manifest = json.loads(json.dumps(current_manifest))
    legacy_manifest["runtime_files"] = [
        entry
        for entry in legacy_manifest["runtime_files"]
        if entry["path"]
        not in {
            "scripts/ops/nexus-hermes-controller-guard",
            "scripts/ops/nexus-hermes-continuation-controller",
        }
    ]
    legacy_manifest["components"].pop("hermes_controller_guard", None)
    legacy_manifest["components"].pop("hermes_continuation_controller", None)
    manifest_path.write_text(json.dumps(legacy_manifest, indent=2) + "\n", encoding="utf-8")
    _git(source_repo, "add", "scripts/ops/nexus-host-runtime-manifest.json")
    _git(source_repo, "commit", "-m", "legacy generation without Hermes runtime")
    legacy_revision = _git(source_repo, "rev-parse", "HEAD")

    runtime_root = tmp_path / "runtime"
    manager_python = tmp_path / "manager-python"
    dispatch_target = tmp_path / "bin" / "nexus-agy-dispatch"
    sync_target = tmp_path / "bin" / "nexus-host-sync"
    hermes_guard_target = dispatch_target.parent / "nexus-hermes-controller-guard"
    hermes_controller_target = dispatch_target.parent / "nexus-hermes-continuation-controller"
    _write_fake_manager(manager_python)

    legacy = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "sync",
        revision=legacy_revision,
    )
    assert legacy.returncode == 0, legacy.stderr + legacy.stdout
    assert not hermes_guard_target.exists()
    assert not hermes_guard_target.is_symlink()
    assert not hermes_controller_target.exists()
    assert not hermes_controller_target.is_symlink()

    manifest_path.write_text(json.dumps(current_manifest, indent=2) + "\n", encoding="utf-8")
    _git(source_repo, "add", "scripts/ops/nexus-host-runtime-manifest.json")
    _git(source_repo, "commit", "-m", "Hermes runtime generation")
    hermes_revision = _git(source_repo, "rev-parse", "HEAD")

    upgraded = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "sync",
        revision=hermes_revision,
    )
    assert upgraded.returncode == 0, upgraded.stderr + upgraded.stdout
    upgraded_payload = json.loads(upgraded.stdout)
    assert upgraded_payload["components"]["hermes_controller_guard"]["status"] == "VERIFIED"
    assert upgraded_payload["components"]["hermes_continuation_controller"]["status"] == "VERIFIED"
    assert hermes_guard_target.is_symlink()
    assert hermes_controller_target.is_symlink()

    rollback = _invoke(
        source_repo,
        runtime_root,
        manager_python,
        dispatch_target,
        sync_target,
        "rollback",
    )
    assert rollback.returncode == 0, rollback.stderr + rollback.stdout
    rollback_payload = json.loads(rollback.stdout)
    assert "hermes_controller_guard" not in rollback_payload["components"]
    assert "hermes_continuation_controller" not in rollback_payload["components"]
    assert not hermes_guard_target.exists()
    assert not hermes_guard_target.is_symlink()
    assert not hermes_controller_target.exists()
    assert not hermes_controller_target.is_symlink()
