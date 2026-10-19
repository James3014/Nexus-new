"""Characterization of the finalize-runtime cluster of ``SelfHostedTaskService`` (S11).

Big-file split step S11 (Issue #2705) moves these class members out of
``nexus/orchestrator/self_hosted_task_service.py`` into a mixin:

* ``_promotion_authority_error`` (may a production-bound task become promotable: the
  ephemeral / canonical-state / durable-Controller / Controller-revision refusals);
* the static ``_run_fail_to_pass_probe`` (the contract verifiers on a clean detached
  checkout of the base, #2274 / #2387);
* ``_finalize_runtime_candidate`` (capture -> verify -> Core -> attempt resolution ->
  Track-1 mirror -> promotion authority -> fail-to-pass -> commit -> protected ref ->
  Target cleanup) and ``_finalize_runtime_failure`` (the terminal write of a failed or
  timed-out attempt: verified-uncommitted retention, or cleanup / salvage / task-branch
  restore, then ``_checkpoint``);
* the worker-process helpers ``_run_owned_task``, ``_wait_for_owner``, ``_launch_worker``,
  the static ``_pid_alive`` and ``_terminate_owned_processes``.

These tests pin the behaviour before the move and must pass unchanged after it:

* the member table (descriptor kind, signature, docstring);
* every terminal status, checkpoint / update value and returned field of every finalize
  path, every fail-closed branch in its order with its exact code, and the exact call
  order across the collaborators (``WorktreeManager``, ``SelfHostedDevelopmentController``,
  ``CandidateVerifier``, ``CandidateCommitter``, ``resolve_attempt``) and the members
  reached through ``self``;
* the failure-only production path: a failed attempt's terminal write reaches the real
  ``_checkpoint`` and, for a declared-universe task without a receipt, the terminal Core
  record (#2346);
* that every facade-module name the moved code reads is resolved through the facade at
  call time (patched after a first call that reached the same site), including the
  module's ``__file__``: ``_launch_worker`` passes ``Path(__file__).resolve().parents[2]``
  of the facade (the repository root) as the worker source root.  ``os`` is the exception:
  other parts of the facade already load it by bare name, so ``facade.os`` is not a
  patch seam (the stale-patch guard of ``test_bigfile_split_surface`` forbids it) and the
  process-helper tests patch the ``os`` module's functions instead;
* that instance, class and subclass patches of the members reached through ``self`` are
  honoured, also from the runtime coordination bridge and the worker entry point.

No test runs a worker, reaches a real Core, sends a real signal or writes outside
``tmp_path``; the only real child processes are ``git`` on temporary repositories, one
``python -c`` verifier on a temporary base checkout and one short-lived ``python -c pass``
child that ``_pid_alive`` reaps.  No test asserts on inode numbers, file modes or other
platform details.
"""

from __future__ import annotations

import dataclasses
import inspect
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

import pytest

import nexus.orchestrator.runtime_coordination_bridge as bridge_module
import nexus.orchestrator.self_hosted_task_service as service_module
from nexus.orchestrator.ambient_core import AmbientCoreVerdictBlocked
from nexus.orchestrator.candidate_verifier import VerifiedCandidateReceipt, VerifierEvidence
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

MEMBERS = (
    "_promotion_authority_error",
    "_run_fail_to_pass_probe",
    "_finalize_runtime_candidate",
    "_finalize_runtime_failure",
    "_run_owned_task",
    "_wait_for_owner",
    "_launch_worker",
    "_pid_alive",
    "_terminate_owned_processes",
)
AUTHORITY_DOC = (
    "Return a fail-closed reason when a task cannot become promotable.\n\n"
    "Ephemeral services are test/rehearsal surfaces.  A production-bound\n"
    "task (one with a task card or lifecycle identity requirement) must be\n"
    "backed by the canonical state root and a durable, existing Controller.\n"
    "This prevents a temporary rehearsal receipt from becoming an\n"
    "approval/integration authority by accident."
)
PROBE_DOC = (
    "Run the contract verifiers on a clean detached checkout of the base.\n\n"
    "A repair task must fail its verifiers on ``target_base_revision`` and\n"
    "pass them on the candidate.  The checkout is a fresh temporary git\n"
    "worktree (never the candidate Target nor the Controller working tree)\n"
    "and is always removed.  Any infrastructure problem fails closed as\n"
    "BASE_NOT_PHYSICAL_FAIL.  The code_integrity_v1 internal check inspects\n"
    "the candidate diff and has no base meaning, so it is not re-run."
)
MEMBER_TABLE = {
    "_promotion_authority_error": (
        "function",
        "(self, *, contract: 'Optional[ArchitectTaskContract]' = None, request: "
        "'Optional[Mapping[str, Any]]' = None) -> 'Optional[str]'",
        AUTHORITY_DOC,
    ),
    "_run_fail_to_pass_probe": (
        "staticmethod",
        "(manager, contract) -> 'dict[str, Any]'",
        PROBE_DOC,
    ),
    "_finalize_runtime_candidate": (
        "function",
        "(self, contract, request, lease, state, attempts, update, *, execution, status)",
        None,
    ),
    "_finalize_runtime_failure": ("function", "(self, task_id, attempt_id, exc)", None),
    "_run_owned_task": ("function", "(self, task_id: 'str', attempt_id: 'str') -> 'None'", None),
    "_wait_for_owner": (
        "function",
        "(self, task_id: 'str', attempt_id: 'str', pid: 'int') -> 'bool'",
        None,
    ),
    "_launch_worker": (
        "function",
        "(self, task_id: 'str', attempt_id: 'str') -> 'Optional[dict[str, Any]]'",
        None,
    ),
    "_pid_alive": ("staticmethod", "(pid: 'int') -> 'bool'", None),
    "_terminate_owned_processes": (
        "function",
        "(self, task_id: 'str', *, exclude_pid: 'Optional[int]' = None) -> 'None'",
        None,
    ),
}
SCHEMA = "nexus.fail_to_pass_probe.v1"
TOKEN = "fail_to_pass_base_verifier"
# the repository root of this checkout (tests/contracts/<this file> -> parents[2])
REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# fixtures and helpers


@pytest.fixture
def service(tmp_path: Path) -> SelfHostedTaskService:
    return SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)


def _receipt(**extra: Any) -> VerifiedCandidateReceipt:
    fields: dict[str, Any] = {
        "schema": "nexus.verified_candidate_receipt.v1",
        "task_id": "task-1",
        "contract_hash": "contract",
        "lease_id": "lease",
        "candidate_state_hash": "candidate-state",
        "scope_gate_passed": True,
        "deletion_gate_passed": True,
        "controller_gate_passed": True,
        "protected_contract_gate_passed": True,
        "verifier_gate_passed": True,
        "verified": True,
        "candidate_commit_allowed": True,
        "public_claim_allowed": False,
        "production_ready": False,
        "failure_reasons": [],
        "verifier_evidence": (),
        "candidate_commit_created": False,
        "merge_performed": False,
    }
    fields.update(extra)
    return VerifiedCandidateReceipt(**fields)


def _evidence(command: str, status: str = "COMPLETED", exit_code: Optional[int] = 0) -> Any:
    return VerifierEvidence(
        command=command,
        status=status,
        exit_code=exit_code,
        stdout_sha256="5" * 64,
        stderr_sha256="6" * 64,
        wall_time_ms=1,
    )


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def _repo(path: Path) -> str:
    """A real git repository with one commit; returns HEAD."""
    path.mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.name", "Nexus Test")
    _git(path, "config", "user.email", "nexus-test@example.invalid")
    _git(path, "config", "commit.gpgsign", "false")
    (path / "a.txt").write_text("a\n", encoding="utf-8")
    _git(path, "add", "a.txt")
    _git(path, "commit", "-q", "-m", "init")
    return _git(path, "rev-parse", "HEAD")


# ---------------------------------------------------------------------------
# member table


def test_member_table() -> None:
    table = {}
    for name in MEMBERS:
        raw = inspect.getattr_static(SelfHostedTaskService, name)
        func = raw.__func__ if isinstance(raw, staticmethod) else raw
        kind = "staticmethod" if isinstance(raw, staticmethod) else type(raw).__name__
        table[name] = (kind, str(inspect.signature(func)), inspect.getdoc(func))
    assert table == MEMBER_TABLE


def test_static_members_are_the_same_through_class_and_instance(service) -> None:
    for name in ("_run_fail_to_pass_probe", "_pid_alive"):
        assert getattr(service, name) is getattr(SelfHostedTaskService, name)
        assert not inspect.ismethod(getattr(service, name))


# ---------------------------------------------------------------------------
# _promotion_authority_error


class _Proc:
    """A recording ``subprocess`` stand-in for the Controller probes."""

    def __init__(self, log: list[Any], answers: list[Any]) -> None:
        self.log, self.answers = log, list(answers)

    def run(self, argv: Any, **kwargs: Any) -> Any:
        self.log.append((tuple(argv), kwargs))
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        code, stdout = answer
        return SimpleNamespace(returncode=code, stdout=stdout)


@pytest.fixture
def production(service, monkeypatch, tmp_path) -> SimpleNamespace:
    """A non-ephemeral service on its canonical root with an existing Controller dir."""
    controller = (tmp_path / "controller").resolve()
    controller.mkdir()
    monkeypatch.setattr(service, "ephemeral", False)
    monkeypatch.setattr(service, "canonical_state_dir", lambda: service.state_dir)
    monkeypatch.setattr(service_module, "_temporary_state_roots", lambda: ())
    log: list[Any] = []
    return SimpleNamespace(
        service=service,
        controller=controller,
        log=log,
        contract=SimpleNamespace(controller_repo_root=str(controller), controller_revision="R1"),
        request={"task_card_required": True},
        use=lambda answers: monkeypatch.setattr(service_module, "subprocess", _Proc(log, answers)),
    )


def _probe_kwargs(cwd: Path) -> dict[str, Any]:
    return {"cwd": cwd, "capture_output": True, "text": True, "check": False}


def test_authority_not_production_bound_is_never_refused(service, monkeypatch) -> None:
    monkeypatch.setattr(service_module, "subprocess", _Proc([], []))
    for request in (None, {}, {"task_card_required": False, "lifecycle_identity_required": 0}):
        assert service._promotion_authority_error(request=request) is None
        assert service._promotion_authority_error(contract=object(), request=request) is None
    assert service._promotion_authority_error() is None


@pytest.mark.parametrize("flag", ["task_card_required", "lifecycle_identity_required"])
def test_authority_ephemeral_production_bound_is_refused_first(service, monkeypatch, flag) -> None:
    monkeypatch.setattr(
        service, "canonical_state_dir", lambda: (_ for _ in ()).throw(AssertionError)
    )
    assert service._promotion_authority_error(request={flag: "yes"}) == (
        "EPHEMERAL_PROMOTION_FORBIDDEN: rehearsal state cannot become a promotable Candidate"
    )


def test_authority_without_a_contract_is_not_probed(production) -> None:
    production.use([])
    assert production.service._promotion_authority_error(request=production.request) is None
    assert production.log == []


def test_authority_requires_the_canonical_state_root(production, monkeypatch, tmp_path) -> None:
    production.use([])
    monkeypatch.setattr(production.service, "canonical_state_dir", lambda: tmp_path / "elsewhere")
    assert (
        production.service._promotion_authority_error(
            contract=production.contract, request=production.request
        )
        == "CANONICAL_STATE_REQUIRED: production Candidate must use the canonical state root"
    )


def test_authority_requires_an_existing_controller(production, tmp_path) -> None:
    production.use([])
    missing = tmp_path / "missing"
    contract = SimpleNamespace(controller_repo_root=str(missing), controller_revision="R1")
    assert (
        production.service._promotion_authority_error(
            contract=contract, request={"lifecycle_identity_required": True}
        )
        == f"CONTROLLER_MISSING: {missing.resolve()}"
    )
    assert production.log == []


@pytest.mark.parametrize("where", ["equal", "below"])
def test_authority_refuses_a_temporary_controller(production, monkeypatch, where) -> None:
    production.use([])
    root = production.controller if where == "equal" else production.controller.parent
    monkeypatch.setattr(service_module, "_temporary_state_roots", lambda: (Path("/nowhere"), root))
    assert (
        production.service._promotion_authority_error(
            contract=production.contract, request=production.request
        )
        == f"DURABLE_CONTROLLER_REQUIRED: temporary Controller is not promotable: {production.controller}"
    )
    assert production.log == []


def test_authority_probe_os_error(production) -> None:
    production.use([OSError("no git")])
    assert (
        production.service._promotion_authority_error(
            contract=production.contract, request=production.request
        )
        == "CONTROLLER_PROBE_FAILED: no git"
    )
    assert production.log == [
        (("git", "rev-parse", "--show-toplevel"), _probe_kwargs(production.controller))
    ]


@pytest.mark.parametrize(
    "answer",
    [(128, ""), (1, "{root}"), (0, "{root}/sub"), (0, "")],
    ids=["exit-128", "exit-1-right-root", "other-toplevel", "empty-toplevel"],
)
def test_authority_controller_must_be_its_own_repository(production, answer) -> None:
    code, stdout = answer
    production.use([(code, stdout.replace("{root}", str(production.controller)) + "\n")])
    assert (
        production.service._promotion_authority_error(
            contract=production.contract, request=production.request
        )
        == f"CONTROLLER_NOT_A_REPOSITORY: {production.controller}"
    )
    assert len(production.log) == 1


