"""Characterization of the task-build cluster of ``SelfHostedTaskService`` (split S8b).

Big-file split step S8b moves these class members out of
``nexus/orchestrator/self_hosted_task_service.py`` into a mixin:

* ``build_contract`` (a submit / retry request -> ``ArchitectTaskContract``);
* the static ``_terminal_retry_revision_refresh_allowed`` (may a terminal retry refresh
  the Controller / Target revisions of its predecessor);
* ``_contract_from_state``, the static ``_prompt``, ``_set_child_pgid``,
  ``_lease_from_state``, ``_capture_resumed_candidate`` and the static
  ``_receipt_from_state`` / ``_escalation_policy``.

These tests pin the behaviour before the move and must pass unchanged after it:

* the member table (descriptor kind, signature, docstring);
* the exact contract ``build_contract`` derives (golden ``contract_hash`` values and the
  full ``model_dump``), every refusal in its order, every default, the workforce
  dispatch-binding overrides, the provider order / fallback / call-budget derivation,
  the expected-evidence projection, the owner-inline authority-change confirmation, the
  collaboration realm, ``fail_to_pass_required`` and the ``git rev-parse HEAD`` default of
  the Controller revision (real temporary git repositories);
* every branch of ``_terminal_retry_revision_refresh_allowed``, including the order of
  the two predecessor-state proofs and the ``git merge-base --is-ancestor`` calls (real
  temporary git repositories, short-circuit included);
* ``_set_child_pgid``: the write under the state ``flock``, the clock read under the lock
  and only for an owned, non-terminal attempt;
* the small projections (``_contract_from_state``, ``_prompt``, ``_lease_from_state``,
  ``_capture_resumed_candidate``, ``_receipt_from_state``, ``_escalation_policy``);
* that every facade-module name the moved code reads is resolved through the facade at
  call time (patched after a first call), and that instance, class and subclass patches
  of the members it reaches through ``self`` are honoured, also from the runtime
  coordination bridge.

Git runs only in repositories this file creates under ``tmp_path`` (``GIT_CEILING_
DIRECTORIES`` keeps discovery from leaving them; global / system git config is ignored).
Self-deadlocks fail fast: an autouse fixture bounds the runtime store's blocking ``flock``
to 15 s.  No test asserts on inode numbers, file modes or other platform details.
"""

from __future__ import annotations

import fcntl
import hashlib
import inspect
import json
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import nexus_runtime.execution_state.store as store_module
import pytest

import nexus.orchestrator.self_hosted_task_service as service_module
from nexus.contracts.collaboration_realm import CollaborationExecutionRealm
from nexus.contracts.lifecycle_action import ContractKind
from nexus.executors.worker_contract import SUPPORTED_WORKER_PROVIDERS, WorkerExecutionReceipt
from nexus.orchestrator import runtime_coordination_bridge
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.task_contract import (
    ArchitectTaskContract,
    ArchitectureDecision,
    ExpectedEvidenceUniverse,
)
from nexus.orchestrator.worker_escalation import WorkerEscalationPolicy
from nexus.orchestrator.worktree_manager import TargetWorktreeLease

NOW = "2026-10-18T12:00:00+00:00"
ROOTS = (Path("/targets"), Path("/targets/t1"))
SHA_A = "a" * 40
SHA_B = "b" * 40

# ---------------------------------------------------------------------------
# fixtures


class _BoundedFlock:
    """``fcntl`` for the runtime store: a blocking exclusive lock waits at most 15 s."""

    DEADLINE_S = 15.0

    def __getattr__(self, name: str) -> Any:
        return getattr(fcntl, name)

    def flock(self, fd: int, operation: int) -> None:
        if operation != fcntl.LOCK_EX:
            fcntl.flock(fd, operation)
            return
        deadline = time.monotonic() + self.DEADLINE_S
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        "state lock not acquired within 15 s (self-deadlock?)"
                    ) from None
                time.sleep(0.005)


@pytest.fixture(autouse=True)
def _bounded_state_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    assert store_module.fcntl is fcntl
    monkeypatch.setattr(store_module, "fcntl", _BoundedFlock())


@pytest.fixture(autouse=True)
def _pinned_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "_utc_now", lambda: NOW)


@pytest.fixture(autouse=True)
def _isolated_git(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # git discovery never leaves tmp_path; no global / system config (hooks, signing)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.delenv("NEXUS_TARGET_ROOT_OVERRIDE", raising=False)


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path / "state"


@pytest.fixture
def service(state_dir: Path) -> SelfHostedTaskService:
    return SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)


@pytest.fixture
def roots(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace the facade's target-root resolver by a recorder with fixed answers."""
    calls: list[dict[str, Any]] = []

    def resolve(**kwargs: Any) -> tuple[Path, Path]:
        calls.append(kwargs)
        return ROOTS

    monkeypatch.setattr(service_module, "resolve_canonical_target_roots", resolve)
    return calls


def _request(**overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "task_id": "t1",
        "what": "W",
        "why": "Y",
        "allowed_files": ["a.py"],
        "verifier_commands": ["pytest -q"],
        "controller_revision": SHA_A,
        "controller_repo_root": "/repo/ctl",
    }
    request.update(overrides)
    return request


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> SimpleNamespace:
    """A temporary git repository: A -> B on main, C on a side branch from A."""
    root = tmp_path / "ctl"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "commit", "-q", "--allow-empty", "-m", "A")
    a = _git(root, "rev-parse", "HEAD")
    _git(root, "commit", "-q", "--allow-empty", "-m", "B")
    b = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "-b", "side", a)
    _git(root, "commit", "-q", "--allow-empty", "-m", "C")
    c = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-q", "main")
    return SimpleNamespace(root=root, a=a, b=b, c=c)


class RecordingSubprocess:
    """Facade ``subprocess`` replacement: records every ``run`` and delegates."""

    def __init__(self, calls: list[Any]) -> None:
        self.calls = calls

    def run(self, argv: list[str], **kwargs: Any) -> Any:
        self.calls.append((list(argv), str(kwargs.get("cwd")), sorted(kwargs)))
        return subprocess.run(argv, **kwargs)


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


# ---------------------------------------------------------------------------
# member table

SIGNATURES = {
    "build_contract": (
        "function",
        "(self, request: 'Mapping[str, Any]') -> 'ArchitectTaskContract'",
    ),
    "_terminal_retry_revision_refresh_allowed": (
        "staticmethod",
        "(existing: 'Mapping[str, Any]', request: 'Mapping[str, Any]', "
        "contract: 'ArchitectTaskContract') -> 'bool'",
    ),
    "_contract_from_state": (
        "function",
        "(self, state: 'Mapping[str, Any]') -> 'ArchitectTaskContract'",
    ),
    "_prompt": ("staticmethod", "(contract: 'ArchitectTaskContract') -> 'str'"),
    "_set_child_pgid": (
        "function",
        "(self, task_id: 'str', attempt_id: 'str', pgid: 'Optional[int]') -> 'None'",
    ),
    "_lease_from_state": (
        "function",
        "(self, state: 'Mapping[str, Any]') -> 'TargetWorktreeLease'",
    ),
    "_capture_resumed_candidate": (
        "function",
        "(self, contract: 'ArchitectTaskContract', controller: "
        "'SelfHostedDevelopmentController', lease: 'TargetWorktreeLease', "
        "state: 'Mapping[str, Any]')",
    ),
    "_receipt_from_state": (
        "staticmethod",
        "(value: 'Any') -> 'Optional[WorkerExecutionReceipt]'",
    ),
    "_escalation_policy": (
        "staticmethod",
        "(contract: 'ArchitectTaskContract') -> 'Optional[WorkerEscalationPolicy]'",
    ),
}


def test_task_build_members_keep_kinds_signatures_and_docstrings() -> None:
    for name, (kind, signature) in SIGNATURES.items():
        static = inspect.getattr_static(SelfHostedTaskService, name)
        assert type(static).__name__ == kind, name
        func = static.__func__ if isinstance(static, staticmethod) else static
        assert str(inspect.signature(func)) == signature, name
        assert func.__doc__ is None, name
    svc = SelfHostedTaskService(
        state_dir=Path("/nonexistent-s8b"), auto_reconcile=False, ephemeral=True
    )
    # the static helpers are reachable from the class and from an instance (runtime bridge)
    for name in ("_prompt", "_receipt_from_state", "_escalation_policy"):
        assert getattr(svc, name) is getattr(SelfHostedTaskService, name)


# ---------------------------------------------------------------------------
# build_contract: the derived contract

GOLDEN_MINIMAL_HASH = "977d1e0073c3ec129b2745bab8a3ff2b05de58e316b57b0302e36f5458f9731c"


