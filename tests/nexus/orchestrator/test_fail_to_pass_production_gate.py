"""Production fail-to-pass gate for opted-in repair tasks (#2274).

These tests drive the live default runtime path (real git repos, real
WorktreeManager and CandidateVerifier, stub worker) through
``SelfHostedTaskService._run_default_resumable`` into
``_finalize_runtime_candidate``.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.executors.worker_contract import (
    WorkerExecutionReceipt,
    WorkerOutcome,
    WorkerPreflight,
)
from nexus.executors.worker_registry import WorkerRegistry
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

PROBE_SCHEMA = "nexus.fail_to_pass_probe.v1"


def _git(cwd: Path, *args: str) -> str:
    env = os.environ.copy()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    return subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()


def _python_verifier(code: str) -> str:
    return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"


class _StubAdapter:
    """Worker stub that edits the leased Target and reports completion."""

    def __init__(self, provider: str, content: str, extra_files: dict | None = None):
        self.provider = provider
        self.content = content
        self.extra_files = extra_files or {}

    def preflight(self):
        return WorkerPreflight(
            provider=self.provider,
            executable=f"/bin/{self.provider}",
            executable_available=True,
            authorized=True,
            implementation_status="IMPLEMENTED",
            ready=True,
            reason="ready",
        )

    def invoke(self, contract, lease, *, prompt, **options):
        (Path(lease.target_worktree) / "bounded.txt").write_text(self.content, encoding="utf-8")
        for rel, body in self.extra_files.items():
            path = Path(lease.target_worktree) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        return WorkerExecutionReceipt(
            provider=self.provider,
            task_id=contract.task_id,
            target_worktree=lease.target_worktree,
            worker_status="COMPLETED",
            outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
            exit_code=0,
            executable_identity=f"/bin/{self.provider}",
            argv=(self.provider,),
            stdout_sha256="a" * 64,
            stderr_sha256="b" * 64,
            wall_time_ms=1,
            process_group_id=None,
            process_group_killed=False,
            timed_out=False,
            provider_calls=1,
            evidence_complete=True,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
            failure_reason=None,
        )


def _run(
    tmp_path: Path,
    monkeypatch,
    task_id: str,
    verifier_commands: list[str],
    *,
    base_files: dict | None = None,
    worker_files: dict | None = None,
    **extra,
):
    controller = tmp_path / "controller"
    controller.mkdir()
    _git(controller, "init", "-b", "main")
    _git(controller, "config", "user.name", "F2P Test")
    _git(controller, "config", "user.email", "f2p@example.test")
    (controller / "bounded.txt").write_text("broken\n", encoding="utf-8")
    for rel, body in (base_files or {}).items():
        (controller / rel).parent.mkdir(parents=True, exist_ok=True)
        (controller / rel).write_text(body, encoding="utf-8")
    _git(controller, "add", "-A")
    _git(controller, "commit", "-m", "base")
    head = _git(controller, "rev-parse", "HEAD")
    targets = tmp_path / "targets"
    targets.mkdir()
    # tmp roots are otherwise redirected next to the CWD; keep targets in tmp_path.
    monkeypatch.setenv("NEXUS_TARGET_ROOT_OVERRIDE", str(targets))
    registry = WorkerRegistry({
        provider: _StubAdapter(provider, "fixed\n", worker_files)
        for provider in ("codex", "gemini", "opencode", "mimo", "ollama")
    })
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state",
        worker_registry=registry,
        auto_reconcile=False,
    )
    request = {
        "task_id": task_id,
        "what": "Fix bounded.txt",
        "why": "Repair the broken content",
        "controller_revision": head,
        "target_base_revision": head,
        "controller_repo_root": str(controller),
        "target_repo_root": str(targets / task_id),
        "target_worktree_root": str(targets),
        "allowed_files": ["bounded.txt"],
        "verifier_commands": verifier_commands,
        "protected_contracts": ["candidate-receipt-v1"],
        "worker": "codex",
        **extra,
    }
    contract = service.build_contract(request)
    attempt_id = "a" * 32
    service._write_state(
        task_id,
        {
            "task_id": task_id,
            "status": "SUBMITTED",
            "attempt_id": attempt_id,
            "attempts": [{"attempt_id": attempt_id}],
            "request": request,
        },
    )

    def update(status, values):
        service._checkpoint(task_id, status, values, attempt_id=attempt_id)

    error = None
    result = None
    try:
        result = service._run_default_resumable(
            contract,
            request,
            update,
            task_id=task_id,
            attempt_id=attempt_id,
        )
    except RuntimeError as exc:
        # The owned-attempt runner hands a raised gate failure to
        # _finalize_runtime_failure; do the same so the terminal state is real.
        error = exc
        service._finalize_runtime_failure(task_id, attempt_id, exc)
    state = service._read_state(task_id) or {}
    return state, result, error, controller, head


def _fixed_verifier() -> str:
    return _python_verifier(
        "import sys; sys.exit(0 if open('bounded.txt').read().startswith('fixed') else 1)"
    )


def _promoted(state: dict) -> bool:
    return (
        state.get("status") in {"CANDIDATE_COMMITTED", "CANDIDATE_REF_PROTECTED", "TARGET_CLEANED"}
        or state.get("promotion_status") == "PENDING_HUMAN_APPROVAL"
        or bool(state.get("candidate_commit_created"))
    )


def test_repair_task_whose_verifier_already_passes_on_base_is_not_promoted(tmp_path, monkeypatch):
    state, _result, _error, controller, head = _run(
        tmp_path,
        monkeypatch,
        "f2p-already-pass",
        [_python_verifier("import sys; sys.exit(0)")],
        fail_to_pass_required=True,
    )

    assert not _promoted(state)
    assert state["promotion_status"] == "NOT_CREATED"
    assert state["status"] in {"FINAL_BLOCK", "RETAINED_FOR_REVIEW"}
    assert state.get("recovery_action") != "recover_verified_uncommitted_candidate"
    assert state["fail_to_pass"]["schema"] == PROBE_SCHEMA
    assert state["fail_to_pass"]["status"] == "BASE_ALREADY_PASS"
    assert state["fail_to_pass"]["required"] is True
    assert state["fail_to_pass"]["base_revision"] == head
    assert state["fail_to_pass"]["base_exit_codes"] == [0]
    assert "BASE_ALREADY_PASS" in str(state.get("error"))
    # The probe checkout must not linger or touch the controller working tree.
    assert "nexus-f2p-base-" not in _git(controller, "worktree", "list")
    with pytest.raises(RuntimeError, match="FAIL_TO_PASS_GATE_BLOCKED"):
        SelfHostedTaskService(
            state_dir=tmp_path / "state", auto_reconcile=False
        ).recover_verified_uncommitted_candidate("f2p-already-pass")
    assert _git(controller, "status", "--porcelain") == ""


def test_repair_task_with_real_fail_to_pass_is_promoted(tmp_path, monkeypatch):
    state, _result, error, controller, head = _run(
        tmp_path,
        monkeypatch,
        "f2p-real",
        [_fixed_verifier()],
        fail_to_pass_required=True,
    )

    assert error is None
    assert state["status"] in {
        "TARGET_CLEANED",
        "CANDIDATE_REF_PROTECTED",
        "CANDIDATE_COMMITTED",
        "PENDING_HUMAN_APPROVAL",
    }
    assert state["promotion_status"] == "PENDING_HUMAN_APPROVAL"
    assert state["fail_to_pass"]["schema"] == PROBE_SCHEMA
    assert state["fail_to_pass"]["status"] == "VERIFIED"
    assert state["fail_to_pass"]["required"] is True
    assert state["fail_to_pass"]["base_revision"] == head
    assert state["fail_to_pass"]["base_exit_codes"] == [1]
    assert _git(controller, "status", "--porcelain") == ""
    assert (controller / "bounded.txt").read_text(encoding="utf-8") == "broken\n"


def test_general_task_unchanged_and_marked_unproven(tmp_path, monkeypatch):
    counter = tmp_path / "counter.txt"
    verifier = _python_verifier(
        f"open({str(counter)!r}, 'a').write('x'); "
        "import sys; sys.exit(0 if open('bounded.txt').read().startswith('fixed') else 1)"
    )

    state, _result, error, _controller, _head = _run(
        tmp_path, monkeypatch, "f2p-general", [verifier]
    )

    assert error is None
    assert state["promotion_status"] == "PENDING_HUMAN_APPROVAL"
    assert state["fail_to_pass"] == {
        "schema": PROBE_SCHEMA,
        "status": "UNPROVEN",
        "reason": "fail_to_pass_unproven",
        "required": False,
    }
    # The verifier ran exactly once (candidate only); no base probe executed.
    assert counter.read_text(encoding="utf-8") == "x"


def test_required_flag_is_bound_into_contract_evidence_and_hash(tmp_path):
    service = SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False)
    base = {
        "task_id": "f2p-contract",
        "what": "Fix bounded.txt",
        "why": "Repair",
        "controller_revision": "a" * 40,
        "target_base_revision": "b" * 40,
        "controller_repo_root": str(tmp_path / "controller"),
        "target_repo_root": str(tmp_path / "targets" / "f2p-contract"),
        "target_worktree_root": str(tmp_path / "targets"),
        "allowed_files": ["bounded.txt"],
        "verifier_commands": ["python3 -c 'print(1)'"],
        "worker": "codex",
    }
    plain = service.build_contract(base)
    repair = service.build_contract({**base, "fail_to_pass_required": True})

    assert "fail_to_pass_base_verifier" not in plain.acceptance_profile.required_evidence
    assert "fail_to_pass_base_verifier" in repair.acceptance_profile.required_evidence
    assert plain.contract_hash != repair.contract_hash


def test_probe_fails_closed_when_base_cannot_be_checked_out(tmp_path):
    from types import SimpleNamespace

    from nexus.orchestrator.worktree_manager import WorktreeManager

    controller = tmp_path / "controller"
    controller.mkdir()
    _git(controller, "init", "-b", "main")
    _git(controller, "config", "user.name", "F2P Test")
    _git(controller, "config", "user.email", "f2p@example.test")
    (controller / "bounded.txt").write_text("x\n", encoding="utf-8")
    _git(controller, "add", "bounded.txt")
    _git(controller, "commit", "-m", "base")
    contract = SimpleNamespace(
        target_base_revision="0" * 40,
        controller_repo_root=str(controller),
        verifier_commands=[_python_verifier("import sys; sys.exit(1)")],
    )

    probe = SelfHostedTaskService._run_fail_to_pass_probe(
        WorktreeManager(root_dir=str(tmp_path / "targets")), contract
    )

    assert probe["status"] == "BASE_NOT_PHYSICAL_FAIL"
    assert probe["schema"] == PROBE_SCHEMA
    assert probe["required"] is True
    assert probe["base_exit_codes"] == []
    assert _git(controller, "worktree", "list").count("\n") == 0


def test_required_probe_blocks_recovery_until_it_records_verified() -> None:
    from nexus.orchestrator.self_hosted_task_service import _fail_to_pass_blocked

    def state(status: str, required: bool) -> dict:
        return {"fail_to_pass": {"status": status, "required": required}}

    # A crash between the VERIFIED checkpoint and the probe leaves PENDING.
    assert _fail_to_pass_blocked(state("PENDING", True))
    assert _fail_to_pass_blocked(state("BASE_ALREADY_PASS", True))
    assert _fail_to_pass_blocked(state("BASE_NOT_PHYSICAL_FAIL", True))
    assert not _fail_to_pass_blocked(state("VERIFIED", True))
    assert not _fail_to_pass_blocked(state("UNPROVEN", False))
    assert not _fail_to_pass_blocked({})


def test_contract_requirement_blocks_recovery_without_probe_record() -> None:
    from nexus.orchestrator.self_hosted_task_service import _fail_to_pass_blocked

    contract = {"acceptance_profile": {"required_evidence": ["fail_to_pass_base_verifier"]}}
    # The durable contract decides; a missing or tampered probe record cannot unblock it.
    assert _fail_to_pass_blocked({"contract": contract})
    assert _fail_to_pass_blocked({"contract": contract, "fail_to_pass": "VERIFIED"})
    assert _fail_to_pass_blocked({
        "contract": contract,
        "fail_to_pass": {"status": "UNPROVEN", "required": False},
    })
    assert not _fail_to_pass_blocked({
        "contract": contract,
        "fail_to_pass": {"status": "VERIFIED", "required": True},
    })
    assert not _fail_to_pass_blocked({
        "contract": {"acceptance_profile": {"required_evidence": []}}
    })


def test_probe_with_a_timed_out_base_command_is_not_verified(monkeypatch, tmp_path) -> None:
    from types import SimpleNamespace

    from nexus.executors.cli_worker import CliWorkerStatus
    from nexus.orchestrator import self_hosted_task_service as service_module
    from nexus.orchestrator.candidate_verifier import CandidateVerifier

    evidence = (
        SimpleNamespace(status=CliWorkerStatus.COMPLETED.value, exit_code=1),
        SimpleNamespace(status="TIMED_OUT", exit_code=None),
    )
    monkeypatch.setattr(
        CandidateVerifier,
        "_run_verifiers",
        staticmethod(
            lambda *_a, **_k: (False, evidence, ["verifier_failed:a", "verifier_failed:b"])
        ),
    )
    calls: list[list[str]] = []
    manager = SimpleNamespace(_run_git=lambda args, cwd=None: calls.append(list(args)) or "")
    contract = SimpleNamespace(
        target_base_revision="0" * 40,
        verifier_commands=["python -c 'raise SystemExit(1)'", "python -c 'import time'"],
        controller_repo_root=str(tmp_path),
    )
    probe = service_module.SelfHostedTaskService._run_fail_to_pass_probe(manager, contract)
    assert probe["status"] == "BASE_NOT_PHYSICAL_FAIL"
    assert any(call[:2] == ["worktree", "remove"] for call in calls)


_FIXED_TEST = "def test_fixed():\n    assert open('bounded.txt').read().startswith('fixed')\n"


def _pytest_verifier(target: str) -> str:
    return f"{shlex.quote(sys.executable)} -m pytest -q -p no:cacheprovider {target}"


def test_repair_task_whose_base_test_file_is_missing_is_not_verified(tmp_path, monkeypatch):
    # The worker adds the very test file the verifier names; base never ran it.
    state, _result, _error, controller, _head = _run(
        tmp_path,
        monkeypatch,
        "f2p-missing-test",
        [_pytest_verifier("tests/test_new.py")],
        fail_to_pass_required=True,
        allowed_files=["bounded.txt", "tests/test_new.py"],
        worker_files={"tests/test_new.py": _FIXED_TEST},
    )

    assert not _promoted(state)
    assert state["promotion_status"] == "NOT_CREATED"
    assert state["fail_to_pass"]["status"] == "BASE_NOT_PHYSICAL_FAIL"
    assert state["fail_to_pass"]["reason"] == "base_test_path_missing"
    assert state["fail_to_pass"]["base_exit_codes"] == [4]
    assert state.get("recovery_action") != "recover_verified_uncommitted_candidate"
    assert "nexus-f2p-base-" not in _git(controller, "worktree", "list")


def test_repair_task_whose_base_test_file_collects_nothing_is_not_verified(tmp_path, monkeypatch):
    state, _result, _error, _controller, _head = _run(
        tmp_path,
        monkeypatch,
        "f2p-empty-test",
        [_pytest_verifier("tests/test_new.py")],
        fail_to_pass_required=True,
        allowed_files=["bounded.txt", "tests/test_new.py"],
        base_files={"tests/test_new.py": "# no tests yet\n"},
        worker_files={"tests/test_new.py": _FIXED_TEST},
    )

    assert not _promoted(state)
    assert state["fail_to_pass"]["status"] == "BASE_NOT_PHYSICAL_FAIL"
    assert state["fail_to_pass"]["reason"] == "base_collected_no_tests"
    assert state["fail_to_pass"]["base_exit_codes"] == [5]


def test_repair_task_whose_base_lacks_the_named_test_node_is_not_verified(tmp_path, monkeypatch):
    # #2532 G0 unknown: the test file exists on base but the named node id
    # does not. pytest exits 4 ("not found"), which is not a real base failure:
    # the worker could be adding exactly that test. It must not count as F2P.
    state, _result, _error, _controller, _head = _run(
        tmp_path,
        monkeypatch,
        "f2p-missing-node",
        [_pytest_verifier("tests/test_new.py::test_fixed")],
        fail_to_pass_required=True,
        allowed_files=["bounded.txt", "tests/test_new.py"],
        base_files={"tests/test_new.py": "def test_other():\n    pass\n"},
        worker_files={"tests/test_new.py": "def test_other():\n    pass\n\n\n" + _FIXED_TEST},
    )

    assert not _promoted(state)
    assert state["fail_to_pass"]["status"] == "BASE_NOT_PHYSICAL_FAIL"
    assert state["fail_to_pass"]["reason"] == "base_collected_no_tests"
    assert state["fail_to_pass"]["base_exit_codes"] == [4]


def test_repair_task_with_a_real_failing_base_pytest_is_promoted(tmp_path, monkeypatch):
    state, _result, error, _controller, _head = _run(
        tmp_path,
        monkeypatch,
        "f2p-real-pytest",
        [_pytest_verifier("tests/test_fixed.py")],
        fail_to_pass_required=True,
        allowed_files=["bounded.txt"],
        base_files={"tests/test_fixed.py": _FIXED_TEST},
    )

    assert error is None
    assert state["promotion_status"] == "PENDING_HUMAN_APPROVAL"
    assert state["fail_to_pass"]["status"] == "VERIFIED"
    assert state["fail_to_pass"]["base_exit_codes"] == [1]
    assert "reason" not in state["fail_to_pass"]


def test_pytest_command_shapes_are_recognised_and_others_are_not():
    from nexus.orchestrator.self_hosted_task_service import _pytest_named_paths as parse

    assert parse("PYTHONDONTWRITEBYTECODE=1 pytest tests/a.py::t") == ["tests/a.py"]
    assert parse("uv run pytest -q tests/a.py") == ["tests/a.py"]
    assert parse("uv run python -m pytest tests/a.py") == ["tests/a.py"]
    assert parse("python -mpytest tests/a.py") == ["tests/a.py"]
    assert parse("python -m coverage run -m pytest tests/a.py") == ["tests/a.py"]
    assert parse("python -m pytest -k x.py tests/b.py") == ["tests/b.py"]
    assert parse("python -c 'print(1)'") is None
    assert parse("\x00pytest tests/a.py") is None
    assert parse("") is None


def test_repair_task_with_env_prefixed_pytest_and_missing_base_file_is_not_verified(
    tmp_path, monkeypatch
):
    state, _result, _error, _controller, _head = _run(
        tmp_path,
        monkeypatch,
        "f2p-env-prefix",
        ["PYTHONDONTWRITEBYTECODE=1 " + _pytest_verifier("tests/test_new.py")],
        fail_to_pass_required=True,
        allowed_files=["bounded.txt", "tests/test_new.py"],
        worker_files={"tests/test_new.py": _FIXED_TEST},
    )

    assert not _promoted(state)
    assert state["fail_to_pass"]["status"] == "BASE_NOT_PHYSICAL_FAIL"
    assert state["fail_to_pass"]["reason"] == "base_test_path_missing"


def test_base_probe_path_outside_checkout_fails_closed(tmp_path):
    from types import SimpleNamespace

    from nexus.orchestrator.self_hosted_task_service import _base_run_collected_nothing

    outside = tmp_path / "worker_tree_test.py"
    outside.write_text("def test_x():\n    assert False\n", encoding="utf-8")
    checkout = tmp_path / "base"
    checkout.mkdir()
    for target in (str(outside), "../worker_tree_test.py"):
        item = SimpleNamespace(command=f"pytest {target}", exit_code=1)
        assert _base_run_collected_nothing([item], checkout) == "base_test_path_outside_checkout"