def test_authority_revision_probe_os_error(production) -> None:
    production.use([(0, f"{production.controller}\n"), OSError("gone")])
    assert (
        production.service._promotion_authority_error(
            contract=production.contract, request=production.request
        )
        == "CONTROLLER_REVISION_PROBE_FAILED: gone"
    )
    assert production.log == [
        (("git", "rev-parse", "--show-toplevel"), _probe_kwargs(production.controller)),
        (("git", "rev-parse", "HEAD"), _probe_kwargs(production.controller)),
    ]


def test_authority_revision_mismatch(production) -> None:
    production.use([(0, f"{production.controller}\n"), (0, " R2 \n")])
    assert (
        production.service._promotion_authority_error(
            contract=production.contract, request=production.request
        )
        == "CONTROLLER_REVISION_MISMATCH: expected R1, got R2"
    )


def test_authority_revision_probe_exit_code_is_not_checked(production) -> None:
    production.use([(0, f"{production.controller}\n"), (128, "R1\n")])
    assert (
        production.service._promotion_authority_error(
            contract=production.contract, request=production.request
        )
        is None
    )


@pytest.mark.parametrize("revision", ["R1", "", None])
def test_authority_passes_on_a_matching_or_unpinned_revision(production, revision) -> None:
    production.use([(0, f"{production.controller}\n"), (0, "R1\n")])
    contract = SimpleNamespace(
        controller_repo_root=str(production.controller), controller_revision=revision
    )
    assert (
        production.service._promotion_authority_error(contract=contract, request=production.request)
        is None
    )
    assert [argv for argv, _ in production.log] == [
        ("git", "rev-parse", "--show-toplevel"),
        ("git", "rev-parse", "HEAD"),
    ]


def test_authority_with_a_real_controller_repository(service, monkeypatch, tmp_path) -> None:
    controller = (tmp_path / "real-controller").resolve()
    head = _repo(controller)
    monkeypatch.setattr(service, "ephemeral", False)
    monkeypatch.setattr(service, "canonical_state_dir", lambda: service.state_dir)
    monkeypatch.setattr(service_module, "_temporary_state_roots", lambda: ())
    request = {"task_card_required": True}
    good = SimpleNamespace(controller_repo_root=str(controller), controller_revision=head)
    assert service._promotion_authority_error(contract=good, request=request) is None
    stale = SimpleNamespace(controller_repo_root=str(controller), controller_revision="0" * 40)
    assert service._promotion_authority_error(contract=stale, request=request) == (
        f"CONTROLLER_REVISION_MISMATCH: expected {'0' * 40}, got {head}"
    )
    (controller / "sub").mkdir()
    nested = SimpleNamespace(controller_repo_root=str(controller / "sub"), controller_revision=head)
    assert service._promotion_authority_error(contract=nested, request=request) == (
        f"CONTROLLER_NOT_A_REPOSITORY: {controller / 'sub'}"
    )


def test_authority_temporary_roots_default_covers_tmp_path(service, monkeypatch, tmp_path) -> None:
    # the real _temporary_state_roots: pytest's tmp_path lives below the system temp dir
    controller = (tmp_path / "c").resolve()
    controller.mkdir()
    monkeypatch.setattr(service, "ephemeral", False)
    monkeypatch.setattr(service, "canonical_state_dir", lambda: service.state_dir)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    contract = SimpleNamespace(controller_repo_root=str(controller), controller_revision="R")
    assert (
        service._promotion_authority_error(contract=contract, request={"task_card_required": True})
        == f"DURABLE_CONTROLLER_REQUIRED: temporary Controller is not promotable: {controller}"
    )


def test_authority_reaches_canonical_state_dir_through_self(
    production, monkeypatch, tmp_path
) -> None:
    production.use([])
    calls: list[str] = []
    monkeypatch.setattr(
        production.service, "canonical_state_dir", lambda: (calls.append("x"), tmp_path / "o")[1]
    )
    assert production.service._promotion_authority_error(
        contract=production.contract, request=production.request
    ).startswith("CANONICAL_STATE_REQUIRED")
    assert calls == ["x"]


def test_late_subprocess_and_temporary_roots_in_authority(production, monkeypatch) -> None:
    production.use([(0, f"{production.controller}\n"), (0, "R1\n")])
    assert (
        production.service._promotion_authority_error(
            contract=production.contract, request=production.request
        )
        is None
    )
    # patched after a first call that reached both sites
    late_log: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "subprocess",
        _Proc(late_log, [(0, f"{production.controller}\n"), (0, "LATE\n")]),
    )
    assert (
        production.service._promotion_authority_error(
            contract=production.contract, request=production.request
        )
        == "CONTROLLER_REVISION_MISMATCH: expected R1, got LATE"
    )
    assert len(late_log) == 2
    monkeypatch.setattr(service_module, "_temporary_state_roots", lambda: (production.controller,))
    assert production.service._promotion_authority_error(
        contract=production.contract, request=production.request
    ).startswith("DURABLE_CONTROLLER_REQUIRED")


# ---------------------------------------------------------------------------
# _run_fail_to_pass_probe


class _Manager:
    """A recording ``WorktreeManager`` stand-in (only ``_run_git`` is used by the probe)."""

    def __init__(self, log: list[Any], *, fail: dict[str, BaseException] | None = None) -> None:
        self.log, self.fail = log, fail or {}

    def _run_git(self, args: list[str], *, cwd: str) -> Any:
        self.log.append(("git", tuple(args), cwd))
        error = self.fail.get(args[0] + (":" + args[1] if len(args) > 1 else ""))
        if error is not None:
            raise error
        return SimpleNamespace(returncode=0, stdout="")


class _ProbeEnv:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self.log: list[Any] = []
        self.scratch = tmp_path / "f2p-scratch"
        self.passed = False
        self.evidence: tuple[Any, ...] = (_evidence("pytest -q", exit_code=1),)
        self.failures: list[str] = []
        self.verifier_error: Optional[BaseException] = None
        self.nothing_ran: Optional[str] = None
        env = self

        def mkdtemp(prefix: str) -> str:
            env.log.append(("mkdtemp", prefix))
            env.scratch.mkdir()
            return str(env.scratch)

        def rmtree(path: Any, ignore_errors: bool = False) -> None:
            env.log.append(("rmtree", Path(path), ignore_errors))

        class Verifier:
            @staticmethod
            def _run_verifiers(contract: Any, target: str, candidate: Any) -> Any:
                entry = (
                    "run_verifiers",
                    type(contract).__name__,
                    tuple(contract.verifier_commands),
                    target,
                    candidate,
                )
                env.log.append(entry)
                if env.verifier_error is not None:
                    raise env.verifier_error
                return env.passed, env.evidence, env.failures

            @staticmethod
            def effective_verifier_manifest(commands: Any) -> Any:
                env.log.append(("manifest", tuple(commands)))
                return tuple(commands)

        def nothing(evidence: Any, checkout: Path) -> Optional[str]:
            env.log.append(("nothing_ran", len(evidence), checkout))
            return env.nothing_ran

        monkeypatch.setattr(service_module, "tempfile", SimpleNamespace(mkdtemp=mkdtemp))
        monkeypatch.setattr(service_module, "shutil", SimpleNamespace(rmtree=rmtree))
        monkeypatch.setattr(service_module, "CandidateVerifier", Verifier)
        monkeypatch.setattr(service_module, "_base_run_collected_nothing", nothing)
        self.controller = tmp_path / "ctl"
        self.contract = SimpleNamespace(
            target_base_revision="BASE",
            verifier_commands=("pytest -q",),
            controller_repo_root=str(self.controller),
        )

    def run(self, manager: Optional[_Manager] = None, **contract: Any) -> dict[str, Any]:
        for key, value in contract.items():
            setattr(self.contract, key, value)
        return SelfHostedTaskService._run_fail_to_pass_probe(
            manager or _Manager(self.log), self.contract
        )


@pytest.fixture
def probe(monkeypatch, tmp_path) -> _ProbeEnv:
    return _ProbeEnv(monkeypatch, tmp_path)


def test_probe_without_commands_fails_closed_and_removes_scratch(probe) -> None:
    for commands in ((), ("code_integrity_v1",), ("", "   ", 7, None, "code_integrity_v1")):
        probe.log.clear()
        if probe.scratch.exists():
            probe.scratch.rmdir()
        assert probe.run(verifier_commands=commands) == {
            "schema": SCHEMA,
            "status": "BASE_NOT_PHYSICAL_FAIL",
            "base_revision": "BASE",
            "base_exit_codes": [],
            "required": True,
        }
        assert probe.log == [("mkdtemp", "nexus-f2p-base-"), ("rmtree", probe.scratch, True)]


def test_probe_verified_call_order_and_arguments(probe) -> None:
    probe.contract.target_base_revision = 1234  # str() of the revision
    probe.evidence = (_evidence("pytest -q", exit_code=1), _evidence("make t", exit_code=0))
    out = probe.run(verifier_commands=("pytest -q", "code_integrity_v1", "make t"))
    checkout = probe.scratch / "base"
    root = str(probe.controller.resolve())
    assert out == {
        "schema": SCHEMA,
        "status": "VERIFIED",
        "base_revision": "1234",
        "base_exit_codes": [1, 0],
        "required": True,
    }
    assert probe.log == [
        ("mkdtemp", "nexus-f2p-base-"),
        ("git", ("worktree", "add", "--detach", str(checkout), "1234"), root),
        ("run_verifiers", "SimpleNamespace", ("pytest -q", "make t"), str(checkout), None),
        ("manifest", ("pytest -q", "make t")),
        ("nothing_ran", 2, checkout),
        ("git", ("worktree", "remove", "--force", str(checkout)), root),
        ("rmtree", probe.scratch, True),
        ("git", ("worktree", "prune"), root),
    ]


def test_probe_nothing_ran_check_comes_after_the_normal_checks(probe) -> None:
    probe.evidence = (_evidence("pytest -q", exit_code=1), _evidence("make t", exit_code=0))
    probe.nothing_ran = "base_test_path_missing"
    out = probe.run(verifier_commands=("pytest -q", "make t"))
    assert out["status"] == "BASE_NOT_PHYSICAL_FAIL" and out["reason"] == "base_test_path_missing"
    assert out["base_exit_codes"] == [1, 0]
    assert ("nothing_ran", 2, probe.scratch / "base") in probe.log


@pytest.mark.parametrize(
    ("evidence", "failures", "passed"),
    [
        ((), [], False),
        ((_evidence("pytest -q", exit_code=1),), [], False),  # 1 of 2 manifest entries
        ((_evidence("a", status="TIMED_OUT", exit_code=1), _evidence("b", exit_code=1)), [], False),
        ((_evidence("a", exit_code=None), _evidence("b", exit_code=1)), [], False),
        (
            (_evidence("a", exit_code=1), _evidence("b", exit_code=1)),
            ["verifier_invalid: x"],
            False,
        ),
        (
            (_evidence("a", exit_code=1), _evidence("b", exit_code=1)),
            ["verifier_evidence_inconsistent"],
            True,
        ),
    ],
    ids=[
        "no-evidence",
        "short",
        "timed-out",
        "no-exit-code",
        "invalid",
        "inconsistent-even-if-passed",
    ],
)
def test_probe_abnormal_runs_are_not_physical_failures(probe, evidence, failures, passed) -> None:
    probe.evidence, probe.failures, probe.passed = evidence, failures, passed
    probe.nothing_ran = "never-consulted"
    out = probe.run(verifier_commands=("a", "b"))
    assert out["status"] == "BASE_NOT_PHYSICAL_FAIL" and "reason" not in out
    assert out["base_exit_codes"] == [item.exit_code for item in evidence]
    assert not [entry for entry in probe.log if entry[0] == "nothing_ran"]


def test_probe_base_already_passes(probe) -> None:
    probe.evidence, probe.passed = (_evidence("a", exit_code=0),), True
    probe.nothing_ran = "never-consulted"
    out = probe.run(verifier_commands=("a",))
    assert out["status"] == "BASE_ALREADY_PASS" and "reason" not in out


def test_probe_failed_without_a_nonzero_exit_stays_not_physical(probe) -> None:
    probe.evidence, probe.failures, probe.passed = (_evidence("a", exit_code=0),), ["other"], False
    out = probe.run(verifier_commands=("a",))
    assert out["status"] == "BASE_NOT_PHYSICAL_FAIL" and "error" not in out
    assert out["base_exit_codes"] == [0]


def test_probe_checkout_failure_fails_closed_without_removal(probe) -> None:
    manager = _Manager(probe.log, fail={"worktree:add": RuntimeError("x" * 900)})
    out = probe.run(manager)
    assert out == {
        "schema": SCHEMA,
        "status": "BASE_NOT_PHYSICAL_FAIL",
        "base_revision": "BASE",
        "base_exit_codes": [],
        "required": True,
        "error": "x" * 500,
    }
    assert [entry[0] for entry in probe.log] == ["mkdtemp", "git", "rmtree"]


def test_probe_verifier_crash_fails_closed_and_still_removes(probe) -> None:
    probe.verifier_error = ValueError("boom")
    out = probe.run()
    assert out["status"] == "BASE_NOT_PHYSICAL_FAIL" and out["error"] == "boom"
    assert [entry[1][:2] for entry in probe.log if entry[0] == "git"] == [
        ("worktree", "add"),
        ("worktree", "remove"),
        ("worktree", "prune"),
    ]