def test_build_contract_minimal_request(service, roots) -> None:
    contract = service.build_contract(_request())
    assert type(contract) is ArchitectTaskContract
    assert contract.contract_hash == GOLDEN_MINIMAL_HASH
    assert contract.model_dump(mode="json") == {
        "schema": "nexus.self_hosted_task_contract.v2",
        "task_id": "t1",
        "objective": "W",
        "goal": {"what": "W", "why": "Y"},
        "architecture_decisions": [
            {
                "decision_id": "target-boundary",
                "selected_option": "Target-only mutation",
                "rationale": "Preserve Controller immutability during worker execution",
                "rejected_alternatives": ["Controller mutation"],
            }
        ],
        "acceptance_profile": {
            "verifier_commands": ["pytest -q"],
            "protected_contracts": [],
            "authorized_deletions": [],
            "required_evidence": [
                "candidate_state_hash",
                "controller_unchanged",
                "verified_candidate_receipt",
            ],
        },
        "human_approval_policy": {
            "approver_roles": ["James"],
            "decision_approval_required": True,
            "promotion_approval_required": True,
        },
        "controller_revision": SHA_A,
        "target_base_revision": SHA_A,
        "controller_repo_root": "/repo/ctl",
        "target_repo_root": "/targets/t1",
        "target_worktree_root": "/targets",
        "allowed_files": ["a.py"],
        "forbidden_files": [],
        "authorized_deletions": [],
        "verifier_commands": ["pytest -q"],
        "protected_contracts": [],
        "preferred_provider": "codex",
        "fallback_provider": None,
        "provider_order": ["codex"],
        "maximum_provider_calls": 1,
        "maximum_replans": 0,
        "maximum_attempts_per_task": 5,
        "maximum_wall_time_seconds": 0.0,
        "maximum_changed_files": 0,
        "maximum_deleted_files": 0,
        "mutation_mode": "WORKING_TREE_ONLY",
        "human_approval_required": True,
        "collaboration_realm": None,
        "expected_evidence": None,
        "contract_hash": GOLDEN_MINIMAL_HASH,
    }
    assert roots == [
        {
            "task_id": "t1",
            "campaign_id": None,
            "requested_target_worktree_root": None,
            "requested_target_repo_root": None,
        }
    ]


UNIVERSE = {
    "universe_generation": 3,
    "subjects": [
        {
            "logical_subject_id": "git diff --check",
            "evidence_kind": "verifier-run",
            "requirement_mode": "REQUIRED",
            "applicability": "APPLICABLE",
        }
    ],
}


def _full_request(**overrides: Any) -> dict[str, Any]:
    return _request(
        worker=" Gemini ",
        fallback_provider="CODEX",
        what="  Do the thing  ",
        why="\tbecause\n",
        architecture_decisions=[
            {
                "decision_id": "d1",
                "selected_option": "opt",
                "rationale": "r",
                "rejected_alternatives": ["x"],
            }
        ],
        verifier_commands=["pytest -q", 7],
        protected_contracts=["p.v1"],
        authorized_deletions=["old.py"],
        allowed_files=["a.py", "old.py"],
        forbidden_files=["secret.py"],
        approver_roles=("James", "Owner"),
        target_base_revision=SHA_B,
        campaign_id="camp",
        target_worktree_root="/w",
        target_repo_root="/w/r",
        maximum_attempts_per_task="3",
        maximum_wall_time_seconds="12.5",
        maximum_changed_files="4",
        maximum_deleted_files=2,
        fail_to_pass_required=True,
        expected_evidence=UNIVERSE,
        **overrides,
    )


GOLDEN_FULL_HASH = "6d69331ec00596147be1e4ff1303fb12f1c751ea427ac0f9d70a74492edc052d"


def test_build_contract_full_request(service, roots) -> None:
    contract = service.build_contract(_full_request())
    dumped = contract.model_dump(mode="json")
    assert dumped["task_id"] == "t1"
    assert dumped["objective"] == "Do the thing"
    assert dumped["goal"] == {"what": "Do the thing", "why": "because"}
    assert dumped["architecture_decisions"] == [
        {
            "decision_id": "d1",
            "selected_option": "opt",
            "rationale": "r",
            "rejected_alternatives": ["x"],
        }
    ]
    assert dumped["acceptance_profile"] == {
        "verifier_commands": ["pytest -q", "7"],
        "protected_contracts": ["p.v1"],
        "authorized_deletions": ["old.py"],
        "required_evidence": [
            "candidate_state_hash",
            "controller_unchanged",
            "verified_candidate_receipt",
            "fail_to_pass_base_verifier",
        ],
    }
    assert dumped["human_approval_policy"]["approver_roles"] == ["James", "Owner"]
    assert dumped["controller_revision"] == SHA_A
    assert dumped["target_base_revision"] == SHA_B
    assert dumped["forbidden_files"] == ["secret.py"]
    assert dumped["verifier_commands"] == ["pytest -q", "7"]
    assert dumped["preferred_provider"] == "gemini"
    assert dumped["fallback_provider"] == "codex"
    assert dumped["provider_order"] == ["gemini", "codex"]
    assert dumped["maximum_provider_calls"] == 2
    assert dumped["maximum_attempts_per_task"] == 3
    assert dumped["maximum_wall_time_seconds"] == 12.5
    assert dumped["maximum_changed_files"] == 4
    assert dumped["maximum_deleted_files"] == 2
    assert dumped["expected_evidence"] == ExpectedEvidenceUniverse.model_validate(
        UNIVERSE
    ).model_dump(mode="json")
    assert roots == [
        {
            "task_id": "t1",
            "campaign_id": "camp",
            "requested_target_worktree_root": "/w",
            "requested_target_repo_root": "/w/r",
        }
    ]
    assert contract.contract_hash == GOLDEN_FULL_HASH


def test_build_contract_does_not_mutate_the_request(service, roots, monkeypatch) -> None:
    monkeypatch.setattr(
        service_module,
        "validate_workforce_dispatch_binding",
        lambda request: {"provider": "gemini", "model": "m", "worker_id": "w"},
    )
    request = _full_request()
    before = json.dumps(request, sort_keys=True)
    service.build_contract(request)
    assert json.dumps(request, sort_keys=True) == before


def test_build_contract_accepts_any_mapping(service, roots) -> None:
    from types import MappingProxyType

    contract = service.build_contract(MappingProxyType(_request()))
    assert contract.contract_hash == GOLDEN_MINIMAL_HASH


# ---------------------------------------------------------------------------
# build_contract: refusals (in order)


@pytest.mark.parametrize(
    ("request_", "error", "message"),
    [
        (_request(prompt="p"), ValueError, "prompt is not accepted; submit WHAT and WHY"),
        (
            _request(worker="x"),
            ValueError,
            "worker must be one of: auto, " + ", ".join(SUPPORTED_WORKER_PROVIDERS),
        ),
        (
            _request(worker="auto", worker_order=[]),
            ValueError,
            "worker_order must be non-empty for auto selection",
        ),
        (
            _request(worker="auto", worker_order=["codex", "codex"]),
            ValueError,
            "worker_order contains an unknown or duplicate provider",
        ),
        (
            _request(worker="auto", worker_order=["codex", "nope"]),
            ValueError,
            "worker_order contains an unknown or duplicate provider",
        ),
        (
            _request(fallback_worker="zz"),
            ValueError,
            "fallback_worker must be one of: " + ", ".join(SUPPORTED_WORKER_PROVIDERS),
        ),
        (_request(fallback_worker=" CODEX"), ValueError, "fallback_worker must differ from worker"),
        (_request(what=" "), ValueError, "what and why are required"),
        (_request(why=""), ValueError, "what and why are required"),
        (_request(collaboration_realm=[1]), ValueError, "COLLABORATION_REALM_INVALID"),
        (_request(fail_to_pass_required=1), ValueError, "FAIL_TO_PASS_REQUIRED_INVALID"),
        (_request(fail_to_pass_required="true"), ValueError, "FAIL_TO_PASS_REQUIRED_INVALID"),
    ],
    ids=[
        "prompt",
        "worker",
        "auto-empty",
        "auto-duplicate",
        "auto-unknown",
        "fallback-unknown",
        "fallback-equal",
        "what",
        "why",
        "realm-type",
        "f2p-int",
        "f2p-str",
    ],
)
def test_build_contract_refusals(service, roots, request_, error, message) -> None:
    with pytest.raises(error) as caught:
        service.build_contract(request_)
    assert str(caught.value) == message


def test_build_contract_refusal_order(service, roots) -> None:
    # prompt before everything, worker before what/why, what/why before the realm,
    # the realm before fail_to_pass_required
    with pytest.raises(ValueError, match="^prompt is not accepted"):
        service.build_contract(_request(prompt="p", worker="x", what=""))
    with pytest.raises(ValueError, match="^worker must be one of"):
        service.build_contract(_request(worker="x", what=""))
    with pytest.raises(ValueError, match="^what and why are required$"):
        service.build_contract(_request(what="", collaboration_realm=[1]))
    with pytest.raises(ValueError, match="^COLLABORATION_REALM_INVALID$"):
        service.build_contract(_request(collaboration_realm=[1], fail_to_pass_required=1))
    # nothing is resolved before the what / why check passes; the realm comes after
    assert len(roots) == 1


def test_build_contract_target_roots_resolved_before_the_realm_check(service, roots) -> None:
    with pytest.raises(ValueError, match="^COLLABORATION_REALM_INVALID$"):
        service.build_contract(_request(collaboration_realm=[1]))
    assert len(roots) == 1


def test_build_contract_invalid_realm_chains_the_validation_error(service, roots) -> None:
    with pytest.raises(ValueError, match="^COLLABORATION_REALM_INVALID$") as caught:
        service.build_contract(_request(collaboration_realm={"a": 1}))
    assert type(caught.value.__cause__).__name__ == "ValidationError"


def test_build_contract_missing_allowed_files_is_a_key_error(service, roots) -> None:
    request = _request()
    del request["allowed_files"]
    with pytest.raises(KeyError, match="allowed_files"):
        service.build_contract(request)
    assert len(roots) == 1


def test_build_contract_model_validation_errors_propagate(service, roots) -> None:
    with pytest.raises(Exception) as caught:
        service.build_contract(_request(verifier_commands=[]))
    assert type(caught.value).__name__ == "ValidationError"
    assert "verifier_commands must be non-empty" in str(caught.value)
    with pytest.raises(Exception, match="provider_order must include"):
        service.build_contract(_request(worker="gemini", worker_order=["zz"]))


