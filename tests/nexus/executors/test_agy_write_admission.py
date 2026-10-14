"""Agy write-admission model (Owner decision on #1912).

* production executors never pass a permission-bypass flag;
* every run needs an explicit role: implementation runs use ``--mode
  accept-edits``, read-only roles ``--mode plan --sandbox``;
* the effective Agy settings profile may not grant commands;
* every run is wrapped in a Seatbelt profile that only lets the worker write
  the target (implementation), Agy state and a per-run temp dir;
* the protected checkouts (controller, main worktree of the target, loaded
  source root) are fingerprinted before and after; any change fails closed;
* only a parseable JSON SUCCESS result with no denied actions is delivery.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.executors import agy_write_admission as admission
from nexus.executors import cli_worker
from nexus.executors.cli_worker import (
    CliWorkerRequest,
    CliWorkerResult,
    CliWorkerStatus,
    run_cli_worker,
)
from nexus.executors.worker_contract import WorkerOutcome
from nexus.executors.worker_registry import (
    AGY_PERMISSION_BYPASS_FLAGS,
    AGY_PERMISSION_MODE_ACCEPT_EDITS,
    AGY_PERMISSION_MODE_PLAN,
    AgyWorkerAdapter,
    WorkerRegistry,
    agy_delivery_failure,
    agy_permission_bypass_flags,
    canonical_checkout_fingerprint,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
SCANNED_FLAGS = (
    "--dangerously-skip-permissions",
    "--yolo",
    "--auto-approve",
    "--dangerously-bypass-approvals-and-sandbox",
)

# Reviewed allowlist: (path, flag) -> (max occurrences, reason with issue).
BYPASS_FLAG_ALLOWLIST: dict[tuple[str, str], tuple[int, str]] = {
    ("nexus/executors/agy_write_admission.py", "--dangerously-skip-permissions"): (
        1,
        "#1912 deny-list constant AGY_PERMISSION_BYPASS_FLAGS",
    ),
    ("nexus/executors/agy_write_admission.py", "--yolo"): (1, "#1912 deny-list constant"),
    ("nexus/executors/agy_write_admission.py", "--auto-approve"): (1, "#1912 deny-list constant"),
    ("scripts/bench/agy_account_lease.py", "--dangerously-skip-permissions"): (
        1,
        "#1912 deny-list constant AGY_BYPASS_FLAGS",
    ),
    ("scripts/bench/agy_account_lease.py", "--yolo"): (1, "#1912 deny-list constant"),
    ("scripts/bench/agy_account_lease.py", "--auto-approve"): (1, "#1912 deny-list constant"),
    ("scripts/mock_gemini_cli.py", "--yolo"): (
        1,
        "#1912 test mock CLI that only parses the flag; never spawns a worker",
    ),
    ("nexus/executors/worker_registry.py", "--yolo"): (1, "#2195 cline adapter argv"),
    ("nexus/services/external_worker_runtime.py", "--auto-approve"): (
        1,
        "#2195 cline --auto-approve true|false bound to the request",
    ),
    ("nexus/orchestrator/unified_mcp_gateway.py", "--auto-approve"): (
        2,
        "#2195 cline --auto-approve false",
    ),
    ("scripts/ops/nexus-external-worker-dispatch", "--auto-approve"): (
        2,
        "#2195 cline dispatcher flag",
    ),
    ("scripts/ops/start_codex_nexus_enforced.sh", "--dangerously-bypass-approvals-and-sandbox"): (
        1,
        "#2195 codex launcher",
    ),
}

_JOINED_STRING_BOUNDARY = re.compile(r"""["']\s*\+?\s*\\?\s*["']""")


def _flag_counts(text: str) -> dict[str, int]:
    """Count flags, also when assembled from adjacent/concatenated literals."""
    joined = _JOINED_STRING_BOUNDARY.sub("", text)
    counts: dict[str, int] = {}
    for flag in SCANNED_FLAGS:
        pattern = re.compile(rf"(?<![\w-]){re.escape(flag)}(?![\w-])")
        count = len(pattern.findall(joined))
        if count:
            counts[flag] = count
    return counts


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for base in ("nexus", "scripts"):
        for path in sorted((REPO_ROOT / base).rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            if path.suffix in {".py", ".sh"}:
                files.append(path)
            elif base == "scripts" and not path.suffix:
                try:
                    with path.open("rb") as handle:
                        if handle.read(2) == b"#!":
                            files.append(path)
                except OSError:
                    continue
    return files


def test_no_production_code_passes_a_permission_bypass_flag():
    offenders: list[str] = []
    seen: set[tuple[str, str]] = set()
    for path in _scanned_files():
        relative = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for flag, count in _flag_counts(text).items():
            allowed = BYPASS_FLAG_ALLOWLIST.get((relative, flag))
            if allowed is None or count > allowed[0]:
                offenders.append(f"{relative}: {flag} x{count}")
            else:
                seen.add((relative, flag))
    assert offenders == []
    # Keep the reviewed allowlist honest: stale entries must be removed.
    assert seen == set(BYPASS_FLAG_ALLOWLIST)
    assert all(re.search(r"#\d+", reason) for _, reason in BYPASS_FLAG_ALLOWLIST.values())


def test_flag_scanner_catches_flags_assembled_from_string_parts():
    assert _flag_counts('argv = ["--dangerously-" "skip-permissions"]') == {
        "--dangerously-skip-permissions": 1
    }
    assert _flag_counts("flag = '--yo' + 'lo'") == {"--yolo": 1}
    assert _flag_counts('"--auto-approve-later"') == {}


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return completed.stdout


def _repo(tmp_path: Path, name: str = "canonical") -> Path:
    root = tmp_path / name
    root.mkdir()
    _git(root, "init", "-q")
    (root / ".gitignore").write_text(".env\n", encoding="utf-8")
    (root / "tracked.txt").write_text("base\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return root.resolve()


@pytest.fixture
def agy_home(tmp_path, monkeypatch) -> Path:
    home = tmp_path / "home"
    cli = home / ".gemini" / "antigravity-cli"
    cli.mkdir(parents=True)
    (cli / "antigravity-oauth-token").write_text("token", encoding="utf-8")
    (cli / "installation_id").write_text("install", encoding="utf-8")
    # A source profile that grants commands and hooks must never reach the run.
    (cli / "settings.json").write_text(
        json.dumps({"permissions": {"allow": ["command(*)"]}}), encoding="utf-8"
    )
    (home / ".gemini" / "config").mkdir()
    (home / ".gemini" / "config" / "hooks.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    return home.resolve()


def _ready(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.delenv("NEXUS_AGY_WORKER_MODEL", raising=False)
    monkeypatch.delenv("NEXUS_AGY_ACCOUNT_POOL_ENABLED", raising=False)
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")


def _result(
    request,
    *,
    stdout: bytes = b"",
    stderr: bytes = b"",
    exit_code: int | None = 0,
    status=None,
    descendants_swept: bool | None = True,
):
    return CliWorkerResult(
        status=status or CliWorkerStatus.COMPLETED,
        executable_identity=request.executable,
        argv=request.argv,
        cwd=request.cwd,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        wall_time_ms=3,
        process_group_id=None,
        timed_out=status is CliWorkerStatus.TIMED_OUT,
        descendants_swept=descendants_swept,
    )


_OK = json.dumps({"status": "SUCCESS", "response": "edited"}).encode()


def _invoke(adapter, target: Path, *, contract_extra=None, **options):
    options.setdefault("worker_role", "implementation")
    contract = SimpleNamespace(
        task_id="agy-admission", maximum_provider_calls=1, **(contract_extra or {})
    )
    return adapter.invoke(
        contract,
        SimpleNamespace(target_worktree=str(target)),
        prompt="bounded task",
        **options,
    )


def _no_spawn(monkeypatch) -> None:
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: pytest.fail("must not start agy"),
    )


def _target(tmp_path: Path) -> Path:
    target = tmp_path / "target"
    target.mkdir()
    return target.resolve()


# ---------------------------------------------------------------------------
# argv, role and profile admission
# ---------------------------------------------------------------------------


def test_implementation_run_uses_accept_edits_seatbelt_and_records_posture(
    monkeypatch, tmp_path, agy_home
):
    _ready(monkeypatch)
    canonical = _repo(tmp_path)
    target = _target(tmp_path)
    captured = {}

    def fake_worker(request, on_process_group=None):
        captured["request"] = request
        home = Path(request.env["HOME"])
        captured["home_files"] = {
            path.relative_to(home).as_posix() for path in home.rglob("*") if path.is_file()
        }
        captured["settings"] = json.loads(
            (home / ".gemini" / "antigravity-cli" / "settings.json").read_text()
        )
        return _result(request, stdout=_OK)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), target, timeout_seconds=30)

    request = captured["request"]
    assert request.argv == (
        "--new-project",
        "--add-dir",
        str(target),
        "--mode",
        "accept-edits",
        "--model",
        "gemini-3.8-flash-medium",
        "--output-format",
        "json",
        "--print-timeout",
        "30s",
        "--print",
        "bounded task",
    )
    assert not set(request.argv) & AGY_PERMISSION_BYPASS_FLAGS
    assert request.cwd == str(target)
    assert request.sweep_descendants_on_exit is True
    profile = request.seatbelt_profile
    assert "(deny file-write*)" in profile
    assert f'(subpath "{target}")' in profile
    assert f'(subpath "{target / ".git"}")' in profile  # .git entry stays read-only
    assert str(agy_home) not in profile  # real HOME is never writable
    assert "Keychains" not in profile
    assert str(canonical) not in profile
    run_home = Path(request.env["HOME"])
    run_tmp = Path(request.env["TMPDIR"])
    run_root = run_home.parent.parent
    assert f'(subpath "{run_root}")' in profile
    assert run_tmp.is_relative_to(run_root)
    assert captured["home_files"] == {
        ".gemini/antigravity-cli/antigravity-oauth-token",
        ".gemini/antigravity-cli/installation_id",
        ".gemini/antigravity-cli/settings.json",
    }
    assert captured["settings"] == {"permissions": {"allow": [], "deny": ["command(*)"]}}
    assert not run_root.exists()  # per-run root is removed afterwards
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert receipt.provider_permission_mode == AGY_PERMISSION_MODE_ACCEPT_EDITS
    assert str(receipt.provider_write_sandbox).startswith("seatbelt:")
    assert len(str(receipt.provider_permission_profile_sha256)) == 64


@pytest.mark.parametrize("role", ["review", "reviewer", "plan", "planning", "read_only"])
def test_read_only_roles_use_plan_mode_and_cannot_write_target(
    monkeypatch, tmp_path, agy_home, role
):
    _ready(monkeypatch)
    canonical = _repo(tmp_path)
    target = _target(tmp_path)
    captured = {}

    def fake_worker(request, on_process_group=None):
        captured["request"] = request
        return _result(request, stdout=_OK)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), target, worker_role=role)

    argv = captured["request"].argv
    assert argv[argv.index("--mode") + 1] == "plan"
    assert "--sandbox" in argv
    assert "accept-edits" not in argv
    assert f'(subpath "{target}")' not in captured["request"].seatbelt_profile
    assert receipt.provider_permission_mode == AGY_PERMISSION_MODE_PLAN