def test_probe_removal_failure_overrides_verified(probe) -> None:
    manager = _Manager(probe.log, fail={"worktree:remove": RuntimeError("busy " * 200)})
    out = probe.run(manager)
    assert out["status"] == "BASE_NOT_PHYSICAL_FAIL"
    assert out["cleanup_error"] == ("busy " * 200)[:500] and "error" not in out
    assert out["base_exit_codes"] == [1]
    assert [entry[0] for entry in probe.log][-2:] == ["rmtree", "git"]  # prune still runs


def test_probe_prune_failure_is_ignored(probe) -> None:
    manager = _Manager(probe.log, fail={"worktree:prune": RuntimeError("nope")})
    out = probe.run(manager)
    assert out["status"] == "VERIFIED" and "cleanup_error" not in out and "error" not in out


def test_probe_with_real_git_and_verifiers(tmp_path) -> None:
    controller = tmp_path / "repo"
    base = _repo(controller)
    contract = SimpleNamespace(
        target_base_revision=base,
        controller_repo_root=str(controller),
        verifier_commands=(
            "code_integrity_v1",
            f"{shlex.quote(os.path.abspath(sys.executable))} -c "
            + shlex.quote("import sys; sys.exit(0 if open('a.txt').read() == 'fixed' else 3)"),
        ),
    )
    manager = service_module.WorktreeManager(root_dir=str(tmp_path / "targets"))
    out = SelfHostedTaskService._run_fail_to_pass_probe(manager, contract)
    assert out == {
        "schema": SCHEMA,
        "status": "VERIFIED",
        "base_revision": base,
        "base_exit_codes": [3],
        "required": True,
    }
    # the detached base checkout is gone and pruned
    assert _git(controller, "worktree", "list", "--porcelain").count("worktree ") == 1


def test_late_names_in_the_probe(probe, monkeypatch) -> None:
    assert probe.run()["status"] == "VERIFIED"
    # each patched after a first call that reached the same site
    monkeypatch.setattr(service_module, "FAIL_TO_PASS_PROBE_SCHEMA", "late.schema")
    seen: list[str] = []
    real_nothing = service_module._base_run_collected_nothing
    monkeypatch.setattr(
        service_module,
        "_base_run_collected_nothing",
        lambda evidence, checkout: (seen.append("nothing"), real_nothing(evidence, checkout))[1],
    )
    monkeypatch.setattr(
        service_module, "CliWorkerStatus", SimpleNamespace(COMPLETED=SimpleNamespace(value="DONE"))
    )
    probe.evidence = (_evidence("pytest -q", status="DONE", exit_code=1),)
    probe.scratch.rmdir() if probe.scratch.exists() else None
    out = probe.run()
    assert out["schema"] == "late.schema" and out["status"] == "VERIFIED" and seen == ["nothing"]
    late_scratch = probe.scratch.parent / "late-scratch"
    monkeypatch.setattr(
        service_module,
        "tempfile",
        SimpleNamespace(mkdtemp=lambda prefix: (late_scratch.mkdir(), str(late_scratch))[1]),
    )
    removed: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "shutil",
        SimpleNamespace(rmtree=lambda p, ignore_errors: removed.append(Path(p))),
    )
    probe.run()
    assert removed == [late_scratch]
    two = (_evidence("p", status="DONE", exit_code=0), _evidence("q", status="DONE", exit_code=0))
    monkeypatch.setattr(
        service_module,
        "CandidateVerifier",
        SimpleNamespace(
            _run_verifiers=lambda c, t, x: (True, two, []),
            effective_verifier_manifest=lambda commands: ("one", "two"),
        ),
    )
    late_scratch.rmdir()
    assert probe.run()["status"] == "BASE_ALREADY_PASS"


# ---------------------------------------------------------------------------
# _finalize_runtime_candidate


class _Fin:
    """Recording collaborators for ``_finalize_runtime_candidate``.

    Facade names (``WorktreeManager``, ``SelfHostedDevelopmentController``,
    ``CandidateVerifier``, ``CandidateCommitter``, ``resolve_attempt``, ``_utc_now``, ``time``)
    are patched on the facade module; members reached through ``self`` are patched on the
    instance.  Every call lands in ``log`` in order.
    """

    def __init__(self, service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch) -> None:
        self.service, self.mp = service, monkeypatch
        self.log: list[Any] = []
        self.contract = SimpleNamespace(
            task_id="task-1",
            target_worktree_root="/targets",
            acceptance_profile=SimpleNamespace(required_evidence=("other",)),
        )
        self.request: dict[str, Any] = {"protected_paths": {"p": "h"}}
        self.lease = "LEASE"
        self.state: Any = {"task_id": "task-1", "attempt_id": "attempt-1", "v": 0}
        self.reads: list[Any] = [{"task_id": "task-1", "attempt_id": "attempt-1", "v": 1}]
        self.attempts: list[Any] = ["EXEC-0", "EXEC-1"]
        self.execution: Any = {"execution": "raw"}
        self.verified = _receipt()
        self.core_required = False
        self.core_error: Optional[BaseException] = None
        self.receipt_from_state: Any = "EXEC-FROM-STATE"
        self.resolution = SimpleNamespace(verdict="PROVEN", failure_reasons=[])
        self.authority: Optional[str] = None
        self.probe: dict[str, Any] = {"status": "VERIFIED", "base_exit_codes": [1]}
        self.packet = SimpleNamespace(
            promotion_status="PENDING_HUMAN_APPROVAL",
            candidate_commit_created=True,
            public_claim_allowed=False,
            production_ready=False,
            merge_performed=False,
            push_performed=False,
            candidate_commit_sha="c" * 40,
        )
        self.protect_error: Optional[BaseException] = None
        self.cleanups: list[Any] = [
            SimpleNamespace(decision="REMOVED", blocker=None, performed=True, eligible=True)
        ]
        self.clock = iter([1.0, 1.25, 2.0, 2.5, 9.0, 9.0])
        self.now = 0
        fin = self

        def rec(name: Any, value: Any = None) -> Any:
            fin.log.append(name)
            return value

        class Manager:
            def __init__(self, *, root_dir: Any) -> None:
                fin.log.append(("WorktreeManager", root_dir))

            def cleanup_terminal_target(self, contract: Any, lease: Any, **kwargs: Any) -> Any:
                entry = (
                    "cleanup",
                    contract is fin.contract,
                    lease,
                    tuple(sorted(kwargs.items())),
                )
                fin.log.append(entry)
                return fin.cleanups.pop(0)

            def protect_candidate(self, contract: Any, lease: Any, sha: str) -> Any:
                fin.log.append(("protect", lease, sha))
                if fin.protect_error is not None:
                    raise fin.protect_error
                return "refs/nexus/candidate"

        class Controller:
            def __init__(self, *, worktree_manager: Any) -> None:
                fin.log.append(("Controller", type(worktree_manager).__name__))

        class Verifier:
            def __init__(self, manager: Any) -> None:
                fin.log.append(("CandidateVerifier", type(manager).__name__))

            def verify(
                self, contract: Any, lease: Any, candidate: Any, *, protected_paths: Any
            ) -> Any:
                fin.log.append(("verify", lease, candidate, protected_paths))
                return fin.verified

        class Committer:
            def __init__(self, manager: Any) -> None:
                fin.log.append(("CandidateCommitter", type(manager).__name__))

            def create_candidate_commit(self, contract: Any, lease: Any, verified: Any) -> Any:
                fin.log.append(("commit", lease, verified is fin.last_verified))
                return fin.packet

        def resolve(execution: Any, candidate: Any, verified: Any) -> Any:
            fin.last_verified = verified
            entry = (
                "resolve_attempt",
                execution,
                candidate,
                verified.verified,
                verified.candidate_commit_allowed,
            )
            fin.log.append(entry)
            return fin.resolution

        def utc_now() -> str:
            fin.now += 1
            return f"NOW-{fin.now}"

        def perf_counter() -> float:
            value = next(fin.clock)
            fin.log.append(("perf", value))
            return value

        monkeypatch.setattr(service_module, "WorktreeManager", Manager)
        monkeypatch.setattr(service_module, "SelfHostedDevelopmentController", Controller)
        monkeypatch.setattr(service_module, "CandidateVerifier", Verifier)
        monkeypatch.setattr(service_module, "CandidateCommitter", Committer)
        monkeypatch.setattr(service_module, "resolve_attempt", resolve)
        monkeypatch.setattr(service_module, "_utc_now", utc_now)
        monkeypatch.setattr(
            service_module,
            "time",
            SimpleNamespace(
                perf_counter=perf_counter,
                time=time.time,
                monotonic=time.monotonic,
                sleep=time.sleep,
            ),
        )
        self.last_verified: Any = None

        def read_state(task_id: str) -> Any:
            fin.log.append(("read_state", task_id))
            return fin.reads.pop(0) if fin.reads else None

        def verify_core(**kwargs: Any) -> Any:
            entry = (
                "verify_core",
                kwargs["state"],
                kwargs["candidate"],
                kwargs["verified"].candidate_commit_allowed,
                kwargs["verified"].core_provenance_required,
                kwargs["lease"],
                kwargs["contract"] is fin.contract,
                kwargs["request"] is fin.request,
            )
            fin.log.append(entry)
            if fin.core_error is not None:
                raise fin.core_error
            return kwargs["verified"]

        def track1(**kwargs: Any) -> Any:
            entry = (
                "track1",
                kwargs["state"],
                kwargs["execution"],
                kwargs["candidate"],
                kwargs["lease"],
            )
            fin.log.append(entry)
            return {"ignored": True}

        def authority(**kwargs: Any) -> Any:
            entry = (
                "authority",
                kwargs["contract"] is fin.contract,
                kwargs["request"] is fin.request,
            )
            fin.log.append(entry)
            return fin.authority

        def run_probe(manager: Any, contract: Any) -> Any:
            fin.log.append(("probe", type(manager).__name__, contract is fin.contract))
            return fin.probe

        def claim(task_id: str, attempt_id: Any, operation: str) -> None:
            fin.log.append(("claim", task_id, attempt_id, operation))

        monkeypatch.setattr(
            service,
            "_bridge_validate_claim",
            lambda task_id, attempt_id, *, operation: claim(task_id, attempt_id, operation),
        )
        monkeypatch.setattr(
            service,
            "_capture_resumed_candidate",
            lambda contract, controller, lease, state: rec(
                ("capture", type(controller).__name__, lease, state), "CANDIDATE"
            ),
        )
        monkeypatch.setattr(service, "_read_state", read_state)
        monkeypatch.setattr(
            service,
            "_ambient_core_required",
            lambda contract, request: rec(("core_required",), fin.core_required),
        )
        monkeypatch.setattr(service, "_verify_ambient_core_candidate", verify_core)
        monkeypatch.setattr(
            service,
            "_receipt_from_state",
            lambda execution: rec(("receipt_from_state", execution), fin.receipt_from_state),
        )
        monkeypatch.setattr(service, "_record_track1_verified_outcome", track1)
        monkeypatch.setattr(service, "_promotion_authority_error", authority)
        monkeypatch.setattr(service, "_run_fail_to_pass_probe", run_probe)
        self.updates: list[tuple[str, dict[str, Any]]] = []

    def update(self, status: str, values: dict[str, Any]) -> None:
        self.log.append(("update", status))
        self.updates.append((status, dict(values)))

    def run(self, status: str = "WORKER_COMPLETED") -> Any:
        return self.service._finalize_runtime_candidate(
            self.contract,
            self.request,
            self.lease,
            self.state,
            self.attempts,
            self.update,
            execution=self.execution,
            status=status,
        )

    def statuses(self) -> list[str]:
        return [status for status, _ in self.updates]


@pytest.fixture
def fin(service, monkeypatch) -> _Fin:
    return _Fin(service, monkeypatch)


READ1 = {"task_id": "task-1", "attempt_id": "attempt-1", "v": 1}
READ2 = {"task_id": "task-1", "attempt_id": "attempt-1", "v": 2}
READ3 = {"task_id": "task-1", "attempt_id": "attempt-1", "v": 3}


def test_finalize_success_call_order(fin) -> None:
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.run()
    assert fin.log == [
        ("claim", "task-1", "attempt-1", "FINALIZE_CANDIDATE"),
        ("WorktreeManager", "/targets"),
        ("Controller", "Manager"),
        (
            "capture",
            "Controller",
            "LEASE",
            {"task_id": "task-1", "attempt_id": "attempt-1", "v": 0},
        ),
        ("update", "CANDIDATE_CAPTURED"),
        ("read_state", "task-1"),
        ("CandidateVerifier", "Manager"),
        ("verify", "LEASE", "CANDIDATE", {"p": "h"}),
        ("core_required",),
        ("read_state", "task-1"),
        ("verify_core", READ2, "CANDIDATE", True, False, "LEASE", True, True),
        ("resolve_attempt", "EXEC-1", "CANDIDATE", True, True),
        ("read_state", "task-1"),
        ("track1", READ3, "EXEC-1", "CANDIDATE", "LEASE"),
        ("update", "VERIFIED"),
        ("authority", True, True),
        ("perf", 1.0),
        ("CandidateCommitter", "Manager"),
        ("commit", "LEASE", True),
        ("perf", 1.25),
        ("update", "CANDIDATE_COMMITTED"),
        ("protect", "LEASE", "c" * 40),
        ("update", "CANDIDATE_REF_PROTECTED"),
        ("perf", 2.0),
        (
            "cleanup",
            True,
            "LEASE",
            (("candidate_commit", "c" * 40), ("candidate_ref", "refs/nexus/candidate")),
        ),
        ("perf", 2.5),
        ("update", "TARGET_CLEANED"),
    ]


