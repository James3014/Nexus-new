"""Agy write-admission model (Owner decision on #1912).

* production executors never pass ``--dangerously-skip-permissions``;
* implementation runs use ``--mode accept-edits`` and read-only roles
  ``--mode plan --sandbox``; nothing is auto-approved;
* the target must be a runtime-owned worktree outside the canonical checkout;
* any change to the canonical checkout during the run fails closed;
* a permission-blocked, empty or timed-out run is non-delivery.
"""

from __future__ import annotations

import ast
import json
import subprocess
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.executors.cli_worker import CliWorkerResult, CliWorkerStatus
from nexus.executors.worker_contract import WorkerOutcome
from nexus.executors.worker_registry import (
    AGY_PERMISSION_BYPASS_FLAGS,
    AGY_PERMISSION_MODE_ACCEPT_EDITS,
    AGY_PERMISSION_MODE_PLAN,
    AgyWorkerAdapter,
    agy_delivery_failure,
    agy_permission_bypass_flags,
    canonical_checkout_fingerprint,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BYPASS_FLAG = "--dangerously-skip-permissions"

# Reviewed allowlist: path -> (max literal occurrences, reason). Everything else
# under nexus/ and scripts/ must not carry the bypass flag in any string literal.
BYPASS_FLAG_ALLOWLIST: dict[str, tuple[int, str]] = {
    "nexus/executors/worker_registry.py": (
        1,
        "deny-list constant AGY_PERMISSION_BYPASS_FLAGS used to reject the flag",
    ),
    "scripts/bench/agy_account_lease.py": (
        1,
        "deny-list constant AGY_BYPASS_FLAGS used by assert_contained_agy_argv",
    ),
    "scripts/bench/real_world_task_runner.py": (
        1,
        "offline research benchmark harness on throwaway case dirs; not a production executor",
    ),
}


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _canonical_repo(tmp_path: Path) -> Path:
    root = tmp_path / "canonical"
    root.mkdir()
    _git(root, "init", "-q")
    (root / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    return root


def _ready(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_EXTERNAL_RUNTIME_AUTHORIZED", "1")
    monkeypatch.delenv("NEXUS_AGY_WORKER_MODEL", raising=False)
    monkeypatch.setattr("nexus.executors.worker_registry.shutil.which", lambda name: "/bin/agy")


def _result(
    request, *, stdout: bytes = b"", stderr: bytes = b"", exit_code: int | None = 0, status=None
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
    )


_OK = json.dumps({"status": "SUCCESS", "response": "edited"}).encode()


def _invoke(adapter, target: Path, **options):
    return adapter.invoke(
        SimpleNamespace(task_id="agy-admission", maximum_provider_calls=1),
        SimpleNamespace(target_worktree=str(target)),
        prompt="bounded task",
        **options,
    )


def _string_literals(path: Path) -> list[str]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_no_production_code_passes_agy_permission_bypass_flag():
    offenders: list[str] = []
    seen_allowlisted: set[str] = set()
    for base in ("nexus", "scripts"):
        for path in sorted((REPO_ROOT / base).rglob("*.py")):
            relative = path.relative_to(REPO_ROOT).as_posix()
            count = sum(BYPASS_FLAG in literal for literal in _string_literals(path))
            if not count:
                continue
            allowed = BYPASS_FLAG_ALLOWLIST.get(relative)
            if allowed is None or count > allowed[0]:
                offenders.append(f"{relative}: {count}")
            else:
                seen_allowlisted.add(relative)
    assert offenders == []
    # Keep the reviewed allowlist honest: stale entries must be removed.
    assert seen_allowlisted == set(BYPASS_FLAG_ALLOWLIST)
    assert all(reason.strip() for _, reason in BYPASS_FLAG_ALLOWLIST.values())


def test_implementation_argv_uses_accept_edits_without_auto_approve(monkeypatch, tmp_path):
    _ready(monkeypatch)
    canonical = _canonical_repo(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    captured = {}

    def fake_worker(request, on_process_group=None):
        captured["request"] = request
        return _result(request, stdout=_OK)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), target, timeout_seconds=30)

    argv = captured["request"].argv
    assert argv == (
        "--new-project",
        "--add-dir",
        str(target.resolve()),
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
    assert not set(argv) & AGY_PERMISSION_BYPASS_FLAGS
    assert captured["request"].cwd == str(target.resolve())
    assert receipt.outcome == WorkerOutcome.EXECUTION_COMPLETED.value
    assert receipt.provider_permission_mode == AGY_PERMISSION_MODE_ACCEPT_EDITS


@pytest.mark.parametrize("role", ["review", "reviewer", "plan", "planning", "read_only"])
def test_read_only_roles_use_plan_mode_with_sandbox(monkeypatch, tmp_path, role):
    _ready(monkeypatch)
    canonical = _canonical_repo(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    captured = {}

    def fake_worker(request, on_process_group=None):
        captured["argv"] = request.argv
        return _result(request, stdout=_OK)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), target, worker_role=role)

    argv = captured["argv"]
    assert argv[argv.index("--mode") + 1] == "plan"
    assert "--sandbox" in argv
    assert "accept-edits" not in argv
    assert receipt.provider_permission_mode == AGY_PERMISSION_MODE_PLAN


def test_unknown_worker_role_is_refused_before_any_process(monkeypatch, tmp_path):
    _ready(monkeypatch)
    canonical = _canonical_repo(tmp_path)
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: pytest.fail("must not start agy"),
    )
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), tmp_path, worker_role="yolo")

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.provider_calls == 0
    assert receipt.failure_reason == "agy_worker_role_unsupported"