# ---------------------------------------------------------------------------
# build_contract: provider selection


@pytest.mark.parametrize(
    ("overrides", "preferred", "fallback", "order", "calls"),
    [
        ({}, "codex", None, ["codex"], 1),
        ({"worker": "gemini"}, "gemini", None, ["gemini"], 1),
        ({"worker": " GEMINI "}, "gemini", None, ["gemini"], 1),
        ({"worker": "auto"}, "codex", "gemini", list(SUPPORTED_WORKER_PROVIDERS), 8),
        ({"worker": " AUTO "}, "codex", "gemini", list(SUPPORTED_WORKER_PROVIDERS), 8),
        (
            {"worker": "auto", "worker_order": [" Agy", "codex"]},
            "agy",
            "codex",
            ["agy", "codex"],
            2,
        ),
        ({"worker": "auto", "worker_order": ["mimo"]}, "mimo", None, ["mimo"], 1),
        (
            {"worker": "auto", "fallback_worker": "codex", "worker_order": ["agy"]},
            "agy",
            "codex",
            ["agy", "codex"],
            2,
        ),
        (
            {"worker": "auto", "fallback_worker": "agy", "worker_order": ["codex", "agy"]},
            "codex",
            "agy",
            ["codex", "agy"],
            2,
        ),
        (
            {"worker": "gemini", "fallback_worker": "codex"},
            "gemini",
            "codex",
            ["gemini", "codex"],
            2,
        ),
        (
            {"worker": "gemini", "fallback_provider": "codex"},
            "gemini",
            "codex",
            ["gemini", "codex"],
            2,
        ),
        (
            {"worker": "gemini", "fallback_worker": "codex", "fallback_provider": "agy"},
            "gemini",
            "codex",
            ["gemini", "codex"],
            2,
        ),
        (
            {"worker": "gemini", "fallback_worker": None, "fallback_provider": "agy"},
            "gemini",
            None,
            ["gemini"],
            1,
        ),
        (
            {"worker": "gemini", "worker_order": ["gemini", "codex", "agy"]},
            "gemini",
            "codex",
            ["gemini", "codex", "agy"],
            1,
        ),
        (
            {"worker": "gemini", "worker_order": ["gemini", "codex"], "fallback_worker": "agy"},
            "gemini",
            "agy",
            ["gemini", "codex", "agy"],
            2,
        ),
        (
            {"worker": "gemini", "worker_order": ("GEMINI", "codex")},
            "gemini",
            "codex",
            ["gemini", "codex"],
            1,
        ),
    ],
)
def test_build_contract_provider_selection(
    service, roots, overrides, preferred, fallback, order, calls
) -> None:
    contract = service.build_contract(_request(**overrides))
    assert contract.preferred_provider == preferred
    assert contract.fallback_provider == fallback
    assert contract.provider_order == order
    assert contract.maximum_provider_calls == calls


# ---------------------------------------------------------------------------
# build_contract: workforce dispatch binding

BINDING = {"provider": "gemini", "model": "m-1", "worker_id": "w-1"}


@pytest.fixture
def binding(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    seen: list[Any] = []

    def validate(request: Any) -> dict[str, str]:
        seen.append(dict(request))
        return dict(BINDING)

    monkeypatch.setattr(service_module, "validate_workforce_dispatch_binding", validate)
    return seen


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"worker": "codex"}, "WORKFORCE_ADMISSION_PROVIDER_MISMATCH"),
        ({"worker": "agy"}, "WORKFORCE_ADMISSION_PROVIDER_MISMATCH"),
        ({"provider": "codex"}, "WORKFORCE_ADMISSION_PROVIDER_MISMATCH"),
        ({"worker_id": "w-2"}, "WORKFORCE_ADMISSION_WORKER_MISMATCH"),
        ({"model": "m-2"}, "WORKFORCE_ADMISSION_MODEL_MISMATCH"),
        ({"worker": "codex", "worker_id": "w-2"}, "WORKFORCE_ADMISSION_PROVIDER_MISMATCH"),
        ({"provider": "codex", "worker_id": "w-2"}, "WORKFORCE_ADMISSION_PROVIDER_MISMATCH"),
        ({"worker_id": "w-2", "model": "m-2"}, "WORKFORCE_ADMISSION_WORKER_MISMATCH"),
        ({"model": "m-2", "worker": "x"}, "WORKFORCE_ADMISSION_PROVIDER_MISMATCH"),
    ],
)
def test_dispatch_binding_mismatches(service, roots, binding, overrides, code) -> None:
    with pytest.raises(RuntimeError) as caught:
        service.build_contract(_request(**overrides))
    assert str(caught.value) == code
    assert len(binding) == 1 and roots == []


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"worker": ""},
        {"worker": " Auto "},
        {"worker": "gemini"},
        {"worker": " GEMINI "},
        {"provider": " GEMINI "},
        {"provider": ""},
        {"worker_id": " w-1 "},
        {"model": " m-1 "},
        {"model": None, "worker_id": None, "provider": None},
        {"worker": "auto", "worker_order": ["codex", "agy"]},
    ],
)
def test_dispatch_binding_overrides_the_provider(service, roots, binding, overrides) -> None:
    contract = service.build_contract(_request(**overrides))
    assert contract.preferred_provider == "gemini"
    assert contract.provider_order == ["gemini"]
    assert contract.fallback_provider is None
    assert contract.maximum_provider_calls == 1
    assert binding == [_request(**overrides)]


def test_dispatch_binding_keeps_a_fallback(service, roots, binding) -> None:
    contract = service.build_contract(_request(fallback_worker="codex"))
    assert (contract.preferred_provider, contract.fallback_provider) == ("gemini", "codex")
    assert contract.provider_order == ["gemini", "codex"]
    assert contract.maximum_provider_calls == 2
    with pytest.raises(ValueError, match="fallback_worker must differ from worker"):
        service.build_contract(_request(fallback_worker="gemini"))


def test_dispatch_binding_none_keeps_the_request(service, roots, monkeypatch) -> None:
    seen: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "validate_workforce_dispatch_binding",
        lambda request: seen.append(request),
    )
    request = _request(worker="agy", provider="codex", worker_id="x", model="y")
    contract = service.build_contract(request)
    assert seen == [request] and seen[0] is request
    assert contract.preferred_provider == "agy"


def test_dispatch_binding_error_propagates_first(service, roots, monkeypatch) -> None:
    def refuse(request: Any) -> Any:
        raise RuntimeError("WORKFORCE_DISPATCH_BINDING_REQUIRED")

    monkeypatch.setattr(service_module, "validate_workforce_dispatch_binding", refuse)
    with pytest.raises(RuntimeError, match="^WORKFORCE_DISPATCH_BINDING_REQUIRED$"):
        service.build_contract(_request(what=""))
    # but "prompt" is refused before the binding is validated
    with pytest.raises(ValueError, match="^prompt is not accepted"):
        service.build_contract(_request(prompt="p"))


def test_real_dispatch_binding_is_none_for_a_plain_request(service, roots) -> None:
    assert service_module.validate_workforce_dispatch_binding(_request()) is None


# ---------------------------------------------------------------------------
# build_contract: identity, decisions, evidence, owner-inline confirmation


def test_task_id_default_uses_uuid4(service, roots, monkeypatch) -> None:
    monkeypatch.setattr(
        service_module, "uuid4", lambda: SimpleNamespace(hex="0123456789abcdef0123")
    )
    request = _request()
    del request["task_id"]
    contract = service.build_contract(request)
    assert contract.task_id == "mcp-0123456789ab"
    assert roots[0]["task_id"] == "mcp-0123456789ab"
    assert service.build_contract(_request(task_id="")).task_id == "mcp-0123456789ab"
    assert service.build_contract(_request(task_id=17)).task_id == "17"


def test_architecture_decisions(service, roots) -> None:
    model = ArchitectureDecision(
        decision_id="m", selected_option="o", rationale="r", rejected_alternatives=["z"]
    )
    contract = service.build_contract(
        _request(
            architecture_decisions=[
                model,
                {
                    "decision_id": "d",
                    "selected_option": "s",
                    "rationale": "q",
                    "rejected_alternatives": [],
                },
            ]
        )
    )
    assert contract.architecture_decisions[0] is model
    assert contract.architecture_decisions[1].decision_id == "d"
    # an empty list falls back to the default decision
    default = service.build_contract(_request(architecture_decisions=[]))
    assert [d.decision_id for d in default.architecture_decisions] == ["target-boundary"]


@pytest.mark.parametrize("form", ["mapping", "model", "pairs", "dumpable"])
def test_expected_evidence_projection(service, roots, form) -> None:
    model = ExpectedEvidenceUniverse.model_validate(UNIVERSE)

    class Dumpable:
        def model_dump(self, mode: str) -> Any:
            assert mode == "json"
            return UNIVERSE

    raw: Any = {
        "mapping": UNIVERSE,
        "model": model,
        "pairs": list(UNIVERSE.items()),
        "dumpable": Dumpable(),
    }[form]
    contract = service.build_contract(_request(expected_evidence=raw))
    assert contract.expected_evidence == model
    assert contract.expected_evidence is not model