@pytest.mark.parametrize("role", [None, "", "  "])
def test_missing_role_fails_closed(monkeypatch, tmp_path, agy_home, role):
    _ready(monkeypatch)
    _no_spawn(monkeypatch)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=_repo(tmp_path)), tmp_path, worker_role=role)

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.provider_calls == 0
    assert receipt.failure_reason == "agy_worker_role_required"


def test_unknown_worker_role_is_refused_before_any_process(monkeypatch, tmp_path, agy_home):
    _ready(monkeypatch)
    _no_spawn(monkeypatch)
    receipt = _invoke(
        AgyWorkerAdapter(canonical_root=_repo(tmp_path)), tmp_path, worker_role="yolo"
    )

    assert receipt.failure_reason == "agy_worker_role_unsupported"
    assert receipt.provider_calls == 0


def test_registry_forwards_role_only_to_role_aware_adapters(monkeypatch, tmp_path, agy_home):
    _ready(monkeypatch)
    _no_spawn(monkeypatch)
    registry = WorkerRegistry.default()
    contract = SimpleNamespace(task_id="registry-role", maximum_provider_calls=1)
    lease = SimpleNamespace(target_worktree=str(tmp_path))

    receipt = registry.invoke("agy", contract, lease, prompt="x")
    assert receipt.failure_reason == "agy_worker_role_required"

    seen = {}

    class RoleBlindAdapter:
        provider = "gemini"

        def preflight(self):
            return SimpleNamespace(ready=True, reason="ready")

        def invoke(self, contract, lease, *, prompt, **options):
            seen.update(options)
            return "ok"

    registry = WorkerRegistry.default()
    monkeypatch.setitem(registry._adapters, "gemini", RoleBlindAdapter())
    assert (
        registry.invoke("gemini", contract, lease, prompt="x", worker_role="implementation") == "ok"
    )
    assert "worker_role" not in seen