def test_finalize_success_updates_and_result(fin) -> None:
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    result = fin.run()
    verified = fin.verified
    resolution = fin.resolution
    candidate_values = {
        "execution": {"execution": "raw"},
        "candidate": "CANDIDATE",
        "verified_receipt": verified,
        "attempt_resolution": resolution,
        "promotion_packet": fin.packet,
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "candidate_commit_created": True,
        "public_claim_allowed": False,
        "production_ready": False,
        "merge_performed": False,
        "push_performed": False,
        "telemetry": {"commit_hook_time_ms": 250},
    }
    assert fin.updates == [
        ("CANDIDATE_CAPTURED", {"candidate": "CANDIDATE"}),
        (
            "VERIFIED",
            {
                "verified_receipt": verified,
                "attempt_resolution": resolution,
                "fail_to_pass": {
                    "schema": SCHEMA,
                    "status": "UNPROVEN",
                    "reason": "fail_to_pass_unproven",
                    "required": False,
                },
            },
        ),
        ("CANDIDATE_COMMITTED", candidate_values),
        ("CANDIDATE_REF_PROTECTED", {"candidate_ref": "refs/nexus/candidate"}),
        (
            "TARGET_CLEANED",
            {
                "cleanup_eligible": True,
                "cleanup_decision": "REMOVED",
                "cleanup_blocker": None,
                "cleanup_performed": True,
                "cleanup_performed_at": "NOW-1",
                "telemetry": {"cleanup_time_ms": 500},
            },
        ),
    ]
    assert result == {
        **candidate_values,
        "candidate_ref": "refs/nexus/candidate",
        "candidate_status": "PENDING_HUMAN_APPROVAL",
        "cleanup_decision": "REMOVED",
        "cleanup_blocker": None,
        "cleanup_performed": True,
        "cleanup_performed_at": "NOW-2",
        "terminal_status": "PENDING_HUMAN_APPROVAL",
        "cleanup_eligible": True,
        "state_retention_status": "ACTIVE",
        "archive_eligible": False,
    }
    assert list(result) == [
        *candidate_values,
        "candidate_ref",
        "candidate_status",
        "cleanup_decision",
        "cleanup_blocker",
        "cleanup_performed",
        "cleanup_performed_at",
        "terminal_status",
        "cleanup_eligible",
        "state_retention_status",
        "archive_eligible",
    ]


def test_finalize_negative_timings_are_clamped(fin) -> None:
    fin.clock = iter([5.0, 4.0, 7.0, 6.0])
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    result = fin.run()
    assert result["telemetry"] == {"commit_hook_time_ms": 0}
    assert fin.updates[-1][1]["telemetry"] == {"cleanup_time_ms": 0}


def test_finalize_already_captured_does_not_checkpoint_the_capture(fin) -> None:
    fin.reads = [dict(READ2), dict(READ3)]
    fin.run(status="CANDIDATE_CAPTURED")
    assert fin.log[:4] == [
        ("claim", "task-1", "attempt-1", "FINALIZE_CANDIDATE"),
        ("WorktreeManager", "/targets"),
        ("Controller", "Manager"),
        (
            "capture",
            "Controller",
            "LEASE",
            {"task_id": "task-1", "attempt_id": "attempt-1", "v": 0},
        ),
    ]
    assert fin.log[4] == ("CandidateVerifier", "Manager")
    assert fin.statuses()[0] == "VERIFIED"


@pytest.mark.parametrize("state", [None, "not-a-mapping", ["attempt-1"]])
def test_finalize_claim_without_a_mapping_state(fin, state) -> None:
    fin.state = state
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.run()
    assert fin.log[0] == ("claim", "task-1", None, "FINALIZE_CANDIDATE")


def test_finalize_state_fallbacks_when_reads_return_nothing(fin) -> None:
    fin.reads = []
    fin.run()
    # after the capture checkpoint the state becomes {} (read or {}), then each later read
    # falls back to that state
    assert [entry for entry in fin.log if entry[0] in {"verify_core", "track1"}] == [
        ("verify_core", {}, "CANDIDATE", True, False, "LEASE", True, True),
        ("track1", {}, "EXEC-1", "CANDIDATE", "LEASE"),
    ]


def test_finalize_state_fallbacks_without_the_capture_checkpoint(fin) -> None:
    fin.reads = []
    fin.run(status="CANDIDATE_CAPTURED")
    original = {"task_id": "task-1", "attempt_id": "attempt-1", "v": 0}
    assert [entry[1] for entry in fin.log if entry[0] in {"verify_core", "track1"}] == [
        original,
        original,
    ]


def test_finalize_without_protected_paths_passes_an_empty_mapping(fin) -> None:
    fin.request = {"protected_paths": None}
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.run()
    assert ("verify", "LEASE", "CANDIDATE", {}) in fin.log


def test_finalize_core_required_withholds_commit_before_core(fin) -> None:
    fin.core_required = True
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.run()
    (core,) = [entry for entry in fin.log if entry[0] == "verify_core"]
    assert core[3:5] == (
        False,
        True,
    )  # candidate_commit_allowed False, core_provenance_required True
    (resolved,) = [entry for entry in fin.log if entry[0] == "resolve_attempt"]
    assert resolved[3:] == (True, False)


def test_finalize_core_blocked_persists_the_blocked_receipt(fin) -> None:
    blocked = _receipt(verified=False, candidate_commit_allowed=False, failure_reasons=["CORE"])
    fin.core_error = AmbientCoreVerdictBlocked(
        "blocked", receipt=blocked, verdict={"blocking": True}
    )
    fin.resolution = SimpleNamespace(verdict="FAILED", failure_reasons=["CORE", "LOCAL"])
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    with pytest.raises(RuntimeError) as raised:
        fin.run()
    assert str(raised.value) == "candidate verification failed: CORE, LOCAL"
    assert type(raised.value) is RuntimeError
    assert fin.last_verified is blocked
    assert fin.updates[-1] == (
        "VERIFIED",
        {
            "verified_receipt": blocked,
            "attempt_resolution": fin.resolution,
            "fail_to_pass": {
                "schema": SCHEMA,
                "status": "UNPROVEN",
                "reason": "fail_to_pass_unproven",
                "required": False,
            },
        },
    )
    assert ("track1", READ3, "EXEC-1", "CANDIDATE", "LEASE") in fin.log
    assert not [e for e in fin.log if e[0] in {"authority", "CandidateCommitter", "probe"}]


def test_finalize_other_core_errors_propagate_before_resolution(fin) -> None:
    fin.core_error = RuntimeError("AMBIENT_CORE_TRANSPORT_FAILED: down")
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    with pytest.raises(RuntimeError, match="AMBIENT_CORE_TRANSPORT_FAILED"):
        fin.run()
    assert fin.statuses() == ["CANDIDATE_CAPTURED"]
    assert not [e for e in fin.log if e[0] in {"resolve_attempt", "track1"}]


def test_finalize_without_attempts_uses_the_state_execution(fin) -> None:
    fin.attempts = []
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.run()
    index = fin.log.index(("receipt_from_state", {"execution": "raw"}))
    assert fin.log[index + 1] == ("resolve_attempt", "EXEC-FROM-STATE", "CANDIDATE", True, True)
    assert ("track1", READ3, "EXEC-FROM-STATE", "CANDIDATE", "LEASE") in fin.log


def test_finalize_without_any_execution_receipt_fails_before_verified(fin) -> None:
    fin.attempts, fin.receipt_from_state = [], None
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    with pytest.raises(RuntimeError) as raised:
        fin.run()
    assert str(raised.value) == "worker execution receipt is missing for attempt resolution"
    assert fin.statuses() == ["CANDIDATE_CAPTURED"]
    assert not [e for e in fin.log if e[0] in {"resolve_attempt", "track1"}]


@pytest.mark.parametrize(
    ("resolution", "message"),
    [
        (SimpleNamespace(verdict="INCOMPLETE", failure_reasons=[]), "verdict is INCOMPLETE"),
        (SimpleNamespace(verdict="FAILED", failure_reasons=["a", "b"]), "a, b"),
        (SimpleNamespace(verdict="proven", failure_reasons=[]), "verdict is proven"),
    ],
)
def test_finalize_unproven_resolution_fails_after_verified(fin, resolution, message) -> None:
    fin.resolution = resolution
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    with pytest.raises(RuntimeError) as raised:
        fin.run()
    assert str(raised.value) == f"candidate verification failed: {message}"
    assert fin.statuses() == ["CANDIDATE_CAPTURED", "VERIFIED"]
    assert fin.log[-1] == ("update", "VERIFIED")


def test_finalize_fail_to_pass_required_records_pending_then_the_probe(fin) -> None:
    fin.contract.acceptance_profile = SimpleNamespace(required_evidence=["x", TOKEN])
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.run()
    assert fin.updates[1][1]["fail_to_pass"] == {
        "schema": SCHEMA,
        "status": "PENDING",
        "required": True,
    }
    assert fin.updates[2] == ("VERIFIED", {"fail_to_pass": fin.probe})
    index = fin.log.index(("authority", True, True))
    assert fin.log[index + 1 : index + 4] == [
        ("probe", "Manager", True),
        ("update", "VERIFIED"),
        ("perf", 1.0),
    ]
    assert fin.statuses() == [
        "CANDIDATE_CAPTURED",
        "VERIFIED",
        "VERIFIED",
        "CANDIDATE_COMMITTED",
        "CANDIDATE_REF_PROTECTED",
        "TARGET_CLEANED",
    ]


@pytest.mark.parametrize("status", ["BASE_ALREADY_PASS", "BASE_NOT_PHYSICAL_FAIL", "PENDING"])
def test_finalize_fail_to_pass_blocked_raises_after_persisting_the_probe(fin, status) -> None:
    fin.contract.acceptance_profile = SimpleNamespace(required_evidence=(TOKEN,))
    fin.probe = {"status": status, "base_exit_codes": [0, 2]}
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    with pytest.raises(RuntimeError) as raised:
        fin.run()
    assert str(raised.value) == f"fail_to_pass gate failed: {status} (base exit codes [0, 2])"
    assert fin.updates[-1] == ("VERIFIED", {"fail_to_pass": fin.probe})
    assert not [e for e in fin.log if e[0] in {"CandidateCommitter", "perf"}]


@pytest.mark.parametrize(
    "profile",
    [
        None,
        SimpleNamespace(),
        SimpleNamespace(required_evidence=None),
        SimpleNamespace(required_evidence=f"x{TOKEN}"),
    ],
    ids=["no-profile", "no-field", "none", "substring-only"],
)
def test_finalize_fail_to_pass_not_required_shapes(fin, profile) -> None:
    fin.contract.acceptance_profile = profile
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.run()
    assert fin.updates[1][1]["fail_to_pass"]["status"] == "UNPROVEN"
    assert not [e for e in fin.log if e[0] == "probe"]


def test_finalize_contract_without_acceptance_profile_attribute(fin) -> None:
    del fin.contract.acceptance_profile
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.run()
    assert fin.updates[1][1]["fail_to_pass"]["status"] == "UNPROVEN"


@pytest.mark.parametrize(
    ("ephemeral", "decision", "terminal", "candidate_status", "verdict"),
    [
        (True, "REMOVED", "REHEARSAL_VERIFIED", "REHEARSAL_VERIFIED", "PROVEN"),
        (True, "ALREADY_REMOVED", "REHEARSAL_VERIFIED", "REHEARSAL_VERIFIED", "PROVEN"),
        (True, "TARGET_CLEANED", "REHEARSAL_VERIFIED", "REHEARSAL_VERIFIED", "PROVEN"),
        (
            True,
            "BLOCKED_BY_UNSAVED_CHANGES",
            "RETAINED_FOR_REVIEW",
            "RETAINED_FOR_REVIEW",
            "FAILED",
        ),
        (True, "CLEANUP_BLOCKED", "FINAL_BLOCK", "FINAL_BLOCK", "FAILED"),
        (False, "REMOVED", "FINAL_BLOCK", "FINAL_BLOCK", "FAILED"),
        (
            False,
            "BLOCKED_BY_UNSAVED_CHANGES",
            "RETAINED_FOR_REVIEW",
            "RETAINED_FOR_REVIEW",
            "FAILED",
        ),
    ],
)
def test_finalize_promotion_authority_refusal(
    fin, monkeypatch, ephemeral, decision, terminal, candidate_status, verdict
) -> None:
    monkeypatch.setattr(fin.service, "ephemeral", ephemeral)
    fin.contract.acceptance_profile = SimpleNamespace(required_evidence=(TOKEN,))  # probe skipped
    fin.authority = "EPHEMERAL_PROMOTION_FORBIDDEN: x"
    performed = decision != "CLEANUP_BLOCKED"
    fin.cleanups = [
        SimpleNamespace(decision=decision, blocker="B", performed=performed, eligible="E")
    ]
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    result = fin.run()
    index = fin.log.index(("authority", True, True))
    assert fin.log[index + 1 :] == [("cleanup", True, "LEASE", ()), ("update", terminal)]
    # the refusal comes before (and instead of) the fail-to-pass probe
    assert not [entry for entry in fin.log if entry[0] == "probe"]
    at = "NOW-1" if performed else None
    assert fin.updates[-1] == (
        terminal,
        {
            "error": "EPHEMERAL_PROMOTION_FORBIDDEN: x",
            "candidate_status": candidate_status,
            "promotion_status": "NOT_CREATED",
            "promotion_eligible": False,
            "verification_verdict": verdict,
            "verified_receipt": fin.verified,
            "attempt_resolution": fin.resolution,
            "cleanup_decision": decision,
            "cleanup_blocker": "B",
            "cleanup_performed": performed,
            "cleanup_performed_at": at,
            "cleanup_eligible": "E",
            "terminal_status": terminal,
            "state_retention_status": "TERMINAL",
            "archive_eligible": False,
        },
    )
    assert result == {
        "execution": {"execution": "raw"},
        "candidate": "CANDIDATE",
        "verified_receipt": fin.verified,
        "attempt_resolution": fin.resolution,
        "candidate_status": candidate_status,
        "promotion_status": "NOT_CREATED",
        "promotion_eligible": False,
        "cleanup_decision": decision,
        "cleanup_performed": performed,
        "terminal_status": terminal,
        "error": "EPHEMERAL_PROMOTION_FORBIDDEN: x",
    }