def test_expected_evidence_invalid_propagates(service, roots) -> None:
    with pytest.raises(Exception) as caught:
        service.build_contract(
            _request(expected_evidence={"universe_generation": -1, "subjects": []})
        )
    assert type(caught.value).__name__ == "ValidationError"
    assert service.build_contract(_request(expected_evidence=None)).expected_evidence is None


INLINE = ContractKind.OWNER_INLINE.value
MARKER = "repository-authority-change.v1"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        (
            {"authority_change_candidate_confirmation": "yes"},
            "AUTHORITY_CHANGE_CONFIRMATION_INVALID",
        ),
        ({"authority_change_candidate_confirmation": 1}, "AUTHORITY_CHANGE_CONFIRMATION_INVALID"),
        (
            {"authority_change_candidate_confirmation": None},
            "AUTHORITY_CHANGE_CONFIRMATION_INVALID",
        ),
        (
            {"authority_change_candidate_confirmation": True},
            "AUTHORITY_CHANGE_CONFIRMATION_MARKER_MISMATCH",
        ),
        ({"protected_contracts": [MARKER]}, "AUTHORITY_CHANGE_CONFIRMATION_MARKER_MISMATCH"),
        ({}, "AUTHORITY_CHANGE_CONFIRMATION_CONTRACT_MISMATCH"),
        ({"owner_inline_contract": [("a", 1)]}, "AUTHORITY_CHANGE_CONFIRMATION_CONTRACT_MISMATCH"),
        (
            {
                "authority_change_candidate_confirmation": True,
                "protected_contracts": [MARKER],
                "owner_inline_contract": {},
            },
            "AUTHORITY_CHANGE_CONFIRMATION_CONTRACT_MISMATCH",
        ),
        (
            {
                "authority_change_candidate_confirmation": True,
                "protected_contracts": [MARKER],
                "owner_inline_contract": {"authority_change_candidate_confirmation": 1},
            },
            "AUTHORITY_CHANGE_CONFIRMATION_CONTRACT_MISMATCH",
        ),
        (
            {"owner_inline_contract": {"authority_change_candidate_confirmation": 0}},
            "AUTHORITY_CHANGE_CONFIRMATION_CONTRACT_MISMATCH",
        ),
    ],
)
def test_owner_inline_confirmation_refusals(service, roots, overrides, code) -> None:
    request = _request(worker_candidate_ingress=True, contract_kind=INLINE, **overrides)
    with pytest.raises(RuntimeError) as caught:
        service.build_contract(request)
    assert str(caught.value) == code
    assert roots == [], "the confirmation is checked before the target roots are resolved"


@pytest.mark.parametrize(
    "overrides",
    [
        {"owner_inline_contract": {}},
        {"owner_inline_contract": {"authority_change_candidate_confirmation": False}},
        {
            "authority_change_candidate_confirmation": True,
            "protected_contracts": ["x", MARKER],
            "owner_inline_contract": {"authority_change_candidate_confirmation": True},
        },
    ],
)
def test_owner_inline_confirmation_accepted(service, roots, overrides) -> None:
    request = _request(worker_candidate_ingress=True, contract_kind=INLINE, **overrides)
    assert service.build_contract(request).task_id == "t1"


@pytest.mark.parametrize(
    "overrides",
    [
        {"worker_candidate_ingress": False, "contract_kind": INLINE},
        {"worker_candidate_ingress": 0, "contract_kind": INLINE},
        {"worker_candidate_ingress": True, "contract_kind": "TRACKED_TASK_CARD"},
        {"worker_candidate_ingress": True},
        {"worker_candidate_ingress": "yes", "contract_kind": "owner_inline"},
    ],
)
def test_owner_inline_confirmation_not_checked(service, roots, overrides) -> None:
    request = _request(authority_change_candidate_confirmation="garbage", **overrides)
    assert service.build_contract(request).task_id == "t1"


def test_owner_inline_truthy_ingress_is_checked(service, roots) -> None:
    request = _request(worker_candidate_ingress="yes", contract_kind=INLINE)
    with pytest.raises(RuntimeError, match="^AUTHORITY_CHANGE_CONFIRMATION_CONTRACT_MISMATCH$"):
        service.build_contract(request)


# ---------------------------------------------------------------------------
# build_contract: roots, revisions (real git), realm, fail-to-pass


def test_controller_root_default_is_the_resolved_cwd(service, roots, tmp_path, monkeypatch) -> None:
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.chdir(work)
    request = _request()
    del request["controller_repo_root"]
    contract = service.build_contract(request)
    assert contract.controller_repo_root == str(work.resolve())
    assert service.build_contract(_request(controller_repo_root="")).controller_repo_root == str(
        work.resolve()
    )


def test_controller_root_is_expanded_and_resolved(service, roots, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "ctl").mkdir()
    contract = service.build_contract(_request(controller_repo_root="~/ctl/../ctl"))
    assert contract.controller_repo_root == str((tmp_path / "ctl").resolve())


def test_controller_revision_default_is_git_head(service, roots, repo, monkeypatch) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(service_module, "subprocess", RecordingSubprocess(calls))
    request = _request(controller_repo_root=str(repo.root))
    del request["controller_revision"]
    contract = service.build_contract(request)
    assert contract.controller_revision == repo.b
    assert contract.target_base_revision == repo.b
    assert calls == [
        (["git", "rev-parse", "HEAD"], str(repo.root.resolve()), ["capture_output", "cwd", "text"])
    ]
    # an empty revision also asks git; a given one does not
    assert (
        service.build_contract(
            _request(controller_repo_root=str(repo.root), controller_revision="")
        ).controller_revision
        == repo.b
    )
    assert len(calls) == 2
    given = _request(controller_repo_root=str(repo.root), controller_revision=repo.a)
    assert service.build_contract(given).controller_revision == repo.a
    assert len(calls) == 2


def test_controller_revision_outside_git_is_head(service, roots, tmp_path, monkeypatch) -> None:
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    request = _request(controller_repo_root=str(plain))
    del request["controller_revision"]
    # the literal "HEAD" reaches the contract model, which refuses it
    with pytest.raises(Exception, match="controller_revision must be an exact 40-char") as caught:
        service.build_contract(request)
    assert type(caught.value).__name__ == "ValidationError"
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(
        service_module, "ArchitectTaskContract", lambda **kwargs: (seen.append(kwargs), "C")[1]
    )
    assert service.build_contract(request) == "C"
    assert (seen[0]["controller_revision"], seen[0]["target_base_revision"]) == ("HEAD", "HEAD")
    assert seen[0]["controller_repo_root"] == str(plain.resolve())
    # a non-string revision is passed through str()
    service.build_contract(_request(controller_revision=7, target_base_revision=8))
    assert (seen[1]["controller_revision"], seen[1]["target_base_revision"]) == ("7", "8")


def test_controller_revision_missing_root_raises(service, roots, tmp_path) -> None:
    request = _request(controller_repo_root=str(tmp_path / "missing"))
    del request["controller_revision"]
    with pytest.raises(FileNotFoundError):
        service.build_contract(request)


def test_target_base_revision(service, roots) -> None:
    assert service.build_contract(_request(target_base_revision="")).target_base_revision == SHA_A
    assert service.build_contract(_request(target_base_revision=None)).target_base_revision == SHA_A
    assert (
        service.build_contract(_request(target_base_revision=SHA_B)).target_base_revision == SHA_B
    )


def test_real_target_roots_are_used(service, tmp_path) -> None:
    worktree, repo_root = str(tmp_path / "w"), str(tmp_path / "w" / "r")
    expected = service_module.resolve_canonical_target_roots(
        task_id="t1",
        campaign_id="c",
        requested_target_worktree_root=worktree,
        requested_target_repo_root=repo_root,
    )
    contract = service.build_contract(
        _request(campaign_id="c", target_worktree_root=worktree, target_repo_root=repo_root)
    )
    assert (contract.target_worktree_root, contract.target_repo_root) == tuple(map(str, expected))
    with pytest.raises(ValueError, match="^DISABLED_TARGET_ROOT"):
        service.build_contract(_request(target_worktree_root="/x/nexus-worktrees/y"))


def _realm(
    collaboration_root: str = "/srv/nexus/collaboration", head: str = SHA_A
) -> CollaborationExecutionRealm:
    return CollaborationExecutionRealm.issue(
        control_plane={"repo_root": "/srv/nexus/control", "revision": "1" * 40},
        collaboration={
            "repository": {
                "repository_id": "James3014/Nexus-new",
                "canonical_remote": "https://github.com/James3014/Nexus-new.git",
            },
            "base": {"branch": "main", "head_sha": head},
            "repo_root": collaboration_root,
        },
        runtime_activation={"realm_id": "local-runtime", "activation_authorized": False},
        execution_root=str(ROOTS[0]),
    )


def test_collaboration_realm(service, roots) -> None:
    realm = _realm()
    contract = service.build_contract(
        _request(
            collaboration_realm=realm.model_dump(mode="json"),
            controller_repo_root="/srv/nexus/collaboration",
        )
    )
    assert contract.collaboration_realm == realm
    # a model instance is not a Mapping
    with pytest.raises(ValueError, match="^COLLABORATION_REALM_INVALID$"):
        service.build_contract(_request(collaboration_realm=realm))
    assert service.build_contract(_request(collaboration_realm=None)).collaboration_realm is None


def test_fail_to_pass_required(service, roots) -> None:
    on = service.build_contract(_request(fail_to_pass_required=True))
    off = service.build_contract(_request(fail_to_pass_required=False))
    assert on.acceptance_profile.required_evidence[-1] == "fail_to_pass_base_verifier"
    assert len(on.acceptance_profile.required_evidence) == 4
    assert off.contract_hash == GOLDEN_MINIMAL_HASH
    assert on.contract_hash != off.contract_hash