def test_runtime_bridge_binds_implementation_role(monkeypatch):
    from nexus.orchestrator.runtime_coordination_bridge import _Worker

    captured = {}

    class Registry:
        def invoke(self, provider, contract, lease, **kwargs):
            captured.update(kwargs, provider=provider)
            return SimpleNamespace(provider=provider)

    service = SimpleNamespace(worker_registry=Registry())
    _Worker(service).invoke("agy", SimpleNamespace(task_id=None), object(), prompt="p")

    assert captured["worker_role"] == "implementation"
    assert captured["provider"] == "agy"


@pytest.mark.parametrize(
    "model",
    ["--dangerously-skip-permissions", "--yolo", "--mode=auto", "m --yolo"],
)
def test_caller_supplied_flag_shapes_are_refused(monkeypatch, tmp_path, agy_home, model):
    _ready(monkeypatch)
    _no_spawn(monkeypatch)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=_repo(tmp_path)), tmp_path, model=model)

    assert receipt.provider_calls == 0
    assert receipt.failure_reason == "agy_command_shape_unsupported"


def test_env_model_cannot_inject_bypass_flag(monkeypatch, tmp_path, agy_home):
    _ready(monkeypatch)
    monkeypatch.setenv("NEXUS_AGY_WORKER_MODEL", "--dangerously-skip-permissions")
    _no_spawn(monkeypatch)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=_repo(tmp_path)), tmp_path)

    assert receipt.failure_reason == "agy_command_shape_unsupported"