@pytest.mark.parametrize(
    "model",
    ["--dangerously-skip-permissions", "--yolo", "--mode=auto", "m --yolo"],
)
def test_caller_supplied_flag_shapes_are_refused(monkeypatch, tmp_path, model):
    _ready(monkeypatch)
    canonical = _canonical_repo(tmp_path)
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: pytest.fail("must not start agy"),
    )
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), tmp_path, model=model)

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.provider_calls == 0
    assert receipt.failure_reason == "agy_command_shape_unsupported"


def test_env_model_cannot_inject_bypass_flag(monkeypatch, tmp_path):
    _ready(monkeypatch)
    monkeypatch.setenv("NEXUS_AGY_WORKER_MODEL", "--dangerously-skip-permissions")
    canonical = _canonical_repo(tmp_path)
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: pytest.fail("must not start agy"),
    )
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), tmp_path)

    assert receipt.failure_reason == "agy_command_shape_unsupported"
    assert receipt.provider_calls == 0


def test_bypass_flag_detection_ignores_prompt_value_only():
    assert agy_permission_bypass_flags(("--mode", "plan", "--print", BYPASS_FLAG)) == []
    assert agy_permission_bypass_flags((BYPASS_FLAG, "--print", "x")) == [BYPASS_FLAG]
    assert agy_permission_bypass_flags(("--mode=auto", "--print", "x")) == ["--mode=auto"]
    assert agy_permission_bypass_flags(("--mode", "auto", "--print", "x")) == ["--mode auto"]


@pytest.mark.parametrize("inside", ["same", "nested", "parent"])
def test_target_overlapping_canonical_checkout_is_refused(monkeypatch, tmp_path, inside):
    _ready(monkeypatch)
    canonical = _canonical_repo(tmp_path)
    if inside == "same":
        target = canonical
    elif inside == "nested":
        target = canonical / "sub" / "worktree"
        target.mkdir(parents=True)
    else:
        target = tmp_path
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: pytest.fail("must not start agy"),
    )
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), target)

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.provider_calls == 0
    assert receipt.failure_reason == "agy_target_overlaps_canonical_checkout"