@pytest.mark.parametrize(
    ("field", "raw", "value"),
    [
        ("maximum_attempts_per_task", 0, 5),
        ("maximum_attempts_per_task", None, 5),
        ("maximum_attempts_per_task", "", 5),
        ("maximum_attempts_per_task", 2, 2),
        ("maximum_wall_time_seconds", None, 0.0),
        ("maximum_wall_time_seconds", "1.5", 1.5),
        ("maximum_changed_files", None, 0),
        ("maximum_changed_files", 9, 9),
        ("maximum_deleted_files", "", 0),
        ("maximum_deleted_files", "3", 3),
    ],
)
def test_budget_fields(service, roots, field, raw, value) -> None:
    assert getattr(service.build_contract(_request(**{field: raw})), field) == value


def test_budget_default_is_the_facade_constant(service, roots, monkeypatch) -> None:
    assert service.build_contract(_request()).maximum_attempts_per_task == 5
    monkeypatch.setattr(service_module, "DEFAULT_MAXIMUM_ATTEMPTS_PER_TASK", 7)
    assert service.build_contract(_request()).maximum_attempts_per_task == 7
    assert (
        service.build_contract(_request(maximum_attempts_per_task=0)).maximum_attempts_per_task == 7
    )


# ---------------------------------------------------------------------------
# _terminal_retry_revision_refresh_allowed


def _contract(root: Path | str, controller: str, target: str) -> Any:
    return SimpleNamespace(
        controller_revision=controller, target_base_revision=target, controller_repo_root=str(root)
    )


def _existing(
    request: Any = None, controller: str = "", target: str = "", **extra: Any
) -> dict[str, Any]:
    existing: dict[str, Any] = {
        "request": {"task_id": "t1", "what": "W"} if request is None else request,
        "contract": {"controller_revision": controller, "target_base_revision": target},
    }
    existing.update(extra)
    return existing


refresh = SelfHostedTaskService._terminal_retry_revision_refresh_allowed


def test_refresh_allowed_for_ancestors(repo, monkeypatch) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(service_module, "subprocess", RecordingSubprocess(calls))
    existing = _existing(controller=repo.a, target=repo.a)
    assert (
        refresh(existing, {"task_id": "t1", "what": "W"}, _contract(repo.root, repo.b, repo.b))
        is True
    )
    root = str(repo.root.resolve())
    assert calls == [
        (
            ["git", "merge-base", "--is-ancestor", repo.a, repo.b],
            root,
            ["capture_output", "cwd", "text"],
        ),
        (
            ["git", "merge-base", "--is-ancestor", repo.a, repo.b],
            root,
            ["capture_output", "cwd", "text"],
        ),
    ]


def test_refresh_controller_only_or_target_only(repo) -> None:
    request = {"task_id": "t1", "what": "W"}
    assert (
        refresh(
            _existing(controller=repo.a, target=repo.b),
            request,
            _contract(repo.root, repo.b, repo.b),
        )
        is True
    )
    assert (
        refresh(
            _existing(controller=repo.b, target=repo.a),
            request,
            _contract(repo.root, repo.b, repo.b),
        )
        is True
    )


def test_refresh_refused_for_a_non_ancestor_and_short_circuits(repo, monkeypatch) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(service_module, "subprocess", RecordingSubprocess(calls))
    request = {"task_id": "t1", "what": "W"}
    # controller C -> B is not an ancestor: the target pair is never asked
    assert (
        refresh(
            _existing(controller=repo.c, target=repo.a),
            request,
            _contract(repo.root, repo.b, repo.b),
        )
        is False
    )
    assert [c[0][3:] for c in calls] == [[repo.c, repo.b]]
    calls.clear()
    # backwards (B -> A) is refused on the second pair
    assert (
        refresh(
            _existing(controller=repo.a, target=repo.b),
            request,
            _contract(repo.root, repo.b, repo.a),
        )
        is False
    )
    assert [c[0][3:] for c in calls] == [[repo.a, repo.b], [repo.b, repo.a]]


def test_refresh_unknown_revision_is_refused(repo) -> None:
    request = {"task_id": "t1", "what": "W"}
    assert (
        refresh(
            _existing(controller="f" * 40, target=repo.a),
            request,
            _contract(repo.root, repo.b, repo.b),
        )
        is False
    )


def test_refresh_controller_root_is_expanded(repo, monkeypatch, tmp_path) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(service_module, "subprocess", RecordingSubprocess(calls))
    monkeypatch.setenv("HOME", str(tmp_path))
    request = {"task_id": "t1", "what": "W"}
    assert (
        refresh(
            _existing(controller=repo.a, target=repo.a),
            request,
            _contract("~/ctl/.", repo.b, repo.b),
        )
        is True
    )
    assert {c[1] for c in calls} == {str(repo.root.resolve())}