def test_bypass_flag_detection_ignores_prompt_value_only():
    flag = "--dangerously-skip-permissions"
    assert agy_permission_bypass_flags(("--mode", "plan", "--print", flag)) == []
    assert agy_permission_bypass_flags((flag, "--print", "x")) == [flag]
    assert agy_permission_bypass_flags(("--mode=auto", "--print", "x")) == ["--mode=auto"]
    assert agy_permission_bypass_flags(("--mode", "auto", "--print", "x")) == ["--mode auto"]


def test_read_only_run_home_denies_commands_and_writes(tmp_path):
    source = tmp_path / "src"
    (source / ".gemini" / "antigravity-cli").mkdir(parents=True)
    refusal, implementation = admission.materialize_run_home(
        source, tmp_path / "impl", read_only=False
    )
    assert refusal is None
    refusal, plan = admission.materialize_run_home(source, tmp_path / "plan", read_only=True)
    assert refusal is None
    settings = json.loads(
        (tmp_path / "plan" / ".gemini" / "antigravity-cli" / "settings.json").read_text()
    )
    assert settings["permissions"]["deny"] == ["command(*)", "write_file(*)"]
    assert len({implementation, plan}) == 2


# ---------------------------------------------------------------------------
# protected checkouts and integrity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("inside", ["same", "nested", "parent"])
def test_target_overlapping_canonical_checkout_is_refused(monkeypatch, tmp_path, agy_home, inside):
    _ready(monkeypatch)
    canonical = _repo(tmp_path)
    if inside == "same":
        target = canonical
    elif inside == "nested":
        target = canonical / "sub" / "worktree"
        target.mkdir(parents=True)
    else:
        target = tmp_path
    _no_spawn(monkeypatch)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), target)

    assert receipt.provider_calls == 0
    assert receipt.failure_reason == "agy_target_overlaps_canonical_checkout"


def _escape(kind: str, root: Path) -> None:
    if kind == "tracked_edit":
        (root / "tracked.txt").write_text("escaped write\n", encoding="utf-8")
    elif kind == "untracked_file":
        (root / "escaped.txt").write_text("escaped\n", encoding="utf-8")
    elif kind == "ignored_file":
        time.sleep(0.01)
        (root / ".env").write_text("SECRET=stolen-and-rewritten\n", encoding="utf-8")
    elif kind == "git_hook":
        (root / ".git" / "hooks" / "post-checkout").write_text("#!/bin/sh\n", encoding="utf-8")
    elif kind == "git_config":
        _git(root, "config", "core.fsmonitor", "evil")
    elif kind == "git_info":
        (root / ".git" / "info" / "attributes").write_text("* diff=evil\n", encoding="utf-8")
    else:
        _git(
            root,
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "x",
        )


ESCAPES = [
    "tracked_edit",
    "untracked_file",
    "ignored_file",
    "git_hook",
    "git_config",
    "git_info",
    "commit",
]