@pytest.mark.parametrize("mutation", ["tracked_edit", "untracked_file", "commit"])
def test_canonical_checkout_change_during_run_fails_closed(monkeypatch, tmp_path, mutation):
    _ready(monkeypatch)
    canonical = _canonical_repo(tmp_path)
    target = tmp_path / "target"
    target.mkdir()

    def fake_worker(request, on_process_group=None):
        if mutation == "tracked_edit":
            (canonical / "tracked.txt").write_text("escaped write\n", encoding="utf-8")
        elif mutation == "untracked_file":
            (canonical / "escaped.txt").write_text("escaped\n", encoding="utf-8")
        else:
            _git(
                canonical,
                "-c",
                "user.email=t@t",
                "-c",
                "user.name=t",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "escaped",
            )
        return _result(request, stdout=_OK)

    monkeypatch.setattr("nexus.executors.worker_registry.run_cli_worker", fake_worker)
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), target)

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.evidence_complete is False
    assert receipt.failure_reason == "canonical_checkout_integrity_violation"
    # The adapter reports; it never reverts the canonical checkout itself.
    if mutation == "untracked_file":
        assert (canonical / "escaped.txt").exists()


def test_canonical_snapshot_unavailable_refuses_run(monkeypatch, tmp_path):
    _ready(monkeypatch)
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: pytest.fail("must not start agy"),
    )
    receipt = _invoke(AgyWorkerAdapter(canonical_root=not_a_repo), target)

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == "canonical_checkout_snapshot_unavailable"


def test_canonical_fingerprint_is_stable_and_detects_changes(tmp_path):
    canonical = _canonical_repo(tmp_path)
    first = canonical_checkout_fingerprint(canonical)
    assert first is not None
    assert canonical_checkout_fingerprint(canonical) == first
    (canonical / "tracked.txt").write_text("changed\n", encoding="utf-8")
    assert canonical_checkout_fingerprint(canonical) != first


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
        (json.dumps({"status": "SUCCESS", "response": "  "}).encode(), b"", "agy_no_output"),
        (json.dumps({"status": "ERROR", "response": "x"}).encode(), b"", "agy_status_not_success"),
    ],
)
def test_permission_blocked_or_empty_run_is_non_delivery(
    monkeypatch, tmp_path, stdout, stderr, reason
):
    _ready(monkeypatch)
    canonical = _canonical_repo(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: _result(request, stdout=stdout, stderr=stderr),
    )
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), target)

    assert agy_delivery_failure(stdout, stderr) == reason
    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.evidence_complete is False
    assert receipt.failure_reason == reason
    assert receipt.provider_permission_mode == AGY_PERMISSION_MODE_ACCEPT_EDITS


def test_permission_denial_is_non_delivery_on_pool_path(monkeypatch, tmp_path):
    _ready(monkeypatch)
    canonical = _canonical_repo(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    from nexus.services.agy_account_pool import AgyAccount, AgyAccountPoolManager

    pool = AgyAccountPoolManager([AgyAccount(alias="acc1", home_dir=str(tmp_path / "h1"))])
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: _result(request, stderr=_DENIED_STDERR),
    )
    receipt = _invoke(AgyWorkerAdapter(account_pool=pool, canonical_root=canonical), target)

    assert receipt.outcome == WorkerOutcome.FAILED.value
    assert receipt.failure_reason == "agy_permission_denied"
    assert receipt.provider_calls == 1


def test_timeout_is_non_delivery_with_permission_mode_recorded(monkeypatch, tmp_path):
    _ready(monkeypatch)
    canonical = _canonical_repo(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    monkeypatch.setattr(
        "nexus.executors.worker_registry.run_cli_worker",
        lambda request, on_process_group=None: _result(
            request, status=CliWorkerStatus.TIMED_OUT, exit_code=None
        ),
    )
    receipt = _invoke(AgyWorkerAdapter(canonical_root=canonical), target)

    assert receipt.outcome == WorkerOutcome.INCOMPLETE.value
    assert receipt.evidence_complete is False
    assert receipt.provider_permission_mode == AGY_PERMISSION_MODE_ACCEPT_EDITS