def test_finalize_ref_protection_failure_retains_for_review(fin) -> None:
    fin.protect_error = OSError("ref locked")
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    with pytest.raises(RuntimeError) as raised:
        fin.run()
    assert str(raised.value) == "candidate ref protection failed: ref locked"
    assert fin.updates[-1] == (
        "RETAINED_FOR_REVIEW",
        {
            "error": "candidate ref protection failed: ref locked",
            "promotion_status": "NOT_CREATED",
            "candidate_status": "RETAINED_FOR_REVIEW",
            "terminal_status": "RETAINED_FOR_REVIEW",
            "state_retention_status": "ACTIVE",
            "recovery_action": "recover_retained_candidate",
        },
    )
    assert fin.statuses()[-2] == "CANDIDATE_COMMITTED"
    assert not [e for e in fin.log if e[0] == "cleanup"]


@pytest.mark.parametrize(
    "decision", ["ALREADY_REMOVED", "BLOCKED_BY_UNSAVED_CHANGES", "TARGET_CLEANED"]
)
def test_finalize_cleanup_must_remove_the_target(fin, decision) -> None:
    fin.cleanups = [
        SimpleNamespace(decision=decision, blocker=None, performed=False, eligible=False)
    ]
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    with pytest.raises(RuntimeError) as raised:
        fin.run()
    assert str(raised.value) == f"candidate Target cleanup failed: {decision}"
    assert fin.statuses()[-1] == "CANDIDATE_REF_PROTECTED"


def test_finalize_with_the_real_checkpoint_persists_each_status(service, monkeypatch) -> None:
    """The bridge's default update is ``_checkpoint``; the persisted state follows it."""
    fin = _Fin(service, monkeypatch)
    monkeypatch.setattr(service, "_read_state", SelfHostedTaskService._read_state.__get__(service))
    service._write_state(
        "task-1", {"task_id": "task-1", "attempt_id": "attempt-1", "status": "WORKER_COMPLETED"}
    )
    monkeypatch.setattr(service, "_emit_bound_attempt_transition", lambda result, task_id: None)
    fin.state = service._read_state("task-1")

    def update(status: str, values: dict[str, Any]) -> None:
        fin.updates.append((status, dict(values)))
        service._checkpoint("task-1", status, values, attempt_id="attempt-1")

    fin.update = update  # type: ignore[method-assign]
    fin.run()
    state = service._read_state("task-1")
    assert state is not None
    assert [item["status"] for item in state["status_history"]] == [
        "CANDIDATE_CAPTURED",
        "VERIFIED",
        "CANDIDATE_COMMITTED",
        "CANDIDATE_REF_PROTECTED",
        "TARGET_CLEANED",
    ]
    assert state["status"] == "TARGET_CLEANED"
    assert state["candidate_ref"] == "refs/nexus/candidate"
    assert state["cleanup_decision"] == "REMOVED"
    assert state["fail_to_pass"]["status"] == "UNPROVEN"
    assert state["verified_receipt"]["verified"] is True


# ---------------------------------------------------------------------------
# _finalize_runtime_failure


class _Fail:
    """Recording collaborators for ``_finalize_runtime_failure``."""

    def __init__(self, service: SelfHostedTaskService, monkeypatch: pytest.MonkeyPatch) -> None:
        self.service = service
        self.log: list[Any] = []
        self.state: dict[str, Any] = {"task_id": "t", "lease": {"id": "L"}, "request": {"r": 1}}
        self.cleanups: list[Any] = []
        self.salvage: Any = {
            "salvage_commit_sha": "S" * 40,
            "salvage_ref": "refs/salvage/x",
            "extra": 1,
        }
        self.restore: Any = {"decision": "RESTORED", "restored_to": "S" * 40}
        self.build_error: Optional[BaseException] = None
        self.now = 0
        fail = self

        class Manager:
            def __init__(self, *, root_dir: Any) -> None:
                fail.log.append(("WorktreeManager", root_dir))

            def cleanup_terminal_target(self, contract: Any, lease: Any, **kwargs: Any) -> Any:
                fail.log.append(("cleanup", contract, lease, tuple(sorted(kwargs.items()))))
                answer = fail.cleanups.pop(0)
                if isinstance(answer, BaseException):
                    raise answer
                return answer

            def create_salvage_snapshot(self, contract: Any, lease: Any, attempt_id: Any) -> Any:
                fail.log.append(("salvage", contract, lease, attempt_id))
                if isinstance(fail.salvage, BaseException):
                    raise fail.salvage
                return fail.salvage

            def restore_task_branch_for_retry(
                self, contract: Any, lease: Any, commit: Any, ref: Any
            ) -> Any:
                fail.log.append(("restore", contract, lease, commit, ref))
                if isinstance(fail.restore, BaseException):
                    raise fail.restore
                return fail.restore

        def utc_now() -> str:
            fail.now += 1
            return f"NOW-{fail.now}"

        def build_contract(request: Any) -> Any:
            fail.log.append(("build_contract", request))
            if fail.build_error is not None:
                raise fail.build_error
            return SimpleNamespace(target_worktree_root="/targets", tag="CONTRACT")

        monkeypatch.setattr(service_module, "WorktreeManager", Manager)
        monkeypatch.setattr(service_module, "_utc_now", utc_now)
        monkeypatch.setattr(
            service,
            "_read_state",
            lambda task_id: (fail.log.append(("read_state", task_id)), fail.state)[1],
        )
        monkeypatch.setattr(service, "build_contract", build_contract)
        monkeypatch.setattr(
            service,
            "_lease_from_state",
            lambda state: (fail.log.append(("lease_from_state", state is fail.state)), "LEASE")[1],
        )

        def checkpoint(task_id: str, status: str, values: Any, attempt_id: Any) -> None:
            fail.log.append(("checkpoint", task_id, status, dict(values), attempt_id))

        monkeypatch.setattr(
            service,
            "_checkpoint",
            lambda task_id, status, values, *, attempt_id: checkpoint(
                task_id, status, values, attempt_id
            ),
        )

    def run(self, exc: BaseException = RuntimeError("worker failed")) -> None:
        assert self.service._finalize_runtime_failure("t", "attempt-1", exc) is None

    def checkpoint(self) -> tuple[str, dict[str, Any]]:
        (entry,) = [e for e in self.log if e[0] == "checkpoint"]
        assert entry[1] == "t" and entry[4] == "attempt-1"
        return entry[2], entry[3]


@pytest.fixture
def failing(service, monkeypatch) -> _Fail:
    return _Fail(service, monkeypatch)


def _cleanup(
    decision: str, performed: bool = True, blocker: Any = None, eligible: Any = True
) -> Any:
    return SimpleNamespace(
        decision=decision, performed=performed, blocker=blocker, eligible=eligible
    )


VERIFIED_STATE = {
    "task_id": "t",
    "verified_receipt": {"verified": True},
    "attempt_resolution": {"verdict": "PROVEN"},
    "lease": {"id": "L"},
    "request": {"r": 1},
}


def test_failure_of_a_verified_candidate_is_retained_for_recovery(failing) -> None:
    failing.state = dict(VERIFIED_STATE)
    failing.run(ValueError("commit crashed"))
    assert failing.log == [
        ("read_state", "t"),
        (
            "checkpoint",
            "t",
            "RETAINED_FOR_REVIEW",
            {
                "error": "commit crashed",
                "promotion_status": "NOT_CREATED",
                "terminal_status": "RETAINED_FOR_REVIEW",
                "state_retention_status": "ACTIVE",
                "recovery_action": "recover_verified_uncommitted_candidate",
                "cleanup_eligible": False,
                "cleanup_performed": False,
                "cleanup_decision": "PRESERVED_FOR_REVIEW",
            },
            "attempt-1",
        ),
    ]


@pytest.mark.parametrize(
    "fields",
    [
        {"verified_receipt": {"verified": False}},
        {"verified_receipt": None},
        {"attempt_resolution": {"verdict": "FAILED"}},
        {"attempt_resolution": None},
        {"fail_to_pass": {"status": "BASE_ALREADY_PASS"}},
        {"fail_to_pass": {"status": "PENDING", "required": True}},
        {"contract": {"acceptance_profile": {"required_evidence": [TOKEN]}}},
    ],
    ids=[
        "unverified",
        "no-receipt",
        "failed",
        "no-resolution",
        "f2p-blocked",
        "f2p-pending",
        "f2p-required-unrecorded",
    ],
)
def test_failure_of_an_unrecoverable_candidate_is_a_final_block(failing, fields) -> None:
    failing.state = {**VERIFIED_STATE, **fields}
    failing.cleanups = [_cleanup("REMOVED")]
    failing.run()
    status, values = failing.checkpoint()
    assert status == "FINAL_BLOCK" and values["cleanup_decision"] == "REMOVED"


def test_failure_with_a_recorded_verified_probe_stays_recoverable(failing) -> None:
    failing.state = {
        **VERIFIED_STATE,
        "fail_to_pass": {"status": "VERIFIED", "required": True},
        "contract": {"acceptance_profile": {"required_evidence": [TOKEN]}},
    }
    failing.run()
    assert failing.checkpoint()[0] == "RETAINED_FOR_REVIEW"


@pytest.mark.parametrize("state", [None, {}, {"lease": None}, {"lease": {}}])
def test_failure_without_a_lease_is_a_final_block_without_cleanup(failing, state) -> None:
    failing.state = state
    failing.run(RuntimeError("timed out"))
    assert failing.log == [
        ("read_state", "t"),
        (
            "checkpoint",
            "t",
            "FINAL_BLOCK",
            {
                "error": "timed out",
                "promotion_status": "NOT_CREATED",
                "cleanup_decision": "ALREADY_REMOVED",
                "cleanup_blocker": None,
                "cleanup_performed": False,
                "terminal_status": "FINAL_BLOCK",
                "state_retention_status": "TERMINAL",
            },
            "attempt-1",
        ),
    ]


@pytest.mark.parametrize(
    ("decision", "performed"),
    [("REMOVED", True), ("ALREADY_REMOVED", False), ("CLEANUP_BLOCKED", False)],
)
def test_failure_cleans_up_the_target(failing, decision, performed) -> None:
    failing.cleanups = [_cleanup(decision, performed=performed, blocker="why", eligible="E")]
    failing.run()
    assert failing.log[:5] == [
        ("read_state", "t"),
        ("build_contract", {"r": 1}),
        ("lease_from_state", True),
        ("WorktreeManager", "/targets"),
        ("cleanup", failing.log[4][1], "LEASE", ()),
    ]
    assert failing.log[4][1].tag == "CONTRACT"
    assert failing.checkpoint() == (
        "FINAL_BLOCK",
        {
            "error": "worker failed",
            "promotion_status": "NOT_CREATED",
            "cleanup_decision": decision,
            "cleanup_blocker": "why",
            "cleanup_performed": performed,
            "terminal_status": "FINAL_BLOCK",
            "state_retention_status": "TERMINAL",
            "cleanup_performed_at": "NOW-1" if performed else None,
            "cleanup_eligible": "E",
        },
    )