@pytest.mark.parametrize("kind", ESCAPES)
def test_canonical_checkout_change_during_run_fails_closed(monkeypatch, tmp_path, agy_home, kind):
    _ready(monkeypatch)
    canonical = _repo(tmp_path)
    target = _target(tmp_path)

    def fake_worker(request, on_process_group=None):
        _escape(kind, canonical)
        return _result(request, stdout=_OK)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), target)

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.evidence_complete is False
    assert receipt.failure_reason == "canonical_checkout_integrity_violation"


@pytest.mark.parametrize("where", ["controller_repo_root", "target_main_worktree"])
def test_production_roots_are_protected_without_injected_root(
    monkeypatch, tmp_path, agy_home, where
):
    """No ``canonical_root``: controller root and the target's main worktree are watched."""
    _ready(monkeypatch)
    controller = _repo(tmp_path, "controller")
    main = _repo(tmp_path, "main")
    target = (tmp_path / "targets" / "task").resolve()
    target.parent.mkdir()
    _git(main, "worktree", "add", "-q", "--detach", str(target))

    roots = admission.protected_checkout_roots(
        target=target,
        controller_repo_root=str(controller),
        canonical_source_root=REPO_ROOT,
    )
    assert [Path(root) for root in roots] == [controller, main, Path(os.path.realpath(REPO_ROOT))]

    victim = controller if where == "controller_repo_root" else main

    def fake_worker(request, on_process_group=None):
        _escape("untracked_file", victim)
        return _result(request, stdout=_OK)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = _invoke(
        AgyWorkerAdapter(), target, contract_extra={"controller_repo_root": str(controller)}
    )
    assert receipt.failure_reason == "canonical_checkout_integrity_violation"


@pytest.mark.skipif(sys.platform != "darwin", reason="case-insensitive comparison is darwin-only")
def test_protected_roots_deduplicate_case_insensitively_on_darwin(tmp_path):
    root = _repo(tmp_path)
    variant = Path(str(root).upper()) if Path(str(root).upper()).exists() else root
    roots = admission.protected_checkout_roots(
        target=_target(tmp_path), controller_repo_root=str(variant), canonical_source_root=root
    )
    assert len(roots) == 1


def test_bare_repository_deployment_layout_is_admitted(monkeypatch, tmp_path, agy_home):
    """Gateway layout: bare repo + deployment worktree + target worktree."""
    _ready(monkeypatch)
    seed = _repo(tmp_path, "seed")
    bare = (tmp_path / "repository.git").resolve()
    subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(bare)], check=True)
    deploy = (tmp_path / "deployments" / "r1").resolve()
    deploy.parent.mkdir()
    _git(bare, "worktree", "add", "-q", "--detach", str(deploy))
    target = (tmp_path / "targets" / "task").resolve()
    target.parent.mkdir()
    _git(bare, "worktree", "add", "-q", "--detach", str(target))

    assert admission.main_worktree_of(target) is None  # bare entry skipped
    assert admission.protected_checkout_roots(
        target=target, controller_repo_root=None, canonical_source_root=deploy
    ) == [deploy]
    assert admission.checkout_fingerprint(deploy) is not None

    def fake_worker(request, on_process_group=None):
        return _result(request, stdout=_OK)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=deploy), target)
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value

    def hook_writer(request, on_process_group=None):
        (bare / "hooks" / "post-checkout").write_text("#!/bin/sh\n", encoding="utf-8")
        return _result(request, stdout=_OK)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", hook_writer)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=deploy), target)
    assert receipt.failure_reason == "canonical_checkout_integrity_violation"


def test_ignored_files_in_target_main_worktree_do_not_fail_runs(monkeypatch, tmp_path, agy_home):
    """Seatbelt guards the Owner checkout; concurrent log/cache churn is not a violation."""
    _ready(monkeypatch)
    main = _repo(tmp_path, "main")
    target = (tmp_path / "targets" / "task").resolve()
    target.parent.mkdir()
    _git(main, "worktree", "add", "-q", "--detach", str(target))
    plan = admission.protected_checkout_plan(
        target=target, controller_repo_root=None, canonical_source_root=REPO_ROOT
    )
    assert (main, False) in plan

    def fake_worker(request, on_process_group=None):
        _escape("ignored_file", main)
        return _result(request, stdout=_OK)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = _invoke(AgyWorkerAdapter(), target)
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value