@pytest.mark.parametrize(
    ("controller", "target", "new_controller", "new_target"),
    [
        ("", SHA_A, SHA_B, SHA_B),
        (SHA_A, "", SHA_B, SHA_B),
        (SHA_A, SHA_A, "", SHA_B),
        (SHA_A, SHA_A, SHA_B, ""),
        (SHA_A, SHA_B, SHA_A, SHA_B),
    ],
    ids=["no-old-controller", "no-old-target", "no-new-controller", "no-new-target", "unchanged"],
)
def test_refresh_refused_without_a_revision_change(
    monkeypatch, controller, target, new_controller, new_target
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(service_module, "subprocess", RecordingSubprocess(calls))
    request = {"task_id": "t1", "what": "W"}
    existing = _existing(controller=controller, target=target)
    assert refresh(existing, request, _contract("/nowhere", new_controller, new_target)) is False
    assert calls == []


def test_refresh_contract_missing_or_none(monkeypatch) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(service_module, "subprocess", RecordingSubprocess(calls))
    request = {"task_id": "t1"}
    for contract in (None, {}, {"controller_revision": None, "target_base_revision": None}):
        existing = {"request": {"task_id": "t1"}, "contract": contract}
        assert refresh(existing, request, _contract("/nowhere", SHA_A, SHA_A)) is False
    assert calls == []


def test_refresh_refused_on_a_semantic_change(monkeypatch) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(service_module, "subprocess", RecordingSubprocess(calls))
    existing = _existing(controller=SHA_A, target=SHA_A)
    assert (
        refresh(existing, {"task_id": "t1", "what": "other"}, _contract("/nowhere", SHA_B, SHA_B))
        is False
    )
    assert calls == []


def test_refresh_compares_the_facade_semantic_payload(monkeypatch, repo) -> None:
    seen: list[Any] = []

    def payload(request: Any) -> Any:
        seen.append(dict(request))
        return "same"

    monkeypatch.setattr(service_module, "_terminal_retry_semantic_payload", payload)
    existing = _existing(request={"x": 1}, controller=repo.a, target=repo.a)
    assert refresh(existing, {"y": 2}, _contract(repo.root, repo.b, repo.b)) is True
    assert seen == [{"x": 1}, {"y": 2}]


@pytest.mark.parametrize("previous", [None, [("task_id", "t1")], (), 0])
def test_refresh_refused_without_a_mapping_request(monkeypatch, previous) -> None:
    seen: list[Any] = []
    monkeypatch.setattr(
        service_module, "_terminal_retry_semantic_payload", lambda r: seen.append(r)
    )
    existing = _existing(request=previous, controller=SHA_A, target=SHA_A)
    existing["request"] = previous
    assert refresh(existing, {"task_id": "t1"}, _contract("/nowhere", SHA_B, SHA_B)) is False
    assert seen == []


def test_refresh_a_string_request_raises() -> None:
    existing = {"request": "xy", "contract": {}}
    with pytest.raises(ValueError):
        refresh(existing, {}, _contract("/nowhere", SHA_B, SHA_B))


class _Proof:
    def __init__(self, log: list[Any], name: str, answer: bool) -> None:
        self.log, self.name, self.answer = log, name, answer

    def __call__(self, existing: Any) -> bool:
        self.log.append((self.name, existing))
        return self.answer


@pytest.mark.parametrize("key", ["action", "bound_action_request"])
@pytest.mark.parametrize(
    ("pre", "static", "expected_log", "result"),
    [
        (False, False, ["pre", "static"], False),
        (True, False, ["pre"], True),
        (False, True, ["pre", "static"], True),
        (True, True, ["pre"], True),
    ],
)
def test_refresh_action_bound_needs_a_predecessor_proof(
    monkeypatch, repo, key, pre, static, expected_log, result
) -> None:
    log: list[Any] = []
    monkeypatch.setattr(
        service_module, "_terminal_retry_pre_provider_state_allowed", _Proof(log, "pre", pre)
    )
    monkeypatch.setattr(
        service_module,
        "_terminal_retry_verifier_static_failure_allowed",
        _Proof(log, "static", static),
    )
    monkeypatch.setattr(service_module, "_terminal_retry_semantic_payload", lambda r: "same")
    existing = _existing(request={key: {}}, controller=repo.a, target=repo.a)
    assert refresh(existing, {}, _contract(repo.root, repo.b, repo.b)) is result
    assert [entry[0] for entry in log] == expected_log
    assert all(entry[1] is existing for entry in log)


def test_refresh_plain_request_skips_the_proofs(monkeypatch, repo) -> None:
    log: list[Any] = []
    monkeypatch.setattr(
        service_module, "_terminal_retry_pre_provider_state_allowed", _Proof(log, "pre", False)
    )
    monkeypatch.setattr(
        service_module,
        "_terminal_retry_verifier_static_failure_allowed",
        _Proof(log, "static", False),
    )
    existing = _existing(controller=repo.a, target=repo.a)
    assert (
        refresh(existing, {"task_id": "t1", "what": "W"}, _contract(repo.root, repo.b, repo.b))
        is True
    )
    assert log == []


def test_refresh_from_an_instance_and_from_submit_path(service, repo) -> None:
    existing = _existing(controller=repo.a, target=repo.a)
    request = {"task_id": "t1", "what": "W"}
    assert (
        service._terminal_retry_revision_refresh_allowed(
            existing, request, _contract(repo.root, repo.b, repo.b)
        )
        is True
    )


# ---------------------------------------------------------------------------
# _contract_from_state


def test_contract_from_state_rebuilds_from_the_request(service, monkeypatch) -> None:
    built: list[Any] = []
    monkeypatch.setattr(service, "build_contract", lambda request: (built.append(request), "C")[1])
    request = {"task_id": "t"}
    assert service._contract_from_state({"request": request, "contract": {"x": 1}}) == "C"
    assert built == [request] and built[0] is request


def test_contract_from_state_validates_the_stored_contract(service, roots) -> None:
    contract = service.build_contract(_request())
    stored = contract.model_dump(mode="json", exclude={"contract_hash"})
    for state in (
        {"contract": stored},
        {"request": None, "contract": stored},
        {"request": ["x"], "contract": stored},
    ):
        rebuilt = service._contract_from_state(state)
        assert type(rebuilt) is ArchitectTaskContract
        assert rebuilt.contract_hash == GOLDEN_MINIMAL_HASH


@pytest.mark.parametrize("state", [{}, {"contract": None}, {"contract": [1]}, {"request": "x"}])
def test_contract_from_state_without_a_contract(service, state) -> None:
    with pytest.raises(RuntimeError) as caught:
        service._contract_from_state(state)
    assert str(caught.value) == "task state is missing its contract"


def test_contract_from_state_invalid_contract_propagates(service, roots) -> None:
    with pytest.raises(Exception) as caught:
        service._contract_from_state({"contract": {"task_id": "t"}})
    assert type(caught.value).__name__ == "ValidationError"
    # the computed contract_hash is not an input field
    stored = service.build_contract(_request()).model_dump(mode="json")
    with pytest.raises(Exception, match="contract_hash"):
        service._contract_from_state({"contract": stored})


# ---------------------------------------------------------------------------
# _prompt


def test_prompt_text(service, roots) -> None:
    contract = service.build_contract(
        _request(
            what="Fix it",
            why="Broken",
            allowed_files=["a.py", "b/c.py"],
            verifier_commands=["pytest -q", "ruff check"],
        )
    )
    assert SelfHostedTaskService._prompt(contract) == (
        "WHAT: Fix it\n"
        "WHY: Broken\n"
        "Allowed files: a.py, b/c.py\n"
        "Work only in the isolated Target. Do not edit, delete, stage, commit, merge, push, or reset "
        "outside the allowed scope. Run every verifier command below after making the change; if any "
        "verifier fails, diagnose and repair within the allowed files before returning.\n"
        "Required verifier commands:\n- pytest -q\n- ruff check\n"
        "Return a concise summary only after all required verifiers pass."
    )


def test_prompt_reads_only_goal_files_and_verifiers() -> None:
    contract = SimpleNamespace(
        goal=SimpleNamespace(what="w", why="y"), allowed_files=[], verifier_commands=[]
    )
    text = SelfHostedTaskService._prompt(cast(Any, contract))
    assert text.startswith("WHAT: w\nWHY: y\nAllowed files: \n")
    assert "Required verifier commands:\n\nReturn a concise summary" in text


# ---------------------------------------------------------------------------
# _set_child_pgid


def _lock_held(state_dir: Path) -> bool:
    path = state_dir / ".state.lock"
    if not path.exists():
        return False
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return False


def _seed(service: SelfHostedTaskService, **extra: Any) -> dict[str, Any]:
    state: dict[str, Any] = {"task_id": "t", "attempt_id": "attempt-1", "status": "WORKER_RUNNING"}
    state.update(extra)
    return service._write_state("t", state)


def _read(state_dir: Path) -> dict[str, Any]:
    return json.loads((state_dir / "t.json").read_text(encoding="utf-8"))


def test_set_child_pgid_writes_under_the_lock(service, state_dir, monkeypatch) -> None:
    _seed(service)
    clock: list[bool] = []
    monkeypatch.setattr(
        service_module, "_utc_now", lambda: (clock.append(_lock_held(state_dir)), "T-LOCKED")[1]
    )
    assert service._set_child_pgid("t", "attempt-1", 4242) is None
    state = _read(state_dir)
    assert state["worker_child_pgid"] == 4242 and state["updated_at"] == "T-LOCKED"
    assert clock == [True]
    service._set_child_pgid("t", "attempt-1", None)
    assert _read(state_dir)["worker_child_pgid"] is None


@pytest.mark.parametrize(
    ("seed", "attempt"),
    [
        ({}, "attempt-2"),
        ({"status": "FINAL_BLOCK"}, "attempt-1"),
        ({"status": "CANCELLED"}, "attempt-1"),
        ({"attempt_id": None}, "attempt-1"),
    ],
)
def test_set_child_pgid_refusals_leave_the_state(
    service, state_dir, monkeypatch, seed, attempt
) -> None:
    _seed(service, **seed)
    before = _read(state_dir)
    clock: list[str] = []
    monkeypatch.setattr(service_module, "_utc_now", lambda: (clock.append("x"), "T")[1])
    assert service._set_child_pgid("t", attempt, 7) is None
    assert _read(state_dir) == before
    assert clock == []


def test_set_child_pgid_unknown_task(service, state_dir) -> None:
    assert service._set_child_pgid("nope", "attempt-1", 7) is None
    assert not (state_dir / "nope.json").exists()


def test_set_child_pgid_reads_the_facade_terminal_statuses(service, state_dir, monkeypatch) -> None:
    _seed(service)
    service._set_child_pgid("t", "attempt-1", 1)
    monkeypatch.setattr(service_module, "TERMINAL_STATUSES", frozenset({"WORKER_RUNNING"}))
    service._set_child_pgid("t", "attempt-1", 2)
    assert _read(state_dir)["worker_child_pgid"] == 1
    monkeypatch.setattr(service_module, "TERMINAL_STATUSES", frozenset())
    _seed(service, status="FINAL_BLOCK")
    service._set_child_pgid("t", "attempt-1", 3)
    assert _read(state_dir)["worker_child_pgid"] == 3


def test_set_child_pgid_goes_through_mutate_state(service, monkeypatch) -> None:
    _seed(service)
    calls: list[Any] = []
    real = service._mutate_state
    monkeypatch.setattr(service, "_mutate_state", lambda t, f: (calls.append(t), real(t, f))[1])
    service._set_child_pgid("t", "attempt-1", 5)
    assert calls == ["t"]
    hits: list[str] = []
    cls_real = inspect.getattr_static(SelfHostedTaskService, "_mutate_state")
    other = SelfHostedTaskService(state_dir=service.state_dir, auto_reconcile=False, ephemeral=True)
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_mutate_state",
        lambda self, t, f: (hits.append(t), cls_real(self, t, f))[1],
    )
    other._set_child_pgid("t", "attempt-1", 6)
    assert hits == ["t"]


def test_set_child_pgid_waits_for_a_lock_holder(service, state_dir) -> None:
    import threading

    _seed(service)
    entered, release, done = threading.Event(), threading.Event(), threading.Event()

    def hold() -> None:
        with service._state_lock():
            entered.set()
            release.wait(10)

    holder = threading.Thread(target=hold, daemon=True)
    holder.start()
    assert entered.wait(10)
    writer = threading.Thread(
        target=lambda: (service._set_child_pgid("t", "attempt-1", 9), done.set()), daemon=True
    )
    writer.start()
    time.sleep(0.2)
    assert not done.is_set() and "worker_child_pgid" not in _read(state_dir)
    release.set()
    holder.join(10)
    writer.join(10)
    assert done.is_set() and _read(state_dir)["worker_child_pgid"] == 9


# ---------------------------------------------------------------------------
# _lease_from_state / _capture_resumed_candidate


LEASE = {
    "schema": "s",
    "lease_id": "l",
    "task_id": "t",
    "controller_revision": SHA_A,
    "target_base_revision": SHA_A,
    "target_worktree": "/w",
    "target_branch": "b",
    "initial_head": SHA_A,
    "initial_status_sha256": "0" * 64,
    "controller_status_sha256": "1" * 64,
    "created_from_exact_revision": True,
    "commit_created": False,
    "merge_performed": False,
}


def test_lease_from_state(service) -> None:
    lease = service._lease_from_state({"lease": LEASE})
    assert lease == TargetWorktreeLease(**LEASE)
    assert type(lease) is TargetWorktreeLease
    with pytest.raises(TypeError):
        service._lease_from_state({"lease": {**LEASE, "extra": 1}})
    with pytest.raises(TypeError):
        service._lease_from_state({"lease": {}})


@pytest.mark.parametrize("state", [{}, {"lease": None}, {"lease": [("a", 1)]}, {"lease": "x"}])
def test_lease_from_state_missing(service, state) -> None:
    with pytest.raises(RuntimeError) as caught:
        service._lease_from_state(state)
    assert str(caught.value) == "durable lease evidence is missing"