def test_failure_with_unsaved_changes_salvages_restores_and_ends_final(failing) -> None:
    failing.cleanups = [
        _cleanup("BLOCKED_BY_UNSAVED_CHANGES", performed=False, blocker="dirty", eligible=False),
        _cleanup("REMOVED", performed=True, blocker=None, eligible=True),
    ]
    failing.run()
    contract = failing.log[1 + 3][1]
    assert [e[0] for e in failing.log] == [
        "read_state",
        "build_contract",
        "lease_from_state",
        "WorktreeManager",
        "cleanup",
        "salvage",
        "cleanup",
        "restore",
        "checkpoint",
    ]
    assert failing.log[5] == ("salvage", contract, "LEASE", "attempt-1")
    assert failing.log[6] == (
        "cleanup",
        contract,
        "LEASE",
        (("salvage_commit", "S" * 40), ("salvage_ref", "refs/salvage/x")),
    )
    assert failing.log[7] == ("restore", contract, "LEASE", "S" * 40, "refs/salvage/x")
    status, values = failing.checkpoint()
    assert status == "FINAL_BLOCK"
    assert values == {
        "error": "worker failed",
        "promotion_status": "NOT_CREATED",
        "cleanup_decision": "REMOVED",
        "cleanup_blocker": None,
        "cleanup_performed": True,
        "terminal_status": "FINAL_BLOCK",
        "state_retention_status": "TERMINAL",
        "cleanup_performed_at": "NOW-1",
        "cleanup_eligible": False,
        "salvage_commit_sha": "S" * 40,
        "salvage_ref": "refs/salvage/x",
        "extra": 1,
        "task_branch_restore_decision": "RESTORED",
        "task_branch_restored_to": "S" * 40,
        "task_branch_restore_performed": True,
        "task_branch_restore_verified": True,
    }
    # the first cleanup was not performed: no timestamp was taken for it
    assert failing.now == 1


def test_failure_salvage_values_can_override_the_cleanup_fields(failing) -> None:
    failing.salvage = {
        "salvage_commit_sha": "S",
        "salvage_ref": "R",
        "cleanup_decision": "FROM-SALVAGE",
    }
    failing.cleanups = [
        _cleanup("BLOCKED_BY_UNSAVED_CHANGES", performed=False),
        _cleanup("REMOVED"),
    ]
    failing.run()
    assert failing.checkpoint()[1]["cleanup_decision"] == "FROM-SALVAGE"


def test_failure_restore_refusal_is_retained_for_review(failing) -> None:
    failing.restore = RuntimeError("branch moved")
    failing.cleanups = [
        _cleanup("BLOCKED_BY_UNSAVED_CHANGES", performed=False),
        _cleanup("ALREADY_REMOVED", performed=False),
    ]
    failing.run()
    status, values = failing.checkpoint()
    assert status == "RETAINED_FOR_REVIEW"
    assert values["task_branch_restore_decision"] == "RESTORE_BLOCKED"
    assert values["task_branch_restore_performed"] is False
    assert values["task_branch_restore_verified"] is False
    assert "task_branch_restored_to" not in values
    assert values["state_retention_status"] == "TERMINAL"
    assert (
        values["cleanup_decision"] == "ALREADY_REMOVED" and values["cleanup_performed_at"] is None
    )


@pytest.mark.parametrize(
    ("salvage", "second"),
    [
        ({"salvage_commit_sha": "S", "salvage_ref": "R"}, "CLEANUP_BLOCKED"),
        ({"salvage_commit_sha": "", "salvage_ref": "R"}, "REMOVED"),
        ({"salvage_commit_sha": "S", "salvage_ref": None}, "REMOVED"),
        ({}, "REMOVED"),
    ],
    ids=["not-removed", "no-commit", "no-ref", "empty"],
)
def test_failure_without_a_restorable_salvage_is_retained(failing, salvage, second) -> None:
    failing.salvage = salvage
    failing.cleanups = [_cleanup("BLOCKED_BY_UNSAVED_CHANGES", performed=False), _cleanup(second)]
    failing.run()
    assert not [e for e in failing.log if e[0] == "restore"]
    status, values = failing.checkpoint()
    assert status == "RETAINED_FOR_REVIEW" and values["cleanup_decision"] == second
    second_cleanup = [e for e in failing.log if e[0] == "cleanup"][1]
    commit = str(salvage.get("salvage_commit_sha", "") or "")
    ref = str(salvage.get("salvage_ref", "") or "")
    assert second_cleanup[3] == (("salvage_commit", commit), ("salvage_ref", ref))


@pytest.mark.parametrize("where", ["salvage", "second-cleanup"])
def test_failure_salvage_errors_block_cleanup(failing, where) -> None:
    if where == "salvage":
        failing.salvage = RuntimeError("cannot snapshot")
        failing.cleanups = [
            _cleanup("BLOCKED_BY_UNSAVED_CHANGES", performed=False, blocker="dirty")
        ]
    else:
        failing.cleanups = [
            _cleanup("BLOCKED_BY_UNSAVED_CHANGES", performed=False),
            RuntimeError("cannot snapshot"),
        ]
    failing.run()
    status, values = failing.checkpoint()
    assert status == "RETAINED_FOR_REVIEW"
    assert values["cleanup_decision"] == "CLEANUP_BLOCKED"
    assert values["cleanup_blocker"] == "cannot snapshot"
    assert values["cleanup_performed"] is False and values["cleanup_eligible"] is False
    assert values["state_retention_status"] == "TERMINAL"


@pytest.mark.parametrize("where", ["build_contract", "first-cleanup"])
def test_failure_cleanup_errors_are_recorded_as_blocked(failing, where) -> None:
    if where == "build_contract":
        failing.build_error = ValueError("bad request")
    else:
        failing.cleanups = [RuntimeError("bad request")]
    failing.run()
    assert failing.checkpoint() == (
        "FINAL_BLOCK",
        {
            "error": "worker failed",
            "promotion_status": "NOT_CREATED",
            "cleanup_decision": "CLEANUP_BLOCKED",
            "cleanup_blocker": "bad request",
            "cleanup_performed": False,
            "terminal_status": "FINAL_BLOCK",
            "state_retention_status": "TERMINAL",
        },
    )


def test_failure_error_text_is_str_of_the_exception(failing) -> None:
    failing.state = {}

    class Odd(Exception):
        def __str__(self) -> str:
            return "odd text"

    failing.run(Odd())
    assert failing.checkpoint()[1]["error"] == "odd text"


def test_late_names_in_the_failure_path(failing, monkeypatch) -> None:
    failing.cleanups = [_cleanup("REMOVED")]
    failing.run()
    failing.state = dict(VERIFIED_STATE)  # reaches the fail-to-pass check
    failing.run()
    failing.state = {"task_id": "t", "lease": {"id": "L"}, "request": {"r": 1}}
    # patched after a first call that reached the same sites
    managers: list[Any] = []

    class Late:
        def __init__(self, *, root_dir: Any) -> None:
            managers.append(root_dir)

        def cleanup_terminal_target(self, contract: Any, lease: Any, **kwargs: Any) -> Any:
            return _cleanup("REMOVED")

    monkeypatch.setattr(service_module, "WorktreeManager", Late)
    monkeypatch.setattr(service_module, "_utc_now", lambda: "LATE-NOW")
    failing.log.clear()
    failing.run()
    assert managers == ["/targets"]
    assert failing.checkpoint()[1]["cleanup_performed_at"] == "LATE-NOW"
    failing.state = dict(VERIFIED_STATE)
    failing.log.clear()
    monkeypatch.setattr(service_module, "_fail_to_pass_blocked", lambda state: True)
    monkeypatch.setattr(service_module, "WorktreeManager", Late)
    failing.run()
    assert failing.checkpoint()[0] == "FINAL_BLOCK"


def test_failure_path_reaches_the_real_checkpoint_and_terminal_core_record(
    service, monkeypatch
) -> None:
    """Failure-only production path: worker failure -> FINAL_BLOCK -> terminal Core record."""
    universe = {"universe_generation": 1}
    service._write_state(
        "t",
        {
            "task_id": "t",
            "attempt_id": "attempt-1",
            "status": "WORKER_RUNNING",
            "verified_receipt": None,
            "request": {
                "task_id": "t",
                "core_envelope_required": True,
                "expected_evidence": universe,
            },
            "attempts": [{"attempt_id": "attempt-1"}],
        },
    )
    built: list[Any] = []
    monkeypatch.setattr(
        service,
        "build_contract",
        lambda request: (built.append(dict(request)), SimpleNamespace(expected_evidence=universe))[
            1
        ],
    )
    monkeypatch.setattr(service, "_card_evidence_binding_error", lambda contract, request: None)
    monkeypatch.setattr(service, "_emit_bound_attempt_transition", lambda result, task_id: None)
    service.ambient_core_port = None
    service._finalize_runtime_failure("t", "attempt-1", TimeoutError("worker timed out"))
    state = service._read_state("t")
    assert state is not None
    assert state["status"] == "FINAL_BLOCK"
    assert state["error"] == "worker timed out"
    assert state["promotion_status"] == "NOT_CREATED"
    assert state["cleanup_decision"] == "ALREADY_REMOVED"
    assert state["terminal_status"] == "FINAL_BLOCK"
    assert state["state_retention_status"] == "TERMINAL"
    assert state["attempts"][0]["last_status"] == "FINAL_BLOCK"
    record = state["terminal_core_record"]
    assert record["schema"] == "nexus.self_hosted_terminal_core_record.v1"
    assert (record["task_id"], record["attempt_id"], record["terminal_status"]) == (
        "t",
        "attempt-1",
        "FINAL_BLOCK",
    )
    assert record["record_status"] == "FAILED"
    assert (
        record["failure_reason"] == "CORE_TERMINAL_RECORD_FAILED:AMBIENT_CORE_CONTROL_PORT_REQUIRED"
    )
    assert record["verified"] is False and record["candidate_commit_allowed"] is False
    assert built == [
        {"task_id": "t", "core_envelope_required": True, "expected_evidence": universe}
    ]


def test_failure_path_records_cores_not_covered_answer(service, monkeypatch) -> None:
    universe = {"universe_generation": 1}
    service._write_state(
        "t",
        {
            "task_id": "t",
            "attempt_id": "attempt-1",
            "status": "WORKER_RUNNING",
            "verified_receipt": None,
            "request": {"task_id": "t", "expected_evidence": universe},
        },
    )
    monkeypatch.setattr(
        service, "build_contract", lambda request: SimpleNamespace(expected_evidence=universe)
    )
    monkeypatch.setattr(service, "_card_evidence_binding_error", lambda contract, request: None)
    monkeypatch.setattr(service, "_emit_bound_attempt_transition", lambda result, task_id: None)
    calls: list[Any] = []

    class Port:
        def record_terminal_not_covered(self, **kwargs: Any) -> Any:
            calls.append(kwargs["terminal_status"])
            return {"terminal_status": kwargs["terminal_status"]}

    service.ambient_core_port = Port()  # type: ignore[assignment]
    monkeypatch.setattr(
        service_module,
        "build_core_verdict",
        lambda *, contract, projection, **kw: {
            "blocking": True,
            "core_status": "UNVERIFIABLE",
            "integrity": "MISSING",
            "reason_codes": ["MISSING"],
            "host_reason_codes": ["AMBIENT_CORE_FAILED_VERIFICATION:UNVERIFIABLE"],
        },
    )
    service._finalize_runtime_failure("t", "attempt-1", RuntimeError("worker exited 1"))
    state = service._read_state("t")
    assert state is not None and state["status"] == "FINAL_BLOCK"
    assert calls == ["FINAL_BLOCK"]
    assert state["terminal_core_record"]["record_status"] == "RECORDED"


def test_failure_of_a_verified_candidate_writes_no_terminal_core_record(
    service, monkeypatch
) -> None:
    service._write_state(
        "t",
        {
            "task_id": "t",
            "attempt_id": "attempt-1",
            "status": "VERIFIED",
            "verified_receipt": {"verified": True},
            "attempt_resolution": {"verdict": "PROVEN"},
            "request": {"task_id": "t", "expected_evidence": {"universe_generation": 1}},
        },
    )
    monkeypatch.setattr(service, "_emit_bound_attempt_transition", lambda result, task_id: None)
    monkeypatch.setattr(
        service,
        "build_contract",
        lambda request: (_ for _ in ()).throw(AssertionError("not built")),
    )
    service._finalize_runtime_failure("t", "attempt-1", RuntimeError("commit failed"))
    state = service._read_state("t")
    assert state is not None
    assert state["status"] == "RETAINED_FOR_REVIEW"
    assert state["recovery_action"] == "recover_verified_uncommitted_candidate"
    assert "terminal_core_record" not in state


def test_failure_checkpoint_refuses_a_changed_attempt(service, monkeypatch) -> None:
    service._write_state(
        "t", {"task_id": "t", "attempt_id": "attempt-2", "status": "WORKER_RUNNING"}
    )
    monkeypatch.setattr(service, "_emit_bound_attempt_transition", lambda result, task_id: None)
    with pytest.raises(RuntimeError, match="task attempt ownership changed"):
        service._finalize_runtime_failure("t", "attempt-1", RuntimeError("x"))
    state = service._read_state("t")
    assert state is not None and state["status"] == "WORKER_RUNNING"


# ---------------------------------------------------------------------------
# worker process helpers


class _Bridge:
    calls: list[Any] = []

    def __init__(self, service: Any) -> None:
        _Bridge.calls.append(("init", service))

    def run_owned_attempt(self, task_id: str, attempt_id: str, runner: Any) -> Any:
        _Bridge.calls.append(("run_owned_attempt", task_id, attempt_id, runner))
        return "RAN"

    def launch(self, task_id: str, attempt_id: str, **kwargs: Any) -> Any:
        _Bridge.calls.append(("launch", task_id, attempt_id, kwargs))
        return {"launched": True}


@pytest.fixture
def bridge(monkeypatch) -> type[_Bridge]:
    _Bridge.calls = []
    monkeypatch.setattr(bridge_module, "RuntimeCoordinationBridge", _Bridge)
    return _Bridge