@pytest.mark.parametrize("layout", ["gitfile", "gitdir"])
def test_tampered_target_git_entry_fails_closed(monkeypatch, tmp_path, agy_home, layout):
    _ready(monkeypatch)
    canonical = _repo(tmp_path)
    if layout == "gitfile":
        target = (tmp_path / "targets" / "task").resolve()
        target.parent.mkdir()
        _git(canonical, "worktree", "add", "-q", "--detach", str(target))
    else:
        target = _repo(tmp_path, "standalone-target")

    def fake_worker(request, on_process_group=None):
        if layout == "gitfile":
            (target / ".git").write_text("gitdir: /tmp/attacker\n", encoding="utf-8")
        else:
            _git(target, "config", "core.fsmonitor", "evil")
        return _result(request, stdout=_OK)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), target)
    assert receipt.failure_reason == "agy_target_gitdir_tampered"


def test_target_main_worktree_is_not_protected_when_target_is_itself_main(tmp_path):
    target = _repo(tmp_path, "standalone")
    roots = admission.protected_checkout_roots(
        target=target, controller_repo_root=None, canonical_source_root=REPO_ROOT
    )
    assert target not in [Path(root) for root in roots]


def test_after_snapshot_failure_has_its_own_reason(monkeypatch, tmp_path, agy_home):
    _ready(monkeypatch)
    canonical = _repo(tmp_path)
    target = _target(tmp_path)

    def fake_worker(request, on_process_group=None):
        shutil.rmtree(canonical / ".git")
        return _result(request, stdout=_OK)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), target)

    assert receipt.failure_reason == "canonical_snapshot_failed"
    assert receipt.outcome == WorkerOutcome.FAILED.value


def test_canonical_snapshot_unavailable_refuses_run(monkeypatch, tmp_path, agy_home):
    _ready(monkeypatch)
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    _no_spawn(monkeypatch)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=not_a_repo), _target(tmp_path))

    assert receipt.failure_reason == "canonical_checkout_snapshot_unavailable"


def test_fingerprint_is_stable_and_detects_changes(tmp_path):
    canonical = _repo(tmp_path)
    first = canonical_checkout_fingerprint(canonical)
    assert first is not None
    assert canonical_checkout_fingerprint(canonical) == first
    (canonical / "tracked.txt").write_text("changed\n", encoding="utf-8")
    assert canonical_checkout_fingerprint(canonical) != first


def test_new_escaping_symlink_in_target_fails_closed(monkeypatch, tmp_path, agy_home):
    _ready(monkeypatch)
    canonical = _repo(tmp_path)
    target = _target(tmp_path)
    (target / "preexisting").symlink_to("/nonexistent/outside")  # tolerated: unchanged

    def fake_worker(request, on_process_group=None):
        (target / "env-link").symlink_to(canonical / ".env")
        return _result(request, stdout=_OK)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), target)

    assert receipt.failure_reason == "agy_target_symlink_escape"


# ---------------------------------------------------------------------------
# output classification
# ---------------------------------------------------------------------------

_DENIED_STDERR = (
    b'jetski: no output produced \xe2\x80\x94 a tool required the "command" permission that '
    b"headless mode cannot prompt for, so it was auto-denied."
)


@pytest.mark.parametrize(
    ("stdout", "stderr", "reason"),
    [
        (
            json.dumps({
                "status": "SUCCESS",
                "response": "",
                "denied_actions": [{"action": "command", "display_name": "RunCommand"}],
            }).encode(),
            _DENIED_STDERR,
            "agy_permission_denied",
        ),
        (
            json.dumps({
                "status": "SUCCESS",
                "response": "partial answer",
                "denied_actions": [{"action": "command"}],
            }).encode(),
            b"",
            "agy_permission_denied",
        ),
        (b"", _DENIED_STDERR, "agy_permission_denied"),
        (b"", b"", "agy_no_output"),
        (b"plain text answer", b"", "agy_output_unparseable"),
        (b'["status", "SUCCESS"]', b"", "agy_output_unparseable"),
        (json.dumps({"response": "x"}).encode(), b"", "agy_status_not_success"),
        (json.dumps({"status": "SUCCESS", "response": "  "}).encode(), b"", "agy_no_output"),
        (json.dumps({"status": "SUCCESS"}).encode(), b"", "agy_no_output"),
        (json.dumps({"status": "ERROR", "response": "x"}).encode(), b"", "agy_status_not_success"),
    ],
)
def test_blocked_empty_or_unparseable_run_is_non_delivery(
    monkeypatch, tmp_path, agy_home, stdout, stderr, reason
):
    _ready(monkeypatch)
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: _result(request, stdout=stdout, stderr=stderr),
    )
    receipt = _invoke(AgyWorkerAdapter(canonical_root=_repo(tmp_path)), _target(tmp_path))

    assert agy_delivery_failure(stdout, stderr) == reason
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.evidence_complete is False
    assert receipt.failure_reason == reason
    assert receipt.provider_permission_mode == AGY_PERMISSION_MODE_ACCEPT_EDITS


