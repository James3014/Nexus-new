"""Characterization of the reconcile-recovery cluster of ``SelfHostedTaskService`` (S12).

Big-file split step S12 (Issue #2725) moves these class members out of
``nexus/orchestrator/self_hosted_task_service.py`` into a mixin:

* ``_reconcile_direct_action`` (an interrupted Direct canonical action -- DIRECT_STARTED /
  APPLIED / VERIFIED / COMMITTED after a crash -- is classified by four read-only git
  probes and recorded as UNKNOWN_REQUIRES_RECONCILE, never replayed);
* ``_reconcile_direct_failure`` (a DIRECT_RECONCILE_REQUIRED task is closed as
  FINAL_BLOCK / NO_MUTATION_OBSERVED only when five git probes prove that nothing in the
  allowed paths moved and no Target or Candidate exists; otherwise it stays
  RETAINED_FOR_REVIEW);
* the static ``_projected_pre_apply_recovery_evidence`` and
  ``_reconcile_projected_pre_apply_failure`` (an exact, fully bound lost PRE_APPLY
  projection -- FINAL_BLOCK / NOT_CREATED with the original packet -- is restored to the
  native INTEGRATION_FAILED_PRE_APPLY status under the state lock, with a history record);
* ``_resume_external_adoption``, ``_read_adoption_artifact`` and
  ``_validate_persisted_external_adoption`` (a crash-interrupted ADOPTING record is replayed
  from the service-owned evidence artifacts -- canonical locator, no symlinks, content hash
  -- and an adoption replay is accepted only when every durable binding still holds).

These tests pin the behaviour before the move and must pass unchanged after it:

* the member table (descriptor kind, signature, docstring);
* every reconcile / recovery outcome (terminal status, checkpoint values, the evidence
  record, the history entries), every fail-closed branch in its order with its exact
  message, and the exact git probe arguments and order;
* the failure-only production paths: restart of a service on a state dir holding an
  interrupted Direct action or an interrupted adoption (``auto_reconcile=True``), a lost
  PRE_APPLY projection, and evidence artifacts that were removed, replaced, truncated or
  redirected through a symlink;
* that every facade-module name the moved code reads at run time is resolved through the
  facade at call time (patched after a first call that reached the same site):
  ``CANONICAL_SOURCE_ROOT``, ``subprocess``, ``_utc_now``, ``_jsonable``,
  ``LifecycleActionType`` and ``_EXTERNAL_ADOPTION_CLAIM_CEILING``.  The stdlib modules
  ``base64``, ``hashlib``, ``json``, ``os``, ``re`` and ``stat`` are not patch seams (the
  stale-patch guard of ``test_bigfile_split_surface`` forbids patching them on the
  facade); the artifact-reader tests wrap the ``os`` module's functions instead;
* that instance, class and subclass patches of the members reached through ``self`` are
  honoured, also through ``reconcile_task``.

No test runs a worker, reaches a real Core, sends a signal or writes outside
``tmp_path``; the only real child processes are ``git`` on temporary repositories (with a
git identity).  No test asserts on inode numbers, file modes or other platform details.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import inspect
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

import nexus.orchestrator.self_hosted_task_service as service_module
from nexus.contracts.lifecycle_action import LifecycleActionType
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

MEMBERS = (
    "_reconcile_direct_action",
    "_reconcile_direct_failure",
    "_projected_pre_apply_recovery_evidence",
    "_reconcile_projected_pre_apply_failure",
    "_resume_external_adoption",
    "_read_adoption_artifact",
    "_validate_persisted_external_adoption",
)
PROJECTION_DOC = (
    "Return bounded evidence for an exact lost pre-apply projection.\n\n"
    "Older reconciliation projected a non-applied integration failure to\n"
    "FINAL_BLOCK/NOT_CREATED while retaining the original PRE_APPLY packet.\n"
    "Only that exact, fully bound projection may be restored to the native\n"
    "pre-apply status for a fresh closure rebind."
)
RESUME_DOC = (
    "Replay a crash-interrupted external adoption from durable evidence.\n\n"
    "The original request deliberately omits receipt payloads from the\n"
    "task state.  Only the service-owned artifact locators are accepted on\n"
    "restart, and both paths and content hashes are checked before the\n"
    "normal adoption verifier is called.  This keeps restart idempotent\n"
    "without granting a partially written ADOPTING state any authority."
)
MEMBER_TABLE = {
    "_reconcile_direct_action": (
        "function",
        "(self, task_id: 'str') -> 'Optional[dict[str, Any]]'",
        "Classify an interrupted canonical action without replaying it.",
    ),
    "_reconcile_direct_failure": (
        "function",
        "(self, task_id: 'str') -> 'Optional[dict[str, Any]]'",
        "Close a no-mutation Direct failure without replaying its action.",
    ),
    "_projected_pre_apply_recovery_evidence": (
        "staticmethod",
        "(state: 'Mapping[str, Any]') -> 'Optional[dict[str, Any]]'",
        PROJECTION_DOC,
    ),
    "_reconcile_projected_pre_apply_failure": (
        "function",
        "(self, task_id: 'str', evidence: 'Mapping[str, Any]') -> 'dict[str, Any]'",
        None,
    ),
    "_resume_external_adoption": (
        "function",
        "(self, task_id: 'str', state: 'Mapping[str, Any]') -> 'dict[str, Any]'",
        RESUME_DOC,
    ),
    "_read_adoption_artifact": (
        "function",
        "(self, task_id: 'str', raw_locator: 'str', digest: 'str', kind: 'str') -> 'bytes'",
        "Read a service-owned adoption artifact without following symlinks.",
    ),
    "_validate_persisted_external_adoption": (
        "function",
        "(self, state: 'Mapping[str, Any]', request: 'ExternalCandidateAdoptionRequest', "
        "semantic_hash: 'str', acceptance: 'Mapping[str, Any]') -> 'None'",
        "Validate every durable binding before returning an adoption replay.",
    ),
}
NOW = "2026-10-19T00:00:00+00:00"
HEAD = "a" * 40
CURRENT = "b" * 40


# ---------------------------------------------------------------------------
# fixtures and helpers


@pytest.fixture
def service(tmp_path: Path) -> SelfHostedTaskService:
    return SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True)


@pytest.fixture
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def now() -> str:
        calls.append(NOW)
        return NOW

    monkeypatch.setattr(service_module, "_utc_now", now)
    return calls


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> str:
    return _sha(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def _repo(path: Path) -> str:
    """A real git repository with one tracked file ``src/a.py``; returns HEAD."""
    (path / "src").mkdir(parents=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.name", "Nexus Test")
    _git(path, "config", "user.email", "nexus-test@example.invalid")
    _git(path, "config", "commit.gpgsign", "false")
    (path / "src" / "a.py").write_text("a = 1\n", encoding="utf-8")
    (path / "README").write_text("r\n", encoding="utf-8")
    _git(path, "add", "src/a.py", "README")
    _git(path, "commit", "-q", "-m", "init")
    return _git(path, "rev-parse", "HEAD")


class _Proc:
    """A recording ``subprocess`` stand-in: answers are (returncode, stdout) or exceptions."""

    def __init__(self, answers: list[Any], log: list[Any] | None = None) -> None:
        self.answers = list(answers)
        self.log: list[Any] = [] if log is None else log

    def run(self, argv: Any, **kwargs: Any) -> Any:
        self.log.append((tuple(argv), kwargs))
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        code, stdout = answer
        return SimpleNamespace(returncode=code, stdout=stdout)


def _kwargs(cwd: Path) -> dict[str, Any]:
    return {"cwd": cwd, "capture_output": True, "text": True, "check": False}


def _reading(service: Any, monkeypatch: pytest.MonkeyPatch, state: Any) -> list[str]:
    reads: list[str] = []
    monkeypatch.setattr(
        service, "_read_state", lambda task_id: (reads.append(task_id), copy.deepcopy(state))[1]
    )
    return reads


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


def test_static_projection_is_the_same_through_class_and_instance(service) -> None:
    name = "_projected_pre_apply_recovery_evidence"
    assert getattr(service, name) is getattr(SelfHostedTaskService, name)
    assert not inspect.ismethod(getattr(service, name))


# ---------------------------------------------------------------------------
# _reconcile_direct_action


@pytest.fixture
def action(service, monkeypatch, tmp_path) -> SimpleNamespace:
    controller = (tmp_path / "controller").resolve()
    controller.mkdir()
    recorded: list[Any] = []
    monkeypatch.setattr(
        service,
        "_record_direct_failure",
        lambda task_id, blocker, error="": (recorded.append((task_id, blocker, error)), "RECORDED")[
            1
        ],
    )
    log: list[Any] = []
    return SimpleNamespace(
        service=service,
        controller=controller,
        recorded=recorded,
        log=log,
        use=lambda answers: monkeypatch.setattr(service_module, "subprocess", _Proc(answers, log)),
    )


def _observed(recorded: list[Any]) -> dict[str, Any]:
    ((task_id, blocker, error),) = recorded
    assert (task_id, blocker) == ("t", "UNKNOWN_REQUIRES_RECONCILE")
    assert error == json.dumps(json.loads(error), sort_keys=True, separators=(",", ":"))
    return json.loads(error)


def test_direct_action_unknown_task_returns_none_without_probes(action, monkeypatch) -> None:
    reads = _reading(action.service, monkeypatch, None)
    action.use([])
    assert action.service._reconcile_direct_action("t") is None
    assert reads == ["t"] and action.log == [] and action.recorded == []


def test_direct_action_intent_recorded_is_returned_unchanged(action, monkeypatch) -> None:
    state = {"status": "DIRECT_INTENT_RECORDED", "request": {"controller_repo_root": "/x"}}
    _reading(action.service, monkeypatch, state)
    action.use([])
    assert action.service._reconcile_direct_action("t") == state
    assert action.log == [] and action.recorded == []


def test_direct_action_probe_order_arguments_and_record(action, monkeypatch) -> None:
    state = {
        "status": "DIRECT_STARTED",
        "request": {"controller_repo_root": str(action.controller), "controller_revision": HEAD},
        "controller_worktree": "/ignored",
        "controller_revision": "ignored",
    }
    _reading(action.service, monkeypatch, state)
    action.use([(0, f" {CURRENT}\n"), (0, " M x\n"), (0, "src/a.py\nsrc/b.py\n"), (0, "w.py\n")])
    assert action.service._reconcile_direct_action("t") == "RECORDED"
    assert action.log == [
        (("git", "rev-parse", "HEAD"), _kwargs(action.controller)),
        (("git", "status", "--porcelain=v1"), _kwargs(action.controller)),
        (("git", "diff", "--name-only", f"{HEAD}..HEAD"), _kwargs(action.controller)),
        (("git", "diff", "--name-only"), _kwargs(action.controller)),
    ]
    assert _observed(action.recorded) == {
        "controller_repo_root": str(action.controller),
        "expected_head": HEAD,
        "current_head": CURRENT,
        "dirty": True,
        "commits_since_base": ["src/a.py", "src/b.py"],
        "working_tree_changes": ["w.py"],
    }


@pytest.mark.parametrize("revision", ["", "short", "a" * 39, "a" * 41])
def test_direct_action_without_a_full_revision_skips_the_base_diff(
    action, monkeypatch, revision
) -> None:
    state = {
        "status": "DIRECT_APPLIED",
        "request": {
            "controller_repo_root": str(action.controller),
            "controller_revision": revision,
        },
    }
    _reading(action.service, monkeypatch, state)
    action.use([(0, "h\n"), (0, "\n  \n"), (0, "")])
    action.service._reconcile_direct_action("t")
    assert [argv for argv, _ in action.log] == [
        ("git", "rev-parse", "HEAD"),
        ("git", "status", "--porcelain=v1"),
        ("git", "diff", "--name-only"),
    ]
    observed = _observed(action.recorded)
    assert observed["expected_head"] == revision and observed["dirty"] is False
    assert observed["commits_since_base"] == [] and observed["working_tree_changes"] == []


def test_direct_action_falls_back_to_the_state_controller_and_revision(action, monkeypatch) -> None:
    state = {
        "status": "DIRECT_VERIFIED",
        "controller_worktree": str(action.controller / "sub" / ".."),
        "controller_revision": HEAD,
    }
    _reading(action.service, monkeypatch, state)
    action.use([(0, ""), (0, ""), (0, ""), (0, "")])
    action.service._reconcile_direct_action("t")
    assert {kwargs["cwd"] for _, kwargs in action.log} == {action.controller}
    observed = _observed(action.recorded)
    assert observed["controller_repo_root"] == str(action.controller)
    assert observed["expected_head"] == HEAD and observed["current_head"] == ""


def test_direct_action_falls_back_to_the_canonical_source_root(
    action, monkeypatch, tmp_path
) -> None:
    canonical = (tmp_path / "canonical").resolve()
    monkeypatch.setattr(service_module, "CANONICAL_SOURCE_ROOT", canonical)
    _reading(action.service, monkeypatch, {"status": "DIRECT_COMMITTED", "request": None})
    action.use([(0, ""), (0, ""), (0, "")])
    action.service._reconcile_direct_action("t")
    assert {kwargs["cwd"] for _, kwargs in action.log} == {canonical}
    assert _observed(action.recorded)["controller_repo_root"] == str(canonical)


@pytest.mark.parametrize("at", [0, 1, 2, 3])
def test_direct_action_probe_os_error_is_recorded_not_raised(action, monkeypatch, at) -> None:
    state = {
        "status": "DIRECT_STARTED",
        "request": {"controller_repo_root": str(action.controller), "controller_revision": HEAD},
    }
    _reading(action.service, monkeypatch, state)
    answers: list[Any] = [(0, "H\n"), (0, "x\n"), (0, "c.py\n"), (0, "w.py\n")]
    answers[at] = OSError(f"git gone {at}")
    action.use(answers[: at + 1])
    action.service._reconcile_direct_action("t")
    observed = _observed(action.recorded)
    assert observed["probe_error"] == f"git gone {at}"
    assert observed["current_head"] == ("H" if at > 0 else None)
    assert observed["dirty"] == (True if at > 1 else None)
    assert observed["commits_since_base"] == (["c.py"] if at > 2 else [])
    assert observed["working_tree_changes"] == []
    assert len(action.log) == at + 1


def test_direct_action_other_errors_propagate(action, monkeypatch) -> None:
    _reading(
        action.service,
        monkeypatch,
        {"status": "DIRECT_STARTED", "request": {"controller_repo_root": str(action.controller)}},
    )
    action.use([ValueError("boom")])
    with pytest.raises(ValueError, match="boom"):
        action.service._reconcile_direct_action("t")
    assert action.recorded == []


def test_direct_action_with_real_git_and_the_real_record(
    service, monkeypatch, tmp_path, fixed_now
) -> None:
    controller = (tmp_path / "repo").resolve()
    head = _repo(controller)
    (controller / "src" / "a.py").write_text("a = 2\n", encoding="utf-8")
    emitted: list[Any] = []
    monkeypatch.setattr(
        service, "_emit_bound_attempt_transition", lambda result, task_id: emitted.append(task_id)
    )
    service._write_state(
        "t",
        {
            "task_id": "t",
            "attempt_id": "a1",
            "status": "DIRECT_STARTED",
            "request": {"controller_repo_root": str(controller), "controller_revision": head},
            "status_history": [],
        },
    )
    result = service._reconcile_direct_action("t")
    assert result is not None and result["status"] == "DIRECT_RECONCILE_REQUIRED"
    assert result["reconciliation_required"] is True and emitted == ["t"]
    reconciliation = result["canonical_action"]["reconciliation"]
    assert reconciliation["status"] == "REQUIRED"
    assert reconciliation["blocker"] == "UNKNOWN_REQUIRES_RECONCILE"
    assert json.loads(reconciliation["error"]) == {
        "controller_repo_root": str(controller),
        "expected_head": head,
        "current_head": head,
        "dirty": True,
        "commits_since_base": [],
        "working_tree_changes": ["src/a.py"],
    }
    assert result["error"] == reconciliation["error"]
    assert result["status_history"][-1] == {"status": "DIRECT_RECONCILE_REQUIRED", "at": NOW}


# ---------------------------------------------------------------------------
# _reconcile_direct_failure


@pytest.fixture
def failure(service, monkeypatch, tmp_path, fixed_now) -> SimpleNamespace:
    controller = (tmp_path / "controller").resolve()
    controller.mkdir()
    checkpoints: list[Any] = []
    monkeypatch.setattr(
        service,
        "_checkpoint",
        lambda task_id, status, values=None, *, attempt_id=None: (
            checkpoints.append((task_id, status, copy.deepcopy(values), attempt_id)),
            {"checkpointed": status},
        )[1],
    )
    log: list[Any] = []
    holder: dict[str, Any] = {}
    monkeypatch.setattr(service, "_read_state", lambda task_id: copy.deepcopy(holder.get("state")))

    def state(**extra: Any) -> dict[str, Any]:
        value: dict[str, Any] = {
            "status": "DIRECT_RECONCILE_REQUIRED",
            "attempt_id": "a1",
            "request": {
                "controller_repo_root": str(controller),
                "controller_revision": HEAD,
                "allowed_files": ["src/a.py", "docs/"],
            },
            "canonical_action": {
                "action_id": "act-1",
                "reconciliation": {"status": "REQUIRED", "blocker": "UNKNOWN_REQUIRES_RECONCILE"},
            },
        }
        value.update(extra)
        holder["state"] = value
        return value

    return SimpleNamespace(
        service=service,
        controller=controller,
        checkpoints=checkpoints,
        log=log,
        state=state,
        use=lambda answers: monkeypatch.setattr(service_module, "subprocess", _Proc(answers, log)),
        now=fixed_now,
    )


CLEAN = [(0, f"{CURRENT}\n"), (0, ""), (0, "src/other.py\0"), (0, "README\0"), (0, ""), (0, "")]


def _evidence(controller: Path, **extra: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "controller_repo_root": str(controller),
        "expected_head": HEAD,
        "current_head": CURRENT,
        "expected_head_is_ancestor": True,
        "commits_since_base": ["src/other.py"],
        "working_tree_changes": ["README"],
        "staged_changes": [],
        "untracked_changes": [],
        "allowed_paths": ["docs", "src/a.py"],
        "invalid_allowed_paths": [],
        "target_created": False,
        "candidate_created": False,
        "allowed_paths_touched": [],
    }
    value.update(extra)
    return value


def test_direct_failure_unknown_task_returns_none(failure) -> None:
    failure.use([])
    assert failure.service._reconcile_direct_failure("t") is None
    assert failure.log == [] and failure.checkpoints == [] and failure.now == []


@pytest.mark.parametrize("status", ["DIRECT_STARTED", "FINAL_BLOCK", None])
def test_direct_failure_other_status_is_returned_unchanged(failure, status) -> None:
    state = failure.state(status=status)
    failure.use([])
    assert failure.service._reconcile_direct_failure("t") == state
    assert failure.log == [] and failure.checkpoints == [] and failure.now == []


def test_direct_failure_no_mutation_closes_as_final_block(failure) -> None:
    failure.state()
    failure.use(list(CLEAN))
    assert failure.service._reconcile_direct_failure("t") == {"checkpointed": "FINAL_BLOCK"}
    c = failure.controller
    assert failure.log == [
        (("git", "rev-parse", "HEAD"), _kwargs(c)),
        (("git", "merge-base", "--is-ancestor", HEAD, CURRENT), _kwargs(c)),
        (("git", "diff", "--name-only", "--no-renames", "-z", f"{HEAD}..HEAD"), _kwargs(c)),
        (("git", "diff", "--name-only", "--no-renames", "-z"), _kwargs(c)),
        (("git", "diff", "--cached", "--name-only", "--no-renames", "-z"), _kwargs(c)),
        (
            (
                "git",
                "ls-files",
                "--others",
                "--exclude-standard",
                "--full-name",
                "-z",
                "--",
                ":(top)",
            ),
            _kwargs(c),
        ),
    ]
    evidence = _evidence(c)
    assert failure.checkpoints == [
        (
            "t",
            "FINAL_BLOCK",
            {
                "canonical_action": {
                    "action_id": "act-1",
                    "reconciliation": {
                        "status": "RECONCILED",
                        "blocker": "UNKNOWN_REQUIRES_RECONCILE",
                        "decision": "NO_MUTATION_OBSERVED",
                        "evidence": evidence,
                        "reconciled_at": NOW,
                    },
                },
                "reconciliation_status": "RECONCILED",
                "reconciliation_decision": "NO_MUTATION_OBSERVED",
                "reconciliation_evidence": evidence,
                "reconciliation_required": False,
                "cleanup_decision": "ALREADY_REMOVED",
                "cleanup_eligible": True,
                "cleanup_performed": False,
                "promotion_status": "NOT_CREATED",
                "terminal_status": "FINAL_BLOCK",
                "state_retention_status": "TERMINAL",
                "archive_eligible": True,
            },
            "a1",
        )
    ]
    assert failure.now == [NOW]


def _retained(failure: SimpleNamespace, evidence: dict[str, Any], *, action: Any = None) -> None:
    (checkpoint,) = failure.checkpoints
    expected_action = {
        "action_id": "act-1",
        "reconciliation": {
            "status": "REQUIRED",
            "blocker": "UNKNOWN_REQUIRES_RECONCILE",
            "decision": "RETAINED_FOR_REVIEW",
            "evidence": evidence,
            "reconciled_at": NOW,
        },
    }
    assert checkpoint == (
        "t",
        "DIRECT_RECONCILE_REQUIRED",
        {
            "canonical_action": expected_action if action is None else action,
            "reconciliation_status": "REQUIRED",
            "reconciliation_decision": "RETAINED_FOR_REVIEW",
            "reconciliation_evidence": evidence,
            "reconciliation_required": True,
        },
        "a1",
    )


@pytest.mark.parametrize(
    "touched, answers",
    [
        (
            ["src/a.py"],
            [(0, f"{CURRENT}\n"), (0, ""), (0, "src/a.py\0"), (0, ""), (0, ""), (0, "")],
        ),
        (
            ["src/a.py"],
            [(0, f"{CURRENT}\n"), (0, ""), (0, ""), (0, "src/a.py\0"), (0, ""), (0, "")],
        ),
        (
            ["src/a.py"],
            [(0, f"{CURRENT}\n"), (0, ""), (0, ""), (0, ""), (0, "src/a.py\0"), (0, "")],
        ),
        (
            ["docs", "src/a.py"],
            [
                (0, f"{CURRENT}\n"),
                (0, ""),
                (0, "docs\0src/a.py\0"),
                (0, "src/a.py\0"),
                (0, "x\0"),
                (0, ""),
            ],
        ),
    ],
)
def test_direct_failure_touched_allowed_paths_are_retained(failure, touched, answers) -> None:
    failure.state()
    failure.use(answers)
    assert failure.service._reconcile_direct_failure("t") == {
        "checkpointed": "DIRECT_RECONCILE_REQUIRED"
    }
    ((_, _, values, _),) = failure.checkpoints
    assert values["reconciliation_evidence"]["allowed_paths_touched"] == touched


def test_direct_failure_directory_boundaries_only_match_exactly(failure) -> None:
    # Issue #2727 item 1 (this test id predates the fix): a file strictly below an allowed
    # directory is an allowed-path touch; a sibling that only shares a prefix is not.
    failure.state()
    failure.use(
        [
            (0, f"{CURRENT}\n"),
            (0, ""),
            (0, "docs/x.md\0src/a.py.bak\0docs2/y\0"),
            (0, ""),
            (0, ""),
            (0, ""),
        ]
    )
    failure.service._reconcile_direct_failure("t")
    ((_, status, values, _),) = failure.checkpoints
    assert status == "DIRECT_RECONCILE_REQUIRED"
    assert values["reconciliation_evidence"]["allowed_paths_touched"] == ["docs/x.md"]
    assert values["reconciliation_evidence"]["allowed_paths"] == ["docs", "src/a.py"]


def test_direct_failure_allowed_files_normalisation(failure) -> None:
    failure.state(
        request={
            "controller_repo_root": str(failure.controller),
            "controller_revision": f"  {HEAD}\n",
            "allowed_files": ["b//", "", "  ", "a", 7, "a/"],
        }
    )
    failure.use([(0, f"{CURRENT}\n"), (0, ""), (0, "7\0"), (0, ""), (0, ""), (0, "")])
    failure.service._reconcile_direct_failure("t")
    ((_, status, values, _),) = failure.checkpoints
    evidence = values["reconciliation_evidence"]
    assert evidence["expected_head"] == HEAD
    assert evidence["allowed_paths"] == ["7", "a", "b"]
    assert evidence["allowed_paths_touched"] == ["7"] and status == "DIRECT_RECONCILE_REQUIRED"


def test_direct_failure_not_an_ancestor_is_retained_without_the_base_diff(failure) -> None:
    failure.state()
    failure.use([(0, f"{CURRENT}\n"), (1, ""), (0, "w\0"), (0, "s\0"), (0, "")])
    failure.service._reconcile_direct_failure("t")
    assert [argv[1:3] for argv, _ in failure.log] == [
        ("rev-parse", "HEAD"),
        ("merge-base", "--is-ancestor"),
        ("diff", "--name-only"),
        ("diff", "--cached"),
        ("ls-files", "--others"),
    ]
    _retained(
        failure,
        _evidence(
            failure.controller,
            expected_head_is_ancestor=False,
            commits_since_base=[],
            working_tree_changes=["w"],
            staged_changes=["s"],
        ),
    )


@pytest.mark.parametrize("revision", ["", "abc", "a" * 39])
def test_direct_failure_without_a_full_expected_head_is_retained(failure, revision) -> None:
    failure.state(
        request={"controller_repo_root": str(failure.controller), "controller_revision": revision}
    )
    failure.use([(0, f"{CURRENT}\n"), (0, ""), (0, ""), (0, "")])
    failure.service._reconcile_direct_failure("t")
    assert [argv[1:3] for argv, _ in failure.log] == [
        ("rev-parse", "HEAD"),
        ("diff", "--name-only"),
        ("diff", "--cached"),
        ("ls-files", "--others"),
    ]
    _retained(
        failure,
        _evidence(
            failure.controller,
            expected_head=revision,
            expected_head_is_ancestor=False,
            commits_since_base=[],
            working_tree_changes=[],
            allowed_paths=[],
        ),
    )


def test_direct_failure_without_a_current_head_is_retained(failure) -> None:
    failure.state()
    failure.use([(128, "  \n"), (0, ""), (0, ""), (0, "")])
    failure.service._reconcile_direct_failure("t")
    assert len(failure.log) == 4
    _retained(
        failure,
        _evidence(
            failure.controller,
            current_head="",
            expected_head_is_ancestor=False,
            commits_since_base=[],
            working_tree_changes=[],
        ),
    )


@pytest.mark.parametrize("at", [0, 1, 2, 3, 4, 5])
def test_direct_failure_probe_os_error_is_retained(failure, at) -> None:
    failure.state()
    answers: list[Any] = list(CLEAN)
    answers[at] = OSError(f"probe {at}")
    failure.use(answers[: at + 1])
    failure.service._reconcile_direct_failure("t")
    ((_, status, values, _),) = failure.checkpoints
    evidence = values["reconciliation_evidence"]
    assert status == "DIRECT_RECONCILE_REQUIRED"
    assert evidence["probe_error"] == f"probe {at}"
    assert evidence["current_head"] == (CURRENT if at > 0 else None)
    assert evidence["expected_head_is_ancestor"] is (at > 1)
    assert evidence["commits_since_base"] == (["src/other.py"] if at > 2 else [])
    assert evidence["working_tree_changes"] == (["README"] if at > 3 else [])
    assert evidence["staged_changes"] == []
    assert evidence["untracked_changes"] == []


def test_direct_failure_other_probe_errors_propagate(failure) -> None:
    failure.state()
    failure.use([ValueError("not os")])
    with pytest.raises(ValueError, match="not os"):
        failure.service._reconcile_direct_failure("t")
    assert failure.checkpoints == [] and failure.now == []


@pytest.mark.parametrize(
    "extra, target, candidate",
    [
        ({"target_worktree": "/t"}, True, False),
        ({"lease": {"lease_id": "l"}}, True, False),
        ({"candidate_ref": "refs/c"}, False, True),
        ({"candidate_commit_sha": "c" * 40}, False, True),
        ({"promotion_packet": {"x": 1}}, False, True),
        (
            {"target_worktree": "", "lease": {}, "candidate_ref": "", "promotion_packet": {}},
            False,
            False,
        ),
    ],
)
def test_direct_failure_target_or_candidate_blocks_the_close(
    failure, extra, target, candidate
) -> None:
    failure.state(**extra)
    failure.use(list(CLEAN))
    failure.service._reconcile_direct_failure("t")
    ((_, status, values, _),) = failure.checkpoints
    evidence = values["reconciliation_evidence"]
    assert (evidence["target_created"], evidence["candidate_created"]) == (target, candidate)
    assert status == ("FINAL_BLOCK" if not (target or candidate) else "DIRECT_RECONCILE_REQUIRED")


def test_direct_failure_request_must_be_a_mapping(failure, monkeypatch, tmp_path) -> None:
    canonical = (tmp_path / "canonical").resolve()
    monkeypatch.setattr(service_module, "CANONICAL_SOURCE_ROOT", canonical)
    failure.state(request=["controller_repo_root", "/x"], controller_revision=HEAD)
    failure.use(list(CLEAN))
    failure.service._reconcile_direct_failure("t")
    assert {kwargs["cwd"] for _, kwargs in failure.log} == {canonical}
    ((_, status, values, _),) = failure.checkpoints
    assert status == "FINAL_BLOCK"
    assert values["reconciliation_evidence"]["allowed_paths"] == []
    assert values["reconciliation_evidence"]["expected_head"] == HEAD


def test_direct_failure_controller_falls_back_to_the_state_worktree(failure) -> None:
    failure.state(
        request={"controller_revision": HEAD},
        controller_worktree=str(failure.controller / "x" / ".."),
    )
    failure.use(list(CLEAN))
    failure.service._reconcile_direct_failure("t")
    assert {kwargs["cwd"] for _, kwargs in failure.log} == {failure.controller}


def test_direct_failure_without_an_action_builds_one(failure) -> None:
    failure.state(canonical_action=None, attempt_id=None)
    failure.use(list(CLEAN))
    failure.service._reconcile_direct_failure("t")
    ((_, _, values, attempt),) = failure.checkpoints
    assert attempt is None
    assert values["canonical_action"] == {
        "reconciliation": {
            "status": "RECONCILED",
            "decision": "NO_MUTATION_OBSERVED",
            "evidence": _evidence(failure.controller),
            "reconciled_at": NOW,
        }
    }


def test_direct_failure_with_real_git_and_the_real_checkpoint(
    service, monkeypatch, tmp_path, fixed_now
) -> None:
    controller = (tmp_path / "repo").resolve()
    head = _repo(controller)
    (controller / "other.txt").write_text("o\n", encoding="utf-8")
    _git(controller, "add", "other.txt")
    _git(controller, "commit", "-q", "-m", "unrelated")
    base_state = {
        "task_id": "t",
        "attempt_id": "a1",
        "status": "DIRECT_RECONCILE_REQUIRED",
        "request": {
            "controller_repo_root": str(controller),
            "controller_revision": head,
            "allowed_files": ["src/a.py"],
        },
        "canonical_action": {
            "reconciliation": {"status": "REQUIRED", "blocker": "UNKNOWN_REQUIRES_RECONCILE"}
        },
        "status_history": [],
    }
    service._write_state("t", copy.deepcopy(base_state))
    closed = service._reconcile_direct_failure("t")
    assert closed is not None and closed["status"] == "FINAL_BLOCK"
    assert closed["reconciliation_decision"] == "NO_MUTATION_OBSERVED"
    assert closed["reconciliation_evidence"]["commits_since_base"] == ["other.txt"]
    assert closed["archive_eligible"] is True and closed["promotion_status"] == "NOT_CREATED"
    assert closed["status_history"] == [{"status": "FINAL_BLOCK", "at": NOW}]
    assert service._reconcile_direct_failure("t") == service._read_state("t")

    # an allowed path changed in the working tree: retained for review
    (controller / "src" / "a.py").write_text("a = 3\n", encoding="utf-8")
    service._write_state("u", {**copy.deepcopy(base_state), "task_id": "u"})
    retained = service._reconcile_direct_failure("u")
    assert retained is not None and retained["status"] == "DIRECT_RECONCILE_REQUIRED"
    assert retained["reconciliation_decision"] == "RETAINED_FOR_REVIEW"
    assert retained["reconciliation_evidence"]["allowed_paths_touched"] == ["src/a.py"]
    assert retained["reconciliation_required"] is True
    assert "archive_eligible" not in retained


def test_direct_failure_does_not_see_untracked_files(service, tmp_path, fixed_now) -> None:
    # Issue #2727 item 2 (this test id predates the fix): an untracked file at an allowed
    # path is now observed, so the task is retained for review instead of closed.
    controller = (tmp_path / "repo").resolve()
    head = _repo(controller)
    (controller / "src" / "new.py").write_text("n\n", encoding="utf-8")
    service._write_state(
        "t",
        {
            "task_id": "t",
            "attempt_id": "a1",
            "status": "DIRECT_RECONCILE_REQUIRED",
            "request": {
                "controller_repo_root": str(controller),
                "controller_revision": head,
                "allowed_files": ["src/new.py"],
            },
        },
    )
    retained = service._reconcile_direct_failure("t")
    assert retained is not None and retained["status"] == "DIRECT_RECONCILE_REQUIRED"
    assert retained["reconciliation_evidence"]["untracked_changes"] == ["src/new.py"]
    assert retained["reconciliation_evidence"]["allowed_paths_touched"] == ["src/new.py"]


# ---------------------------------------------------------------------------
# _projected_pre_apply_recovery_evidence

T, A = "task-pre", "attempt-1"
C, TREE, SH, RH = "c" * 40, "d" * 40, "e" * 64, "f" * 64
AH, ZH = "1" * 64, "2" * 64


def _projected_state() -> dict[str, Any]:
    identity4 = {
        "candidate_commit_sha": C,
        "candidate_tree_sha": TREE,
        "candidate_state_hash": SH,
        "verified_receipt_hash": RH,
    }
    return {
        "task_id": T,
        "attempt_id": A,
        "status": "FINAL_BLOCK",
        "promotion_status": "NOT_CREATED",
        "terminal_status": "INTEGRATION_FAILED_PRE_APPLY",
        "final_disposition": "INTEGRATION_FAILED_PRE_APPLY",
        "integration_status": "NOT_APPLIED",
        "merge_performed": False,
        "integration_result_sha": None,
        "integration_receipt": None,
        "integration_error": "pre-apply check failed",
        "integration_execution": {
            "stage": "PRE_APPLY",
            "merge_performed": False,
            "post_apply_verified": False,
            "branch_head_before": "9" * 40,
            "branch_head_after": "9" * 40,
            "candidate_commit_sha": C,
        },
        "integration_closure_binding": {
            "binding_hash": "binding-1",
            "task_id": T,
            "attempt_id": A,
            "candidate_commit_sha": C,
            "acceptance_receipt_hash": AH,
            "authorization_hash": ZH,
        },
        "integration_approval_grant": {
            "approval_id": "approval-1",
            "consumed_at": "2026-10-18T00:00:00+00:00",
            "bound_task_id": T,
            "bound_attempt_id": A,
            "bound_action_type": LifecycleActionType.CANDIDATE_INTEGRATE.value,
            **identity4,
            "acceptance_receipt_hash": AH,
        },
        "external_acceptance": {
            "task_id": T,
            "attempt_id": A,
            "candidate_commit": C,
            "passed": True,
            "receipt_hash": AH,
        },
        "integration_preview": {"task_id": T, "candidate_commit": C, "acceptance_receipt_hash": AH},
        "integration_authorization": {
            "task_id": T,
            "attempt_id": A,
            "candidate_commit": C,
            "candidate_tree_sha": TREE,
            "candidate_state_hash": SH,
            "candidate_receipt_hash": RH,
            "acceptance_receipt_hash": AH,
            "authorization_hash": ZH,
        },
        "promotion_packet": dict(identity4),
        "approved_binding": dict(identity4),
        "status_history": [
            {"status": "APPROVED", "at": "t0"},
            {"status": "INTEGRATION_FAILED_PRE_APPLY", "at": "t1"},
            {"status": "FINAL_BLOCK", "at": "t2"},
        ],
    }


def _expected_projection(state: dict[str, Any]) -> dict[str, Any]:
    projection: dict[str, Any] = {
        "task_id": T,
        "attempt_id": A,
        "candidate_commit_sha": C,
        "candidate_tree_sha": TREE,
        "candidate_state_hash": SH,
        "verified_receipt_hash": RH,
        "closure_binding_hash": "binding-1",
        "integration_approval_id": "approval-1",
        "integration_execution_sha256": _canonical(state["integration_execution"]),
    }
    projection["projection_sha256"] = _canonical(projection)
    return projection


PROJECT = SelfHostedTaskService._projected_pre_apply_recovery_evidence


def test_projection_of_an_exact_lost_pre_apply_state() -> None:
    state = _projected_state()
    before = copy.deepcopy(state)
    assert PROJECT(state) == _expected_projection(state)
    assert state == before


def _set(path: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def apply(state: dict[str, Any]) -> None:
        *parents, leaf = path.split(".")
        target: Any = state
        for key in parents:
            target = target[key]
        if value is _DELETE:
            del target[leaf]
        else:
            target[leaf] = value

    return apply


_DELETE = object()
REFUSALS = {
    # the projected FINAL_BLOCK shape
    "status": _set("status", "INTEGRATION_FAILED_PRE_APPLY"),
    "promotion_status": _set("promotion_status", "APPROVED"),
    "terminal_status": _set("terminal_status", "FINAL_BLOCK"),
    "final_disposition": _set("final_disposition", None),
    "integration_status": _set("integration_status", "APPLIED"),
    "merge_performed": _set("merge_performed", "yes"),
    "integration_result_sha": _set("integration_result_sha", "r" * 40),
    "integration_receipt": _set("integration_receipt", {"x": 1}),
    # every bound record is a non-empty mapping
    "execution_missing": _set("integration_execution", _DELETE),
    "closure_empty": _set("integration_closure_binding", {}),
    "grant_list": _set("integration_approval_grant", [["approval_id", "x"]]),
    "acceptance_none": _set("external_acceptance", None),
    "preview_str": _set("integration_preview", "preview"),
    "authorization_empty": _set("integration_authorization", {}),
    "packet_missing": _set("promotion_packet", _DELETE),
    "approved_none": _set("approved_binding", None),
    # the PRE_APPLY execution record
    "stage": _set("integration_execution.stage", "POST_APPLY"),
    "execution_merge_none": _set("integration_execution.merge_performed", None),
    "post_apply_verified_none": _set("integration_execution.post_apply_verified", None),
    "branch_head_moved": _set("integration_execution.branch_head_after", "8" * 40),
    "binding_hash": _set("integration_closure_binding.binding_hash", ""),
    "approval_id": _set("integration_approval_grant.approval_id", None),
    "consumed_at": _set("integration_approval_grant.consumed_at", ""),
    # the identity
    "task_id": _set("task_id", ""),
    "attempt_id": _set("attempt_id", None),
    "packet_commit": _set("promotion_packet.candidate_commit_sha", ""),
    "packet_tree": _set("promotion_packet.candidate_tree_sha", None),
    "packet_state": _set("promotion_packet.candidate_state_hash", _DELETE),
    "packet_receipt": _set("promotion_packet.verified_receipt_hash", ""),
    # the status history and the error
    "history_not_list": _set(
        "status_history", ({"status": "INTEGRATION_FAILED_PRE_APPLY"}, {"status": "FINAL_BLOCK"})
    ),
    "history_short": _set("status_history", [{"status": "FINAL_BLOCK"}]),
    "history_not_mapping": _set(
        "status_history", [{"status": "INTEGRATION_FAILED_PRE_APPLY"}, "FINAL_BLOCK"]
    ),
    "history_order": _set(
        "status_history", [{"status": "FINAL_BLOCK"}, {"status": "INTEGRATION_FAILED_PRE_APPLY"}]
    ),
    "history_tail": _set(
        "status_history",
        [{"status": "INTEGRATION_FAILED_PRE_APPLY"}, {"status": "FINAL_BLOCK"}, {"status": "X"}],
    ),
    "error_blank": _set("integration_error", "  \n"),
    "error_missing": _set("integration_error", _DELETE),
    # closure / approved bindings
    "closure_task": _set("integration_closure_binding.task_id", "other"),
    "closure_attempt": _set("integration_closure_binding.attempt_id", ""),
    "closure_commit": _set("integration_closure_binding.candidate_commit_sha", "0" * 40),
    "approved_commit": _set("approved_binding.candidate_commit_sha", "0" * 40),
    "approved_tree": _set("approved_binding.candidate_tree_sha", _DELETE),
    "approved_state": _set("approved_binding.candidate_state_hash", "x"),
    "approved_receipt": _set("approved_binding.verified_receipt_hash", "x"),
    "execution_commit": _set("integration_execution.candidate_commit_sha", "0" * 40),
    # grant / acceptance / preview / authorization
    "grant_task": _set("integration_approval_grant.bound_task_id", "x"),
    "grant_attempt": _set("integration_approval_grant.bound_attempt_id", "x"),
    "grant_action": _set("integration_approval_grant.bound_action_type", "CANDIDATE_APPROVE"),
    "acceptance_task": _set("external_acceptance.task_id", "x"),
    "acceptance_attempt": _set("external_acceptance.attempt_id", "x"),
    "acceptance_commit": _set("external_acceptance.candidate_commit", "x"),
    "acceptance_passed": _set("external_acceptance.passed", "true"),
    "acceptance_hash": _set("external_acceptance.receipt_hash", "x"),
    "preview_task": _set("integration_preview.task_id", "x"),
    "preview_commit": _set("integration_preview.candidate_commit", "x"),
    "preview_hash": _set("integration_preview.acceptance_receipt_hash", "x"),
    "authorization_task": _set("integration_authorization.task_id", "x"),
    "authorization_attempt": _set("integration_authorization.attempt_id", "x"),
    "authorization_commit": _set("integration_authorization.candidate_commit", "x"),
    "authorization_tree": _set("integration_authorization.candidate_tree_sha", "x"),
    "authorization_state": _set("integration_authorization.candidate_state_hash", "x"),
    "authorization_receipt": _set("integration_authorization.candidate_receipt_hash", "x"),
    "authorization_acceptance": _set("integration_authorization.acceptance_receipt_hash", "x"),
    "authorization_hash": _set("integration_authorization.authorization_hash", "x"),
    "grant_commit": _set("integration_approval_grant.candidate_commit_sha", "x"),
    "grant_tree": _set("integration_approval_grant.candidate_tree_sha", "x"),
    "grant_state": _set("integration_approval_grant.candidate_state_hash", "x"),
    "grant_receipt": _set("integration_approval_grant.verified_receipt_hash", "x"),
    "grant_acceptance": _set("integration_approval_grant.acceptance_receipt_hash", _DELETE),
}


@pytest.mark.parametrize("label", sorted(REFUSALS))
def test_projection_refuses_any_unbound_or_changed_field(label) -> None:
    state = _projected_state()
    REFUSALS[label](state)
    assert PROJECT(state) is None


@pytest.mark.parametrize(
    "label, mutate",
    [
        (
            "closure without identity keys",
            lambda s: [
                s["integration_closure_binding"].pop(k)
                for k in ("task_id", "attempt_id", "candidate_commit_sha")
            ],
        ),
        (
            "closure without hashes (both empty)",
            lambda s: (
                [
                    s["integration_closure_binding"].pop(k)
                    for k in ("acceptance_receipt_hash", "authorization_hash")
                ]
                + [
                    s[r].update(v)
                    for r, v in (
                        ("external_acceptance", {"receipt_hash": ""}),
                        ("integration_preview", {"acceptance_receipt_hash": ""}),
                        (
                            "integration_authorization",
                            {"acceptance_receipt_hash": "", "authorization_hash": ""},
                        ),
                        ("integration_approval_grant", {"acceptance_receipt_hash": ""}),
                    )
                ]
            ),
        ),
        (
            "execution without its commit",
            lambda s: s["integration_execution"].pop("candidate_commit_sha"),
        ),
        ("longer history", lambda s: s["status_history"].insert(0, "not-a-mapping")),
        (
            "falsy merge flags",
            lambda s: s.update(
                merge_performed=0, integration_result_sha="", integration_receipt={}
            ),
        ),
        (
            "numeric identity compared as text",
            lambda s: [
                s.update(attempt_id=7),
                s["integration_closure_binding"].update(attempt_id="7"),
                s["integration_approval_grant"].update(bound_attempt_id=7),
                s["external_acceptance"].update(attempt_id="7"),
                s["integration_authorization"].update(attempt_id=7),
            ],
        ),
    ],
)
def test_projection_tolerated_variants(label, mutate) -> None:
    state = _projected_state()
    mutate(state)
    projection = PROJECT(state)
    assert projection is not None, label
    assert projection["attempt_id"] == str(state["attempt_id"])
    assert projection["integration_execution_sha256"] == _canonical(state["integration_execution"])


def test_projection_execution_digest_uses_the_jsonable_projection(monkeypatch) -> None:
    state = _projected_state()
    first = PROJECT(state)
    seen: list[Any] = []
    real = service_module._jsonable

    def late(value: Any) -> Any:
        seen.append(type(value).__name__)
        out = real(value)
        if isinstance(value, dict) and "stage" in value:
            out = {**out, "late": True}
        return out

    monkeypatch.setattr(service_module, "_jsonable", late)
    second = PROJECT(state)
    assert first is not None and second is not None
    assert seen and seen[0] == "dict"
    late_execution = {**state["integration_execution"], "late": True}
    assert second["integration_execution_sha256"] == _canonical(late_execution)
    assert second["projection_sha256"] != first["projection_sha256"]


def test_projection_action_type_is_read_through_the_facade(monkeypatch) -> None:
    state = _projected_state()
    assert PROJECT(state) is not None
    monkeypatch.setattr(
        service_module,
        "LifecycleActionType",
        SimpleNamespace(CANDIDATE_INTEGRATE=SimpleNamespace(value="LATE_INTEGRATE")),
    )
    assert PROJECT(state) is None
    state["integration_approval_grant"]["bound_action_type"] = "LATE_INTEGRATE"
    assert PROJECT(state) is not None


def _reconciled_native_state() -> dict[str, Any]:
    """A lost projection after ``_reconcile_projected_pre_apply_failure`` (Target removed)."""
    state = _projected_state()
    state.update(
        status="INTEGRATION_FAILED_PRE_APPLY",
        promotion_status="INTEGRATION_FAILED_PRE_APPLY",
        cleanup_decision="REMOVED",
        cleanup_performed=True,
        reconciliation_status="RECONCILED",
        reconciliation_decision="RESTORE_NATIVE_PRE_APPLY_STATUS",
        integration_reconciliation_history=[
            {
                "decision": "RESTORE_NATIVE_PRE_APPLY_STATUS",
                "projection_sha256": _expected_projection(_projected_state())["projection_sha256"],
            }
        ],
    )
    restored = {
        "status": "INTEGRATION_FAILED_PRE_APPLY",
        "reason": "projected_pre_apply_reconciled",
    }
    state["status_history"].append(restored)
    return state


def test_pre_apply_rejection_evidence_reaches_the_projection_through_the_class(monkeypatch) -> None:
    # the facade's pre-apply rejection path calls the static member on the class with the
    # state projected back to FINAL_BLOCK / NOT_CREATED
    state = _reconciled_native_state()
    calls: list[Any] = []
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_projected_pre_apply_recovery_evidence",
        staticmethod(lambda projected: (calls.append(dict(projected)), None)[1]),
    )
    assert SelfHostedTaskService._pre_apply_rejection_evidence(copy.deepcopy(state)) is None
    ((projected,),) = [calls]
    assert (projected["status"], projected["promotion_status"]) == ("FINAL_BLOCK", "NOT_CREATED")
    assert projected["status_history"] == _projected_state()["status_history"]


# ---------------------------------------------------------------------------
# _reconcile_projected_pre_apply_failure


@pytest.fixture
def projected(service, fixed_now) -> SimpleNamespace:
    state = _projected_state()
    service._write_state(T, copy.deepcopy(state))
    return SimpleNamespace(
        service=service, state=state, evidence=_expected_projection(state), now=fixed_now
    )


def test_projected_reconcile_restores_the_native_pre_apply_status(projected) -> None:
    result = projected.service._reconcile_projected_pre_apply_failure(T, projected.evidence)
    assert projected.now == [NOW]
    assert result["integration_reconciliation_history"] == [
        {
            "schema": "nexus.pre_apply_reconciliation.v1",
            **projected.evidence,
            "reconciled_at": NOW,
            "decision": "RESTORE_NATIVE_PRE_APPLY_STATUS",
        }
    ]
    expected = {
        "status": "INTEGRATION_FAILED_PRE_APPLY",
        "promotion_status": "INTEGRATION_FAILED_PRE_APPLY",
        "terminal_status": "INTEGRATION_FAILED_PRE_APPLY",
        "final_disposition": "INTEGRATION_FAILED_PRE_APPLY",
        "reconciliation_status": "RECONCILED",
        "reconciliation_decision": "RESTORE_NATIVE_PRE_APPLY_STATUS",
        "state_retention_status": "ACTIVE",
        "archive_eligible": False,
        "cleanup_eligible": False,
        "updated_at": NOW,
    }
    assert {key: result[key] for key in expected} == expected
    assert result["status_history"] == [
        *projected.state["status_history"],
        {
            "at": NOW,
            "status": "INTEGRATION_FAILED_PRE_APPLY",
            "reason": "projected_pre_apply_reconciled",
        },
    ]
    for key in (
        "integration_execution",
        "integration_closure_binding",
        "integration_approval_grant",
        "promotion_packet",
        "approved_binding",
        "integration_error",
    ):
        assert result[key] == projected.state[key]
    persisted = projected.service._read_state_snapshot(T)
    assert {key: persisted[key] for key in expected} == expected
    assert (
        persisted["integration_reconciliation_history"]
        == result["integration_reconciliation_history"]
    )
    # replaying the same evidence on the restored state is concurrency drift
    with pytest.raises(RuntimeError, match="^PRE_APPLY_RECONCILIATION_CONCURRENCY_DRIFT$"):
        projected.service._reconcile_projected_pre_apply_failure(T, projected.evidence)


def test_projected_reconcile_appends_to_an_existing_history(service, fixed_now) -> None:
    state = {
        **_projected_state(),
        "integration_reconciliation_history": [{"projection_sha256": "older"}],
    }
    service._write_state(T, state)
    result = service._reconcile_projected_pre_apply_failure(T, _expected_projection(state))
    assert [
        entry.get("projection_sha256") for entry in result["integration_reconciliation_history"]
    ] == [
        "older",
        _expected_projection(state)["projection_sha256"],
    ]


def test_projected_reconcile_same_projection_already_recorded_is_a_no_op(
    service, fixed_now
) -> None:
    evidence = _expected_projection(_projected_state())
    state = {
        **_projected_state(),
        "integration_reconciliation_history": [
            {"projection_sha256": evidence["projection_sha256"], "n": 1}
        ],
    }
    service._write_state(T, copy.deepcopy(state))
    before = service._read_state_snapshot(T)
    result = service._reconcile_projected_pre_apply_failure(T, evidence)
    assert result["status"] == "FINAL_BLOCK"
    assert result["integration_reconciliation_history"] == [
        {"projection_sha256": evidence["projection_sha256"], "n": 1}
    ]
    assert result["status_history"] == state["status_history"]
    assert "updated_at" not in result or result.get("updated_at") == before.get("updated_at")


@pytest.mark.parametrize("history", [{}, "x", 0, None])
def test_projected_reconcile_refuses_a_malformed_history(service, fixed_now, history) -> None:
    state = {**_projected_state(), "integration_reconciliation_history": history}
    service._write_state(T, copy.deepcopy(state))
    evidence = _expected_projection(state)
    # an explicit null history is "present but not a list" too
    with pytest.raises(RuntimeError, match="^PRE_APPLY_RECONCILIATION_HISTORY_MALFORMED$"):
        service._reconcile_projected_pre_apply_failure(T, evidence)
    assert service._read_state_snapshot(T)["status"] == "FINAL_BLOCK"


def test_projected_reconcile_refuses_changed_evidence(projected) -> None:
    changed = {**projected.evidence, "projection_sha256": "0" * 64}
    with pytest.raises(RuntimeError, match="^PRE_APPLY_RECONCILIATION_CONCURRENCY_DRIFT$"):
        projected.service._reconcile_projected_pre_apply_failure(T, changed)
    assert projected.service._read_state_snapshot(T)["status"] == "FINAL_BLOCK"


def test_projected_reconcile_refuses_a_state_that_moved_on(projected) -> None:
    projected.service._mutate_state(T, lambda state: state.update(integration_error=""))
    with pytest.raises(RuntimeError, match="^PRE_APPLY_RECONCILIATION_CONCURRENCY_DRIFT$"):
        projected.service._reconcile_projected_pre_apply_failure(T, projected.evidence)


def test_projected_reconcile_refuses_a_malformed_status_history(
    service, monkeypatch, fixed_now
) -> None:
    # only reachable when the projection is patched through self
    evidence = {"projection_sha256": "p", "x": 1}
    monkeypatch.setattr(
        service, "_projected_pre_apply_recovery_evidence", lambda current: dict(evidence)
    )
    service._write_state(T, {"task_id": T, "status": "FINAL_BLOCK", "status_history": "broken"})
    with pytest.raises(RuntimeError, match="^PRE_APPLY_RECONCILIATION_STATUS_HISTORY_MALFORMED$"):
        service._reconcile_projected_pre_apply_failure(T, evidence)
    assert service._read_state_snapshot(T)["status"] == "FINAL_BLOCK"


def test_projected_reconcile_unknown_task_is_a_key_error(service, fixed_now) -> None:
    with pytest.raises(KeyError, match="unknown task_id: missing"):
        service._reconcile_projected_pre_apply_failure("missing", {"projection_sha256": "x"})


def test_projected_reconcile_reaches_the_projection_and_mutate_through_self(
    service, monkeypatch, fixed_now
) -> None:
    seen: list[Any] = []
    evidence = {"projection_sha256": "p"}
    monkeypatch.setattr(
        service,
        "_projected_pre_apply_recovery_evidence",
        lambda current: (seen.append("projection"), dict(evidence))[1],
    )
    current: dict[str, Any] = {"status_history": []}

    def mutate(task_id: str, mutator: Callable[[dict[str, Any]], None]) -> Any:
        seen.append(("mutate", task_id))
        mutator(current)
        return {"persisted": current["status"]}

    monkeypatch.setattr(service, "_mutate_state", mutate)
    assert service._reconcile_projected_pre_apply_failure("x", evidence) == {
        "persisted": "INTEGRATION_FAILED_PRE_APPLY"
    }
    assert seen == [("mutate", "x"), "projection"]
    assert current["integration_reconciliation_history"] == [
        {
            "schema": "nexus.pre_apply_reconciliation.v1",
            "projection_sha256": "p",
            "reconciled_at": NOW,
            "decision": "RESTORE_NATIVE_PRE_APPLY_STATUS",
        }
    ]


def test_projected_reconcile_history_record_uses_jsonable(service, monkeypatch, fixed_now) -> None:
    evidence = {"projection_sha256": "p"}
    monkeypatch.setattr(
        service, "_projected_pre_apply_recovery_evidence", lambda current: dict(evidence)
    )
    current: dict[str, Any] = {"status_history": []}
    monkeypatch.setattr(
        service, "_mutate_state", lambda task_id, mutator: (mutator(current), current)[1]
    )
    service._reconcile_projected_pre_apply_failure("x", evidence)
    seen: list[Any] = []
    monkeypatch.setattr(
        service_module,
        "_jsonable",
        lambda value: (seen.append(dict(value)), {"jsonable": "late"})[1],
    )
    monkeypatch.setattr(service_module, "_utc_now", lambda: "LATE-NOW")
    current = {"status_history": []}
    service._reconcile_projected_pre_apply_failure("x", evidence)
    assert seen == [evidence]
    assert current["integration_reconciliation_history"] == [
        {
            "schema": "nexus.pre_apply_reconciliation.v1",
            "jsonable": "late",
            "reconciled_at": "LATE-NOW",
            "decision": "RESTORE_NATIVE_PRE_APPLY_STATUS",
        }
    ]
    assert current["updated_at"] == "LATE-NOW"


# ---------------------------------------------------------------------------
# _read_adoption_artifact

TASK = "adopt-1"
CONTENT = b'{"evidence": true}\n'
DIGEST = _sha(CONTENT)


def _store(
    service: Any, task_id: str = TASK, content: bytes = CONTENT, kind: str = "validation"
) -> str:
    return service._store_adoption_artifact(task_id, _sha(content), content, kind)


def test_read_artifact_round_trip(service) -> None:
    locator = _store(service)
    assert locator == str(
        service.state_dir / "adoption-artifacts" / TASK / f"validation-{DIGEST}.json"
    )
    assert service._read_adoption_artifact(TASK, locator, DIGEST, "validation") == CONTENT


def test_read_artifact_opens_relative_without_following_symlinks(service, monkeypatch) -> None:
    locator = _store(service)
    log: list[Any] = []
    real = {name: getattr(os, name) for name in ("open", "close", "fstat", "read")}
    fds: dict[int, str] = {}

    def opener(path: Any, flags: int, *args: Any, dir_fd: Any = None, **kwargs: Any) -> int:
        fd = real["open"](path, flags, *args, dir_fd=dir_fd, **kwargs)
        name = Path(path).name if dir_fd is None else str(path)
        fds[fd] = name
        parent = fds.get(dir_fd) if dir_fd is not None else None
        directory = bool(flags & os.O_DIRECTORY)
        nofollow = bool(flags & getattr(os, "O_NOFOLLOW", 0)) or not hasattr(os, "O_NOFOLLOW")
        log.append(("open", name, parent, directory, nofollow))
        return fd

    monkeypatch.setattr(os, "open", opener)
    monkeypatch.setattr(
        os, "close", lambda fd: (log.append(("close", fds.get(fd))), real["close"](fd))[1]
    )
    monkeypatch.setattr(
        os, "fstat", lambda fd: (log.append(("fstat", fds.get(fd))), real["fstat"](fd))[1]
    )
    monkeypatch.setattr(
        os, "read", lambda fd, n: (log.append(("read", fds.get(fd), n)), real["read"](fd, n))[1]
    )
    assert service._read_adoption_artifact(TASK, locator, DIGEST, "validation") == CONTENT
    file_name = f"validation-{DIGEST}.json"
    assert log == [
        ("open", "state", None, True, True),
        ("open", "adoption-artifacts", "state", True, True),
        ("open", TASK, "adoption-artifacts", True, True),
        ("open", file_name, TASK, False, True),
        ("close", TASK),
        ("close", "adoption-artifacts"),
        ("close", "state"),
        ("fstat", file_name),
        ("read", file_name, 1024 * 1024 + 1),
        ("close", file_name),
    ]


@pytest.mark.parametrize("task_id", ["", "-lead", ".hidden", "a/b", "a b", "../x", "ä"])
def test_read_artifact_refuses_an_unsafe_task_id(service, task_id) -> None:
    with pytest.raises(RuntimeError, match="^adoption artifact task id is unsafe$"):
        service._read_adoption_artifact(task_id, "/x", DIGEST, "validation")


@pytest.mark.parametrize(
    "kind, digest",
    [
        ("Validation", DIGEST),
        ("1kind", DIGEST),
        ("", DIGEST),
        ("validation", DIGEST.upper()),
        ("validation", DIGEST[:-1]),
        ("validation", DIGEST + "0"),
    ],
)
def test_read_artifact_refuses_a_malformed_locator(service, kind, digest) -> None:
    with pytest.raises(RuntimeError, match="^adoption artifact locator is malformed$"):
        service._read_adoption_artifact(TASK, "/x", digest, kind)


def test_read_artifact_refuses_a_non_canonical_locator(service, tmp_path) -> None:
    locator = _store(service)
    for other in (
        str(tmp_path / "elsewhere.json"),
        locator + "/",
        str(Path(locator).parent / ".." / TASK / Path(locator).name),
        str(service.state_dir / "adoption-artifacts" / TASK / f"acceptance-{DIGEST}.json"),
    ):
        expected = "^external adoption evidence locator is not canonical$"
        if Path(other) == Path(locator):
            continue
        with pytest.raises(RuntimeError, match=expected):
            service._read_adoption_artifact(TASK, other, DIGEST, "validation")


def test_read_artifact_missing_file_is_unreadable(service) -> None:
    locator = str(service.state_dir / "adoption-artifacts" / TASK / f"validation-{DIGEST}.json")
    with pytest.raises(RuntimeError, match="unreadable or escaped service state") as caught:
        service._read_adoption_artifact(TASK, locator, DIGEST, "validation")
    assert isinstance(caught.value.__cause__, OSError)


@pytest.mark.parametrize("where", ["file", "task", "artifacts"])
def test_read_artifact_refuses_symlinks(service, tmp_path, where) -> None:
    locator = _store(service)
    artifacts = service.state_dir / "adoption-artifacts"
    outside = tmp_path / "outside"
    if where == "file":
        real = Path(locator).with_name("real.json")
        Path(locator).rename(real)
        Path(locator).symlink_to(real)
    elif where == "task":
        (artifacts / TASK).rename(outside)
        (artifacts / TASK).symlink_to(outside, target_is_directory=True)
    else:
        artifacts.rename(outside)
        artifacts.symlink_to(outside, target_is_directory=True)
    assert Path(locator).read_bytes() == CONTENT  # readable when symlinks are followed
    with pytest.raises(RuntimeError, match="unreadable or escaped service state"):
        service._read_adoption_artifact(TASK, locator, DIGEST, "validation")


def test_read_artifact_refuses_a_state_root_replaced_by_a_symlink(service, tmp_path) -> None:
    # the service resolves its state dir at construction; a later swap of that path for a
    # symlink is refused (the root itself is opened without following symlinks)
    locator = _store(service)
    moved = tmp_path / "moved-state"
    service.state_dir.rename(moved)
    service.state_dir.symlink_to(moved, target_is_directory=True)
    assert Path(locator).read_bytes() == CONTENT
    with pytest.raises(RuntimeError, match="unreadable or escaped service state"):
        service._read_adoption_artifact(TASK, locator, DIGEST, "validation")


def test_read_artifact_refuses_a_non_regular_file(service) -> None:
    locator = _store(service)
    Path(locator).unlink()
    Path(locator).mkdir()
    with pytest.raises(
        RuntimeError, match="^external adoption restart evidence is not a regular file$"
    ):
        service._read_adoption_artifact(TASK, locator, DIGEST, "validation")


def test_read_artifact_refuses_replaced_content(service) -> None:
    locator = _store(service)
    Path(locator).write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="^external adoption restart evidence hash mismatch$"):
        service._read_adoption_artifact(TASK, locator, DIGEST, "validation")


def test_read_artifact_reads_at_most_one_mebibyte_plus_one(service) -> None:
    exact = b"x" * (1024 * 1024 + 1)
    locator = _store(service, content=exact)
    assert service._read_adoption_artifact(TASK, locator, _sha(exact), "validation") == exact
    bigger = b"y" * (1024 * 1024 + 2)
    locator = _store(service, content=bigger)
    with pytest.raises(RuntimeError, match="^external adoption restart evidence hash mismatch$"):
        service._read_adoption_artifact(TASK, locator, _sha(bigger), "validation")


def test_read_artifact_other_errors_propagate(service, monkeypatch) -> None:
    locator = _store(service)
    monkeypatch.setattr(os, "fstat", lambda fd: (_ for _ in ()).throw(ValueError("odd")))
    with pytest.raises(ValueError, match="odd"):
        service._read_adoption_artifact(TASK, locator, DIGEST, "validation")


# ---------------------------------------------------------------------------
# _resume_external_adoption

VALIDATION = b'{"validation": 1}'
ACCEPTANCE = b'{"acceptance": 1}'


@pytest.fixture
def resume(service, monkeypatch) -> SimpleNamespace:
    reads: list[Any] = []
    adopted: list[Any] = []
    contents = {"validation": VALIDATION, "acceptance": ACCEPTANCE}

    def read(task_id: str, raw_locator: str, digest: str, kind: str) -> bytes:
        reads.append((task_id, raw_locator, digest, kind))
        return contents[kind]

    monkeypatch.setattr(service, "_read_adoption_artifact", read)
    monkeypatch.setattr(
        service,
        "adopt_external_candidate",
        lambda request: (adopted.append(dict(request)), {"adopted": True})[1],
    )
    request = {
        "task_id": TASK,
        "attempt_id": "att",
        "validation_receipt_sha256": _sha(VALIDATION),
        "acceptance_receipt_sha256": _sha(ACCEPTANCE),
    }
    state = {
        "status": "ADOPTING",
        "request": request,
        "validation_receipt_locator": "/loc/validation",
        "acceptance_receipt_locator": "/loc/acceptance",
    }
    return SimpleNamespace(
        service=service,
        reads=reads,
        adopted=adopted,
        contents=contents,
        request=request,
        state=state,
    )


def test_resume_replays_the_request_with_both_receipts(resume) -> None:
    assert resume.service._resume_external_adoption(TASK, resume.state) == {"adopted": True}
    assert resume.reads == [
        (TASK, "/loc/validation", _sha(VALIDATION), "validation"),
        (TASK, "/loc/acceptance", _sha(ACCEPTANCE), "acceptance"),
    ]
    assert resume.adopted == [
        {
            **resume.request,
            "validation_receipt_b64": base64.b64encode(VALIDATION).decode("ascii"),
            "acceptance_receipt_b64": base64.b64encode(ACCEPTANCE).decode("ascii"),
        }
    ]
    assert "validation_receipt_b64" not in resume.request


@pytest.mark.parametrize("request_value", [None, "x", ["task_id"], {"task_id": "other"}, {}])
def test_resume_refuses_a_missing_or_mismatched_request(resume, request_value) -> None:
    state = {**resume.state, "request": request_value}
    with pytest.raises(
        RuntimeError, match="^external adoption restart request is missing or mismatched$"
    ):
        resume.service._resume_external_adoption(TASK, state)
    assert resume.reads == [] and resume.adopted == []


@pytest.mark.parametrize(
    "field, value",
    [
        ("validation_receipt_locator", None),
        ("validation_receipt_locator", ""),
        ("validation_receipt_locator", 7),
        ("acceptance_receipt_locator", None),
        ("validation_receipt_sha256", "A" * 64),
        ("validation_receipt_sha256", "0" * 63),
        ("acceptance_receipt_sha256", None),
        ("acceptance_receipt_sha256", "g" * 64),
    ],
)
def test_resume_refuses_a_missing_locator_or_digest(resume, field, value) -> None:
    state = copy.deepcopy(resume.state)
    if field.endswith("_locator"):
        state[field] = value
    else:
        state["request"][field] = value
    with pytest.raises(
        RuntimeError, match="^external adoption restart evidence locator is missing$"
    ):
        resume.service._resume_external_adoption(TASK, state)
    assert resume.adopted == []
    assert len(resume.reads) == (1 if field.startswith("acceptance") else 0)


@pytest.mark.parametrize("kind", ["validation", "acceptance"])
def test_resume_refuses_content_that_does_not_match_the_request_digest(resume, kind) -> None:
    resume.contents[kind] = b"other"
    with pytest.raises(RuntimeError, match="^external adoption restart evidence hash mismatch$"):
        resume.service._resume_external_adoption(TASK, resume.state)
    assert resume.adopted == []


def test_resume_reader_errors_propagate(resume, monkeypatch) -> None:
    monkeypatch.setattr(
        resume.service,
        "_read_adoption_artifact",
        lambda *a: (_ for _ in ()).throw(RuntimeError("reader says no")),
    )
    with pytest.raises(RuntimeError, match="^reader says no$"):
        resume.service._resume_external_adoption(TASK, resume.state)


def test_resume_with_real_artifacts(service, monkeypatch) -> None:
    validation_locator = _store(service, content=VALIDATION, kind="validation")
    acceptance_locator = _store(service, content=ACCEPTANCE, kind="acceptance")
    adopted: list[Any] = []
    monkeypatch.setattr(
        service, "adopt_external_candidate", lambda request: (adopted.append(request), "OK")[1]
    )
    request = {
        "task_id": TASK,
        "validation_receipt_sha256": _sha(VALIDATION),
        "acceptance_receipt_sha256": _sha(ACCEPTANCE),
    }
    state = {
        "request": request,
        "validation_receipt_locator": validation_locator,
        "acceptance_receipt_locator": acceptance_locator,
    }
    assert service._resume_external_adoption(TASK, state) == "OK"
    assert base64.b64decode(adopted[0]["acceptance_receipt_b64"]) == ACCEPTANCE
    # the locators are bound to their kind: swapped locators are not canonical
    swapped = {**state, "validation_receipt_locator": acceptance_locator}
    with pytest.raises(RuntimeError, match="not canonical"):
        service._resume_external_adoption(TASK, swapped)


# ---------------------------------------------------------------------------
# _validate_persisted_external_adoption


def _adoption() -> SimpleNamespace:
    request = SimpleNamespace(
        task_id=TASK,
        attempt_id="att-1",
        action_id="action-1",
        idempotency_key="idem-1",
        task_card_path="cards/adopt.md",
        task_card_hash="h" * 64,
        controller_revision="1" * 40,
        target_base_revision="2" * 40,
        candidate_commit_sha="3" * 40,
        candidate_tree_sha="4" * 40,
        candidate_diff_sha256="5" * 64,
        validation_receipt_sha256="6" * 64,
        acceptance_receipt_sha256="7" * 64,
        action=SimpleNamespace(
            model_dump=lambda mode: {"type": "CANDIDATE_ADOPT_EXTERNAL", "mode": mode}
        ),
    )
    contract = {
        "task_id": TASK,
        "allowed_files": ["src/a.py"],
        "expected_evidence": None,
        "contract_hash": "self",
    }
    contract_hash = _canonical({"task_id": TASK, "allowed_files": ["src/a.py"]})
    verified = {
        "verified": True,
        "repository_contract_policy_revision_hash": "p" * 64,
        "public_claim_allowed": False,
    }
    derived = {
        "repository_contract_policy_revision_hash": "p" * 64,
        "forbidden_repository_patterns": ["secrets/**"],
    }
    packet = {
        "task_id": TASK,
        "contract_hash": contract_hash,
        "controller_revision": request.controller_revision,
        "target_base_revision": request.target_base_revision,
        "candidate_state_hash": "s" * 64,
        "candidate_commit_sha": request.candidate_commit_sha,
        "candidate_tree_sha": request.candidate_tree_sha,
        "verified_receipt_hash": _canonical(verified),
        "candidate_commit_created": True,
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "public_claim_allowed": False,
        "production_ready": False,
        "merge_performed": False,
        "push_performed": False,
    }
    receipt = {
        "schema": "nexus.external_candidate_adoption_receipt.v1",
        "task_id": TASK,
        "attempt_id": request.attempt_id,
        "action_id": request.action_id,
        "idempotency_key": request.idempotency_key,
        "adoption_request_hash": "semantic",
        "task_card_path": request.task_card_path,
        "task_card_hash": request.task_card_hash,
        "contract_hash": contract_hash,
        "controller_revision": request.controller_revision,
        "target_base_revision": request.target_base_revision,
        "candidate_commit_sha": request.candidate_commit_sha,
        "candidate_tree_sha": request.candidate_tree_sha,
        "candidate_diff_sha256": request.candidate_diff_sha256,
        "candidate_state_hash": packet["candidate_state_hash"],
        "verified_receipt_hash": packet["verified_receipt_hash"],
        "validation_receipt_sha256": request.validation_receipt_sha256,
        "acceptance_receipt_sha256": request.acceptance_receipt_sha256,
        "reviewer_id": "reviewer-1",
        "repository_contract_policy_revision_hash": "p" * 64,
        "derived_contract_projection": derived,
        "forbidden_repository_patterns": ["secrets/**"],
        "candidate_ref": f"refs/nexus/candidates/{TASK}",
        "promotion_packet_hash": _canonical(packet),
        "worker_invocations": 0,
        "candidate_rewritten": False,
        "approval_performed": False,
        "integration_performed": False,
        "merge_performed": False,
        "push_performed": False,
        "public_claim_allowed": False,
        "production_ready": False,
        "claim_ceiling": ["CANDIDATE_ADOPTED_PENDING_HUMAN_APPROVAL_ONLY"],
        "issued_at": NOW,
    }
    acceptance = {
        "schema": "nexus.external_candidate_acceptance.v1",
        "task_id": TASK,
        "candidate_commit_sha": request.candidate_commit_sha,
        "candidate_tree_sha": request.candidate_tree_sha,
        "candidate_diff_sha256": request.candidate_diff_sha256,
        "validation_receipt_sha256": request.validation_receipt_sha256,
        "disposition": "ACCEPT_CANDIDATE",
        "reviewer_id": "reviewer-1",
    }
    state = {
        "status": "PENDING_HUMAN_APPROVAL",
        "promotion_status": "PENDING_HUMAN_APPROVAL",
        "adoption_request_hash": "semantic",
        "action": {"type": "CANDIDATE_ADOPT_EXTERNAL", "mode": "json"},
        "task_card_path": request.task_card_path,
        "task_card_hash": request.task_card_hash,
        "controller_revision": request.controller_revision,
        "target_initial_revision": request.target_base_revision,
        "candidate_commit_sha": request.candidate_commit_sha,
        "candidate_tree_sha": request.candidate_tree_sha,
        "candidate": {
            "candidate_commit_sha": request.candidate_commit_sha,
            "candidate_tree_sha": request.candidate_tree_sha,
            "candidate_state_hash": "s" * 64,
            "verified_receipt_hash": packet["verified_receipt_hash"],
        },
        "candidate_state_hash": "s" * 64,
        "verified_receipt_hash": packet["verified_receipt_hash"],
        "contract": contract,
        "contract_hash": contract_hash,
        "adoption_receipt": receipt,
        "adoption_receipt_hash": _canonical(receipt),
        "promotion_packet": packet,
        "verified_receipt": verified,
        "derived_contract_projection": derived,
        "candidate_ref": f"refs/nexus/candidates/{TASK}",
        "submitted_at": NOW,
        "external_acceptance": dict(acceptance),
        "approved_binding": None,
        "integration_authorization": None,
        "integration_receipt": None,
        "merge_performed": False,
        "push_performed": False,
        "public_claim_allowed": False,
        "production_ready": False,
    }
    return SimpleNamespace(state=state, request=request, acceptance=acceptance, semantic="semantic")


def _validate(service: Any, a: SimpleNamespace) -> None:
    service._validate_persisted_external_adoption(a.state, a.request, a.semantic, a.acceptance)


def test_validate_accepts_a_fully_bound_replay(service) -> None:
    a = _adoption()
    before = copy.deepcopy(a.state)
    assert (
        service._validate_persisted_external_adoption(a.state, a.request, a.semantic, a.acceptance)
        is None
    )
    assert a.state == before


def _rehash(a: SimpleNamespace) -> None:
    """Re-seal the receipt hash after a deliberate receipt edit."""
    a.state["adoption_receipt_hash"] = _canonical(a.state["adoption_receipt"])


def _with(fn: Callable[[SimpleNamespace], Any]) -> Callable[[SimpleNamespace], None]:
    def apply(a: SimpleNamespace) -> None:
        fn(a)

    return apply


VALIDATE_REFUSALS: list[tuple[str, Callable[[SimpleNamespace], None], str]] = [
    (
        "receipt missing",
        _with(lambda a: a.state.pop("adoption_receipt")),
        "replay evidence is incomplete",
    ),
    (
        "packet not mapping",
        _with(lambda a: a.state.update(promotion_packet=["x"])),
        "replay evidence is incomplete",
    ),
    (
        "verified none",
        _with(lambda a: a.state.update(verified_receipt=None)),
        "replay evidence is incomplete",
    ),
    ("status", _with(lambda a: a.state.update(status="ADOPTING")), "replay status is invalid"),
    (
        "promotion status",
        _with(lambda a: a.state.update(promotion_status="APPROVED")),
        "replay status is invalid",
    ),
    (
        "semantic hash",
        _with(lambda a: setattr(a, "semantic", "other")),
        "replay request binding mismatch",
    ),
    (
        "action",
        _with(lambda a: a.state.update(action={"type": "X"})),
        "replay request binding mismatch",
    ),
    (
        "card path",
        _with(lambda a: a.state.update(task_card_path="x")),
        "replay state binding mismatch",
    ),
    (
        "card hash",
        _with(lambda a: a.state.update(task_card_hash="x")),
        "replay state binding mismatch",
    ),
    (
        "controller revision",
        _with(lambda a: a.state.update(controller_revision="x")),
        "replay state binding mismatch",
    ),
    (
        "target base",
        _with(lambda a: a.state.update(target_initial_revision="x")),
        "replay state binding mismatch",
    ),
    (
        "commit",
        _with(lambda a: a.state.update(candidate_commit_sha="x")),
        "replay state binding mismatch",
    ),
    (
        "tree",
        _with(lambda a: a.state.update(candidate_tree_sha="x")),
        "replay state binding mismatch",
    ),
    (
        "candidate not mapping",
        _with(lambda a: a.state.update(candidate=None)),
        "replay candidate identity mismatch",
    ),
    (
        "candidate extra key",
        _with(lambda a: a.state["candidate"].update(extra=1)),
        "replay candidate identity mismatch",
    ),
    (
        "candidate commit",
        _with(lambda a: a.state["candidate"].update(candidate_commit_sha="x")),
        "replay candidate identity mismatch",
    ),
    (
        "candidate state vs packet",
        _with(lambda a: a.state["promotion_packet"].update(candidate_state_hash="x")),
        "replay candidate identity mismatch",
    ),
    (
        "candidate state vs receipt",
        _with(lambda a: a.state["adoption_receipt"].update(candidate_state_hash="x")),
        "replay candidate identity mismatch",
    ),
    (
        "contract not mapping",
        _with(lambda a: a.state.update(contract="x")),
        "replay contract binding mismatch",
    ),
    (
        "contract changed",
        _with(lambda a: a.state["contract"].update(allowed_files=["src/b.py"])),
        "replay contract binding mismatch",
    ),
    (
        "contract universe added",
        _with(lambda a: a.state["contract"].update(expected_evidence={"u": 1})),
        "replay contract binding mismatch",
    ),
    (
        "contract hash",
        _with(lambda a: a.state.update(contract_hash="x")),
        "replay contract binding mismatch",
    ),
    (
        "receipt reviewer (self-bound) breaks the hash",
        _with(lambda a: a.state["adoption_receipt"].update(reviewer_id=None)),
        "replay receipt hash mismatch",
    ),
    (
        "receipt reviewer re-sealed",
        _with(lambda a: (a.state["adoption_receipt"].update(reviewer_id="other"), _rehash(a))),
        "replay acceptance binding mismatch",
    ),
    (
        "receipt worker invocations",
        _with(lambda a: a.state["adoption_receipt"].update(worker_invocations=1)),
        "replay receipt binding mismatch",
    ),
    (
        "receipt ceiling",
        _with(lambda a: a.state["adoption_receipt"].update(claim_ceiling=["MORE"])),
        "replay receipt binding mismatch",
    ),
    (
        "receipt issued at",
        _with(lambda a: a.state.update(submitted_at="later")),
        "replay receipt binding mismatch",
    ),
    (
        "receipt candidate ref",
        _with(lambda a: a.state.update(candidate_ref="refs/x")),
        "replay receipt binding mismatch",
    ),
    (
        "receipt packet hash",
        _with(lambda a: a.state["adoption_receipt"].update(promotion_packet_hash="x")),
        "replay receipt binding mismatch",
    ),
    (
        "receipt forbidden patterns",
        _with(lambda a: a.state["adoption_receipt"].update(forbidden_repository_patterns=[])),
        "replay receipt binding mismatch",
    ),
    (
        "receipt policy hash",
        _with(
            lambda a: a.state["verified_receipt"].update(
                repository_contract_policy_revision_hash="q"
            )
        ),
        "replay receipt binding mismatch",
    ),
    (
        "receipt extra field",
        _with(lambda a: (a.state["adoption_receipt"].update(extra=True), _rehash(a))),
        "replay receipt contains unexpected fields",
    ),
    (
        "receipt hash",
        _with(lambda a: a.state.update(adoption_receipt_hash="x")),
        "replay receipt hash mismatch",
    ),
    (
        "verified hash vs packet",
        _with(lambda a: a.state.update(verified_receipt_hash="x")),
        "replay candidate identity mismatch",
    ),
    (
        "verified content",
        _with(lambda a: a.state["verified_receipt"].update(verified=False)),
        "replay verified receipt binding mismatch",
    ),
    (
        "policy projection none",
        _with(
            lambda a: (
                a.state.update(derived_contract_projection=None),
                a.state["adoption_receipt"].update(
                    derived_contract_projection=None, forbidden_repository_patterns=[]
                ),
                _rehash(a),
            )
        ),
        "replay policy evidence binding mismatch",
    ),
    (
        "policy projection hash",
        _with(
            lambda a: (
                a.state["derived_contract_projection"].update(
                    repository_contract_policy_revision_hash="q"
                ),
                a.state["adoption_receipt"].update(
                    derived_contract_projection=a.state["derived_contract_projection"]
                ),
                _rehash(a),
            )
        ),
        "replay policy evidence binding mismatch",
    ),
    (
        "packet promotion status",
        _with(
            lambda a: (
                a.state["promotion_packet"].update(promotion_status="APPROVED"),
                a.state["adoption_receipt"].update(
                    promotion_packet_hash=_canonical(a.state["promotion_packet"])
                ),
                _rehash(a),
            )
        ),
        "replay promotion packet binding mismatch",
    ),
    (
        "packet commit created",
        _with(
            lambda a: (
                a.state["promotion_packet"].update(candidate_commit_created=False),
                a.state["adoption_receipt"].update(
                    promotion_packet_hash=_canonical(a.state["promotion_packet"])
                ),
                _rehash(a),
            )
        ),
        "replay promotion packet binding mismatch",
    ),
    (
        "packet push",
        _with(
            lambda a: (
                a.state["promotion_packet"].update(push_performed=None),
                a.state["adoption_receipt"].update(
                    promotion_packet_hash=_canonical(a.state["promotion_packet"])
                ),
                _rehash(a),
            )
        ),
        "replay promotion packet binding mismatch",
    ),
    (
        "packet task",
        _with(
            lambda a: (
                a.state["promotion_packet"].update(task_id="x"),
                a.state["adoption_receipt"].update(
                    promotion_packet_hash=_canonical(a.state["promotion_packet"])
                ),
                _rehash(a),
            )
        ),
        "replay promotion packet binding mismatch",
    ),
]


def _verified_flag(field: str, value: Any) -> Callable[[SimpleNamespace], None]:
    def apply(a: SimpleNamespace) -> None:
        a.state["verified_receipt"][field] = value
        digest = _canonical(a.state["verified_receipt"])
        a.state["verified_receipt_hash"] = digest
        a.state["candidate"]["verified_receipt_hash"] = digest
        a.state["promotion_packet"]["verified_receipt_hash"] = digest
        a.state["adoption_receipt"]["verified_receipt_hash"] = digest
        a.state["adoption_receipt"]["promotion_packet_hash"] = _canonical(
            a.state["promotion_packet"]
        )
        _rehash(a)

    return apply


VALIDATE_REFUSALS += [
    (
        "verified public claim",
        _verified_flag("public_claim_allowed", True),
        "replay verified receipt contains downstream authority",
    ),
    (
        "verified production",
        _verified_flag("production_ready", "yes"),
        "replay verified receipt contains downstream authority",
    ),
    (
        "verified merge",
        _verified_flag("merge_performed", 1),
        "replay verified receipt contains downstream authority",
    ),
    (
        "verified push",
        _verified_flag("push_performed", True),
        "replay verified receipt contains downstream authority",
    ),
    (
        "verified commit created",
        _verified_flag("candidate_commit_created", True),
        "replay verified receipt contains promotion authority",
    ),
    (
        "verified authority findings",
        _verified_flag("authority_change_required", ["x"]),
        "replay verified receipt contains authority findings",
    ),
    (
        "acceptance state differs",
        _with(lambda a: a.state.update(external_acceptance={**a.acceptance, "x": 1})),
        "replay acceptance binding mismatch",
    ),
    (
        "acceptance missing in state",
        _with(lambda a: a.state.update(external_acceptance=None)),
        "replay acceptance binding mismatch",
    ),
    (
        "acceptance schema",
        _with(
            lambda a: (
                a.acceptance.update(schema="v2"),
                a.state.update(external_acceptance=dict(a.acceptance)),
            )
        ),
        "replay acceptance binding mismatch",
    ),
    (
        "acceptance disposition",
        _with(
            lambda a: (
                a.acceptance.update(disposition="REJECT"),
                a.state.update(external_acceptance=dict(a.acceptance)),
            )
        ),
        "replay acceptance binding mismatch",
    ),
    (
        "acceptance diff",
        _with(
            lambda a: (
                a.acceptance.update(candidate_diff_sha256="x"),
                a.state.update(external_acceptance=dict(a.acceptance)),
            )
        ),
        "replay acceptance binding mismatch",
    ),
    (
        "acceptance reviewer vs receipt",
        _with(
            lambda a: (
                a.acceptance.update(reviewer_id="other"),
                a.state.update(external_acceptance=dict(a.acceptance)),
            )
        ),
        "replay acceptance binding mismatch",
    ),
    (
        "downstream approved binding",
        _with(lambda a: a.state.update(approved_binding={"x": 1})),
        "replay contains downstream authority",
    ),
    (
        "downstream authorization",
        _with(lambda a: a.state.update(integration_authorization={"x": 1})),
        "replay contains downstream authority",
    ),
    (
        "downstream receipt",
        _with(lambda a: a.state.update(integration_receipt="r")),
        "replay contains downstream authority",
    ),
    (
        "downstream merge",
        _with(lambda a: a.state.update(merge_performed=True)),
        "replay contains downstream authority",
    ),
    (
        "downstream push",
        _with(lambda a: a.state.update(push_performed=1)),
        "replay contains downstream authority",
    ),
    (
        "downstream public",
        _with(lambda a: a.state.update(public_claim_allowed=True)),
        "replay contains downstream authority",
    ),
    (
        "downstream production",
        _with(lambda a: a.state.update(production_ready=True)),
        "replay contains downstream authority",
    ),
]


@pytest.mark.parametrize("label", [label for label, _, _ in VALIDATE_REFUSALS])
def test_validate_refuses_every_broken_binding_in_order(service, label) -> None:
    ((_, mutate, message),) = [item for item in VALIDATE_REFUSALS if item[0] == label]
    a = _adoption()
    mutate(a)
    with pytest.raises(RuntimeError) as caught:
        _validate(service, a)
    assert str(caught.value) == f"external adoption {message}"


@pytest.mark.parametrize(
    "label, mutate",
    [
        ("contract universe is null and dropped from the hash", lambda a: None),
        (
            "contract without an expected_evidence key",
            lambda a: a.state["contract"].pop("expected_evidence"),
        ),
        (
            "contract_hash inside the contract is ignored",
            lambda a: a.state["contract"].update(contract_hash="anything"),
        ),
        ("verified flags False", lambda a: _verified_flag("merge_performed", False)(a)),
        (
            "verified commit created False",
            lambda a: _verified_flag("candidate_commit_created", False)(a),
        ),
        ("verified authority None", lambda a: _verified_flag("authority_change_required", None)(a)),
        (
            "downstream fields absent",
            lambda a: [
                a.state.pop(k)
                for k in (
                    "approved_binding",
                    "integration_authorization",
                    "integration_receipt",
                    "merge_performed",
                    "push_performed",
                    "public_claim_allowed",
                    "production_ready",
                )
            ],
        ),
        (
            "acceptance extra field",
            lambda a: (
                a.acceptance.update(note="x"),
                a.state.update(external_acceptance=dict(a.acceptance)),
            ),
        ),
    ],
)
def test_validate_tolerated_variants(service, label, mutate) -> None:
    a = _adoption()
    mutate(a)
    _validate(service, a)


def test_validate_with_a_non_null_universe_hashes_it(service) -> None:
    a = _adoption()
    a.state["contract"]["expected_evidence"] = {"universe": 1}
    with pytest.raises(RuntimeError, match="contract binding mismatch"):
        _validate(service, a)
    universe_contract = {
        "task_id": TASK,
        "allowed_files": ["src/a.py"],
        "expected_evidence": {"universe": 1},
    }
    a.state["contract_hash"] = _canonical(universe_contract)
    with pytest.raises(RuntimeError, match="receipt binding mismatch"):
        _validate(service, a)  # the receipt still names the old contract hash


def test_validate_claim_ceiling_and_jsonable_are_read_through_the_facade(
    service, monkeypatch
) -> None:
    a = _adoption()
    _validate(service, a)
    seen: list[Any] = []
    real = service_module._jsonable
    monkeypatch.setattr(
        service_module,
        "_jsonable",
        lambda value: (seen.append(type(value).__name__), real(value))[1],
    )
    _validate(service, a)
    assert seen and seen[0] == "dict"
    monkeypatch.setattr(service_module, "_EXTERNAL_ADOPTION_CLAIM_CEILING", ("LATE",))
    with pytest.raises(RuntimeError, match="receipt binding mismatch"):
        _validate(service, a)
    a.state["adoption_receipt"]["claim_ceiling"] = ["LATE"]
    _rehash(a)
    _validate(service, a)


# ---------------------------------------------------------------------------
# reconcile_task dispatch and restart (failure-only production paths)


def test_reconcile_task_routes_to_the_recovery_members_through_self(service, monkeypatch) -> None:
    calls: list[Any] = []
    states = {
        "adopting": {"status": "ADOPTING"},
        "direct-required": {"status": "DIRECT_RECONCILE_REQUIRED"},
        "direct-started": {"status": "DIRECT_STARTED"},
        "direct-applied": {"status": "DIRECT_APPLIED"},
        "direct-verified": {"status": "DIRECT_VERIFIED"},
        "direct-committed": {"status": "DIRECT_COMMITTED"},
        "projected": {"status": "FINAL_BLOCK", "projected": True},
    }
    monkeypatch.setattr(service, "_read_state", lambda task_id: states.get(task_id))
    monkeypatch.setattr(
        service,
        "_resume_external_adoption",
        lambda task_id, state: (calls.append(("resume", task_id, state)), "R")[1],
    )
    monkeypatch.setattr(
        service,
        "_reconcile_direct_failure",
        lambda task_id: (calls.append(("failure", task_id)), "F")[1],
    )
    monkeypatch.setattr(
        service,
        "_reconcile_direct_action",
        lambda task_id: (calls.append(("action", task_id)), "A")[1],
    )
    monkeypatch.setattr(
        service,
        "_projected_pre_apply_recovery_evidence",
        lambda state: (
            calls.append(("project", dict(state))),
            {"e": 1} if state.get("projected") else None,
        )[1],
    )
    monkeypatch.setattr(
        service,
        "_reconcile_projected_pre_apply_failure",
        lambda task_id, evidence: (calls.append(("projected", task_id, evidence)), "P")[1],
    )
    results = {task_id: service.reconcile_task(task_id) for task_id in states}
    assert results == {
        "adopting": "R",
        "direct-required": "F",
        "direct-started": "A",
        "direct-applied": "A",
        "direct-verified": "A",
        "direct-committed": "A",
        "projected": "P",
    }
    assert calls == [
        ("resume", "adopting", {"status": "ADOPTING"}),
        ("failure", "direct-required"),
        ("action", "direct-started"),
        ("action", "direct-applied"),
        ("action", "direct-verified"),
        ("action", "direct-committed"),
        ("project", {"status": "FINAL_BLOCK", "projected": True}),
        ("projected", "projected", {"e": 1}),
    ]


def test_restart_reconciles_an_interrupted_direct_action_without_replay(
    tmp_path, monkeypatch, fixed_now
) -> None:
    controller = (tmp_path / "repo").resolve()
    head = _repo(controller)
    first = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    first._write_state(
        "direct-crash",
        {
            "task_id": "direct-crash",
            "attempt_id": "a1",
            "status": "DIRECT_COMMITTED",
            "request": {
                "controller_repo_root": str(controller),
                "controller_revision": head,
                "allowed_files": ["src/a.py"],
            },
            "status_history": [],
        },
    )
    emitted: list[Any] = []
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_emit_bound_attempt_transition",
        lambda self, result, task_id: emitted.append(task_id),
    )
    # a new service on the same state dir reconciles at start-up
    SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=True, ephemeral=True)
    state = first._read_state("direct-crash")
    assert state is not None and state["status"] == "DIRECT_RECONCILE_REQUIRED"
    assert state["canonical_action"]["reconciliation"]["blocker"] == "UNKNOWN_REQUIRES_RECONCILE"
    assert json.loads(state["error"])["current_head"] == head
    assert emitted == ["direct-crash"]
    # the next start-up closes it: nothing moved since the base
    SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=True, ephemeral=True)
    state = first._read_state("direct-crash")
    assert state is not None and state["status"] == "FINAL_BLOCK"
    assert state["reconciliation_decision"] == "NO_MUTATION_OBSERVED"
    assert _git(controller, "rev-parse", "HEAD") == head


def test_restart_replays_an_interrupted_adoption_from_its_artifacts(tmp_path, monkeypatch) -> None:
    first = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    validation_locator = _store(first, content=VALIDATION, kind="validation")
    acceptance_locator = _store(first, content=ACCEPTANCE, kind="acceptance")
    request = {
        "task_id": TASK,
        "validation_receipt_sha256": _sha(VALIDATION),
        "acceptance_receipt_sha256": _sha(ACCEPTANCE),
    }
    first._write_state(
        TASK,
        {
            "task_id": TASK,
            "status": "ADOPTING",
            "request": request,
            "validation_receipt_locator": validation_locator,
            "acceptance_receipt_locator": acceptance_locator,
        },
    )
    replays: list[Any] = []
    monkeypatch.setattr(
        SelfHostedTaskService,
        "adopt_external_candidate",
        lambda self, replay: (
            replays.append((self.state_dir, dict(replay))),
            {"status": "PENDING_HUMAN_APPROVAL"},
        )[1],
    )
    SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=True, ephemeral=True)
    assert [state_dir for state_dir, _ in replays] == [tmp_path / "state"]
    assert base64.b64decode(replays[0][1]["validation_receipt_b64"]) == VALIDATION
    assert base64.b64decode(replays[0][1]["acceptance_receipt_b64"]) == ACCEPTANCE

    # a removed artifact fails closed on the next restart instead of guessing an outcome;
    # since #2727 the service still starts, leaves the record untouched and reports it
    Path(acceptance_locator).unlink()
    state_path = tmp_path / "state" / f"{TASK}.json"
    before = state_path.read_bytes()
    restarted = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=True, ephemeral=True
    )
    assert len(replays) == 1
    assert state_path.read_bytes() == before
    failures = restarted.lifecycle_status()["reconcile_failures"]
    assert [(f["task_id"], f["error_type"]) for f in failures] == [(TASK, "RuntimeError")]
    assert "unreadable or escaped service state" in failures[0]["error"]
    with pytest.raises(RuntimeError, match="unreadable or escaped service state"):
        restarted.reconcile_task(TASK)


def test_restart_restores_a_lost_pre_apply_projection(tmp_path, fixed_now) -> None:
    first = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    first._write_state(T, _projected_state())
    SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=True, ephemeral=True)
    state = first._read_state(T)
    assert state is not None and state["status"] == "INTEGRATION_FAILED_PRE_APPLY"
    assert (
        state["integration_reconciliation_history"][-1]["projection_sha256"]
        == _expected_projection(_projected_state())["projection_sha256"]
    )
    # idempotent across further restarts
    snapshot = first._read_state_snapshot(T)
    SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=True, ephemeral=True)
    assert first._read_state_snapshot(T) == snapshot


# ---------------------------------------------------------------------------
# late binding of the facade names (patched after a first call that reached the site)


def test_late_subprocess_and_root_in_direct_action(action, monkeypatch, tmp_path) -> None:
    state = {"status": "DIRECT_STARTED", "request": {"controller_revision": HEAD}}
    _reading(action.service, monkeypatch, state)
    first_root = (tmp_path / "first").resolve()
    monkeypatch.setattr(service_module, "CANONICAL_SOURCE_ROOT", first_root)
    action.use([(0, "1\n"), (0, "x\n"), (0, "c\n"), (0, "w\n")])
    action.service._reconcile_direct_action("t")
    assert len(action.log) == 4
    late_root = (tmp_path / "late").resolve()
    late_log: list[Any] = []
    monkeypatch.setattr(service_module, "CANONICAL_SOURCE_ROOT", late_root)
    monkeypatch.setattr(
        service_module,
        "subprocess",
        _Proc([(0, "2\n"), (0, ""), (0, "c2\n"), (0, "w2\n")], late_log),
    )
    action.recorded.clear()
    action.service._reconcile_direct_action("t")
    assert len(action.log) == 4
    assert [argv for argv, _ in late_log] == [
        ("git", "rev-parse", "HEAD"),
        ("git", "status", "--porcelain=v1"),
        ("git", "diff", "--name-only", f"{HEAD}..HEAD"),
        ("git", "diff", "--name-only"),
    ]
    assert {kwargs["cwd"] for _, kwargs in late_log} == {late_root}
    observed = _observed(action.recorded)
    assert observed["current_head"] == "2" and observed["commits_since_base"] == ["c2"]


def test_late_subprocess_root_and_clock_in_direct_failure(failure, monkeypatch, tmp_path) -> None:
    failure.state(request={"controller_revision": HEAD, "allowed_files": ["src/a.py"]})
    monkeypatch.setattr(service_module, "CANONICAL_SOURCE_ROOT", (tmp_path / "first").resolve())
    failure.use(list(CLEAN))
    failure.service._reconcile_direct_failure("t")
    assert len(failure.log) == 6
    late_root = (tmp_path / "late").resolve()
    late_log: list[Any] = []
    monkeypatch.setattr(service_module, "CANONICAL_SOURCE_ROOT", late_root)
    monkeypatch.setattr(
        service_module,
        "subprocess",
        _Proc(
            [(0, f"{CURRENT}\n"), (0, ""), (0, "src/a.py\0"), (0, "w\0"), (0, "s\0"), (0, "")],
            late_log,
        ),
    )
    monkeypatch.setattr(service_module, "_utc_now", lambda: "LATE-NOW")
    failure.checkpoints.clear()
    failure.service._reconcile_direct_failure("t")
    assert len(failure.log) == 6
    assert [argv[1:3] for argv, _ in late_log] == [
        ("rev-parse", "HEAD"),
        ("merge-base", "--is-ancestor"),
        ("diff", "--name-only"),
        ("diff", "--name-only"),
        ("diff", "--cached"),
        ("ls-files", "--others"),
    ]
    assert {kwargs["cwd"] for _, kwargs in late_log} == {late_root}
    ((_, status, values, _),) = failure.checkpoints
    evidence = values["reconciliation_evidence"]
    assert status == "DIRECT_RECONCILE_REQUIRED"
    assert evidence["controller_repo_root"] == str(late_root)
    assert (
        evidence["commits_since_base"],
        evidence["working_tree_changes"],
        evidence["staged_changes"],
    ) == (["src/a.py"], ["w"], ["s"])
    assert values["canonical_action"]["reconciliation"]["reconciled_at"] == "LATE-NOW"


def test_late_names_in_the_safe_close(failure, monkeypatch) -> None:
    failure.state()
    failure.use(list(CLEAN))
    failure.service._reconcile_direct_failure("t")
    monkeypatch.setattr(service_module, "_utc_now", lambda: "LATE-NOW")
    failure.use(list(CLEAN))
    failure.checkpoints.clear()
    failure.service._reconcile_direct_failure("t")
    ((_, status, values, _),) = failure.checkpoints
    assert (
        status == "FINAL_BLOCK"
        and values["canonical_action"]["reconciliation"]["reconciled_at"] == "LATE-NOW"
    )


# ---------------------------------------------------------------------------
# self dispatch: instance / class / subclass patches


def test_direct_members_reach_read_record_and_checkpoint_through_self(
    service, monkeypatch, tmp_path
) -> None:
    calls: list[Any] = []
    monkeypatch.setattr(service_module, "subprocess", _Proc([(0, "")] * 9))
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_read_state",
        lambda self, task_id: (
            calls.append(("class-read", task_id)),
            {"status": "DIRECT_STARTED", "request": {"controller_repo_root": str(tmp_path)}},
        )[1],
    )
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_record_direct_failure",
        lambda self, task_id, blocker, error="": (calls.append(("class-record", blocker)), "CLASS")[
            1
        ],
    )
    assert service._reconcile_direct_action("t") == "CLASS"
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_read_state",
        lambda self, task_id: {
            "status": "DIRECT_RECONCILE_REQUIRED",
            "request": {"controller_repo_root": str(tmp_path)},
        },
    )
    monkeypatch.setattr(
        SelfHostedTaskService,
        "_checkpoint",
        lambda self, task_id, status, values=None, *, attempt_id=None: (
            calls.append(("class-checkpoint", status)),
            "CP",
        )[1],
    )
    assert service._reconcile_direct_failure("t") == "CP"
    assert calls == [
        ("class-read", "t"),
        ("class-record", "UNKNOWN_REQUIRES_RECONCILE"),
        ("class-checkpoint", "DIRECT_RECONCILE_REQUIRED"),
    ]


def test_class_patch_of_a_moved_member_and_undo(tmp_path) -> None:
    svc = SelfHostedTaskService(state_dir=tmp_path / "s", auto_reconcile=False, ephemeral=True)
    name = "_projected_pre_apply_recovery_evidence"
    original = inspect.getattr_static(SelfHostedTaskService, name)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(SelfHostedTaskService, name, staticmethod(lambda state: "patched"))
        assert svc._projected_pre_apply_recovery_evidence({}) == "patched"
    assert inspect.getattr_static(SelfHostedTaskService, name) is original


def test_subclass_overrides_are_dispatched_through_self(tmp_path, monkeypatch) -> None:
    calls: list[Any] = []

    class Sub(SelfHostedTaskService):
        def _read_adoption_artifact(
            self, task_id: str, raw_locator: str, digest: str, kind: str
        ) -> bytes:
            calls.append(("read", kind))
            return {"validation": VALIDATION, "acceptance": ACCEPTANCE}[kind]

        def adopt_external_candidate(self, raw_request: Any) -> Any:
            calls.append(("adopt", sorted(raw_request)))
            return "SUB"

        @staticmethod
        def _projected_pre_apply_recovery_evidence(state: Any) -> Any:
            calls.append(("project",))
            return dict(state["evidence"])

        def _mutate_state(self, task_id: str, mutator: Any) -> Any:
            current = {"evidence": {"projection_sha256": "p"}, "status_history": []}
            calls.append(("mutate", task_id))
            mutator(current)
            return current

    svc = Sub(state_dir=tmp_path / "s", auto_reconcile=False, ephemeral=True)
    request = {
        "task_id": TASK,
        "validation_receipt_sha256": _sha(VALIDATION),
        "acceptance_receipt_sha256": _sha(ACCEPTANCE),
    }
    state = {
        "request": request,
        "validation_receipt_locator": "v",
        "acceptance_receipt_locator": "a",
    }
    assert svc._resume_external_adoption(TASK, state) == "SUB"
    result = svc._reconcile_projected_pre_apply_failure("x", {"projection_sha256": "p"})
    assert result["status"] == "INTEGRATION_FAILED_PRE_APPLY"
    assert calls == [
        ("read", "validation"),
        ("read", "acceptance"),
        (
            "adopt",
            [
                "acceptance_receipt_b64",
                "acceptance_receipt_sha256",
                "task_id",
                "validation_receipt_b64",
                "validation_receipt_sha256",
            ],
        ),
        ("mutate", "x"),
        ("project",),
    ]


# --- #2727: one unrecoverable record must not stop the service from starting ----------


def _seed_records(state_dir: Path, task_ids: list[str]) -> SelfHostedTaskService:
    service = SelfHostedTaskService(state_dir=state_dir, auto_reconcile=False, ephemeral=True)
    for task_id in task_ids:
        service._write_state(task_id, {"task_id": task_id, "status": "SUBMITTED"})
    return service


def test_reconcile_tasks_isolates_a_failing_record_and_continues(
    tmp_path, monkeypatch, caplog
) -> None:
    service = _seed_records(tmp_path / "state", ["a-task", "b-bad", "c-task"])
    seen: list[str] = []

    def reconcile(self, task_id: str):
        seen.append(task_id)
        if task_id == "b-bad":
            raise RuntimeError("evidence artifact is gone")
        return {"task_id": task_id, "status": "SUBMITTED"}

    monkeypatch.setattr(SelfHostedTaskService, "reconcile_task", reconcile)
    with caplog.at_level("ERROR", logger=service_module.__name__):
        states = service.reconcile_tasks()

    assert seen == ["a-task", "b-bad", "c-task"]
    assert [state["task_id"] for state in states] == ["a-task", "c-task"]
    failures = service.lifecycle_status()["reconcile_failures"]
    assert [(f["task_id"], f["error_type"], f["error"]) for f in failures] == [
        ("b-bad", "RuntimeError", "evidence artifact is gone")
    ]
    assert failures[0]["at"]
    assert any(
        "b-bad" in record.getMessage() and "left untouched" in record.getMessage()
        for record in caplog.records
    )


def test_startup_survives_a_failing_record(tmp_path, monkeypatch) -> None:
    _seed_records(tmp_path / "state", ["a-task", "b-bad"])

    def reconcile(self, task_id: str):
        if task_id == "b-bad":
            raise ValueError("corrupt record")
        return {"task_id": task_id, "status": "SUBMITTED"}

    monkeypatch.setattr(SelfHostedTaskService, "reconcile_task", reconcile)
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=True, ephemeral=True
    )

    assert [f["task_id"] for f in service.lifecycle_status()["reconcile_failures"]] == ["b-bad"]


def test_reconcile_failure_clears_after_a_successful_pass(tmp_path, monkeypatch) -> None:
    service = _seed_records(tmp_path / "state", ["b-bad"])
    broken = {"value": True}

    def reconcile(self, task_id: str):
        if broken["value"]:
            raise RuntimeError("transient")
        return {"task_id": task_id, "status": "SUBMITTED"}

    monkeypatch.setattr(SelfHostedTaskService, "reconcile_task", reconcile)
    service.reconcile_tasks()
    assert [f["task_id"] for f in service.lifecycle_status()["reconcile_failures"]] == ["b-bad"]
    broken["value"] = False
    assert [state["task_id"] for state in service.reconcile_tasks()] == ["b-bad"]
    assert service.lifecycle_status()["reconcile_failures"] == []


def test_reconcile_tasks_does_not_swallow_base_exceptions(tmp_path, monkeypatch) -> None:
    service = _seed_records(tmp_path / "state", ["a-task"])

    def reconcile(self, task_id: str):
        raise KeyboardInterrupt

    monkeypatch.setattr(SelfHostedTaskService, "reconcile_task", reconcile)
    with pytest.raises(KeyboardInterrupt):
        service.reconcile_tasks()


def test_lifecycle_status_reports_no_reconcile_failures_by_default(tmp_path) -> None:
    service = _seed_records(tmp_path / "state", [])
    assert service.lifecycle_status()["reconcile_failures"] == []


def test_reconcile_tasks_fails_fast_when_every_record_fails(tmp_path, monkeypatch) -> None:
    service = _seed_records(tmp_path / "state", ["a-task", "b-task"])

    def reconcile(self, task_id: str):
        raise TypeError(f"schema bug on {task_id}")

    monkeypatch.setattr(SelfHostedTaskService, "reconcile_task", reconcile)
    with pytest.raises(TypeError, match="^schema bug on a-task$"):
        service.reconcile_tasks()
    with pytest.raises(TypeError, match="^schema bug on a-task$"):
        SelfHostedTaskService(state_dir=tmp_path / "state", auto_reconcile=True, ephemeral=True)
    assert [f["task_id"] for f in service.reconcile_failures()] == ["a-task", "b-task"]


def test_reconcile_tasks_isolates_a_single_failing_record(tmp_path, monkeypatch) -> None:
    service = _seed_records(tmp_path / "state", ["only-task"])

    def reconcile(self, task_id: str):
        raise RuntimeError("bad record")

    monkeypatch.setattr(SelfHostedTaskService, "reconcile_task", reconcile)
    assert service.reconcile_tasks() == []
    assert [f["task_id"] for f in service.reconcile_failures()] == ["only-task"]


def test_reconcile_failure_of_a_removed_record_is_dropped(tmp_path, monkeypatch) -> None:
    service = _seed_records(tmp_path / "state", ["a-task", "b-bad"])

    def reconcile(self, task_id: str):
        if task_id == "b-bad":
            raise RuntimeError("bad record")
        return {"task_id": task_id, "status": "SUBMITTED"}

    monkeypatch.setattr(SelfHostedTaskService, "reconcile_task", reconcile)
    service.reconcile_tasks()
    assert [f["task_id"] for f in service.reconcile_failures()] == ["b-bad"]
    (tmp_path / "state" / "b-bad.json").unlink()
    service.reconcile_tasks()
    assert service.reconcile_failures() == []


def test_reconcile_failures_returns_copies(tmp_path, monkeypatch) -> None:
    service = _seed_records(tmp_path / "state", ["a-task", "b-bad"])

    def reconcile(self, task_id: str):
        if task_id == "b-bad":
            raise RuntimeError("bad record")
        return {"task_id": task_id, "status": "SUBMITTED"}

    monkeypatch.setattr(SelfHostedTaskService, "reconcile_task", reconcile)
    service.reconcile_tasks()
    service.reconcile_failures()[0]["error"] = "tampered"
    assert service.reconcile_failures()[0]["error"] == "bad record"


def test_reconcile_tool_reports_failures(tmp_path, monkeypatch) -> None:
    from nexus.orchestrator.self_hosted_mcp import NexusSelfHostedMCPServer

    service = _seed_records(tmp_path / "state", ["a-task", "b-bad"])

    def reconcile(self, task_id: str):
        if task_id == "b-bad":
            raise RuntimeError("bad record")
        return {"task_id": task_id, "status": "SUBMITTED"}

    monkeypatch.setattr(SelfHostedTaskService, "reconcile_task", reconcile)
    server = NexusSelfHostedMCPServer.__new__(NexusSelfHostedMCPServer)
    server.service = service
    result = server._call_tool("nexus_self_hosted_reconcile_tasks", {})
    assert [state["task_id"] for state in result["tasks"]] == ["a-task"]
    assert [f["task_id"] for f in result["reconcile_failures"]] == ["b-bad"]