class Controller:
    def __init__(self, digest: str) -> None:
        self.digest = digest
        self.calls: list[Any] = []

    def collect_candidate(self, contract: Any, lease: Any) -> Any:
        self.calls.append((contract, lease))
        return SimpleNamespace(candidate_state_hash=self.digest)


@pytest.mark.parametrize(
    "state",
    [
        {},
        {"candidate": None},
        {"candidate": {}},
        {"candidate": {"candidate_state_hash": ""}},
        {"candidate": {"candidate_state_hash": "h"}},
    ],
)
def test_capture_resumed_candidate(service, state) -> None:
    controller = Controller("h")
    contract, lease = object(), object()
    candidate = service._capture_resumed_candidate(contract, controller, lease, state)
    assert candidate.candidate_state_hash == "h"
    assert controller.calls == [(contract, lease)]


def test_capture_resumed_candidate_changed(service) -> None:
    controller = Controller("new")
    with pytest.raises(RuntimeError) as caught:
        service._capture_resumed_candidate(
            object(), controller, object(), {"candidate": {"candidate_state_hash": "old"}}
        )
    assert str(caught.value) == "candidate state changed during recovery"
    assert len(controller.calls) == 1


def test_capture_resumed_candidate_collect_error_propagates(service) -> None:
    class Broken:
        def collect_candidate(self, contract: Any, lease: Any) -> Any:
            raise OSError("gone")

    with pytest.raises(OSError, match="gone"):
        service._capture_resumed_candidate(object(), Broken(), object(), {})


# ---------------------------------------------------------------------------
# _receipt_from_state / _escalation_policy

RECEIPT = {
    "provider": "codex",
    "task_id": "t",
    "target_worktree": "/w",
    "worker_status": "COMPLETED",
    "outcome": "SUCCEEDED",
    "exit_code": 0,
    "executable_identity": "x",
    "argv": ["codex", "exec"],
    "stdout_sha256": "0" * 64,
    "stderr_sha256": "1" * 64,
    "wall_time_ms": 5,
    "process_group_id": None,
    "process_group_killed": False,
    "timed_out": False,
    "provider_calls": 1,
    "evidence_complete": True,
    "commit_created": False,
    "merge_performed": False,
    "push_performed": False,
}


def test_receipt_from_state() -> None:
    receipt = SelfHostedTaskService._receipt_from_state(RECEIPT)
    assert type(receipt) is WorkerExecutionReceipt
    assert receipt.argv == ("codex", "exec")
    assert receipt == WorkerExecutionReceipt(**{**RECEIPT, "argv": ("codex", "exec")})
    assert SelfHostedTaskService._receipt_from_state(receipt) is receipt
    no_argv = {k: v for k, v in RECEIPT.items() if k != "argv"}
    without = SelfHostedTaskService._receipt_from_state(no_argv)
    assert without is not None and without.argv == ()
    assert RECEIPT["argv"] == ["codex", "exec"], "the input is not changed"


@pytest.mark.parametrize(
    "value",
    [
        None,
        "x",
        [("outcome", "x")],
        {},
        {"provider": "codex"},
        {"outcome": "x"},
        {**RECEIPT, "extra": 1},
        {**RECEIPT, "argv": 5},
    ],
)
def test_receipt_from_state_rejects(value) -> None:
    assert SelfHostedTaskService._receipt_from_state(value) is None


def test_receipt_from_state_swallows_a_value_error() -> None:
    class Argv:
        def __iter__(self) -> Any:
            raise ValueError("bad argv")

    assert SelfHostedTaskService._receipt_from_state({**RECEIPT, "argv": Argv()}) is None


def test_receipt_from_state_other_errors_propagate() -> None:
    from collections.abc import Mapping as AbcMapping

    class Weird(AbcMapping):
        def __iter__(self) -> Any:
            return iter(RECEIPT)

        def __len__(self) -> int:
            return len(RECEIPT)

        def __getitem__(self, key: str) -> Any:
            if key == "argv":
                raise LookupError("boom")
            return RECEIPT[key]

    with pytest.raises(LookupError, match="boom"):
        SelfHostedTaskService._receipt_from_state(Weird())


@pytest.mark.parametrize(
    ("preferred", "fallback", "order", "expected"),
    [
        ("codex", "gemini", ["codex", "agy", "gemini"], ("codex", "agy", "gemini")),
        ("codex", "gemini", [], ("codex", "gemini")),
        ("codex", "gemini", None, ("codex", "gemini")),
    ],
)
def test_escalation_policy(preferred, fallback, order, expected) -> None:
    contract = SimpleNamespace(
        preferred_provider=preferred, fallback_provider=fallback, provider_order=order
    )
    policy = SelfHostedTaskService._escalation_policy(cast(Any, contract))
    assert policy == WorkerEscalationPolicy(
        cheap_provider=preferred, strong_provider=fallback, provider_order=expected
    )
    assert type(policy) is WorkerEscalationPolicy


@pytest.mark.parametrize(
    ("preferred", "fallback"), [("codex", None), ("", "gemini"), (None, None), ("codex", "")]
)
def test_escalation_policy_none(preferred, fallback) -> None:
    contract = SimpleNamespace(
        preferred_provider=preferred, fallback_provider=fallback, provider_order=["x"]
    )
    assert SelfHostedTaskService._escalation_policy(cast(Any, contract)) is None


def test_escalation_policy_from_a_built_contract(service, roots) -> None:
    contract = service.build_contract(_request(worker="gemini", fallback_worker="codex"))
    assert SelfHostedTaskService._escalation_policy(contract) == WorkerEscalationPolicy(
        "gemini", "codex", ("gemini", "codex")
    )
    assert SelfHostedTaskService._escalation_policy(service.build_contract(_request())) is None


# ---------------------------------------------------------------------------
# late binding: every facade name is read at call time (patched after a first call)


class _CallRecorder:
    def __init__(self, log: list[str], name: str, real: Any) -> None:
        self.log, self.name, self.real = log, name, real

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.log.append(self.name)
        return self.real(*args, **kwargs)

    def __getattr__(self, attr: str) -> Any:
        value = getattr(self.real, attr)
        if callable(value):
            return _CallRecorder(self.log, f"{self.name}.{attr}", value)
        return value


BUILD_NAMES = (
    "validate_workforce_dispatch_binding",
    "uuid4",
    "resolve_canonical_target_roots",
    "subprocess",
    "CollaborationExecutionRealm",
    "ArchitectTaskContract",
    "DevelopmentGoal",
    "AcceptanceProfile",
    "HumanApprovalPolicy",
)


def _late_request(root: Path) -> dict[str, Any]:
    request = _request(controller_repo_root=str(root))
    del request["task_id"], request["controller_revision"]
    return request


@pytest.mark.parametrize("name", BUILD_NAMES)
def test_late_callables_in_build_contract(service, roots, repo, monkeypatch, name) -> None:
    request = _late_request(repo.root)
    if name == "CollaborationExecutionRealm":
        realm = _realm(str(repo.root.resolve()), repo.b)
        request.update(collaboration_realm=realm.model_dump(mode="json"))
    first = service.build_contract(request)  # a first call before the patch
    log: list[str] = []
    monkeypatch.setattr(
        service_module, name, _CallRecorder(log, name, getattr(service_module, name))
    )
    second = service.build_contract(request)
    assert log and all(entry.startswith(name) for entry in log)
    assert second.controller_revision == first.controller_revision == repo.b


def test_late_constants_in_build_contract(service, roots, monkeypatch) -> None:
    service.build_contract(_request())
    monkeypatch.setattr(service_module, "SUPPORTED_WORKER_PROVIDERS", ("agy", "codex", "gemini"))
    contract = service.build_contract(_request(worker="auto"))
    assert contract.provider_order == ["agy", "codex", "gemini"]
    with pytest.raises(ValueError, match="^worker must be one of: auto, agy, codex, gemini$"):
        service.build_contract(_request(worker="mimo"))
    monkeypatch.setattr(service_module, "FAIL_TO_PASS_EVIDENCE_TOKEN", "late-token")
    assert (
        service.build_contract(
            _request(fail_to_pass_required=True)
        ).acceptance_profile.required_evidence[-1]
        == "late-token"
    )


def test_late_architecture_decision_class(service, roots, monkeypatch) -> None:
    service.build_contract(_request())

    class LateDecision(ArchitectureDecision):
        pass

    item = LateDecision(
        decision_id="z", selected_option="o", rationale="r", rejected_alternatives=[]
    )
    monkeypatch.setattr(service_module, "ArchitectureDecision", LateDecision)
    contract = service.build_contract(
        _request(
            architecture_decisions=[
                item,
                {
                    "decision_id": "d",
                    "selected_option": "s",
                    "rationale": "q",
                    "rejected_alternatives": [],
                },
            ]
        )
    )
    assert contract.architecture_decisions[0] is item
    assert type(contract.architecture_decisions[1]) is LateDecision


def test_late_contract_kind(service, roots, monkeypatch) -> None:
    request = _request(worker_candidate_ingress=True, contract_kind="CUSTOM_INLINE")
    service.build_contract(request)
    monkeypatch.setattr(
        service_module,
        "ContractKind",
        SimpleNamespace(OWNER_INLINE=SimpleNamespace(value="CUSTOM_INLINE")),
    )
    with pytest.raises(RuntimeError, match="^AUTHORITY_CHANGE_CONFIRMATION_CONTRACT_MISMATCH$"):
        service.build_contract(request)