def test_delivery_accepts_pretty_json_with_trailing_line_and_ignores_stdout_marker():
    pretty = json.dumps({"status": "SUCCESS", "response": "done"}, indent=2).encode()
    assert agy_delivery_failure(pretty + b"\ntrailing log line\n", b"") is None
    model_text = json.dumps({
        "status": "SUCCESS",
        "response": "The CLI prints 'jetski: no output produced' when denied.",
    }).encode()
    assert agy_delivery_failure(model_text, b"") is None


def test_permission_denial_is_non_delivery_on_pool_path(monkeypatch, tmp_path, agy_home):
    _ready(monkeypatch)
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1"))])
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: _result(request, stderr=_DENIED_STDERR),
    )
    receipt = _invoke(
        AgyWorkerAdapter(account_pool=pool, canonical_root=_repo(tmp_path)), _target(tmp_path)
    )

    assert receipt.failure_reason == "agy_permission_denied"
    assert receipt.provider_calls == 1


def test_continuation_prompt_does_not_ask_for_commands(monkeypatch, tmp_path, agy_home):
    _ready(monkeypatch)
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([
        AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1")),
        AgyAccount(alias="acc2", home_dir=str(tmp_path / "h2")),
    ])
    prompts = []

    def fake_worker(request, on_process_group=None):
        prompts.append(request.argv[-1])
        if len(prompts) == 1:
            return _result(request, stderr=b"429 Rate Limit Exceeded", exit_code=1)
        return _result(request, stdout=_OK)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    contract_extra = {"maximum_provider_calls": 2}
    adapter = AgyWorkerAdapter(account_pool=pool, canonical_root=_repo(tmp_path))
    receipt = adapter.invoke(
        SimpleNamespace(task_id="cont", **contract_extra),
        SimpleNamespace(target_worktree=str(_target(tmp_path))),
        prompt="bounded task",
        worker_role="implementation",
    )

    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert "[Continuation Handoff]" in prompts[1]
    assert "run tests" not in prompts[1]
    assert "shell commands are not available" in prompts[1]


def test_timeout_is_non_delivery_with_permission_mode_recorded(monkeypatch, tmp_path, agy_home):
    _ready(monkeypatch)
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: _result(
            request, status=CliWorkerStatus.TIMED_OUT, exit_code=None
        ),
    )
    receipt = _invoke(AgyWorkerAdapter(canonical_root=_repo(tmp_path)), _target(tmp_path))

    assert receipt.outcome == WorkerOutcome.INCOMPLETE.value
    assert receipt.evidence_complete is False
    assert receipt.provider_permission_mode == AGY_PERMISSION_MODE_ACCEPT_EDITS


def test_surviving_descendant_is_non_delivery(monkeypatch, tmp_path, agy_home):
    _ready(monkeypatch)
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: _result(
            request, stdout=_OK, descendants_swept=False
        ),
    )
    receipt = _invoke(AgyWorkerAdapter(canonical_root=_repo(tmp_path)), _target(tmp_path))

    assert receipt.failure_reason == "agy_descendant_sweep_failed"


def test_missing_sandbox_exec_fails_closed(monkeypatch, tmp_path, agy_home):
    _ready(monkeypatch)
    monkeypatch.setattr(cli_worker, "_SANDBOX_EXEC", str(tmp_path / "no-sandbox-exec"))
    request = CliWorkerRequest(
        executable=sys.executable,
        argv=("-c", "print('hi')"),
        cwd=str(tmp_path),
        seatbelt_profile="(version 1)\n(allow default)\n",
    )
    result = run_cli_worker(request)
    assert result.status is CliWorkerStatus.START_FAILED
    assert result.stderr == b"seatbelt_unavailable"

    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: _result(
            request,
            status=CliWorkerStatus.START_FAILED,
            exit_code=None,
            stderr=b"seatbelt_unavailable",
        ),
    )
    receipt = _invoke(AgyWorkerAdapter(canonical_root=_repo(tmp_path)), _target(tmp_path))
    assert receipt.failure_reason == "agy_seatbelt_unavailable"