def test_run_owned_task_hands_the_custom_runner_to_the_bridge(tmp_path, bridge) -> None:
    def runner(*args: Any) -> Any:
        return None

    svc = SelfHostedTaskService(
        state_dir=tmp_path / "s", auto_reconcile=False, ephemeral=True, runner=runner
    )
    assert svc._run_owned_task("t", "a") == "RAN"
    assert bridge.calls == [("init", svc), ("run_owned_attempt", "t", "a", runner)]


def test_launch_worker_arguments(service, bridge) -> None:
    assert service._launch_worker("t", "a") == {"launched": True}
    assert bridge.calls == [
        ("init", service),
        (
            "launch",
            "t",
            "a",
            {
                "custom_runner": None,
                "state_dir": str(service.state_dir),
                "source_root": str(Path(service_module.__file__).resolve().parents[2]),
            },
        ),
    ]


def test_launch_worker_passes_the_custom_runner(tmp_path, bridge) -> None:
    def runner(*args: Any) -> Any:
        return None

    svc = SelfHostedTaskService(
        state_dir=tmp_path / "s", auto_reconcile=False, ephemeral=True, runner=runner
    )
    svc._launch_worker("t", "a")
    assert bridge.calls[-1][3]["custom_runner"] is runner


def test_launch_worker_source_root_is_the_facade_files_repository(service, bridge) -> None:
    service._launch_worker("t", "a")
    source_root = Path(bridge.calls[-1][3]["source_root"])
    assert source_root == REPO_ROOT
    assert (source_root / "nexus" / "orchestrator" / "self_hosted_task_service.py").is_file()


def test_late_module_file_in_launch_worker(service, bridge, monkeypatch, tmp_path) -> None:
    service._launch_worker("t", "a")
    fake = tmp_path / "x" / "y" / "z" / "facade.py"
    monkeypatch.setattr(service_module, "__file__", str(fake))
    service._launch_worker("t", "a")
    assert bridge.calls[-1][3]["source_root"] == str((tmp_path / "x").resolve())


def test_worker_entry_point_reaches_wait_and_run_through_the_service(tmp_path, monkeypatch) -> None:
    from nexus.orchestrator import self_hosted_task_worker

    calls: list[Any] = []

    class Sub(SelfHostedTaskService):
        owner = True

        def _wait_for_owner(self, task_id: str, attempt_id: str, pid: int) -> bool:
            calls.append(("wait", task_id, attempt_id, pid == os.getpid()))
            return Sub.owner

        def _run_owned_task(self, task_id: str, attempt_id: str) -> None:
            calls.append(("run", task_id, attempt_id))

    monkeypatch.setattr(self_hosted_task_worker, "SelfHostedTaskService", Sub)
    argv = ["--state-dir", str(tmp_path / "s"), "--task-id", "t", "--attempt-id", "a"]
    monkeypatch.setattr(sys, "argv", ["worker", *argv])
    # the detached worker builds a production service on the (here: temporary) canonical root
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(tmp_path / "s"))
    assert self_hosted_task_worker.main() == 0
    assert calls == [("wait", "t", "a", True), ("run", "t", "a")]
    calls.clear()
    Sub.owner = False
    assert self_hosted_task_worker.main() == 2
    assert calls == [("wait", "t", "a", True)]


class _Clock:
    def __init__(self, step: float = 0.0) -> None:
        self.now, self.step, self.sleeps = 100.0, step, []

    def monotonic(self) -> float:
        value = self.now
        self.now += self.step
        return value

    def sleep(self, seconds: float) -> None:
        # a wait loop that no longer sees this clock advance must fail, not hang
        assert len(self.sleeps) < 1000, "runaway wait loop"
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(
        service_module,
        "time",
        SimpleNamespace(
            monotonic=fake.monotonic,
            sleep=fake.sleep,
            time=time.time,
            perf_counter=time.perf_counter,
        ),
    )
    return fake


def _reads(service: Any, monkeypatch: pytest.MonkeyPatch, states: list[Any]) -> list[str]:
    seen: list[str] = []
    iterator = iter(states)
    monkeypatch.setattr(
        service, "_read_state", lambda task_id: (seen.append(task_id), next(iterator))[1]
    )
    return seen


def test_wait_for_owner_true_when_the_worker_pid_is_recorded(service, monkeypatch, clock) -> None:
    seen = _reads(
        service,
        monkeypatch,
        [
            {"attempt_id": "a"},
            {"attempt_id": "a", "worker_pid": 41},
            {"attempt_id": "a", "worker_pid": 42},
        ],
    )
    assert service._wait_for_owner("t", "a", 42) is True
    assert seen == ["t", "t", "t"] and clock.sleeps == [0.05, 0.05]


@pytest.mark.parametrize("state", [None, {"attempt_id": "b", "worker_pid": 42}, {}])
def test_wait_for_owner_false_when_the_attempt_is_gone(service, monkeypatch, clock, state) -> None:
    _reads(service, monkeypatch, [state])
    assert service._wait_for_owner("t", "a", 42) is False
    assert clock.sleeps == []


def test_wait_for_owner_times_out_after_ten_seconds(service, monkeypatch, clock) -> None:
    monkeypatch.setattr(
        service, "_read_state", lambda task_id: {"attempt_id": "a", "worker_pid": 1}
    )
    assert service._wait_for_owner("t", "a", 42) is False
    # 10 s of 0.05 s sleeps (float accumulation may add one more)
    assert len(clock.sleeps) in {200, 201} and set(clock.sleeps) == {0.05}


def test_wait_for_owner_deadline_is_taken_once(service, monkeypatch, clock) -> None:
    clock.step = 4.0
    reads = _reads(service, monkeypatch, [{"attempt_id": "a"}] * 10)
    assert service._wait_for_owner("t", "a", 42) is False
    # deadline 100 + 10; checks at 104 and 108.05+... -> two reads
    assert len(reads) == 2


class _Os:
    WNOHANG = 1

    def __init__(
        self, log: list[Any], *, waitpid: Any = None, kill: Any = None, pgrp: int = 7
    ) -> None:
        self.log, self._waitpid, self._kill, self.pgrp = log, waitpid, kill, pgrp
        self.killpg_errors: dict[tuple[int, int], BaseException] = {}

    def waitpid(self, pid: int, options: int) -> Any:
        self.log.append(("waitpid", pid, options))
        if isinstance(self._waitpid, BaseException):
            raise self._waitpid
        return self._waitpid

    def kill(self, pid: int, sig: int) -> None:
        self.log.append(("kill", pid, sig))
        if self._kill is not None:
            raise self._kill

    def getpgrp(self) -> int:
        self.log.append(("getpgrp",))
        return self.pgrp

    def killpg(self, pgid: int, sig: int) -> None:
        self.log.append(("killpg", pgid, sig))
        error = self.killpg_errors.get((pgid, sig))
        if error is not None:
            raise error


def _use_os(monkeypatch: pytest.MonkeyPatch, fake: _Os) -> None:
    """Route the ``os`` calls of the process helpers to ``fake``.

    The helpers use the ``os`` module itself (other parts of the facade already load
    ``os`` by bare name, so a patch of ``facade.os`` is not a supported seam): the
    functions are patched on the module, for the duration of one test.
    """
    for name in ("waitpid", "kill", "getpgrp", "killpg"):
        monkeypatch.setattr(os, name, getattr(fake, name))
    monkeypatch.setattr(os, "WNOHANG", fake.WNOHANG)


@pytest.mark.parametrize(
    ("waitpid", "kill", "alive", "calls"),
    [
        ((42, 0), None, False, ["waitpid"]),
        ((0, 0), None, True, ["waitpid", "kill"]),
        ((41, 0), None, True, ["waitpid", "kill"]),
        (ChildProcessError(), None, True, ["waitpid", "kill"]),
        (OSError(), ProcessLookupError(), False, ["waitpid", "kill"]),
        ((0, 0), PermissionError(), True, ["waitpid", "kill"]),
        ((0, 0), OSError(), False, ["waitpid", "kill"]),
    ],
    ids=["reaped", "running", "other-child", "not-our-child", "gone", "foreign", "os-error"],
)
def test_pid_alive(monkeypatch, waitpid, kill, alive, calls) -> None:
    log: list[Any] = []
    _use_os(monkeypatch, _Os(log, waitpid=waitpid, kill=kill))
    assert SelfHostedTaskService._pid_alive(42) is alive
    assert [entry[0] for entry in log] == calls
    if "waitpid" in calls:
        assert log[0] == ("waitpid", 42, 1)
    if "kill" in calls:
        assert log[-1] == ("kill", 42, 0)


@pytest.mark.parametrize("pid", [0, -5])
def test_pid_alive_never_waits_on_a_process_group(monkeypatch, pid) -> None:
    log: list[Any] = []
    _use_os(monkeypatch, _Os(log, waitpid=(pid, 0)))
    assert SelfHostedTaskService._pid_alive(pid) is True
    assert log == [("kill", pid, 0)]


def test_pid_alive_reaps_a_real_finished_child() -> None:
    child = subprocess.Popen([sys.executable, "-c", "pass"], stdout=subprocess.PIPE)
    pid = child.pid
    assert child.stdout is not None
    child.stdout.read()  # EOF: the child is exiting; nobody waits on it here
    deadline = time.monotonic() + 30
    alive = True
    while alive and time.monotonic() < deadline:
        alive = SelfHostedTaskService._pid_alive(pid)
        if alive:
            time.sleep(0.02)
    assert alive is False
    # it was _pid_alive that reaped it
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)
    child.returncode = 0
    child.stdout.close()
    assert SelfHostedTaskService._pid_alive(os.getpid()) is True


def test_terminate_owned_processes_order_and_skips(service, monkeypatch) -> None:
    log: list[Any] = []
    fake = _Os(log, pgrp=7)
    fake.killpg_errors[(30, signal.SIGTERM)] = ProcessLookupError()
    _use_os(monkeypatch, fake)
    sleeps: list[float] = []
    monkeypatch.setattr(
        service_module,
        "time",
        SimpleNamespace(sleep=sleeps.append, monotonic=time.monotonic, time=time.time),
    )
    monkeypatch.setattr(
        service, "_read_state", lambda task_id: {"worker_child_pgid": "30", "worker_pgid": 31}
    )
    assert service._terminate_owned_processes("t") is None
    assert log == [
        ("getpgrp",),
        ("killpg", 30, signal.SIGTERM),
        ("killpg", 31, signal.SIGTERM),
        ("killpg", 31, signal.SIGKILL),
    ]
    assert sleeps == [0.05]


@pytest.mark.parametrize(
    ("state", "exclude", "killed"),
    [
        ({"worker_child_pgid": 7, "worker_pgid": 9}, None, [9]),
        ({"worker_child_pgid": 9, "worker_pgid": 8}, 9, [8]),
        ({"worker_child_pgid": None, "worker_pgid": 0}, None, []),
        ({}, None, []),
        (None, None, []),
    ],
    ids=["own-group", "excluded", "falsy", "empty", "no-state"],
)
def test_terminate_owned_processes_skips(service, monkeypatch, state, exclude, killed) -> None:
    log: list[Any] = []
    _use_os(monkeypatch, _Os(log, pgrp=7))
    monkeypatch.setattr(service_module, "time", SimpleNamespace(sleep=lambda s: None))
    monkeypatch.setattr(service, "_read_state", lambda task_id: state)
    service._terminate_owned_processes("t", exclude_pid=exclude)
    assert [
        entry[1] for entry in log if entry[0] == "killpg" and entry[2] == signal.SIGKILL
    ] == killed


def test_terminate_owned_processes_permission_error_continues(service, monkeypatch) -> None:
    log: list[Any] = []
    fake = _Os(log, pgrp=7)
    fake.killpg_errors[(30, signal.SIGKILL)] = PermissionError()
    _use_os(monkeypatch, fake)
    monkeypatch.setattr(service_module, "time", SimpleNamespace(sleep=lambda s: None))
    monkeypatch.setattr(
        service, "_read_state", lambda task_id: {"worker_child_pgid": 30, "worker_pgid": 31}
    )
    service._terminate_owned_processes("t")
    assert [entry[1:] for entry in log if entry[0] == "killpg"] == [
        (30, signal.SIGTERM),
        (30, signal.SIGKILL),
        (31, signal.SIGTERM),
        (31, signal.SIGKILL),
    ]


def test_terminate_owned_processes_other_errors_propagate(service, monkeypatch) -> None:
    fake = _Os([], pgrp=7)
    fake.killpg_errors[(30, signal.SIGTERM)] = OSError("EINVAL")
    _use_os(monkeypatch, fake)
    monkeypatch.setattr(service_module, "time", SimpleNamespace(sleep=lambda s: None))
    monkeypatch.setattr(service, "_read_state", lambda task_id: {"worker_child_pgid": 30})
    with pytest.raises(OSError, match="EINVAL"):
        service._terminate_owned_processes("t")