def test_late_mutation_mode(service, roots, monkeypatch) -> None:
    service.build_contract(_request())
    seen: list[str] = []

    real_mode = service_module.MutationMode

    class Mode:
        @property
        def WORKING_TREE_ONLY(self) -> Any:  # noqa: N802 - mirrors the enum member
            seen.append("mode")
            return real_mode.WORKING_TREE_ONLY

    monkeypatch.setattr(service_module, "MutationMode", Mode())
    contract = service.build_contract(_request())
    assert seen == ["mode"] and contract.mutation_mode is real_mode.WORKING_TREE_ONLY


def test_late_utc_now_and_terminal_statuses_in_set_child_pgid(
    service, state_dir, monkeypatch
) -> None:
    _seed(service)
    service._set_child_pgid("t", "attempt-1", 1)
    monkeypatch.setattr(service_module, "_utc_now", lambda: "LATE-NOW")
    service._set_child_pgid("t", "attempt-1", 2)
    assert _read(state_dir)["updated_at"] == "LATE-NOW"


def test_late_names_in_refresh(monkeypatch, repo) -> None:
    existing = _existing(request={"action": {}}, controller=repo.a, target=repo.a)
    refresh(existing, {}, _contract(repo.root, repo.b, repo.b))
    log: list[Any] = []
    for name, answer in (
        ("_terminal_retry_pre_provider_state_allowed", False),
        ("_terminal_retry_verifier_static_failure_allowed", True),
    ):
        monkeypatch.setattr(service_module, name, _Proof(log, name, answer))
    monkeypatch.setattr(
        service_module,
        "_terminal_retry_semantic_payload",
        lambda r: (log.append(("payload",)), 1)[1],
    )
    sub_log: list[Any] = []
    monkeypatch.setattr(service_module, "subprocess", RecordingSubprocess(sub_log))
    assert refresh(existing, {}, _contract(repo.root, repo.b, repo.b)) is True
    assert [e[0] for e in log] == [
        "_terminal_retry_pre_provider_state_allowed",
        "_terminal_retry_verifier_static_failure_allowed",
        "payload",
        "payload",
    ]
    assert len(sub_log) == 2


def test_late_isinstance_checks_use_the_facade_classes(service, roots, monkeypatch) -> None:
    # the isinstance checks read the facade class at call time: once it is replaced, an
    # instance of the original class is no longer passed through
    real_decision = ArchitectureDecision(
        decision_id="z", selected_option="o", rationale="r", rejected_alternatives=[]
    )
    assert (
        service.build_contract(
            _request(architecture_decisions=[real_decision])
        ).architecture_decisions[0]
        is real_decision
    )
    real_receipt = WorkerExecutionReceipt(**{**RECEIPT, "argv": ()})
    assert SelfHostedTaskService._receipt_from_state(real_receipt) is real_receipt

    class LateDecision(ArchitectureDecision):
        pass

    class LateReceipt(WorkerExecutionReceipt):
        pass

    monkeypatch.setattr(service_module, "ArchitectureDecision", LateDecision)
    monkeypatch.setattr(service_module, "WorkerExecutionReceipt", LateReceipt)
    with pytest.raises(TypeError):
        service.build_contract(_request(architecture_decisions=[real_decision]))
    assert SelfHostedTaskService._receipt_from_state(real_receipt) is None


def test_late_types_in_projections(service, monkeypatch) -> None:
    log: list[str] = []
    service._lease_from_state({"lease": LEASE})
    SelfHostedTaskService._receipt_from_state(RECEIPT)
    contract = SimpleNamespace(preferred_provider="a", fallback_provider="b", provider_order=None)
    SelfHostedTaskService._escalation_policy(cast(Any, contract))
    for name in ("TargetWorktreeLease", "WorkerExecutionReceipt", "WorkerEscalationPolicy"):
        monkeypatch.setattr(
            service_module, name, _CallRecorder(log, name, getattr(service_module, name))
        )
    service._lease_from_state({"lease": LEASE})
    SelfHostedTaskService._receipt_from_state(RECEIPT)
    SelfHostedTaskService._escalation_policy(cast(Any, contract))
    assert log == ["TargetWorktreeLease", "WorkerExecutionReceipt", "WorkerEscalationPolicy"]

    class LateReceipt(WorkerExecutionReceipt):
        pass

    instance = LateReceipt(**{**RECEIPT, "argv": ()})
    monkeypatch.setattr(service_module, "WorkerExecutionReceipt", LateReceipt)
    assert SelfHostedTaskService._receipt_from_state(instance) is instance


def test_late_contract_class_in_contract_from_state(service, roots, monkeypatch) -> None:
    stored = service.build_contract(_request()).model_dump(mode="json", exclude={"contract_hash"})
    service._contract_from_state({"contract": stored})
    log: list[str] = []
    monkeypatch.setattr(
        service_module,
        "ArchitectTaskContract",
        _CallRecorder(log, "ATC", service_module.ArchitectTaskContract),
    )
    service._contract_from_state({"contract": stored})
    assert log == ["ATC.model_validate"]


# ---------------------------------------------------------------------------
# self dispatch: instance, class and subclass patches; the runtime bridge


def test_contract_from_state_reaches_class_and_subclass_build_contract(
    state_dir, monkeypatch
) -> None:
    hits: list[Any] = []
    monkeypatch.setattr(
        SelfHostedTaskService,
        "build_contract",
        lambda self, request: (hits.append(request), "CLS")[1],
    )
    svc = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    assert svc._contract_from_state({"request": {"a": 1}}) == "CLS"
    monkeypatch.undo()

    class Sub(SelfHostedTaskService):
        def build_contract(self, request: Any) -> Any:
            return ("SUB", dict(request))

    sub = Sub(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    assert sub._contract_from_state({"request": {"b": 2}}) == ("SUB", {"b": 2})
    assert hits == [{"a": 1}]


def test_subclass_override_of_a_moved_member_wins(state_dir) -> None:
    class Sub(SelfHostedTaskService):
        @staticmethod
        def _prompt(contract: Any) -> str:
            return "SUB-PROMPT"

    sub = Sub(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    assert runtime_coordination_bridge._Contract(sub).prompt(object()) == "SUB-PROMPT"


def test_runtime_bridge_reaches_the_moved_members(service, state_dir, roots, monkeypatch) -> None:
    contract_port = runtime_coordination_bridge._Contract(service)
    built = contract_port.build_contract(_request())
    assert built.contract_hash == GOLDEN_MINIMAL_HASH
    assert contract_port.prompt(built) == SelfHostedTaskService._prompt(built)
    assert contract_port.receipt_from_state(RECEIPT) == SelfHostedTaskService._receipt_from_state(
        RECEIPT
    )
    calls: list[str] = []
    monkeypatch.setattr(service, "_prompt", lambda contract: (calls.append("prompt"), "P")[1])
    monkeypatch.setattr(service, "build_contract", lambda request: (calls.append("build"), "B")[1])
    monkeypatch.setattr(
        service, "_receipt_from_state", lambda value: (calls.append("receipt"), "R")[1]
    )
    monkeypatch.setattr(service, "_lease_from_state", lambda state: (calls.append("lease"), "L")[1])
    assert contract_port.prompt(built) == "P"
    assert contract_port.build_contract({}) == "B"
    assert contract_port.receipt_from_state({}) == "R"
    assert calls == ["prompt", "build", "receipt"]
    pgids: list[Any] = []
    monkeypatch.setattr(service, "_set_child_pgid", lambda *args: pgids.append(args))
    source = inspect.getsource(runtime_coordination_bridge)
    assert "self.service._set_child_pgid(task_id, attempt_id, pgid)" in source
    assert "return self.service._lease_from_state(state)" in source


def test_no_files_besides_the_state_and_the_lock(service, state_dir, roots) -> None:
    _seed(service)
    service.build_contract(_request())
    service._set_child_pgid("t", "attempt-1", 3)
    assert sorted(p.name for p in state_dir.rglob("*")) == [".state.lock", "t.json"]


# ---------------------------------------------------------------------------
# S8b review NITs (#2583): the two remaining SUPPORTED_WORKER_PROVIDERS sites


def test_late_supported_providers_in_the_worker_order_check(service, roots, monkeypatch) -> None:
    # a first call that reaches the auto worker_order membership check
    assert service.build_contract(
        _request(worker="auto", worker_order=["codex"])
    ).provider_order == ["codex"]
    monkeypatch.setattr(service_module, "SUPPORTED_WORKER_PROVIDERS", ("late-a", "codex"))
    contract = service.build_contract(_request(worker="auto", worker_order=["late-a", "codex"]))
    assert contract.provider_order == ["late-a", "codex"]
    with pytest.raises(
        ValueError, match="^worker_order contains an unknown or duplicate provider$"
    ):
        service.build_contract(_request(worker="auto", worker_order=["gemini"]))


def test_late_supported_providers_in_the_fallback_check(service, roots, monkeypatch) -> None:
    # a first call that reaches the fallback_worker membership check
    assert service.build_contract(_request(fallback_worker="gemini")).provider_order == [
        "codex",
        "gemini",
    ]
    monkeypatch.setattr(service_module, "SUPPORTED_WORKER_PROVIDERS", ("codex", "late-b"))
    assert service.build_contract(_request(fallback_worker="late-b")).provider_order == [
        "codex",
        "late-b",
    ]
    with pytest.raises(ValueError, match="^fallback_worker must be one of: codex, late-b$"):
        service.build_contract(_request(fallback_worker="gemini"))