# ---------------------------------------------------------------------------
# real process behaviour (cli_worker)
# ---------------------------------------------------------------------------


def _seatbelt_usable() -> bool:
    if not admission.seatbelt_available():
        return False
    probe = subprocess.run(
        [admission.SANDBOX_EXEC_PATH, "-p", "(version 1) (allow default)", "/usr/bin/true"],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


@pytest.mark.skipif(not _seatbelt_usable(), reason="macOS sandbox-exec not usable here")
def test_seatbelt_profile_blocks_absolute_path_write_outside_target(tmp_path):
    target = _target(tmp_path)
    outside = (tmp_path / "canonical").resolve()
    outside.mkdir()
    run_tmp = (tmp_path / "run-tmp").resolve()
    (run_tmp / "home").mkdir(parents=True)
    home = run_tmp / "home"
    (target / ".git").write_text("gitdir: /expected\n", encoding="utf-8")
    profile = admission.build_seatbelt_profile(run_root=run_tmp, writable_target=target)
    code = (
        "import sys\n"
        "open(sys.argv[1] + '/inside.txt', 'w').write('ok')\n"
        "results = []\n"
        "for path in (sys.argv[2] + '/escape.txt', sys.argv[1] + '/.git'):\n"
        "    try:\n"
        "        open(path, 'w').write('x')\n"
        "        results.append('ESCAPED')\n"
        "    except OSError:\n"
        "        results.append('BLOCKED')\n"
        "print(','.join(results))\n"
    )
    result = run_cli_worker(
        CliWorkerRequest(
            executable=sys.executable,
            argv=("-c", code, str(target), str(outside)),
            cwd=str(target),
            env={"HOME": str(home), "TMPDIR": str(run_tmp)},
            seatbelt_profile=profile,
        )
    )
    assert result.exit_code == 0, result.stderr
    assert result.stdout.strip() == b"BLOCKED,BLOCKED"
    assert (target / ".git").read_text() == "gitdir: /expected\n"
    assert (target / "inside.txt").read_text() == "ok"
    assert not (outside / "escape.txt").exists()
    assert len(result.seatbelt_profile_sha256) == 64


@pytest.mark.skipif(not _seatbelt_usable(), reason="macOS sandbox-exec not usable here")
def test_seatbelt_profile_blocks_planting_agy_workspace_customizations(tmp_path):
    target = _target(tmp_path)
    (target / ".agents" / "skills").mkdir(parents=True)
    run_tmp = (tmp_path / "run-tmp").resolve()
    (run_tmp / "home").mkdir(parents=True)
    profile = admission.build_seatbelt_profile(run_root=run_tmp, writable_target=target)
    code = (
        "import os, sys\n"
        "t = sys.argv[1]\n"
        "results = []\n"
        "for rel in ('.agents/hooks.json', '.agents/mcp_config.json',\n"
        "            '.agents/plugins/p.json', '.antigravitycli/x.json',\n"
        "            '.agents/skills/ok.md'):\n"
        "    path = os.path.join(t, rel)\n"
        "    try:\n"
        "        os.makedirs(os.path.dirname(path), exist_ok=True)\n"
        "        open(path, 'w').write('x')\n"
        "        results.append('WROTE')\n"
        "    except OSError:\n"
        "        results.append('BLOCKED')\n"
        "print(','.join(results))\n"
    )
    result = run_cli_worker(
        CliWorkerRequest(
            executable=sys.executable,
            argv=("-c", code, str(target)),
            cwd=str(target),
            env={"HOME": str(run_tmp / "home"), "TMPDIR": str(run_tmp)},
            seatbelt_profile=profile,
        )
    )
    assert result.exit_code == 0, result.stderr
    assert result.stdout.strip() == b"BLOCKED,BLOCKED,BLOCKED,BLOCKED,WROTE"
    assert not (target / ".agents" / "hooks.json").exists()


def test_post_exit_sweep_kills_detached_descendants(tmp_path):
    code = (
        "import subprocess, sys\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],\n"
        "    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)\n"
        "print(child.pid)\n"
    )
    result = run_cli_worker(
        CliWorkerRequest(
            executable=sys.executable,
            argv=("-c", code),
            cwd=str(tmp_path),
            sweep_descendants_on_exit=True,
        )
    )
    pid = int(result.stdout.strip())
    assert result.descendants_swept is True
    deadline = time.monotonic() + 5
    alive = True
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            alive = False
            break
        time.sleep(0.05)
    assert alive is False