def test_late_signal_and_time_in_the_process_helpers(service, monkeypatch) -> None:
    log: list[Any] = []
    _use_os(monkeypatch, _Os(log, waitpid=(0, 0), pgrp=7))
    early_sleeps: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "time",
        SimpleNamespace(
            sleep=early_sleeps.append,
            monotonic=iter([1000.0, 1000.0, 1000.0, 1000.0, 2000.0]).__next__,
        ),
    )
    monkeypatch.setattr(
        service,
        "_read_state",
        lambda task_id: {"worker_pgid": 31, "attempt_id": "a", "worker_pid": 5},
    )
    SelfHostedTaskService._pid_alive(5)
    service._terminate_owned_processes("t")
    assert service._wait_for_owner("t", "a", 5) is True
    assert service._wait_for_owner("t", "a", 6) is False  # one sleep, then past the deadline
    assert early_sleeps == [0.05, 0.05]
    # patched after a first call that reached the same sites
    late: list[Any] = []
    late_os = _Os(late, waitpid=(5, 0), pgrp=31)
    late_os.WNOHANG = 8  # type: ignore[misc]  # read at call time from the os module
    _use_os(monkeypatch, late_os)
    monkeypatch.setattr(service_module, "signal", SimpleNamespace(SIGTERM="TERM", SIGKILL="KILL"))
    sleeps: list[Any] = []
    monkeypatch.setattr(
        service_module, "time", SimpleNamespace(sleep=sleeps.append, monotonic=lambda: 0.0)
    )
    assert SelfHostedTaskService._pid_alive(5) is False
    assert late == [("waitpid", 5, 8)]
    monkeypatch.setattr(
        service,
        "_read_state",
        lambda task_id: {"worker_child_pgid": 30, "worker_pgid": 31, "attempt_id": "a"},
    )
    service._terminate_owned_processes("t")
    assert late[1:] == [("getpgrp",), ("killpg", 30, "TERM"), ("killpg", 30, "KILL")]
    monkeypatch.setattr(
        service_module,
        "time",
        SimpleNamespace(sleep=sleeps.append, monotonic=iter([0.0, 0.0, 99.0]).__next__),
    )
    assert service._wait_for_owner("t", "a", 5) is False
    assert sleeps == [0.05, 0.05]


# ---------------------------------------------------------------------------
# late binding of the collaborators in _finalize_runtime_candidate


def test_late_collaborators_in_finalize(fin, monkeypatch) -> None:
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.run()
    # patched after a first call that reached every site
    late: list[Any] = []

    class LateManager:
        def __init__(self, *, root_dir: Any) -> None:
            late.append(("manager", root_dir))

        def cleanup_terminal_target(self, contract: Any, lease: Any, **kwargs: Any) -> Any:
            return _cleanup("REMOVED")

        def protect_candidate(self, contract: Any, lease: Any, sha: str) -> Any:
            return "refs/late"

    class LateController:
        def __init__(self, *, worktree_manager: Any) -> None:
            late.append(("controller", type(worktree_manager).__name__))

    class LateVerifier:
        def __init__(self, manager: Any) -> None:
            late.append(("verifier", type(manager).__name__))

        def verify(self, *args: Any, **kwargs: Any) -> Any:
            return _receipt(failure_reasons=["late"])

    class LateCommitter:
        def __init__(self, manager: Any) -> None:
            late.append(("committer", type(manager).__name__))

        def create_candidate_commit(self, contract: Any, lease: Any, verified: Any) -> Any:
            return fin.packet

    monkeypatch.setattr(service_module, "WorktreeManager", LateManager)
    monkeypatch.setattr(service_module, "SelfHostedDevelopmentController", LateController)
    monkeypatch.setattr(service_module, "CandidateVerifier", LateVerifier)
    monkeypatch.setattr(service_module, "CandidateCommitter", LateCommitter)
    monkeypatch.setattr(
        service_module,
        "resolve_attempt",
        lambda execution, candidate, verified: (
            late.append(("resolve", verified.failure_reasons)),
            fin.resolution,
        )[1],
    )
    monkeypatch.setattr(service_module, "_utc_now", lambda: "LATE-NOW")
    monkeypatch.setattr(
        service_module, "time", SimpleNamespace(perf_counter=iter([0.0, 3.0, 0.0, 4.0]).__next__)
    )
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.updates.clear()
    result = fin.run()
    assert late == [
        ("manager", "/targets"),
        ("controller", "LateManager"),
        ("verifier", "LateManager"),
        ("resolve", ["late"]),
        ("committer", "LateManager"),
    ]
    assert result["candidate_ref"] == "refs/late" and result["cleanup_performed_at"] == "LATE-NOW"
    assert fin.updates[-1][1]["cleanup_performed_at"] == "LATE-NOW"
    assert result["telemetry"] == {"commit_hook_time_ms": 3000}
    assert fin.updates[-1][1]["telemetry"] == {"cleanup_time_ms": 4000}


def test_late_constants_and_verdict_in_finalize(fin, monkeypatch) -> None:
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.run()
    monkeypatch.setattr(service_module, "FAIL_TO_PASS_PROBE_SCHEMA", "late.schema")
    monkeypatch.setattr(service_module, "FAIL_TO_PASS_EVIDENCE_TOKEN", "other")
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.updates.clear()
    fin.clock = iter([1.0, 1.0, 1.0, 1.0])
    fin.cleanups = [_cleanup("REMOVED")]
    fin.run()
    # required_evidence ("other",) now names the (patched) token
    assert fin.updates[1][1]["fail_to_pass"] == {
        "schema": "late.schema",
        "status": "PENDING",
        "required": True,
    }
    monkeypatch.setattr(
        service_module,
        "AttemptResolutionVerdict",
        SimpleNamespace(PROVEN=SimpleNamespace(value="OK")),
    )
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    with pytest.raises(RuntimeError, match="verdict is PROVEN"):
        fin.run()


def test_late_replace_and_blocked_type_in_finalize(fin, monkeypatch) -> None:
    fin.core_required = True
    fin.core_error = AmbientCoreVerdictBlocked("b", receipt=_receipt(), verdict={})
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.run()  # reaches both sites: replace and the blocked-verdict handler
    assert fin.last_verified is fin.core_error.receipt
    replaced: list[Any] = []
    real_replace = dataclasses.replace
    monkeypatch.setattr(
        service_module,
        "replace",
        lambda obj, **changes: (replaced.append(sorted(changes)), real_replace(obj, **changes))[1],
    )

    class LateBlocked(Exception):
        receipt = _receipt(verified=False, failure_reasons=["late-blocked"])

    monkeypatch.setattr(service_module, "AmbientCoreVerdictBlocked", LateBlocked)
    fin.core_error = LateBlocked("x")
    fin.resolution = SimpleNamespace(verdict="FAILED", failure_reasons=["late-blocked"])
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    with pytest.raises(RuntimeError, match="late-blocked"):
        fin.run()
    assert replaced == [["candidate_commit_allowed", "core_provenance_required"]]
    assert fin.last_verified is LateBlocked.receipt


def test_late_names_in_the_authority_refusal_and_unproven_branches(fin, monkeypatch) -> None:
    fin.authority = "REFUSED"
    fin.cleanups = [_cleanup("REMOVED")]
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    assert fin.run()["terminal_status"] == "REHEARSAL_VERIFIED"
    assert fin.updates[-1][1]["cleanup_performed_at"] == "NOW-1"
    assert fin.updates[1][1]["fail_to_pass"]["schema"] == SCHEMA
    # patched after a first call that reached the same sites
    monkeypatch.setattr(service_module, "_utc_now", lambda: "LATE-NOW")
    monkeypatch.setattr(service_module, "FAIL_TO_PASS_PROBE_SCHEMA", "late.schema")
    fin.cleanups = [_cleanup("REMOVED")]
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.updates.clear()
    fin.run()
    assert fin.updates[-1][1]["cleanup_performed_at"] == "LATE-NOW"
    assert fin.updates[1][1]["fail_to_pass"] == {
        "schema": "late.schema",
        "status": "UNPROVEN",
        "reason": "fail_to_pass_unproven",
        "required": False,
    }


def test_late_utc_now_in_the_salvage_branch(failing, monkeypatch) -> None:
    failing.cleanups = [
        _cleanup("BLOCKED_BY_UNSAVED_CHANGES", performed=False),
        _cleanup("REMOVED"),
    ]
    failing.run()
    assert failing.checkpoint()[1]["cleanup_performed_at"] == "NOW-1"
    monkeypatch.setattr(service_module, "_utc_now", lambda: "LATE-NOW")
    failing.cleanups = [
        _cleanup("BLOCKED_BY_UNSAVED_CHANGES", performed=False),
        _cleanup("REMOVED"),
    ]
    failing.log.clear()
    failing.run()
    assert failing.checkpoint()[1]["cleanup_performed_at"] == "LATE-NOW"


# ---------------------------------------------------------------------------
# self dispatch: instance / class / subclass patches, the bridge


def test_bridge_finalization_reaches_the_members_through_the_service(service, monkeypatch) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(service, "_bridge_validate_claim", lambda *a, **k: None)
    monkeypatch.setattr(service, "_ambient_core_required", lambda contract, request: False)
    monkeypatch.setattr(
        service,
        "_finalize_runtime_candidate",
        lambda *a, **k: (calls.append(("candidate", a, k)), "DONE")[1],
    )
    monkeypatch.setattr(
        service, "_finalize_runtime_failure", lambda *a: calls.append(("failure", a))
    )
    finalization = bridge_module._Finalization(service, update="U", task_id="t", attempt_id="a")
    assert (
        finalization.finalize_completed("C", {}, "L", {"x": 1}, ["E"], execution="X", status="S")
        == "DONE"
    )
    finalization.finalize_failure("t", "a", "ERR")
    assert calls == [
        ("candidate", ("C", {}, "L", {"x": 1}, ["E"], "U"), {"execution": "X", "status": "S"}),
        ("failure", ("t", "a", "ERR")),
    ]


def test_bridge_process_adapters_reach_the_members_through_the_service(
    service, monkeypatch
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(service, "_wait_for_owner", lambda *a: (calls.append(("wait", a)), True)[1])
    monkeypatch.setattr(
        service, "_terminate_owned_processes", lambda t, **k: calls.append(("terminate", t, k))
    )
    monkeypatch.setattr(service, "_pid_alive", lambda pid: (calls.append(("alive", pid)), False)[1])
    adapter: Any = bridge_module._Processes()
    adapter.service = service  # as RuntimeCoordinationBridge._coordinator wires it
    assert adapter.wait_for_owner("t", "a", 5) is True
    adapter.terminate_owned_processes("t", 9)
    assert adapter.pid_alive(5) is False
    assert calls == [("wait", ("t", "a", 5)), ("terminate", "t", {"exclude_pid": 9}), ("alive", 5)]


def test_finalize_reaches_the_authority_and_probe_through_self(fin, monkeypatch) -> None:
    # the instance patches of _Fin are what finalize called (see the call-order test);
    # a class-level patch is honoured too once the instance patch is gone
    monkeypatch.delattr(fin.service, "_promotion_authority_error")
    seen: list[Any] = []
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_promotion_authority_error",
        lambda self, *, contract, request: (seen.append(self), "CLASS_PATCHED")[1],
    )
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.cleanups = [_cleanup("REMOVED")]
    result = fin.run()
    assert seen == [fin.service] and result["error"] == "CLASS_PATCHED"


def test_class_patch_of_reached_members_and_undo(tmp_path) -> None:
    svc = SelfHostedTaskService(state_dir=tmp_path / "s", auto_reconcile=False, ephemeral=True)
    original = SelfHostedTaskService.__dict__.get("_pid_alive")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(SelfHostedTaskService, "_pid_alive", staticmethod(lambda pid: "patched"))
        assert svc._pid_alive(1) == "patched"
    assert SelfHostedTaskService.__dict__.get("_pid_alive") is original
    assert inspect.getattr_static(SelfHostedTaskService, "_pid_alive") is not None


def test_subclass_overrides_are_dispatched_through_self(tmp_path, monkeypatch) -> None:
    calls: list[Any] = []

    class Sub(SelfHostedTaskService):
        def _read_state(self, task_id: str) -> Any:
            calls.append(("read", task_id))
            return {"task_id": task_id, "lease": None}

        def _checkpoint(
            self, task_id: str, status: str, values: Any = None, *, attempt_id: Any = None
        ) -> Any:
            calls.append(("checkpoint", status, attempt_id))
            return None

        @staticmethod
        def _pid_alive(pid: int) -> bool:
            calls.append(("alive", pid))
            return True

    svc = Sub(state_dir=tmp_path / "s", auto_reconcile=False, ephemeral=True)
    svc._finalize_runtime_failure("t", "a", RuntimeError("x"))
    assert calls == [("read", "t"), ("checkpoint", "FINAL_BLOCK", "a")]
    assert svc._pid_alive(3) is True


def test_finalize_records_learning_writeback_only_under_measurement_switch(fin, monkeypatch) -> None:
    """#2721: with NEXUS_LEARNING_WRITEBACK=1 the VERIFIED update carries the write-back observation."""
    from nexus.orchestrator.self_hosted_task_service_parts import learning_writeback

    calls: list[dict[str, Any]] = []

    def fake_writeback(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"schema": learning_writeback.SCHEMA, "enabled": True, "read_only": False, "card_written": True}

    monkeypatch.setattr(learning_writeback, "run_learning_writeback", fake_writeback)
    fin.reads = [dict(READ1), dict(READ2), dict(READ3)]
    fin.run()
    verified_update = dict(fin.updates)["VERIFIED"]
    assert verified_update["learning_writeback"]["card_written"] is True
    assert calls and calls[0]["verified"] is fin.verified
